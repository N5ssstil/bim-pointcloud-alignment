#!/usr/bin/env python3
"""
BIM-点云施工质量检测系统 - 主窗口
PyQt5桌面应用程序
"""

import sys
import os
import numpy as np
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFileDialog, QGroupBox, QTextEdit,
    QProgressBar, QTabWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QSplitter, QFrame
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QColor

# 导入核心分析模块
sys.path.insert(0, str(Path(__file__).parent))
from core.quality_analyzer import QualityAnalyzer

class AnalysisWorker(QThread):
    """后台分析线程"""
    progress = pyqtSignal(str)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    
    def __init__(self, ifc_path, las_path):
        super().__init__()
        self.ifc_path = ifc_path
        self.las_path = las_path
    
    def run(self):
        try:
            self.progress.emit("正在解析BIM模型...")
            analyzer = QualityAnalyzer(self.ifc_path, self.las_path)
            
            self.progress.emit("正在读取点云数据...")
            analyzer.load_data()
            
            self.progress.emit("正在检测平面...")
            planes = analyzer.detect_planes()
            
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
    """主窗口"""
    
    def __init__(self):
        super().__init__()
        self.ifc_path = None
        self.las_path = None
        self.analysis_result = None
        
        self.init_ui()
    
    def init_ui(self):
        """初始化界面"""
        self.setWindowTitle("BIM-点云施工质量检测系统 v1.0")
        self.setGeometry(100, 100, 1200, 800)
        
        # 主布局
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # ===== 文件导入区域 =====
        import_group = QGroupBox("文件导入")
        import_layout = QHBoxLayout(import_group)
        
        # BIM文件
        self.ifc_label = QLabel("BIM文件: 未选择")
        self.ifc_label.setStyleSheet("color: gray;")
        btn_ifc = QPushButton("选择IFC文件")
        btn_ifc.clicked.connect(self.select_ifc)
        
        # 点云文件
        self.las_label = QLabel("点云文件: 未选择")
        self.las_label.setStyleSheet("color: gray;")
        btn_las = QPushButton("选择LAS文件")
        btn_las.clicked.connect(self.select_las)
        
        import_layout.addWidget(QLabel("BIM模型:"))
        import_layout.addWidget(self.ifc_label)
        import_layout.addWidget(btn_ifc)
        import_layout.addSpacing(20)
        import_layout.addWidget(QLabel("点云数据:"))
        import_layout.addWidget(self.las_label)
        import_layout.addWidget(btn_las)
        import_layout.addStretch()
        
        main_layout.addWidget(import_group)
        
        # ===== 分析控制区域 =====
        control_group = QGroupBox("分析控制")
        control_layout = QHBoxLayout(control_group)
        
        self.btn_analyze = QPushButton("开始分析")
        self.btn_analyze.setEnabled(False)
        self.btn_analyze.clicked.connect(self.start_analysis)
        self.btn_analyze.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-size: 14px;
                padding: 8px 20px;
                border-radius: 4px;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        
        self.btn_export = QPushButton("导出报告")
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(self.export_report)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        
        self.status_label = QLabel("请选择BIM和点云文件")
        
        control_layout.addWidget(self.btn_analyze)
        control_layout.addWidget(self.btn_export)
        control_layout.addWidget(self.progress_bar)
        control_layout.addWidget(self.status_label)
        control_layout.addStretch()
        
        main_layout.addWidget(control_group)
        
        # ===== 结果显示区域 =====
        result_tabs = QTabWidget()
        
        # 概览标签页
        overview_tab = QWidget()
        overview_layout = QVBoxLayout(overview_tab)
        
        # 检测结果表格
        self.result_table = QTableWidget()
        self.result_table.setColumnCount(5)
        self.result_table.setHorizontalHeaderLabels([
            "检测项目", "设计值", "实测值", "偏差", "评定"
        ])
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.result_table.setAlternatingRowColors(True)
        
        overview_layout.addWidget(QLabel("<b>检测结果概览</b>"))
        overview_layout.addWidget(self.result_table)
        
        # 墙面质量表格
        self.wall_table = QTableWidget()
        self.wall_table.setColumnCount(5)
        self.wall_table.setHorizontalHeaderLabels([
            "墙面编号", "测点数", "垂直度(°)", "垂直度偏差(mm)", "平整度RMSE(mm)"
        ])
        self.wall_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        
        overview_layout.addWidget(QLabel("<b>墙面质量详情</b>"))
        overview_layout.addWidget(self.wall_table)
        
        result_tabs.addTab(overview_tab, "检测结果")
        
        # 详细报告标签页
        report_tab = QWidget()
        report_layout = QVBoxLayout(report_tab)
        
        self.report_text = QTextEdit()
        self.report_text.setFont(QFont("Courier", 10))
        self.report_text.setReadOnly(True)
        
        report_layout.addWidget(self.report_text)
        
        result_tabs.addTab(report_tab, "详细报告")
        
        # 数据信息标签页
        info_tab = QWidget()
        info_layout = QVBoxLayout(info_tab)
        
        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        
        info_layout.addWidget(self.info_text)
        
        result_tabs.addTab(info_tab, "数据信息")
        
        main_layout.addWidget(result_tabs)
        
        # 状态栏
        self.statusBar().showMessage("就绪")
    
    def select_ifc(self):
        """选择IFC文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择BIM模型文件", "",
            "IFC文件 (*.ifc);;所有文件 (*.*)"
        )
        
        if file_path:
            self.ifc_path = file_path
            self.ifc_label.setText(f"BIM文件: {Path(file_path).name}")
            self.ifc_label.setStyleSheet("color: green;")
            self.check_ready()
    
    def select_las(self):
        """选择LAS文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择点云文件", "",
            "LAS文件 (*.las *.laz);;所有文件 (*.*)"
        )
        
        if file_path:
            self.las_path = file_path
            self.las_label.setText(f"点云文件: {Path(file_path).name}")
            self.las_label.setStyleSheet("color: green;")
            self.check_ready()
    
    def check_ready(self):
        """检查是否可以开始分析"""
        ready = self.ifc_path and self.las_path
        self.btn_analyze.setEnabled(ready)
        if ready:
            self.status_label.setText("已选择文件，可以开始分析")
    
    def start_analysis(self):
        """开始分析"""
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # 无限进度条
        self.btn_analyze.setEnabled(False)
        self.status_label.setText("正在分析...")
        self.statusBar().showMessage("分析进行中...")
        
        # 启动后台线程
        self.worker = AnalysisWorker(self.ifc_path, self.las_path)
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
        self.status_label.setText("分析完成")
        self.statusBar().showMessage("分析完成")
        
        # 显示结果
        self.display_results(result)
    
    def on_error(self, error_msg):
        """分析出错"""
        self.progress_bar.setVisible(False)
        self.btn_analyze.setEnabled(True)
        self.status_label.setText(f"错误: {error_msg}")
        self.statusBar().showMessage(f"错误: {error_msg}")
        
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
            self.result_table.setItem(row, 2, QTableWidgetItem(f"{h['实测值_m']:.2f}m"))
            self.result_table.setItem(row, 3, QTableWidgetItem(f"{h['偏差_mm']:.1f}mm"))
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
            self.result_table.setItem(row, 2, QTableWidgetItem(f"{d['开间实测_m']:.2f}m"))
            self.result_table.setItem(row, 3, QTableWidgetItem(f"{d['开间偏差_mm']:.1f}mm"))
            status_item = QTableWidgetItem("合格" if d['合格'] else "不合格")
            status_item.setBackground(QColor("#90EE90" if d['合格'] else "#FFB6C1"))
            self.result_table.setItem(row, 4, status_item)
            
            # 进深
            row = self.result_table.rowCount()
            self.result_table.insertRow(row)
            self.result_table.setItem(row, 0, QTableWidgetItem("进深"))
            self.result_table.setItem(row, 1, QTableWidgetItem(f"{d['进深设计_m']:.2f}m"))
            self.result_table.setItem(row, 2, QTableWidgetItem(f"{d['进深实测_m']:.2f}m"))
            self.result_table.setItem(row, 3, QTableWidgetItem(f"{d['进深偏差_mm']:.1f}mm"))
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
            
            v_item = QTableWidgetItem(f"{wq['垂直度角度_deg']:.2f}")
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
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存报告", "施工质量检测报告.txt",
            "文本文件 (*.txt);;PDF文件 (*.pdf)"
        )
        
        if file_path:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(self.analysis_result['report'])
            
            QMessageBox.information(self, "导出成功", f"报告已保存至:\n{file_path}")


def main():
    app = QApplication(sys.argv)
    
    # 设置应用样式
    app.setStyle('Fusion')
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()