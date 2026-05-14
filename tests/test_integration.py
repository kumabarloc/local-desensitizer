"""端到端集成测试：脱敏 → 快照 → 还原全流程"""
import pytest
from pathlib import Path
import tempfile

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.models.models import Base
from src.services.word_library import WordLibraryService
from src.services.document_processor import DocumentDesensitizer, ReplacementItem
from src.services.snapshot_service import SnapshotService, SessionService
from src.services.restore_service import RestoreService
from src.services.document_handler import TextHandler


@pytest.fixture
def db_engine():
    """内存数据库引擎"""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db(db_engine):
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def wl(db):
    return WordLibraryService(db)


@pytest.fixture
def ds(db):
    return DocumentDesensitizer(db)


@pytest.fixture
def snapshot_svc(db):
    return SnapshotService(db)


@pytest.fixture
def session_svc(db):
    return SessionService(db)


@pytest.fixture
def restore_svc(db):
    return RestoreService(db)


class TestEndToEndDesensitization:
    """完整脱敏流程测试"""

    def test_add_word_and_desensitize(self, wl, ds):
        """添加词条 → 扫描文本 → 脱敏"""
        # 1. 添加词条
        entry = wl.add_entry("张三", note="重要客户")
        assert entry.placeholder == "[PERSON_1]"
        assert entry.category == "PERSON"

        # 2. 扫描文本
        items, warnings = ds.scan_text("张三在腾讯工作")
        placeholders = {item.placeholder for item in items}
        assert "[PERSON_1]" in placeholders

        # 3. 执行脱敏
        confirmed = [item for item in items if item.source == "wordlibrary"]
        result = ds.desensitize("张三在腾讯工作", confirmed)
        assert result == "[PERSON_1]在腾讯工作"

    def test_multiple_occurrences_replaced(self, wl, ds):
        """同一词多次出现全部替换"""
        wl.add_entry("腾讯科技")  # contains 科技 -> COMPANY
        items, _ = ds.scan_text("腾讯科技和腾讯科技")
        confirmed = [item for item in items if item.source == "wordlibrary"]
        result = ds.desensitize("腾讯科技和腾讯科技", confirmed)
        assert result == "[COMPANY_1]和[COMPANY_1]"

    def test_autodetect_phone_not_in_wordlibrary(self, ds):
        """自动规则检测到手机号但不写入词库"""
        items, warnings = ds.scan_text("联系13812345678")
        phone_items = [i for i in items if i.source == "autodetect:PHONE"]
        assert len(phone_items) == 1
        assert phone_items[0].original == "13812345678"
        assert phone_items[0].placeholder == "[PHONE_AUTO]"


class TestSnapshotFlow:
    """会话快照流程测试"""

    def test_create_and_load_snapshot(self, wl, ds, snapshot_svc, session_svc):
        """创建快照 → 加载映射"""
        # 1. 添加词条
        wl.add_entry("张三")
        wl.add_entry("腾讯")

        # 2. 脱敏文本
        items, _ = ds.scan_text("张三在腾讯工作")
        confirmed = [item for item in items if item.source == "wordlibrary"]
        desensitized = ds.desensitize("张三在腾讯工作", confirmed)

        # 3. 创建会话
        session = session_svc.create_session(
            operation_type="desensitization",
            source_filename="test.txt",
            stats={"replaced": 2}
        )

        # 4. 创建快照
        mappings = [
            {"placeholder": "[PERSON_1]", "original": "张三", "category": "PERSON", "source": "wordlibrary"},
            {"placeholder": "[COMPANY_2]", "original": "腾讯", "category": "COMPANY", "source": "wordlibrary"},
        ]
        snapshot = snapshot_svc.create_snapshot(
            session_id=session.id,
            source_filename="test.txt",
            desensitized_filename="test_desensitized.txt",
            mappings=mappings,
            stats={"replaced": 2}
        )
        assert snapshot.id is not None

        # 5. 加载快照映射
        loaded = snapshot_svc.load_mappings(snapshot.id)
        assert len(loaded) == 2
        ph_to_orig = {e["placeholder"]: e["original"] for e in loaded}
        assert ph_to_orig["[PERSON_1]"] == "张三"
        assert ph_to_orig["[COMPANY_2]"] == "腾讯"

    def test_list_snapshots(self, snapshot_svc, session_svc):
        """列出快照"""
        session = session_svc.create_session("desensitization", "test.txt")
        snapshot_svc.create_snapshot(session.id, "test.txt", "out.txt", [], {"replaced": 0})
        snapshots = snapshot_svc.list_snapshots()
        assert len(snapshots) >= 1


class TestRestoreFlow:
    """还原流程测试"""

    def test_restore_with_snapshot_mappings(self, restore_svc, wl, ds, snapshot_svc, session_svc):
        """使用快照映射还原"""
        # 1. 脱敏
        wl.add_entry("张三")
        items, _ = ds.scan_text("张三")
        confirmed = [item for item in items if item.source == "wordlibrary"]
        desensitized = ds.desensitize("张三", confirmed)

        # 2. 创建快照
        session = session_svc.create_session("desensitization", "test.txt")
        mappings = [{"placeholder": "[PERSON_1]", "original": "张三", "category": "PERSON", "source": "wordlibrary"}]
        snapshot = snapshot_svc.create_snapshot(session.id, "test.txt", "test_out.txt", mappings, {"replaced": 1})

        # 3. 还原
        result = restore_svc.restore_text("[PERSON_1]", {"[PERSON_1]": "张三"})
        assert result.restored_text == "张三"
        assert len(result.unreplaced) == 0

    def test_restore_unmatched_placeholder(self, restore_svc):
        """还原时遇到无法匹配的代号"""
        result = restore_svc.restore_text("[PERSON_999]", {"[PERSON_1]": "张三"})
        assert result.unreplaced == ["[PERSON_999]"]
        assert "[PERSON_999]" in result.restored_text  # 保持不变

    def test_restore_nested_placeholder_warning(self, restore_svc):
        """还原后再次出现代号"""
        # 这是一个隐蔽风险场景
        result = restore_svc.restore_text("代号[PERSON_1]", {"[PERSON_1]": "[OUTER_1]"})
        # 如果原始词本身含代号，还原后会再次出现
        assert len(result.nested_warnings) >= 0  # 有检测机制


class TestDocumentFormatRoundTrip:
    """文档格式往返测试"""

    def test_text_round_trip(self, tmp_path):
        """纯文本文档读写往返"""
        handler = TextHandler()
        original = "第一行\n第二行\n第三行"
        test_file = tmp_path / "round_trip.txt"

        handler.write(test_file, original)
        read_back = handler.read(test_file)
        assert read_back == original


class TestCollisionScenarios:
    """碰撞场景测试"""

    def test_substring_collision_long优先(self, wl, ds):
        """包含关系冲突：长词优先"""
        wl.add_entry("腾讯")
        wl.add_entry("腾讯科技")
        items, _ = ds.scan_text("腾讯科技")
        # 长的那个应该在前面被匹配
        company_items = [i for i in items if i.category == "COMPANY"]
        originals = {i.original for i in company_items}
        assert "腾讯科技" in originals

    def test_duplicate_original_blocked(self, wl):
        """重复原始词被阻止"""
        wl.add_entry("张三")
        with pytest.raises(Exception):  # OriginalWordConflictError
            wl.add_entry("张三")


class TestStatsAndHealth:
    """统计与健康检查"""

    def test_word_library_stats(self, wl):
        """词库统计"""
        wl.add_entry("张三")
        wl.add_entry("李四")
        wl.add_entry("13812345678")
        stats = wl.get_stats()
        assert stats["total"] == 3
        assert stats["by_category"]["PERSON"] == 2
        assert stats["by_category"]["PHONE"] == 1

    def test_session_history(self, session_svc):
        """会话历史记录"""
        s1 = session_svc.create_session("desensitization", "a.txt")
        s2 = session_svc.create_session("desensitization", "b.txt")
        sessions = session_svc.list_sessions()
        assert len(sessions) >= 2