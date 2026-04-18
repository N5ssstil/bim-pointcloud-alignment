# Windows 运行指南

## 一、安装 Python

1. 访问 https://www.python.org/downloads/
2. 下载 **Python 3.10** 或 **3.11**（推荐 3.10）
3. 安装时**务必勾选**：
   - ✅ **Add Python to PATH**
4. 安装完成后重启 PowerShell

验证安装：
```powershell
python --version
pip --version
```

---

## 二、获取项目代码

### 方法1：Git 克隆（推荐）
```powershell
git clone https://github.com/N5ssstil/bim-pointcloud-alignment.git
cd bim-pointcloud-alignment
```

### 方法2：直接下载 ZIP
1. 访问 https://github.com/N5ssstil/bim-pointcloud-alignment
2. 点击 "Code" → "Download ZIP"
3. 解压到任意目录

---

## 三、安装依赖

**依赖极少，只需 3 个包：**

```powershell
pip install numpy laspy PyQt5 -i https://pypi.tuna.tsinghua.edu.cn/simple
```

如果 PyQt5 安装失败，可以用 Tkinter 版本（Python 内置，无需额外安装）：
```powershell
pip install numpy laspy -i https://pypi.tuna.tsinghua.edu.cn/simple
```

---

## 四、运行程序

### 方法1：PyQt5 版本（推荐，界面更美观）
```powershell
python main_pyqt.py
```

### 方法2：Tkinter 版本（备用，无需 PyQt5）
```powershell
python main_tk.py
```

### 方法3：自动选择版本
```powershell
python run_app.py
```

---

## 五、使用流程

### 1. 导入数据
- 点击 **"选择IFC文件"** → 导入 BIM 模型（.ifc 格式）
- 点击 **"选择LAS文件"** → 导入点云数据（.las 格式）

### 2. 设置参数
- **平面检测阈值**：默认 50mm
- **最大检测平面数**：默认 10

### 3. 开始分析
- 点击 **"开始分析"** 按钮
- 等待分析完成（几秒钟）

### 4. 查看结果
| 检测项 | 说明 |
|--------|------|
| 楼层净高 | 实测值 vs 设计值 |
| 房间尺寸 | 开间、进深测量 |
| 墙面垂直度 | 法向量偏差 |
| 墙面平整度 | RMSE 计算 |

### 5. 导出报告
- 点击 **"导出报告"** → 保存 TXT 文件

---

## 六、数据准备

### IFC 文件（BIM 模型）
- 格式：.ifc（IFC2x3 或 IFC4）
- Revit 导出方法：
  1. 打开 Revit 模型
  2. 文件 → 导出 → IFC
  3. 选择 IFC 2x3 格式
  4. 保存文件

### LAS 文件（点云数据）
- 格式：.las 或 .laz
- 常见扫描设备：Faro、Leica、Trimble
- 导出时选择 LAS 1.2 或 1.4 格式

---

## 七、检测标准

| 检测项目 | 合格标准 |
|----------|----------|
| 楼层净高偏差 | ≤50mm |
| 房间尺寸偏差 | ≤30mm |
| 墙面垂直度 | ≤3° |
| 墙面平整度(RMSE) | ≤8mm |

---

## 八、常见问题

### Q: pip 安装失败
```powershell
# 使用国内镜像
pip install numpy laspy PyQt5 -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### Q: PyQt5 安装失败
- 使用 Tkinter 版本：`python main_tk.py`
- Tkinter 是 Python 内置的，无需额外安装

### Q: DLL load failed
- 安装 Visual C++ Redistributable：https://aka.ms/vs/17/release/vc_redist.x64.exe

### Q: 找不到模块
- 确认在项目目录下运行：
```powershell
cd bim-pointcloud-alignment
python main_pyqt.py
```

### Q: 中文乱码
- 确保文件编码为 UTF-8
- PowerShell 执行：`chcp 65001`

---

## 九、打包成 EXE（可选）

如果想生成独立的可执行文件：

```powershell
pip install pyinstaller
pyinstaller --onefile --windowed main_pyqt.py
```

输出文件：`dist/main_pyqt.exe`

---

## 十、快速启动脚本

创建 `run.bat` 文件：
```batch
@echo off
cd /d %~dp0
python main_pyqt.py
pause
```

双击即可运行。

---

## 技术支持

- GitHub: https://github.com/N5ssstil/bim-pointcloud-alignment
- 问题反馈：GitHub Issues

---

*最后更新: 2026-04-18*