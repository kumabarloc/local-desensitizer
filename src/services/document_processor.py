"""文档脱敏处理引擎"""
import re
import json
import uuid
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.orm import Session as DbSession

from src.models.models import WordEntry, Snapshot, Session as SessionRecord
from src.services.temp_dictionary import TempDictionary, DuplicateInUserDictError
from src.services.word_library import WordLibraryService


@dataclass
class ReplacementItem:
    """待确认替换项"""
    original: str
    placeholder: str
    category: str
    source: str  # "wordlibrary" | "tempdict" | "autodetect:PHONE" | ...
    positions: list[tuple[int, int]] = field(default_factory=list)  # start, end positions


@dataclass
class DesensitizationResult:
    """脱敏结果"""
    desensitized_text: str
    snapshot: dict
    stats: dict


class DocumentDesensitizer:
    """文档脱敏处理器

    v0.4.0 词典体系:
      1. 词库匹配 (USER scope + enabled=True) - 命中即脱敏
      2. 临时词典匹配 (内存, 文档级) - 命中即脱敏
      3. 自动规则扫描 (正则) - 命中提示用户确认
    """

    # 自动识别规则
    AUTO_PATTERNS = {
        "PHONE": (re.compile(r'1[3-9]\d{9}'), "手机号"),
        "EMAIL": (re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'), "邮箱"),
        "IDCARD": (re.compile(r'[1-9]\d{5}(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx]'), "身份证"),
        "BANKCARD": (re.compile(r'[1-9]\d{12,18}'), "银行卡号"),
        "IPV4": (re.compile(r'(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)'), "IPv4地址"),
        "AMOUNT": (re.compile(r'¥?\s*\d+(?:[,，]\d{3})*(?:[万千百]?)'), "金额"),
    }

    # 代号格式冲突检测正则
    PH_FORMAT_REGEX = re.compile(r'\[[A-Z]{2,10}_\d{1,9}\]')

    def __init__(self, db: DbSession):
        self.db = db
        # v0.4.0: 临时词典由 DocumentDesensitizer 内部管理
        # UI 端可通过 desensitizer.temp_dict.add(...) 直接操作
        self.temp_dict = TempDictionary()

    def refresh_temp_dict_user_lookup(self) -> None:
        """刷新临时词典的用户词典查询集合

        当用户词典发生变化 (新增/删除/启用切换) 时调用,
        临时词典的去重判断才能跟得上。
        """
        wl = WordLibraryService(self.db)
        user_entries = wl.get_all_for_desensitization()
        originals = {e.original for e in user_entries}
        self.temp_dict.update_user_dict_lookup(originals)

    def clear_temp_dict(self) -> int:
        """清空临时词典 (文档关闭时调用)

        Returns:
            清空的条数
        """
        return self.temp_dict.clear()

    def add_temp_entry(self, original: str, category: str = "CUSTOM", note: Optional[str] = None):
        """添加临时词条 (UI 入口)

        Raises:
            DuplicateInUserDictError: 用户词典已有此 original
            ValueError: 重复添加或参数错误
        """
        return self.temp_dict.add(original, category=category, note=note)

    def scan_text(self, text: str) -> tuple[list[ReplacementItem], list[str]]:
        """
        扫描文本，返回待确认替换列表和警告信息
        按词条长度从长到短排序后匹配
        """
        items: dict[str, ReplacementItem] = {}  # key = placeholder
        warnings = []

        # 1. 检测原文中的代号格式字符串
        format_conflicts = self.PH_FORMAT_REGEX.findall(text)
        if format_conflicts:
            for ph in set(format_conflicts):
                warnings.append(f"检测到原文含有代号格式字符串 '{ph}'")

        # 2. 词库匹配 (只查 USER + enabled, 从长到短排序)
        entries = self.db.execute(
            select(WordEntry)
            .where(WordEntry.scope == "USER", WordEntry.enabled == True)  # noqa: E712
            .order_by(func.length(WordEntry.original).desc())
        ).scalars().all()

        for entry in entries:
            if entry.original in text:
                pos = 0
                positions = []
                while True:
                    idx = text.find(entry.original, pos)
                    if idx == -1:
                        break
                    positions.append((idx, idx + len(entry.original)))
                    pos = idx + 1
                items[entry.placeholder] = ReplacementItem(
                    original=entry.original,
                    placeholder=entry.placeholder,
                    category=entry.category,
                    source="wordlibrary",
                    positions=positions
                )

        # 3. 临时词典匹配 (从长到短)
        temp_entries = sorted(self.temp_dict.get_all(), key=lambda e: len(e.original), reverse=True)
        for entry in temp_entries:
            if entry.original in text:
                # 检查是否已被词库匹配
                already_matched = any(item.original == entry.original for item in items.values())
                if not already_matched:
                    pos = 0
                    positions = []
                    while True:
                        idx = text.find(entry.original, pos)
                        if idx == -1:
                            break
                        positions.append((idx, idx + len(entry.original)))
                        pos = idx + 1
                    items[entry.placeholder] = ReplacementItem(
                        original=entry.original,
                        placeholder=entry.placeholder,
                        category=entry.category,
                        source="tempdict",
                        positions=positions
                    )

        # 4. 自动规则扫描
        for rule_name, (pattern, label) in self.AUTO_PATTERNS.items():
            for match in pattern.finditer(text):
                matched_text = match.group()
                # 检查是否已被词库/临时词典匹配
                already_matched = any(item.original == matched_text for item in items.values())
                if not already_matched:
                    # 自动规则只收集信息，不写入词库
                    key = f"autodetect:{rule_name}"
                    if key not in items:  # avoid duplicates from same rule
                        items[key] = ReplacementItem(
                            original=matched_text,
                            placeholder=f"[{rule_name}_AUTO]",
                            category=rule_name,
                            source=f"autodetect:{rule_name}",
                            positions=[(match.start(), match.end())]
                        )

        return list(items.values()), warnings

    def desensitize(self, text: str, confirmed_items: list[ReplacementItem]) -> str:
        """执行脱敏替换（从后往前替换，避免位置偏移）"""
        # 收集所有位置
        all_positions: list[tuple[int, int, str]] = []
        for item in confirmed_items:
            for start, end in item.positions:
                all_positions.append((start, end, item.placeholder))

        # 按起始位置从后往前排序（这样从后往前替换不会影响前面位置）
        all_positions.sort(key=lambda x: x[0], reverse=True)

        result = text
        for start, end, placeholder in all_positions:
            result = result[:start] + placeholder + result[end:]
        return result

    def check_collision(self, original1: str, original2: str) -> bool:
        """检查两个原始词是否存在包含关系冲突"""
        return original1 in original2 or original2 in original1

    def auto_detect(self, text: str) -> list[ReplacementItem]:
        """仅用自动规则扫描，不依赖词库"""
        items = []
        for rule_name, (pattern, label) in self.AUTO_PATTERNS.items():
            for match in pattern.finditer(text):
                matched_text = match.group()
                items.append(ReplacementItem(
                    original=matched_text,
                    placeholder=f"[{rule_name}_AUTO]",
                    category=rule_name,
                    source=f"autodetect:{rule_name}",
                    positions=[(match.start(), match.end())]
                ))
        return items