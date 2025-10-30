# --------------------读取uid并写入配置文件--------------------
import pandas as pd
import yaml
import os
from pathlib import Path

# 获取项目根目录
project_root = Path(__file__).parent.parent

# Excel文件路径
ac_excel_path = project_root / "uid" / "103A信息化机房设备信息导出-空调.xls"
temp_hum_excel_path = project_root / "uid" / "103A信息化机房设备信息导出-温湿度.xls"

# ==================== 读取空调文件 ====================
print("正在读取空调文件...")
df_ac = pd.read_excel(ac_excel_path, skiprows=4)

# 存储空调数据的字典
ac_dict = {}

# 读取空调数据并按设备分类
# 列索引: 文本(列1)=设备名称, 文本.2(列8)=测点名称, 文本.3(列9)=uid
for _, row in df_ac.iterrows():
    # 跳过空行
    if pd.isna(row['文本']) or pd.isna(row['文本.2']) or pd.isna(row['文本.3']):
        continue
    
    device = str(row['文本']).strip()  # 空调设备名称
    point = str(row['文本.2']).strip()  # 测点名称
    uid = str(row['文本.3']).strip()  # 测点UID
    
    # 如果该设备还没有记录，就创建一个字典
    if device not in ac_dict:
        ac_dict[device] = {
            "device_name": device,
            "measurement_points": {}
        }
    
    # 添加测点及其对应的UID
    ac_dict[device]["measurement_points"][point] = uid

print(f"成功读取 {len(ac_dict)} 台空调的配置信息")

# ==================== 读取温湿度文件 ====================
print("\n正在读取温湿度传感器文件...")
df_temp_hum = pd.read_excel(temp_hum_excel_path, skiprows=4)

# 存储温度和湿度传感器的UID列表
temperature_sensor_uids = []
humidity_sensor_uids = []

# 读取温湿度传感器数据
# 列索引: 文本(列1)=设备名称, 文本.2(列6)=测点类型, 文本.3(列7)=uid
for _, row in df_temp_hum.iterrows():
    # 跳过空行
    if pd.isna(row['文本']) or pd.isna(row['文本.2']) or pd.isna(row['文本.3']):
        continue
    
    device = str(row['文本']).strip()  # 传感器设备名称
    point_type = str(row['文本.2']).strip()  # 测点类型（如"1#温度"或"1#湿度"）
    uid = str(row['文本.3']).strip()  # 测点UID
    
    # 根据测点类型分类
    if '温度' in point_type:
        temperature_sensor_uids.append(uid)
    elif '湿度' in point_type:
        humidity_sensor_uids.append(uid)

print(f"成功读取 {len(temperature_sensor_uids)} 个温度传感器")
print(f"成功读取 {len(humidity_sensor_uids)} 个湿度传感器")

# ==================== 构建配置数据结构 ====================
config = {
    "room_name": "103A信息化机房",
    "air_conditioners": ac_dict,
    "sensors": {
        "temperature_sensor_uid": temperature_sensor_uids,
        "humidity_sensor_uid": humidity_sensor_uids
    }
}

# 输出配置文件路径
output_path = project_root / "configs" / "uid_config.yaml"

# 确保输出目录存在
os.makedirs(output_path.parent, exist_ok=True)

# 写入YAML文件
with open(output_path, 'w', encoding='utf-8') as f:
    yaml.dump(config, f, allow_unicode=True, sort_keys=False, indent=2, default_flow_style=False)

# ==================== 打印统计信息 ====================
print(f"\n{'='*60}")
print(f"UID配置文件生成成功")
print(f"{'='*60}")
print(f"机房名称: {config['room_name']}")
print(f"空调总数: {len(ac_dict)}")
print(f"温度传感器总数: {len(temperature_sensor_uids)}")
print(f"湿度传感器总数: {len(humidity_sensor_uids)}")
print(f"配置文件路径: {output_path}")
print(f"{'='*60}")

# 打印前3台空调的信息作为示例
print(f"\n前3台空调信息预览:")
for i, (device_name, device_info) in enumerate(list(ac_dict.items())[:3], 1):
    print(f"\n{i}. {device_name}")
    print(f"   测点数量: {len(device_info['measurement_points'])}")
    points = list(device_info['measurement_points'].keys())
    print(f"   测点示例: {points[:5]}")  # 只显示前5个测点

# 打印传感器UID示例
print(f"\n温度传感器UID示例（前5个）:")
for i, uid in enumerate(temperature_sensor_uids[:5], 1):
    print(f"  {i}. {uid}")

print(f"\n湿度传感器UID示例（前5个）:")
for i, uid in enumerate(humidity_sensor_uids[:5], 1):
    print(f"  {i}. {uid}")
