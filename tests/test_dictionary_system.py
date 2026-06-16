"""v0.4.0 词典体系测试

覆盖:
  - database.py: 迁移逻辑 (老库 → 新库)
  - dictionary_init.py: BUILTIN 初始化 (幂等)
  - dictionary_io.py: CSV 导入/导出
  - temp_dictionary.py: 临时词典 (去重/重复)
  - document_processor.py: 临时词典集成
  - word_library.py: scope 相关 (copy_builtin_to_user, set_enabled)
"""
import json
import os
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker

from src.models.models import Base, WordEntry
from src.services.database import init_db, _migrate_v040
from src.services.dictionary_init import (
    init_builtin_dictionary,
    has_builtin_entries,
    get_default_dict_path,
)
from src.services.dictionary_io import (
    export_to_csv,
    import_from_csv,
    generate_csv_template,
    CSVFormatError,
)
from src.services.temp_dictionary import (
    TempDictionary,
    DuplicateInUserDictError,
)
from src.services.word_library import (
    WordLibraryService,
    OriginalWordConflictError,
)
from src.services.document_processor import DocumentDesensitizer


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def engine():
    return create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})


@pytest.fixture
def db(engine):
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def wordlib(db):
    return WordLibraryService(db)


@pytest.fixture
def desensitizer(db):
    d = DocumentDesensitizer(db)
    d.refresh_temp_dict_user_lookup()
    return d


@pytest.fixture
def tmp_csv(tmp_path):
    """临时 CSV 路径"""
    return tmp_path / "test_dict.csv"


# ============================================================
# 数据库迁移
# ============================================================

class TestDatabaseMigration:
    """v0.4.0 迁移: scope + enabled 字段"""

    def test_fresh_db_has_new_columns(self, engine):
        """新建库应包含 scope/enabled 字段"""
        Base.metadata.create_all(engine)
        inspector = inspect(engine)
        cols = {c['name'] for c in inspector.get_columns('word_entries')}
        assert 'scope' in cols
        assert 'enabled' in cols

    def test_migrate_old_db_adds_columns(self):
        """老库 (8字段) → 新库 (10字段)"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            path = f.name
        try:
            engine = create_engine(f"sqlite:///{path}")

            # 模拟老库 (无 scope/enabled)
            with engine.begin() as conn:
                conn.execute(text('''
                    CREATE TABLE word_entries (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        category VARCHAR(20) NOT NULL,
                        original TEXT NOT NULL UNIQUE,
                        placeholder VARCHAR(50) NOT NULL UNIQUE,
                        created_at DATETIME,
                        last_used_at DATETIME,
                        hit_count INTEGER DEFAULT 0,
                        note VARCHAR(200)
                    )
                '''))
                conn.execute(text('''
                    INSERT INTO word_entries (category, original, placeholder, note)
                    VALUES ('PERSON', '张三', '[PERSON_1]', '老数据')
                '''))

            # 跑迁移
            _migrate_v040(engine)

            # 验证
            inspector = inspect(engine)
            cols = {c['name'] for c in inspector.get_columns('word_entries')}
            assert 'scope' in cols
            assert 'enabled' in cols

            # 验证老数据保留 + 默认值
            with engine.connect() as conn:
                row = conn.execute(text(
                    "SELECT original, scope, enabled FROM word_entries"
                )).fetchone()
                assert row[0] == '张三'
                assert row[1] == 'USER'  # 默认
                assert row[2] == 1  # 默认 True (SQLite BOOLEAN -> INTEGER)

        finally:
            os.unlink(path)

    def test_migrate_is_idempotent(self, engine):
        """迁移跑两次不会报错"""
        with engine.begin() as conn:
            conn.execute(text('''
                CREATE TABLE word_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category VARCHAR(20) NOT NULL,
                    original TEXT NOT NULL,
                    placeholder VARCHAR(50) NOT NULL
                )
            '''))
        _migrate_v040(engine)
        _migrate_v040(engine)  # 第二次不应报错
        inspector = inspect(engine)
        cols = {c['name'] for c in inspector.get_columns('word_entries')}
        assert 'scope' in cols
        assert 'enabled' in cols


# ============================================================
# BUILTIN 初始化
# ============================================================

class TestBuiltinInit:
    """出厂预置词典初始化"""

    def test_default_dict_path_exists(self):
        """默认 JSON 文件应存在"""
        path = get_default_dict_path()
        assert path.exists(), f"默认词典文件不存在: {path}"

    def test_init_first_time(self, db):
        """首次初始化应插入 BUILTIN 词条"""
        assert not has_builtin_entries(db)
        inserted = init_builtin_dictionary(db)
        assert inserted > 0
        assert has_builtin_entries(db)

    def test_init_idempotent(self, db):
        """重复调用不会重复插入"""
        first = init_builtin_dictionary(db)
        second = init_builtin_dictionary(db)
        assert first > 0
        assert second == 0

    def test_builtin_scope_and_disabled(self, db):
        """BUILTIN 词条 scope=BUILTIN, enabled=False"""
        init_builtin_dictionary(db)
        entries = db.query(WordEntry).filter_by(scope="BUILTIN").all()
        assert all(e.scope == "BUILTIN" for e in entries)
        assert all(e.enabled == False for e in entries)  # noqa: E712

    def test_skip_existing_originals(self, db):
        """BUILTIN original 跟现有 USER 冲突时跳过"""
        # 先加一个 USER 词条, original 跟 BUILTIN 冲突
        wordlib = WordLibraryService(db)
        wordlib.add_entry("张三", scope="USER")

        # 再初始化 BUILTIN, 应该跳过"张三"
        inserted = init_builtin_dictionary(db)
        all_zs = db.query(WordEntry).filter_by(original="张三").all()
        # 只有 1 条 (USER 那条)
        assert len(all_zs) == 1
        assert all_zs[0].scope == "USER"


# ============================================================
# WordEntry scope 操作
# ============================================================

class TestWordLibraryScope:
    """WordLibraryService 的 scope 相关方法"""

    def test_copy_builtin_to_user(self, wordlib, db):
        """复制 BUILTIN → USER"""
        init_builtin_dictionary(db)
        zs_builtin = wordlib.search(scope="BUILTIN", keyword="张三")
        assert len(zs_builtin) == 1
        builtin = zs_builtin[0]

        new_user = wordlib.copy_builtin_to_user(builtin.id)

        # 验证新条目属性
        assert new_user.scope == "USER"
        assert new_user.enabled == True  # noqa: E712
        assert new_user.original == "张三"
        assert new_user.placeholder != builtin.placeholder  # 新占位符
        assert "从全局词典复制" in new_user.note

    def test_copy_builtin_twice_raises(self, wordlib, db):
        """重复复制同一条 BUILTIN 应报错"""
        init_builtin_dictionary(db)
        zs_builtin = wordlib.search(scope="BUILTIN", keyword="张三")[0]
        wordlib.copy_builtin_to_user(zs_builtin.id)

        with pytest.raises(OriginalWordConflictError):
            wordlib.copy_builtin_to_user(zs_builtin.id)

    def test_copy_non_builtin_raises(self, wordlib):
        """复制非 BUILTIN 词条应报错"""
        entry = wordlib.add_entry("李四", scope="USER")
        with pytest.raises(ValueError, match="不是 BUILTIN"):
            wordlib.copy_builtin_to_user(entry.id)

    def test_set_enabled_user_ok(self, wordlib):
        """USER 词条可以切换 enabled"""
        entry = wordlib.add_entry("李四", scope="USER")
        assert entry.enabled == True  # noqa: E712

        disabled = wordlib.set_enabled(entry.id, False)
        assert disabled.enabled == False  # noqa: E712

        re_enabled = wordlib.set_enabled(entry.id, True)
        assert re_enabled.enabled == True  # noqa: E712

    def test_set_enabled_builtin_blocked(self, wordlib, db):
        """BUILTIN 词条不允许 set_enabled"""
        init_builtin_dictionary(db)
        builtin = wordlib.search(scope="BUILTIN")[0]
        with pytest.raises(ValueError, match="不允许直接修改"):
            wordlib.set_enabled(builtin.id, True)

    def test_get_all_for_desensitization(self, wordlib, db):
        """脱敏依据查询: USER + enabled=True"""
        init_builtin_dictionary(db)
        wordlib.add_entry("李建国", scope="USER", enabled=True)
        wordlib.add_entry("王芳", scope="USER", enabled=False)
        wordlib.add_entry("张三", scope="USER", enabled=True)  # 故意同名

        entries = wordlib.get_all_for_desensitization()
        originals = {e.original for e in entries}
        # 应包含 USER+enabled 的: 李建国, 张三
        # 不应包含: 王芳 (USER 但 disabled), BUILTIN 任何
        assert "李建国" in originals
        assert "张三" in originals
        assert "王芳" not in originals
        # BUILTIN 都不在
        for e in entries:
            assert e.scope == "USER"

    def test_search_scope_filter(self, wordlib, db):
        """search 加 scope 参数"""
        init_builtin_dictionary(db)
        wordlib.add_entry("USER词", scope="USER")

        builtin = wordlib.search(scope="BUILTIN")
        user = wordlib.search(scope="USER")
        assert all(e.scope == "BUILTIN" for e in builtin)
        assert all(e.scope == "USER" for e in user)

    def test_search_enabled_only(self, wordlib, db):
        """search 加 enabled_only 参数"""
        init_builtin_dictionary(db)
        wordlib.add_entry("启用", scope="USER", enabled=True)
        wordlib.add_entry("禁用", scope="USER", enabled=False)

        enabled = wordlib.search(enabled_only=True)
        originals = {e.original for e in enabled}
        assert "启用" in originals
        assert "禁用" not in originals
        # BUILTIN 都不在 (因为默认 enabled=False)
        for e in enabled:
            assert e.scope == "USER"


# ============================================================
# CSV 导入/导出
# ============================================================

class TestCSVIo:
    """CSV 导入/导出"""

    def test_export_basic(self, wordlib, db, tmp_csv):
        """基本导出"""
        wordlib.add_entry("李建国", scope="USER", note="某局长")
        count = export_to_csv(db, tmp_csv, scope="USER")
        assert count == 1
        content = tmp_csv.read_text(encoding='utf-8-sig')
        assert "type,value,note" in content
        assert "李建国" in content
        assert "某局长" in content

    def test_export_filter_scope(self, wordlib, db, tmp_csv):
        """导出按 scope 过滤"""
        init_builtin_dictionary(db)
        wordlib.add_entry("USER词", scope="USER")

        user_count = export_to_csv(db, tmp_csv, scope="USER")
        assert user_count == 1

        builtin_count = export_to_csv(db, tmp_csv.with_name("builtin.csv"), scope="BUILTIN")
        assert builtin_count > 0

    def test_import_basic(self, wordlib, db, tmp_csv):
        """基本导入"""
        tmp_csv.write_text(
            "type,value,note\n"
            "PERSON,李建国,某局长\n"
            "ORG,XX 医院,合作医院\n",
            encoding='utf-8-sig'
        )
        result = import_from_csv(db, tmp_csv)
        assert result["imported"] == 2
        assert result["skipped"] == 0
        assert len(result["errors"]) == 0

    def test_import_skip_duplicates(self, wordlib, db, tmp_csv):
        """重复 value 跳过"""
        wordlib.add_entry("李建国", scope="USER")
        tmp_csv.write_text(
            "type,value,note\n"
            "PERSON,李建国,重复\n"
            "PERSON,新词,新增\n",
            encoding='utf-8-sig'
        )
        result = import_from_csv(db, tmp_csv)
        assert result["imported"] == 1
        assert result["skipped"] == 1

    def test_import_strict_mode_raises(self, wordlib, db, tmp_csv):
        """严格模式 (skip_duplicates=False)"""
        wordlib.add_entry("李建国", scope="USER")
        tmp_csv.write_text(
            "type,value,note\n"
            "PERSON,李建国,重复\n",
            encoding='utf-8-sig'
        )
        result = import_from_csv(db, tmp_csv, skip_duplicates=False)
        # 不抛错, 但 errors 里有记录
        assert result["imported"] == 0
        assert len(result["errors"]) == 1

    def test_import_invalid_category(self, wordlib, db, tmp_csv):
        """非法 category 进 errors"""
        tmp_csv.write_text(
            "type,value,note\n"
            "INVALID_CAT,坏数据,非法\n"
            "PERSON,正常,合法\n",
            encoding='utf-8-sig'
        )
        result = import_from_csv(db, tmp_csv)
        assert result["imported"] == 1
        assert len(result["errors"]) == 1
        assert "INVALID_CAT" in result["errors"][0]["reason"]

    def test_import_empty_value(self, wordlib, db, tmp_csv):
        """空 value 进 errors"""
        tmp_csv.write_text(
            "type,value,note\n"
            "PERSON,,空值\n",
            encoding='utf-8-sig'
        )
        result = import_from_csv(db, tmp_csv)
        assert result["imported"] == 0
        assert len(result["errors"]) == 1

    def test_import_missing_columns(self, wordlib, db, tmp_csv):
        """缺列抛 CSVFormatError"""
        tmp_csv.write_text("foo,bar\n1,2\n", encoding='utf-8-sig')
        with pytest.raises(CSVFormatError, match="缺少必需列"):
            import_from_csv(db, tmp_csv)

    def test_import_skip_comment_lines(self, wordlib, db, tmp_csv):
        """跳过 # 开头注释行"""
        tmp_csv.write_text(
            "# 这是注释\n"
            "# 第二行注释\n"
            "type,value,note\n"
            "PERSON,李建国,数据\n",
            encoding='utf-8-sig'
        )
        result = import_from_csv(db, tmp_csv)
        assert result["imported"] == 1

    def test_generate_template(self, tmp_path):
        """模板生成"""
        path = tmp_path / "template.csv"
        generate_csv_template(path)
        content = path.read_text(encoding='utf-8-sig')
        assert "type,value,note" in content
        assert "# " in content  # 注释
        assert "PERSON,张三" in content  # 示例


# ============================================================
# 临时词典
# ============================================================

class TestTempDictionary:
    """TempDictionary 内存服务"""

    def test_add_basic(self):
        """基本添加"""
        td = TempDictionary()
        entry = td.add("李建国", category="PERSON")
        assert entry.original == "李建国"
        assert entry.category == "PERSON"
        assert entry.placeholder.startswith("[PERSON_T")
        assert len(td) == 1

    def test_add_duplicate_in_temp_raises(self):
        """临时词典内重复"""
        td = TempDictionary()
        td.add("李建国")
        with pytest.raises(ValueError, match="临时词典已存在"):
            td.add("李建国")

    def test_add_dup_with_user_dict_raises(self):
        """用户词典已有则禁止加入临时"""
        td = TempDictionary(user_dict_lookup={"李建国"})
        with pytest.raises(DuplicateInUserDictError):
            td.add("李建国")

    def test_empty_original_raises(self):
        """空 original 报错"""
        td = TempDictionary()
        with pytest.raises(ValueError, match="不能为空"):
            td.add("")
        with pytest.raises(ValueError, match="不能为空"):
            td.add("   ")

    def test_remove(self):
        """删除"""
        td = TempDictionary()
        td.add("李建国")
        assert td.remove("李建国") == True
        assert len(td) == 0
        assert td.remove("李建国") == False  # 已删

    def test_clear(self):
        """清空"""
        td = TempDictionary()
        td.add("A")
        td.add("B")
        td.add("C")
        count = td.clear()
        assert count == 3
        assert len(td) == 0

    def test_update_user_dict_lookup(self):
        """动态更新用户词典查询"""
        td = TempDictionary()
        # 初始: 用户词典为空, 加临时 A
        td.add("A")
        td.add("B")
        assert "A" in td
        assert "B" in td

        # 更新用户词典查询, 加 B/C
        td.update_user_dict_lookup({"B", "C"})

        # B 已在临时 → 加 B 报"临时已存在" (而不是"用户在")
        with pytest.raises(ValueError, match="临时词典已存在"):
            td.add("B")
        # A 已在临时 → 加 A 报"临时已存在"
        with pytest.raises(ValueError, match="临时词典已存在"):
            td.add("A")

        # C 不在临时, 但在用户词典 → 加 C 报"用户在"
        with pytest.raises(DuplicateInUserDictError):
            td.add("C")

        # D 不在任何词典 → 能加
        td.add("D")
        assert "D" in td

    def test_placeholder_unique_within_category(self):
        """同类目下占位符序号递增"""
        td = TempDictionary()
        e1 = td.add("A", category="PERSON")
        e2 = td.add("B", category="PERSON")
        e3 = td.add("C", category="ORG")
        assert e1.placeholder == "[PERSON_T1]"
        assert e2.placeholder == "[PERSON_T2]"
        assert e3.placeholder == "[ORG_T1]"


# ============================================================
# DocumentDesensitizer 集成
# ============================================================

class TestDesensitizerIntegration:
    """DocumentDesensitizer 集成临时词典 + scope 过滤"""

    def test_user_scope_only(self, wordlib, db):
        """scan_text 只查 USER+enabled"""
        init_builtin_dictionary(db)
        wordlib.add_entry("USER词", scope="USER", enabled=True)
        wordlib.add_entry("禁用词", scope="USER", enabled=False)

        d = DocumentDesensitizer(db)
        items, _ = d.scan_text("USER词 和 禁用词 还有 BUILTIN词")

        originals = {item.original for item in items}
        assert "USER词" in originals
        assert "禁用词" not in originals
        # BUILTIN 默认不脱敏
        # (具体哪些 BUILTIN 词条被测试用到不重要, 反正 enabled=False 不参与)

    def test_temp_dict_joins_scan(self, desensitizer):
        """临时词典参与扫描"""
        text = "李建国 在会上发言。"
        desensitizer.add_temp_entry("李建国", category="PERSON", note="本次特有")

        items, _ = desensitizer.scan_text(text)
        items_with_ljg = [i for i in items if i.original == "李建国"]
        assert len(items_with_ljg) == 1
        assert items_with_ljg[0].source == "tempdict"

    def test_user_dict_priority_over_temp(self, wordlib, db):
        """用户词典优先于临时词典 (不重复生成占位符)"""
        wordlib.add_entry("李建国", scope="USER", enabled=True)
        d = DocumentDesensitizer(db)
        d.refresh_temp_dict_user_lookup()
        # 临时加同名 → 应失败
        with pytest.raises(DuplicateInUserDictError):
            d.add_temp_entry("李建国")

    def test_clear_temp_dict(self, desensitizer):
        """清空临时词典"""
        desensitizer.add_temp_entry("A")
        desensitizer.add_temp_entry("B")
        assert len(desensitizer.temp_dict) == 2
        desensitizer.clear_temp_dict()
        assert len(desensitizer.temp_dict) == 0

    def test_refresh_user_lookup(self, wordlib, db):
        """refresh_temp_dict_user_lookup 跟得上用户词典变化"""
        d = DocumentDesensitizer(db)
        d.refresh_temp_dict_user_lookup()

        # 此时临时词典为空, 加临时词"李建国"应成功
        d.add_temp_entry("李建国", category="PERSON")
        assert "李建国" in d.temp_dict

        # 清空临时, 加 USER 词
        d.clear_temp_dict()
        wordlib.add_entry("李建国", scope="USER", enabled=True)
        d.refresh_temp_dict_user_lookup()

        # 此时再加临时"李建国"应失败 (用户词典已有)
        with pytest.raises(DuplicateInUserDictError):
            d.add_temp_entry("李建国", category="PERSON")

    def test_source_field_distinguishes(self, wordlib, db):
        """source 字段区分词库/临时/AUTO"""
        wordlib.add_entry("李建国", scope="USER", enabled=True)
        d = DocumentDesensitizer(db)
        d.refresh_temp_dict_user_lookup()
        d.add_temp_entry("王芳", category="PERSON")
        text = "李建国 13812345678 王芳"

        items, _ = d.scan_text(text)
        sources = {item.source for item in items}
        assert "wordlibrary" in sources
        assert "tempdict" in sources
        assert any(s.startswith("autodetect:") for s in sources)
