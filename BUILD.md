# 打包成 Windows .exe

## 快速打包（推荐）

在 **Windows PowerShell**（不是 WSL）里执行：

```powershell
cd C:\Users\barlo\Desktop\claw\desensitizer
.\venv\Scripts\Activate.ps1
.\build.ps1
```

跑完会生成 `dist\墨盾.exe`（单文件，约 60-90 MB）。

## 手动打包（如果 build.ps1 出问题）

```powershell
# 1. 装 PyInstaller
pip install pyinstaller

# 2. 跑测试
pytest tests/ -v

# 3. 打包
pyinstaller build.spec --clean --noconfirm
```

## 用户数据位置

打包后的 exe 运行时会**自动创建**用户数据目录：

```
%APPDATA%\墨盾\
├── data\
│   ├── vault.db          ← 词库、快照
│   ├── config.json       ← 配置
│   ├── snapshots\        ← 快照
│   └── backups\          ← 自动备份
```

Windows 实际路径：`C:\Users\<用户名>\AppData\Roaming\墨盾\`

> 卸载 exe 时**手动删这个目录**即可清理全部数据。

## 文件清单

| 文件 | 作用 |
|------|------|
| `build.spec` | PyInstaller 配置（入口、隐藏 import、排除项）|
| `build.ps1` | 一键打包脚本（装 pyinstaller + 测 + 打包 + 验证）|
| `BUILD.md` | 本文件 |

## 调大小（可选）

PyInstaller 打出来的 exe 默认 60-90 MB。如果想压缩到 30-40 MB：

```powershell
# 装 UPX（开源压缩工具）
# 从 https://github.com/upx/upx/releases 下载 upx.exe
# 放到 PATH 里或 build.spec 旁边

# 然后重打包，UPX 会自动压缩
pyinstaller build.spec --clean --noconfirm --upx-dir "C:\path\to\upx"
```

## 常见问题

### Q: 双击 exe 闪退？
A: 用终端跑（`.\dist\墨盾.exe`），看 traceback。最常见：
- 缺 `data/` 子目录：会自动创建
- PyQt6 平台插件缺失：重装 PyQt6
- 杀毒软件拦截：加白名单

### Q: 找不到模块？
A: 在 `build.spec` 的 `hiddenimports` 里加上漏的模块

### Q: 词库里的数据丢了？
A: 打包后 exe 默认存到 `%APPDATA%\墨盾\`，不会丢。
   开发模式 (PyCharm) 和 exe 模式用**不同的数据目录**，互不影响。

## 完整工作流

```
开发 (PyCharm + WSL)        打包后 (Windows 用户)
─────────────────────       ──────────────────
./data/vault.db              %APPDATA%/墨盾/data/vault.db
./data/config.json            %APPDATA%/墨盾/data/config.json
./data/snapshots/             %APPDATA%/墨盾/data/snapshots/
./data/backups/               %APPDATA%/墨盾/data/backups/
```

`src/services/database.py` 里的 `get_app_data_dir()` 自动判断：
- `sys.frozen = True`（打包后）→ APPDATA
- `sys.frozen = False`（开发）→ 项目根目录
