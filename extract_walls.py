#!/usr/bin/env python3
"""
精确提取BIM墙体几何并生成对比点云
"""

import re
import json
import numpy as np
from pathlib import Path

def parse_ifc_complete(ifc_path):
    """完整解析IFC文件"""
    with open(ifc_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    # 提取所有实体
    entities = {}
    for match in re.finditer(r'#(\d+)\s*=\s*(\w+)\s*\(([^;]*?)\);', content, re.DOTALL):
        entity_id = int(match.group(1))
        entity_type = match.group(2)
        entity_params = match.group(3)
        entities[entity_id] = {'type': entity_type, 'params': entity_params}
    
    return entities, content

def parse_ifc_coords(params_str):
    """解析IFC坐标字符串"""
    params_str = params_str.strip('()')
    if not params_str:
        return []
    return [float(x.strip()) for x in params_str.split(',')]

def get_entity_by_ref(entities, ref_str):
    """通过引用字符串获取实体"""
    if not ref_str or not ref_str.startswith('#'):
        return None
    ref_id = int(ref_str[1:])
    return entities.get(ref_id)

def extract_wall_geometry_detailed(entities):
    """详细提取墙体几何"""
    walls_data = []
    
    # 找所有墙体的代表实体
    for eid, data in entities.items():
        if data['type'] == 'IFCEXTRUDEDAREASOLID':
            # 解析拉伸实体
            params = data['params']
            parts = params.split(',')
            if len(parts) < 4:
                continue
            
            profile_ref = parts[0].strip()
            position_ref = parts[1].strip()
            depth = float(parts[3].strip())
            
            # 获取轮廓
            profile = get_entity_by_ref(entities, profile_ref)
            if profile and profile['type'] == 'IFCRECTANGLEPROFILEDEF':
                profile_params = profile['params'].split(',')
                width = float(profile_params[3].strip()) if len(profile_params) > 3 else 0
                height = float(profile_params[4].strip()) if len(profile_params) > 4 else 0
                
                # 获取位置信息
                position = get_entity_by_ref(entities, position_ref)
                location = None
                if position and position['type'] == 'IFCAXIS2PLACEMENT3D':
                    pos_params = position['params']
                    # 获取位置点引用
                    loc_ref = pos_params.split(',')[0].strip()
                    loc_entity = get_entity_by_ref(entities, loc_ref)
                    if loc_entity and loc_entity['type'] == 'IFCCARTESIANPOINT':
                        location = parse_ifc_coords(loc_entity['params'])
                
                wall_info = {
                    'solid_id': eid,
                    'width_mm': width,
                    'height_mm': height,  # 墙厚度
                    'depth_mm': depth,    # 墙高度
                    'location': location,
                    'profile_type': 'rectangle'
                }
                
                walls_data.append(wall_info)
                print(f"墙体实体 #{eid}:")
                print(f"  墙体长度: {width:.1f}mm")
                print(f"  墙体厚度: {height:.1f}mm")
                print(f"  墙体高度: {depth:.1f}mm")
                if location:
                    print(f"  位置: ({location[0]:.1f}, {location[1]:.1f}, {location[2]:.1f})mm")
    
    return walls_data

def extract_wall_from_local_placements(entities, content):
    """从IFCLOCALPLACEMENT提取墙体位置"""
    wall_positions = []
    
    # 查找IFCLOCALPLACEMENT链
    placements = {}
    for eid, data in entities.items():
        if data['type'] == 'IFCLOCALPLACEMENT':
            params = data['params']
            parts = params.split(',')
            placements[eid] = {
                'placement_rel_to': parts[0].strip() if len(parts) > 0 else None,
                'relative_placement': parts[1].strip() if len(parts) > 1 else None
            }
    
    # 查找IFCCARTESIANPOINT定义的位置
    locations = {}
    for eid, data in entities.items():
        if data['type'] == 'IFCCARTESIANPOINT':
            coords = parse_ifc_coords(data['params'])
            if len(coords) >= 2:
                locations[eid] = coords
    
    # 查找IFCAXIS2PLACEMENT3D
    axis3d = {}
    for eid, data in entities.items():
        if data['type'] == 'IFCAXIS2PLACEMENT3D':
            params = data['params']
            parts = params.split(',')
            loc_ref = parts[0].strip() if len(parts) > 0 else None
            axis3d[eid] = {
                'location_ref': loc_ref
            }
            if loc_ref and loc_ref.startswith('#'):
                loc_id = int(loc_ref[1:])
                if loc_id in locations:
                    axis3d[eid]['location'] = locations[loc_id]
    
    print("\n=== 墙体位置提取 ===")
    for eid, placement in placements.items():
        rel_placement = placement['relative_placement']
        if rel_placement and rel_placement.startswith('#'):
            axis_id = int(rel_placement[1:])
            if axis_id in axis3d and 'location' in axis3d[axis_id]:
                loc = axis3d[axis_id]['location']
                wall_positions.append({
                    'placement_id': eid,
                    'location': loc
                })
                print(f"位置 #{eid}: ({loc[0]:.1f}, {loc[1]:.1f}, {loc[2] if len(loc)>2 else 0:.1f})mm")
    
    return wall_positions

def generate_wall_points(walls_data, wall_positions):
    """生成墙体的点云表示"""
    wall_points = []
    
    for wall in walls_data:
        length = wall['width_mm']
        thickness = wall['height_mm']
        height = wall['depth_mm']
        
        if wall['location']:
            x, y, z = wall['location']
        else:
            x, y, z = 0, 0, 0
        
        # 生成墙体表面点云
        # 墙体是一个长方体
        n_points_per_face = 100  # 每面100个点
        
        # 面1和面2 (长度×高度)
        for i in range(n_points_per_face):
            px = x + np.random.uniform(0, length)
            pz = z + np.random.uniform(0, height)
            wall_points.append([px, y, pz])           # 面1
            wall_points.append([px, y + thickness, pz]) # 面2
        
        # 面3和面4 (厚度×高度)
        for i in range(n_points_per_face // 2):
            py = y + np.random.uniform(0, thickness)
            pz = z + np.random.uniform(0, height)
            wall_points.append([x, py, pz])            # 面3
            wall_points.append([x + length, py, pz])   # 面4
        
        # 面5和面6 (长度×厚度) - 顶面和底面
        for i in range(n_points_per_face // 2):
            px = x + np.random.uniform(0, length)
            py = y + np.random.uniform(0, thickness)
            wall_points.append([px, py, z])            # 底面
            wall_points.append([px, py, z + height])   # 顶面
    
    return np.array(wall_points)

def main():
    ifc_path = "/home/admin/.openclaw/media/inbound/教学楼测量墙体---37c603dd-68e8-4dee-b2f0-9e41740270ce"
    
    print("=" * 60)
    print("BIM墙体几何精确提取")
    print("=" * 60)
    
    entities, content = parse_ifc_complete(ifc_path)
    print(f"实体总数: {len(entities)}")
    
    # 提取墙体几何
    walls_data = extract_wall_geometry_detailed(entities)
    
    # 提取墙体位置
    wall_positions = extract_wall_from_local_placements(entities, content)
    
    # 生成墙体点云
    if walls_data:
        wall_points = generate_wall_points(walls_data, wall_positions)
        print(f"\n生成的墙体点云: {len(wall_points)} 个点")
        
        # 转换到米单位
        wall_points_m = wall_points * 0.001
        
        # 保存
        np.savetxt('/home/admin/.openclaw/workspace/bim-pointcloud-alignment/bim_wall_points.csv',
                   wall_points_m, delimiter=',', 
                   header='x,y,z', comments='')
        print("墙体点云已保存到 bim_wall_points.csv")
        
        # 边界框
        print(f"\nBIM墙体点云边界 (米):")
        print(f"  X: [{wall_points_m[:,0].min():.2f}, {wall_points_m[:,0].max():.2f}]")
        print(f"  Y: [{wall_points_m[:,1].min():.2f}, {wall_points_m[:,1].max():.2f}]")
        print(f"  Z: [{wall_points_m[:,2].min():.2f}, {wall_points_m[:,2].max():.2f}]")

if __name__ == "__main__":
    main()