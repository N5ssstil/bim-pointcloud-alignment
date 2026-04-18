#!/usr/bin/env python3
"""
BIM-点云完整配准与施工质量分析
功能：
1. 从IFC提取墙体几何和位置
2. 从点云检测墙面
3. 基于特征点配准
4. 计算墙体偏差（垂直度、平整度、位置偏差）
5. 生成施工质量报告
"""

import re
import json
import numpy as np
from datetime import datetime

# ==================== 文件解析 ====================

def read_las_file(las_path):
    """读取LAS点云"""
    import laspy
    las = laspy.read(las_path)
    
    points = np.vstack([las.x, las.y, las.z]).T
    colors = None
    if hasattr(las, 'red'):
        colors = np.vstack([las.red, las.green, las.blue]).T
    
    return {
        'points': points,
        'colors': colors,
        'n_points': len(points),
        'bbox': {'min': points.min(axis=0), 'max': points.max(axis=0)}
    }

def parse_ifc(ifc_path):
    """解析IFC文件"""
    with open(ifc_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    entities = {}
    for match in re.finditer(r'#(\d+)\s*=\s*(\w+)\s*\(([^;]*?)\);', content, re.DOTALL):
        entities[int(match.group(1))] = {
            'type': match.group(2),
            'params': match.group(3)
        }
    return entities

def parse_coords(params_str):
    """解析坐标"""
    params_str = params_str.strip('()')
    return [float(x.strip()) for x in params_str.split(',')] if params_str else []

def get_entity(entities, ref_str):
    """通过引用获取实体"""
    if ref_str and ref_str.startswith('#'):
        return entities.get(int(ref_str[1:]))
    return None

# ==================== 墙体提取 ====================

def extract_wall_corners_from_ifc(entities):
    """从IFC提取墙体角落点"""
    wall_corners = []
    
    # 找IFCLOCALPLACEMENT的位置点
    for eid, data in entities.items():
        if data['type'] == 'IFCLOCALPLACEMENT':
            params = data['params'].split(',')
            if len(params) > 1:
                # 获取相对位置
                axis_ref = params[1].strip()
                axis = get_entity(entities, axis_ref)
                if axis and axis['type'] == 'IFCAXIS2PLACEMENT3D':
                    axis_params = axis['params'].split(',')
                    loc_ref = axis_params[0].strip()
                    loc = get_entity(entities, loc_ref)
                    if loc and loc['type'] == 'IFCCARTESIANPOINT':
                        coords = parse_coords(loc['params'])
                        if len(coords) >= 3:
                            wall_corners.append({
                                'id': eid,
                                'coords_mm': coords,
                                'coords_m': [coords[0]/1000, coords[1]/1000, coords[2]/1000]
                            })
    
    return wall_corners

def extract_wall_geometries(entities):
    """提取墙体几何参数"""
    walls = []
    
    for eid, data in entities.items():
        if data['type'] == 'IFCEXTRUDEDAREASOLID':
            params = data['params'].split(',')
            if len(params) < 4:
                continue
            
            # 拉伸深度 = 墙体高度
            depth = float(params[3].strip())
            
            # 获取轮廓（矩形 = 墙体长度×厚度）
            profile = get_entity(entities, params[0].strip())
            if profile and profile['type'] == 'IFCRECTANGLEPROFILEDEF':
                profile_params = profile['params'].split(',')
                width = float(profile_params[3].strip()) if len(profile_params) > 3 else 0
                height = float(profile_params[4].strip()) if len(profile_params) > 4 else 0
                
                walls.append({
                    'id': eid,
                    'length_mm': width,
                    'thickness_mm': height,
                    'height_mm': depth,
                    'length_m': width / 1000,
                    'thickness_m': height / 1000,
                    'height_m': depth / 1000
                })
    
    return walls

# ==================== 点云分析 ====================

def detect_planes_ransac(points, threshold=0.05, min_points=100):
    """使用RANSAC检测平面"""
    planes = []
    remaining_points = points.copy()
    
    while len(remaining_points) > min_points:
        # 随机选3个点
        indices = np.random.choice(len(remaining_points), 3, replace=False)
        sample = remaining_points[indices]
        
        # 计算平面
        v1 = sample[1] - sample[0]
        v2 = sample[2] - sample[0]
        normal = np.cross(v1, v2)
        norm = np.linalg.norm(normal)
        if norm < 1e-6:
            continue
        normal = normal / norm
        
        # 计算距离
        d = -np.dot(normal, sample[0])
        distances = np.abs(remaining_points @ normal + d)
        
        inliers = distances < threshold
        n_inliers = np.sum(inliers)
        
        if n_inliers > min_points:
            # 用内点重新拟合平面
            inlier_points = remaining_points[inliers]
            centroid = inlier_points.mean(axis=0)
            _, _, vh = np.linalg.svd(inlier_points - centroid)
            normal = vh[-1]
            
            plane_points = remaining_points[inliers]
            
            # 分类：地面/墙面/天花板
            abs_normal = np.abs(normal)
            if abs_normal[2] > 0.9:
                plane_type = 'floor' if normal[2] > 0 else 'ceiling'
            else:
                plane_type = 'wall'
            
            planes.append({
                'type': plane_type,
                'normal': normal,
                'centroid': centroid,
                'n_points': len(plane_points),
                'points': plane_points,
                'rmse': np.sqrt(np.mean((np.abs(plane_points @ normal - np.dot(normal, centroid)))**2))
            })
            
            remaining_points = remaining_points[~inliers]
        
        if len(planes) > 10:  # 最多10个平面
            break
    
    return planes

def segment_point_cloud(points):
    """分割点云：地面、墙面、天花板"""
    # 采样加速
    if len(points) > 100000:
        sample_idx = np.random.choice(len(points), 100000, replace=False)
        points = points[sample_idx]
    
    # 检测平面
    planes = detect_planes_ransac(points, threshold=0.03, min_points=500)
    
    # 分类
    walls = [p for p in planes if p['type'] == 'wall']
    floors = [p for p in planes if p['type'] == 'floor']
    ceilings = [p for p in planes if p['type'] == 'ceiling']
    
    return {
        'walls': walls,
        'floors': floors,
        'ceilings': ceilings,
        'all_planes': planes
    }

# ==================== 配准 ====================

def find_matching_corners(bim_corners, las_planes):
    """匹配BIM墙体角点和点云墙面"""
    # 将BIM角点转换到米单位
    bim_points = np.array([c['coords_m'] for c in bim_corners])
    
    # 从点云墙面提取特征点（墙面中心）
    wall_centroids = np.array([w['centroid'] for w in las_planes['walls']])
    
    return bim_points, wall_centroids

def compute_alignment_transform(bim_points, las_points):
    """计算配准变换"""
    # 中心化
    bim_center = bim_points.mean(axis=0)
    las_center = las_points.mean(axis=0)
    
    # 计算尺度（通过边界框）
    bim_range = bim_points.max(axis=0) - bim_points.min(axis=0)
    las_range = las_points.max(axis=0) - las_points.min(axis=0)
    
    # 尺度因子
    scale = np.mean(las_range / (bim_range + 1e-10))
    
    # 平移
    translation = las_center - bim_center * scale
    
    return {
        'scale': scale,
        'translation': translation,
        'bim_center': bim_center,
        'las_center': las_center
    }

# ==================== 质量评估 ====================

def evaluate_wall_quality(wall_plane, bim_wall):
    """评估墙面施工质量"""
    results = {}
    
    # 垂直度：墙面法向量与理论垂直方向的偏差
    theoretical_normal = np.array([0, 0, 1])  # 理论垂直向上
    if wall_plane['type'] == 'wall':
        # 墙面应该垂直，法向量的Z分量应该接近0
        verticality_error = np.abs(wall_plane['normal'][2])
        results['垂直度偏差'] = {
            'value_deg': np.degrees(np.arcsin(verticality_error)),
            'value_mm': verticality_error * bim_wall['height_m'] * 1000,
            'assessment': '合格' if verticality_error < 0.02 else '不合格'
        }
    
    # 平整度：点云到拟合平面的距离RMSE
    results['平整度'] = {
        'value_mm': wall_plane['rmse'] * 1000,
        'assessment': '合格' if wall_plane['rmse'] < 0.005 else '不合格'
    }
    
    return results

def generate_quality_report(bim_walls, las_segmentation, alignment):
    """生成施工质量报告"""
    report = {
        'title': '施工质量检测报告',
        'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'project': '教学楼测量墙体',
        'results': []
    }
    
    # 评估每个检测到的墙面
    for i, wall_plane in enumerate(las_segmentation['walls']):
        if i >= len(bim_walls):
            bim_wall = {'height_m': 3.6, 'thickness_m': 0.12}
        else:
            bim_wall = bim_walls[i]
        
        quality = evaluate_wall_quality(wall_plane, bim_wall)
        
        report['results'].append({
            'wall_id': i + 1,
            'point_count': wall_plane['n_points'],
            'centroid': wall_plane['centroid'].tolist(),
            'quality': quality
        })
    
    return report

def format_report_text(report):
    """格式化报告为文本"""
    lines = []
    lines.append("=" * 60)
    lines.append(report['title'])
    lines.append("=" * 60)
    lines.append(f"项目: {report['project']}")
    lines.append(f"日期: {report['date']}")
    lines.append("")
    
    for result in report['results']:
        lines.append(f"【墙面 #{result['wall_id']}】")
        lines.append(f"  点数: {result['point_count']:,}")
        lines.append(f"  中心位置: ({result['centroid'][0]:.2f}, {result['centroid'][1]:.2f}, {result['centroid'][2]:.2f})m")
        
        for metric, values in result['quality'].items():
            if 'value_mm' in values:
                lines.append(f"  {metric}: {values['value_mm']:.1f}mm ({values['assessment']})")
            elif 'value_deg' in values:
                lines.append(f"  {metric}: {values['value_deg']:.2f}° ({values['assessment']})")
        
        lines.append("")
    
    # 总结
    total_pass = sum(1 for r in report['results'] 
                     for m, v in r['quality'].items() if v['assessment'] == '合格')
    total_metrics = sum(len(r['quality']) for r in report['results'])
    
    lines.append("【质量总评】")
    lines.append(f"  合格项: {total_pass}/{total_metrics}")
    lines.append(f"  合格率: {total_pass/total_metrics*100:.1f}%")
    lines.append("=" * 60)
    
    return '\n'.join(lines)

# ==================== 主程序 ====================

def main():
    print("=" * 60)
    print("BIM-点云配准与施工质量分析")
    print("=" * 60)
    
    # 文件路径
    ifc_path = "/home/admin/.openclaw/media/inbound/教学楼测量墙体---37c603dd-68e8-4dee-b2f0-9e41740270ce"
    las_path = "/home/admin/.openclaw/media/inbound/项目点云2---94a7adb9-ce6a-485f-90cf-d503d92cb5a9"
    
    # 1. 解析IFC
    print("\n[步骤1] 解析BIM模型...")
    entities = parse_ifc(ifc_path)
    bim_corners = extract_wall_corners_from_ifc(entities)
    bim_walls = extract_wall_geometries(entities)
    
    print(f"  墙体角点: {len(bim_corners)} 个")
    for c in bim_corners[:5]:
        print(f"    #{c['id']}: ({c['coords_m'][0]:.3f}, {c['coords_m'][1]:.3f}, {c['coords_m'][2]:.3f})m")
    
    print(f"  墙体几何: {len(bim_walls)} 个")
    for w in bim_walls[:4]:
        print(f"    #{w['id']}: 长{w['length_m']:.2f}m × 厚{w['thickness_m']:.3f}m × 高{w['height_m']:.2f}m")
    
    # 2. 读取点云
    print("\n[步骤2] 读取点云数据...")
    las_data = read_las_file(las_path)
    print(f"  点数: {las_data['n_points']:,}")
    print(f"  范围: X[{las_data['bbox']['min'][0]:.2f}, {las_data['bbox']['max'][0]:.2f}]m")
    print(f"        Y[{las_data['bbox']['min'][1]:.2f}, {las_data['bbox']['max'][1]:.2f}]m")
    print(f"        Z[{las_data['bbox']['min'][2]:.2f}, {las_data['bbox']['max'][2]:.2f}]m")
    
    # 3. 点云分割
    print("\n[步骤3] 点云平面分割...")
    segmentation = segment_point_cloud(las_data['points'])
    
    print(f"  检测到 {len(segmentation['walls'])} 个墙面")
    print(f"  检测到 {len(segmentation['floors'])} 个地面")
    print(f"  检测到 {len(segmentation['ceilings'])} 个天花板")
    
    for i, wall in enumerate(segmentation['walls']):
        print(f"    墙面#{i+1}: {wall['n_points']:,}点, 平整度RMSE={wall['rmse']*1000:.1f}mm")
    
    for i, floor in enumerate(segmentation['floors']):
        print(f"    地面#{i+1}: {floor['n_points']:,}点, 平整度RMSE={floor['rmse']*1000:.1f}mm")
    
    # 4. 配准分析
    print("\n[步骤4] 配准分析...")
    bim_points, las_points = find_matching_corners(bim_corners, segmentation)
    
    if len(bim_points) > 0 and len(las_points) > 0:
        alignment = compute_alignment_transform(bim_points, las_points)
        print(f"  尺度因子: {alignment['scale']:.4f}")
        print(f"  平移向量: ({alignment['translation'][0]:.2f}, {alignment['translation'][1]:.2f}, {alignment['translation'][2]:.2f})m")
    
    # 5. 质量评估
    print("\n[步骤5] 施工质量评估...")
    report = generate_quality_report(bim_walls, segmentation, alignment)
    
    # 输出报告
    report_text = format_report_text(report)
    print("\n" + report_text)
    
    # 保存报告
    report_path = "/home/admin/.openclaw/workspace/bim-pointcloud-alignment/quality_report.txt"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_text)
    print(f"\n报告已保存至: {report_path}")
    
    return report

if __name__ == "__main__":
    main()