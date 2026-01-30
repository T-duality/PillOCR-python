import platform

# 平台检测
CURRENT_PLATFORM = platform.system()
IS_WINDOWS = CURRENT_PLATFORM == "Windows"
IS_MACOS = CURRENT_PLATFORM == "Darwin"

# 尝试导入特定平台的模块
KEYBOARD_AVAILABLE = False
if IS_WINDOWS:
    try:
        import keyboard

        KEYBOARD_AVAILABLE = True
    except ImportError:
        pass


class HotkeyManager:
    def __init__(self, callback=None):
        """
        Args:
            callback: 热键触发时执行的回调函数
        """
        self.callback = callback
        self.current_hotkey = None
        self.is_active = False
        # 添加截图监听相关属性
        self.screenshot_callback = None
        self.screenshot_hotkey = None
        self.screenshot_active = False

    def register_hotkey(self, hotkey_str):
        """注册热键

        Args:
            hotkey_str: 热键字符串，如 'ctrl+shift+o'

        Returns:
            bool: 是否成功注册
        """
        raise NotImplementedError("子类必须实现此方法")

    def unregister_hotkey(self, hotkey_str=None):
        """取消注册热键

        Args:
            hotkey_str: 要取消的热键，如果为None则取消当前热键

        Returns:
            bool: 是否成功取消
        """
        raise NotImplementedError("子类必须实现此方法")

    def register_screenshot_listener(self, hotkey_str, callback):
        """注册截图快捷键监听

        Args:
            hotkey_str: 截图快捷键字符串
            callback: 监听到快捷键时的回调函数

        Returns:
            bool: 是否成功注册
        """
        raise NotImplementedError("子类必须实现此方法")

    def unregister_screenshot_listener(self):
        """取消截图快捷键监听

        Returns:
            bool: 是否成功取消
        """
        raise NotImplementedError("子类必须实现此方法")

    def set_callback(self, callback):
        """设置热键触发回调

        Args:
            callback: 回调函数
        """
        self.callback = callback

    @staticmethod
    def is_supported():
        """检查当前平台是否支持全局热键

        Returns:
            bool: 当前平台是否支持
        """
        return KEYBOARD_AVAILABLE

    @staticmethod
    def should_show_ui():
        """判断是否应该显示热键相关UI元素

        Returns:
            bool: 是否应显示UI
        """
        return IS_WINDOWS  # 只在Windows上显示热键UI


class WindowsHotkeyManager(HotkeyManager):
    """Windows平台的热键管理实现"""

    def register_hotkey(self, hotkey_str):
        if not KEYBOARD_AVAILABLE:
            return False

        try:
            # 先取消已有的热键
            self.unregister_hotkey()

            # 注册新热键
            keyboard.add_hotkey(hotkey_str, self.callback)
            self.current_hotkey = hotkey_str
            self.is_active = True
            return True
        except Exception:
            return False

    def unregister_hotkey(self, hotkey_str=None):
        if not KEYBOARD_AVAILABLE:
            return False

        try:
            key_to_remove = hotkey_str or self.current_hotkey
            if key_to_remove:
                keyboard.remove_hotkey(key_to_remove)
                if hotkey_str is None or hotkey_str == self.current_hotkey:
                    self.current_hotkey = None
                    self.is_active = False
            return True
        except Exception:
            return False

    def register_screenshot_listener(self, hotkey_str, callback):
        if not KEYBOARD_AVAILABLE:
            return False

        try:
            # 先取消已有的截图监听
            self.unregister_screenshot_listener()

            # 注册新的截图监听
            keyboard.add_hotkey(hotkey_str, callback)
            self.screenshot_hotkey = hotkey_str
            self.screenshot_callback = callback
            self.screenshot_active = True
            return True
        except Exception:
            return False

    def unregister_screenshot_listener(self):
        if not KEYBOARD_AVAILABLE:
            return False

        try:
            if self.screenshot_hotkey:
                keyboard.remove_hotkey(self.screenshot_hotkey)
                self.screenshot_hotkey = None
                self.screenshot_callback = None
                self.screenshot_active = False
            return True
        except Exception:
            return False


class MacOSHotkeyManager(HotkeyManager):
    """macOS平台的热键管理实现 - 空实现"""

    def register_hotkey(self, hotkey_str):
        # macOS上不支持，返回假成功
        self.current_hotkey = hotkey_str
        self.is_active = False
        return True

    def unregister_hotkey(self, hotkey_str=None):
        # macOS上不支持，返回假成功
        if hotkey_str is None or hotkey_str == self.current_hotkey:
            self.current_hotkey = None
            self.is_active = False
        return True

    def register_screenshot_listener(self, hotkey_str, callback):
        # macOS上不支持，返回假成功
        self.screenshot_hotkey = hotkey_str
        self.screenshot_callback = callback
        self.screenshot_active = False
        return True

    def unregister_screenshot_listener(self):
        # macOS上不支持，返回假成功
        self.screenshot_hotkey = None
        self.screenshot_callback = None
        self.screenshot_active = False
        return True


def create_hotkey_manager(callback=None):
    """工厂方法，根据平台创建合适的热键管理器

    Args:
        callback: 热键触发回调函数

    Returns:
        HotkeyManager: 热键管理器实例
    """
    if IS_WINDOWS:
        return WindowsHotkeyManager(callback)
    else:  # macOS或其他平台
        return MacOSHotkeyManager(callback)
