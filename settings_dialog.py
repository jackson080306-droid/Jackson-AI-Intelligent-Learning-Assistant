"""本地 API 配置编辑窗口。"""

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from config import DEFAULT_CONFIG, load_profiles, save_profiles, validate_config


def open_settings(parent, current, on_saved):
    """编辑副本，保存成功后通知主窗口；取消不改变配置。"""
    try:
        collection = load_profiles()
    except ValueError as error:
        messagebox.showerror("配置错误", str(error), parent=parent)
        return
    profiles = collection["profiles"]
    selected = collection["active_profile"]
    window = tk.Toplevel(parent)
    window.title("API 配置")
    window.transient(parent)
    window.grab_set()
    window.columnconfigure(1, weight=1)
    profile_name = tk.StringVar(value=selected)
    ttk.Label(window, text="配置名称").grid(row=0, column=0, padx=12, pady=8)
    selector = ttk.Combobox(window, textvariable=profile_name, values=list(profiles), state="readonly")
    selector.grid(row=0, column=1, padx=12, pady=8, sticky="ew")
    current = profiles[selected]
    values = {name: tk.StringVar(value=str(current[name])) for name in (
        "mode", "base_url", "model", "api_key", "timeout"
    )}
    labels = {
        "mode": "模式", "base_url": "接口基础地址", "model": "模型名称",
        "api_key": "API Key", "timeout": "超时（秒）",
    }
    key_entry = None
    for row, (name, variable) in enumerate(values.items(), start=2):
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
    ).grid(row=7, column=1, sticky="w", padx=12)
    ttk.Label(
        window, text="基础地址不要包含 /chat/completions。\n密钥以明文保存在本地 config.json，请勿分享该文件。",
        wraplength=410
    ).grid(row=8, column=0, columnspan=2, padx=12, pady=12)

    def remember():
        """切换前保存表单到内存；校验失败时停留在原配置。"""
        settings = {name: variable.get() for name, variable in values.items()}
        try:
            settings["timeout"] = int(settings["timeout"])
        except ValueError:
            messagebox.showerror("配置错误", "超时必须是正整数秒数。", parent=window)
            return False
        try:
            profiles[selected] = validate_config(settings)
        except ValueError as error:
            messagebox.showerror("配置错误", str(error), parent=window)
            return False
        return True

    def display(name):
        nonlocal selected
        selected = name
        profile_name.set(name)
        selector.configure(values=list(profiles))
        for field, variable in values.items():
            variable.set(str(profiles[name][field]))
        visible.set(False)
        key_entry.configure(show="*")

    def switch(event=None):
        target = profile_name.get()
        if remember():
            display(target)
        else:
            profile_name.set(selected)

    def new_profile():
        if not remember():
            return
        name = simpledialog.askstring("新建配置", "输入配置名称：", parent=window)
        if name is None:
            return
        name = name.strip()
        if not name or name in profiles:
            messagebox.showerror("名称错误", "名称不能为空，也不能与已有配置重复。", parent=window)
            return
        profiles[name] = DEFAULT_CONFIG.copy()
        display(name)

    def delete_profile():
        if len(profiles) == 1:
            messagebox.showinfo("无法删除", "至少需要保留一套配置。", parent=window)
            return
        if messagebox.askyesno("删除配置", f"删除“{selected}”？保存后生效。", parent=window):
            del profiles[selected]
            display(next(iter(profiles)))

    selector.bind("<<ComboboxSelected>>", switch)
    profile_buttons = ttk.Frame(window)
    profile_buttons.grid(row=1, column=0, columnspan=2)
    ttk.Button(profile_buttons, text="新建配置", command=new_profile).pack(side="left", padx=8)
    ttk.Button(profile_buttons, text="删除配置", command=delete_profile).pack(side="left", padx=8)

    def save():
        if not remember():
            return
        try:
            updated = save_profiles({"active_profile": selected, "profiles": profiles})
        except ValueError as error:
            messagebox.showerror("配置错误", str(error), parent=window)
            return
        except OSError:
            messagebox.showerror("保存失败", "无法写入本地配置，请检查权限和磁盘空间。", parent=window)
            return
        on_saved(updated["profiles"][selected].copy())
        window.destroy()

    buttons = ttk.Frame(window)
    buttons.grid(row=9, column=0, columnspan=2, pady=12)
    ttk.Button(buttons, text="保存并应用", command=save).pack(side="left", padx=8)
    ttk.Button(buttons, text="取消", command=window.destroy).pack(side="left", padx=8)
