"""会话快照服务"""
import json
import uuid
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from src.models.models import Snapshot, Session as SessionRecord


DEFAULT_SNAPSHOT_DIR = Path(__file__).parent.parent.parent / "data" / "snapshots"

# 打包后: 用 %APPDATA%/DataVault/ 存快照
try:
    from src.services.database import APP_DATA_DIR
    DEFAULT_SNAPSHOT_DIR = APP_DATA_DIR / "data" / "snapshots"
    DEFAULT_SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
except (ImportError, NameError):
    pass


class SnapshotService:
    """会话快照管理"""

    def __init__(self, db: DbSession, snapshot_dir: Path = DEFAULT_SNAPSHOT_DIR):
        self.db = db
        self.snapshot_dir = Path(snapshot_dir)
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

    def create_snapshot(
        self,
        session_id: str,
        source_filename: str,
        desensitized_filename: str,
        mappings: list[dict],
        stats: dict
    ) -> Snapshot:
        """创建新快照"""
        snapshot_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        snapshot = Snapshot(
            id=snapshot_id,
            session_id=session_id,
            created_at=now,
            source_filename=source_filename,
            desensitized_filename=desensitized_filename,
            mappings=json.dumps({"entries": mappings, "version": "1.0"}),
            stats=json.dumps(stats),
        )
        self.db.add(snapshot)
        self.db.commit()
        return snapshot

    def get_snapshot(self, snapshot_id: str) -> Optional[Snapshot]:
        """获取快照"""
        return self.db.execute(
            select(Snapshot).where(Snapshot.id == snapshot_id)
        ).scalar_one_or_none()

    def load_mappings(self, snapshot_id: str) -> list[dict]:
        """从快照加载映射关系"""
        snapshot = self.get_snapshot(snapshot_id)
        if not snapshot:
            return []
        data = json.loads(snapshot.mappings)
        return data.get("entries", [])

    def list_snapshots(self) -> list[Snapshot]:
        """列出所有快照"""
        return list(self.db.execute(
            select(Snapshot).order_by(Snapshot.created_at.desc())
        ).scalars().all())

    def delete_snapshot(self, snapshot_id: str) -> None:
        """删除快照"""
        snapshot = self.get_snapshot(snapshot_id)
        if snapshot:
            self.db.delete(snapshot)
            self.db.commit()

    def export_snapshot(self, snapshot_id: str) -> dict:
        """导出会话快照（不含original，用于团队共享）"""
        snapshot = self.get_snapshot(snapshot_id)
        if not snapshot:
            return {}
        data = json.loads(snapshot.mappings)
        return {
            "snapshot_id": snapshot_id,
            "source_filename": snapshot.source_filename,
            "created_at": snapshot.created_at.isoformat(),
            "entries": [
                {"placeholder": e["placeholder"], "category": e["category"]}
                for e in data.get("entries", [])
            ],
            "stats": json.loads(snapshot.stats),
        }


class SessionService:
    """会话历史管理"""

    def __init__(self, db: DbSession):
        self.db = db

    def create_session(
        self,
        operation_type: str,
        source_filename: str,
        snapshot_id: Optional[str] = None,
        stats: Optional[dict] = None
    ) -> SessionRecord:
        """创建新会话"""
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        session = SessionRecord(
            id=session_id,
            created_at=now,
            operation_type=operation_type,
            source_filename=source_filename,
            snapshot_id=snapshot_id,
            status="pending",
            stats=json.dumps(stats or {}),
        )
        self.db.add(session)
        self.db.commit()
        return session

    def get_session(self, session_id: str) -> Optional[SessionRecord]:
        """获取会话"""
        return self.db.execute(
            select(SessionRecord).where(SessionRecord.id == session_id)
        ).scalar_one_or_none()

    def update_status(self, session_id: str, status: str, stats: Optional[dict] = None) -> None:
        """更新会话状态"""
        session = self.get_session(session_id)
        if session:
            session.status = status
            if stats:
                session.stats = json.dumps(stats)
            self.db.commit()

    def list_sessions(
        self,
        operation_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50
    ) -> list[SessionRecord]:
        """列出会话历史"""
        stmt = select(SessionRecord)
        if operation_type:
            stmt = stmt.where(SessionRecord.operation_type == operation_type)
        if status:
            stmt = stmt.where(SessionRecord.status == status)
        stmt = stmt.order_by(SessionRecord.created_at.desc()).limit(limit)
        return list(self.db.execute(stmt).scalars().all())