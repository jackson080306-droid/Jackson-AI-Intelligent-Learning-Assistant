"""本地 API 配置编辑窗口。"""

import tkinter as tk
from tkinter import messagebox, ttk

from config import save_config


def open_settings(parent, current, on_saved):
    """编辑副本，保存成功后通知主窗口；取消不改变配置。"""
    window = tk.Toplevel(parent)
    window.title("API 配置")
    window.transient(parent)
    window.grab_set()
    window.columnconfigure(1, weight=1)
    values = {name: tk.StringVar(value=str(current[name])) for name in (
        "mode", "base_url", "model", "api_key", "timeout"
    )}
    labels = {
        "mode": "模式", "base_url": "接口基础地址", "model": "模型名称",
        "api_key": "API Key", "timeout": "超时（秒）",
    }
    key_entry = None
    for row, (name, variable) in enumerate(values.items()):
        ttk.Label(window, text=labels[name]).grid(row=row, column=0, padx=12, pady=8, sticky="w")
        if name == "mode":
            widget = ttk.Combobox(window, textvariable=variable, values=("mock", "api"), state="readonly")
        else:
            widget = ttk.Entry(window, textvariable=variable, width=46, show="*" if name == "api_key" else "")
        widget.grid(row=row, column=1, padx=12, pady=8, sticky="ew")
        if name == "api_key":
            key_entry = widget
    visible = tk.BooleanVar(value=False)
    ttk.Checkbutton(
        window, text="显示密钥", variable=visible,
        command=lambda: key_entry.configure(show="" if visible.get() else "*")
    ).grid(row=5, column=1, sticky="w", padx=12)
    ttk.Label(
        window, text="基础地址不要包含 /chat/completions。\n密钥以明文保存在本地 config.json，请勿分享该文件。",
        wraplength=410
    ).grid(row=6, column=0, columnspan=2, padx=12, pady=12)

    def save():
        settings = {name: variable.get() for name, variable in values.items()}
        try:
            settings["timeout"] = int(settings["timeout"])
        except ValueError:
            messagebox.showerror("配置错误", "超时必须是正整数秒数。", parent=window)
            return
        try:
            updated = save_config(settings)
        except ValueError as error:
            messagebox.showerror("配置错误", str(error), parent=window)
            return
        except OSError:
            messagebox.showerror("保存失败", "无法写入本地配置，请检查权限和磁盘空间。", parent=window)
            return
        on_saved(updated)
        window.destroy()

    buttons = ttk.Frame(window)
    buttons.grid(row=7, column=0, columnspan=2, pady=12)
    ttk.Button(buttons, text="保存并应用", command=save).pack(side="left", padx=8)
    ttk.Button(buttons, text="取消", command=window.destroy).pack(side="left", padx=8)
