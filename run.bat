@echo off
chcp 65001 >nul
title BIM-点云施工质量检测系统

echo ========================================
echo   BIM-点云施工质量检测系统
echo ========================================
echo.

cd /d "%~dp0"

echo 正在启动程序...
echo.

python main_pyqt.py

if errorlevel 1 (
    echo.
    echo [错误] PyQt5版本启动失败，尝试Tkinter版本...
    echo.
    python main_tk.py
)

if errorlevel 1 (
    echo.
    echo [错误] 程序启动失败，请检查Python环境
    echo 请运行: pip install numpy laspy PyQt5
    pause
)