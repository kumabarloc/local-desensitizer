"""临时词典服务 (v0.4.0)

设计：
- 纯内存 dict，不持久化到磁盘
- 会话级 (一个 DocumentDesensitizer 实例一个 TempDictionary)
- 与用户词典 (USER scope) 自动去重：添加时若用户词典已有，跳过 + 轻提示
- 文档关闭/重启 app 即清空

使用场景：
- 文档预览里右键选中 → "加入临时词典"
- 脱敏主界面右侧"本次词条"侧边栏手动添加
- 用户发现"这个词本文档常用但还没加到用户词典" → 临时加入
"""
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class TempEntry:
    """临时词条 (内存对象, 不进数据库)"""
    original: str
    category: str
    placeholder: str
    note: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "original": self.original,
            "category": self.category,
            "placeholder": self.placeholder,
            "note": self.note or "",
            "created_at": self.created_at.isoformat(),
        }


# 代号格式 (跟 word_library.py 保持一致)
PH_REGEX = re.compile(r'^\[([A-Z]{2,10})_(\d{1,9})\]$')


class DuplicateInUserDictError(ValueError):
    """临时词典与用户词典冲突"""


class TempDictionary:
    """文档级临时词典

    用法:
        temp_dict = TempDictionary(user_dict_lookup=wordlib.search(scope='USER'))

        try:
            temp_dict.add("李建国", category="PERSON")
        except DuplicateInUserDictError as e:
            # 提示用户: '李建国' 已在用户词典, 跳过临时添加
            show_toast(str(e))
    """

    def __init__(self, user_dict_lookup: Optional[set[str]] = None):
        """初始化临时词典

        Args:
            user_dict_lookup: 用户词典里所有 original 的集合 (用于去重)
                调用方负责每次添加前更新这个集合 (或传一个动态查询函数)
        """
        self._entries: dict[str, TempEntry] = {}  # original -> TempEntry
        # 用函数而不是固定 set，支持动态查询
        self._user_dict_lookup = user_dict_lookup if user_dict_lookup is not None else set()
        # 按 category 维护计数器 (避免编号冲突)
        self._category_counters: dict[str, int] = {}

    def _next_sequence(self, category: str) -> int:
        self._category_counters[category] = self._category_counters.get(category, 0) + 1
        return self._category_counters[category]

    def _gen_placeholder(self, category: str) -> str:
        seq = self._next_sequence(category)
        return f"[{category.upper()}_T{seq}]"  # 用 _T 后缀区分临时词条

    def is_in_user_dict(self, original: str) -> bool:
        """检查 original 是否已在用户词典"""
        return original in self._user_dict_lookup

    def update_user_dict_lookup(self, user_dict_lookup: set[str]) -> None:
        """更新用户词典查询集合 (用于用户词典发生变化后)"""
        self._user_dict_lookup = user_dict_lookup

    def add(self, original: str, category: str = "CUSTOM", note: Optional[str] = None) -> TempEntry:
        """添加临时词条

        Args:
            original: 原始词
            category: 分类 (PERSON/ORG/KEYWORD/CUSTOM 等)
            note: 备注

        Returns:
            新建的 TempEntry

        Raises:
            DuplicateInUserDictError: 用户词典已有此 original
            ValueError: 重复添加或格式错误
        """
        original = original.strip()
        if not original:
            raise ValueError("原始词不能为空")

        if original in self._entries:
            raise ValueError(f"临时词典已存在 '{original}'")

        if original in self._user_dict_lookup:
            raise DuplicateInUserDictError(
                f"'{original}' 已在用户词典中,无需添加临时词条"
            )

        entry = TempEntry(
            original=original,
            category=category.upper(),
            placeholder=self._gen_placeholder(category),
            note=note,
        )
        self._entries[original] = entry
        return entry

    def remove(self, original: str) -> bool:
        """删除临时词条 (按 original 精确匹配)"""
        if original in self._entries:
            del self._entries[original]
            return True
        return False

    def clear(self) -> int:
        """清空临时词典 (文档关闭时调用)

        Returns:
            清空的条目数
        """
        count = len(self._entries)
        self._entries.clear()
        self._category_counters.clear()
        return count

    def get_all(self) -> list[TempEntry]:
        """获取所有临时词条"""
        return list(self._entries.values())

    def get_by_original(self, original: str) -> Optional[TempEntry]:
        """按 original 查询"""
        return self._entries.get(original)

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, original: str) -> bool:
        return original in self._entries
