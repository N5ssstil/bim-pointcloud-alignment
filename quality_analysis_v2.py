#!/usr/bin/env python3
"""
BIM-点云施工质量分析 - 改进版
修正配准算法和质量评估标准
"""

import re
import numpy as np
from datetime import datetime

def read_las(las_path):
    """读取LAS点云"""
    import laspy
    las = laspy.read(las_path)
    points = np.vstack([las.x, las.y, las.z]).T
    return {
        'points': points,
        'n_points': len(points),
        'bbox': {'min': points.min(axis=0), 'max': points.max(axis=0)}
    }

def parse_ifc(ifc_path):
    """解析IFC"""
    with open(ifc_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    entities = {}
    for match in re.finditer(r'#(\d+)\s*=\s*(\w+)\s*\(([^;]*?)\);', content, re.DOTALL):
        entities[int(match.group(1))] = {'type': match.group(2), 'params': match.group(3)}
    return entities

def parse_coords(s):
    s = s.strip('()')
    return [float(x.strip()) for x in s.split(',')] if s else []

def get_ref(entities, ref):
    if ref and ref.startswith('#'):
        return entities.get(int(ref[1:]))
    return None

def extract_bim_walls(entities):
    """提取BIM墙体信息"""
    walls = []
    
    # 提取墙体位置点
    position_points = {}
    for eid, data in entities.items():
        if data['type'] == 'IFCAXIS2PLACEMENT3D':
            params = data['params'].split(',')
            loc = get_ref(entities, params[0].strip())
            if loc and loc['type'] == 'IFCCARTESIANPOINT':
                coords = parse_coords(loc['params'])
                if len(coords) >= 3:
                    position_points[eid] = coords
    
    # 提取墙体几何
    for eid, data in entities.items():
        if data['type'] == 'IFCEXTRUDEDAREASOLID':
            params = data['params'].split(',')
            if len(params) < 4:
                continue
            
            depth = float(params[3].strip())  # 拉伸高度
            
            profile = get_ref(entities, params[0].strip())
            if profile and profile['type'] == 'IFCRECTANGLEPROFILEDEF':
                pp = profile['params'].split(',')
                width = float(pp[3].strip()) if len(pp) > 3 else 0
                height = float(pp[4].strip()) if len(pp) > 4 else 0
                
                pos = get_ref(entities, params[1].strip())
                location = position_points.get(int(params[1].strip()[1:]) if params[1].strip().startswith('#') else 0)
                
                walls.append({
                    'id': eid,
                    'length_m': width / 1000,
                    'thickness_m': height / 1000,
                    'height_m': depth / 1000,
                    'location_mm': location
                })
    
    return walls

def detect_wall_planes(points, threshold=0.03):
    """检测墙面"""
    # 大幅下采样
    if len(points) > 10000:
        idx = np.random.choice(len(points), 10000, replace=False)
        points = points[idx]
    
    planes = []
    remaining = points.copy()
    
    for _ in range(6):  # 减少迭代次数
        if len(remaining) < 200:
            break
        
        # RANSAC - 减少尝试次数
        best_inliers = []
        best_normal = None
        best_centroid = None
        
        for attempt in range(50):
            idx = np.random.choice(len(remaining), 3, replace=False)
            sample = remaining[idx]
            
            v1 = sample[1] - sample[0]
            v2 = sample[2] - sample[0]
            n = np.cross(v1, v2)
            norm = np.linalg.norm(n)
            if norm < 1e-6:
                continue
            n = n / norm
            
            d = -np.dot(n, sample[0])
            dist = np.abs(remaining @ n + d)
            inliers = dist < threshold
            
            if np.sum(inliers) > np.sum(best_inliers):
                best_inliers = inliers
                best_normal = n
                best_centroid = sample[0]
        
        if np.sum(best_inliers) < 200:
            break
        
        inlier_pts = remaining[best_inliers]
        
        # 重新拟合
        centroid = inlier_pts.mean(axis=0)
        centered = inlier_pts - centroid
        _, _, vh = np.linalg.svd(centered)
        normal = vh[-1]
        
        # 计算RMSE
        dist_to_plane = np.abs(centered @ normal)
        rmse = np.sqrt(np.mean(dist_to_plane**2))
        
        # 判断是否为墙面（法向量Z分量小于0.3）
        is_wall = np.abs(normal[2]) < 0.3
        
        if is_wall:
            planes.append({
                'points': inlier_pts,
                'n_points': len(inlier_pts),
                'normal': normal,
                'centroid': centroid,
                'rmse_m': rmse,
                'rmse_mm': rmse * 1000
            })
        
        remaining = remaining[~best_inliers]
    
    return planes

def analyze_wall_quality(wall_plane, design_thickness_m=0.12, design_height_m=3.6):
    """分析墙面质量"""
    results = {}
    
    # 垂直度：墙面法向量应该水平（Z分量接近0）
    z_component = np.abs(wall_plane['normal'][2])
    verticality_angle = np.degrees(np.arcsin(z_component))
    verticality_deviation_mm = z_component * design_height_m * 1000
    
    results['垂直度'] = {
        'angle_deg': verticality_angle,
        'deviation_mm': verticality_deviation_mm,
        '合格': verticality_angle < 3.0  # 建筑标准：小于3度
    }
    
    # 平整度：RMSE
    flatness_mm = wall_plane['rmse_mm']
    results['平整度'] = {
        'rmse_mm': flatness_mm,
        '合格': flatness_mm < 8.0  # 建筑标准：小于8mm
    }
    
    return results

def generate_report(wall_planes, bim_walls):
    """生成质量报告"""
    lines = []
    lines.append("=" * 70)
    lines.append("         施工质量检测报告")
    lines.append("=" * 70)
    lines.append(f"检测时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"项目名称: 教学楼测量墙体")
    lines.append("")
    
    lines.append("【BIM设计信息】")
    lines.append(f"  墙体数量: {len(bim_walls)} 面")
    for i, w in enumerate(bim_walls[:4]):
        lines.append(f"  墙体#{i+1}: 长{w['length_m']:.2f}m, 厚{w['thickness_m']*1000:.0f}mm, 高{w['height_m']:.2f}m")
    lines.append("")
    
    lines.append("【实测点云信息】")
    lines.append(f"  检测平面数: {len(wall_planes)} 个")
    lines.append("")
    
    lines.append("-" * 70)
    lines.append("【检测结果】")
    lines.append("-" * 70)
    
    total_metrics = 0
    pass_count = 0
    
    for i, plane in enumerate(wall_planes):
        lines.append(f"\n墙面 #{i+1}:")
        lines.append(f"  测点数: {plane['n_points']:,}")
        lines.append(f"  中心坐标: ({plane['centroid'][0]:.2f}, {plane['centroid'][1]:.2f}, {plane['centroid'][2]:.2f}) m")
        lines.append(f"  法向量: ({plane['normal'][0]:.3f}, {plane['normal'][1]:.3f}, {plane['normal'][2]:.3f})")
        
        quality = analyze_wall_quality(plane)
        
        # 垂直度
        v = quality['垂直度']
        total_metrics += 1
        status = "✓ 合格" if v['合格'] else "✗ 不合格"
        if v['合格']:
            pass_count += 1
        lines.append(f"  垂直度: {v['angle_deg']:.2f}° (偏差 {v['deviation_mm']:.1f}mm) {status}")
        
        # 平整度
        f = quality['平整度']
        total_metrics += 1
        status = "✓ 合格" if f['合格'] else "✗ 不合格"
        if f['合格']:
            pass_count += 1
        lines.append(f"  平整度: RMSE = {f['rmse_mm']:.1f}mm {status}")
    
    lines.append("")
    lines.append("-" * 70)
    lines.append("【质量总评】")
    lines.append("-" * 70)
    pass_rate = pass_count / total_metrics * 100 if total_metrics > 0 else 0
    lines.append(f"  检测指标总数: {total_metrics}")
    lines.append(f"  合格指标数: {pass_count}")
    lines.append(f"  合格率: {pass_rate:.1f}%")
    
    if pass_rate >= 90:
        overall = "优秀"
    elif pass_rate >= 70:
        overall = "合格"
    else:
        overall = "不合格"
    
    lines.append(f"  总体评定: {overall}")
    lines.append("=" * 70)
    
    return '\n'.join(lines)

def main():
    print("BIM-点云施工质量分析 v2")
    print("=" * 60)
    
    ifc_path = "/home/admin/.openclaw/media/inbound/教学楼测量墙体---37c603dd-68e8-4dee-b2f0-9e41740270ce"
    las_path = "/home/admin/.openclaw/media/inbound/项目点云2---94a7adb9-ce6a-485f-90cf-d503d92cb5a9"
    
    # 解析IFC
    print("[1] 解析BIM模型...")
    entities = parse_ifc(ifc_path)
    bim_walls = extract_bim_walls(entities)
    print(f"    提取墙体: {len(bim_walls)} 面")
    
    # 读取点云
    print("[2] 读取点云...")
    las = read_las(las_path)
    print(f"    点数: {las['n_points']:,}")
    print(f"    范围: X[{las['bbox']['min'][0]:.2f}, {las['bbox']['max'][0]:.2f}]m")
    print(f"          Y[{las['bbox']['min'][1]:.2f}, {las['bbox']['max'][1]:.2f}]m")
    print(f"          Z[{las['bbox']['min'][2]:.2f}, {las['bbox']['max'][2]:.2f}]m")
    
    # 检测墙面
    print("[3] 检测墙面...")
    wall_planes = detect_wall_planes(las['points'])
    print(f"    检测到墙面: {len(wall_planes)} 个")
    
    # 生成报告
    print("[4] 生成报告...")
    report = generate_report(wall_planes, bim_walls)
    print("\n" + report)
    
    # 保存
    out_path = "/home/admin/.openclaw/workspace/bim-pointcloud-alignment/quality_report_v2.txt"
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"\n报告已保存: {out_path}")

if __name__ == "__main__":
    main()