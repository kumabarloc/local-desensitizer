"""数据库模型"""
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Text, Boolean, UniqueConstraint, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class WordEntry(Base):
    """敏感词条目

    v0.4.0 词典体系:
      scope: BUILTIN (出厂预置, 只读) / USER (用户自己添加)
      enabled: 是否直接参与脱敏 (BUILTIN 默认 False, USER 默认 True)
      临时词典 (TEMP) 不写数据库, 纯内存, 见 services/temp_dictionary.py
    """
    __tablename__ = "word_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    # 联合唯一: (scope, original) — 允许 BUILTIN 和 USER 各有一份"张三"
    original: Mapped[str] = mapped_column(Text, nullable=False)
    placeholder: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_used_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    hit_count: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str | None] = mapped_column(String(200), default=None)
    # === v0.4.0 词典体系 ===
    scope: Mapped[str] = mapped_column(String(20), default="USER")  # BUILTIN / USER
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)   # 是否直接脱敏

    __table_args__ = (
        UniqueConstraint('placeholder', name='uq_placeholder'),
        UniqueConstraint('scope', 'original', name='uq_scope_original'),
        Index('idx_category', 'category'),
        Index('idx_scope', 'scope'),
    )


class Snapshot(Base):
    """会话快照"""
    __tablename__ = "snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # UUID
    session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    source_filename: Mapped[str] = mapped_column(String(260), nullable=False)
    desensitized_filename: Mapped[str] = mapped_column(String(260), nullable=False)
    mappings: Mapped[str] = mapped_column(Text, nullable=False)  # JSON
    stats: Mapped[str] = mapped_column(Text, nullable=False)  # JSON


class Session(Base):
    """会话历史"""
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # UUID
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    operation_type: Mapped[str] = mapped_column(String(20), nullable=False)  # desensitization / restoration
    source_filename: Mapped[str] = mapped_column(String(260), nullable=False)
    snapshot_id: Mapped[str | None] = mapped_column(String(36), default=None)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending / completed / restored
    stats: Mapped[str] = mapped_column(Text, default="{}")  # JSON