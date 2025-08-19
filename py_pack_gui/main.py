import os
import sys
import json
import shlex
import queue
import threading
import subprocess
import platform
from pathlib import Path
import ast
import importlib.util

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText


class PackagerGUI(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Python 打包 GUI (PyInstaller)")
        self.geometry("980x700")

        # State variables
        self.entry_script_var = tk.StringVar()
        self.output_dir_var = tk.StringVar(value=str(Path.cwd() / "dist"))
        self.icon_path_var = tk.StringVar()
        self.app_name_var = tk.StringVar()
        self.onefile_var = tk.BooleanVar(value=True)
        self.windowed_var = tk.BooleanVar(value=False)
        self.clean_var = tk.BooleanVar(value=True)
        self.noconfirm_var = tk.BooleanVar(value=True)
        self.debug_var = tk.BooleanVar(value=False)
        self.strip_var = tk.BooleanVar(value=(platform.system() != "Windows"))
        self.upx_var = tk.BooleanVar(value=False)
        self.upx_dir_var = tk.StringVar()
        self.additional_args_var = tk.StringVar()

        self.hidden_imports: list[str] = []
        self.data_mappings: list[tuple[str, str]] = []  # (src, dest_relative)

        # Runtime
        self.current_process: subprocess.Popen | None = None
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.is_running = False

        self._build_ui()
        self._poll_log_queue()

    def _build_ui(self) -> None:
        container = ttk.Frame(self)
        container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Top controls
        top = ttk.LabelFrame(container, text="基本配置")
        top.pack(fill=tk.X, expand=False)

        # Entry script
        row0 = ttk.Frame(top)
        row0.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(row0, text="入口脚本").pack(side=tk.LEFT)
        entry_script = ttk.Entry(row0, textvariable=self.entry_script_var)
        entry_script.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        ttk.Button(row0, text="选择...", command=self._choose_entry_script).pack(side=tk.LEFT)

        # Output dir + icon
        row1 = ttk.Frame(top)
        row1.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(row1, text="输出目录").pack(side=tk.LEFT)
        out_entry = ttk.Entry(row1, textvariable=self.output_dir_var)
        out_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        ttk.Button(row1, text="选择...", command=self._choose_output_dir).pack(side=tk.LEFT)

        row2 = ttk.Frame(top)
        row2.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(row2, text="图标文件").pack(side=tk.LEFT)
        icon_entry = ttk.Entry(row2, textvariable=self.icon_path_var)
        icon_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        ttk.Button(row2, text="选择...", command=self._choose_icon_file).pack(side=tk.LEFT)

        row2b = ttk.Frame(top)
        row2b.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(row2b, text="应用名称").pack(side=tk.LEFT)
        ttk.Entry(row2b, textvariable=self.app_name_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)

        # Options
        opts = ttk.LabelFrame(container, text="打包选项")
        opts.pack(fill=tk.X, pady=(10, 0))

        row3 = ttk.Frame(opts)
        row3.pack(fill=tk.X, padx=8, pady=6)
        ttk.Checkbutton(row3, text="单文件 (--onefile)", variable=self.onefile_var).pack(side=tk.LEFT)
        ttk.Checkbutton(row3, text="窗口应用/无控制台 (--windowed)", variable=self.windowed_var).pack(side=tk.LEFT, padx=(16, 0))
        ttk.Checkbutton(row3, text="清理缓存 (--clean)", variable=self.clean_var).pack(side=tk.LEFT, padx=(16, 0))
        ttk.Checkbutton(row3, text="无需确认 (--noconfirm)", variable=self.noconfirm_var).pack(side=tk.LEFT, padx=(16, 0))

        row4 = ttk.Frame(opts)
        row4.pack(fill=tk.X, padx=8, pady=6)
        ttk.Checkbutton(row4, text="调试日志 (log-level=DEBUG)", variable=self.debug_var).pack(side=tk.LEFT)
        ttk.Checkbutton(row4, text="剥离符号 (--strip)", variable=self.strip_var).pack(side=tk.LEFT, padx=(16, 0))
        ttk.Checkbutton(row4, text="使用 UPX", variable=self.upx_var).pack(side=tk.LEFT, padx=(16, 0))

        row4b = ttk.Frame(opts)
        row4b.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(row4b, text="UPX 目录").pack(side=tk.LEFT)
        ttk.Entry(row4b, textvariable=self.upx_dir_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        ttk.Button(row4b, text="选择...", command=self._choose_upx_dir).pack(side=tk.LEFT)

        row5 = ttk.Frame(opts)
        row5.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(row5, text="额外参数").pack(side=tk.LEFT)
        ttk.Entry(row5, textvariable=self.additional_args_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)

        # Hidden imports and data files
        adv = ttk.LabelFrame(container, text="高级 (隐藏依赖 / 资源打包)")
        adv.pack(fill=tk.BOTH, expand=False, pady=(10, 0))

        mid = ttk.Frame(adv)
        mid.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

        hidden_frame = ttk.Frame(mid)
        hidden_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ttk.Label(hidden_frame, text="隐藏依赖 (hidden-import)").pack(anchor=tk.W)
        self.hidden_list = tk.Listbox(hidden_frame, height=6)
        self.hidden_list.pack(fill=tk.BOTH, expand=True)
        hidden_btns = ttk.Frame(hidden_frame)
        hidden_btns.pack(fill=tk.X, pady=4)
        self.hidden_entry = ttk.Entry(hidden_btns)
        self.hidden_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(hidden_btns, text="添加", command=self._add_hidden_import).pack(side=tk.LEFT, padx=4)
        ttk.Button(hidden_btns, text="删除", command=self._remove_hidden_import).pack(side=tk.LEFT)
        ttk.Button(hidden_btns, text="依赖分析", command=self._auto_analyze_and_fill_hidden).pack(side=tk.LEFT, padx=4)

        data_frame = ttk.Frame(mid)
        data_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(16, 0))
        ttk.Label(data_frame, text="资源文件 (--add-data) | 目标路径为相对路径，如 assets/").pack(anchor=tk.W)
        self.data_list = tk.Listbox(data_frame, height=6)
        self.data_list.pack(fill=tk.BOTH, expand=True)
        data_btns = ttk.Frame(data_frame)
        data_btns.pack(fill=tk.X, pady=4)
        ttk.Button(data_btns, text="添加文件", command=self._add_data_file).pack(side=tk.LEFT)
        ttk.Button(data_btns, text="添加目录", command=self._add_data_dir).pack(side=tk.LEFT, padx=4)
        ttk.Button(data_btns, text="删除", command=self._remove_data_mapping).pack(side=tk.LEFT)

        # Actions
        actions = ttk.Frame(container)
        actions.pack(fill=tk.X, pady=10)
        self.pack_btn = ttk.Button(actions, text="开始打包", command=self._on_pack_clicked)
        self.pack_btn.pack(side=tk.LEFT)
        ttk.Button(actions, text="生成spec", command=self._on_make_spec_clicked).pack(side=tk.LEFT, padx=6)
        self.cancel_btn = ttk.Button(actions, text="取消", command=self._on_cancel_clicked, state=tk.DISABLED)
        self.cancel_btn.pack(side=tk.LEFT, padx=6)
        ttk.Button(actions, text="显示命令", command=self._show_command).pack(side=tk.LEFT, padx=6)
        ttk.Button(actions, text="保存配置", command=self._save_config).pack(side=tk.LEFT, padx=6)
        ttk.Button(actions, text="加载配置", command=self._load_config).pack(side=tk.LEFT, padx=6)
        ttk.Button(actions, text="清空日志", command=self._clear_log).pack(side=tk.LEFT, padx=6)

        # Log output
        log_frame = ttk.LabelFrame(container, text="日志")
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.log_text = ScrolledText(log_frame, height=18, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

    def _choose_entry_script(self) -> None:
        path = filedialog.askopenfilename(title="选择入口 .py 文件", filetypes=[("Python", "*.py"), ("所有文件", "*.*")])
        if path:
            self.entry_script_var.set(path)

    def _choose_output_dir(self) -> None:
        path = filedialog.askdirectory(title="选择输出目录")
        if path:
            self.output_dir_var.set(path)

    def _choose_icon_file(self) -> None:
        path = filedialog.askopenfilename(title="选择图标文件", filetypes=[("Icon", "*.ico;*.icns;*.png"), ("所有文件", "*.*")])
        if path:
            self.icon_path_var.set(path)

    def _choose_upx_dir(self) -> None:
        path = filedialog.askdirectory(title="选择 UPX 安装目录")
        if path:
            self.upx_dir_var.set(path)

    def _add_hidden_import(self) -> None:
        mod = self.hidden_entry.get().strip()
        if mod and mod not in self.hidden_imports:
            self.hidden_imports.append(mod)
            self.hidden_list.insert(tk.END, mod)
            self.hidden_entry.delete(0, tk.END)

    def _remove_hidden_import(self) -> None:
        sel = list(self.hidden_list.curselection())
        sel.reverse()
        for idx in sel:
            mod = self.hidden_list.get(idx)
            self.hidden_list.delete(idx)
            try:
                self.hidden_imports.remove(mod)
            except ValueError:
                pass

    def _add_data_file(self) -> None:
        src = filedialog.askopenfilename(title="选择资源文件")
        if not src:
            return
        dest = self._ask_dest_relative()
        if dest is None:
            return
        self.data_mappings.append((src, dest))
        self.data_list.insert(tk.END, f"{src} -> {dest}")

    def _add_data_dir(self) -> None:
        src = filedialog.askdirectory(title="选择资源目录")
        if not src:
            return
        dest = self._ask_dest_relative()
        if dest is None:
            return
        self.data_mappings.append((src, dest))
        self.data_list.insert(tk.END, f"{src} -> {dest}")

    def _ask_dest_relative(self) -> str | None:
        dialog = tk.Toplevel(self)
        dialog.title("输入相对目标路径 (如 assets 或 assets/images)")
        dialog.transient(self)
        dialog.grab_set()

        var = tk.StringVar(value="assets")
        ttk.Label(dialog, text="相对目标路径:").pack(padx=10, pady=(10, 0), anchor=tk.W)
        entry = ttk.Entry(dialog, textvariable=var, width=48)
        entry.pack(padx=10, pady=8)
        entry.focus_set()

        result: dict[str, str | None] = {"value": None}

        def on_ok() -> None:
            result["value"] = var.get().strip()
            dialog.destroy()

        def on_cancel() -> None:
            result["value"] = None
            dialog.destroy()

        btns = ttk.Frame(dialog)
        btns.pack(pady=10)
        ttk.Button(btns, text="确定", command=on_ok).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text="取消", command=on_cancel).pack(side=tk.LEFT)

        self.wait_window(dialog)
        value = result["value"]
        if value == "":
            return None
        return value

    def _remove_data_mapping(self) -> None:
        sel = list(self.data_list.curselection())
        sel.reverse()
        for idx in sel:
            self.data_list.delete(idx)
            try:
                del self.data_mappings[idx]
            except Exception:
                pass

    def _on_pack_clicked(self) -> None:
        if self.is_running:
            return
        entry_script = self.entry_script_var.get().strip()
        if not entry_script:
            messagebox.showerror("错误", "请先选择入口脚本 (.py)")
            return
        if not os.path.isfile(entry_script):
            messagebox.showerror("错误", "入口脚本不存在")
            return

        out_dir = self.output_dir_var.get().strip() or str(Path.cwd() / "dist")
        Path(out_dir).mkdir(parents=True, exist_ok=True)

        cmd = self._build_pyinstaller_command()
        self._append_log_line("$ " + self._format_cmd_for_display(cmd))

        self.is_running = True
        self._set_running_state(True)
        self.current_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            cwd=str(Path(entry_script).parent),
        )

        threading.Thread(target=self._pump_process_output, daemon=True).start()
        threading.Thread(target=self._wait_for_process_end, daemon=True).start()

    def _on_cancel_clicked(self) -> None:
        if not self.is_running or not self.current_process:
            return
        try:
            self.current_process.terminate()
        except Exception:
            try:
                self.current_process.kill()
            except Exception:
                pass

    def _pump_process_output(self) -> None:
        assert self.current_process is not None
        assert self.current_process.stdout is not None
        for line in self.current_process.stdout:
            self.log_queue.put(line.rstrip("\n"))

    def _wait_for_process_end(self) -> None:
        assert self.current_process is not None
        return_code = self.current_process.wait()
        if return_code == 0:
            self.log_queue.put("[完成] 打包成功")
        else:
            self.log_queue.put(f"[失败] 进程退出码: {return_code}")
        self.after(0, lambda: self._set_running_state(False))

    def _set_running_state(self, running: bool) -> None:
        self.is_running = running
        self.pack_btn.configure(state=tk.DISABLED if running else tk.NORMAL)
        self.cancel_btn.configure(state=tk.NORMAL if running else tk.DISABLED)

    def _build_pyinstaller_command(self) -> list[str]:
        # Use module invocation to avoid PATH issues
        cmd: list[str] = [sys.executable, "-m", "PyInstaller"]

        app_name = self.app_name_var.get().strip()
        if app_name:
            cmd.extend(["--name", app_name])

        if self.onefile_var.get():
            cmd.append("--onefile")
        if self.windowed_var.get():
            cmd.append("--windowed")
        if self.clean_var.get():
            cmd.append("--clean")
        if self.noconfirm_var.get():
            cmd.append("--noconfirm")
        if self.debug_var.get():
            cmd.append("--log-level=DEBUG")
        if self.strip_var.get():
            cmd.append("--strip")

        icon_path = self.icon_path_var.get().strip()
        if icon_path:
            cmd.append(f"--icon={icon_path}")

        upx_enabled = self.upx_var.get()
        upx_dir = self.upx_dir_var.get().strip()
        if upx_enabled:
            cmd.append("--upx-dir")
            cmd.append(upx_dir if upx_dir else os.environ.get("UPX_DIR", ""))

        # Output paths
        out_dir = self.output_dir_var.get().strip() or str(Path.cwd() / "dist")
        work_dir = str(Path(out_dir) / ".build")
        spec_dir = str(Path(out_dir) / ".spec")
        Path(work_dir).mkdir(parents=True, exist_ok=True)
        Path(spec_dir).mkdir(parents=True, exist_ok=True)
        cmd.extend(["--distpath", out_dir, "--workpath", work_dir, "--specpath", spec_dir])

        # Hidden imports
        for mod in self.hidden_imports:
            cmd.extend(["--hidden-import", mod])

        # Data files
        sep = ";" if platform.system() == "Windows" else ":"
        for src, dest in self.data_mappings:
            mapping = f"{src}{sep}{dest}"
            cmd.extend(["--add-data", mapping])

        # Additional args
        extra = self.additional_args_var.get().strip()
        if extra:
            try:
                cmd.extend(shlex.split(extra))
            except ValueError:
                # Fall back to raw append
                cmd.append(extra)

        # Entry script (last)
        cmd.append(self.entry_script_var.get().strip())

        return cmd

    def _build_makespec_command(self) -> list[str]:
        cmd: list[str] = [sys.executable, "-m", "PyInstaller.utils.cliutils.makespec"]

        app_name = self.app_name_var.get().strip()
        if app_name:
            cmd.extend(["--name", app_name])

        if self.onefile_var.get():
            cmd.append("--onefile")
        if self.windowed_var.get():
            cmd.append("--windowed")

        icon_path = self.icon_path_var.get().strip()
        if icon_path:
            cmd.append(f"--icon={icon_path}")

        # Hidden imports
        for mod in self.hidden_imports:
            cmd.extend(["--hidden-import", mod])

        # Data files
        sep = ";" if platform.system() == "Windows" else ":"
        for src, dest in self.data_mappings:
            mapping = f"{src}{sep}{dest}"
            cmd.extend(["--add-data", mapping])

        # Spec path
        out_dir = self.output_dir_var.get().strip() or str(Path.cwd() / "dist")
        spec_dir = str(Path(out_dir) / ".spec")
        Path(spec_dir).mkdir(parents=True, exist_ok=True)
        cmd.extend(["--specpath", spec_dir])

        # Additional args
        extra = self.additional_args_var.get().strip()
        if extra:
            try:
                cmd.extend(shlex.split(extra))
            except ValueError:
                cmd.append(extra)

        # Entry script
        cmd.append(self.entry_script_var.get().strip())
        return cmd

    def _on_make_spec_clicked(self) -> None:
        if self.is_running:
            return
        entry_script = self.entry_script_var.get().strip()
        if not entry_script:
            messagebox.showerror("错误", "请先选择入口脚本 (.py)")
            return
        if not os.path.isfile(entry_script):
            messagebox.showerror("错误", "入口脚本不存在")
            return

        cmd = self._build_makespec_command()
        self._append_log_line("$ " + self._format_cmd_for_display(cmd))

        self.is_running = True
        self._set_running_state(True)
        self.current_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            cwd=str(Path(entry_script).parent),
        )

        threading.Thread(target=self._pump_process_output, daemon=True).start()
        threading.Thread(target=self._wait_for_process_end, daemon=True).start()

    def _auto_analyze_and_fill_hidden(self) -> None:
        entry_script = self.entry_script_var.get().strip()
        if not entry_script or not os.path.isfile(entry_script):
            messagebox.showerror("错误", "请先选择有效的入口脚本 (.py)")
            return

        try:
            imports = self._collect_top_level_imports(entry_script)
        except Exception as exc:
            messagebox.showerror("错误", f"依赖分析失败: {exc}")
            return

        # Filter: exclude built-in and stdlib
        stdlib_names = set()
        if hasattr(sys, "stdlib_module_names"):
            try:
                stdlib_names = set(sys.stdlib_module_names)  # type: ignore[attr-defined]
            except Exception:
                stdlib_names = set()

        builtin_names = set(sys.builtin_module_names)

        suggestions: list[str] = []
        for name in sorted(imports):
            if name.startswith("."):
                continue
            root = name.split(".", 1)[0]
            if root in builtin_names or root in stdlib_names:
                continue
            suggestions.append(root)

        added = 0
        for mod in suggestions:
            if mod not in self.hidden_imports:
                self.hidden_imports.append(mod)
                self.hidden_list.insert(tk.END, mod)
                added += 1

        self._append_log_line(f"[分析] 建议隐藏依赖共 {len(suggestions)} 个，新增 {added} 个")

    def _collect_top_level_imports(self, file_path: str) -> set[str]:
        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source, filename=file_path)

        imports: set[str] = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name:
                        imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    base = ("." * node.level) + node.module if node.level else node.module
                    imports.add(base)
                else:
                    # from . import something
                    imports.add("." * max(1, node.level))

        return imports

    def _show_command(self) -> None:
        try:
            cmd = self._build_pyinstaller_command()
        except Exception as exc:
            messagebox.showerror("错误", f"生成命令失败: {exc}")
            return
        display = self._format_cmd_for_display(cmd)

        dialog = tk.Toplevel(self)
        dialog.title("PyInstaller 命令")
        dialog.geometry("900x240")
        dialog.transient(self)
        dialog.grab_set()

        txt = ScrolledText(dialog, height=8)
        txt.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        txt.insert(tk.END, display)
        txt.configure(state=tk.DISABLED)

        btns = ttk.Frame(dialog)
        btns.pack(pady=8)

        def copy_to_clipboard() -> None:
            self.clipboard_clear()
            self.clipboard_append(display)
            messagebox.showinfo("已复制", "命令已复制到剪贴板")

        ttk.Button(btns, text="复制到剪贴板", command=copy_to_clipboard).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text="关闭", command=dialog.destroy).pack(side=tk.LEFT)

    def _save_config(self) -> None:
        path = filedialog.asksaveasfilename(title="保存配置为...", defaultextension=".json", filetypes=[("JSON", "*.json")])
        if not path:
            return
        data = {
            "entry_script": self.entry_script_var.get(),
            "output_dir": self.output_dir_var.get(),
            "icon_path": self.icon_path_var.get(),
            "onefile": self.onefile_var.get(),
            "windowed": self.windowed_var.get(),
            "clean": self.clean_var.get(),
            "noconfirm": self.noconfirm_var.get(),
            "debug": self.debug_var.get(),
            "strip": self.strip_var.get(),
            "upx": self.upx_var.get(),
            "upx_dir": self.upx_dir_var.get(),
            "hidden_imports": self.hidden_imports,
            "data_mappings": self.data_mappings,
            "additional_args": self.additional_args_var.get(),
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._append_log_line(f"[配置] 已保存到: {path}")
        except Exception as exc:
            messagebox.showerror("错误", f"保存失败: {exc}")

    def _load_config(self) -> None:
        path = filedialog.askopenfilename(title="加载配置", filetypes=[("JSON", "*.json"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            messagebox.showerror("错误", f"读取失败: {exc}")
            return

        self.entry_script_var.set(data.get("entry_script", ""))
        self.output_dir_var.set(data.get("output_dir", ""))
        self.icon_path_var.set(data.get("icon_path", ""))
        self.onefile_var.set(bool(data.get("onefile", True)))
        self.windowed_var.set(bool(data.get("windowed", False)))
        self.clean_var.set(bool(data.get("clean", True)))
        self.noconfirm_var.set(bool(data.get("noconfirm", True)))
        self.debug_var.set(bool(data.get("debug", False)))
        self.strip_var.set(bool(data.get("strip", platform.system() != "Windows")))
        self.upx_var.set(bool(data.get("upx", False)))
        self.upx_dir_var.set(data.get("upx_dir", ""))
        self.additional_args_var.set(data.get("additional_args", ""))

        self.hidden_imports = list(data.get("hidden_imports", []))
        self.hidden_list.delete(0, tk.END)
        for mod in self.hidden_imports:
            self.hidden_list.insert(tk.END, mod)

        self.data_mappings = [(s, d) for s, d in data.get("data_mappings", [])]
        self.data_list.delete(0, tk.END)
        for s, d in self.data_mappings:
            self.data_list.insert(tk.END, f"{s} -> {d}")

        self._append_log_line(f"[配置] 已加载: {path}")

    def _clear_log(self) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _append_log_line(self, text: str) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, text + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _poll_log_queue(self) -> None:
        try:
            while True:
                line = self.log_queue.get_nowait()
                self._append_log_line(line)
        except queue.Empty:
            pass
        finally:
            self.after(80, self._poll_log_queue)

    @staticmethod
    def _format_cmd_for_display(cmd: list[str]) -> str:
        # Create a shell-friendly single line for display/copying
        def quote(arg: str) -> str:
            if not arg:
                return "''"
            if any(c.isspace() for c in arg) or any(c in arg for c in ['"', "'", "(", ")", "|", "&", ";", "<", ">"]):
                return shlex.quote(arg)
            return arg

        return " ".join(quote(a) for a in cmd)


def main() -> None:
    app = PackagerGUI()
    app.mainloop()


if __name__ == "__main__":
    main()

