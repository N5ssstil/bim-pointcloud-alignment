#!/usr/bin/env python3
"""
BIM-点云施工质量检测系统 - PyQt5版本
适用于Python 3.7+环境，本地电脑运行
"""

import sys
import os
import traceback
import numpy as np
from pathlib import Path
from datetime import datetime
import threading

# PyQt5导入
try:
    from PyQt5.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QPushButton, QFileDialog, QGroupBox, QTextEdit,
        QProgressBar, QTabWidget, QTableWidget, QTableWidgetItem,
        QHeaderView, QMessageBox, QSplitter, QFrame, QComboBox,
        QSpinBox, QDoubleSpinBox, QCheckBox, QGridLayout, QStatusBar,
        QAction, QToolBar, QMenu, QMenuBar
    )
    from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize
    from PyQt5.QtGui import QFont, QColor, QIcon, QPalette
    HAS_PYQT = True
except ImportError as e:
    HAS_PYQT = False
    print(f"警告: PyQt5未安装，请运行: pip install PyQt5")
    print(f"错误详情: {e}")

# 导入核心分析模块
sys.path.insert(0, str(Path(__file__).parent))
from core.quality_analyzer import QualityAnalyzer


class AnalysisWorker(QThread):
    """后台分析线程"""
    progress = pyqtSignal(str)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    
    def __init__(self, ifc_path, las_path, params=None):
        super().__init__()
        self.ifc_path = ifc_path
        self.las_path = las_path
        self.params = params or {}
    
    def run(self):
        try:
            self.progress.emit("正在解析BIM模型...")
            analyzer = QualityAnalyzer(self.ifc_path, self.las_path)
            
            self.progress.emit("正在读取点云数据...")
            analyzer.load_data()
            
            threshold = self.params.get('threshold', 0.05)
            max_planes = self.params.get('max_planes', 10)
            
            self.progress.emit("正在检测平面...")
            planes = analyzer.detect_planes(threshold=threshold, max_planes=max_planes)
            
            self.progress.emit("正在测量房间尺寸...")
            room_dims = analyzer.measure_room()
            
            self.progress.emit("正在分析墙面质量...")
            wall_quality = analyzer.analyze_walls()
            
            self.progress.emit("正在生成报告...")
            report = analyzer.generate_report()
            
            result = {
                'planes': planes,
                'room_dims': room_dims,
                'wall_quality': wall_quality,
                'report': report,
                'bim_info': analyzer.bim_info,
                'las_info': analyzer.las_info
            }
            
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class MainWindow(QMainWindow):
    """主窗口 - PyQt5版本"""
    
    def __init__(self):
        super().__init__()
        self.ifc_path = None
        self.las_path = None
        self.analysis_result = None
        self.worker = None
        
        self.init_ui()
        self.create_menu()
    
    def init_ui(self):
        """初始化界面"""
        self.setWindowTitle("BIM-点云施工质量检测系统 v1.0")
        self.setGeometry(100, 100, 1200, 800)
        
        # 设置样式
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f5f5;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #cccccc;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
            QTableWidget {
                gridline-color: #d9d9d9;
                background-color: white;
            }
            QTabWidget::pane {
                border: 1px solid #cccccc;
                background-color: white;
            }
        """)
        
        # 主布局
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(15, 15, 15, 15)
        
        # ===== 文件导入区域 =====
        import_group = QGroupBox("📁 文件导入")
        import_layout = QGridLayout(import_group)
        
        # BIM文件
        import_layout.addWidget(QLabel("BIM模型 (IFC):"), 0, 0)
        self.ifc_label = QLabel("未选择")
        self.ifc_label.setStyleSheet("color: #999999;")
        import_layout.addWidget(self.ifc_label, 0, 1)
        self.btn_ifc = QPushButton("选择文件")
        self.btn_ifc.setStyleSheet("background-color: #2196F3;")
        self.btn_ifc.clicked.connect(self.select_ifc)
        import_layout.addWidget(self.btn_ifc, 0, 2)
        
        # 点云文件
        import_layout.addWidget(QLabel("点云数据 (LAS/LAZ):"), 1, 0)
        self.las_label = QLabel("未选择")
        self.las_label.setStyleSheet("color: #999999;")
        import_layout.addWidget(self.las_label, 1, 1)
        self.btn_las = QPushButton("选择文件")
        self.btn_las.setStyleSheet("background-color: #2196F3;")
        self.btn_las.clicked.connect(self.select_las)
        import_layout.addWidget(self.btn_las, 1, 2)
        
        import_layout.setColumnStretch(1, 1)
        
        main_layout.addWidget(import_group)
        
        # ===== 参数设置区域 =====
        params_group = QGroupBox("⚙️ 分析参数")
        params_layout = QHBoxLayout(params_group)
        
        params_layout.addWidget(QLabel("平面检测阈值(mm):"))
        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setRange(10, 100)
        self.threshold_spin.setValue(50)
        self.threshold_spin.setSuffix(" mm")
        params_layout.addWidget(self.threshold_spin)
        
        params_layout.addSpacing(20)
        
        params_layout.addWidget(QLabel("最大检测平面数:"))
        self.max_planes_spin = QSpinBox()
        self.max_planes_spin.setRange(5, 20)
        self.max_planes_spin.setValue(10)
        params_layout.addWidget(self.max_planes_spin)
        
        params_layout.addStretch()
        
        main_layout.addWidget(params_group)
        
        # ===== 分析控制区域 =====
        control_group = QGroupBox("▶️ 分析控制")
        control_layout = QHBoxLayout(control_group)
        
        self.btn_analyze = QPushButton("🔍 开始分析")
        self.btn_analyze.setEnabled(False)
        self.btn_analyze.setMinimumWidth(120)
        self.btn_analyze.clicked.connect(self.start_analysis)
        control_layout.addWidget(self.btn_analyze)
        
        self.btn_export = QPushButton("📄 导出报告")
        self.btn_export.setEnabled(False)
        self.btn_export.setStyleSheet("background-color: #FF9800;")
        self.btn_export.clicked.connect(self.export_report)
        control_layout.addWidget(self.btn_export)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumWidth(200)
        control_layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("请选择BIM和点云文件")
        self.status_label.setStyleSheet("color: #666666; font-size: 12px;")
        control_layout.addWidget(self.status_label)
        
        control_layout.addStretch()
        
        main_layout.addWidget(control_group)
        
        # ===== 结果显示区域 =====
        result_tabs = QTabWidget()
        
        # 概览标签页
        overview_tab = QWidget()
        overview_layout = QVBoxLayout(overview_tab)
        
        # 检测结果表格
        overview_layout.addWidget(QLabel("检测结果概览"))
        self.result_table = QTableWidget()
        self.result_table.setColumnCount(5)
        self.result_table.setHorizontalHeaderLabels([
            "检测项目", "设计值", "实测值", "偏差", "评定"
        ])
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.result_table.setAlternatingRowColors(True)
        self.result_table.setMinimumHeight(150)
        overview_layout.addWidget(self.result_table)
        
        # 墙面质量表格
        overview_layout.addWidget(QLabel("墙面质量详情"))
        self.wall_table = QTableWidget()
        self.wall_table.setColumnCount(5)
        self.wall_table.setHorizontalHeaderLabels([
            "墙面编号", "测点数", "垂直度(°)", "垂直度偏差(mm)", "平整度RMSE(mm)"
        ])
        self.wall_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.wall_table.setAlternatingRowColors(True)
        overview_layout.addWidget(self.wall_table)
        
        result_tabs.addTab(overview_tab, "📊 检测结果")
        
        # 详细报告标签页
        report_tab = QWidget()
        report_layout = QVBoxLayout(report_tab)
        
        self.report_text = QTextEdit()
        self.report_text.setFont(QFont("Courier New", 10))
        self.report_text.setReadOnly(True)
        self.report_text.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")
        
        report_layout.addWidget(self.report_text)
        
        result_tabs.addTab(report_tab, "📝 详细报告")
        
        # 数据信息标签页
        info_tab = QWidget()
        info_layout = QVBoxLayout(info_tab)
        
        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        
        info_layout.addWidget(self.info_text)
        
        result_tabs.addTab(info_tab, "ℹ️ 数据信息")
        
        main_layout.addWidget(result_tabs)
        
        # 状态栏
        self.statusBar().showMessage("就绪 - 请选择IFC和BIM文件开始分析")
    
    def create_menu(self):
        """创建菜单栏"""
        menubar = self.menuBar()
        
        # 文件菜单
        file_menu = menubar.addMenu("文件")
        
        open_ifc_action = QAction("打开IFC文件", self)
        open_ifc_action.triggered.connect(self.select_ifc)
        file_menu.addAction(open_ifc_action)
        
        open_las_action = QAction("打开LAS文件", self)
        open_las_action.triggered.connect(self.select_las)
        file_menu.addAction(open_las_action)
        
        file_menu.addSeparator()
        
        export_action = QAction("导出报告", self)
        export_action.triggered.connect(self.export_report)
        file_menu.addAction(export_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # 帮助菜单
        help_menu = menubar.addMenu("帮助")
        
        about_action = QAction("关于", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    def select_ifc(self):
        """选择IFC文件"""
        try:
            file_path, _ = QFileDialog.getOpenFileName(
                self, "选择BIM模型文件", "",
                "IFC文件 (*.ifc);;所有文件 (*.*)"
            )
            
            if file_path:
                self.ifc_path = file_path
                self.ifc_label.setText(Path(file_path).name)
                self.ifc_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
                self.check_ready()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"选择文件时出错: {e}\n{traceback.format_exc()}")
    
    def select_las(self):
        """选择LAS文件"""
        try:
            file_path, _ = QFileDialog.getOpenFileName(
                self, "选择点云文件", "",
                "LAS文件 (*.las *.laz);;所有文件 (*.*)"
            )
            
            if file_path:
                self.las_path = file_path
                self.las_label.setText(Path(file_path).name)
                self.las_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
                self.check_ready()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"选择文件时出错: {e}\n{traceback.format_exc()}")
    
    def check_ready(self):
        """检查是否可以开始分析"""
        ready = bool(self.ifc_path and self.las_path)
        self.btn_analyze.setEnabled(ready)
        if ready:
            self.status_label.setText("✅ 已选择文件，可以开始分析")
            self.statusBar().showMessage("准备就绪 - 点击开始分析")
    
    def start_analysis(self):
        """开始分析"""
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # 无限进度条
        self.btn_analyze.setEnabled(False)
        self.status_label.setText("正在分析...")
        self.statusBar().showMessage("分析进行中...")
        
        # 获取参数
        params = {
            'threshold': self.threshold_spin.value() / 1000,  # mm转m
            'max_planes': self.max_planes_spin.value()
        }
        
        # 启动后台线程
        self.worker = AnalysisWorker(self.ifc_path, self.las_path, params)
        self.worker.progress.connect(self.on_progress)
        self.worker.finished.connect(self.on_finished)
        self.worker.error.connect(self.on_error)
        self.worker.start()
    
    def on_progress(self, msg):
        """更新进度"""
        self.status_label.setText(msg)
        self.statusBar().showMessage(msg)
    
    def on_finished(self, result):
        """分析完成"""
        self.analysis_result = result
        self.progress_bar.setVisible(False)
        self.btn_analyze.setEnabled(True)
        self.btn_export.setEnabled(True)
        self.status_label.setText("✅ 分析完成")
        self.statusBar().showMessage("分析完成 - 查看检测结果")
        
        # 显示结果
        self.display_results(result)
    
    def on_error(self, error_msg):
        """分析出错"""
        self.progress_bar.setVisible(False)
        self.btn_analyze.setEnabled(True)
        self.status_label.setText(f"❌ 错误: {error_msg}")
        self.statusBar().showMessage(f"分析失败: {error_msg}")
        
        QMessageBox.critical(self, "分析错误", error_msg)
    
    def display_results(self, result):
        """显示分析结果"""
        # 更新概览表格
        self.result_table.setRowCount(0)
        
        room = result['room_dims']
        
        # 楼层净高
        if '楼层净高' in room:
            h = room['楼层净高']
            row = self.result_table.rowCount()
            self.result_table.insertRow(row)
            self.result_table.setItem(row, 0, QTableWidgetItem("楼层净高"))
            self.result_table.setItem(row, 1, QTableWidgetItem(f"{h['设计值_m']:.2f}m"))
            
            if h['实测值_m'] is not None:
                self.result_table.setItem(row, 2, QTableWidgetItem(f"{h['实测值_m']:.2f}m"))
                self.result_table.setItem(row, 3, QTableWidgetItem(f"{h['偏差_mm']:.1f}mm"))
            else:
                self.result_table.setItem(row, 2, QTableWidgetItem("无法测量"))
                self.result_table.setItem(row, 3, QTableWidgetItem(h.get('备注', '-') if h.get('备注') else '-'))
            
            status_item = QTableWidgetItem("合格" if h['合格'] else "不合格")
            status_item.setBackground(QColor("#90EE90" if h['合格'] else "#FFB6C1"))
            self.result_table.setItem(row, 4, status_item)
        
        # 房间尺寸
        if '房间尺寸' in room:
            d = room['房间尺寸']
            # 开间
            row = self.result_table.rowCount()
            self.result_table.insertRow(row)
            self.result_table.setItem(row, 0, QTableWidgetItem("开间"))
            self.result_table.setItem(row, 1, QTableWidgetItem(f"{d['开间设计_m']:.2f}m"))
            
            if d['开间实测_m'] is not None:
                self.result_table.setItem(row, 2, QTableWidgetItem(f"{d['开间实测_m']:.2f}m"))
                self.result_table.setItem(row, 3, QTableWidgetItem(f"{d['开间偏差_mm']:.1f}mm"))
            else:
                self.result_table.setItem(row, 2, QTableWidgetItem("无法测量"))
                self.result_table.setItem(row, 3, QTableWidgetItem("-"))
            
            status_item = QTableWidgetItem("合格" if d['合格'] else "不合格")
            status_item.setBackground(QColor("#90EE90" if d['合格'] else "#FFB6C1"))
            self.result_table.setItem(row, 4, status_item)
            
            # 进深
            row = self.result_table.rowCount()
            self.result_table.insertRow(row)
            self.result_table.setItem(row, 0, QTableWidgetItem("进深"))
            self.result_table.setItem(row, 1, QTableWidgetItem(f"{d['进深设计_m']:.2f}m"))
            
            if d['进深实测_m'] is not None:
                self.result_table.setItem(row, 2, QTableWidgetItem(f"{d['进深实测_m']:.2f}m"))
                self.result_table.setItem(row, 3, QTableWidgetItem(f"{d['进深偏差_mm']:.1f}mm"))
            else:
                self.result_table.setItem(row, 2, QTableWidgetItem("无法测量"))
                self.result_table.setItem(row, 3, QTableWidgetItem("-"))
            
            status_item = QTableWidgetItem("合格" if d['合格'] else "不合格")
            status_item.setBackground(QColor("#90EE90" if d['合格'] else "#FFB6C1"))
            self.result_table.setItem(row, 4, status_item)
        
        # 更新墙面表格
        self.wall_table.setRowCount(0)
        for wq in result['wall_quality']:
            row = self.wall_table.rowCount()
            self.wall_table.insertRow(row)
            self.wall_table.setItem(row, 0, QTableWidgetItem(f"墙面#{wq['墙面编号']}"))
            self.wall_table.setItem(row, 1, QTableWidgetItem(f"{wq['测点数']:,}"))
            
            v_item = QTableWidgetItem(f"{wq['垂直度角度_deg']:.2f}°")
            v_item.setBackground(QColor("#90EE90" if wq['垂直度合格'] else "#FFB6C1"))
            self.wall_table.setItem(row, 2, v_item)
            
            vd_item = QTableWidgetItem(f"{wq['垂直度偏差_mm']:.1f}")
            vd_item.setBackground(QColor("#90EE90" if wq['垂直度合格'] else "#FFB6C1"))
            self.wall_table.setItem(row, 3, vd_item)
            
            f_item = QTableWidgetItem(f"{wq['平整度RMSE_mm']:.1f}")
            f_item.setBackground(QColor("#90EE90" if wq['平整度合格'] else "#FFB6C1"))
            self.wall_table.setItem(row, 4, f_item)
        
        # 显示详细报告
        self.report_text.setText(result['report'])
        
        # 显示数据信息
        info = f"""=== BIM模型信息 ===
墙体数量: {len(result['bim_info']['walls'])}
设计楼层高度: {result['bim_info']['floor_height']:.2f}m

=== 点云数据信息 ===
点数: {result['las_info']['n_points']:,}
范围 X: [{result['las_info']['bbox']['min'][0]:.2f}, {result['las_info']['bbox']['max'][0]:.2f}]m
范围 Y: [{result['las_info']['bbox']['min'][1]:.2f}, {result['las_info']['bbox']['max'][1]:.2f}]m
范围 Z: [{result['las_info']['bbox']['min'][2]:.2f}, {result['las_info']['bbox']['max'][2]:.2f}]m

=== 检测到的平面 ===
地面: {len([p for p in result['planes'] if p['type']=='floor'])} 个
天花板: {len([p for p in result['planes'] if p['type']=='ceiling'])} 个
墙面: {len([p for p in result['planes'] if p['type']=='wall'])} 个
"""
        self.info_text.setText(info)
    
    def export_report(self):
        """导出报告"""
        if not self.analysis_result:
            return
        
        # 选择保存格式
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存报告", f"施工质量检测报告_{datetime.now().strftime('%Y%m%d')}",
            "Markdown文件 (*.md);;文本文件 (*.txt);;所有文件 (*.*)"
        )
        
        if file_path:
            try:
                # 根据文件扩展名选择格式
                if file_path.endswith('.md'):
                    # 生成 Markdown 格式报告
                    from core.quality_analyzer import QualityAnalyzer
                    analyzer = QualityAnalyzer(self.ifc_path, self.las_path)
                    analyzer.load_data()
                    analyzer.detect_planes()
                    analyzer.measure_room()
                    analyzer.analyze_walls()
                    report_content = analyzer.generate_markdown_report()
                else:
                    # 默认使用 txt 格式
                    report_content = self.analysis_result['report']
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(report_content)
                
                # 同时生成另一种格式的报告
                base_path = Path(file_path).stem
                parent_dir = Path(file_path).parent
                
                if file_path.endswith('.md'):
                    # 同时保存 txt
                    txt_path = parent_dir / f"{base_path}.txt"
                    with open(txt_path, 'w', encoding='utf-8') as f:
                        f.write(self.analysis_result['report'])
                    QMessageBox.information(self, "导出成功", 
                        f"报告已保存:\n\n📄 Markdown: {file_path}\n📄 文本: {txt_path}")
                else:
                    # 同时保存 md
                    md_path = parent_dir / f"{base_path}.md"
                    from core.quality_analyzer import QualityAnalyzer
                    analyzer = QualityAnalyzer(self.ifc_path, self.las_path)
                    analyzer.load_data()
                    analyzer.detect_planes()
                    analyzer.measure_room()
                    analyzer.analyze_walls()
                    md_content = analyzer.generate_markdown_report()
                    with open(md_path, 'w', encoding='utf-8') as f:
                        f.write(md_content)
                    QMessageBox.information(self, "导出成功", 
                        f"报告已保存:\n\n📄 文本: {file_path}\n📄 Markdown: {md_path}")
            except Exception as e:
                QMessageBox.critical(self, "导出失败", f"保存报告时出错: {e}")
    
    def show_about(self):
        """显示关于对话框"""
        QMessageBox.about(self, "关于",
            """BIM-点云施工质量检测系统 v1.0

功能:
- IFC模型解析
- LAS点云读取
- 楼层净高检测
- 房间尺寸检测
- 墙面垂直度/平整度检测
- 自动报告生成

技术: Python + PyQt5 + NumPy + laspy

© 2026 施工质量检测系统""")


def main():
    if not HAS_PYQT:
        print("请先安装PyQt5: pip install PyQt5")
        print("或使用tkinter版本: python main_tk.py")
        return
    
    try:
        # 导入核心模块
        sys.path.insert(0, str(Path(__file__).parent))
        from core.quality_analyzer import QualityAnalyzer
        print("核心模块导入成功")
    except Exception as e:
        print(f"导入核心模块失败: {e}")
        print(traceback.format_exc())
        return
    
    try:
        app = QApplication(sys.argv)
        app.setStyle('Fusion')
        
        window = MainWindow()
        window.show()
        
        sys.exit(app.exec_())
    except Exception as e:
        print(f"程序启动失败: {e}")
        print(traceback.format_exc())


if __name__ == "__main__":
    main()