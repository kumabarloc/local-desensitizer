"""敏感词库管理核心服务"""
import re
import uuid
import json
from typing import Optional
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.orm import Session as DbSession

from src.models.models import WordEntry


class PlaceholderFormatError(ValueError):
    """代号格式错误"""


class PlaceholderConflictError(ValueError):
    """代号冲突"""


class OriginalWordConflictError(ValueError):
    """原始词冲突"""


class WordEntryNotFoundError(ValueError):
    """词条未找到"""


# 代号格式正则: [A-Z]{2,10}_\d{1,9}]
PH_REGEX = re.compile(r'^\[([A-Z]{2,10})_(\d{1,9})\]$')
SEMANTIC_PH_REGEX = re.compile(r'^\[([A-Z]{2,10})_([A-Z]{1,6})_(\d{1,9})\]$')
RANDOM_PH_REGEX = re.compile(r'^\[X_([A-Z0-9]{4})\]$')


def validate_placeholder(placeholder: str) -> bool:
    """校验代号格式是否合规"""
    return bool(PH_REGEX.match(placeholder) or
                SEMANTIC_PH_REGEX.match(placeholder) or
                RANDOM_PH_REGEX.match(placeholder))


def generate_structured_placeholder(category: str, sequence: int) -> str:
    """生成结构化代号"""
    return f"[{category.upper()}_{sequence}]"


def generate_semantic_placeholder(category: str, pinyin_initials: str, sequence: int) -> str:
    """生成语义摘要代号"""
    return f"[{category.upper()}_{pinyin_initials.upper()}_{sequence}]"


def generate_random_placeholder() -> str:
    """生成随机匿名代号"""
    import secrets
    chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    code = ''.join(secrets.choice(chars) for _ in range(4))
    return f"[X_{code}]"


def infer_category(original: str) -> str:
    """智能推断分类"""
    # 手机号
    if re.match(r'^1[3-9]\d{9}$', original):
        return "PHONE"
    # 邮箱
    if '@' in original and re.search(r'[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', original):
        return "EMAIL"
    # 身份证
    if re.match(r'^[1-9]\d{5}(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx]$', original):
        return "IDCARD"
    # 银行卡
    if re.match(r'^[1-9]\d{12,18}$', original):
        return "BANKCARD"
    # 金额
    if re.search(r'¥?\s*\d+(?:[,，]\d{3})*(?:[万千百]?)', original):
        return "AMOUNT"
    # IP地址
    if re.match(r'^(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)$', original):
        return "IPV4"
    # 人名（百家姓 + 2-4字姓名模式）
    from src.resources.surname_dict import SURNAMES
    if 2 <= len(original) <= 4 and len(original) == len(original.encode('utf-8')):
        first_char = original[0]
        if first_char in SURNAMES and re.match(r'^[\u4e00-\u9fff]+$', original):
            return "PERSON"
    # 公司
    company_keywords = ['公司', '集团', '科技', '工作室', '企业', '有限', '股份']
    if any(kw in original for kw in company_keywords):
        return "COMPANY"
    # 项目
    project_keywords = ['项目', '计划', '工程', '方案', '任务']
    if any(kw in original for kw in project_keywords):
        return "PROJECT"
    # 地点
    from src.resources.location_dict import LOCATIONS
    if original in LOCATIONS:
        return "LOCATION"
    return "CUSTOM"


def get_next_sequence(db: DbSession, category: str) -> int:
    """获取指定分类的下一个序号"""
    stmt = select(func.max(WordEntry.id)).where(WordEntry.category == category.upper())
    result = db.execute(stmt).scalar()
    if result is None:
        return 1
    # 最大ID+1（简化处理，实际用单独的sequence字段更优，此处保持结构不变）
    stmt2 = select(func.count(WordEntry.id)).where(WordEntry.category == category.upper())
    return db.execute(stmt2).scalar() + 1


class WordLibraryService:
    """词库管理服务"""

    def __init__(self, db: DbSession):
        self.db = db

    def add_entry(self, original: str, category: Optional[str] = None,
                  placeholder: Optional[str] = None, note: Optional[str] = None) -> WordEntry:
        """新增词条"""
        category = category or infer_category(original)
        category = category.upper()

        # 检查原始词冲突
        existing = db.execute(select(WordEntry).where(WordEntry.original == original)).scalar_one_or_none()
        if existing:
            raise OriginalWordConflictError(f"原始词 '{original}' 已存在于词库，映射为 {existing.placeholder}")

        # 检查包含关系冲突
        self._check_substring_conflict(original)

        # 生成或校验代号
        if placeholder:
            if not validate_placeholder(placeholder):
                raise PlaceholderFormatError(f"代号 '{placeholder}' 格式不合规")
            # 检查代号冲突
            existing_ph = db.execute(select(WordEntry).where(WordEntry.placeholder == placeholder)).scalar_one_or_none()
            if existing_ph:
                raise PlaceholderConflictError(f"代号 '{placeholder}' 已被 '{existing_ph.original}' 占用")
        else:
            seq = get_next_sequence(self.db, category)
            placeholder = generate_structured_placeholder(category, seq)

        entry = WordEntry(
            original=original,
            category=category,
            placeholder=placeholder,
            note=note,
            created_at=datetime.utcnow(),
            last_used_at=datetime.utcnow(),
        )
        self.db.add(entry)
        self.db.commit()
        return entry

    def _check_substring_conflict(self, original: str) -> list[str]:
        """检查包含关系冲突，返回冲突词条列表"""
        all_entries = db.execute(select(WordEntry)).scalars().all()
        conflicts = []
        for e in all_entries:
            if original != e.original:
                if original in e.original:
                    conflicts.append(f"'{original}' 是已有词条 '{e.original}' 的子串")
                elif e.original in original:
                    conflicts.append(f"'{original}' 包含已有词条 '{e.original}'")
        return conflicts

    def delete_entry(self, entry_id: int) -> None:
        """删除词条"""
        entry = db.get(WordEntry, entry_id)
        if not entry:
            raise WordEntryNotFoundError(f"词条ID {entry_id} 不存在")
        db.delete(entry)
        db.commit()

    def search(self, keyword: Optional[str] = None,
               category: Optional[str] = None) -> list[WordEntry]:
        """搜索词条"""
        stmt = select(WordEntry)
        if category:
            stmt = stmt.where(WordEntry.category == category.upper())
        if keyword:
            stmt = stmt.where(
                (WordEntry.original.contains(keyword)) |
                (WordEntry.note.contains(keyword))
            )
        return list(db.execute(stmt).scalars().all())

    def get_stats(self) -> dict:
        """词库统计"""
        stmt = select(WordEntry.category, func.count(WordEntry.id)).group_by(WordEntry.category)
        result = db.execute(stmt).all()
        total = sum(r[1] for r in result)
        return {
            "total": total,
            "by_category": {r[0]: r[1] for r in result}
        }