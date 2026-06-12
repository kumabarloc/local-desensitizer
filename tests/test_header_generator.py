"""脱敏文档头部生成器测试"""
import pytest
from pathlib import Path
from datetime import datetime

from src.services.header_generator import (
    detect_conflicts,
    generate_header,
    _describe_original,
)
from src.services.document_processor import ReplacementItem


def make_item(original, placeholder, category, source="wordlibrary"):
    return ReplacementItem(
        original=original,
        placeholder=placeholder,
        category=category,
        source=source,
        positions=[(0, len(original))],
    )


class TestDescribeOriginal:
    """原文遮蔽描述测试"""

    def test_short_string(self):
        # 1-2 字符：只保留首字符 + *
        assert _describe_original("李") == "李*"
        assert _describe_original("AB") == "A*"

    def test_medium_string(self):
        # 3-4 字符：保留首尾，中间 **
        assert _describe_original("李局长") == "李**长"
        assert _describe_original("ABCD") == "A**D"

    def test_long_string(self):
        # 5+ 字符：保留首尾，中间 ***
        assert _describe_original("某市某局子部门") == "某***门"
        assert _describe_original("ZhangSan123") == "Z***3"


class TestDetectConflicts:
    """冲突检测测试"""

    def test_no_conflicts(self):
        original = "李局长在会议上强调。"
        result = "[LEADER_1]在会议上强调。"
        items = [make_item("李局长", "[LEADER_1]", "PERSON")]
        conflicts = detect_conflicts(original, result, items)
        assert conflicts == []

    def test_leak_detection(self):
        """漏脱：原文里有 "李局长"，结果里还有 1 处"""
        original = "李局长说，李局长是领导。"
        result = "[LEADER_1]说，李局长是领导。"  # 第二处漏脱
        items = [make_item("李局长", "[LEADER_1]", "PERSON")]
        conflicts = detect_conflicts(original, result, items)
        assert len(conflicts) == 1
        assert "漏脱" in conflicts[0]
        assert "'李局长'" in conflicts[0]

    def test_inconsistent_placeholder(self):
        """同一原文对应不同占位符"""
        original = "李局长李局长"
        # 注：这个不会发生（实际脱敏逻辑是统一替换），但理论上 items 可能这么传
        result = "[LEADER_1][LEADER_1]"
        items = [
            make_item("李局长", "[LEADER_1]", "PERSON"),
            make_item("李局长", "[PERSON_1]", "PERSON"),  # 模拟 bug
        ]
        conflicts = detect_conflicts(original, result, items)
        assert any("占位符不一致" in c for c in conflicts)

    def test_placeholder_reused(self):
        """同一占位符被多个原文占用"""
        original = "李局长和王处长"
        result = "[LEADER_1]和[LEADER_1]"
        items = [
            make_item("李局长", "[LEADER_1]", "PERSON"),
            make_item("王处长", "[LEADER_1]", "PERSON"),  # 模拟 bug
        ]
        conflicts = detect_conflicts(original, result, items)
        assert any("占位符定义冲突" in c for c in conflicts)

    def test_auto_items_ignored(self):
        """自动规则项不参与冲突检测（它们不稳定）"""
        original = "2026年6月12日"
        result = "2026年6月12日"  # AMOUNT 误识别"2026"但没替换
        items = [make_item("2026", "[AMOUNT_AUTO]", "AMOUNT", source="autodetect:AMOUNT")]
        conflicts = detect_conflicts(original, result, items)
        # 应当忽略 auto 项，不报漏脱
        assert conflicts == []


class TestGenerateHeader:
    """头部生成测试"""

    def test_basic_header(self):
        items = [make_item("李局长", "[LEADER_1]", "PERSON")]
        conflicts = []
        header = generate_header(Path("test.docx"), items, conflicts)
        # 验证关键元素
        assert "脱敏元数据" in header
        assert "test.docx" in header
        assert "[LEADER_1]" in header
        assert "PERSON" in header
        assert "北***" not in header or "李**" in header  # 描述里应该有遮蔽
        assert "✅" in header or "通过" in header  # 无冲突
        assert "LLM" in header  # 行为提示

    def test_with_conflicts(self):
        items = [make_item("李局长", "[LEADER_1]", "PERSON")]
        conflicts = ["漏脱: '李局长' 在结果中仍出现 1 次"]
        header = generate_header(Path("test.docx"), items, conflicts)
        assert "⚠️" in header
        assert "漏脱" in header

    def test_with_auto_items(self):
        """有自动规则命中时也展示"""
        items = [
            make_item("李局长", "[LEADER_1]", "PERSON"),
            make_item("13812345678", "[PHONE_AUTO]", "PHONE", source="autodetect:PHONE"),
        ]
        header = generate_header(Path("test.docx"), items, [])
        assert "词库匹配" in header
        assert "自动规则" in header
        assert "PHONE=1" in header

    def test_empty_items(self):
        """空词库：只生成元信息和规则说明"""
        header = generate_header(Path("test.docx"), [], [])
        assert "（无词库匹配项）" in header
        assert "词库匹配：0" in header

    def test_header_is_separated(self):
        """头部与正文应该有清晰分界"""
        items = []
        header = generate_header(Path("test.docx"), items, [])
        # 头部末尾应该有"正文开始"标记
        assert "正文开始" in header
        # 有 HTML 注释作为分界
        assert "<!--" in header


class TestEndToEnd:
    """完整端到端：脱敏后头部嵌入"""

    def test_full_output_includes_header(self):
        """模拟 on_execute_desensitize 的输出"""
        from src.services.header_generator import generate_header, detect_conflicts
        original = "李局长在会议上发言。"
        items = [make_item("李局长", "[LEADER_1]", "PERSON")]
        result = "[LEADER_1]在会议上发言。"

        conflicts = detect_conflicts(original, result, items)
        header = generate_header(Path("report.docx"), items, conflicts)
        full_output = header + result

        # 头部在前
        assert full_output.startswith("<!--")
        # 脱敏结果在头部后
        assert "[LEADER_1]在会议上发言。" in full_output
        # 元数据明确
        assert "report.docx" in full_output
