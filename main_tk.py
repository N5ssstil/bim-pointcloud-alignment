#!/usr/bin/env python3
"""
BIM-点云施工质量检测系统 - Tkinter版本
使用Python内置GUI库，无需额外安装
"""

import sys
import os
import threading
import numpy as np
from pathlib import Path
from datetime import datetime

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

# 导入核心分析模块
sys.path.insert(0, str(Path(__file__).parent))
from core.quality_analyzer import QualityAnalyzer


class MainWindow:
    """主窗口 - Tkinter版本"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("BIM-点云施工质量检测系统 v1.0")
        self.root.geometry("1000x700")
        
        self.ifc_path = None
        self.las_path = None
        self.analysis_result = None
        
        self.create_widgets()
    
    def create_widgets(self):
        """创建界面组件"""
        # ===== 文件导入区域 =====
        import_frame = ttk.LabelFrame(self.root, text="文件导入", padding=10)
        import_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # BIM文件
        ttk.Label(import_frame, text="BIM模型:").grid(row=0, column=0, sticky=tk.W)
        self.ifc_label = ttk.Label(import_frame, text="未选择", foreground="gray")
        self.ifc_label.grid(row=0, column=1, sticky=tk.W, padx=5)
        ttk.Button(import_frame, text="选择IFC文件", command=self.select_ifc).grid(row=0, column=2)
        
        # 点云文件
        ttk.Label(import_frame, text="点云数据:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.las_label = ttk.Label(import_frame, text="未选择", foreground="gray")
        self.las_label.grid(row=1, column=1, sticky=tk.W, padx=5)
        ttk.Button(import_frame, text="选择LAS文件", command=self.select_las).grid(row=1, column=2)
        
        import_frame.columnconfigure(1, weight=1)
        
        # ===== 分析控制区域 =====
        control_frame = ttk.LabelFrame(self.root, text="分析控制", padding=10)
        control_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.analyze_btn = ttk.Button(control_frame, text="开始分析", command=self.start_analysis, state=tk.DISABLED)
        self.analyze_btn.pack(side=tk.LEFT, padx=5)
        
        self.export_btn = ttk.Button(control_frame, text="导出报告", command=self.export_report, state=tk.DISABLED)
        self.export_btn.pack(side=tk.LEFT, padx=5)
        
        self.status_label = ttk.Label(control_frame, text="请选择BIM和点云文件")
        self.status_label.pack(side=tk.LEFT, padx=20)
        
        # ===== 结果显示区域 =====
        result_frame = ttk.LabelFrame(self.root, text="检测结果", padding=10)
        result_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 创建Tab控件
        self.notebook = ttk.Notebook(result_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # 概览标签页
        overview_tab = ttk.Frame(self.notebook)
        self.notebook.add(overview_tab, text="检测结果")
        
        # 检测结果表格
        ttk.Label(overview_tab, text="检测结果概览", font=('Arial', 12, 'bold')).pack(anchor=tk.W)
        
        columns = ('检测项目', '设计值', '实测值', '偏差', '评定')
        self.result_table = ttk.Treeview(overview_tab, columns=columns, show='headings', height=6)
        
        for col in columns:
            self.result_table.heading(col, text=col)
            self.result_table.column(col, width=100)
        
        self.result_table.pack(fill=tk.X, pady=5)
        
        # 墙面质量表格
        ttk.Label(overview_tab, text="墙面质量详情", font=('Arial', 12, 'bold')).pack(anchor=tk.W)
        
        wall_columns = ('墙面编号', '测点数', '垂直度(°)', '垂直度偏差(mm)', '平整度RMSE(mm)')
        self.wall_table = ttk.Treeview(overview_tab, columns=wall_columns, show='headings', height=6)
        
        for col in wall_columns:
            self.wall_table.heading(col, text=col)
            self.wall_table.column(col, width=100)
        
        self.wall_table.pack(fill=tk.X, pady=5)
        
        # 详细报告标签页
        report_tab = ttk.Frame(self.notebook)
        self.notebook.add(report_tab, text="详细报告")
        
        self.report_text = ScrolledText(report_tab, wrap=tk.WORD, font=('Courier', 10))
        self.report_text.pack(fill=tk.BOTH, expand=True)
        
        # 数据信息标签页
        info_tab = ttk.Frame(self.notebook)
        self.notebook.add(info_tab, text="数据信息")
        
        self.info_text = ScrolledText(info_tab, wrap=tk.WORD)
        self.info_text.pack(fill=tk.BOTH, expand=True)
        
        # ===== 状态栏 =====
        self.status_bar = ttk.Label(self.root, text="就绪", relief=tk.SUNKEN)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
    
    def select_ifc(self):
        """选择IFC文件"""
        file_path = filedialog.askopenfilename(
            title="选择BIM模型文件",
            filetypes=[("IFC文件", "*.ifc"), ("所有文件", "*.*")]
        )
        
        if file_path:
            self.ifc_path = file_path
            self.ifc_label.config(text=Path(file_path).name, foreground="green")
            self.check_ready()
    
    def select_las(self):
        """选择LAS文件"""
        file_path = filedialog.askopenfilename(
            title="选择点云文件",
            filetypes=[("LAS文件", "*.las *.laz"), ("所有文件", "*.*")]
        )
        
        if file_path:
            self.las_path = file_path
            self.las_label.config(text=Path(file_path).name, foreground="green")
            self.check_ready()
    
    def check_ready(self):
        """检查是否可以开始分析"""
        ready = self.ifc_path and self.las_path
        if ready:
            self.analyze_btn.config(state=tk.NORMAL)
            self.status_label.config(text="已选择文件，可以开始分析")
    
    def start_analysis(self):
        """开始分析"""
        self.analyze_btn.config(state=tk.DISABLED)
        self.status_label.config(text="正在分析...")
        self.status_bar.config(text="分析进行中...")
        
        # 启动后台线程
        thread = threading.Thread(target=self._run_analysis)
        thread.start()
    
    def _run_analysis(self):
        """后台分析线程"""
        try:
            analyzer = QualityAnalyzer(self.ifc_path, self.las_path)
            
            self._update_status("正在解析BIM模型...")
            analyzer.load_data()
            
            self._update_status("正在检测平面...")
            planes = analyzer.detect_planes()
            
            self._update_status("正在分析质量...")
            room_dims = analyzer.measure_room()
            wall_quality = analyzer.analyze_walls()
            
            self._update_status("正在生成报告...")
            report = analyzer.generate_report()
            
            result = {
                'planes': planes,
                'room_dims': room_dims,
                'wall_quality': wall_quality,
                'report': report,
                'bim_info': analyzer.bim_info,
                'las_info': analyzer.las_info
            }
            
            self.analysis_result = result
            
            # 在主线程更新UI
            self.root.after(0, lambda: self._on_analysis_finished(result))
            
        except Exception as e:
            self.root.after(0, lambda: self._on_analysis_error(str(e)))
    
    def _update_status(self, msg):
        """更新状态"""
        self.root.after(0, lambda: self.status_label.config(text=msg))
        self.root.after(0, lambda: self.status_bar.config(text=msg))
    
    def _on_analysis_finished(self, result):
        """分析完成"""
        self.analyze_btn.config(state=tk.NORMAL)
        self.export_btn.config(state=tk.NORMAL)
        self.status_label.config(text="分析完成")
        self.status_bar.config(text="分析完成")
        
        self.display_results(result)
    
    def _on_analysis_error(self, error_msg):
        """分析出错"""
        self.analyze_btn.config(state=tk.NORMAL)
        self.status_label.config(text=f"错误: {error_msg}")
        self.status_bar.config(text=f"错误")
        
        messagebox.showerror("分析错误", error_msg)
    
    def display_results(self, result):
        """显示分析结果"""
        # 清空表格
        for row in self.result_table.get_children():
            self.result_table.delete(row)
        for row in self.wall_table.get_children():
            self.wall_table.delete(row)
        
        room = result['room_dims']
        
        # 楼层净高
        if '楼层净高' in room:
            h = room['楼层净高']
            status = "合格" if h['合格'] else "不合格"
            self.result_table.insert('', tk.END, values=(
                "楼层净高", f"{h['设计值_m']:.2f}m", f"{h['实测值_m']:.2f}m",
                f"{h['偏差_mm']:.1f}mm", status
            ))
        
        # 房间尺寸
        if '房间尺寸' in room:
            d = room['房间尺寸']
            status = "合格" if d['合格'] else "不合格"
            self.result_table.insert('', tk.END, values=(
                "开间", f"{d['开间设计_m']:.2f}m", f"{d['开间实测_m']:.2f}m",
                f"{d['开间偏差_mm']:.1f}mm", status
            ))
            self.result_table.insert('', tk.END, values=(
                "进深", f"{d['进深设计_m']:.2f}m", f"{d['进深实测_m']:.2f}m",
                f"{d['进深偏差_mm']:.1f}mm", status
            ))
        
        # 墙面质量
        for wq in result['wall_quality']:
            v_status = "✓" if wq['垂直度合格'] else "✗"
            f_status = "✓" if wq['平整度合格'] else "✗"
            self.wall_table.insert('', tk.END, values=(
                f"墙面#{wq['墙面编号']}",
                f"{wq['测点数']:,}",
                f"{wq['垂直度角度_deg']:.2f}° {v_status}",
                f"{wq['垂直度偏差_mm']:.1f}",
                f"{wq['平整度RMSE_mm']:.1f} {f_status}"
            ))
        
        # 详细报告
        self.report_text.delete('1.0', tk.END)
        self.report_text.insert('1.0', result['report'])
        
        # 数据信息
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
        self.info_text.delete('1.0', tk.END)
        self.info_text.insert('1.0', info)
    
    def export_report(self):
        """导出报告"""
        if not self.analysis_result:
            return
        
        file_path = filedialog.asksaveasfilename(
            title="保存报告",
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        
        if file_path:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(self.analysis_result['report'])
            
            messagebox.showinfo("导出成功", f"报告已保存至:\n{file_path}")
    
    def run(self):
        """运行应用"""
        self.root.mainloop()


def main():
    app = MainWindow()
    app.run()


if __name__ == "__main__":
    main()