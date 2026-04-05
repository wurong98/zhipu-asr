import pyperclip
import pyautogui

text = "要输入的中文内容"

# 写入剪贴板
pyperclip.copy(text)

# 模拟 Ctrl+V 粘贴
pyautogui.hotkey('ctrl', 'v')