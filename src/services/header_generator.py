"""脱敏文档头部生成器

为脱敏后的 MD 文档生成首部元数据 + 提示词，让 LLM 在读的时候
明确知道：
1. 这是一份脱敏后文档（不要反推原文）
2. 代号映射表（占位符代表什么）
3. 应用的规则（哪些词被脱敏了）
4. 冲突检查结果（前后是否一致）
5. 行为约束（不要编造、可以引用代号等）
"""
from datetime import datetime
from pathlib import Path
from typing import Iterable

from src.services.document_processor import ReplacementItem


def detect_conflicts(
    original_text: str,
    result_text: str,
    items: list[ReplacementItem],
) -> list[str]:
    """检测脱敏前后不一致

    检查项：
    1. 漏脱：原文中的敏感词在结果中仍出现（没被替换）
    2. 占位符不一致：同一个原文对应多个占位符
    3. 占位符定义不一致：同一个占位符被多个原文占用（间接）

    Returns:
        冲突描述列表（人类可读），空列表 = 全部一致
    """
    conflicts: list[str] = []

    # 1. 漏脱检查：原文里的敏感词在 result 中是否还存在
    for item in items:
        # 跳过自动规则的非确定性项（如 AMOUNT 误识别 2026）— 这里只检查词库
        if not item.source.startswith("wordlibrary"):
            continue
        count_in_result = result_text.count(item.original)
        if count_in_result > 0:
            conflicts.append(
                f"漏脱: '{item.original}' 在结果中仍出现 {count_in_result} 次（占位符: {item.placeholder}）"
            )

    # 2. 同原文 → 不同占位符
    orig_to_placeholders: dict[str, set[str]] = {}
    for item in items:
        if not item.source.startswith("wordlibrary"):
            continue
        orig_to_placeholders.setdefault(item.original, set()).add(item.placeholder)
    for orig, placeholders in orig_to_placeholders.items():
        if len(placeholders) > 1:
            conflicts.append(
                f"占位符不一致: '{orig}' 同时被替换为 {sorted(placeholders)}"
            )

    # 3. 同占位符 → 不同原文
    ph_to_originals: dict[str, set[str]] = {}
    for item in items:
        if not item.source.startswith("wordlibrary"):
            continue
        ph_to_originals.setdefault(item.placeholder, set()).add(item.original)
    for ph, originals in ph_to_originals.items():
        if len(originals) > 1:
            conflicts.append(
                f"占位符定义冲突: '{ph}' 同时对应 {len(originals)} 个原文 ({sorted(originals)})"
            )

    return conflicts


def generate_header(
    source_path: Path,
    items: list[ReplacementItem],
    conflicts: list[str],
) -> str:
    """生成脱敏文档首部（MD 格式）

    结构：
    1. 元数据块（时间、源文件、规则版本）
    2. 代号映射表
    3. 规则应用统计
    4. 冲突检查结果
    5. 给 LLM 的提示
    6. 文档分界线

    Returns:
        MD 格式的字符串，可直接拼接到 result_text 之前
    """
    source_name = source_path.name
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rules_version = "v1.0"  # 后续可在 settings 里配置

    # 分类统计
    wordlib_items = [i for i in items if i.source.startswith("wordlibrary")]
    auto_items = [i for i in items if i.source.startswith("autodetect")]
    by_category: dict[str, int] = {}
    for item in wordlib_items:
        by_category[item.category] = by_category.get(item.category, 0) + 1
    auto_by_rule: dict[str, int] = {}
    for item in auto_items:
        # source 格式: "autodetect:PHONE"
        rule = item.source.split(":", 1)[1] if ":" in item.source else "UNKNOWN"
        auto_by_rule[rule] = auto_by_rule.get(rule, 0) + 1

    # 代号映射（去重 + 排序）
    seen_phs: dict[str, ReplacementItem] = {}
    for item in wordlib_items:
        if item.placeholder not in seen_phs:
            seen_phs[item.placeholder] = item

    lines: list[str] = []
    lines.append("<!-- ============================================================== -->")
    lines.append("<!-- 脱敏元数据 / Desensitization Metadata                              -->")
    lines.append("<!-- ============================================================== -->")
    lines.append("")
    lines.append("# 🔒 脱敏元数据")
    lines.append("")
    lines.append("> **⚠️ 本文件是脱敏后版本**，敏感信息已替换为代号。LLM 读取时请按下方指引。")
    lines.append("")
    lines.append("**元信息**")
    lines.append("")
    lines.append(f"- 源文件：`{source_name}`")
    lines.append(f"- 脱敏时间：{now}")
    lines.append(f"- 规则版本：{rules_version}")
    lines.append("")
    lines.append("**代号映射表**")
    lines.append("")
    if seen_phs:
        lines.append("| 占位符 | 类别 | 原始内容（描述）|")
        lines.append("|--------|------|----------------|")
        for ph, item in sorted(seen_phs.items()):
            # 描述：对原文做长度截断+遮蔽
            desc = _describe_original(item.original)
            lines.append(f"| `{ph}` | {item.category} | {desc} |")
    else:
        lines.append("（无词库匹配项）")
    lines.append("")

    lines.append("**应用规则统计**")
    lines.append("")
    lines.append(f"- 词库匹配：{len(wordlib_items)} 项")
    if by_category:
        cat_str = ", ".join(f"{k}={v}" for k, v in sorted(by_category.items()))
        lines.append(f"  - 按类别：{cat_str}")
    lines.append(f"- 自动规则命中：{len(auto_items)} 项")
    if auto_by_rule:
        auto_str = ", ".join(f"{k}={v}" for k, v in sorted(auto_by_rule.items()))
        lines.append(f"  - 按规则：{auto_str}")
    lines.append("")

    lines.append("**冲突检查**")
    lines.append("")
    if conflicts:
        lines.append(f"⚠️ 发现 **{len(conflicts)}** 处冲突：")
        lines.append("")
        for c in conflicts:
            lines.append(f"- {c}")
    else:
        lines.append("✅ 通过：所有敏感词替换一致")
    lines.append("")

    lines.append("**给 LLM 的行为提示**")
    lines.append("")
    lines.append('1. **不要尝试从上下文反推原始值**——即使代号所在句子有充分上下文')
    lines.append('2. **不要基于代号编造原值**——遇到 `[PERSON_1]` 时不要猜为某个人')
    lines.append('3. **可以引用代号**——分析、总结时可以说「根据 [LEADER_1] 的指示」')
    lines.append('4. **发现矛盾请指出**——如果文档内部代号使用前后不一致，明确告知用户')
    lines.append('5. **优先信任显式信息**——不要用推断弥补缺失')
    lines.append("")

    lines.append("<!-- ============================================================== -->")
    lines.append("<!-- 脱敏后文档正文开始                                                -->")
    lines.append("<!-- ============================================================== -->")
    lines.append("")

    return "\n".join(lines)


def _describe_original(original: str) -> str:
    """生成原文的描述（不暴露完整原文，做部分遮蔽）"""
    if len(original) <= 2:
        return original[0] + "*"
    if len(original) <= 4:
        return original[0] + "**" + original[-1]
    return original[0] + "***" + original[-1]
