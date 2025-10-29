# --------------------读取uid并创建空调实例--------------------
import pandas as pd

class AirConditioner:
    def __init__(self, device_name):
        self.device_name = device_name  # 空调设备名称
        self.measurement_points = {}  # 存储测点和UID的字典
        
    def add_measurement_point(self, point_name, uid):
        self.measurement_points[point_name] = uid  # 添加测点及其对应的UID

# 读取Excel文件
df = pd.read_excel("C:\\Users\\zouwei\\Desktop\\1号楼IDC机房空调AO量及DO量测点_0617(2).xlsx")

# 去掉空行
df = df.dropna(subset=["设备名称", "测点名称", "uid"])

# 存储空调实例的字典
ac_dict = {}

for _, row in df.iterrows():
    device = row["设备名称"].strip()  # 空调设备名称
    point = row["测点名称"].strip()  # 测点名称
    uid = row["uid"].strip()  # 测点UID
    
    # 如果该设备还没有实例化，就创建一个空调实例
    if device not in ac_dict:
        ac_dict[device] = AirConditioner(device)
    
    # 为空调实例添加测点
    ac_dict[device].add_measurement_point(point, uid)

# 打印每个空调实例的测点信息
for ac in ac_dict.values():
    print(f"空调设备: {ac.device_name}")
    print(f"测点: {ac.measurement_points}")
    print("-" * 50)
