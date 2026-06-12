# 🔒 墨盾 (Moshield) · 本地数据脱敏与还原工具

> **本地化 · 离线运行 · LLM 友好 · 文档结构完整保留**

一款基于 Python + PyQt6 的桌面应用，用于对办公文档进行**敏感信息脱敏**与**还原**。
不依赖云端服务，所有数据存在你自己的电脑上。

---

## ✨ 核心特性

| 特性 | 说明 |
|------|------|
| 🎯 **6 种文档格式** | docx / xlsx / pptx / txt / csv / md 全支持 |
| 🔍 **脱敏识别** | 词库匹配 + 6 条 L0 自动规则（手机/邮箱/身份证/银行卡/IP/金额）|
| 📐 **结构保留** | 走 Markdown 中间格式，**表格/列表/标题完整保留**（docx 表格不再丢失）|
| 🤖 **LLM 友好输出** | 脱敏后 .md 文件**自动嵌入元数据头部** + 5 条 LLM 行为约束 |
| ⚠️ **冲突检测** | 漏脱 / 占位符不一致 / 定义冲突——头部醒目列出 |
| 🔁 **完整还原** | 基于快照，可逆（即使过 1 年也能还原原文）|
| 🔒 **本地存储** | 数据存 `%APPDATA%\墨盾\`，不上云 |
| 🖥️ **PyQt6 GUI** | 5 个 Tab：词库管理 / 文档脱敏 / 文档还原 / 会话历史 / 设置 |

---

## 📸 截图

> 暂无截图，欢迎 PR 添加

界面包含：
- **词库管理**：增删改查敏感词、自定义代号
- **文档脱敏**：选文件 → 预览候选词 → 选输出格式 → 一键脱敏
- **会话历史**：所有脱敏/还原记录可查

---

## 🚀 快速开始

### 方式 1：从源码运行（开发者）

```bash
git clone https://github.com/kumabarloc/local-desensitizer.git
cd local-desensitizer
python -m venv venv

# Windows
.\venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# 运行 GUI
python -m src.gui.app

# 跑测试
pytest tests/ -v
```

### 方式 2：用打包好的 exe（普通用户）

1. 从 [Releases](https://github.com/kumabarloc/local-desensitizer/releases) 下载 `Moshield.exe`
2. 双击运行
3. 首次启动会在 `%APPDATA%\墨盾\` 创建数据目录

### 方式 3：自己打包

```powershell
# Windows PowerShell
.\venv\Scripts\Activate.ps1
.\build.ps1
# 产物: dist\Moshield.exe （约 60-90 MB）
```

---

## 📖 使用示例

### 场景 1：把 Word 文档脱敏后喂给 LLM

```
[原文档: 项目管理办法评审会议纪要.docx]
   ├─ 表格: 参会人员名单
   └─ 正文: 4 位领导发言

↓ 打开 墨盾 → 选文件 → 词库匹配自动识别 4 位领导
↓ 输出格式选: Markdown (.md) - 推荐 LLM 使用
↓ 点 🚀 执行脱敏

[产物: 项目管理办法评审会议纪要_desensitized.md]
   ├─ 顶部元数据（代号映射、规则统计、冲突检查、LLM 行为提示）
   ├─ 表格保留（人员用 [LEADER_1] 等代号替换）
   └─ 正文保留（敏感人名/单位用代号）

→ 直接把这个 .md 喂给 ChatGPT / Claude / 任何 LLM
→ LLM 看到头部就知道"这是脱敏文档，不要反推原文"
```

### 场景 2：还原原文

```
打开"文档还原" Tab → 选脱敏后的 .md → 选历史快照 → 🔁 还原
   ↓
[产物: 项目管理办法评审会议纪要_restored.docx]
（人名、单位、金额 全部还原回原文）
```

---

## 🛠️ 技术栈

| 层 | 技术 |
|----|------|
| GUI | PyQt6 6.6+ |
| 数据库 | SQLAlchemy 2.0 + SQLite |
| 文档解析 | python-docx / openpyxl / python-pptx |
| 密码学 | argon2-cffi（密码哈希）|
| 测试 | pytest（109 个测试）|
| 打包 | PyInstaller |
| CI | （待加 GitHub Actions）|

---

## 📁 项目结构

```
local-desensitizer/
├── src/
│   ├── gui/                  # PyQt6 GUI
│   │   ├── app.py            # 应用入口
│   │   └── main_window.py    # 主窗口（5 个 Tab）
│   ├── services/             # 业务逻辑
│   │   ├── database.py       # 数据库 + 路径解析（打包后走 APPDATA）
│   │   ├── document_processor.py  # 脱敏引擎（词库匹配 + L0 正则）
│   │   ├── document_handler.py    # 文档格式 I/O
│   │   ├── md_converter.py        # docx ↔ Markdown 转换
│   │   ├── header_generator.py    # 脱敏文档元数据头部生成
│   │   ├── word_library.py        # 词库管理
│   │   ├── snapshot_service.py    # 快照（用于还原）
│   │   ├── restore_service.py     # 还原引擎
│   │   └── settings_service.py    # 配置
│   ├── models/               # SQLAlchemy ORM
│   ├── resources/            # 姓氏/地名词典
│   └── main.py               # 开发用 CLI 入口
├── tests/                    # 109 个测试
├── data/                     # 开发模式数据（gitignore）
├── build.spec                # PyInstaller 配置
├── build.ps1                 # 一键打包脚本
├── BUILD.md                  # 打包详细说明
└── README.md                 # 本文件
```

---

## 🧪 开发

```bash
# 装依赖
pip install -e ".[dev]"

# 跑测试
pytest tests/ -v

# 跑测试 + 覆盖率
pytest tests/ --cov=src

# 代码风格（可选）
# pip install ruff
# ruff check src/
```

### 贡献

1. Fork 本仓库
2. 创建 feature 分支 (`git checkout -b feature/amazing-feature`)
3. 提交改动 (`git commit -m 'Add: amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 提交 Pull Request

---

## 🗺️ 路线图

| 状态 | 计划 |
|------|------|
| ✅ | 6 条 L0 自动规则（手机/邮箱/身份证/银行卡/IP/金额）|
| ✅ | MD 中间格式 + 表格保留 |
| ✅ | 脱敏文档头部 + 冲突检测 |
| ✅ | PyInstaller 打包 |
| ⏳ | JioNLP 集成（自动识别人名/单位/地名，词库自动采种）|
| ⏳ | 行业词典（多场景适配）|
| ⏳ | 批量处理（一次扫整个文件夹）|
| 💡 | macOS / Linux 打包 |
| 💡 | 多语言 UI（English / 中文切换）|

---

## 🐛 已知问题

- 简单正则可能误识别（如 "2026" 被当作金额 "2026 元" 误命中），可在 GUI 设置里调阈值
- L0 规则不识别中文人名/单位（计划用 JioNLP 解决）
- 自动备份路径硬编码 `%APPDATA%\墨盾\data\backups\`

---

## 🔐 安全

- 所有数据**仅存在本地**（`%APPDATA%\墨盾\data\`）
- **不上传任何文档**到云端
- 可选访问密码保护（argon2 哈希）
- 词库、配置、快照都在本地 SQLite 里

> ⚠️ **脱敏不是匿名化**。脱敏后的文档应仍能通过快照还原，请妥善保管本地数据。

---

## 📜 许可证

[MIT License](./LICENSE) — 欢迎分享、修改、商用，保留版权即可。

---

## 🙏 致谢

- 借力于 LLM 时代对**安全数据流通**的强烈需求
- 用了 LLM 帮我写代码和重构（dogfooding）

---

## 📮 联系

- GitHub Issues: <https://github.com/kumabarloc/local-desensitizer/issues>
