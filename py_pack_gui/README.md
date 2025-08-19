Python 打包 GUI (基于 Tkinter + PyInstaller)

功能

- 选择入口 `*.py` 文件，一键打包
- 支持 `--onefile`/`--windowed`/`--clean`/`--noconfirm`/`--strip`
- 选择图标、输出目录
- 添加隐藏依赖(`--hidden-import`)与资源文件(`--add-data`)
- 可选使用 UPX 压缩，并指定 UPX 目录
- 额外参数直通 PyInstaller
- 显示/复制最终命令，保存/加载 JSON 配置
- 日志实时输出，可取消打包

快速开始

1. 安装依赖：

```bash
pip install -r requirements.txt
```

2. 启动 GUI：

```bash
python main.py
```

3. 在界面中：
- 选择入口脚本与输出目录
- 根据需要勾选选项、添加资源/隐藏依赖
- 点击“开始打包”

提示

- 资源映射格式遵循 PyInstaller：Linux/macOS 使用 `源:目标`，Windows 使用 `源;目标`。本工具会自动根据系统选择正确分隔符。
- 如需更细粒度控制，可在“额外参数”中传入原生 PyInstaller 选项，例如：`--collect-all somepkg --exclude-module tests`。
- 若启用 UPX，请先安装 UPX 并在界面中指定其目录，或设置环境变量 `UPX_DIR`。

兼容性

- 需要 Python 3.9+。
- 测试平台：Linux、Windows、macOS（界面相同，打包行为以 PyInstaller 支持为准）。

