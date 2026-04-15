"""终端窗口检测逻辑的单元测试"""
import unittest


# 独立的检测函数（与 asr_engine.py 中保持一致）
TERMINAL_INDICATORS = ['terminal', 'konsole', 'xterm', 'gnome-terminal',
                      'alacritty', 'tilix', 'terminator', 'kitty', 'putty',
                      'rxvt', 'urxvt', 'xfce4-terminal', 'mate-terminal']


def is_terminal_window(window_name: str, window_class: str) -> bool:
    """检测窗口是否是终端（支持前缀匹配）"""
    window_name = window_name.lower()
    window_class = window_class.lower()
    for ind in TERMINAL_INDICATORS:
        # 支持子串匹配和前缀匹配
        if ind in window_name or ind in window_class:
            return True
        # 处理 gnome-terminal-server 这类带后缀的情况
        if window_name.startswith(ind) or window_class.startswith(ind):
            return True
    return False


class TestTerminalDetection(unittest.TestCase):
    """测试终端窗口检测"""

    def test_gnome_terminal(self):
        """测试 GNOME Terminal 检测"""
        self.assertTrue(is_terminal_window("GNOME Terminal", "gnome-terminal"))
        self.assertTrue(is_terminal_window("zhipu-asr - gnome-terminal", "gnome-terminal"))
        self.assertTrue(is_terminal_window("", "gnome-terminal-server"))
        self.assertTrue(is_terminal_window("", "gnome-terminal-server"))  # xprop 输出前缀匹配

    def test_konsole(self):
        """测试 Konsole 检测"""
        self.assertTrue(is_terminal_window("konsole", "konsole"))
        self.assertTrue(is_terminal_window("root@localhost - konsole", "konsole"))

    def test_xterm(self):
        """测试 xterm 检测"""
        self.assertTrue(is_terminal_window("xterm", "xterm"))
        self.assertTrue(is_terminal_window("", "xterm"))

    def test_alacritty(self):
        """测试 Alacritty 检测"""
        self.assertTrue(is_terminal_window("alacritty", "alacritty"))
        self.assertTrue(is_terminal_window("", "Alacritty"))

    def test_kitty(self):
        """测试 Kitty 检测"""
        self.assertTrue(is_terminal_window("kitty", "kitty"))
        self.assertTrue(is_terminal_window("", "kitty"))

    def test_putty(self):
        """测试 PuTTY 检测"""
        self.assertTrue(is_terminal_window("PuTTY", "putty"))

    def test_browser(self):
        """测试浏览器不被误判为终端"""
        self.assertFalse(is_terminal_window("Google Chrome", "google-chrome"))
        self.assertFalse(is_terminal_window("Mozilla Firefox", "firefox"))
        self.assertFalse(is_terminal_window("Edge", "microsoft-edge"))
        self.assertFalse(is_terminal_window("Tab - Chromium", "chromium"))

    def test_editor(self):
        """测试编辑器不被误判为终端"""
        self.assertFalse(is_terminal_window("Visual Studio Code", "code"))
        self.assertFalse(is_terminal_window("gedit", "gedit"))
        self.assertFalse(is_terminal_window("Sublime Text", "sublime-text"))

    def test_empty(self):
        """测试空字符串"""
        self.assertFalse(is_terminal_window("", ""))
        self.assertFalse(is_terminal_window("", "code"))

    def test_case_insensitive(self):
        """测试大小写不敏感"""
        self.assertTrue(is_terminal_window("GNOME TERMINAL", "GNOME-TERMINAL"))
        self.assertTrue(is_terminal_window("Konsole", "KONSOLE"))
        self.assertTrue(is_terminal_window("KITTY", "KITTY"))

    def test_tilix(self):
        """测试 Tilix 检测"""
        self.assertTrue(is_terminal_window("tilix", "tilix"))
        self.assertTrue(is_terminal_window("", "com.gexe.tilix"))

    def test_terminator(self):
        """测试 Terminator 检测"""
        self.assertTrue(is_terminal_window("terminator", "terminator"))

    def test_rxvt_urxvt(self):
        """测试 rxvt/urxvt 检测"""
        self.assertTrue(is_terminal_window("rxvt", "rxvt"))
        self.assertTrue(is_terminal_window("urxvt", "urxvt"))

    def test_xfce4_terminal(self):
        """测试 XFCE4 Terminal 检测"""
        self.assertTrue(is_terminal_window("xfce4-terminal", "xfce4-terminal"))
        self.assertTrue(is_terminal_window("", "xfce4-terminal.real"))

    def test_mate_terminal(self):
        """测试 MATE Terminal 检测"""
        self.assertTrue(is_terminal_window("mate-terminal", "mate-terminal"))


if __name__ == "__main__":
    unittest.main()
