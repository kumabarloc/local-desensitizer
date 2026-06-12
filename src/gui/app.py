"""墨盾 GUI 应用入口"""
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon

from src import __version__, __app_name__, __app_name_en__
from src.gui.main_window import MainWindow
from src.services.database import get_engine, init_db, get_session
from src.services.word_library import WordLibraryService
from src.services.document_processor import DocumentDesensitizer
from src.services.snapshot_service import SnapshotService, SessionService
from src.services.restore_service import RestoreService
from src.services.settings_service import SettingsService
from src.services.batch_import import BatchImportService


def get_app_icon_path() -> Path:
    """获取应用图标路径（兼容开发与打包两种模式）"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后
        return Path(sys._MEIPASS) / "assets" / "icon.ico"
    # 开发模式
    return Path(__file__).parent.parent / "assets" / "icon.ico"


class AppService:
    """应用服务聚合器（连接所有服务层）"""

    def __init__(self):
        # 数据库
        self.engine = get_engine()
        init_db(self.engine)
        self.db = get_session(self.engine)

        # 核心服务
        self.wordlib = WordLibraryService(self.db)
        self.desensitizer = DocumentDesensitizer(self.db)
        self.snapshot_svc = SnapshotService(self.db)
        self.session_svc = SessionService(self.db)
        self.restore_svc = RestoreService(self.db)
        self.settings = SettingsService()

        # 批量导入
        self.batch_import_svc = BatchImportService(self.wordlib)

    def backup(self):
        return self.settings.auto_backup_if_enabled()

    def batch_import(self, path: Path):
        return self.batch_import_svc.import_file(path)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(__app_name__)
    app.setApplicationVersion(__version__)
    app.setApplicationDisplayName(f"{__app_name__} v{__version__}")
    app.setOrganizationName(__app_name_en__)
    app.setStyle("Fusion")  # 跨平台统一风格

    # 设置应用图标
    icon_path = get_app_icon_path()
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # 初始化应用服务
    service = AppService()

    # 创建并显示主窗口
    window = MainWindow(service)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
