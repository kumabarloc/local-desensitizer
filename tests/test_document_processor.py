"""文档脱敏处理器测试"""
import pytest
from src.services.document_processor import DocumentDesensitizer, ReplacementItem


class TestAutoPatternDetection:
    """自动规则识别测试"""

    def test_phone_detection(self):
        ds = DocumentDesensitizer.__new__(DocumentDesensitizer)
        pattern = ds.AUTO_PATTERNS["PHONE"][0]
        matches = pattern.findall("张三的手机是13812345678，李四的是13898765432")
        assert len(matches) == 2
        assert "13812345678" in matches
        assert "13898765432" in matches

    def test_email_detection(self):
        ds = DocumentDesensitizer.__new__(DocumentDesensitizer)
        pattern = ds.AUTO_PATTERNS["EMAIL"][0]
        matches = pattern.findall("联系user@company.com或admin@test.org")
        assert len(matches) == 2

    def test_idcard_detection(self):
        ds = DocumentDesensitizer.__new__(DocumentDesensitizer)
        pattern = ds.AUTO_PATTERNS["IDCARD"][0]
        matches = pattern.findall("身份证110101199001011234是伪造的")
        assert "110101199001011234" in matches

    def test_amount_detection(self):
        ds = DocumentDesensitizer.__new__(DocumentDesensitizer)
        pattern = ds.AUTO_PATTERNS["AMOUNT"][0]
        matches = pattern.findall("项目预算500万，另有¥1,000,000备用金")
        assert "500万" in matches
        assert "¥1,000,000" in matches


class TestDesensitization:
    """脱敏处理测试"""

    def test_scan_text_with_wordlibrary(self, desensitizer_service, wordlib_service):
        """词库匹配扫描测试"""
        wordlib_service.add_entry("张三")
        wordlib_service.add_entry("腾讯")
        items, warnings = desensitizer_service.scan_text("张三在腾讯工作")
        placeholders = {item.placeholder for item in items}
        assert "[PERSON_1]" in placeholders
        assert "[COMPANY_2]" in placeholders

    def test_scan_text_with_autodetect(self, desensitizer_service):
        """自动规则扫描测试"""
        items, warnings = desensitizer_service.scan_text("联系13812345678")
        phone_items = [i for i in items if i.source == "autodetect:PHONE"]
        assert len(phone_items) == 1
        assert phone_items[0].original == "13812345678"

    def test_scan_text_format_conflict_warning(self, desensitizer_service, wordlib_service):
        """代号格式冲突警告测试"""
        items, warnings = desensitizer_service.scan_text("项目代号是[PROJECT_1]")
        assert any("代号格式字符串" in w for w in warnings)

    def test_desensitize_replace_all_occurrences(self, desensitizer_service):
        """同一原始词多次出现时全部替换"""
        item = ReplacementItem(
            original="腾讯",
            placeholder="[COMPANY_1]",
            category="COMPANY",
            source="wordlibrary",
            positions=[(0, 2), (6, 8)]
        )
        result = desensitizer_service.desensitize("腾讯和腾讯", [item])
        assert result == "[COMPANY_1]和[COMPANY_1]"

    def test_desensitize_from_long_to_short(self, desensitizer_service, wordlib_service):
        """包含关系冲突：长词优先匹配"""
        wordlib_service.add_entry("腾讯")
        wordlib_service.add_entry("腾讯科技")
        items, _ = desensitizer_service.scan_text("腾讯科技是腾讯的子公司")
        # 应该只有"腾讯科技"被匹配（更长）
        company_items = [i for i in items if i.category == "COMPANY"]
        assert any(i.original == "腾讯科技" for i in company_items)

    def test_collision_check(self, desensitizer_service):
        """包含关系冲突检测"""
        assert desensitizer_service.check_collision("腾讯", "腾讯科技") == True
        assert desensitizer_service.check_collision("腾讯科技", "腾讯") == True
        assert desensitizer_service.check_collision("北京", "上海") == False