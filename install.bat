@echo off
chcp 65001 >nul
title 安装依赖

echo ========================================
echo   BIM-点云施工质量检测系统 - 安装依赖
echo ========================================
echo.

cd /d "%~dp0"

echo 正在安装依赖包...
echo 使用清华镜像加速下载
echo.

pip install numpy laspy PyQt5 -i https://pypi.tuna.tsinghua.edu.cn/simple

echo.
echo ========================================
echo   安装完成！
echo ========================================
echo.
echo 现在可以双击 run.bat 启动程序
echo.

pause