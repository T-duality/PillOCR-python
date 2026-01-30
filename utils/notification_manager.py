"""
跨平台系统通知管理器
"""
import platform
import threading
from utils.path_tools import get_absolute_path

# 尝试导入 plyer
PLYER_AVAILABLE = False
try:
    from plyer import notification
    PLYER_AVAILABLE = True
except ImportError:
    pass


class NotificationManager:
    """系统通知管理器"""

    def __init__(self, app_name="PillOCR"):
        self.app_name = app_name
        self.enabled = True
        try:
            self.icon_path = get_absolute_path('ocrgui.ico')
        except Exception:
            self.icon_path = None

    def notify(self, title: str, message: str, timeout: int = 5):
        """
        发送系统通知

        Args:
            title: 通知标题
            message: 通知内容
            timeout: 显示时间（秒）
        """
        if not self.enabled or not PLYER_AVAILABLE:
            return

        # 在后台线程发送通知，避免阻塞主线程
        def _send():
            try:
                notification.notify(
                    title=title,
                    message=message,
                    app_name=self.app_name,
                    app_icon=self.icon_path if platform.system() == 'Windows' else None,
                    timeout=timeout
                )
            except Exception:
                pass

        threading.Thread(target=_send, daemon=True).start()

    def notify_success(self, message: str = "识别完成，已复制到剪贴板"):
        """发送成功通知"""
        self.notify("识别成功", message)

    def notify_error(self, message: str = "识别失败"):
        """发送错误通知"""
        self.notify("识别失败", message)

    def notify_processing(self, message: str = "正在识别图像..."):
        """发送处理中通知"""
        self.notify("处理中", message, timeout=2)

    def set_enabled(self, enabled: bool):
        """设置是否启用通知"""
        self.enabled = enabled

    @staticmethod
    def is_available():
        """检查通知功能是否可用"""
        return PLYER_AVAILABLE
