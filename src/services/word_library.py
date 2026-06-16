"""敏感词库管理核心服务"""
import re
import uuid
import json
from typing import Optional
from datetime import datetime, timezone

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
    if not placeholder.startswith('[') or not placeholder.endswith(']'):
        return False
    inner = placeholder[1:-1]
    # 结构化: [A-Z]{2,10}_\d{1,9} (序号不带前导零)
    m = re.match(r'^([A-Z]{2,10})_(\d+)$', inner)
    if m and len(m.group(2)) <= 9 and not m.group(2).startswith('0'):
        return True
    # 语义摘要: [A-Z]{2,10}_[A-Z]{1,6}_\d{1,9} (序号不带前导零)
    m = re.match(r'^([A-Z]{2,10})_([A-Z]{1,6})_(\d+)$', inner)
    if m and not m.group(3).startswith('0'):
        return True
    # 随机匿名: [X_[A-Z0-9]{4}]
    m = re.match(r'^X_([A-Z0-9]{4})$', inner)
    if m:
        return True
    return False


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
    if 2 <= len(original) <= 4 and len(original) != len(original.encode('utf-8')):
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


class WordLibraryService:
    """词库管理服务"""

    def __init__(self, db: DbSession):
        self.db = db

    def get_next_sequence(self, category: str) -> int:
        """获取指定分类的下一个序号（当前最大id+1）"""
        stmt = select(func.count(WordEntry.id)).where(WordEntry.category == category.upper())
        count = self.db.execute(stmt).scalar() or 0
        return count + 1

    def add_entry(self, original: str, category: Optional[str] = None,
                  placeholder: Optional[str] = None, note: Optional[str] = None,
                  scope: str = "USER", enabled: bool = True) -> WordEntry:
        """新增词条

        v0.4.0: 增加 scope (BUILTIN/USER) 和 enabled 参数
          - 默认 scope=USER, enabled=True (与老版本行为一致)
          - BUILTIN scope 词条应通过 init_builtin_dictionary() 批量插入
          - 普通用户调用应使用 scope='USER'
        """
        category = category or infer_category(original)
        category = category.upper()
        scope = scope.upper()
        assert scope in ("BUILTIN", "USER"), f"scope 必须是 BUILTIN 或 USER, 不能是 {scope}"

        # 检查原始词冲突 (同 scope 内 unique, BUILTIN 和 USER 可同名)
        existing = self.db.execute(
            select(WordEntry).where(
                (WordEntry.original == original) & (WordEntry.scope == scope)
            )
        ).scalar_one_or_none()
        if existing:
            raise OriginalWordConflictError(f"原始词 '{original}' 已存在于{scope}词库，映射为 {existing.placeholder}")

        # 检查包含关系冲突
        conflicts = self._check_substring_conflict(original)
        # TODO: 向用户展示冲突警告

        # 生成或校验代号
        if placeholder:
            if not validate_placeholder(placeholder):
                raise PlaceholderFormatError(f"代号 '{placeholder}' 格式不合规")
            # 检查代号冲突
            existing_ph = self.db.execute(select(WordEntry).where(WordEntry.placeholder == placeholder)).scalar_one_or_none()
            if existing_ph:
                raise PlaceholderConflictError(f"代号 '{placeholder}' 已被 '{existing_ph.original}' 占用")
        else:
            seq = self.get_next_sequence(category)
            placeholder = generate_structured_placeholder(category, seq)

        now = datetime.now(timezone.utc)
        entry = WordEntry(
            original=original,
            category=category,
            placeholder=placeholder,
            note=note,
            scope=scope,
            enabled=enabled,
            created_at=now,
            last_used_at=now,
        )
        self.db.add(entry)
        self.db.commit()
        return entry

    def _check_substring_conflict(self, original: str) -> list[str]:
        """检查包含关系冲突，返回冲突词条列表"""
        all_entries = self.db.execute(select(WordEntry)).scalars().all()
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
        entry = self.db.get(WordEntry, entry_id)
        if not entry:
            raise WordEntryNotFoundError(f"词条ID {entry_id} 不存在")
        self.db.delete(entry)
        self.db.commit()

    def search(self, keyword: Optional[str] = None,
               category: Optional[str] = None, scope: Optional[str] = None,
               enabled_only: bool = False) -> list[WordEntry]:
        """搜索词条

        v0.4.0: 增加 scope 和 enabled_only 过滤
          - scope=None: 不限
          - scope='BUILTIN'/'USER': 只查该层
          - enabled_only=True: 只查 enabled=True 的词条 (脱敏依据)
        """
        stmt = select(WordEntry)
        if category:
            stmt = stmt.where(WordEntry.category == category.upper())
        if scope:
            stmt = stmt.where(WordEntry.scope == scope.upper())
        if enabled_only:
            stmt = stmt.where(WordEntry.enabled == True)  # noqa: E712
        if keyword:
            stmt = stmt.where(
                (WordEntry.original.contains(keyword)) |
                (WordEntry.note.contains(keyword))
            )
        return list(self.db.execute(stmt).scalars().all())

    def get_stats(self) -> dict:
        """词库统计"""
        stmt = select(WordEntry.category, func.count(WordEntry.id)).group_by(WordEntry.category)
        result = self.db.execute(stmt).all()
        total = sum(r[1] for r in result)
        return {
            "total": total,
            "by_category": {r[0]: r[1] for r in result}
        }

    # === v0.4.0 词典体系方法 ===

    def copy_builtin_to_user(self, entry_id: int) -> WordEntry:
        """把 BUILTIN 词条复制为 USER 词条 (用户"领取"预置词条)

        用户从全局词典里看到想要直接用于脱敏的词条时,
        点"复制到用户词典" -> 创建一条 scope=USER, enabled=True 的新词条。
        原 BUILTIN 词条不变。
        """
        source = self.db.get(WordEntry, entry_id)
        if not source:
            raise WordEntryNotFoundError(f"词条ID {entry_id} 不存在")
        if source.scope != "BUILTIN":
            raise ValueError(f"词条 '{source.original}' 不是 BUILTIN scope, 无需复制")

        # 检查 USER 是否已有相同 original
        existing = self.db.execute(
            select(WordEntry).where(
                (WordEntry.original == source.original) & (WordEntry.scope == "USER")
            )
        ).scalar_one_or_none()
        if existing:
            raise OriginalWordConflictError(
                f"用户词典已存在 '{source.original}', 当前映射 {existing.placeholder}"
            )

        # 生成新占位符 (USER scope 的序号)
        seq = self.get_next_sequence(source.category)
        new_placeholder = generate_structured_placeholder(source.category, seq)

        now = datetime.now(timezone.utc)
        new_entry = WordEntry(
            original=source.original,
            category=source.category,
            placeholder=new_placeholder,
            note=f"从全局词典复制: {source.note or ''}".strip(":"),
            scope="USER",
            enabled=True,
            created_at=now,
            last_used_at=now,
        )
        self.db.add(new_entry)
        self.db.commit()
        return new_entry

    def set_enabled(self, entry_id: int, enabled: bool) -> WordEntry:
        """启用/禁用词条 (只对 USER scope 有意义, BUILTIN 不允许改)"""
        entry = self.db.get(WordEntry, entry_id)
        if not entry:
            raise WordEntryNotFoundError(f"词条ID {entry_id} 不存在")
        if entry.scope == "BUILTIN":
            raise ValueError("BUILTIN 词条不允许直接修改, 请用 copy_builtin_to_user()")
        entry.enabled = enabled
        self.db.commit()
        return entry

    def get_all_for_desensitization(self) -> list[WordEntry]:
        """获取所有用于脱敏的词条 (USER scope + enabled=True)

        这是脱敏时查询"用户词典完整列表"的标准入口。
        BUILTIN scope 不参与脱敏 (除非用户先 copy 到 USER)。
        """
        return self.search(scope="USER", enabled_only=True)

    def get_all_builtin(self) -> list[WordEntry]:
        """获取所有 BUILTIN 词条 (用于词典管理界面展示)"""
        return self.search(scope="BUILTIN")