# UID配置文件适配说明

## 概述

`data_reading_writing.py` 已经修改为同时支持**旧格式**和**新格式**的 `uid_config.yaml`。

---

## 新格式结构

```yaml
room_name: 1号楼IDC机房
air_conditioners:
  佳力图KN10空调4-3-9:
    device_name: 佳力图KN10空调4-3-9
    measurement_points:
      温度设定值: 64d36414_c7cf_4b72_a3ff_b55c0d4ccffc
      湿度设置值: fd735696_baf7_4125_9eb5_ffaa40c9966b
      开关机命令: 80c662f3_0173_4b21_a36c_f63f722bce4d
  艾特空调4-1-4:
    device_name: 艾特空调4-1-4
    measurement_points:
      送风温度设置点: nodeZNV.00001006000000001139.0176302001
      湿度设定点: nodeZNV.00001006000000001139.0176306001
      监控开关机: e3867c9d_ee5d_4698_a437_6df10951528e
```

---

## 主要修改内容

### 1. 新增辅助函数

#### `_extract_uids_from_air_conditioners(uid_config, measurement_point_names=None)`
从新格式中提取 UID 列表

**参数：**
- `uid_config`: 配置字典
- `measurement_point_names`: 要提取的测点名称列表，None 表示提取所有

**返回：** UID 列表

**示例：**
```python
# 提取所有测点的 UID
all_uids = _extract_uids_from_air_conditioners(uid_config)

# 提取特定测点的 UID
temp_uids = _extract_uids_from_air_conditioners(
    uid_config, 
    ['温度设定值', '温度设定点']
)
```

---

#### `_get_air_conditioner_uids_and_names(uid_config)`
提取所有空调的 UID 和名称列表

**返回：** `(uids列表, names列表)`

**UID 提取优先级：**
1. 开关机相关测点：`监控开关机`、`监控开关机状态`、`开关机命令`
2. 温度设定点：`温度设定值`、`温度设定点`、`回风温度设定点（℃）`、`送风温度设置点`

**示例：**
```python
uids, names = _get_air_conditioner_uids_and_names(uid_config)
# uids: ['80c662f3_...', 'e3867c9d_...']
# names: ['佳力图KN10空调4-3-9', '艾特空调4-1-4']
```

---

#### `_map_measurement_points_to_uids(uid_config, ac_name, point_names)`
将空调的测点名称映射到 UID

**示例：**
```python
points_mapping = _map_measurement_points_to_uids(
    uid_config,
    '佳力图KN10空调4-3-9',
    ['温度设定值', '湿度设置值']
)
# 返回: {'温度设定值': 'uid1', '湿度设置值': 'uid2'}
```

---

### 2. 修改的现有函数

#### `get_measurements_tags_fields(uid_config, uid_type, measurements_fields_dict)`

**旧格式用法：**
```python
# measurements_fields_dict 格式: {measurement_type: [value1, value2]}
measurements_fields_dict = {
    "indoor_temperature": [25.0, 26.0],
    "outdoor_temperature": [30.0, 31.0]
}

uid_values_mapping, get_value_by_uid = get_measurements_tags_fields(
    uid_config, 
    "dc_status_data_uid", 
    measurements_fields_dict
)
```

**新格式用法：**
```python
# measurements_fields_dict 格式: {ac_name: {point_name: value}}
measurements_fields_dict = {
    "佳力图KN10空调4-3-9": {
        "温度设定值": 25.0,
        "湿度设置值": 50.0
    },
    "艾特空调4-1-4": {
        "送风温度设置点": 26.0,
        "湿度设定点": 55.0
    }
}

# uid_type 参数会被忽略（传入 None 即可）
uid_values_mapping, get_value_by_uid = get_measurements_tags_fields(
    uid_config, 
    None, 
    measurements_fields_dict
)
```

---

#### `reading_data_query(...)`

函数自动检测配置格式，无需修改调用方式。

**旧格式：** 从 `uid_config[query_uid]` 读取  
**新格式：** 从 `uid_config['air_conditioners']` 读取

**指定查询测点（新格式）：**
```python
# 查询特定测点
df = reading_data_query(
    influxdb_config,
    uid_config,
    reading_data_client,
    query_range="-1h",
    query_measurement=['温度设定值', '湿度设置值']  # 测点名称列表
)
```

---

#### `generate_optimization_result_points(...)`

函数自动检测配置格式：

**旧格式：** 从 `uid_config['device_uid']` 读取  
**新格式：** 调用 `_get_air_conditioner_uids_and_names()` 提取

无需修改调用方式，完全向后兼容。

---

## 数据写入示例

### 使用新格式写入设置数据

```python
from utils import data_reading_writing

# 构建要写入的数据（新格式）
setting_data_measurements_fields = {
    "佳力图KN10空调4-3-9": {
        "温度设定值": 24.5,
        "湿度设置值": 50.0,
        "开关机命令": 1
    },
    "艾特空调4-1-4": {
        "送风温度设置点": 25.0,
        "湿度设定点": 55.0,
        "监控开关机": 1
    }
}

# 写入数据库
data_reading_writing.setting_data_writing(
    influxdb_config,
    uid_config,
    setting_data_measurements_fields,
    setting_data_client
)
```

---

## 兼容性说明

### ✅ 完全兼容的场景

1. **所有读取操作** - `reading_data_query()` 自动适配
2. **所有写入操作** - `prediction_data_writing()`, `setting_data_writing()`, `reference_data_writing()`
3. **优化结果写入** - `optimization_result_writing_suggestions()`, `optimization_result_writing_reference()`

### ⚠️ 需要注意的变化

1. **`get_measurements_tags_fields()` 参数格式变化**
   - 旧格式：`{measurement_type: [value1, value2]}`
   - 新格式：`{ac_name: {point_name: value}}`

2. **测点名称映射**
   - 新格式使用实际的中文测点名称（如 `温度设定值`）
   - 旧格式使用英文 measurement 类型（如 `indoor_temperature`）

---

## 迁移建议

### 推荐方案：完全使用新格式

1. ✅ 运行 `modules/uid_read.py` 生成 `uid_config.yaml`
2. ✅ 修改调用代码以使用新的参数格式
3. ✅ 测试所有读写功能

### 过渡方案：混合使用

可以保留旧格式的某些部分，同时添加新格式的 `air_conditioners` 部分：

```yaml
# 旧格式部分（用于其他传感器）
dc_status_data_uid:
  indoor_temperature_sensor_uid: [uid1, uid2]

# 新格式部分（用于空调控制）
air_conditioners:
  佳力图KN10空调4-3-9:
    device_name: 佳力图KN10空调4-3-9
    measurement_points:
      温度设定值: uid_xxx
```

代码会自动选择合适的格式进行处理。

---

## 常见问题

### Q: 如何判断使用了哪种格式？

A: 代码会首先检查 `uid_config.get(uid_type)`：
- 如果存在，使用旧格式逻辑
- 如果不存在，使用新格式逻辑（从 `air_conditioners` 读取）

### Q: 新旧格式可以同时存在吗？

A: 可以！代码支持混合配置。对于同一个 UID 类型，会优先使用旧格式。

### Q: 如何添加新的空调？

A: 在 Excel 文件中添加新空调的数据，重新运行 `modules/uid_read.py` 即可。

---

## 测试建议

```python
# 测试新格式的读写
def test_new_format():
    # 1. 测试数据写入
    test_data = {
        "佳力图KN10空调4-3-9": {
            "温度设定值": 25.0,
            "湿度设置值": 50.0
        }
    }
    
    uid_mapping, _ = get_measurements_tags_fields(uid_config, None, test_data)
    print(f"UID映射: {uid_mapping}")
    
    # 2. 测试数据读取
    df = reading_data_query(
        influxdb_config,
        uid_config,
        reading_data_client,
        query_range="-10m"
    )
    print(f"查询结果行数: {len(df)}")
    
    # 3. 测试空调信息提取
    uids, names = _get_air_conditioner_uids_and_names(uid_config)
    print(f"空调数量: {len(names)}")
    print(f"空调列表: {names[:5]}")  # 显示前5个
```

---

## 更新日期

2025-10-30

