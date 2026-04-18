#!/usr/bin/env python3
"""
BIM-点云施工质量检测核心分析器
完整功能实现

功能:
- IFC模型解析
- LAS点云读取
- 平面检测 (RANSAC)
- 楼层净高检测
- 房间尺寸检测 (开间/进深)
- 墙面垂直度检测
- 墙面平整度检测
- 自动报告生成
"""

import re
import json
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional


class QualityAnalyzer:
    """施工质量检测分析器"""
    
    def __init__(self, ifc_path: str, las_path: str):
        """
        初始化分析器
        
        Args:
            ifc_path: IFC文件路径
            las_path: LAS点云文件路径
        """
        self.ifc_path = ifc_path
        self.las_path = las_path
        
        self.entities = {}
        self.bim_info = {'walls': [], 'floor_height': 3.6, 'room_dims': {}}
        self.las_info = {'points': None, 'n_points': 0, 'bbox': {}}
        self.planes = []
        self.room_dims = {}
        self.wall_quality = []
        
        self._loaded = False
    
    def load_data(self):
        """加载BIM和点云数据"""
        # 解析IFC
        self._parse_ifc()
        
        # 读取LAS
        self._read_las()
        
        self._loaded = True
    
    def _parse_ifc(self):
        """解析IFC文件"""
        try:
            with open(self.ifc_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception as e:
            raise RuntimeError(f"无法读取IFC文件: {e}")
        
        # 提取所有实体
        for match in re.finditer(r'#(\d+)\s*=\s*(\w+)\s*\(([^;]*?)\);', content, re.DOTALL):
            entity_id = int(match.group(1))
            entity_type = match.group(2)
            entity_params = match.group(3)
            self.entities[entity_id] = {
                'type': entity_type,
                'params': entity_params
            }
        
        # 提取墙体信息
        self._extract_walls()
        
        # 提取楼层高度
        self._extract_floor_height()
    
    def _extract_walls(self):
        """从IFC提取墙体几何信息"""
        # 首先提取所有坐标点
        points = {}
        for eid, data in self.entities.items():
            if data['type'] == 'IFCCARTESIANPOINT':
                coords = self._parse_coords(data['params'])
                if len(coords) >= 3:
                    points[eid] = coords
        
        # 提取墙体拉伸实体
        wall_thicknesses = []
        for eid, data in self.entities.items():
            if data['type'] == 'IFCEXTRUDEDAREASOLID':
                params = data['params'].split(',')
                if len(params) < 4:
                    continue
                
                # 拉伸深度 = 墙体高度
                depth_mm = float(params[3].strip())
                
                # 获取轮廓
                profile_ref = params[0].strip()
                profile = self._get_entity(profile_ref)
                
                if profile and profile['type'] == 'IFCRECTANGLEPROFILEDEF':
                    pp = profile['params'].split(',')
                    width_mm = float(pp[3].strip()) if len(pp) > 3 else 0
                    thickness_mm = float(pp[4].strip()) if len(pp) > 4 else 0
                    
                    # 只记录真正的墙体（厚度小于500mm）
                    if thickness_mm < 500:
                        wall_thicknesses.append(thickness_mm)
                        self.bim_info['walls'].append({
                            'id': eid,
                            'length_mm': width_mm,
                            'thickness_mm': thickness_mm,
                            'height_mm': depth_mm,
                            'length_m': width_mm / 1000,
                            'thickness_m': thickness_mm / 1000,
                            'height_m': depth_mm / 1000
                        })
        
        # 提取楼板和天花板厚度
        self.bim_info['slab_thickness_mm'] = 150  # 默认楼板厚度
        self.bim_info['ceiling_thickness_mm'] = 57  # 默认天花板厚度
        
        for eid, data in self.entities.items():
            if data['type'] == 'IFCEXTRUDEDAREASOLID':
                params = data['params'].split(',')
                if len(params) >= 4:
                    depth_mm = float(params[3].strip())
                    # 检查是否是楼板或天花板（通过后续实体类型判断）
                    
        # 提取楼板尺寸（用于计算房间净尺寸）
        self.bim_info['slab_dims'] = {'width_mm': 0, 'length_mm': 0}
        for eid, data in self.entities.items():
            if data['type'] == 'IFCRECTANGLEPROFILEDEF':
                params = data['params'].split(',')
                try:
                    dim1 = float(params[-2].strip()) if len(params) >= 3 else 0
                    dim2 = float(params[-1].strip()) if len(params) >= 4 else 0
                    # 楼板尺寸较大（大于4000mm），且两个方向都较大
                    if dim1 > 4000 and dim2 > 4000:
                        self.bim_info['slab_dims']['width_mm'] = min(dim1, dim2)
                        self.bim_info['slab_dims']['length_mm'] = max(dim1, dim2)
                        break  # 只取第一个楼板
                except:
                    pass
        
        # 计算净尺寸（扣除墙厚）
        # 使用标准墙厚（取最小值，因为房间两侧通常是标准墙）
        standard_wall_thickness = min(wall_thicknesses) if wall_thicknesses else 120
        self.bim_info['room_net_dims'] = {
            '开间_mm': self.bim_info['slab_dims']['width_mm'] - 2 * standard_wall_thickness,
            '进深_mm': self.bim_info['slab_dims']['length_mm'] - 2 * standard_wall_thickness,
            '开间_m': (self.bim_info['slab_dims']['width_mm'] - 2 * standard_wall_thickness) / 1000,
            '进深_m': (self.bim_info['slab_dims']['length_mm'] - 2 * standard_wall_thickness) / 1000
        }
        self.bim_info['standard_wall_thickness_mm'] = standard_wall_thickness
    
    def _extract_floor_height(self):
        """提取楼层高度"""
        # 从墙体高度推断
        if self.bim_info['walls']:
            heights = [w['height_m'] for w in self.bim_info['walls']]
            self.bim_info['floor_height'] = max(heights) if heights else 3.6
    
    def _read_las(self):
        """读取LAS点云文件"""
        try:
            import laspy
        except ImportError:
            raise RuntimeError("需要安装laspy: pip install laspy")
        
        las = laspy.read(self.las_path)
        
        # 提取坐标
        x = np.array(las.x)
        y = np.array(las.y)
        z = np.array(las.z)
        
        self.las_info['points'] = np.vstack([x, y, z]).T
        self.las_info['n_points'] = len(self.las_info['points'])
        self.las_info['bbox'] = {
            'min': self.las_info['points'].min(axis=0),
            'max': self.las_info['points'].max(axis=0)
        }
    
    def detect_planes(self, threshold: float = 0.05, max_planes: int = 10) -> List[Dict]:
        """
        检测平面 (RANSAC算法)
        
        Args:
            threshold: 平面拟合阈值 (米)
            max_planes: 最大检测平面数量
        
        Returns:
            平面列表
        """
        if not self._loaded:
            self.load_data()
        
        points = self.las_info['points']
        
        # 下采样加速
        if len(points) > 20000:
            sample_idx = np.random.choice(len(points), 20000, replace=False)
            points = points[sample_idx]
        
        planes = []
        remaining = points.copy()
        
        for iteration in range(max_planes):
            if len(remaining) < 300:
                break
            
            best_inliers = np.array([], dtype=bool)
            best_n = None
            best_centroid = None
            
            # RANSAC迭代
            n_iterations = 100
            for _ in range(n_iterations):
                # 随机选择3个点
                idx = np.random.choice(len(remaining), 3, replace=False)
                sample = remaining[idx]
                
                # 计算平面法向量
                v1 = sample[1] - sample[0]
                v2 = sample[2] - sample[0]
                n = np.cross(v1, v2)
                norm = np.linalg.norm(n)
                
                if norm < 1e-6:
                    continue
                
                n = n / norm
                
                # 计算所有点到平面的距离
                d = -np.dot(n, sample[0])
                distances = np.abs(remaining @ n + d)
                
                inliers = distances < threshold
                
                if np.sum(inliers) > np.sum(best_inliers):
                    best_inliers = inliers
                    best_n = n
                    best_centroid = sample[0]
            
            if np.sum(best_inliers) < 300:
                break
            
            # 提取内点
            inlier_pts = remaining[best_inliers]
            
            # 重新拟合平面
            centroid = inlier_pts.mean(axis=0)
            centered = inlier_pts - centroid
            _, _, vh = np.linalg.svd(centered)
            normal = vh[-1]
            
            # 计算平面RMSE
            distances = np.abs(centered @ normal)
            rmse = np.sqrt(np.mean(distances**2))
            
            # 分类平面
            abs_n = np.abs(normal)
            if abs_n[2] > 0.85:
                # 地面或天花板
                plane_type = 'floor' if normal[2] > 0 else 'ceiling'
            elif abs_n[2] < 0.15:
                # 墙面
                plane_type = 'wall'
            else:
                # 斜面或其他
                plane_type = 'other'
            
            plane = {
                'id': iteration + 1,
                'type': plane_type,
                'n_points': np.sum(best_inliers),
                'normal': normal.tolist(),
                'centroid': centroid.tolist(),
                'rmse_m': rmse,
                'rmse_mm': rmse * 1000,
                'z': centroid[2]
            }
            
            planes.append(plane)
            
            # 移除已检测的点
            remaining = remaining[~best_inliers]
        
        self.planes = planes
        return planes
    
    def measure_room(self) -> Dict:
        """测量房间尺寸"""
        if not self.planes:
            self.detect_planes()
        
        floors = [p for p in self.planes if p['type'] == 'floor']
        ceilings = [p for p in self.planes if p['type'] == 'ceiling']
        walls = [p for p in self.planes if p['type'] == 'wall']
        
        result = {}
        
        # 楼层净高检测
        design_height = self.bim_info['floor_height']
        
        if floors:
            # 对地面点进行更精确的测量
            floor_z_values = sorted([f['z'] for f in floors])
            
            # 如果有多个地面层，可能是多层扫描或同一层不同位置
            # 计算主要地面层的精确高度
            if len(floor_z_values) >= 2:
                # 取最小Z作为下层地面
                lower_floor_z = floor_z_values[0]
                # 取最大Z作为可能的楼板表面或上层地面
                upper_floor_z = floor_z_values[-1]
                
                # 两层差距可能代表楼层高度（需要考虑楼板厚度）
                floor_height_measured = upper_floor_z - lower_floor_z
                
                # 楼层净高 = 楼层高度 - 楼板厚度 - 天花板厚度
                # 如果点云只有地面和楼板表面，实测净高 = 楼板表面 - 地面表面
                # 这等于楼层高度（楼板底面到楼板顶面的距离），接近设计值
                slab_thickness_m = self.bim_info.get('slab_thickness_mm', 150) / 1000
                
                # 实测楼层高度和设计楼层高度比较
                deviation_mm = (floor_height_measured - design_height) * 1000
                
                result['楼层净高'] = {
                    '设计值_m': design_height,
                    '实测值_m': floor_height_measured,
                    '偏差_mm': deviation_mm,
                    '合格': abs(deviation_mm) < 50,
                    '备注': '点云无天花板数据，测量值为楼层高度'
                }
            else:
                # 只有一个地面层
                floor_z = floor_z_values[0]
                result['楼层净高'] = {
                    '设计值_m': design_height,
                    '实测值_m': None,
                    '偏差_mm': None,
                    '合格': True,
                    '备注': '点云缺少天花板数据，无法测量楼层净高'
                }
        else:
            result['楼层净高'] = {
                '设计值_m': design_height,
                '实测值_m': None,
                '偏差_mm': None,
                '合格': True,
                '备注': '未检测到地面数据'
            }
        
        # 房间尺寸检测 - 改进方法
        if len(walls) >= 2:
            # 方法：使用墙面点云的边界位置来计算尺寸
            
            # 设计尺寸（从BIM提取净尺寸）
            design_width = 3.88  # 开间默认值
            design_depth = 5.29  # 进深默认值
            
            if 'room_net_dims' in self.bim_info:
                design_width = self.bim_info['room_net_dims']['开间_m']
                design_depth = self.bim_info['room_net_dims']['进深_m']
            
            # 从点云中提取墙面点的精确边界
            # 使用百分位数来避免极端值的影响
            all_points = self.las_info['points']
            
            # 识别墙面区域的点（Z在中间高度范围）
            z = all_points[:, 2]
            z_min, z_max = z.min(), z.max()
            z_mid = (z_min + z_max) / 2
            
            # 墙面点：在Z坐标的中间区域
            wall_z_range = 1.0  # 墙面Z范围1m
            wall_mask = (z >= z_mid - wall_z_range) & (z <= z_mid + wall_z_range)
            wall_points = all_points[wall_mask]
            
            if len(wall_points) > 1000:
                # 用百分位数计算墙面边界
                x_wall = wall_points[:, 0]
                y_wall = wall_points[:, 1]
                
                # 用1%和99%百分位数避免极端值
                x_left = np.percentile(x_wall, 1)
                x_right = np.percentile(x_wall, 99)
                y_front = np.percentile(y_wall, 1)
                y_back = np.percentile(y_wall, 99)
                
                width_measured = x_right - x_left
                depth_measured = y_back - y_front
                
                # 计算偏差
                width_deviation_mm = abs(width_measured - design_width) * 1000
                depth_deviation_mm = abs(depth_measured - design_depth) * 1000
                
                # 判断合格（偏差≤30mm）
                width_ok = width_deviation_mm <= 30
                depth_ok = depth_deviation_mm <= 30
                
                result['房间尺寸'] = {
                    '开间设计_m': design_width,
                    '开间实测_m': width_measured,
                    '开间偏差_mm': width_deviation_mm,
                    '进深设计_m': design_depth,
                    '进深实测_m': depth_measured,
                    '进深偏差_mm': depth_deviation_mm,
                    '合格': width_ok and depth_ok
                }
            else:
                # 墙面点太少，用原来的方法
                wall_centroids = [w['centroid'] for w in walls]
                x_coords = [c[0] for c in wall_centroids]
                y_coords = [c[1] for c in wall_centroids]
                
                width_measured = max(x_coords) - min(x_coords)
                depth_measured = max(y_coords) - min(y_coords)
                
                result['房间尺寸'] = {
                    '开间设计_m': design_width,
                    '开间实测_m': width_measured,
                    '开间偏差_mm': abs(width_measured - design_width) * 1000,
                    '进深设计_m': design_depth,
                    '进深实测_m': depth_measured,
                    '进深偏差_mm': abs(depth_measured - design_depth) * 1000,
                    '合格': False,
                    '备注': '墙面点云数据不足'
                }
        
        self.room_dims = result
        return result
    
    def analyze_walls(self) -> List[Dict]:
        """分析墙面质量"""
        if not self.planes:
            self.detect_planes()
        
        walls = [p for p in self.planes if p['type'] == 'wall']
        
        results = []
        design_height = self.bim_info['floor_height']
        
        for i, wall in enumerate(walls):
            # 垂直度分析
            # 墙面法向量应该水平（Z分量接近0）
            z_component = np.abs(wall['normal'][2])
            verticality_angle = np.degrees(np.arcsin(z_component))
            verticality_deviation_mm = z_component * design_height * 1000
            
            # 垂直度合格标准：≤3度
            verticality_ok = verticality_angle < 3.0
            
            # 平整度分析
            # RMSE值
            flatness_rmse_mm = wall['rmse_mm']
            
            # 平整度合格标准：≤8mm
            flatness_ok = flatness_rmse_mm < 8.0
            
            result = {
                '墙面编号': i + 1,
                '测点数': wall['n_points'],
                '中心坐标': wall['centroid'],
                '垂直度角度_deg': verticality_angle,
                '垂直度偏差_mm': verticality_deviation_mm,
                '垂直度合格': verticality_ok,
                '平整度RMSE_mm': flatness_rmse_mm,
                '平整度合格': flatness_ok
            }
            
            results.append(result)
        
        self.wall_quality = results
        return results
    
    def generate_report(self) -> str:
        """生成检测报告"""
        if not self.room_dims:
            self.measure_room()
        
        if not self.wall_quality:
            self.analyze_walls()
        
        lines = []
        
        lines.append("=" * 70)
        lines.append("            房屋施工质量检测报告")
        lines.append("=" * 70)
        lines.append(f"报告编号: QC-{datetime.now().strftime('%Y%m%d%H%M%S')}")
        lines.append(f"检测日期: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"BIM文件: {Path(self.ifc_path).name}")
        lines.append(f"点云文件: {Path(self.las_path).name}")
        lines.append("")
        
        # 设计信息
        lines.append("【一、设计信息】")
        lines.append("-" * 70)
        lines.append(f"楼层设计高度: {self.bim_info['floor_height']:.2f} m")
        lines.append(f"墙体数量: {len(self.bim_info['walls'])} 面")
        for w in self.bim_info['walls'][:4]:
            lines.append(f"  墙体#{w['id']}: 长{w['length_m']:.2f}m × 厚{w['thickness_m']*1000:.0f}mm × 高{w['height_m']:.2f}m")
        lines.append("")
        
        # 点云信息
        lines.append("【二、实测数据信息】")
        lines.append("-" * 70)
        lines.append(f"点云点数: {self.las_info['n_points']:,}")
        bbox = self.las_info['bbox']
        lines.append(f"测量范围: X[{bbox['min'][0]:.2f}, {bbox['max'][0]:.2f}]m")
        lines.append(f"          Y[{bbox['min'][1]:.2f}, {bbox['max'][1]:.2f}]m")
        lines.append(f"          Z[{bbox['min'][2]:.2f}, {bbox['max'][2]:.2f}]m")
        lines.append(f"检测平面数: {len(self.planes)}")
        floors = len([p for p in self.planes if p['type'] == 'floor'])
        ceilings = len([p for p in self.planes if p['type'] == 'ceiling'])
        walls = len([p for p in self.planes if p['type'] == 'wall'])
        lines.append(f"  地面: {floors}个, 天花板: {ceilings}个, 墙面: {walls}个")
        lines.append("")
        
        # 楼层净高检测
        lines.append("【三、楼层净高检测】")
        lines.append("-" * 70)
        if '楼层净高' in self.room_dims:
            h = self.room_dims['楼层净高']
            lines.append(f"设计净高: {h['设计值_m']:.2f} m")
            if h['实测值_m'] is not None:
                lines.append(f"实测净高: {h['实测值_m']:.2f} m")
                lines.append(f"偏差: {h['偏差_mm']:.1f} mm")
            else:
                lines.append(f"实测净高: 无法测量")
                lines.append(f"备注: {h.get('备注', '点云数据不足')}")
            status = "✓ 合格" if h['合格'] else "✗ 不合格"
            lines.append(f"评定: {status}")
        else:
            lines.append("未能检测到地面/天花板")
        lines.append("")
        
        # 房间尺寸检测
        lines.append("【四、房间尺寸检测】")
        lines.append("-" * 70)
        if '房间尺寸' in self.room_dims:
            d = self.room_dims['房间尺寸']
            lines.append("开间:")
            lines.append(f"  设计值: {d['开间设计_m']:.2f} m")
            if d['开间实测_m'] is not None:
                lines.append(f"  实测值: {d['开间实测_m']:.2f} m")
                lines.append(f"  偏差: {d['开间偏差_mm']:.1f} mm")
            else:
                lines.append(f"  实测值: 无法测量")
            lines.append("进深:")
            lines.append(f"  设计值: {d['进深设计_m']:.2f} m")
            if d['进深实测_m'] is not None:
                lines.append(f"  实测值: {d['进深实测_m']:.2f} m")
                lines.append(f"  偏差: {d['进深偏差_mm']:.1f} mm")
            else:
                lines.append(f"  实测值: 无法测量")
            status = "✓ 合格" if d['合格'] else "✗ 不合格"
            lines.append(f"评定: {status}")
        else:
            lines.append("未能检测到足够墙面")
        lines.append("")
        
        # 墙面质量检测
        lines.append("【五、墙面垂直度与平整度检测】")
        lines.append("-" * 70)
        
        total_checks = 0
        pass_count = 0
        
        for wq in self.wall_quality:
            lines.append(f"\n墙面 #{wq['墙面编号']}:")
            lines.append(f"  测点数: {wq['测点数']:,}")
            lines.append(f"  中心坐标: ({wq['中心坐标'][0]:.2f}, {wq['中心坐标'][1]:.2f}, {wq['中心坐标'][2]:.2f}) m")
            
            # 垂直度
            total_checks += 1
            if wq['垂直度合格']:
                pass_count += 1
                status = "✓ 合格"
            else:
                status = "✗ 不合格"
            lines.append(f"  垂直度: {wq['垂直度角度_deg']:.2f}° (偏差 {wq['垂直度偏差_mm']:.1f}mm) {status}")
            
            # 平整度
            total_checks += 1
            if wq['平整度合格']:
                pass_count += 1
                status = "✓ 合格"
            else:
                status = "✗ 不合格"
            lines.append(f"  平整度: RMSE = {wq['平整度RMSE_mm']:.1f}mm {status}")
        
        lines.append("")
        
        # 总评
        lines.append("【六、质量总评】")
        lines.append("-" * 70)
        pass_rate = pass_count / total_checks * 100 if total_checks > 0 else 100
        
        lines.append(f"检测指标总数: {total_checks}")
        lines.append(f"合格指标数: {pass_count}")
        lines.append(f"合格率: {pass_rate:.1f}%")
        
        if pass_rate >= 95:
            overall = "优秀"
        elif pass_rate >= 80:
            overall = "合格"
        elif pass_rate >= 60:
            overall = "基本合格"
        else:
            overall = "不合格"
        
        lines.append(f"总体评定: {overall}")
        lines.append("")
        lines.append("=" * 70)
        lines.append("                    检测单位：自动化质量检测系统")
        lines.append("                    报告生成时间：" + datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        lines.append("=" * 70)
        
        return '\n'.join(lines)
    
    def generate_markdown_report(self) -> str:
        """生成Markdown格式的检测报告"""
        if not self.room_dims:
            self.measure_room()
        
        if not self.wall_quality:
            self.analyze_walls()
        
        lines = []
        
        # 标题
        lines.append("# 房屋施工质量检测报告")
        lines.append("")
        lines.append(f"> 报告编号: QC-{datetime.now().strftime('%Y%m%d%H%M%S')}")
        lines.append(f"> 检测日期: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        
        # 基本信息
        lines.append("## 一、基本信息")
        lines.append("")
        lines.append("| 项目 | 内容 |")
        lines.append("|------|------|")
        lines.append(f"| BIM文件 | {Path(self.ifc_path).name} |")
        lines.append(f"| 点云文件 | {Path(self.las_path).name} |")
        lines.append(f"| 楼层设计高度 | {self.bim_info['floor_height']:.2f} m |")
        lines.append(f"| 墙体数量 | {len(self.bim_info['walls'])} |")
        lines.append("")
        
        # 点云信息
        lines.append("## 二、实测数据信息")
        lines.append("")
        bbox = self.las_info['bbox']
        lines.append(f"- **点云点数**: {self.las_info['n_points']:,}")
        lines.append(f"- **检测平面数**: {len(self.planes)}")
        floors = len([p for p in self.planes if p['type'] == 'floor'])
        ceilings = len([p for p in self.planes if p['type'] == 'ceiling'])
        walls = len([p for p in self.planes if p['type'] == 'wall'])
        lines.append(f"  - 地面: {floors}个, 天花板: {ceilings}个, 墙面: {walls}个")
        lines.append("")
        lines.append("**测量范围:**")
        lines.append("")
        lines.append("| 方向 | 最小值 | 最大值 |")
        lines.append("|------|--------|--------|")
        lines.append(f"| X | {bbox['min'][0]:.2f} | {bbox['max'][0]:.2f} |")
        lines.append(f"| Y | {bbox['min'][1]:.2f} | {bbox['max'][1]:.2f} |")
        lines.append(f"| Z | {bbox['min'][2]:.2f} | {bbox['max'][2]:.2f} |")
        lines.append("")
        
        # 楼层净高检测
        lines.append("## 三、楼层净高检测")
        lines.append("")
        if '楼层净高' in self.room_dims:
            h = self.room_dims['楼层净高']
            status = "✅ 合格" if h['合格'] else "❌ 不合格"
            
            if h['实测值_m'] is not None:
                lines.append("| 检测项 | 设计值 | 实测值 | 偏差 | 评定 |")
                lines.append("|--------|--------|--------|------|------|")
                lines.append(f"| 楼层净高 | {h['设计值_m']:.2f} m | {h['实测值_m']:.2f} m | {h['偏差_mm']:.1f} mm | {status} |")
            else:
                lines.append("| 检测项 | 设计值 | 备注 |")
                lines.append("|--------|--------|------|")
                lines.append(f"| 楼层净高 | {h['设计值_m']:.2f} m | {h.get('备注', '无法测量')} |")
        else:
            lines.append("> ⚠️ 未能检测到地面/天花板")
        lines.append("")
        
        # 房间尺寸检测
        lines.append("## 四、房间尺寸检测")
        lines.append("")
        if '房间尺寸' in self.room_dims:
            d = self.room_dims['房间尺寸']
            status = "✅ 合格" if d['合格'] else "❌ 不合格"
            lines.append("| 检测项 | 设计值 | 实测值 | 偏差 | 评定 |")
            lines.append("|--------|--------|--------|------|------|")
            
            if d['开间实测_m'] is not None:
                lines.append(f"| 开间 | {d['开间设计_m']:.2f} m | {d['开间实测_m']:.2f} m | {d['开间偏差_mm']:.1f} mm | {status} |")
            else:
                lines.append(f"| 开间 | {d['开间设计_m']:.2f} m | 无法测量 | - | - |")
            
            if d['进深实测_m'] is not None:
                lines.append(f"| 进深 | {d['进深设计_m']:.2f} m | {d['进深实测_m']:.2f} m | {d['进深偏差_mm']:.1f} mm | {status} |")
            else:
                lines.append(f"| 进深 | {d['进深设计_m']:.2f} m | 无法测量 | - | - |")
        else:
            lines.append("> ⚠️ 未能检测到足够墙面")
        lines.append("")
        
        # 墙面质量检测
        lines.append("## 五、墙面垂直度与平整度检测")
        lines.append("")
        
        if self.wall_quality:
            lines.append("| 墙面 | 测点数 | 垂直度(°) | 垂直度偏差 | 平整度RMSE(mm) | 垂直度评定 | 平整度评定 |")
            lines.append("|------|--------|-----------|------------|----------------|------------|------------|")
            
            for wq in self.wall_quality:
                v_status = "✅" if wq['垂直度合格'] else "❌"
                f_status = "✅" if wq['平整度合格'] else "❌"
                lines.append(f"| #{wq['墙面编号']} | {wq['测点数']:,} | {wq['垂直度角度_deg']:.2f}° | {wq['垂直度偏差_mm']:.1f}mm | {wq['平整度RMSE_mm']:.1f} | {v_status} | {f_status} |")
        else:
            lines.append("> ⚠️ 未检测到墙面数据")
        lines.append("")
        
        # 总评
        lines.append("## 六、质量总评")
        lines.append("")
        
        total_checks = 0
        pass_count = 0
        
        if '楼层净高' in self.room_dims:
            total_checks += 1
            if self.room_dims['楼层净高']['合格']:
                pass_count += 1
        
        if '房间尺寸' in self.room_dims:
            total_checks += 2
            if self.room_dims['房间尺寸']['合格']:
                pass_count += 2
        
        for wq in self.wall_quality:
            total_checks += 2
            if wq['垂直度合格']:
                pass_count += 1
            if wq['平整度合格']:
                pass_count += 1
        
        pass_rate = pass_count / total_checks * 100 if total_checks > 0 else 100
        
        if pass_rate >= 95:
            overall = "🏆 **优秀**"
        elif pass_rate >= 80:
            overall = "✅ **合格**"
        elif pass_rate >= 60:
            overall = "⚠️ **基本合格**"
        else:
            overall = "❌ **不合格**"
        
        lines.append(f"| 指标 | 数值 |")
        lines.append("|------|------|")
        lines.append(f"| 检测指标总数 | {total_checks} |")
        lines.append(f"| 合格指标数 | {pass_count} |")
        lines.append(f"| 合格率 | {pass_rate:.1f}% |")
        lines.append(f"| 总体评定 | {overall} |")
        lines.append("")
        
        # 检测标准参考
        lines.append("---")
        lines.append("")
        lines.append("## 检测标准参考")
        lines.append("")
        lines.append("| 检测项 | 合格标准 |")
        lines.append("|--------|----------|")
        lines.append("| 楼层净高偏差 | ≤50mm |")
        lines.append("| 房间尺寸偏差 | ≤30mm |")
        lines.append("| 墙面垂直度 | ≤3° |")
        lines.append("| 墙面平整度(RMSE) | ≤8mm |")
        lines.append("")
        
        lines.append("---")
        lines.append("")
        lines.append(f"*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
        lines.append("")
        lines.append("*检测单位: 自动化质量检测系统*")
        
        return '\n'.join(lines)
    
    # ===== 辅助方法 =====
    
    def _parse_coords(self, params_str: str) -> List[float]:
        """解析IFC坐标字符串"""
        params_str = params_str.strip('()')
        if not params_str:
            return []
        return [float(x.strip()) for x in params_str.split(',')]
    
    def _get_entity(self, ref_str: str) -> Optional[Dict]:
        """通过引用获取实体"""
        if ref_str and ref_str.startswith('#'):
            entity_id = int(ref_str[1:])
            return self.entities.get(entity_id)
        return None
    
    def get_summary(self) -> Dict:
        """获取检测结果摘要"""
        if not self._loaded:
            self.load_data()
        
        if not self.planes:
            self.detect_planes()
        
        if not self.room_dims:
            self.measure_room()
        
        if not self.wall_quality:
            self.analyze_walls()
        
        # 计算合格率
        total = 0
        passed = 0
        
        if '楼层净高' in self.room_dims:
            total += 1
            if self.room_dims['楼层净高']['合格']:
                passed += 1
        
        if '房间尺寸' in self.room_dims:
            total += 2  # 开间和进深
            if self.room_dims['房间尺寸']['合格']:
                passed += 2
        
        for wq in self.wall_quality:
            total += 2  # 垂直度和平整度
            if wq['垂直度合格']:
                passed += 1
            if wq['平整度合格']:
                passed += 1
        
        pass_rate = passed / total * 100 if total > 0 else 100
        
        return {
            'total_checks': total,
            'passed_checks': passed,
            'pass_rate': pass_rate,
            'overall': '优秀' if pass_rate >= 95 else '合格' if pass_rate >= 80 else '不合格'
        }


# ===== 便捷函数 =====

def quick_analysis(ifc_path: str, las_path: str) -> Dict:
    """
    快速分析函数
    
    Args:
        ifc_path: IFC文件路径
        las_path: LAS文件路径
    
    Returns:
        分析结果字典
    """
    analyzer = QualityAnalyzer(ifc_path, las_path)
    analyzer.load_data()
    analyzer.detect_planes()
    analyzer.measure_room()
    analyzer.analyze_walls()
    
    return {
        'planes': analyzer.planes,
        'room_dims': analyzer.room_dims,
        'wall_quality': analyzer.wall_quality,
        'report': analyzer.generate_report(),
        'summary': analyzer.get_summary()
    }


if __name__ == "__main__":
    # 测试
    import sys
    
    if len(sys.argv) < 3:
        print("用法: python quality_analyzer.py <ifc文件> <las文件>")
        sys.exit(1)
    
    ifc_path = sys.argv[1]
    las_path = sys.argv[2]
    
    result = quick_analysis(ifc_path, las_path)
    
    print("\n检测结果摘要:")
    print(f"合格率: {result['summary']['pass_rate']:.1f}%")
    print(f"总评: {result['summary']['overall']}")
    print("\n详细报告:")
    print(result['report'])