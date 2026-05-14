"""文档还原服务"""
import re
import json
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session as DbSession
from sqlalchemy import select

from src.models.models import WordEntry, Snapshot
from src.services.document_handler import get_handler


# 代号格式检测正则
PH_REGEX = re.compile(r'\[([A-Z]{2,10})_(\d+)\]')
SEMANTIC_PH_REGEX = re.compile(r'\[([A-Z]{2,10})_([A-Z]{1,6})_(\d+)\]')
RANDOM_PH_REGEX = re.compile(r'\[X_([A-Z0-9]{4})\]')


def extract_placeholders(text: str) -> list[str]:
    """从文本中提取所有代号"""
    placeholders = set()
    for regex in [PH_REGEX, SEMANTIC_PH_REGEX, RANDOM_PH_REGEX]:
        for match in regex.finditer(text):
            placeholders.add(match.group())
    return list(placeholders)


@dataclass
class RestoreResult:
    """还原结果"""
    restored_text: str
    unreplaced: list[str]  # 有代号但找不到映射的
    nested_warnings: list[str]  # 还原后再次出现代号的
    stats: dict


@dataclass
class UnmatchedItem:
    """未匹配的代号项"""
    placeholder: str
    position: int  # 在文本中的位置


from dataclasses import dataclass


class RestoreService:
    """文档还原服务"""

    def __init__(self, db: DbSession):
        self.db = db

    def load_mappings_from_snapshot(self, snapshot_id: str) -> dict[str, str]:
        """从快照加载映射关系（placeholder → original）"""
        snapshot = self.db.execute(
            select(Snapshot).where(Snapshot.id == snapshot_id)
        ).scalar_one_or_none()

        if not snapshot:
            return {}

        data = json.loads(snapshot.mappings)
        return {entry["placeholder"]: entry["original"] for entry in data.get("entries", [])}

    def load_mappings_from_library(self) -> dict[str, str]:
        """从当前全局词库加载映射关系"""
        entries = self.db.execute(select(WordEntry)).scalars().all()
        return {entry.placeholder: entry.original for entry in entries}

    def restore_text(
        self,
        text: str,
        mappings: dict[str, str],
        warn_on_unmatched: bool = True
    ) -> RestoreResult:
        """还原文本"""
        unreplaced = []
        nested_warnings = []
        result = text

        # 找出所有代号及其位置
        all_placeholders = extract_placeholders(result)
        replacement_map: dict[int, tuple[int, int, str]] = {}  # position → (start, end, replacement)

        for ph in all_placeholders:
            if ph not in mappings:
                unreplaced.append(ph)
                continue
            stats={
                "total_placeholders": len(all_placeholders),
                "replaced": len(all_placeholders) - len(unreplaced),
                "unreplaced_count": len(unreplaced),
            }
        )

    def restore_document(
        self,
        filepath: Path,
        snapshot_id: Optional[str] = None,
        use_library: bool = False
    ) -> RestoreResult:
        """还原文档"""
        ext = filepath.suffix
        handler = get_handler(ext)
        if not handler:
            raise ValueError(f"不支持的格式: {ext}")

        content = handler.read(filepath)

        if use_library:
            mappings = self.load_mappings_from_library()
        elif snapshot_id:
            mappings = self.load_mappings_from_snapshot(snapshot_id)
        else:
            raise ValueError("必须指定 snapshot_id 或 use_library=True")

        result = self.restore_text(content, mappings)

        # 写入还原后的文件（加 _restored 后缀）
        output_path = filepath.parent / f"{filepath.stem}_restored{filepath.suffix}"
        handler.write(output_path, result.restored_text)

        return result