#!/usr/bin/env python3
"""
BIM-点云施工质量检测系统
启动入口
"""

import sys
import os
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def main():
    """主入口函数"""
    
    print("=" * 60)
    print("BIM-点云施工质量检测系统")
    print("=" * 60)
    
    # 检查依赖
    print("\n检查依赖...")
    
    missing = []
    
    try:
        import numpy
        print(f"  NumPy: {numpy.__version__} ✓")
    except ImportError:
        missing.append("numpy")
    
    try:
        import laspy
        print(f"  laspy: ✓")
    except ImportError:
        missing.append("laspy")
    
    try:
        from PyQt5.QtWidgets import QApplication
        print(f"  PyQt5: ✓")
        has_pyqt = True
    except ImportError:
        print(f"  PyQt5: 未安装")
        has_pyqt = False
    
    if missing:
        print(f"\n缺少依赖: {missing}")
        print("请运行: pip install " + " ".join(missing))
        return
    
    # 选择GUI
    if has_pyqt:
        print("\n使用PyQt5界面...")
        from main_pyqt import main as pyqt_main
        pyqt_main()
    else:
        print("\n使用Tkinter界面...")
        from main_tk import MainWindow
        import tkinter as tk
        app = MainWindow()
        app.run()


if __name__ == "__main__":
    main()