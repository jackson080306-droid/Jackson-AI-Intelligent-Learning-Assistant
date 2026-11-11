"""桌面聊天入口：主线程操作窗口，后台线程接收回答。"""

import queue
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

from ai_client import APIError, stream_reply
from config import load_config
from main import load_messages, save_messages


class ChatApp:
    """管理聊天窗口、后台请求和消息显示。"""

    def __init__(self, root, config, messages):
        self.root = root
        self.config = config
        self.messages = messages
        self.events = queue.Queue()
        self.busy = False
        self.pieces = []

        root.title("AI 智能学习助手")
        root.geometry("800x600")
        root.minsize(500, 350)
        self.chat = scrolledtext.ScrolledText(root, wrap="word", state="disabled")
        self.chat.pack(fill="both", expand=True, padx=12, pady=12)

        self.input = tk.Text(root, height=4, wrap="word")
        self.input.pack(fill="x", padx=12)
        self.input.bind("<Control-Return>", self.send)

        bar = ttk.Frame(root)
        bar.pack(fill="x", padx=12, pady=12)
        self.status = tk.StringVar(value="就绪：Ctrl+Enter 发送，Enter 换行")
        ttk.Label(bar, textvariable=self.status).pack(side="left")
        self.send_button = ttk.Button(bar, text="发送", command=self.send)
        self.send_button.pack(side="right")

        for message in messages:
            speaker = "你" if message["role"] == "user" else "AI"
            self.append_text(f"{speaker}：{message['content']}\n\n")
        if config["mode"] == "api":
            self.append_text("提示：当前使用真实 API，历史会发送到配置的服务商。\n\n")
        else:
            self.append_text("提示：当前使用模拟 AI。\n\n")
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(100, self.poll_events)

    def append_text(self, text):
        """只在主线程中更新聊天区域。"""
        self.chat.configure(state="normal")
        self.chat.insert("end", text)
        self.chat.configure(state="disabled")
        self.chat.see("end")

    def save(self):
        """保存失败时在窗口中明确提醒用户。"""
        if not save_messages(self.messages):
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
    messages = load_messages()
    if messages is None:
        messagebox.showerror("历史读取失败", "请检查 chat_history.json，原文件不会被覆盖。")
        root.destroy()
        return
    ChatApp(root, config, messages)
    root.deiconify()
    root.mainloop()


if __name__ == "__main__":
    main()
