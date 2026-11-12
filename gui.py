"""桌面聊天入口：主线程操作窗口，后台线程接收回答。"""

import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk
from pathlib import Path

from ai_client import APIError, stream_reply
from config import load_config
from exporter import export_session
from prompt_templates import TEMPLATES, build_prompt
from session_manager import DATA_FILE, LEGACY_FILE
from config import CONFIG_FILE
from session_manager import SessionManager


class ChatApp:
    """管理聊天窗口、后台请求和消息显示。"""

    def __init__(self, root, config, manager):
        self.root = root
        self.config = config
        self.manager = manager
        self.messages = manager.current_session()["messages"]
        self.drafts = {}
        self.events = queue.Queue()
        self.busy = False
        self.pieces = []

        root.title("AI 智能学习助手")
        root.geometry("800x600")
        root.minsize(500, 350)
        sidebar = ttk.Frame(root, padding=8)
        sidebar.pack(side="left", fill="y")
        self.new_button = ttk.Button(sidebar, text="新建会话", command=self.new_session)
        self.new_button.pack(fill="x", pady=(0, 8))
        self.session_list = tk.Listbox(sidebar, width=22, exportselection=False)
        self.session_list.pack(fill="both", expand=True)
        self.session_list.bind("<<ListboxSelect>>", self.switch_session)
        self.rename_button = ttk.Button(sidebar, text="重命名", command=self.rename_session)
        self.rename_button.pack(fill="x", pady=(8, 0))
        self.delete_button = ttk.Button(sidebar, text="删除会话", command=self.delete_session)
        self.delete_button.pack(fill="x", pady=(8, 0))
        self.export_button = ttk.Button(sidebar, text="导出会话", command=self.export_current)
        self.export_button.pack(fill="x", pady=(8, 0))
        ttk.Button(sidebar, text="收藏问答", command=self.choose_favorite).pack(fill="x", pady=(8, 0))
        ttk.Button(sidebar, text="查看收藏夹", command=self.show_favorites).pack(fill="x", pady=(8, 0))
        content = ttk.Frame(root)
        content.pack(side="right", fill="both", expand=True)
        self.chat = scrolledtext.ScrolledText(content, wrap="word", state="disabled")
        self.chat.pack(fill="both", expand=True, padx=12, pady=12)

        template_bar = ttk.Frame(content)
        template_bar.pack(fill="x", padx=12, pady=(0, 8))
        ttk.Label(template_bar, text="学习模板：").pack(side="left")
        self.template_name = tk.StringVar(value=next(iter(TEMPLATES)))
        ttk.Combobox(
            template_bar, textvariable=self.template_name, values=list(TEMPLATES),
            state="readonly", width=14
        ).pack(side="left", padx=4)
        ttk.Button(template_bar, text="应用到输入框", command=self.apply_template).pack(side="left")

        self.input = tk.Text(content, height=4, wrap="word")
        self.input.pack(fill="x", padx=12)
        self.input.bind("<Control-Return>", self.send)

        bar = ttk.Frame(content)
        bar.pack(fill="x", padx=12, pady=12)
        self.status = tk.StringVar(value="就绪：Ctrl+Enter 发送，Enter 换行")
        ttk.Label(bar, textvariable=self.status).pack(side="left")
        self.send_button = ttk.Button(bar, text="发送", command=self.send)
        self.send_button.pack(side="right")

        self.refresh_sessions()
        self.render_session()
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(100, self.poll_events)

    def choose_favorite(self):
        """从当前会话选择已完成的问答。"""
        if self.busy:
            self.status.set("请等待回答完成后再收藏")
            return
        pairs = self.manager.answered_pairs()
        if not pairs:
            messagebox.showinfo("没有问答", "当前会话还没有完整问答。", parent=self.root)
            return
        self.open_collection(pairs, False)

    def show_favorites(self):
        """显示收藏副本，支持移除。"""
        self.open_collection(list(self.manager.data.get("favorites", [])), True)

    def open_collection(self, items, browsing):
        """以列表和预览窗口展示问答；弹窗期间阻止切换原会话。"""
        window = tk.Toplevel(self.root)
        window.title("收藏夹" if browsing else "选择要收藏的问答")
        window.geometry("650x500")
        window.transient(self.root)
        window.grab_set()
        listing = tk.Listbox(window, height=7, exportselection=False)
        listing.pack(fill="x", padx=10, pady=10)
        preview = scrolledtext.ScrolledText(window, wrap="word", state="disabled")
        preview.pack(fill="both", expand=True, padx=10)

        def refresh():
            listing.delete(0, "end")
            for item in items:
                question = item["question"] if browsing else item[0]
                listing.insert("end", question.replace("\n", " ")[:70])
            preview.configure(state="normal")
            preview.delete("1.0", "end")
            preview.configure(state="disabled")

        def select(event=None):
            selection = listing.curselection()
            if not selection:
                return
            item = items[selection[0]]
            question, answer = (item["question"], item["answer"]) if browsing else item
            source = f"收藏时的会话：{item['source_name']}\n\n" if browsing else ""
            preview.configure(state="normal")
            preview.delete("1.0", "end")
            preview.insert("end", f"{source}你：{question}\n\nAI：{answer}")
            preview.configure(state="disabled")

        def action():
            selection = listing.curselection()
            if not selection:
                return
            index = selection[0]
            if browsing:
                if not messagebox.askyesno("移除收藏", "确定移除此条收藏吗？原会话不受影响。", parent=window):
                    return
                self.manager.remove_favorite(items[index]["id"])
                items.pop(index)
                refresh()
            else:
                if not self.manager.add_favorite(*items[index]):
                    messagebox.showinfo("已收藏", "该问答已经在收藏夹中。", parent=window)
                    return
            self.save()
            self.status.set("收藏夹已更新")

        listing.bind("<<ListboxSelect>>", select)
        ttk.Button(window, text="移除选中收藏" if browsing else "收藏选中问答", command=action).pack(pady=10)
        refresh()

    def apply_template(self):
        """包装输入内容，留给用户审阅后手动发送。"""
        content = self.input.get("1.0", "end-1c")
        if any(content.startswith(template.split("\n")[0]) for template in TEMPLATES.values()):
            messagebox.showinfo("模板已应用", "请先编辑或清空现有模板，避免重复嵌套。", parent=self.root)
            return
        try:
            prompt = build_prompt(self.template_name.get(), content)
        except ValueError as error:
            self.status.set(str(error))
            return
        self.input.delete("1.0", "end")
        self.input.insert("1.0", prompt)
        self.input.focus_set()
        self.status.set("模板已填入，可编辑后发送")

    def refresh_sessions(self):
        """刷新名称列表，并保留当前选中项。"""
        self.session_list.delete(0, "end")
        for index, session in enumerate(self.manager.data["sessions"]):
            self.session_list.insert("end", session["name"])
            if session["id"] == self.manager.data["current_session_id"]:
                self.session_list.selection_set(index)

    def render_session(self):
        """显示当前会话的历史。"""
        self.chat.configure(state="normal")
        self.chat.delete("1.0", "end")
        self.chat.configure(state="disabled")
        self.root.title(f"AI 智能学习助手 - {self.manager.current_session()['name']}")
        for message in self.messages:
            speaker = "你" if message["role"] == "user" else "AI"
            self.append_text(f"{speaker}：{message['content']}\n\n")
        if self.config["mode"] == "api":
            self.append_text("提示：当前使用真实 API，历史会发送到配置的服务商。\n\n")
        else:
            self.append_text("提示：当前使用模拟 AI。\n\n")

    def activate_session(self):
        """切换数据引用，恢复各会话独立的输入草稿。"""
        self.messages = self.manager.current_session()["messages"]
        self.input.delete("1.0", "end")
        self.input.insert("1.0", self.drafts.get(self.manager.data["current_session_id"], ""))
        self.refresh_sessions()
        self.render_session()
        self.save()
        self.status.set("就绪：Ctrl+Enter 发送，Enter 换行")

    def new_session(self):
        """询问名称，创建并显示新会话。"""
        if self.busy:
            return
        name = simpledialog.askstring("新建会话", "请输入会话名称：", parent=self.root)
        if name is None:
            return
        if not name.strip():
            messagebox.showwarning("名称无效", "会话名称不能为空。")
            return
        self.drafts[self.manager.data["current_session_id"]] = self.input.get("1.0", "end-1c")
        self.manager.create_session(name)
        self.activate_session()

    def switch_session(self, event=None):
        """空闲时切换，生成期间保持原会话不变。"""
        if self.busy:
            return
        selection = self.session_list.curselection()
        if not selection:
            return
        identifier = self.manager.data["sessions"][selection[0]]["id"]
        if identifier == self.manager.data["current_session_id"]:
            return
        self.drafts[self.manager.data["current_session_id"]] = self.input.get("1.0", "end-1c")
        self.manager.select_session(identifier)
        self.activate_session()

    def rename_session(self):
        """修改当前名称，保留正在编辑的草稿。"""
        if self.busy:
            return
        name = simpledialog.askstring(
            "重命名", "请输入新名称：",
            initialvalue=self.manager.current_session()["name"], parent=self.root
        )
        if name is None:
            return
        try:
            self.manager.rename_current(name)
        except ValueError as error:
            messagebox.showwarning("名称无效", str(error))
            return
        self.refresh_sessions()
        self.root.title(f"AI 智能学习助手 - {self.manager.current_session()['name']}")
        self.save()

    def delete_session(self):
        """确认后删除当前会话及其草稿。"""
        if self.busy:
            return
        session = self.manager.current_session()
        if not messagebox.askyesno(
            "删除会话", f"确定删除“{session['name']}”及其全部消息吗？此操作无法撤销。",
            parent=self.root
        ):
            return
        self.drafts.pop(session["id"], None)
        self.manager.delete_current()
        self.activate_session()

    def export_current(self):
        """选择导出位置，避免覆盖程序和内部数据文件。"""
        if self.busy:
            return
        session = self.manager.current_session()
        if not session["messages"]:
            messagebox.showinfo("没有记录", "当前会话还没有消息。", parent=self.root)
            return
        filename = filedialog.asksaveasfilename(
            parent=self.root, title="导出当前会话", initialfile="聊天记录.txt",
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("Markdown 文件", "*.md")]
        )
        if not filename:
            return
        path = Path(filename).resolve()
        protected = {Path(item).resolve() for item in (DATA_FILE, LEGACY_FILE, CONFIG_FILE, self.manager.path)}
        project = Path(__file__).resolve().parent
        if path in protected or (path.parent == project and path.exists()):
            messagebox.showwarning("无法导出", "请选择新文件，避免覆盖项目文件。", parent=self.root)
            return
        try:
            export_session(session, path)
        except (OSError, ValueError) as error:
            messagebox.showerror("导出失败", str(error), parent=self.root)
            return
        self.status.set(f"已导出：{path.name}")

    def append_text(self, text):
        """只在主线程中更新聊天区域。"""
        self.chat.configure(state="normal")
        self.chat.insert("end", text)
        self.chat.configure(state="disabled")
        self.chat.see("end")

    def save(self):
        """保存失败时在窗口中明确提醒用户。"""
        try:
            self.manager.save()
        except (OSError, ValueError):
            messagebox.showwarning("保存失败", "记录未能保存，请检查目录权限和磁盘空间。")

    def send(self, event=None):
        """保存问题并启动一次后台请求，避免重复发送。"""
        if self.busy:
            return "break"
        question = self.input.get("1.0", "end-1c").strip()
        if not question:
            self.status.set("问题不能为空")
            return "break"
        self.messages.append({"role": "user", "content": question})
        self.save()
        self.input.delete("1.0", "end")
        self.append_text(f"你：{question}\n\nAI：")
        self.pieces = []
        self.busy = True
        self.send_button.configure(state="disabled")
        self.new_button.configure(state="disabled")
        self.rename_button.configure(state="disabled")
        self.delete_button.configure(state="disabled")
        self.export_button.configure(state="disabled")
        self.session_list.configure(state="disabled")
        self.status.set("正在接收回答，可以继续编辑下一个问题")
        snapshot = [message.copy() for message in self.messages]
        threading.Thread(target=self.receive, args=(snapshot,), daemon=True).start()
        return "break"

    def receive(self, messages):
        """后台只写队列，不读取或修改窗口控件。"""
        try:
            for piece in stream_reply(messages, self.config):
                self.events.put(("piece", piece))
            self.events.put(("done", ""))
        except APIError as error:
            self.events.put(("error", str(error)))
        except Exception:
            self.events.put(("error", "请求发生意外错误，请稍后重试。"))

    def poll_events(self):
        """主线程定时读取队列；限制每轮数量，保持界面响应。"""
        for _ in range(100):
            try:
                kind, text = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "piece":
                self.pieces.append(text)
                self.append_text(text)
                continue
            if kind == "done":
                self.messages.append({"role": "assistant", "content": "".join(self.pieces)})
                self.save()
                self.append_text("\n\n")
                self.status.set("回答完成")
            else:
                self.append_text(f"\n[请求失败：{text}；部分回答未保存]\n\n")
                self.status.set("请求失败，可以继续提问")
            self.busy = False
            self.send_button.configure(state="normal")
            self.new_button.configure(state="normal")
            self.rename_button.configure(state="normal")
            self.delete_button.configure(state="normal")
            self.export_button.configure(state="normal")
            self.session_list.configure(state="normal")
        self.root.after(100, self.poll_events)

    def close(self):
        """生成期间确认关闭，避免误丢尚未完成的回答。"""
        if self.busy and not messagebox.askyesno(
            "关闭窗口", "回答尚未完成，关闭将丢弃本次未完成回答。确定关闭吗？"
        ):
            return
        self.save()
        self.root.destroy()


def main():
    """加载配置和历史后启动窗口，不显示密钥。"""
    root = tk.Tk()
    root.withdraw()
    try:
        config = load_config()
    except ValueError as error:
        messagebox.showerror("配置错误", str(error))
        root.destroy()
        return
    try:
        manager = SessionManager()
    except (OSError, ValueError):
        messagebox.showerror("历史读取失败", "请检查 sessions.json 或旧历史文件，原文件不会被覆盖。")
        root.destroy()
        return
    ChatApp(root, config, manager)
    root.deiconify()
    root.mainloop()


if __name__ == "__main__":
    main()
