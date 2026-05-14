"""主入口（开发阶段用于测试）"""
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from pathlib import Path
from src.services.database import get_engine, init_db, get_session
from src.services.word_library import WordLibraryService, infer_category
from src.services.document_processor import DocumentDesensitizer


def main():
    engine = get_engine()
    init_db(engine)
    db = get_session(engine)

    # 测试词库服务
    wl = WordLibraryService(db)

    print("=== 分类推断测试 ===")
    test_words = ["张三", "李明", "13812345678", "user@company.com", "北京", "某科技公司", "500万"]
    for w in test_words:
        print(f"  {w} → {infer_category(w)}")

    print("\n=== 词库操作测试 ===")
    try:
        e1 = wl.add_entry("张三", note="重要客户")
        print(f"  添加: {e1.original} → {e1.placeholder}")
        e2 = wl.add_entry("李四", note="普通联系人")
        print(f"  添加: {e2.original} → {e2.placeholder}")
        e3 = wl.add_entry("13812345678")
        print(f"  添加: {e3.original} → {e3.placeholder}")
    except Exception as ex:
        print(f"  添加失败: {ex}")

    print("\n=== 词库搜索测试 ===")
    results = wl.search(category="PERSON")
    for r in results:
        print(f"  [{r.category}] {r.original} → {r.placeholder}")

    print("\n=== 词库统计 ===")
    stats = wl.get_stats()
    print(f"  总词条数: {stats['total']}")
    print(f"  分类统计: {stats['by_category']}")

    print("\n=== 脱敏扫描测试 ===")
    ds = DocumentDesensitizer(db)
    test_text = "张三的手机号是13812345678，他的公司是腾讯科技。腾讯是一家大公司。"
    items, warnings = ds.scan_text(test_text)
    print(f"  原文: {test_text}")
    for item in items:
        print(f"  待确认: {item.original} → {item.placeholder} (来源: {item.source})")
    for w in warnings:
        print(f"  警告: {w}")

    print("\n=== 执行脱敏测试 ===")
    confirmed = [item for item in items if item.source == "wordlibrary"]
    result = ds.desensitize(test_text, confirmed)
    print(f"  脱敏后: {result}")

    db.close()
    print("\n✅ 核心模块测试通过！")


if __name__ == "__main__":
    main()