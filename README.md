# Smart Desktop Assistant (MVP)

本项目是一个 Windows 后台常驻小工具（本地运行、无外部服务）：

- 自动整理 `C:\Users\admin\Downloads`（可在配置中修改）
- 记录剪贴板文本历史（SQLite，本地存储）
- 托盘菜单 + 剪贴板历史窗口（最新 50 条、可一键复制）

## 运行

在 PowerShell 中：

```powershell
cd C:\Users\admin\work\tools\smart_desktop_assistant
python -m venv .venv
.\.venv\Scripts\pip install -r .\requirements.txt
.\.venv\Scripts\python .\app.py
```

启动后会在系统托盘出现图标，通过菜单操作：

- Organize Downloads Now
- Open Clipboard History
- Pause/Resume File Organizer
- Pause/Resume Clipboard Monitor
- Open Logs Folder
- Exit

## 配置/数据位置

- 源码运行：项目目录下的 `config.json` / `data\smart.db` / `logs\`
- PyInstaller `--onefile`：自动改为 `%LOCALAPPDATA%\SmartDesktopAssistant\` 下的 `config.json` / `data\smart.db` / `logs\`

## 打包（PyInstaller）

```powershell
cd C:\Users\admin\work\tools\smart_desktop_assistant
.\.venv\Scripts\pip install pyinstaller
.\.venv\Scripts\pyinstaller --onefile --noconsole .\app.py
```

生成的可执行文件位于 `dist\app.exe`。

