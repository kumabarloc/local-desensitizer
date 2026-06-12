# 更新日志

本项目的所有重要变更都会记录在此文件。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 计划中
- JioNLP 集成（自动识别人名/单位/地名，词库自动采种）
- 行业词典（生态环境/医疗/金融等）
- 批量处理（一次扫整个文件夹）

## [0.2.0] - 2026-06-12

### 新增
- 🎉 **MD 中间格式层**：docx 通过 Markdown 中间格式处理，**表格/列表/标题完整保留**
- 🎉 **脱敏文档头部**：自动注入元数据（代号映射、规则统计、冲突检查、5 条 LLM 行为约束）
- 🎉 **冲突检测**：3 类冲突自动检查（漏脱/占位符不一致/定义冲突）
- 🎉 **PyInstaller 打包配置**：build.spec + build.ps1 + BUILD.md
- 🎉 **打包后路径修复**：用户数据存 `%APPDATA%\DataVault\`（不再丢数据）
- 🐛 **修复**：GUI 选中行崩溃（PyQt5 → PyQt6 API 差异）
- 🐛 **修复**：脱敏 Tab 加输出格式选择（默认 Markdown）

### 测试
- 新增 29 个测试（md_converter + header_generator）
- 总计 **109 测试通过**

## [0.1.0] - 2026-05-14

### 新增
- 🎉 **PyQt6 GUI**：5 个 Tab（词库管理 / 文档脱敏 / 文档还原 / 会话历史 / 设置）
- 🎉 **核心脱敏引擎**：词库匹配 + 6 条 L0 正则（手机/邮箱/身份证/银行卡/IP/金额）
- 🎉 **3 种代号格式**：结构化 `[PERSON_1]` / 语义 `[PERSON_LD_1]` / 随机 `[X_A3F7]`
- 🎉 **6 种文档格式 I/O**：docx / xlsx / pptx / txt / csv / md
- 🎉 **快照系统**：脱敏/还原双向支持
- 🎉 **SQLite 词库 + 备份系统**
- 🎉 **密码保护**（argon2 哈希）

### 测试
- 80 个单元测试 + 集成测试

[Unreleased]: https://github.com/kumabarloc/local-desensitizer/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/kumabarloc/local-desensitizer/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/kumabarloc/local-desensitizer/releases/tag/v0.1.0
