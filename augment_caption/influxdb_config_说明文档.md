# InfluxDB 配置文件与使用指南

> 📘 **新手友好指南**：本文档详细介绍了项目中 InfluxDB 配置文件的结构、相关 Python 代码的功能，以及如何使用它们。适合 Python 和 InfluxDB 初学者阅读。

---

## 📑 目录

1. [项目概述](#1-项目概述)
2. [InfluxDB 基础知识](#2-influxdb-基础知识)
3. [配置文件详细说明](#3-配置文件详细说明)
4. [Python 代码详解](#4-python-代码详解)
5. [调用关系与数据流向](#5-调用关系与数据流向)
6. [完整使用示例](#6-完整使用示例)
7. [常见问题解答](#7-常见问题解答)

---

## 1. 项目概述

### 1.1 项目背景

本项目是一个**数据中心能耗优化系统**，主要功能包括：
- 从 InfluxDB 读取数据中心的遥测数据（温度、湿度、功率等）
- 将预测结果（温度预测、能耗预测、PUE预测）写入 InfluxDB
- 将优化控制指令（空调控制、压缩机控制等）写入 InfluxDB

### 1.2 核心配置文件

- **`configs/influxdb_read_write_config.yaml`**：定义数据读取和写入策略
- **`configs/utils_config.yaml`**：定义 InfluxDB 连接参数

### 1.3 核心 Python 模块

- **`utils/data_read_write.py`**：数据读写器（`DataCenterDataReader` 和 `DataCenterDataWriter`）
- **`utils/influxdb_wrapper.py`**：InfluxDB 客户端包装器（带自动重连功能）
- **`utils/critical_operation.py`**：关键操作保护（确保写入操作完成）

---

## 2. InfluxDB 基础知识

### 2.1 什么是 InfluxDB？

**InfluxDB** 是一个开源的时序数据库（Time Series Database），专门用于存储和查询时间序列数据。

**时间序列数据**：按时间顺序记录的数据点，例如：
- 每分钟的温度读数
- 每秒的 CPU 使用率
- 每小时的能耗数据

### 2.2 InfluxDB 核心概念

| 概念 | 说明 | 类比（关系型数据库） | 示例 |
|------|------|---------------------|------|
| **Database** | 数据库 | Database | `iot_origin_database` |
| **Measurement** | 测量值/表 | Table | `ac_a1_001_supply_temp`（空调送风温度） |
| **Field** | 字段（存储实际数值） | Column | `value: 25.5` |
| **Tag** | 标签（索引，用于快速查询） | Indexed Column | `device_type: AC` |
| **Timestamp** | 时间戳 | Primary Key | `2025-11-07 10:30:00` |

### 2.3 InfluxDB 查询语言（InfluxQL）

InfluxQL 类似于 SQL，但专为时序数据设计。

**示例查询**：
```sql
-- 查询最近 1 小时的空调送风温度
SELECT "value" 
FROM "ac_a1_001_supply_temp" 
WHERE time > now() - 1h
ORDER BY time ASC
```

**解释**：
- `SELECT "value"`：选择 `value` 字段
- `FROM "ac_a1_001_supply_temp"`：从 `ac_a1_001_supply_temp` 这个 measurement 中查询
- `WHERE time > now() - 1h`：时间范围为最近 1 小时
- `ORDER BY time ASC`：按时间升序排列

---

## 3. 配置文件详细说明

### 3.1 配置文件位置

```
configs/
├── influxdb_read_write_config.yaml  # 读写策略配置
└── utils_config.yaml                # 连接参数配置
```

### 3.2 `influxdb_read_write_config.yaml` 结构

配置文件分为三大部分：
1. **读取配置（`read`）**：定义如何从 InfluxDB 读取数据
2. **写入配置（`write`）**：定义如何向 InfluxDB 写入数据
3. **查询优化配置（`query_optimization`）**：定义查询优化策略

---

### 3.3 读取配置（`read`）详解

#### 3.3.1 全局默认配置（`read.default`）

```yaml
read:
  default:
    mode: "time_range"              # 数据量选择模式
    time_range:
      duration: 1                   # 时间范围（数值）
      unit: "h"                     # 时间单位
    last_n_points:
      count: 100                    # 读取最近 N 条数据
    default_field_key: "value"      # 默认字段名
```

**配置项说明**：

| 配置项 | 类型 | 可选值 | 说明 |
|--------|------|--------|------|
| `mode` | 字符串 | `"time_range"` 或 `"last_n_points"` | 数据读取模式 |
| `time_range.duration` | 整数 | 任意正整数 | 时间范围的数值部分 |
| `time_range.unit` | 字符串 | `"h"`（小时）、`"m"`（分钟）、`"d"`（天） | 时间单位 |
| `last_n_points.count` | 整数 | 任意正整数 | 读取最近 N 条数据 |
| `default_field_key` | 字符串 | 任意字符串 | InfluxDB 中的字段名，通常为 `"value"` |

**两种读取模式对比**：

| 模式 | 说明 | 适用场景 | 示例 |
|------|------|----------|------|
| `time_range` | 读取指定时间范围内的所有数据 | 需要分析一段时间内的趋势 | 读取最近 1 小时的温度数据 |
| `last_n_points` | 读取最近 N 条数据 | 只需要最新的几条数据 | 读取最近 100 条温度读数 |

#### 3.3.2 数据中心级别配置（`read.datacenter`）

```yaml
read:
  datacenter:
    enabled: true                   # 是否读取数据中心级别数据
    environment_sensors:
      enabled: true                 # 是否读取环境传感器数据
      sensors:
        - sensor_uid: "ENV_DC_TEMP_001"
          mode: "time_range"
          time_range:
            duration: 2
            unit: "h"
          field_key: "value"
```

**配置项说明**：

| 配置项 | 类型 | 说明 |
|--------|------|------|
| `enabled` | 布尔值 | `true` 表示启用，`false` 表示禁用 |
| `sensors` | 列表 | 为特定传感器指定不同的读取策略（可选） |
| `sensor_uid` | 字符串 | 传感器的唯一标识符 |

**注意**：如果不为特定传感器指定配置，将使用全局默认配置。

#### 3.3.3 机房级别配置（`read.computer_rooms`）

```yaml
read:
  computer_rooms:
    enabled: true                   # 全局机房读取开关
    rooms:
      - room_uid: "CR_A1"           # 机房唯一标识符
        enabled: true               # 是否读取该机房数据
        environment_sensors:
          enabled: true
        room_attributes:
          enabled: true
        air_cooled_systems:         # 风冷系统配置
          enabled: true
          systems:
            - system_uid: "ACAC_A1_001"
              enabled: true
              air_conditioners:     # 空调配置
                enabled: true
                devices:
                  - device_uid: "AC_A1_001"
                    enabled: true
                    attributes:
                      - attr_name: "空调送风温度"
                        field_key: "value"
```

**层级结构**：
```
数据中心（DataCenter）
└── 机房（ComputerRoom）
    ├── 环境传感器（EnvironmentSensor）
    ├── 机房属性（RoomAttributes）
    └── 空调系统（AirCooledSystem / WaterCooledSystem）
        └── 设备（Device）
            └── 属性（Attribute）
```

---

### 3.4 写入配置（`write`）详解

#### 3.4.1 预测数据写入配置（`write.prediction`）

```yaml
write:
  prediction:
    enabled: true                           # 是否启用预测数据写入
    database: "iot_origin_prediction"       # 目标数据库
    batch_size: 100                         # 批量写入大小
    retry_times: 3                          # 写入失败重试次数
    retry_interval: 2                       # 重试间隔（秒）
    retention_policy: "autogen"             # 数据保留策略
    data_types:
      - data_type: "temperature_prediction"
        enabled: true
        description: "机房温度预测数据"
```

**配置项说明**：

| 配置项 | 类型 | 说明 |
|--------|------|------|
| `database` | 字符串 | InfluxDB 数据库名称 |
| `batch_size` | 整数 | 每批写入的数据点数量（建议 50-500） |
| `retry_times` | 整数 | 写入失败后的重试次数 |
| `retry_interval` | 整数 | 重试间隔（秒） |
| `retention_policy` | 字符串 | InfluxDB 数据保留策略，`"autogen"` 表示永久保留 |

**Measurement 命名规则**：
- 温度预测：`{room_uid}_temp_pred_{horizon}`，例如 `CR_A1_temp_pred_1h`
- 能耗预测：`{room_uid}_energy_pred_{horizon}`，例如 `CR_A1_energy_pred_6h`
- PUE预测：`dc_pue_pred_{horizon}`，例如 `dc_pue_pred_24h`

#### 3.4.2 优化控制指令写入配置（`write.optimization`）

```yaml
write:
  optimization:
    enabled: true
    database: "iot_origin_optimization"
    batch_size: 50
    retry_times: 3
    retry_interval: 2
    retention_policy: "autogen"
    control_types:
      - control_type: "ac_control"
        enabled: true
        description: "空调控制指令"
```

**Measurement 命名规则**：
- 使用设备的控制属性 UID，例如：
  - `ac_a1_001_on_setpoint`（空调开机设定点）
  - `ac_a1_001_supply_temp_setpoint`（空调送风温度设定点）

---

### 3.5 查询优化配置（`query_optimization`）详解

```yaml
query_optimization:
  enable_cache: false               # 是否启用查询缓存
  cache_ttl: 60                     # 缓存过期时间（秒）
  enable_parallel_query: true       # 是否启用并行查询
  parallel_threads: 4               # 并行查询的线程数
  max_uids_per_query: 50            # 单次查询的最大 UID 数量
  query_timeout: 30                 # 查询超时时间（秒）
```

**配置项说明**：

| 配置项 | 类型 | 说明 | 建议值 |
|--------|------|------|--------|
| `enable_cache` | 布尔值 | 是否启用查询缓存（暂未实现） | `false` |
| `enable_parallel_query` | 布尔值 | 是否启用并行查询（暂未实现） | `true` |
| `max_uids_per_query` | 整数 | 单次查询的最大 UID 数量，超过则分批查询 | 50-100 |
| `query_timeout` | 整数 | 查询超时时间（秒） | 30-60 |

---

### 3.6 `utils_config.yaml` 连接配置

```yaml
InfluxDB:
  _common: &common_config
    host: "121.237.18.5"            # InfluxDB 服务器地址
    port: 8086                      # InfluxDB 端口
    username: "admin"               # 用户名
    password: "admin123"            # 密码

  influxdb_dc_status_data:          # 数据中心状态数据客户端（读取）
    <<: *common_config
    database: "iot_origin_database"

  influxdb_prediction_data:         # 预测数据客户端（读写）
    <<: *common_config
    database: "iot_origin_prediction"

  influxdb_optimization_data:       # 优化数据客户端（写入）
    <<: *common_config
    database: "iot_origin_optimization"
```

**YAML 锚点和别名**：
- `&common_config`：定义锚点，保存公共配置
- `<<: *common_config`：引用锚点，复用公共配置

---

## 4. Python 代码详解

### 4.1 模块概览

| 模块 | 文件路径 | 主要类/函数 | 功能 |
|------|----------|------------|------|
| 数据读写器 | `utils/data_read_write.py` | `DataCenterDataReader`<br>`DataCenterDataWriter` | 读取和写入数据 |
| InfluxDB 包装器 | `utils/influxdb_wrapper.py` | `InfluxDBClientWrapper` | 带自动重连的 InfluxDB 客户端 |
| 关键操作保护 | `utils/critical_operation.py` | `critical_operation` | 保护写入操作 |
| 架构模块 | `modules/architecture_module.py` | `DataCenter`<br>`ComputerRoom`<br>`Device` | 数据中心架构模型 |

---

### 4.2 `InfluxDBClientWrapper` 类详解

#### 4.2.1 类的作用

`InfluxDBClientWrapper` 是对 InfluxDB 官方客户端的封装，提供**自动重连功能**。

**为什么需要自动重连？**
- 网络可能会中断
- InfluxDB 服务器可能会重启
- 自动重连可以提高系统的健壮性

#### 4.2.2 初始化方法

```python
def __init__(
    self, 
    client_config: Dict,        # 客户端配置（host, port, username, password, database）
    reconnect_config: Dict,     # 重连配置（max_retries, retry_interval, timeout）
    logger: logging.Logger,     # 日志器
    client_name: str            # 客户端名称（用于日志标识）
):
```

**参数说明**：
- `client_config`：包含 `host`、`port`、`username`、`password`、`database`
- `reconnect_config`：包含 `max_retries`（最大重试次数）、`retry_interval`（重试间隔）、`timeout`（超时时间）
- `logger`：日志器对象
- `client_name`：客户端名称，例如 `"dc_status_data_client"`

#### 4.2.3 核心方法

**1. `query()` 方法**：执行查询操作

```python
def query(self, query_str: str, *args, **kwargs) -> Any:
    """
    执行查询操作，带自动重连功能
    
    参数:
        query_str: InfluxQL 查询语句
        *args, **kwargs: 传递给 InfluxDBClient.query() 的其他参数
    
    返回:
        查询结果（ResultSet 对象）
    
    异常:
        Exception: 查询失败且重连失败
    """
```

**工作流程**：
1. 尝试执行查询
2. 如果失败（网络错误、超时等），尝试重连
3. 重连成功后，重试查询
4. 如果重连失败，抛出异常

**2. `write_points()` 方法**：写入数据点

```python
def write_points(self, points: List[Dict], *args, **kwargs) -> bool:
    """
    写入数据点，带自动重连功能
    
    参数:
        points: 数据点列表，每个数据点是一个字典
        *args, **kwargs: 传递给 InfluxDBClient.write_points() 的其他参数
    
    返回:
        bool: 写入是否成功
    """
```

**数据点格式**：
```python
point = {
    'measurement': 'ac_a1_001_supply_temp',  # Measurement 名称
    'tags': {'device_type': 'AC'},           # 标签（可选）
    'fields': {'value': 25.5},               # 字段（必须）
    'time': 1699344600000000000              # 时间戳（纳秒级）
}
```

---

### 4.3 `DataCenterDataReader` 类详解

#### 4.3.1 类的作用

`DataCenterDataReader` 负责从 InfluxDB 批量读取数据中心的遥测数据。

**主要功能**：
- 根据配置文件读取数据
- 支持 `time_range` 和 `last_n_points` 两种模式
- 支持批量查询优化
- 返回 Pandas DataFrame 格式的数据

#### 4.3.2 初始化方法

```python
def __init__(
    self,
    datacenter: DataCenter,                 # DataCenter 对象
    read_config: Dict,                      # 读取配置（来自 influxdb_read_write_config.yaml）
    influxdb_client: InfluxDBClientWrapper  # InfluxDB 客户端
):
```

#### 4.3.3 核心方法

**1. `read_all_telemetry_data()` 方法**：读取所有遥测数据

```python
def read_all_telemetry_data(self) -> Dict[str, pd.DataFrame]:
    """
    读取所有遥测数据
    
    返回:
        Dict[str, pd.DataFrame]: uid -> DataFrame 的映射
            DataFrame 包含列: timestamp, value
    
    异常:
        Exception: 查询失败
    """
```

**返回值示例**：
```python
{
    'ac_a1_001_supply_temp': DataFrame([
        {'timestamp': '2025-11-07 10:00:00', 'value': 25.5},
        {'timestamp': '2025-11-07 10:01:00', 'value': 25.6},
        ...
    ]),
    'ac_a1_001_return_temp': DataFrame([...]),
    ...
}
```

**2. `read_room_data()` 方法**：读取指定机房的数据

```python
def read_room_data(self, room_uid: str) -> Dict[str, pd.DataFrame]:
    """
    读取指定机房的所有数据
    
    参数:
        room_uid: 机房唯一标识符，例如 "CR_A1"
    
    返回:
        Dict[str, pd.DataFrame]: uid -> DataFrame 的映射
    
    异常:
        ValueError: 机房不存在
    """
```

**3. `read_device_data()` 方法**：读取指定设备的数据

```python
def read_device_data(self, device_uid: str) -> Dict[str, pd.DataFrame]:
    """
    读取指定设备的所有数据
    
    参数:
        device_uid: 设备唯一标识符，例如 "AC_A1_001"
    
    返回:
        Dict[str, pd.DataFrame]: uid -> DataFrame 的映射
    
    异常:
        ValueError: 设备不存在
    """
```

#### 4.3.4 内部方法详解

**1. `_build_query()` 方法**：构建 InfluxQL 查询语句

```python
def _build_query(self, uid: str) -> str:
    """
    根据配置构建 InfluxDB 查询语句
    
    参数:
        uid: 属性唯一标识符
    
    返回:
        str: InfluxDB 查询语句
    """
```

**生成的查询示例**：

**time_range 模式**：
```sql
SELECT "value" AS value
FROM "ac_a1_001_supply_temp"
WHERE time > now() - 1h
ORDER BY time ASC
```

**last_n_points 模式**：
```sql
SELECT "value" AS value
FROM "ac_a1_001_supply_temp"
ORDER BY time DESC
LIMIT 100
```

**2. `_parse_query_result()` 方法**：解析查询结果

```python
def _parse_query_result(self, query_result: Any, uid: str) -> Optional[pd.DataFrame]:
    """
    解析查询结果并转换为 DataFrame
    
    参数:
        query_result: InfluxDB 查询结果（ResultSet 对象）
        uid: 属性唯一标识符
    
    返回:
        Optional[pd.DataFrame]: DataFrame 或 None（如果没有数据）
            DataFrame 包含列: timestamp, value
    """
```

**工作流程**：
1. 从 `ResultSet` 对象中提取数据点
2. 转换为 Pandas DataFrame
3. 重命名列（`time` -> `timestamp`）
4. 转换时间戳为 `datetime` 类型
5. 按时间排序

---

### 4.4 `DataCenterDataWriter` 类详解

#### 4.4.1 类的作用

`DataCenterDataWriter` 负责将预测数据和优化控制指令写入 InfluxDB。

**主要功能**：
- 批量写入预测数据
- 批量写入优化控制指令
- 实现批量写入和重试机制
- 使用 `critical_operation` 保护写入操作

#### 4.4.2 初始化方法

```python
def __init__(
    self,
    datacenter: DataCenter,                 # DataCenter 对象
    write_config: Dict,                     # 写入配置
    influxdb_client: InfluxDBClientWrapper, # InfluxDB 客户端
    ctx: Any                                # AppContext 对象（用于 critical_operation）
):
```

#### 4.4.3 核心方法

**1. `write_prediction_data()` 方法**：写入预测数据

```python
def write_prediction_data(
    self,
    prediction_data: Dict[str, Any],  # 预测数据字典
    data_type: str                    # 数据类型
) -> bool:
    """
    写入预测数据
    
    参数:
        prediction_data: 预测数据字典
            格式: {
                'room_uid': 'CR_A1',
                'horizon': '1h',
                'predictions': [
                    {'timestamp': datetime, 'value': float},
                    ...
                ]
            }
        data_type: 数据类型（如 "temperature_prediction"）
    
    返回:
        bool: 写入是否成功
    """
```

**预测数据格式示例**：
```python
prediction_data = {
    'room_uid': 'CR_A1',
    'horizon': '1h',
    'predictions': [
        {'timestamp': datetime(2025, 11, 7, 11, 0, 0), 'value': 25.5},
        {'timestamp': datetime(2025, 11, 7, 12, 0, 0), 'value': 25.8},
        {'timestamp': datetime(2025, 11, 7, 13, 0, 0), 'value': 26.0},
    ]
}
```

**2. `write_optimization_commands()` 方法**：写入优化控制指令

```python
def write_optimization_commands(
    self,
    control_commands: Dict[str, Any]  # 控制指令字典
) -> bool:
    """
    写入优化控制指令
    
    参数:
        control_commands: 控制指令字典
            格式: {
                'device_uid': 'AC_A1_001',
                'commands': [
                    {
                        'control_uid': 'ac_a1_001_on_setpoint',
                        'value': 25.0,
                        'timestamp': datetime
                    },
                    ...
                ]
            }
    
    返回:
        bool: 写入是否成功
    """
```

**控制指令格式示例**：
```python
control_commands = {
    'device_uid': 'AC_A1_001',
    'commands': [
        {
            'control_uid': 'ac_a1_001_supply_temp_setpoint',
            'value': 25.0,
            'timestamp': datetime.now()
        },
        {
            'control_uid': 'ac_a1_001_on_setpoint',
            'value': 1.0,  # 1 表示开机
            'timestamp': datetime.now()
        }
    ]
}
```

#### 4.4.4 内部方法详解

**1. `_build_point()` 方法**：构建 InfluxDB Point 对象

```python
def _build_point(
    self,
    measurement: str,                       # Measurement 名称
    fields: Dict[str, Any],                 # 字段字典
    tags: Optional[Dict[str, str]] = None,  # 标签字典（可选）
    timestamp: Optional[datetime] = None    # 时间戳（可选）
) -> Dict[str, Any]:
    """
    构建 InfluxDB Point 对象
    
    返回:
        Dict[str, Any]: Point 字典格式
            {
                'measurement': str,
                'tags': dict,
                'fields': dict,
                'time': int (纳秒级时间戳)
            }
    """
```

**Point 格式示例**：
```python
point = {
    'measurement': 'CR_A1_temp_pred_1h',
    'tags': {'data_type': 'temperature_prediction'},
    'fields': {'value': 25.5},
    'time': 1699344600000000000  # 纳秒级时间戳
}
```

**2. `_batch_write()` 方法**：批量写入数据

```python
def _batch_write(
    self,
    points: List[Dict[str, Any]],  # Point 列表
    database: str,                 # 目标数据库
    batch_size: int,               # 批量大小
    retry_times: int,              # 重试次数
    retry_interval: int            # 重试间隔（秒）
) -> bool:
    """
    批量写入数据到 InfluxDB
    
    返回:
        bool: 写入是否成功
    """
```

**工作流程**：
1. 将 `points` 列表分批（每批 `batch_size` 个）
2. 对每批数据调用 `_retry_write()` 方法
3. 如果任何一批失败，返回 `False`
4. 所有批次成功，返回 `True`

**3. `_retry_write()` 方法**：写入失败时自动重试

```python
def _retry_write(
    self,
    points: List[Dict[str, Any]],  # Point 列表
    database: str,                 # 目标数据库
    retry_times: int,              # 重试次数
    retry_interval: int            # 重试间隔（秒）
) -> bool:
    """
    写入失败时自动重试
    
    返回:
        bool: 写入是否成功
    """
```

**工作流程**：
1. 尝试写入数据
2. 如果失败，等待 `retry_interval` 秒后重试
3. 最多重试 `retry_times` 次
4. 如果所有重试都失败，返回 `False`

---

### 4.5 `critical_operation` 上下文管理器详解

#### 4.5.1 什么是上下文管理器？

**上下文管理器**是 Python 中的一种设计模式，用于管理资源的获取和释放。

**语法**：
```python
with context_manager as variable:
    # 执行操作
```

**常见示例**：
```python
# 文件操作
with open('file.txt', 'r') as f:
    content = f.read()
# 文件会自动关闭

# 数据库连接
with database.connect() as conn:
    conn.execute(query)
# 连接会自动关闭
```

#### 4.5.2 `critical_operation` 的作用

`critical_operation` 用于保护关键操作（如数据库写入、模型保存），确保这些操作在程序退出时能够完成。

**为什么需要保护？**
- 程序可能会被用户中断（Ctrl+C）
- 如果写入操作未完成就退出，可能导致数据损坏
- `critical_operation` 会记录正在执行的关键操作数量，主线程会等待所有关键操作完成后再退出

#### 4.5.3 使用方法

```python
from utils.critical_operation import critical_operation

# 保护数据库写入操作
with critical_operation(ctx):
    ctx.prediction_client.write_points(data)

# 保护模型保存操作
with critical_operation(ctx):
    model.save("checkpoint.pth")
```

#### 4.5.4 工作原理

```python
@contextmanager
def critical_operation(ctx: 'AppContext'):
    # 进入关键操作：增加计数器
    with ctx.critical_operation_lock:
        ctx.critical_operation_count += 1
    
    try:
        # 执行关键操作
        yield
    finally:
        # 退出关键操作：减少计数器
        with ctx.critical_operation_lock:
            ctx.critical_operation_count -= 1
```

**关键点**：
- 使用锁（`Lock`）保护计数器，确保线程安全
- 使用 `try...finally` 确保计数器一定会减少

---

### 4.6 便捷函数详解

#### 4.6.1 `load_read_write_config()` 函数

```python
def load_read_write_config(config_path: str) -> Dict:
    """
    加载 InfluxDB 读写配置文件
    
    参数:
        config_path: influxdb_read_write_config.yaml 配置文件的路径
    
    返回:
        Dict: 配置字典
    
    异常:
        FileNotFoundError: 配置文件不存在
        yaml.YAMLError: 配置文件格式错误
    
    示例:
        config = load_read_write_config("configs/influxdb_read_write_config.yaml")
        read_config = config['read']
        write_config = config['write']
    """
```

**实现**：
```python
def load_read_write_config(config_path: str) -> Dict:
    config_path = Path(config_path)
    
    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    return config
```

#### 4.6.2 `create_data_reader()` 函数

```python
def create_data_reader(
    datacenter: DataCenter,
    config_path: str,
    influxdb_client: InfluxDBClientWrapper
) -> DataCenterDataReader:
    """
    创建数据读取器（便捷函数）
    
    示例:
        reader = create_data_reader(datacenter, "configs/influxdb_read_write_config.yaml", client)
        data = reader.read_all_telemetry_data()
    """
    config = load_read_write_config(config_path)
    read_config = config.get('read', {})
    return DataCenterDataReader(datacenter, read_config, influxdb_client)
```

#### 4.6.3 `create_data_writer()` 函数

```python
def create_data_writer(
    datacenter: DataCenter,
    config_path: str,
    influxdb_client: InfluxDBClientWrapper,
    ctx: Any
) -> DataCenterDataWriter:
    """
    创建数据写入器（便捷函数）
    
    示例:
        writer = create_data_writer(datacenter, "configs/influxdb_read_write_config.yaml", client, ctx)
        writer.write_prediction_data(prediction_data, "temperature_prediction")
    """
    config = load_read_write_config(config_path)
    write_config = config.get('write', {})
    return DataCenterDataWriter(datacenter, write_config, influxdb_client, ctx)
```

---

## 5. 调用关系与数据流向

### 5.1 系统架构图

```
┌─────────────────────────────────────────────────────────────┐
│                         主程序 (main.py)                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ├─ 加载配置文件
                              │  ├─ utils_config.yaml
                              │  └─ influxdb_read_write_config.yaml
                              │
                              ├─ 初始化 InfluxDB 客户端
                              │  ├─ dc_status_client (读取)
                              │  ├─ prediction_client (读写)
                              │  └─ optimization_client (写入)
                              │
                              ├─ 创建数据读取器
                              │  └─ DataCenterDataReader
                              │
                              └─ 创建数据写入器
                                 └─ DataCenterDataWriter
```

### 5.2 数据读取流程

```
用户调用
    │
    ├─> reader.read_all_telemetry_data()
    │       │
    │       ├─> datacenter.get_all_observable_uids()  # 获取所有 UID
    │       │       │
    │       │       └─> 返回 ['ac_a1_001_supply_temp', 'ac_a1_001_return_temp', ...]
    │       │
    │       ├─> _batch_read_data(uids)  # 批量读取
    │       │       │
    │       │       ├─> _read_batch(batch_uids)  # 读取一批
    │       │       │       │
    │       │       │       ├─> _build_query(uid)  # 构建查询语句
    │       │       │       │       │
    │       │       │       │       └─> 返回 "SELECT value FROM uid WHERE time > now() - 1h"
    │       │       │       │
    │       │       │       ├─> influxdb_client.query(query)  # 执行查询
    │       │       │       │       │
    │       │       │       │       └─> 返回 ResultSet 对象
    │       │       │       │
    │       │       │       └─> _parse_query_result(result, uid)  # 解析结果
    │       │       │               │
    │       │       │               └─> 返回 DataFrame([{'timestamp': ..., 'value': ...}])
    │       │       │
    │       │       └─> 返回 {uid: DataFrame, ...}
    │       │
    │       └─> 返回 {uid: DataFrame, ...}
    │
    └─> 用户获得数据
```

### 5.3 数据写入流程

```
用户调用
    │
    ├─> writer.write_prediction_data(prediction_data, data_type)
    │       │
    │       ├─> 验证数据格式
    │       │
    │       ├─> 构建 measurement 名称
    │       │   例如: "CR_A1_temp_pred_1h"
    │       │
    │       ├─> 构建 Points
    │       │   ├─> _build_point(measurement, fields, tags, timestamp)
    │       │   │       │
    │       │   │       └─> 返回 {'measurement': ..., 'fields': ..., 'tags': ..., 'time': ...}
    │       │   │
    │       │   └─> 返回 [point1, point2, ...]
    │       │
    │       ├─> with critical_operation(ctx):  # 保护写入操作
    │       │       │
    │       │       └─> _batch_write(points, database, batch_size, retry_times, retry_interval)
    │       │               │
    │       │               ├─> 分批（每批 batch_size 个）
    │       │               │
    │       │               ├─> _retry_write(batch, database, retry_times, retry_interval)
    │       │               │       │
    │       │               │       ├─> influxdb_client.write_points(batch, database)
    │       │               │       │       │
    │       │               │       │       └─> 写入成功 / 失败
    │       │               │       │
    │       │               │       └─> 如果失败，重试
    │       │               │
    │       │               └─> 返回 True / False
    │       │
    │       └─> 返回 True / False
    │
    └─> 用户获得写入结果
```

### 5.4 配置文件与代码的关联关系

```
influxdb_read_write_config.yaml
    │
    ├─ read.default.mode ──────────────> DataCenterDataReader.default_mode
    ├─ read.default.time_range ────────> DataCenterDataReader.default_time_range
    ├─ read.default.last_n_points ─────> DataCenterDataReader.default_last_n
    ├─ read.default.default_field_key ─> DataCenterDataReader.default_field_key
    │
    ├─ write.prediction.enabled ───────> DataCenterDataWriter.prediction_enabled
    ├─ write.prediction.database ──────> DataCenterDataWriter.prediction_database
    ├─ write.prediction.batch_size ────> DataCenterDataWriter.prediction_batch_size
    ├─ write.prediction.retry_times ───> DataCenterDataWriter.prediction_retry_times
    │
    └─ query_optimization.max_uids_per_query ─> DataCenterDataReader.max_uids_per_query
```

---

## 6. 完整使用示例

### 6.1 读取数据示例

```python
from pathlib import Path
from utils.data_read_write import create_data_reader
from utils.influxdb_wrapper import InfluxDBClientWrapper
from modules.architecture_module import DataCenter
import yaml

# 1. 加载配置
with open('configs/utils_config.yaml', 'r', encoding='utf-8') as f:
    utils_config = yaml.safe_load(f)

# 2. 初始化 InfluxDB 客户端
client_config = utils_config['InfluxDB']['influxdb_dc_status_data']
reconnect_config = utils_config['InfluxDB'].get('influxdb_reconnect', {})

dc_status_client = InfluxDBClientWrapper(
    client_config=client_config,
    reconnect_config=reconnect_config,
    logger=logger,
    client_name="dc_status_data_client"
)

# 3. 创建 DataCenter 对象（假设已经创建）
datacenter = DataCenter(dc_name="示例数据中心", dc_uid="DC_001")
# ... 添加机房、设备等 ...

# 4. 创建数据读取器
reader = create_data_reader(
    datacenter=datacenter,
    config_path="configs/influxdb_read_write_config.yaml",
    influxdb_client=dc_status_client
)

# 5. 读取所有遥测数据
all_data = reader.read_all_telemetry_data()

# 6. 处理数据
for uid, df in all_data.items():
    print(f"UID: {uid}")
    print(f"数据点数量: {len(df)}")
    print(f"最新值: {df.iloc[-1]['value']}")
    print(f"时间范围: {df.iloc[0]['timestamp']} ~ {df.iloc[-1]['timestamp']}")
    print("-" * 50)

# 7. 读取指定机房的数据
room_data = reader.read_room_data(room_uid="CR_A1")

# 8. 读取指定设备的数据
device_data = reader.read_device_data(device_uid="AC_A1_001")
```

### 6.2 写入预测数据示例

```python
from datetime import datetime, timedelta
from utils.data_read_write import create_data_writer

# 1. 创建数据写入器
writer = create_data_writer(
    datacenter=datacenter,
    config_path="configs/influxdb_read_write_config.yaml",
    influxdb_client=prediction_client,
    ctx=ctx  # AppContext 对象
)

# 2. 准备预测数据
prediction_data = {
    'room_uid': 'CR_A1',
    'horizon': '1h',
    'predictions': []
}

# 生成未来 24 小时的预测数据
base_time = datetime.now()
for i in range(24):
    prediction_data['predictions'].append({
        'timestamp': base_time + timedelta(hours=i),
        'value': 25.0 + i * 0.1  # 模拟温度逐渐上升
    })

# 3. 写入预测数据
success = writer.write_prediction_data(
    prediction_data=prediction_data,
    data_type="temperature_prediction"
)

if success:
    print("预测数据写入成功！")
else:
    print("预测数据写入失败！")
```

### 6.3 写入优化控制指令示例

```python
from datetime import datetime

# 1. 准备控制指令
control_commands = {
    'device_uid': 'AC_A1_001',
    'commands': [
        {
            'control_uid': 'ac_a1_001_supply_temp_setpoint',
            'value': 25.0,
            'timestamp': datetime.now()
        },
        {
            'control_uid': 'ac_a1_001_on_setpoint',
            'value': 1.0,  # 1 表示开机
            'timestamp': datetime.now()
        }
    ]
}

# 2. 写入控制指令
success = writer.write_optimization_commands(control_commands)

if success:
    print("控制指令写入成功！")
else:
    print("控制指令写入失败！")
```

---

## 7. 常见问题解答

### 7.1 配置相关问题

**Q1: 如何修改读取的时间范围？**

A: 修改 `influxdb_read_write_config.yaml` 中的 `read.default.time_range`：

```yaml
read:
  default:
    time_range:
      duration: 2  # 改为 2 小时
      unit: "h"
```

**Q2: 如何切换到 `last_n_points` 模式？**

A: 修改 `read.default.mode`：

```yaml
read:
  default:
    mode: "last_n_points"  # 改为 last_n_points 模式
    last_n_points:
      count: 200  # 读取最近 200 条数据
```

**Q3: 如何为特定设备指定不同的读取策略？**

A: 在配置文件中为该设备添加配置：

```yaml
read:
  computer_rooms:
    rooms:
      - room_uid: "CR_A1"
        air_cooled_systems:
          systems:
            - system_uid: "ACAC_A1_001"
              air_conditioners:
                devices:
                  - device_uid: "AC_A1_001"
                    enabled: true
                    mode: "last_n_points"  # 为该设备指定模式
                    last_n_points:
                      count: 500
```

### 7.2 代码使用问题

**Q4: 如何处理读取失败的情况？**

A: 使用 `try...except` 捕获异常：

```python
try:
    all_data = reader.read_all_telemetry_data()
except Exception as e:
    logger.error(f"读取数据失败: {e}")
    # 处理失败情况
```

**Q5: 如何判断某个 UID 是否有数据？**

A: 检查返回的字典中是否包含该 UID：

```python
all_data = reader.read_all_telemetry_data()

if 'ac_a1_001_supply_temp' in all_data:
    df = all_data['ac_a1_001_supply_temp']
    print(f"数据点数量: {len(df)}")
else:
    print("该 UID 没有数据")
```

**Q6: 如何处理 DataFrame 中的缺失值？**

A: 使用 Pandas 的方法：

```python
import pandas as pd

df = all_data['ac_a1_001_supply_temp']

# 检查缺失值
print(df.isnull().sum())

# 删除缺失值
df = df.dropna()

# 填充缺失值
df = df.fillna(method='ffill')  # 前向填充
```

### 7.3 InfluxDB 相关问题

**Q7: 什么是 Measurement？**

A: Measurement 类似于关系型数据库中的表，用于存储同一类型的数据。在本项目中，每个属性的 UID 对应一个 Measurement。

**Q8: 什么是 Field 和 Tag？**

A: 
- **Field**：存储实际的数值，例如温度值 `25.5`
- **Tag**：存储元数据，用于索引和快速查询，例如 `device_type: AC`

**Q9: 为什么时间戳是纳秒级的？**

A: InfluxDB 内部使用纳秒级时间戳，以支持高精度的时间序列数据。

**Q10: 如何在 InfluxDB 中查看写入的数据？**

A: 使用 InfluxDB 的命令行工具或 Web UI：

```bash
# 连接到 InfluxDB
influx -host 121.237.18.5 -port 8086 -username admin -password admin123

# 切换到数据库
USE iot_origin_prediction

# 查询数据
SELECT * FROM "CR_A1_temp_pred_1h" LIMIT 10
```

### 7.4 性能优化问题

**Q11: 如何提高读取性能？**

A: 
1. 减少读取的时间范围
2. 增加 `max_uids_per_query` 的值（但不要太大，避免查询超时）
3. 使用 `last_n_points` 模式（如果只需要最新数据）

**Q12: 如何提高写入性能？**

A: 
1. 增加 `batch_size` 的值（建议 100-500）
2. 减少 `retry_times` 和 `retry_interval`（如果网络稳定）
3. 使用批量写入而不是逐条写入

### 7.5 错误处理问题

**Q13: 遇到 "连接超时" 错误怎么办？**

A: 
1. 检查网络连接
2. 检查 InfluxDB 服务器是否运行
3. 增加 `timeout` 配置：

```yaml
InfluxDB:
  influxdb_reconnect:
    timeout: 30  # 增加超时时间
```

**Q14: 遇到 "数据库不存在" 错误怎么办？**

A: 
1. 检查数据库名称是否正确
2. 在 InfluxDB 中创建数据库：

```bash
influx -host 121.237.18.5 -port 8086 -username admin -password admin123
CREATE DATABASE iot_origin_prediction
```

**Q15: 遇到 "认证失败" 错误怎么办？**

A: 
1. 检查用户名和密码是否正确
2. 检查用户是否有权限访问该数据库

---

## 8. 总结

本文档详细介绍了项目中 InfluxDB 配置文件和相关 Python 代码的使用方法。主要内容包括：

1. **InfluxDB 基础知识**：了解时序数据库的核心概念
2. **配置文件详解**：掌握读取和写入策略的配置方法
3. **Python 代码详解**：理解数据读写器的实现原理
4. **调用关系与数据流向**：了解系统的整体架构
5. **完整使用示例**：学习如何在实际项目中使用
6. **常见问题解答**：解决使用过程中的常见问题

希望本文档能帮助你快速上手 InfluxDB 和相关 Python 代码！

---

**文档版本**：v1.0  
**最后更新**：2025-11-07  
**作者**：Augment Agent

