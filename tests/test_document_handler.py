"""文档格式处理器测试"""
import pytest
from pathlib import Path
import tempfile
import os

from src.services.document_handler import (
    get_handler,
    TextHandler,
    MarkdownHandler,
    CsvHandler,
    DocxHandler,
    XlsxHandler,
    PptxHandler,
)


class TestGetHandler:
    """处理器获取测试"""

    def test_txt_handler(self):
        h = get_handler('.txt')
        assert isinstance(h, TextHandler)

    def test_md_handler(self):
        h = get_handler('.md')
        assert isinstance(h, MarkdownHandler)

    def test_csv_handler(self):
        h = get_handler('.csv')
        assert isinstance(h, CsvHandler)

    def test_docx_handler(self):
        h = get_handler('.docx')
        assert isinstance(h, DocxHandler)

    def test_xlsx_handler(self):
        h = get_handler('.xlsx')
        assert isinstance(h, XlsxHandler)

    def test_pptx_handler(self):
        h = get_handler('.pptx')
        assert isinstance(h, PptxHandler)

    def test_unsupported_handler(self):
        h = get_handler('.pdf')
        assert h is None


class TestTextHandler:
    """纯文本文档测试"""

    def test_read_write(self, tmp_path):
        h = TextHandler()
        test_file = tmp_path / "test.txt"
        h.write(test_file, "Hello\nWorld")
        content = h.read(test_file)
        assert content == "Hello\nWorld"

    def test_extension(self):
        h = TextHandler()
        assert h.get_extension() == ".txt"


class TestCsvHandler:
    """CSV文档测试"""

    def test_read_write(self, tmp_path):
        h = CsvHandler()
        test_file = tmp_path / "test.csv"
        h.write(test_file, "Name,Age\n张三,25\n李四,30")
        content = h.read(test_file)
        assert "张三,25" in content
        assert "李四,30" in content


class TestDocxHandler:
    """Word文档测试"""

    def test_write_and_read(self, tmp_path):
        h = DocxHandler()
        test_file = tmp_path / "test.docx"
        h.write(test_file, "第一行\n第二行\n第三行")
        content = h.read(test_file)
        assert "第一行" in content
        assert "第二行" in content

    def test_extension(self):
        h = DocxHandler()
        assert h.get_extension() == ".docx"


class TestXlsxHandler:
    """Excel文档测试"""

    def test_write_and_read(self, tmp_path):
        h = XlsxHandler()
        test_file = tmp_path / "test.xlsx"
        h.write(test_file, "A\tB\n1\t2\n3\t4")
        content = h.read(test_file)
        assert "=== Sheet1 ===" in content or "=== Sheet ===" in content

    def test_extension(self):
        h = XlsxHandler()
        assert h.get_extension() == ".xlsx"


class TestPptxHandler:
    """PowerPoint文档测试"""

    def test_write_and_read(self, tmp_path):
        h = PptxHandler()
        test_file = tmp_path / "test.pptx"
        h.write(test_file, "Slide 1 content\nSlide 2 content")
        content = h.read(test_file)
        assert "Slide 1 content" in content

    def test_extension(self):
        h = PptxHandler()
        assert h.get_extension() == ".pptx"