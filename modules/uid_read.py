# --------------------读取uid并写入配置文件--------------------
import pandas as pd
import yaml
import os
from pathlib import Path

# 获取项目根目录
project_root = Path(__file__).parent.parent

# Excel文件路径
excel_path = project_root / "uid" / "1号楼IDC机房空调AO量及DO量测点.xlsx"

# 读取Excel文件
df = pd.read_excel(excel_path)

# 去掉空行
df = df.dropna(subset=["设备名称", "测点名称", "uid"])

# 存储空调数据的字典
ac_dict = {}

# 读取数据并按空调分类
for _, row in df.iterrows():
    device = row["设备名称"].strip()  # 空调设备名称
    point = row["测点名称"].strip()  # 测点名称
    uid = row["uid"].strip()  # 测点UID
    
    # 如果该设备还没有记录，就创建一个字典
    if device not in ac_dict:
        ac_dict[device] = {
            "device_name": device,
            "measurement_points": {}
        }
    
    # 添加测点及其对应的UID
    ac_dict[device]["measurement_points"][point] = uid

# 构建配置数据结构
config = {
    "room_name": "1号楼IDC机房",
    "air_conditioners": ac_dict
}

# 输出配置文件路径
output_path = project_root / "configs" / "uid_config.yaml"

# 确保输出目录存在
os.makedirs(output_path.parent, exist_ok=True)

# 写入YAML文件
with open(output_path, 'w', encoding='utf-8') as f:
    yaml.dump(config, f, allow_unicode=True, sort_keys=False, indent=2, default_flow_style=False)

# 打印统计信息
print(f"{'='*60}")
print(f"UID配置文件生成成功")
print(f"{'='*60}")
print(f"机房名称: {config['room_name']}")
print(f"空调总数: {len(ac_dict)}")
print(f"配置文件路径: {output_path}")
print(f"{'='*60}")

# 打印前5台空调的信息作为示例
print(f"\n前5台空调信息预览:")
for i, (device_name, device_info) in enumerate(list(ac_dict.items())[:5], 1):
    print(f"\n{i}. {device_name}")
    print(f"   测点数量: {len(device_info['measurement_points'])}")
    print(f"   测点: {list(device_info['measurement_points'].keys())}")
