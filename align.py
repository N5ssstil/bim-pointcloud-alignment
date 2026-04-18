#!/usr/bin/env python3
"""
BIM-点云配准分析工具
功能：
1. 解析IFC文件提取墙体几何
2. 读取LAS点云数据
3. ICP配准对齐
4. 计算偏差并生成质量报告
"""

import re
import json
import numpy as np
import sys
from pathlib import Path

# ==================== IFC解析 ====================

def parse_ifc_file(ifc_path):
    """解析IFC文件，提取所有实体"""
    with open(ifc_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    entities = {}
    for match in re.finditer(r'#(\d+)\s*=\s*(\w+)\s*\(([^;]*?)\);', content, re.DOTALL):
        entity_id = int(match.group(1))
        entity_type = match.group(2)
        entity_params = match.group(3)
        entities[entity_id] = {'type': entity_type, 'params': entity_params}
    
    return entities

def parse_ifc_list(params_str):
    """解析IFC参数列表"""
    # 简单的参数分割（不处理嵌套）
    result = []
    current = ""
    paren_depth = 0
    
    for char in params_str:
        if char == '(':
            paren_depth += 1
            current += char
        elif char == ')':
            paren_depth -= 1
            current += char
        elif char == ',' and paren_depth == 0:
            result.append(current.strip())
            current = ""
        else:
            current += char
    
    if current.strip():
        result.append(current.strip())
    
    return result

def get_entity_reference(entities, ref_id):
    """获取实体引用"""
    if ref_id.startswith('#'):
        eid = int(ref_id[1:])
        return entities.get(eid)
    return None

def extract_wall_geometry(entities):
    """从IFC实体中提取墙体几何"""
    walls = []
    
    # 找所有墙体
    wall_ids = [eid for eid, data in entities.items() 
                if data['type'] in ['IFCWALLSTANDARDCASE', 'IFCWALL']]
    
    print(f"找到 {len(wall_ids)} 面墙体")
    
    for wall_id in wall_ids:
        wall_data = entities[wall_id]
        wall_info = {
            'id': wall_id,
            'name': '',
            'length': 0,
            'height': 0,
            'thickness': 0,
            'start_point': None,
            'end_point': None,
            'points': []
        }
        
        # 尝试从参数中提取信息
        params = parse_ifc_list(wall_data['params'])
        if len(params) > 1:
            wall_info['name'] = params[1].strip("'\"")
        
        walls.append(wall_info)
    
    return walls

def extract_rectangle_profiles(entities):
    """提取矩形轮廓（墙体截面）"""
    profiles = []
    
    for eid, data in entities.items():
        if data['type'] == 'IFCRECTANGLEPROFILEDEF':
            params = parse_ifc_list(data['params'])
            profile = {
                'id': eid,
                'type': params[0] if len(params) > 0 else '',
                'name': params[1] if len(params) > 1 else '',
                'width': float(params[3]) if len(params) > 3 else 0,
                'height': float(params[4]) if len(params) > 4 else 0
            }
            profiles.append(profile)
            print(f"矩形轮廓 #{eid}: 宽度={profile['width']:.1f}mm, 高度={profile['height']:.1f}mm")
    
    return profiles

def extract_extruded_solids(entities):
    """提取拉伸实体"""
    solids = []
    
    for eid, data in entities.items():
        if data['type'] == 'IFCEXTRUDEDAREASOLID':
            params = parse_ifc_list(data['params'])
            solid = {
                'id': eid,
                'profile_id': params[0] if len(params) > 0 else None,
                'position_id': params[1] if len(params) > 1 else None,
                'depth': float(params[3]) if len(params) > 3 else 0
            }
            solids.append(solid)
            print(f"拉伸实体 #{eid}: 深度={solid['depth']:.1f}mm")
    
    return solids

def extract_all_points_3d(entities):
    """提取所有3D坐标点"""
    points = {}
    
    for eid, data in entities.items():
        if data['type'] == 'IFCCARTESIANPOINT':
            params = data['params'].strip('()')
            if params:
                coords = [float(x.strip()) for x in params.split(',')]
                if len(coords) == 3:
                    points[eid] = np.array(coords)
                elif len(coords) == 2:
                    points[eid] = np.array([coords[0], coords[1], 0.0])
    
    return points

def extract_bim_bbox(entities):
    """从IFC提取边界框"""
    points = extract_all_points_3d(entities)
    if not points:
        return None
    
    coords = np.array(list(points.values()))
    return {
        'min': coords.min(axis=0),
        'max': coords.max(axis=0),
        'points': coords
    }

# ==================== LAS点云解析 ====================

def read_las_file(las_path):
    """读取LAS点云文件"""
    try:
        import laspy
    except ImportError:
        print("错误: 需要安装laspy库: pip install laspy")
        return None
    
    las = laspy.read(las_path)
    
    points = np.vstack([
        las.x, las.y, las.z
    ]).T
    
    # 尝试读取颜色
    colors = None
    if hasattr(las, 'red') and hasattr(las, 'green') and hasattr(las, 'blue'):
        colors = np.vstack([
            las.red, las.green, las.blue
        ]).T
    
    point_cloud = {
        'points': points,
        'colors': colors,
        'n_points': len(points),
        'bbox': {
            'min': points.min(axis=0),
            'max': points.max(axis=0)
        }
    }
    
    return point_cloud

# ==================== 配准算法 ====================

def compute_initial_alignment(bim_bbox, las_bbox):
    """计算初始对齐变换"""
    # BIM单位是毫米，点云单位是米
    # 转换BIM到米
    bim_scale = 0.001  # mm to m
    
    bim_min = bim_bbox['min'] * bim_scale
    bim_max = bim_bbox['max'] * bim_scale
    bim_center = (bim_min + bim_max) / 2
    
    las_min = las_bbox['min']
    las_max = las_bbox['max']
    las_center = (las_min + las_max) / 2
    
    # 计算平移向量（将BIM中心移动到点云中心）
    translation = las_center - bim_center
    
    print(f"\n=== 初始对齐 ===")
    print(f"BIM中心 (转换到米): ({bim_center[0]:.2f}, {bim_center[1]:.2f}, {bim_center[2]:.2f})")
    print(f"点云中心: ({las_center[0]:.2f}, {las_center[1]:.2f}, {las_center[2]:.2f})")
    print(f"平移向量: ({translation[0]:.2f}, {translation[1]:.2f}, {translation[2]:.2f})")
    
    return {
        'scale': bim_scale,
        'translation': translation,
        'bim_center': bim_center,
        'las_center': las_center
    }

def icp_registration(source_points, target_points, max_iterations=50, tolerance=1e-6):
    """简化的ICP配准算法"""
    n_points = min(len(source_points), len(target_points))
    
    # 下采样
    if len(source_points) > 10000:
        indices = np.random.choice(len(source_points), 10000, replace=False)
        source_points = source_points[indices]
    if len(target_points) > 10000:
        indices = np.random.choice(len(target_points), 10000, replace=False)
        target_points = target_points[indices]
    
    # 中心化
    source_center = source_points.mean(axis=0)
    target_center = target_points.mean(axis=0)
    
    source_centered = source_points - source_center
    target_centered = target_points - target_center
    
    # 使用SVD计算最优旋转
    H = source_centered.T @ target_centered
    U, S, Vt = np.linalg.svd(H)
    R = Vt.T @ U.T
    
    # 确保是正确旋转（det=1）
    if np.linalg.det(R) < 0:
        Vt[-1, :] *= -1
        R = Vt.T @ U.T
    
    t = target_center - R @ source_center
    
    return {
        'rotation': R,
        'translation': t,
        'rmse': np.sqrt(np.mean(np.sum((target_points - (R @ source_points.T).T - t)**2, axis=1)))
    }

def compute_point_to_plane_distance(point, plane_point, plane_normal):
    """计算点到平面的距离"""
    return abs(np.dot(point - plane_point, plane_normal))

def fit_plane_ransac(points, n_iterations=1000, threshold=0.05):
    """使用RANSAC拟合平面"""
    best_inliers = []
    best_plane = None
    
    n_points = len(points)
    if n_points < 3:
        return None, []
    
    for _ in range(n_iterations):
        # 随机选择3个点
        indices = np.random.choice(n_points, 3, replace=False)
        sample = points[indices]
        
        # 计算平面方程 ax + by + cz + d = 0
        v1 = sample[1] - sample[0]
        v2 = sample[2] - sample[0]
        normal = np.cross(v1, v2)
        
        norm = np.linalg.norm(normal)
        if norm < 1e-10:
            continue
        normal = normal / norm
        
        # 计算所有点到平面的距离
        d = -np.dot(normal, sample[0])
        distances = np.abs(points @ normal + d)
        
        inliers = np.where(distances < threshold)[0]
        
        if len(inliers) > len(best_inliers):
            best_inliers = inliers
            best_plane = (sample[0], normal)
    
    return best_plane, best_inliers

def analyze_deviation(bim_points, las_points, alignment):
    """分析点云与BIM的偏差"""
    # 转换BIM点到点云坐标系
    bim_transformed = bim_points * alignment['scale'] + alignment['translation']
    
    # 计算最近邻距离
    print("\n=== 偏差分析 ===")
    
    # 简单统计
    bim_mean = bim_transformed.mean(axis=0)
    las_mean = las_points.mean(axis=0)
    
    offset = las_mean - bim_mean
    
    print(f"BIM点云中心（转换后）: ({bim_mean[0]:.2f}, {bim_mean[1]:.2f}, {bim_mean[2]:.2f})")
    print(f"实测点云中心: ({las_mean[0]:.2f}, {las_mean[1]:.2f}, {las_mean[2]:.2f})")
    print(f"整体偏移: ({offset[0]:.2f}m, {offset[1]:.2f}m, {offset[2]:.2f}m)")
    
    return {
        'offset': offset,
        'bim_transformed': bim_transformed
    }

# ==================== 主程序 ====================

def main():
    # 文件路径
    ifc_path = "/home/admin/.openclaw/media/inbound/教学楼测量墙体---37c603dd-68e8-4dee-b2f0-9e41740270ce"
    las_path = "/home/admin/.openclaw/media/inbound/项目点云2---94a7adb9-ce6a-485f-90cf-d503d92cb5a9"
    
    print("=" * 60)
    print("BIM-点云配准分析")
    print("=" * 60)
    
    # 1. 解析IFC
    print("\n[1] 解析BIM文件 (IFC)...")
    entities = parse_ifc_file(ifc_path)
    print(f"   找到 {len(entities)} 个实体")
    
    walls = extract_wall_geometry(entities)
    profiles = extract_rectangle_profiles(entities)
    solids = extract_extruded_solids(entities)
    
    bim_bbox = extract_bim_bbox(entities)
    if bim_bbox:
        print(f"\n   BIM边界框 (mm):")
        print(f"     X: [{bim_bbox['min'][0]:.1f}, {bim_bbox['max'][0]:.1f}]")
        print(f"     Y: [{bim_bbox['min'][1]:.1f}, {bim_bbox['max'][1]:.1f}]")
        print(f"     Z: [{bim_bbox['min'][2]:.1f}, {bim_bbox['max'][2]:.1f}]")
    
    # 2. 读取LAS
    print("\n[2] 读取点云文件 (LAS)...")
    point_cloud = read_las_file(las_path)
    if point_cloud:
        print(f"   点数: {point_cloud['n_points']:,}")
        print(f"   边界框 (m):")
        print(f"     X: [{point_cloud['bbox']['min'][0]:.2f}, {point_cloud['bbox']['max'][0]:.2f}]")
        print(f"     Y: [{point_cloud['bbox']['min'][1]:.2f}, {point_cloud['bbox']['max'][1]:.2f}]")
        print(f"     Z: [{point_cloud['bbox']['min'][2]:.2f}, {point_cloud['bbox']['max'][2]:.2f}]")
    
    # 3. 初始对齐
    print("\n[3] 计算初始对齐...")
    if bim_bbox and point_cloud:
        alignment = compute_initial_alignment(bim_bbox, point_cloud['bbox'])
        
        # 4. 偏差分析
        deviation = analyze_deviation(bim_bbox['points'], point_cloud['points'], alignment)
        
        # 5. 平面检测（检测主要墙面）
        print("\n[4] 检测主要平面...")
        points = point_cloud['points']
        
        # 随机采样加速
        if len(points) > 50000:
            sample_idx = np.random.choice(len(points), 50000, replace=False)
            sample_points = points[sample_idx]
        else:
            sample_points = points
        
        # 检测地面（Z最低的点）
        z_values = sample_points[:, 2]
        ground_mask = z_values < (z_values.min() + 0.5)
        ground_points = sample_points[ground_mask]
        
        if len(ground_points) > 100:
            ground_plane, ground_inliers = fit_plane_ransac(ground_points, n_iterations=500, threshold=0.05)
            if ground_plane:
                print(f"   检测到地面平面:")
                print(f"     法向量: ({ground_plane[1][0]:.4f}, {ground_plane[1][1]:.4f}, {ground_plane[1][2]:.4f})")
                print(f"     平面点: ({ground_plane[0][0]:.2f}, {ground_plane[0][1]:.2f}, {ground_plane[0][2]:.2f})")
                print(f"     内点数: {len(ground_inliers)}")
                
                # 计算地面平整度
                ground_inlier_points = ground_points[ground_inliers]
                distances = np.abs(ground_inlier_points @ ground_plane[1] - np.dot(ground_plane[1], ground_plane[0]))
                print(f"     平整度(RMSE): {np.sqrt(np.mean(distances**2))*1000:.1f}mm")
        
        print("\n" + "=" * 60)
        print("分析完成！")
        print("=" * 60)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())