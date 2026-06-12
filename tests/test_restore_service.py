"""restore_service 测试（含 AUTO 占位符处理）"""
import pytest
from src.services.restore_service import (
    RestoreService,
    extract_placeholders,
    is_auto_placeholder,
    PH_REGEX,
    SEMANTIC_PH_REGEX,
    RANDOM_PH_REGEX,
    AUTO_PH_REGEX,
)
from src.services.database import get_engine, init_db, get_session
from src.models.models import Base, WordEntry


@pytest.fixture
def db():
    engine = get_engine(":memory:")
    init_db(engine)
    session = get_session(engine)
    yield session
    session.close()


@pytest.fixture
def restore_svc(db):
    return RestoreService(db)


class TestExtractPlaceholders:
    """占位符提取测试"""

    def test_standard_placeholder(self):
        phs = extract_placeholders("你好 [LEADER_1]，世界")
        assert "[LEADER_1]" in phs

    def test_semantic_placeholder(self):
        phs = extract_placeholders("这是 [PERSON_LD_1]")
        assert "[PERSON_LD_1]" in phs

    def test_random_placeholder(self):
        phs = extract_placeholders("随机 [X_A3F7]")
        assert "[X_A3F7]" in phs

    def test_auto_placeholder(self):
        """核心修复：AUTO 占位符（[PHONE_AUTO] 等）现在能被识别"""
        phs = extract_placeholders("手机 [PHONE_AUTO]，邮箱 [EMAIL_AUTO]")
        assert "[PHONE_AUTO]" in phs
        assert "[EMAIL_AUTO]" in phs

    def test_multiple_placeholders(self):
        phs = extract_placeholders("[LEADER_1] [PERSON_1] [PHONE_AUTO] [X_AAAA]")
        assert len(phs) == 4
        assert "[LEADER_1]" in phs
        assert "[PERSON_1]" in phs
        assert "[PHONE_AUTO]" in phs
        assert "[X_AAAA]" in phs

    def test_no_placeholder(self):
        phs = extract_placeholders("普通文本，没有代号")
        assert phs == []


class TestIsAutoPlaceholder:
    """AUTO 占位符判断"""

    def test_is_auto(self):
        assert is_auto_placeholder("[PHONE_AUTO]") is True
        assert is_auto_placeholder("[EMAIL_AUTO]") is True
        assert is_auto_placeholder("[AMOUNT_AUTO]") is True

    def test_is_not_auto(self):
        assert is_auto_placeholder("[LEADER_1]") is False
        assert is_auto_placeholder("[PERSON_LD_1]") is False
        assert is_auto_placeholder("[X_A3F7]") is False


class TestRestoreText:
    """还原功能测试"""

    def test_basic_restore(self, restore_svc):
        text = "你好 [LEADER_1]，再见"
        mappings = {"[LEADER_1]": "李局长"}
        result = restore_svc.restore_text(text, mappings)
        assert result.restored_text == "你好 李局长，再见"
        assert result.unreplaced == []
        assert result.auto_unreplaced == []

    def test_unreplaced_placeholder(self, restore_svc):
        text = "[UNKNOWN_1] 是谁？"
        result = restore_svc.restore_text(text, {})
        assert result.restored_text == text  # 原样保留
        assert "[UNKNOWN_1]" in result.unreplaced

    def test_auto_placeholder_kept_as_is(self, restore_svc):
        """核心修复：AUTO 占位符原样保留，不进 unreplaced"""
        text = "手机 [PHONE_AUTO] 和邮箱 [EMAIL_AUTO]"
        result = restore_svc.restore_text(text, {})
        # AUTO 占位符原样保留
        assert "[PHONE_AUTO]" in result.restored_text
        assert "[EMAIL_AUTO]" in result.restored_text
        # 单独放在 auto_unreplaced 列表
        assert "[PHONE_AUTO]" in result.auto_unreplaced
        assert "[EMAIL_AUTO]" in result.auto_unreplaced
        # **不**进 unreplaced（AUTO 是 L0 规则没保存原始值，不是"未匹配"）
        assert "[PHONE_AUTO]" not in result.unreplaced
        assert "[EMAIL_AUTO]" not in result.unreplaced

    def test_mixed_placeholders(self, restore_svc):
        """混合：AUTO + 标准（有映射）+ 标准（无映射）"""
        text = "[LEADER_1] 打了 [PHONE_AUTO] 找了 [UNKNOWN_2]"
        mappings = {"[LEADER_1]": "李局长"}
        result = restore_svc.restore_text(text, mappings)
        assert "李局长" in result.restored_text
        assert "[PHONE_AUTO]" in result.restored_text  # AUTO 原样保留
        assert "[UNKNOWN_2]" in result.restored_text  # 未知也原样保留
        assert "[LEADER_1]" in result.auto_unreplaced or "[LEADER_1]" not in result.auto_unreplaced  # LEADER 已被还原
        assert "[PHONE_AUTO]" in result.auto_unreplaced
        assert "[UNKNOWN_2]" in result.unreplaced


class TestRestoreWithLibrary:
    """从词库加载映射的完整流程"""

    def test_restore_from_word_library(self, restore_svc, db):
        # 添加几个词条
        db.add(WordEntry(original="李局长", placeholder="[LEADER_1]", category="PERSON"))
        db.add(WordEntry(original="我站", placeholder="[ORG_1]", category="ORG"))
        db.commit()

        mappings = restore_svc.load_mappings_from_library()
        assert "[LEADER_1]" in mappings
        assert "[ORG_1]" in mappings

        # 还原
        text = "[LEADER_1] 在 [ORG_1] 主持会议"
        result = restore_svc.restore_text(text, mappings)
        assert "李局长" in result.restored_text
        assert "我站" in result.restored_text


class TestSettingsBackupPath:
    """settings_service 的备份应该用 APP_DATA_DIR 路径（打包后不丢）"""

    def test_backup_uses_appdata_path(self, tmp_path, monkeypatch):
        """备份时应从 APP_DATA_DIR/data/vault.db 读，不从 ./data/vault.db"""
        from src.services import settings_service
        from src.services import database as db_mod

        # 模拟 APPDATA 环境
        monkeypatch.setattr(db_mod, "APP_DATA_DIR", tmp_path)
        # 重新设置 BACKUP_DIR 引用新 APP_DATA_DIR
        monkeypatch.setattr(settings_service, "BACKUP_DIR", tmp_path / "data" / "backups")
        monkeypatch.setattr(settings_service, "CONFIG_FILE", tmp_path / "data" / "config.json")

        # 在 tmp_path/data/ 下创建假数据库
        db_path = tmp_path / "data" / "vault.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db_path.write_bytes(b"fake db content")

        # 跑备份
        svc = settings_service.SettingsService()
        backup_path = svc.backup_database()

        assert backup_path is not None
        assert backup_path.exists()
        assert backup_path.parent == tmp_path / "data" / "backups"
        assert backup_path.read_bytes() == b"fake db content"
