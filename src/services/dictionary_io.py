"""词典 CSV 导入/导出 (v0.4.0)

设计原则：
- CSV 是用户友好的格式 (Excel 可编辑)
- 数据库存 JSON 友好的结构化字段
- 导入时：CSV → WordEntry (scope=USER, enabled=True)
- 导出时：WordEntry → CSV (可按 scope 过滤)

CSV 格式 (v0.4.0 第一版, 三列):
    type,value,note
    PERSON,李建国,环保局局长
    ORG,XX市第三人民医院,合作医院
    KEYWORD,涉密,敏感词

未来扩展 (v0.4.x):
    - alias 字段 (用 | 分隔)
    - CUSTOM_PATTERN 类型 (正则模式)

约束：
- value 列不能为空
- type 列必须是已知 category (PERSON/ORG/KEYWORD/COMPANY/LOCATION/PROJECT/CUSTOM/...)
- 重复 value 在 USER scope 内不导入 (跳过 + 报告)
- BUILTIN scope 不通过 CSV 导入 (只能从 JSON 初始化)
"""
import csv
from io import StringIO
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session as DbSession

from src.models.models import WordEntry
from src.services.word_library import (
    WordLibraryService,
    OriginalWordConflictError,
    PlaceholderFormatError,
    PlaceholderConflictError,
)


# 允许的 category 集合 (跟 infer_category 保持一致, 可扩展)
ALLOWED_CATEGORIES = {
    "PERSON", "ORG", "COMPANY", "LOCATION", "PROJECT",
    "KEYWORD", "PHONE", "EMAIL", "IDCARD", "BANKCARD",
    "AMOUNT", "IPV4", "CUSTOM",
}


class CSVImportError(ValueError):
    """CSV 导入错误基类"""


class CSVFormatError(CSVImportError):
    """CSV 格式错误 (缺列/标题错)"""


class CSVCategoryError(CSVImportError):
    """category 不在白名单内"""


def export_to_csv(
    db: DbSession,
    output_path: Path | str,
    scope: Optional[str] = None,
) -> int:
    """导出词条到 CSV

    Args:
        db: 数据库会话
        output_path: 输出文件路径
        scope: 过滤 scope (None=全部, 'BUILTIN', 'USER')

    Returns:
        导出的条数
    """
    wl = WordLibraryService(db)
    if scope:
        entries = wl.search(scope=scope)
    else:
        from sqlalchemy import select
        entries = list(db.execute(select(WordEntry)).scalars().all())

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8-sig', newline='') as f:
        # 用 utf-8-sig 让 Excel 打开不乱码
        writer = csv.writer(f)
        writer.writerow(["type", "value", "note"])
        for e in entries:
            writer.writerow([e.category, e.original, e.note or ""])

    return len(entries)


def import_from_csv(
    db: DbSession,
    input_path: Path | str,
    skip_duplicates: bool = True,
) -> dict:
    """从 CSV 导入词条到 USER scope

    Args:
        db: 数据库会话
        input_path: 输入文件路径
        skip_duplicates: True=重复时跳过, False=重复时抛错

    Returns:
        {"imported": 成功数, "skipped": 跳过数, "errors": 错误列表}

    Raises:
        CSVFormatError: CSV 缺列/标题错
        FileNotFoundError: 文件不存在
    """
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"CSV 文件不存在: {input_path}")

    wl = WordLibraryService(db)
    result = {"imported": 0, "skipped": 0, "errors": []}

    with open(input_path, 'r', encoding='utf-8-sig', newline='') as f:
        # 跳过以 # 开头的注释行
        lines = [line for line in f if not line.lstrip().startswith('#')]
        reader = csv.DictReader(StringIO(''.join(lines)))

        # 校验标题
        if reader.fieldnames is None:
            raise CSVFormatError("CSV 文件为空")

        required = {"type", "value"}
        missing = required - set(reader.fieldnames)
        if missing:
            raise CSVFormatError(f"CSV 缺少必需列: {missing}, 实际列: {list(reader.fieldnames)}")

        for line_no, row in enumerate(reader, start=2):  # 从第2行开始 (第1行是标题)
            category = (row.get("type") or "").strip().upper()
            original = (row.get("value") or "").strip()
            note = (row.get("note") or "").strip() or None

            if not original:
                result["errors"].append({"line": line_no, "reason": "value 为空", "row": row})
                continue

            if category not in ALLOWED_CATEGORIES:
                result["errors"].append({
                    "line": line_no,
                    "reason": f"category '{category}' 不在白名单: {sorted(ALLOWED_CATEGORIES)}",
                    "row": row,
                })
                continue

            try:
                wl.add_entry(
                    original=original,
                    category=category,
                    note=note,
                    scope="USER",
                    enabled=True,
                )
                result["imported"] += 1
            except OriginalWordConflictError as e:
                if skip_duplicates:
                    result["skipped"] += 1
                else:
                    result["errors"].append({"line": line_no, "reason": str(e), "row": row})
            except (PlaceholderFormatError, PlaceholderConflictError) as e:
                result["errors"].append({"line": line_no, "reason": str(e), "row": row})

    return result


def generate_csv_template(output_path: Path | str) -> None:
    """生成 CSV 导入模板 (含示例行 + 说明行)

    模板结构:
        # 墨盾用户词典 CSV 导入模板
        # 列说明: type=分类, value=原始词(必填), note=备注(可选)
        # 允许的 type: PERSON, ORG, COMPANY, LOCATION, PROJECT, KEYWORD, CUSTOM
        type,value,note
        PERSON,张三,示例:常见测试姓名
        ORG,XX 科技有限公司,示例:客户公司
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    content = (
        "# 墨盾用户词典 CSV 导入模板 (v0.4.0)\n"
        "# 列说明: type=分类, value=原始词(必填), note=备注(可选)\n"
        "# 允许的 type: " + ", ".join(sorted(ALLOWED_CATEGORIES)) + "\n"
        "# 注意: 第一列以 # 开头的行会被跳过 (视为注释)\n"
        "#\n"
        "type,value,note\n"
        "PERSON,张三,示例:常见测试姓名\n"
        "PERSON,李四,示例:常见测试姓名\n"
        "ORG,XX 科技有限公司,示例:客户公司\n"
        "KEYWORD,机密,示例:敏感词\n"
    )
    with open(output_path, 'w', encoding='utf-8-sig', newline='') as f:
        f.write(content)
