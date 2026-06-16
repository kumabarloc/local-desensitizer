"""数据库初始化服务"""
import os
import sys
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from src.models.models import Base


def get_app_data_dir() -> Path:
    """获取应用数据目录（持久化用户数据的位置）

    - 开发模式: 项目根目录的 data/
    - 打包后 (PyInstaller): %APPDATA%/墨盾/ (用户配置目录)
      这样 exe 可以放在 Program Files 等只读位置而不会丢数据
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后：用 Windows %APPDATA% 存数据
        appdata = os.environ.get('APPDATA')
        if appdata:
            data_dir = Path(appdata) / "墨盾"
            data_dir.mkdir(parents=True, exist_ok=True)
            return data_dir
        # fallback: exe 所在目录
        return Path(sys.executable).parent
    # 开发模式：项目根目录
    return Path(__file__).parent.parent.parent


APP_DATA_DIR = get_app_data_dir()
DEFAULT_DB_PATH = APP_DATA_DIR / "data" / "vault.db"
DEFAULT_SNAPSHOT_DIR = APP_DATA_DIR / "data" / "snapshots"


def get_engine(db_path: str | Path | None = None):
    """创建数据库引擎"""
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})


def init_db(engine):
    """初始化数据库（创建所有表 + 迁移）"""
    Base.metadata.create_all(engine)
    _migrate_v040(engine)


def _migrate_v040(engine):
    """v0.4.0 迁移：给 word_entries 加 scope 和 enabled 字段

    设计原则：
    - 增量式迁移，老库无缝升级（不会重建表/丢数据）
    - 已有词条默认 scope=USER, enabled=True（保持现有行为）
    - BUILTIN scope 的词条由 init_builtin_dictionary() 首次启动时插入
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if 'word_entries' not in inspector.get_table_names():
        return  # 新建库，create_all 已经包含新字段，不需要迁移

    existing_columns = {c['name'] for c in inspector.get_columns('word_entries')}

    with engine.begin() as conn:  # 自动 commit
        if 'scope' not in existing_columns:
            conn.execute(text(
                "ALTER TABLE word_entries ADD COLUMN scope VARCHAR(20) DEFAULT 'USER'"
            ))
        if 'enabled' not in existing_columns:
            conn.execute(text(
                "ALTER TABLE word_entries ADD COLUMN enabled BOOLEAN DEFAULT 1"
            ))
        # 索引（IF NOT EXISTS 防止重复创建报错）
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_scope ON word_entries (scope)"
        ))


def get_session(engine) -> Session:
    """获取数据库会话"""
    return sessionmaker(bind=engine)()


def get_next_session_id() -> str:
    """生成新的会话ID"""
    import uuid
    return str(uuid.uuid4())


def get_next_snapshot_id() -> str:
    """生成新的快照ID"""
    import uuid
    return str(uuid.uuid4())
