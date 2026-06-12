"""设置服务测试"""
import pytest
import json
import tempfile
from pathlib import Path

from src.services.settings_service import SettingsService, AppConfig, DEFAULT_CONFIG, BACKUP_DIR


@pytest.fixture
def tmp_config_file(tmp_path):
    return tmp_path / "config.json"


@pytest.fixture
def settings(tmp_config_file):
    return SettingsService(config_path=tmp_config_file)


class TestAppConfig:
    """配置数据类测试"""

    def test_default_values(self):
        config = AppConfig()
        assert config.db_path == "./data/vault.db"
        assert config.placeholder_strategy == "structured"
        assert config.auto_backup == True
        assert config.backup_retention == 10
        assert config.has_password == False

    def test_has_password_true_when_set(self):
        config = AppConfig(access_password_hash="fakehash")
        assert config.has_password == True


class TestSettingsService:
    """设置服务测试"""

    def test_load_creates_default_config(self, settings, tmp_config_file):
        """首次加载时创建默认配置"""
        assert not tmp_config_file.exists()
        config = settings.load()
        assert config.placeholder_strategy == "structured"
        assert tmp_config_file.exists()

    def test_load_reads_existing_config(self, settings, tmp_config_file):
        """加载已存在的配置"""
        config = settings.load()
        config2 = settings.load()
        assert config is config2  # same instance (cached)

    def test_update_config(self, settings):
        """更新配置项"""
        config = settings.update(
            placeholder_strategy="semantic",
            amount_threshold=5000
        )
        assert config.placeholder_strategy == "semantic"
        assert config.amount_threshold == 5000

    def test_get_single_value(self, settings):
        """获取单个配置项"""
        settings.update(amount_threshold=20000)
        assert settings.get("amount_threshold") == 20000
        assert settings.get("nonexistent", "default") == "default"

    def test_reset_to_defaults(self, settings):
        """重置为默认配置"""
        settings.update(placeholder_strategy="random", amount_threshold=5000)
        config = settings.reset_to_defaults()
        assert config.placeholder_strategy == "structured"
        assert config.amount_threshold == 10000

    def test_save_persists_to_disk(self, settings, tmp_config_file):
        """保存配置到磁盘"""
        settings.update(placeholder_strategy="semantic")
        # 重新创建实例验证读取
        settings2 = SettingsService(config_path=tmp_config_file)
        config = settings2.load()
        assert config.placeholder_strategy == "semantic"


class TestPasswordManagement:
    """密码管理测试"""

    def test_set_and_verify_password(self, settings):
        """设置并验证密码"""
        settings.set_password("mysecretpassword")
        assert settings.verify_password("mysecretpassword") == True
        assert settings.verify_password("wrongpassword") == False

    def test_clear_password(self, settings):
        """清除密码"""
        settings.set_password("secret")
        settings.clear_password()
        config = settings.load()
        assert config.access_password_hash == ""
        assert config.has_password == False

    def test_no_password_no_verification(self, settings):
        """未设置密码时验证始终通过"""
        settings.clear_password()
        assert settings.verify_password("anypassword") == True


class TestBackup:
    """备份功能测试"""

    def test_backup_database_creates_file(self, settings, tmp_path, monkeypatch):
        """备份数据库创建备份文件"""
        # 创建一个假的数据库文件
        db_path = tmp_path / "test.db"
        db_path.write_text("fake database content")
        settings.update(db_path=str(db_path))

        backup_path = settings.backup_database()
        assert backup_path is not None
        assert backup_path.exists()
        assert backup_path.stat().st_size > 0

    def test_auto_backup_respects_setting(self, settings, tmp_path, monkeypatch):
        """自动备份受设置控制"""
        settings.update(auto_backup=False)
        # 即使调用也不会真正备份
        result = settings.auto_backup_if_enabled()
        assert result is None

    def test_cleanup_old_backups(self, settings, tmp_path, monkeypatch):
        """清理旧备份"""
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        # 创建 15 个假备份
        for i in range(15):
            p = BACKUP_DIR / f"vault_20260101_{i:06d}.db"
            p.write_text(f"backup {i}")

        settings.update(backup_retention=5)
        settings._cleanup_old_backups()

        remaining = list(BACKUP_DIR.glob("vault_*.db"))
        assert len(remaining) == 5

    def test_backup_database_nonexistent_db(self, settings, tmp_path, monkeypatch):
        """数据库不存在时返回 None（指向不存在的 APP_DATA_DIR）"""
        from src.services import database as db_mod
        # 指向不存在的目录
        nonexistent = tmp_path / "nonexistent_appdata"
        monkeypatch.setattr(db_mod, "APP_DATA_DIR", nonexistent)
        # 重新设置 BACKUP_DIR
        from src.services import settings_service
        monkeypatch.setattr(settings_service, "BACKUP_DIR", nonexistent / "data" / "backups")
        result = settings.backup_database()
        assert result is None