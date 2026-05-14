"""pytest配置"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.models.models import Base


@pytest.fixture
def engine():
    """创建测试数据库引擎（内存数据库）"""
    return create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})


@pytest.fixture
def db(engine):
    """创建测试数据库会话"""
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def wordlib_service(db):
    """词库服务fixture"""
    from src.services.word_library import WordLibraryService
    return WordLibraryService(db)


@pytest.fixture
def desensitizer_service(db):
    """脱敏处理器fixture"""
    from src.services.document_processor import DocumentDesensitizer
    return DocumentDesensitizer(db)