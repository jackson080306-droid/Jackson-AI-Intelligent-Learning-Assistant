"""桌面聊天入口：主线程操作窗口，后台线程接收回答。"""

import queue
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, simpledialog, ttk

from ai_client import APIError, stream_reply
from config import load_config
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
        content = ttk.Frame(root)
        content.pack(side="right", fill="both", expand=True)
        self.chat = scrolledtext.ScrolledText(content, wrap="word", state="disabled")
        self.chat.pack(fill="both", expand=True, padx=12, pady=12)

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
