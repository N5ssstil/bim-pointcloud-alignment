#!/usr/bin/env python3
"""
BIM-点云施工质量检测系统 - 本地运行启动脚本
双版本支持：PyQt5（推荐）/ Tkinter（备用）
"""

import sys
import os
from pathlib import Path

# 设置项目路径
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

print("=" * 70)
print("  BIM-点云施工质量检测系统 v1.0")
print("=" * 70)

# 检查依赖
print("\n[检查依赖]")

missing_deps = []
installed_deps = []

try:
    import numpy as np
    installed_deps.append(f"NumPy {np.__version__}")
except ImportError:
    missing_deps.append("numpy")

try:
    import laspy
    installed_deps.append("laspy")
except ImportError:
    missing_deps.append("laspy")

try:
    from PyQt5.QtWidgets import QApplication
    installed_deps.append("PyQt5")
    HAS_PYQT = True
except ImportError:
    HAS_PYQT = False

# 显示依赖状态
for dep in installed_deps:
    print(f"  ✓ {dep}")

for dep in missing_deps:
    print(f"  ✗ {dep} (未安装)")

if missing_deps:
    print("\n请安装缺失依赖:")
    print(f"  pip install {' '.join(missing_deps)}")
    sys.exit(1)

# 选择GUI版本
if HAS_PYQT:
    print("\n[启动PyQt5界面]")
    from main_pyqt import main as pyqt_main
    pyqt_main()
else:
    print("\n[启动Tkinter界面] (PyQt5未安装)")
    from main_tk import MainWindow
    import tkinter as tk
    root = tk.Tk()
    app = MainWindow(root)
    root.mainloop()