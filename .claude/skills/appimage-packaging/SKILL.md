---
name: appimage-packaging
description: Use when building AppImage for Python/PySide6 applications, especially when system tray icons are missing or Qt platform errors occur
---

# AppImage Packaging for Python/PySide6

## Overview

Build distributable AppImage for Python GUI applications using PyInstaller + appimagetool. Handles common issues with PySide6 system tray icons and Qt platform warnings.

## When to Use

- Building standalone AppImage from Python project
- PySide6/Qt application needs system tray
- `QObject::connect: No such signal` warnings appear
- Tray icon missing in AppImage but works in development

## Quick Reference

### Build Commands

```bash
# 1. PyInstaller one-dir build
pyinstaller --onedir --name zhipu \
  --add-data "assets:assets" \
  --hidden-import zhipuai,sounddevice,numpy,pynput,yaml,pyperclip,pyautogui,PySide6 \
  asr_engine.py zhipu_tray.py

# 2. Create AppDir structure
mkdir -p AppDir/usr/bin AppDir/usr/share/applications AppDir/usr/share/icons/hicolor/256x256/apps

# 3. Copy files
cp -r dist/zhipu/* AppDir/usr/bin/
cp assets/icons/icon.png AppDir/zhipu.png

# 4. Create AppRun and .desktop
# See Implementation section below

# 5. Build AppImage
chmod +x appimagetool
ARCH=x86_64 ./appimagetool AppDir Zhipu.AppImage
```

### Download appimagetool

```bash
curl -L -o appimagetool https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage
chmod +x appimagetool
```

## Common Problems and Fixes

### Problem: Tray Icon Missing in AppImage

**Symptoms:** App works in `python script.py` but no tray icon in AppImage

**Causes:**
1. `QT_QPA_PLATFORM=offscreen` in AppRun prevents GUI features
2. `QIcon` not wrapped properly with `setIcon()`
3. Icon path not resolved in PyInstaller bundle

**Fixes:**

1. **Remove offscreen platform** from AppRun:
```bash
# ❌ WRONG - causes missing tray
export QT_QPA_PLATFORM=offscreen

# ✅ CORRECT - let Qt detect platform automatically
# Just remove the line
```

2. **Wrap QPixmap with QIcon**:
```python
# ❌ WRONG - setIcon expects QIcon, not QPixmap
self.tray.setIcon(self.animated_icon.idle_pixmap)

# ✅ CORRECT
self.tray.setIcon(QIcon(self.animated_icon.idle_pixmap))
```

3. **Fix icon path for PyInstaller**:
```python
def get_base_dir():
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS)
    return Path(__file__).parent
```

### Problem: `QObject::connect: No such signal QPlatformNativeInterface::systemTrayWindowChanged(QScreen*)`

**This is a PySide6 bug, not your code.** The warning appears but doesn't affect functionality.

**Workaround:** No fix needed, ignore the warning.

### Problem: SVG Icons Not Displaying

**Solution:** Convert SVG to PNG for system tray
```bash
convert -size 256x256 icon.svg icon.png
# or with ImageMagick 7
magick convert -size 256x256 icon.svg icon.png
```

## Implementation

### AppRun Script

```bash
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"
export PATH="${HERE}/usr/bin:${PATH}"
export LD_LIBRARY_PATH="${HERE}/usr/bin/_internal:${LD_LIBRARY_PATH}"
exec "${HERE}/usr/bin/zhipu" "$@"
```

### .desktop File

```desktop
[Desktop Entry]
Name=Zhipu 语音输入
Comment=Zhipu AI 语音输入法托盘应用
Exec=zhipu
Icon=zhipu
Type=Application
Categories=Utility;X-VoiceInput;
Terminal=false
```

**Note:** Use `X-VoiceInput` not `VoiceInput` - VoiceInput is not a registered category.

### PyInstaller Spec File (if needed)

```python
# zhipu.spec
a = Analysis(['zhipu_tray.py', 'asr_engine.py'],
             pathex=[],
             binaries=[],
             datas=[('assets', 'assets')],
             hiddenimports=['zhipuai','sounddevice','numpy','pynput','yaml','pyperclip','pyautogui','PySide6'],
             ...)
```

## Gitignore for Build Artifacts

```
__pycache__/
log/
config.yaml
build/
dist/
*.spec
*.AppImage
package/
```

## Verification

```bash
# Test AppImage
./Zhipu.AppImage &

# Check process running
ps aux | grep zhipu | grep -v grep

# Check for tray icon (KDE/GNOME)
# Icon should appear in system tray area
```
