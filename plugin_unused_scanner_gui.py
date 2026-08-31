#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
未使用插件扫描工具 —— GUI 版（tkinter，零第三方依赖）

带图形界面：可手动添加/删除工作流输入目录、选择报告输出目录，点击「开始扫描」
后在窗口内按「未使用 / 已使用 / 无法确定」三类展示插件清单，并可一键保存报告。

运行：
  python plugin_unused_scanner_gui.py
打包：见 build_plugin_scanner_exe.bat（已改为 --noconsole GUI 版）
"""

import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

# 确保能找到同目录下的核心模块（脚本态与 PyInstaller 打包态都适用）
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import plugin_unused_scanner as core


class ScannerGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ComfyUI 未使用插件扫描工具")
        self.geometry("860x640")
        try:
            self.iconbitmap()
        except Exception:
            pass

        self.workflow_dirs = []          # 输入工作流目录列表
        self.include_disabled = tk.BooleanVar(value=False)
        self.report_text = ""            # 最近一次报告文本

        self._build_widgets()
        self._init_defaults()

    # ---------------- UI 构建 ----------------
    def _build_widgets(self):
        pad = {"padx": 8, "pady": 4}

        # 顶部：ComfyUI 路径（自动探测，可改）
        f_top = ttk.LabelFrame(self, text="ComfyUI 安装路径", padding=8)
        f_top.pack(fill="x", **pad)
        self.comfy_var = tk.StringVar()
        ttk.Entry(f_top, textvariable=self.comfy_var).pack(side="left", fill="x", expand=True)
        ttk.Button(f_top, text="浏览...", command=self._pick_comfy).pack(side="left", padx=(6, 0))

        # 输入工作流目录
        f_in = ttk.LabelFrame(self, text="工作流输入目录（可添加多个，递归扫描 .json）", padding=8)
        f_in.pack(fill="x", **pad)
        self.dir_listbox = tk.Listbox(f_in, height=4)
        self.dir_listbox.pack(fill="x", expand=True)
        f_in_btn = ttk.Frame(f_in)
        f_in_btn.pack(fill="x", pady=(4, 0))
        ttk.Button(f_in_btn, text="添加目录", command=self._add_dir).pack(side="left")
        ttk.Button(f_in_btn, text="移除选中", command=self._remove_dir).pack(side="left", padx=(6, 0))
        ttk.Button(f_in_btn, text="使用默认(user/default)", command=self._use_default).pack(side="left", padx=(6, 0))
        ttk.Checkbutton(f_in_btn, text="同时列出 .disabled 已禁用插件", variable=self.include_disabled).pack(side="right")

        # 输出目录
        f_out = ttk.LabelFrame(self, text="报告输出目录（留空则仅窗口显示，不写文件）", padding=8)
        f_out.pack(fill="x", **pad)
        self.out_var = tk.StringVar()
        ttk.Entry(f_out, textvariable=self.out_var).pack(side="left", fill="x", expand=True)
        ttk.Button(f_out, text="浏览...", command=self._pick_out).pack(side="left", padx=(6, 0))

        # 操作按钮
        f_act = ttk.Frame(self)
        f_act.pack(fill="x", **pad)
        self.start_btn = ttk.Button(f_act, text="开始扫描", command=self._on_start)
        self.start_btn.pack(side="left")
        ttk.Button(f_act, text="保存报告", command=self._save_report).pack(side="left", padx=(6, 0))
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(f_act, textvariable=self.status_var, foreground="#555").pack(side="right")

        # 结果展示（三态合并在一块带颜色的文本区）
        f_res = ttk.LabelFrame(self, text="扫描结果", padding=8)
        f_res.pack(fill="both", expand=True, **pad)
        self.result_box = scrolledtext.ScrolledText(f_res, wrap="word", font=("Consolas", 10))
        self.result_box.pack(fill="both", expand=True)
        self.result_box.tag_config("unused", foreground="#c0392b")       # 红：可删
        self.result_box.tag_config("used", foreground="#27ae60")         # 绿：已用
        self.result_box.tag_config("undetermined", foreground="#e67e22")  # 橙：无法确定
        self.result_box.tag_config("disabled", foreground="#7f8c8d")      # 灰：已禁用
        self.result_box.tag_config("header", foreground="#2980b9", font=("Consolas", 10, "bold"))
        self.result_box.config(state="disabled")

    def _init_defaults(self):
        comfy = core.detect_comfy_path()
        self.comfy_var.set(os.path.normpath(comfy))
        self._use_default()

    # ---------------- 目录操作 ----------------
    def _pick_comfy(self):
        d = filedialog.askdirectory(title="选择 ComfyUI 根目录")
        if d:
            self.comfy_var.set(os.path.normpath(d))

    def _add_dir(self):
        d = filedialog.askdirectory(title="选择工作流目录")
        if d and d not in self.workflow_dirs:
            self.workflow_dirs.append(os.path.normpath(d))
            self.dir_listbox.insert("end", d)

    def _remove_dir(self):
        sel = self.dir_listbox.curselection()
        for i in reversed(sel):
            self.workflow_dirs.pop(i)
            self.dir_listbox.delete(i)

    def _use_default(self):
        comfy = self.comfy_var.get()
        default = os.path.join(comfy, "user", "default")
        self.workflow_dirs = [os.path.normpath(default)]
        self.dir_listbox.delete(0, "end")
        self.dir_listbox.insert("end", default)

    def _pick_out(self):
        d = filedialog.askdirectory(title="选择报告保存目录")
        if d:
            self.out_var.set(os.path.normpath(d))

    # ---------------- 扫描 ----------------
    def _on_start(self):
        if not self.workflow_dirs:
            messagebox.showwarning("提示", "请先添加至少一个工作流目录。")
            return
        self.start_btn.config(state="disabled")
        self.status_var.set("扫描中...")
        self._set_result("扫描中，请稍候...\n")
        threading.Thread(target=self._run_scan, daemon=True).start()

    def _run_scan(self):
        try:
            report, result, stats = core.scan(
                comfy_path=self.comfy_var.get(),
                workflow_dirs=self.workflow_dirs,
                include_disabled=self.include_disabled.get(),
            )
            self.report_text = report
            self._render_result(result, stats)
        except Exception as e:
            self.report_text = ""
            self._set_result(f"扫描出错：\n{e}\n")
            self.status_var.set("出错")
        finally:
            self.start_btn.config(state="normal")

    def _render_result(self, result, stats):
        self.result_box.config(state="normal")
        self.result_box.delete("1.0", "end")

        summary = (
            f"扫描完成：{stats['scanned']} 个 JSON，引用 {0} 种节点\n"
            if False else
            f"扫描完成：{stats['scanned']} 个 JSON 文件\n"
        )
        self.result_box.insert("end", summary)

        self._insert_section("未使用 / 可删除", result.get("unused", []), "unused", "[ ] ")
        self._insert_section("已使用", result.get("used", []), "used", "[x] ")
        self._insert_section("无法确定（纯 JS 扩展等，勿盲目删）", result.get("undetermined", []), "undetermined", "[?] ")
        if self.include_disabled.get():
            self._insert_section("已禁用(.disabled)", result.get("disabled", []), "disabled", "[D] ")

        self.result_box.insert("end", "\n提示：报告仅列出清单，未做任何删除/重命名操作。\n", "header")
        self.result_box.config(state="disabled")
        self.status_var.set(
            f"未使用 {len(result.get('unused', []))} / 已使用 {len(result.get('used', []))} / "
            f"无法确定 {len(result.get('undetermined', []))}"
        )

    def _insert_section(self, title, items, tag, prefix):
        self.result_box.insert("end", f"\n{title}（共 {len(items)} 个）\n", "header")
        if items:
            for p in sorted(items):
                self.result_box.insert("end", f"  {prefix}{p}\n", tag)
        else:
            self.result_box.insert("end", "  （无）\n", tag)

    def _set_result(self, text):
        self.result_box.config(state="normal")
        self.result_box.delete("1.0", "end")
        self.result_box.insert("end", text)
        self.result_box.config(state="disabled")

    # ---------------- 保存 ----------------
    def _save_report(self):
        if not self.report_text:
            messagebox.showinfo("提示", "尚无报告可保存，请先扫描。")
            return
        out_dir = self.out_var.get()
        if not out_dir:
            out_dir = filedialog.askdirectory(title="选择报告保存目录")
            if not out_dir:
                return
            self.out_var.set(os.path.normpath(out_dir))
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, "unused_plugins_report.txt")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.report_text + "\n")
            messagebox.showinfo("已保存", f"报告已保存到：\n{path}")
        except Exception as e:
            messagebox.showerror("保存失败", str(e))


def main():
    app = ScannerGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
