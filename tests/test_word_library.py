"""词库服务测试"""
import pytest
from src.services.word_library import (
    WordLibraryService,
    PlaceholderFormatError,
    PlaceholderConflictError,
    OriginalWordConflictError,
    validate_placeholder,
    generate_structured_placeholder,
    generate_semantic_placeholder,
    generate_random_placeholder,
    infer_category,
)


class TestPlaceholderFormat:
    """代号格式测试"""

    def test_valid_structured(self):
        assert validate_placeholder("[PERSON_1]")
        assert validate_placeholder("[COMPANY_99]")
        assert validate_placeholder("[PERSON_1024]")

    def test_valid_semantic(self):
        assert validate_placeholder("[PERSON_ZS_1]")
        assert validate_placeholder("[COMPANY_TX_1]")

    def test_valid_random(self):
        assert validate_placeholder("[X_A3F7]")
        assert validate_placeholder("[X_B2K9]")

    def test_invalid_lowercase_category(self):
        assert not validate_placeholder("[person_1]")

    def test_invalid_leading_zero(self):
        assert not validate_placeholder("[PERSON_01]")

    def test_invalid_no_brackets(self):
        assert not validate_placeholder("PERSON_1")

    def test_invalid_non_numeric_sequence(self):
        assert not validate_placeholder("[PERSON_A]")


class TestPlaceholderGeneration:
    """代号生成测试"""

    def test_generate_structured(self):
        ph = generate_structured_placeholder("PERSON", 1)
        assert ph == "[PERSON_1]"

    def test_generate_semantic(self):
        ph = generate_semantic_placeholder("PERSON", "ZS", 1)
        assert ph == "[PERSON_ZS_1]"

    def test_generate_random(self):
        ph = generate_random_placeholder()
        assert ph.startswith("[X_")
        assert len(ph) == 7  # [X_ + 4 chars + ]


class TestCategoryInference:
    """分类推断测试"""

    def test_phone(self):
        assert infer_category("13812345678") == "PHONE"

    def test_email(self):
        assert infer_category("user@company.com") == "EMAIL"

    def test_idcard(self):
        assert infer_category("110101199001011234") == "IDCARD"

    def test_bankcard(self):
        assert infer_category("6222021234567890123") == "BANKCARD"

    def test_person_surname(self):
        assert infer_category("张三") == "PERSON"
        assert infer_category("李明") == "PERSON"

    def test_company(self):
        assert infer_category("某科技有限公司") == "COMPANY"

    def test_project(self):
        assert infer_category("星链计划项目") == "PROJECT"

    def test_location(self):
        assert infer_category("北京") == "LOCATION"

    def test_custom(self):
        assert infer_category("随机无法归类的词") == "CUSTOM"


class TestWordLibraryService:
    """词库服务测试"""

    def test_add_entry(self, wordlib_service):
        entry = wordlib_service.add_entry("测试人员", note="测试")
        assert entry.original == "测试人员"
        assert entry.placeholder == "[PERSON_1]"
        assert entry.category == "PERSON"

    def test_add_duplicate_original_raises(self, wordlib_service):
        wordlib_service.add_entry("重复测试")
        with pytest.raises(OriginalWordConflictError):
            wordlib_service.add_entry("重复测试")

    def test_search_by_keyword(self, wordlib_service):
        wordlib_service.add_entry("北京")
        wordlib_service.add_entry("上海")
        wordlib_service.add_entry("广州", note="南方城市")
        results = wordlib_service.search(keyword="南方")
        assert len(results) == 1
        assert results[0].original == "广州"

    def test_search_by_category(self, wordlib_service):
        wordlib_service.add_entry("张三")
        wordlib_service.add_entry("李四")
        wordlib_service.add_entry("某科技公司")
        results = wordlib_service.search(category="PERSON")
        assert all(r.category == "PERSON" for r in results)
        assert len(results) == 2

    def test_delete_entry(self, wordlib_service):
        entry = wordlib_service.add_entry("待删除")
        wordlib_service.delete_entry(entry.id)
        results = wordlib_service.search(keyword="待删除")
        assert len(results) == 0

    def test_get_stats(self, wordlib_service):
        wordlib_service.add_entry("张三")
        wordlib_service.add_entry("李四")
        wordlib_service.add_entry("13812345678")
        stats = wordlib_service.get_stats()
        assert stats["total"] == 3
        assert stats["by_category"]["PERSON"] == 2
        assert stats["by_category"]["PHONE"] == 1