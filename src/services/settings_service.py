"""应用配置管理"""
import json
import shutil
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

import argon2


# 默认配置（字段名与 AppConfig 一致）
DEFAULT_CONFIG = {
    "db_path": "./data/vault.db",
    "snapshot_dir": "./data/snapshots",
    "placeholder_strategy": "structured",  # structured | semantic | random
    "auto_backup": True,
    "backup_retention": 10,
    "amount_threshold": 10000,
    "fuzzy_match": False,
    "case_sensitive": False,
    "db_encryption": False,
    "access_password_hash": "",  # 空=未设置密码
}

CONFIG_FILE = Path(__file__).parent.parent.parent / "data" / "config.json"
BACKUP_DIR = Path(__file__).parent.parent.parent / "data" / "backups"

# 打包后: 用 %APPDATA%/DataVault/ 存用户数据
try:
    from src.services.database import APP_DATA_DIR
    CONFIG_FILE = APP_DATA_DIR / "data" / "config.json"
    BACKUP_DIR = APP_DATA_DIR / "data" / "backups"
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
except (ImportError, NameError):
    pass  # 导入失败时保持原路径（开发模式应该不会进这里）


@dataclass
class AppConfig:
    """应用配置"""
    db_path: str = "./data/vault.db"
    snapshot_dir: str = "./data/snapshots"
    placeholder_strategy: str = "structured"
    auto_backup: bool = True
    backup_retention: int = 10
    amount_threshold: int = 10000
    fuzzy_match: bool = False
    case_sensitive: bool = False
    db_encryption: bool = False
    access_password_hash: str = ""  # argon2 hash, never plain text

    @property
    def has_password(self) -> bool:
        return bool(self.access_password_hash)


class SettingsService:
    """设置服务"""

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or CONFIG_FILE
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config: Optional[AppConfig] = None

    def load(self) -> AppConfig:
        """加载配置"""
        if self._config is not None:
            return self._config

        if self.config_path.exists():
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self._config = AppConfig(**data)
        else:
            self._config = AppConfig(**DEFAULT_CONFIG)
            self.save(self._config)

        return self._config

    def save(self, config: AppConfig) -> None:
        """保存配置"""
        self._config = config
        data = asdict(config)
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def update(self, **kwargs) -> AppConfig:
        """更新配置项"""
        config = self.load()
        for key, value in kwargs.items():
            if hasattr(config, key):
                setattr(config, key, value)
        self.save(config)
        return config

    def get(self, key: str, default=None):
        """获取单个配置项"""
        config = self.load()
        return getattr(config, key, default)

    # --- 密码相关 ---

    def set_password(self, password: str) -> None:
        """设置访问密码（argon2 hash）"""
        config = self.load()
        config.access_password_hash = argon2.PasswordHasher().hash(password)
        self.save(config)

    def verify_password(self, password: str) -> bool:
        """验证密码"""
        config = self.load()
        if not config.has_password:
            return True  # 未设置密码，无需验证
        try:
            argon2.PasswordHasher().verify(config.access_password_hash, password)
            return True
        except argon2.exceptions.VerifyMismatchError:
            return False

    def clear_password(self) -> None:
        """清除密码"""
        config = self.load()
        config.access_password_hash = ""
        self.save(config)

    # --- 备份相关 ---

    def backup_database(self) -> Optional[Path]:
        """手动备份数据库（复制到 backup 目录）"""
        config = self.load()
        # 使用实际数据库路径（APP_DATA_DIR 下的 vault.db），
        # 而不是 config.db_path（默认是 "./data/vault.db"，打包后不对）
        from src.services.database import APP_DATA_DIR
        db_path = APP_DATA_DIR / "data" / "vault.db"
        if not db_path.exists():
            return None

        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_name = f"vault_{timestamp}.db"
        backup_path = BACKUP_DIR / backup_name

        shutil.copy2(db_path, backup_path)
        self._cleanup_old_backups()
        return backup_path

    def _cleanup_old_backups(self) -> None:
        """清理超过保留数量的旧备份"""
        config = self.load()
        if not BACKUP_DIR.exists():
            return

        backups = sorted(BACKUP_DIR.glob("vault_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in backups[config.backup_retention:]:
            old.unlink()

    def auto_backup_if_enabled(self) -> Optional[Path]:
        """如果自动备份开启，则执行备份"""
        config = self.load()
        if config.auto_backup:
            return self.backup_database()
        return None

    # --- 配置重置 ---

    def reset_to_defaults(self) -> AppConfig:
        """重置为默认配置"""
        self._config = AppConfig(**DEFAULT_CONFIG)
        self.save(self._config)
        return self._config