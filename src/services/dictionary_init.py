"""词典初始化服务 (v0.4.0)

职责：
1. 首次启动时，把出厂预置词典 (default_global_dict.json) 写入数据库，scope=BUILTIN, enabled=False
2. 提供 default_global_dict.json 的路径解析 (兼容开发模式 + PyInstaller 打包后)
3. 幂等：重复调用不会重复插入 (用 scope=BUILTIN 是否已存在判断)
"""
import json
import sys
from pathlib import Path
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.orm import Session as DbSession

from src.models.models import WordEntry


def get_default_dict_path() -> Path:
    """获取出厂预置词典 JSON 路径

    - 开发模式: src/resources/default_global_dict.json
    - 打包后 (PyInstaller): sys._MEIPASS/resources/default_global_dict.json
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller 临时解压目录
        meipass = Path(getattr(sys, '_MEIPASS', Path(__file__).parent.parent.parent))
        candidate = meipass / "src" / "resources" / "default_global_dict.json"
        if candidate.exists():
            return candidate
        # 兼容某些 spec 配置（资源直接放在 _MEIPASS 根目录）
        candidate = meipass / "default_global_dict.json"
        if candidate.exists():
            return candidate
    # 开发模式
    return Path(__file__).parent.parent / "resources" / "default_global_dict.json"


def has_builtin_entries(db: DbSession) -> bool:
    """检查数据库是否已经有 BUILTIN scope 词条"""
    stmt = select(WordEntry).where(WordEntry.scope == "BUILTIN").limit(1)
    return db.execute(stmt).scalar_one_or_none() is not None


def _get_next_sequence(db: DbSession, category: str) -> int:
    """获取指定分类的下一个序号 (从所有 scope 中算最大值 +1)"""
    stmt = select(func.count(WordEntry.id)).where(WordEntry.category == category)
    count = db.execute(stmt).scalar() or 0
    return count + 1


def init_builtin_dictionary(db: DbSession, dict_path: Optional[Path] = None) -> int:
    """初始化预置词典 (仅在没有 BUILTIN scope 时执行)

    Args:
        db: 数据库会话
        dict_path: 自定义 JSON 路径（默认用 get_default_dict_path()）

    Returns:
        实际新插入的条数 (0 表示已经初始化过或 JSON 不存在)
    """
    if has_builtin_entries(db):
        return 0

    path = dict_path or get_default_dict_path()
    if not path.exists():
        return 0

    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    entries = data.get("entries", [])
    if not entries:
        return 0

    inserted = 0
    for entry_data in entries:
        original = entry_data["original"]
        category = entry_data["category"].upper()

        # 检查 original 是否已存在 (跨 scope 唯一)
        exists = db.execute(
            select(WordEntry).where(WordEntry.original == original)
        ).scalar_one_or_none()
        if exists:
            continue  # 跳过已存在的

        # 生成占位符 (BUILTIN 用独立序号, 避免和 USER 冲突)
        seq = _get_next_sequence(db, category)
        placeholder = f"[{category}_{seq}]"

        entry = WordEntry(
            original=original,
            category=category,
            placeholder=placeholder,
            note=entry_data.get("note"),
            scope="BUILTIN",
            enabled=False,  # BUILTIN 默认不直接脱敏
        )
        db.add(entry)
        inserted += 1

    if inserted > 0:
        db.commit()

    return inserted
