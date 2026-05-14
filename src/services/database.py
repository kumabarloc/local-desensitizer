"""数据库初始化服务"""
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from src.models.models import Base


DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "data" / "vault.db"
DEFAULT_SNAPSHOT_DIR = Path(__file__).parent.parent.parent / "data" / "snapshots"


def get_engine(db_path: str | Path | None = None):
    """创建数据库引擎"""
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})


def init_db(engine):
    """初始化数据库（创建所有表）"""
    Base.metadata.create_all(engine)


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