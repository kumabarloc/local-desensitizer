"""文档还原服务"""
import re
import json
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from sqlalchemy.orm import Session as DbSession
from sqlalchemy import select

from src.models.models import WordEntry, Snapshot
from src.services.document_handler import get_handler


# 代号格式检测正则
PH_REGEX = re.compile(r'\[([A-Z]{2,10})_(\d+)\]')
SEMANTIC_PH_REGEX = re.compile(r'\[([A-Z]{2,10})_([A-Z]{1,6})_(\d+)\]')
RANDOM_PH_REGEX = re.compile(r'\[X_([A-Z0-9]{4})\]')
AUTO_PH_REGEX = re.compile(r'\[([A-Z]{2,10})_AUTO\]')  # L0 规则生成：无法还原，原样保留


def extract_placeholders(text: str) -> list[str]:
    """从文本中提取所有代号"""
    placeholders = set()
    for regex in [PH_REGEX, SEMANTIC_PH_REGEX, RANDOM_PH_REGEX, AUTO_PH_REGEX]:
        for match in regex.finditer(text):
            placeholders.add(match.group())
    return list(placeholders)


def is_auto_placeholder(ph: str) -> bool:
    """判断是否是 L0 自动规则生成的占位符（无法还原）"""
    return bool(AUTO_PH_REGEX.fullmatch(ph))


@dataclass
class RestoreResult:
    """还原结果"""
    restored_text: str
    unreplaced: list[str]  # 有代号但找不到映射的（排除 AUTO 规则）
    auto_unreplaced: list[str]  # L0 自动规则生成的代号（无法还原）
    nested_warnings: list[str]  # 还原后再次出现代号的
    stats: dict


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
        """还原文本

        处理逻辑：
        - 标准代号 (e.g. [LEADER_1])：有映射就还原，没映射报"无法匹配"
        - AUTO 代号 (e.g. [PHONE_AUTO])：L0 规则生成，无原始值可还原，**原样保留**
        """
        unreplaced = []
        auto_unreplaced = []
        nested_warnings = []
        result = text

        # 找出所有代号及其位置
        all_placeholders = extract_placeholders(result)
        replacement_map: dict[int, tuple[int, int, str]] = {}

        for ph in all_placeholders:
            # AUTO 占位符：无原始值可还原，原样保留
            if is_auto_placeholder(ph):
                auto_unreplaced.append(ph)
                continue

            if ph not in mappings:
                unreplaced.append(ph)
                continue

            original = mappings[ph]
            pos = 0
            while True:
                idx = result.find(ph, pos)
                if idx == -1:
                    break
                replacement_map[idx] = (idx, idx + len(ph), original)
                pos = idx + 1

        # 按位置从后往前替换
        for idx in sorted(replacement_map.keys(), reverse=True):
            start, end, replacement = replacement_map[idx]
            result = result[:start] + replacement + result[end:]

        # 检查还原后是否再次出现代号格式
        after_placeholders = extract_placeholders(result)
        for ph in after_placeholders:
            nested_warnings.append(f"还原后文本再次出现代号: {ph}")

        return RestoreResult(
            restored_text=result,
            unreplaced=unreplaced,
            auto_unreplaced=auto_unreplaced,
            nested_warnings=nested_warnings,
            stats={
                "total_placeholders": len(all_placeholders),
                "replaced": len(all_placeholders) - len(unreplaced) - len(auto_unreplaced),
                "unreplaced_count": len(unreplaced),
                "auto_unreplaced_count": len(auto_unreplaced),
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