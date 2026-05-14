"""批量导入服务"""
import csv
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

import pandas as pd

from src.services.word_library import WordLibraryService


@dataclass
class ImportResult:
    """导入结果"""
    total_rows: int
    imported: int
    skipped: int
    errors: list[str]


class BatchImportService:
    """批量导入服务"""

    SUPPORTED_FORMATS = {'.xlsx', '.csv'}

    def __init__(self, wordlib_service: WordLibraryService):
        self.wordlib_service = wordlib_service

    def import_file(
        self,
        filepath: Path,
        original_col: str = "original",
        category_col: Optional[str] = "category",
        note_col: Optional[str] = "note"
    ) -> ImportResult:
        """批量导入词库文件"""
        ext = filepath.suffix.lower()
        if ext not in self.SUPPORTED_FORMATS:
            raise ValueError(f"不支持的格式: {ext}，仅支持 .xlsx 和 .csv")

        if ext == '.xlsx':
            df = pd.read_excel(filepath)
        else:
            df = pd.read_csv(filepath, encoding='utf-8-sig')

        return self._import_dataframe(df, original_col, category_col, note_col)

    def _import_dataframe(
        self,
        df: pd.DataFrame,
        original_col: str,
        category_col: Optional[str],
        note_col: Optional[str]
    ) -> ImportResult:
        """从 DataFrame 导入"""
        imported = 0
        skipped = 0
        errors = []

        for idx, row in df.iterrows():
            try:
                original = str(row[original_col]).strip()
                if not original or original == 'nan':
                    skipped += 1
                    continue

                category = None
                if category_col and category_col in df.columns:
                    cat = str(row[category_col]).strip()
                    if cat and cat != 'nan':
                        category = cat

                note = None
                if note_col and note_col in df.columns:
                    n = str(row[note_col]).strip()
                    if n and n != 'nan':
                        note = n

                self.wordlib_service.add_entry(original, category=category, note=note)
                imported += 1
            except Exception as ex:
                errors.append(f"行 {idx+2}: {ex}")
                skipped += 1

        total = len(df)
        return ImportResult(
            total_rows=total,
            imported=imported,
            skipped=skipped,
            errors=errors
        )

    def preview(self, filepath: Path, original_col: str = "original") -> pd.DataFrame:
        """预览导入文件（不实际写入）"""
        ext = filepath.suffix.lower()
        if ext == '.xlsx':
            df = pd.read_excel(filepath)
        else:
            df = pd.read_csv(filepath, encoding='utf-8-sig')
        return df.head(20)