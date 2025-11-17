# data_read_write.py 详细说明文档

## 📋 目录

1. [文件概述](#文件概述)
2. [导入模块详解](#导入模块详解)
3. [全局变量](#全局变量)
4. [类详解](#类详解)
   - [DataCenterDataReader 类](#datacenteratareader-类)
   - [DataCenterDataWriter 类](#datacenterdatawriter-类)
5. [便捷函数](#便捷函数)
6. [依赖关系分析](#依赖关系分析)
7. [使用示例](#使用示例)
8. [Python 语法和函数详解](#python-语法和函数详解)

---

## 文件概述

### 主要功能

`utils/data_read_write.py` 是数据中心数据读写器模块，负责从 InfluxDB 数据库读取数据和向 InfluxDB 数据库写入数据。

**核心功能：**
1. **数据读取**：从 InfluxDB 批量读取遥测数据（如温度、湿度、功耗等）
2. **数据写入**：向 InfluxDB 批量写入预测数据和优化控制指令

### 文件组成

该文件包含以下组成部分：

| 类型 | 名称 | 说明 |
|------|------|------|
| **类** | `DataCenterDataReader` | 数据读取器，从 InfluxDB 读取遥测数据 |
| **类** | `DataCenterDataWriter` | 数据写入器，向 InfluxDB 写入预测和控制数据 |
| **函数** | `load_read_write_config()` | 加载读写配置文件 |
| **函数** | `create_data_reader()` | 创建数据读取器的便捷函数 |
| **函数** | `create_data_writer()` | 创建数据写入器的便捷函数 |
| **全局变量** | `logger` | 日志记录器 |

---

## 导入模块详解

### 标准库模块

```python
import logging
```
**作用**：Python 的日志记录模块，用于记录程序运行时的信息、警告和错误。

**示例**：
```python
logger = logging.getLogger(__name__)
logger.info("这是一条信息日志")
logger.warning("这是一条警告日志")
logger.error("这是一条错误日志")
```

---

```python
import yaml
```
**作用**：用于读取和解析 YAML 格式的配置文件。YAML 是一种人类可读的数据序列化格式。

**示例**：
```python
# 读取 YAML 文件
with open('config.yaml', 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)
    
# config 是一个 Python 字典
print(config['database']['host'])  # 访问配置项
```

---

```python
import time
```
**作用**：提供时间相关的函数，如获取当前时间、暂停程序执行等。

**示例**：
```python
import time

# 暂停 2 秒
time.sleep(2)

# 获取当前时间戳（秒）
timestamp = time.time()
print(timestamp)  # 输出：1699123456.789
```

---

```python
import pandas as pd
```
**作用**：Pandas 是 Python 中最强大的数据分析库，提供 DataFrame 数据结构用于处理表格数据。

**什么是 DataFrame？**
DataFrame 是一个二维表格数据结构，类似于 Excel 表格，有行和列。

**示例**：
```python
import pandas as pd

# 创建一个 DataFrame
data = {
    'timestamp': ['2024-01-01 10:00:00', '2024-01-01 10:01:00'],
    'value': [25.5, 26.0]
}
df = pd.DataFrame(data)

print(df)
# 输出：
#             timestamp  value
# 0  2024-01-01 10:00:00   25.5
# 1  2024-01-01 10:01:00   26.0

# 访问列
print(df['value'])  # 输出：[25.5, 26.0]

# 访问行
print(df.iloc[0])  # 输出第一行
```

---

```python
from pathlib import Path
```
**作用**：提供面向对象的文件路径操作，比传统的 `os.path` 更简洁易用。

**示例**：
```python
from pathlib import Path

# 创建路径对象
config_path = Path("configs/influxdb_config.yaml")

# 检查文件是否存在
if config_path.exists():
    print("文件存在")
    
# 获取文件名
print(config_path.name)  # 输出：influxdb_config.yaml

# 获取父目录
print(config_path.parent)  # 输出：configs
```

---

```python
from typing import Dict, List, Any, Optional, Tuple
```
**作用**：提供类型提示（Type Hints），让代码更易读、更易维护。

**类型提示详解**：

| 类型 | 说明 | 示例 |
|------|------|------|
| `Dict` | 字典类型 | `Dict[str, int]` 表示键是字符串、值是整数的字典 |
| `List` | 列表类型 | `List[str]` 表示字符串列表 |
| `Any` | 任意类型 | 可以是任何类型的值 |
| `Optional` | 可选类型 | `Optional[str]` 表示可以是字符串或 None |
| `Tuple` | 元组类型 | `Tuple[int, str]` 表示包含整数和字符串的元组 |

**示例**：
```python
from typing import Dict, List, Optional

# 函数参数和返回值的类型提示
def get_user_info(user_id: int) -> Dict[str, str]:
    """
    参数 user_id 是整数类型
    返回值是字典，键和值都是字符串
    """
    return {"name": "张三", "email": "zhangsan@example.com"}

# Optional 表示可以是 None
def find_user(name: str) -> Optional[Dict[str, str]]:
    """
    返回值可以是字典，也可以是 None（找不到用户时）
    """
    if name == "张三":
        return {"name": "张三", "age": "25"}
    else:
        return None  # 找不到用户
```

---

```python
from datetime import datetime, timedelta
```
**作用**：处理日期和时间。

**datetime 详解**：
- `datetime`：表示一个具体的日期和时间
- `timedelta`：表示时间间隔（时间差）

**示例**：
```python
from datetime import datetime, timedelta

# 获取当前时间
now = datetime.now()
print(now)  # 输出：2024-01-01 10:30:45.123456

# 创建指定时间
dt = datetime(2024, 1, 1, 10, 30, 0)  # 2024年1月1日 10:30:00

# 时间运算
one_hour_later = now + timedelta(hours=1)  # 1小时后
one_day_ago = now - timedelta(days=1)      # 1天前

# 时间格式化
time_str = now.strftime("%Y-%m-%d %H:%M:%S")
print(time_str)  # 输出：2024-01-01 10:30:45

# 时间戳转换
timestamp = now.timestamp()  # 转换为时间戳（秒）
print(timestamp)  # 输出：1704096645.123456
```

---

### 项目内部模块

```python
from modules.architecture_module import DataCenter, ComputerRoom, Device, Attribute
```
**作用**：导入数据中心架构相关的类。

- `DataCenter`：数据中心类，表示整个数据中心
- `ComputerRoom`：机房类，表示数据中心中的一个机房
- `Device`：设备类，表示机房中的设备（如空调、服务器等）
- `Attribute`：属性类，表示设备的属性（如温度、功耗等）

**详细说明**：请参考 `augment_caption/architecture_module_详细说明.md`

---

```python
from utils.influxdb_wrapper import InfluxDBClientWrapper
```
**作用**：导入 InfluxDB 客户端包装器，用于连接和操作 InfluxDB 数据库。

**InfluxDB 是什么？**
InfluxDB 是一个时序数据库（Time Series Database），专门用于存储和查询时间序列数据（如传感器数据、监控数据等）。

**InfluxDBClientWrapper 主要方法**：
- `query(query_str)`：执行查询操作
- `write_points(points)`：写入数据点
- `close()`：关闭连接

---

```python
from utils.critical_operation import critical_operation
```
**作用**：导入关键操作保护上下文管理器，用于保护重要操作（如数据库写入）。

**什么是上下文管理器？**
上下文管理器是 Python 中使用 `with` 语句的对象，可以在代码块执行前后自动执行一些操作。

**示例**：
```python
from utils.critical_operation import critical_operation

# 使用 with 语句保护关键操作
with critical_operation(ctx):
    # 这里的代码是关键操作
    # 在执行前会增加计数器，执行后会减少计数器
    # 确保程序退出时等待所有关键操作完成
    influxdb_client.write_points(data)
```

**为什么需要 critical_operation？**
在多线程环境中，程序退出时可能有些操作还没完成（如数据还没写入数据库）。使用 `critical_operation` 可以确保程序等待这些重要操作完成后再退出。

---

## 全局变量

```python
logger = logging.getLogger(__name__)
```

**说明**：
- `logger` 是一个日志记录器对象
- `__name__` 是 Python 的特殊变量，表示当前模块的名称
- 在这个文件中，`__name__` 的值是 `"utils.data_read_write"`

**作用**：
用于记录该模块的日志信息，方便调试和追踪程序运行状态。

**使用示例**：
```python
logger.info("开始读取数据...")
logger.warning("数据为空")
logger.error("读取失败")
```

---

## 类详解

### DataCenterDataReader 类

#### 类的作用

`DataCenterDataReader` 是数据读取器类，负责从 InfluxDB 数据库批量读取遥测数据。

**主要功能**：
1. 支持两种读取模式：
   - `time_range`：读取指定时间范围内的数据（如最近1小时）
   - `last_n_points`：读取最近的 N 个数据点（如最近100个点）
2. 支持批量查询优化（避免一次查询太多数据导致超时）
3. 支持读取整个数据中心、单个机房或单个设备的数据

#### 类的属性

| 属性名 | 类型 | 说明 |
|--------|------|------|
| `datacenter` | `DataCenter` | 数据中心对象 |
| `read_config` | `Dict` | 读取配置字典 |
| `influxdb_client` | `InfluxDBClientWrapper` | InfluxDB 客户端 |
| `default_mode` | `str` | 默认读取模式（'time_range' 或 'last_n_points'） |
| `default_field_key` | `str` | 默认字段键（通常是 'value'） |
| `default_time_range` | `Dict` | 默认时间范围配置 |
| `default_last_n` | `Dict` | 默认最近 N 点配置 |
| `enable_parallel_query` | `bool` | 是否启用并行查询 |
| `max_uids_per_query` | `int` | 每次查询的最大 UID 数量 |
| `query_timeout` | `int` | 查询超时时间（秒） |

#### 构造方法 `__init__()`

```python
def __init__(
    self,
    datacenter: DataCenter,
    read_config: Dict,
    influxdb_client: InfluxDBClientWrapper
):
```

**参数说明**：

| 参数名 | 类型 | 说明 |
|--------|------|------|
| `datacenter` | `DataCenter` | 数据中心对象，包含所有机房和设备信息 |
| `read_config` | `Dict` | 读取配置字典，来自配置文件的 `read` 部分 |
| `influxdb_client` | `InfluxDBClientWrapper` | InfluxDB 客户端包装器 |

**执行流程**：
1. 保存传入的参数到实例属性
2. 从配置中读取默认设置（读取模式、字段键等）
3. 从配置中读取查询优化设置
4. 记录初始化日志

**配置文件示例**（`influxdb_read_write_config.yaml`）：
```yaml
read:
  default:
    mode: time_range  # 或 last_n_points
    default_field_key: value
    time_range:
      duration: 1
      unit: h  # h=小时, m=分钟, d=天
    last_n_points:
      count: 100

  query_optimization:
    enable_parallel_query: true
    max_uids_per_query: 50
    query_timeout: 30
```

#### 公共方法

##### 1. `read_all_observable_data()` - 读取所有遥测数据

```python
def read_all_observable_data(self) -> Dict[str, pd.DataFrame]:
```

**作用**：读取数据中心所有遥测点的数据。

**参数**：无

**返回值**：
- 类型：`Dict[str, pd.DataFrame]`
- 格式：`{uid: DataFrame}` 的字典
- DataFrame 包含两列：
  - `timestamp`：时间戳（datetime 类型）
  - `value`：数值（float 类型）

**执行流程**：
1. 调用 `datacenter.get_all_observable_uids()` 获取所有遥测点的 UID 列表
2. 调用 `_batch_read_data()` 批量读取数据
3. 返回结果字典

**使用示例**：

```python
# 读取所有遥测数据
data = reader.read_all_observable_data()

# 遍历结果
for uid, df in data.items():
    print(f"UID: {uid}")
    print(f"数据点数量: {len(df)}")
    print(df.head())  # 显示前5行

# 输出示例：
# UID: ac_a1_001_temp
# 数据点数量: 120
#              timestamp  value
# 0  2024-01-01 10:00:00   25.5
# 1  2024-01-01 10:01:00   25.6
# 2  2024-01-01 10:02:00   25.7
```

**异常**：
- `Exception`：查询失败时抛出

---

##### 2. `read_room_data()` - 读取指定机房的数据

```python
def read_room_data(self, room_uid: str) -> Dict[str, pd.DataFrame]:
```

**作用**：读取指定机房的所有遥测数据。

**参数**：
- `room_uid`（str）：机房的唯一标识符，如 `"CR_A1"`

**返回值**：
- 类型：`Dict[str, pd.DataFrame]`
- 格式：与 `read_all_observable_data()` 相同

**执行流程**：
1. 调用 `datacenter.get_room_by_uid(room_uid)` 获取机房对象
2. 如果机房不存在，抛出 `ValueError` 异常
3. 调用 `room.get_all_observable_uids()` 获取机房的所有遥测 UID
4. 调用 `_batch_read_data()` 批量读取数据
5. 返回结果字典

**使用示例**：
```python
# 读取机房 CR_A1 的数据
room_data = reader.read_room_data("CR_A1")

# 检查是否有数据
if room_data:
    print(f"成功读取 {len(room_data)} 个遥测点的数据")
else:
    print("没有读取到数据")
```

**异常**：
- `ValueError`：机房不存在时抛出

---

##### 3. `read_device_data()` - 读取指定设备的数据

```python
def read_device_data(self, device_uid: str) -> Dict[str, pd.DataFrame]:
```

**作用**：读取指定设备的所有遥测数据。

**参数**：
- `device_uid`（str）：设备的唯一标识符，如 `"AC_A1_001"`

**返回值**：
- 类型：`Dict[str, pd.DataFrame]`
- 格式：与 `read_all_observable_data()` 相同

**执行流程**：
1. 调用 `datacenter.get_device_by_uid(device_uid)` 获取设备对象
2. 如果设备不存在，抛出 `ValueError` 异常
3. 调用 `device.get_observable_uids()` 获取设备的所有可观测属性 UID
4. 调用 `_batch_read_data()` 批量读取数据
5. 返回结果字典

**使用示例**：
```python
# 读取空调设备 AC_A1_001 的数据
device_data = reader.read_device_data("AC_A1_001")

# 访问特定属性的数据
if "ac_a1_001_temp" in device_data:
    temp_df = device_data["ac_a1_001_temp"]
    print(f"温度数据：{len(temp_df)} 个点")
    print(f"最新温度：{temp_df.iloc[-1]['value']}°C")
```

**异常**：
- `ValueError`：设备不存在时抛出

---

#### 私有方法（内部使用）

##### 1. `_batch_read_data()` - 批量读取数据

```python
def _batch_read_data(self, uids: List[str]) -> Dict[str, pd.DataFrame]:
```

**作用**：批量读取多个 UID 的数据，支持分批查询优化。

**参数**：
- `uids`（List[str]）：UID 列表

**返回值**：
- 类型：`Dict[str, pd.DataFrame]`

**执行流程**：
1. 检查 UID 数量是否超过 `max_uids_per_query`
2. 如果超过，将 UID 列表分成多个批次
3. 对每个批次调用 `_read_batch()` 读取数据
4. 合并所有批次的结果并返回

**分批逻辑示例**：
```python
# 假设有 150 个 UID，max_uids_per_query = 50
# 会分成 3 个批次：
# 批次 1: UID[0:50]   (50 个)
# 批次 2: UID[50:100] (50 个)
# 批次 3: UID[100:150](50 个)
```

---

##### 2. `_read_batch()` - 读取一批数据

```python
def _read_batch(self, uids: List[str]) -> Dict[str, pd.DataFrame]:
```

**作用**：读取一批 UID 的数据（不分批）。

**执行流程**：
1. 遍历每个 UID
2. 调用 `_build_query(uid)` 构建查询语句
3. 调用 `influxdb_client.query()` 执行查询
4. 调用 `_parse_query_result()` 解析查询结果
5. 将有效数据添加到结果字典

---

##### 3. `_build_query()` - 构建查询语句

```python
def _build_query(self, uid: str) -> str:
```

**作用**：根据配置构建 InfluxDB 查询语句。

**参数**：
- `uid`（str）：属性的唯一标识符

**返回值**：
- 类型：`str`
- 内容：InfluxDB 查询语句

**查询语句示例**：

**time_range 模式**（读取最近1小时的数据）：
```sql
SELECT "value" AS value
FROM "ac_a1_001_temp"
WHERE time > now() - 1h
ORDER BY time ASC
```

**last_n_points 模式**（读取最近100个点）：
```sql
SELECT "value" AS value
FROM "ac_a1_001_temp"
ORDER BY time DESC
LIMIT 100
```

**InfluxDB 查询语言（InfluxQL）简介**：
- `SELECT`：选择要查询的字段
- `FROM`：指定 measurement（类似于表名）
- `WHERE`：过滤条件
- `ORDER BY`：排序
- `LIMIT`：限制返回的数据点数量
- `now()`：当前时间
- `1h`：1小时（也可以是 `1m`=1分钟，`1d`=1天）

---

##### 4. `_parse_query_result()` - 解析查询结果

```python
def _parse_query_result(self, query_result: Any, uid: str) -> Optional[pd.DataFrame]:
```

**作用**：将 InfluxDB 查询结果转换为 Pandas DataFrame。

**参数**：
- `query_result`（Any）：InfluxDB 查询结果对象
- `uid`（str）：属性的唯一标识符

**返回值**：
- 类型：`Optional[pd.DataFrame]`
- 如果有数据，返回 DataFrame
- 如果没有数据，返回 `None`

**执行流程**：
1. 检查查询结果是否为空
2. 调用 `query_result.get_points(measurement=uid)` 获取数据点
3. 将数据点列表转换为 DataFrame
4. 重命名列（`time` → `timestamp`）
5. 转换时间戳为 datetime 类型
6. 只保留 `timestamp` 和 `value` 列
7. 按时间排序并重置索引
8. 返回 DataFrame

**转换示例**：
```python
# InfluxDB 查询结果（原始格式）
[
    {'time': '2024-01-01T10:00:00Z', 'value': 25.5},
    {'time': '2024-01-01T10:01:00Z', 'value': 25.6}
]

# 转换后的 DataFrame
#              timestamp  value
# 0  2024-01-01 10:00:00   25.5
# 1  2024-01-01 10:01:00   25.6
```

---

### DataCenterDataWriter 类

#### 类的作用

`DataCenterDataWriter` 是数据写入器类，负责向 InfluxDB 数据库批量写入预测数据和优化控制指令。

**主要功能**：
1. 写入预测数据（如温度预测、能耗预测、PUE 预测）
2. 写入优化控制指令（如空调温度设定值）
3. 实现批量写入和重试机制
4. 使用 `critical_operation` 保护写入操作（线程安全）

#### 类的属性

| 属性名 | 类型 | 说明 |
|--------|------|------|
| `datacenter` | `DataCenter` | 数据中心对象 |
| `write_config` | `Dict` | 写入配置字典 |
| `influxdb_client` | `InfluxDBClientWrapper` | InfluxDB 客户端 |
| `ctx` | `Any` | AppContext 对象（用于 critical_operation） |
| `prediction_config` | `Dict` | 预测数据写入配置 |
| `prediction_enabled` | `bool` | 是否启用预测数据写入 |
| `prediction_database` | `str` | 预测数据库名称 |
| `prediction_batch_size` | `int` | 预测数据批量大小 |
| `prediction_retry_times` | `int` | 预测数据重试次数 |
| `prediction_retry_interval` | `int` | 预测数据重试间隔（秒） |
| `prediction_retention_policy` | `str` | 预测数据保留策略 |
| `optimization_config` | `Dict` | 优化控制配置 |
| `optimization_enabled` | `bool` | 是否启用优化控制写入 |
| `optimization_database` | `str` | 优化数据库名称 |
| `optimization_batch_size` | `int` | 优化数据批量大小 |
| `optimization_retry_times` | `int` | 优化数据重试次数 |
| `optimization_retry_interval` | `int` | 优化数据重试间隔（秒） |
| `optimization_retention_policy` | `str` | 优化数据保留策略 |

#### 构造方法 `__init__()`

```python
def __init__(
    self,
    datacenter: DataCenter,
    write_config: Dict,
    influxdb_client: InfluxDBClientWrapper,
    ctx: Any
):
```

**参数说明**：

| 参数名 | 类型 | 说明 |
|--------|------|------|
| `datacenter` | `DataCenter` | 数据中心对象 |
| `write_config` | `Dict` | 写入配置字典，来自配置文件的 `write` 部分 |
| `influxdb_client` | `InfluxDBClientWrapper` | InfluxDB 客户端包装器 |
| `ctx` | `Any` | AppContext 对象（用于 critical_operation） |

**执行流程**：
1. 保存传入的参数到实例属性
2. 解析预测数据写入配置
3. 解析优化控制指令写入配置
4. 记录初始化日志

**配置文件示例**（`influxdb_read_write_config.yaml`）：
```yaml
write:
  prediction:
    enabled: true
    database: iot_origin_prediction
    batch_size: 100
    retry_times: 3
    retry_interval: 2
    retention_policy: autogen

  optimization:
    enabled: true
    database: iot_origin_optimization
    batch_size: 50
    retry_times: 3
    retry_interval: 2
    retention_policy: autogen
```

#### 公共方法

##### 1. `write_prediction_data()` - 写入预测数据

```python
def write_prediction_data(
    self,
    prediction_data: Dict[str, Any],
    data_type: str
) -> bool:
```

**作用**：写入预测数据到 InfluxDB。

**参数**：

| 参数名 | 类型 | 说明 |
|--------|------|------|
| `prediction_data` | `Dict[str, Any]` | 预测数据字典 |
| `data_type` | `str` | 数据类型（如 "temperature_prediction"） |

**prediction_data 格式**：
```python
{
    'room_uid': 'CR_A1',           # 机房 UID
    'horizon': '1h',               # 预测时间范围
    'predictions': [               # 预测数据列表
        {
            'timestamp': datetime(2024, 1, 1, 11, 0, 0),
            'value': 25.5
        },
        {
            'timestamp': datetime(2024, 1, 1, 11, 1, 0),
            'value': 25.6
        }
    ]
}
```

**data_type 可选值**：
- `"temperature_prediction"`：温度预测
- `"energy_prediction"`：能耗预测
- `"pue_prediction"`：PUE 预测

**返回值**：
- `True`：写入成功
- `False`：写入失败

**执行流程**：
1. 检查预测数据写入是否启用
2. 验证数据格式（必须包含 `predictions` 字段）
3. 根据 `data_type` 构建 measurement 名称
4. 构建 InfluxDB Point 对象列表
5. 使用 `critical_operation` 保护写入操作
6. 调用 `_batch_write()` 批量写入数据
7. 返回写入结果

**measurement 命名规则**：
- 温度预测：`{room_uid}_temp_pred_{horizon}`，如 `CR_A1_temp_pred_1h`
- 能耗预测：`{room_uid}_energy_pred_{horizon}`，如 `CR_A1_energy_pred_1h`
- PUE 预测：`dc_pue_pred_{horizon}`，如 `dc_pue_pred_1h`

**使用示例**：
```python
from datetime import datetime

# 准备预测数据
prediction_data = {
    'room_uid': 'CR_A1',
    'horizon': '1h',
    'predictions': [
        {'timestamp': datetime(2024, 1, 1, 11, 0, 0), 'value': 25.5},
        {'timestamp': datetime(2024, 1, 1, 11, 1, 0), 'value': 25.6},
        {'timestamp': datetime(2024, 1, 1, 11, 2, 0), 'value': 25.7}
    ]
}

# 写入温度预测数据
success = writer.write_prediction_data(
    prediction_data=prediction_data,
    data_type='temperature_prediction'
)

if success:
    print("预测数据写入成功")
else:
    print("预测数据写入失败")
```

**异常**：
- `ValueError`：预测数据格式错误时抛出

---

##### 2. `write_optimization_commands()` - 写入优化控制指令

```python
def write_optimization_commands(
    self,
    control_commands: Dict[str, Any]
) -> bool:
```

**作用**：写入优化控制指令到 InfluxDB。

**参数**：

| 参数名 | 类型 | 说明 |
|--------|------|------|
| `control_commands` | `Dict[str, Any]` | 控制指令字典 |

**control_commands 格式**：
```python
{
    'device_uid': 'AC_A1_001',     # 设备 UID
    'commands': [                  # 控制指令列表
        {
            'control_uid': 'ac_a1_001_on_setpoint',  # 控制属性 UID
            'value': 25.0,                           # 设定值
            'timestamp': datetime(2024, 1, 1, 10, 0, 0)
        },
        {
            'control_uid': 'ac_a1_001_fan_speed',
            'value': 3,
            'timestamp': datetime(2024, 1, 1, 10, 0, 0)
        }
    ]
}
```

**返回值**：
- `True`：写入成功
- `False`：写入失败

**执行流程**：
1. 检查优化控制写入是否启用
2. 验证数据格式（必须包含 `commands` 字段）
3. 遍历每个控制指令，构建 InfluxDB Point 对象
4. 使用 `critical_operation` 保护写入操作
5. 调用 `_batch_write()` 批量写入数据
6. 返回写入结果

**使用示例**：
```python
from datetime import datetime

# 准备控制指令
control_commands = {
    'device_uid': 'AC_A1_001',
    'commands': [
        {
            'control_uid': 'ac_a1_001_on_setpoint',
            'value': 25.0,
            'timestamp': datetime.now()
        },
        {
            'control_uid': 'ac_a1_001_fan_speed',
            'value': 3,
            'timestamp': datetime.now()
        }
    ]
}

# 写入控制指令
success = writer.write_optimization_commands(control_commands)

if success:
    print("控制指令写入成功")
else:
    print("控制指令写入失败")
```

**异常**：
- `ValueError`：控制指令格式错误时抛出

---

#### 私有方法（内部使用）

##### 1. `_build_point()` - 构建 InfluxDB Point

```python
def _build_point(
    self,
    measurement: str,
    fields: Dict[str, Any],
    tags: Optional[Dict[str, str]] = None,
    timestamp: Optional[datetime] = None
) -> Dict[str, Any]:
```

**作用**：构建 InfluxDB Point 对象（字典格式）。

**参数**：

| 参数名 | 类型 | 说明 |
|--------|------|------|
| `measurement` | `str` | measurement 名称（类似于表名） |
| `fields` | `Dict[str, Any]` | 字段字典，如 `{'value': 25.0}` |
| `tags` | `Optional[Dict[str, str]]` | 标签字典（可选），如 `{'device_uid': 'AC_A1_001'}` |
| `timestamp` | `Optional[datetime]` | 时间戳（可选，默认为当前时间） |

**返回值**：
```python
{
    'measurement': 'ac_a1_001_temp',
    'tags': {'device_uid': 'AC_A1_001'},
    'fields': {'value': 25.0},
    'time': 1704096000000000000  # 纳秒级时间戳
}
```

**InfluxDB 数据模型简介**：
- **measurement**：类似于关系数据库中的表名
- **tags**：索引字段，用于快速查询和分组（字符串类型）
- **fields**：数据字段，存储实际的数值（可以是数字、字符串、布尔值）
- **time**：时间戳（纳秒级）

**示例**：
```python
# 构建一个温度数据点
point = writer._build_point(
    measurement='ac_a1_001_temp',
    fields={'value': 25.5},
    tags={'device_uid': 'AC_A1_001', 'room': 'CR_A1'},
    timestamp=datetime(2024, 1, 1, 10, 0, 0)
)

print(point)
# 输出：
# {
#     'measurement': 'ac_a1_001_temp',
#     'tags': {'device_uid': 'AC_A1_001', 'room': 'CR_A1'},
#     'fields': {'value': 25.5},
#     'time': 1704096000000000000
# }
```

---

##### 2. `_batch_write()` - 批量写入数据

```python
def _batch_write(
    self,
    points: List[Dict[str, Any]],
    database: str,
    batch_size: int,
    retry_times: int,
    retry_interval: int
) -> bool:
```

**作用**：批量写入数据到 InfluxDB，支持分批写入。

**参数**：

| 参数名 | 类型 | 说明 |
|--------|------|------|
| `points` | `List[Dict[str, Any]]` | Point 列表 |
| `database` | `str` | 目标数据库名称 |
| `batch_size` | `int` | 批量大小（每批写入的数据点数量） |
| `retry_times` | `int` | 重试次数 |
| `retry_interval` | `int` | 重试间隔（秒） |

**返回值**：
- `True`：写入成功
- `False`：写入失败

**执行流程**：
1. 检查是否有数据需要写入
2. 计算总批次数：`total_batches = (len(points) + batch_size - 1) // batch_size`
3. 遍历每个批次：
   - 切分数据：`batch = points[i:i + batch_size]`
   - 调用 `_retry_write()` 写入该批次
   - 如果写入失败，返回 `False`
4. 所有批次写入成功后，返回 `True`

**分批写入示例**：
```python
# 假设有 250 个数据点，batch_size = 100
# 会分成 3 个批次：
# 批次 1: points[0:100]   (100 个点)
# 批次 2: points[100:200] (100 个点)
# 批次 3: points[200:250] (50 个点)
```

---

##### 3. `_retry_write()` - 重试写入

```python
def _retry_write(
    self,
    points: List[Dict[str, Any]],
    database: str,
    retry_times: int,
    retry_interval: int
) -> bool:
```

**作用**：写入失败时自动重试。

**参数**：

| 参数名 | 类型 | 说明 |
|--------|------|------|
| `points` | `List[Dict[str, Any]]` | Point 列表 |
| `database` | `str` | 目标数据库名称 |
| `retry_times` | `int` | 重试次数 |
| `retry_interval` | `int` | 重试间隔（秒） |

**返回值**：
- `True`：写入成功
- `False`：写入失败

**执行流程**：
1. 循环 `retry_times + 1` 次（第一次尝试 + 重试次数）
2. 每次尝试：
   - 调用 `influxdb_client.write_points()` 写入数据
   - 如果成功，返回 `True`
   - 如果失败且还有重试次数，等待 `retry_interval` 秒后重试
   - 如果失败且已达到最大重试次数，返回 `False`

**重试示例**：
```python
# retry_times = 3, retry_interval = 2
# 最多尝试 4 次（1 次初始尝试 + 3 次重试）

# 第 1 次尝试：失败 → 等待 2 秒
# 第 2 次尝试：失败 → 等待 2 秒
# 第 3 次尝试：失败 → 等待 2 秒
# 第 4 次尝试：失败 → 返回 False
```

---

## 便捷函数

### 1. `load_read_write_config()` - 加载配置文件

```python
def load_read_write_config(config_path: str) -> Dict:
```

**作用**：加载 InfluxDB 读写配置文件。

**参数**：
- `config_path`（str）：配置文件路径，如 `"configs/influxdb_read_write_config.yaml"`

**返回值**：
- 类型：`Dict`
- 内容：配置字典，包含 `read` 和 `write` 两部分

**执行流程**：
1. 将路径转换为 `Path` 对象
2. 检查文件是否存在，不存在则抛出 `FileNotFoundError`
3. 使用 `yaml.safe_load()` 读取 YAML 文件
4. 返回配置字典

**使用示例**：
```python
# 加载配置文件
config = load_read_write_config("configs/influxdb_read_write_config.yaml")

# 访问配置
read_config = config['read']
write_config = config['write']

print(read_config['default']['mode'])  # 输出：time_range
```

**异常**：
- `FileNotFoundError`：配置文件不存在
- `yaml.YAMLError`：配置文件格式错误

---

### 2. `create_data_reader()` - 创建数据读取器

```python
def create_data_reader(
    datacenter: DataCenter,
    config_path: str,
    influxdb_client: InfluxDBClientWrapper
) -> DataCenterDataReader:
```

**作用**：创建数据读取器的便捷函数。

**参数**：

| 参数名 | 类型 | 说明 |
|--------|------|------|
| `datacenter` | `DataCenter` | 数据中心对象 |
| `config_path` | `str` | 配置文件路径 |
| `influxdb_client` | `InfluxDBClientWrapper` | InfluxDB 客户端 |

**返回值**：
- 类型：`DataCenterDataReader`
- 内容：数据读取器对象

**执行流程**：
1. 调用 `load_read_write_config()` 加载配置
2. 提取 `read` 部分的配置
3. 创建并返回 `DataCenterDataReader` 对象

**使用示例**：

```python
# 创建数据读取器
reader = create_data_reader(
    datacenter=datacenter,
    config_path="configs/influxdb_read_write_config.yaml",
    influxdb_client=dc_status_client
)

# 使用读取器读取数据
data = reader.read_all_observable_data()
```

---

### 3. `create_data_writer()` - 创建数据写入器

```python
def create_data_writer(
    datacenter: DataCenter,
    config_path: str,
    influxdb_client: InfluxDBClientWrapper,
    ctx: Any
) -> DataCenterDataWriter:
```

**作用**：创建数据写入器的便捷函数。

**参数**：

| 参数名 | 类型 | 说明 |
|--------|------|------|
| `datacenter` | `DataCenter` | 数据中心对象 |
| `config_path` | `str` | 配置文件路径 |
| `influxdb_client` | `InfluxDBClientWrapper` | InfluxDB 客户端 |
| `ctx` | `Any` | AppContext 对象 |

**返回值**：
- 类型：`DataCenterDataWriter`
- 内容：数据写入器对象

**执行流程**：
1. 调用 `load_read_write_config()` 加载配置
2. 提取 `write` 部分的配置
3. 创建并返回 `DataCenterDataWriter` 对象

**使用示例**：
```python
# 创建数据写入器
writer = create_data_writer(
    datacenter=datacenter,
    config_path="configs/influxdb_read_write_config.yaml",
    influxdb_client=prediction_client,
    ctx=ctx
)

# 使用写入器写入数据
writer.write_prediction_data(prediction_data, "temperature_prediction")
```

---

## 依赖关系分析

### 导入的模块

#### 标准库依赖

| 模块 | 用途 | 安装方式 |
|------|------|----------|
| `logging` | 日志记录 | Python 内置 |
| `yaml` | 读取 YAML 配置文件 | `pip install pyyaml` |
| `time` | 时间相关操作 | Python 内置 |
| `pandas` | 数据处理和分析 | `pip install pandas` |
| `pathlib` | 文件路径操作 | Python 内置 |
| `typing` | 类型提示 | Python 内置 |
| `datetime` | 日期时间处理 | Python 内置 |

#### 项目内部依赖

| 模块 | 文件路径 | 用途 |
|------|----------|------|
| `DataCenter, ComputerRoom, Device, Attribute` | `modules/architecture_module.py` | 数据中心架构类 |
| `InfluxDBClientWrapper` | `utils/influxdb_wrapper.py` | InfluxDB 客户端包装器 |
| `critical_operation` | `utils/critical_operation.py` | 关键操作保护 |

### 被引用的文件

该文件在项目中被以下文件引用：

| 文件 | 引用方式 | 用途 |
|------|----------|------|
| `main.py` | `from utils.data_read_write import create_data_reader, create_data_writer` | 创建数据读取器和写入器 |

### 在项目中的使用场景

#### 1. 训练模式（Training Mode）

在 `main.py` 的 `training_loop()` 函数中：

```python
# 读取训练数据
telemetry_data = ctx.data_reader.read_all_observable_data()

# 使用数据训练模型
# ...
```

#### 2. 推理模式（Inference Mode）

在 `main.py` 的 `inference_loop()` 函数中：

```python
# 读取最新数据
telemetry_data = ctx.data_reader.read_all_observable_data()

# 进行预测
# ...

# 写入预测结果
ctx.data_writer.write_prediction_data(
    prediction_data=prediction_results,
    data_type='temperature_prediction'
)
```

#### 3. 优化模式（Optimization Mode）

在 `main.py` 的 `optimization_loop()` 函数中：

```python
# 读取状态数据
telemetry_data = ctx.data_reader.read_all_observable_data()

# 计算优化控制指令
# ...

# 写入控制指令
ctx.data_writer.write_optimization_commands(
    control_commands=control_commands
)
```

---

## 使用示例

### 完整示例 1：读取数据中心所有数据

```python
from utils.data_read_write import create_data_reader
from utils.influxdb_wrapper import InfluxDBClientWrapper
from utils.architecture_config_parser import load_datacenter_from_config

# 1. 加载数据中心配置
datacenter = load_datacenter_from_config("configs/datacenter_config.yaml")

# 2. 创建 InfluxDB 客户端
influxdb_client = InfluxDBClientWrapper(
    client_config={
        'host': 'localhost',
        'port': 8086,
        'username': 'admin',
        'password': 'admin',
        'database': 'iot_origin_data'
    },
    reconnect_config={
        'max_retries': 3,
        'retry_interval': 5,
        'timeout': 10
    },
    logger=logger,
    client_name='dc_status_client'
)

# 3. 创建数据读取器
reader = create_data_reader(
    datacenter=datacenter,
    config_path="configs/influxdb_read_write_config.yaml",
    influxdb_client=influxdb_client
)

# 4. 读取所有遥测数据
all_data = reader.read_all_observable_data()

# 5. 处理数据
for uid, df in all_data.items():
    print(f"\nUID: {uid}")
    print(f"数据点数量: {len(df)}")
    print(f"时间范围: {df['timestamp'].min()} 到 {df['timestamp'].max()}")
    print(f"数值范围: {df['value'].min()} 到 {df['value'].max()}")
    print(f"平均值: {df['value'].mean():.2f}")
```

**预期输出**：
```
UID: ac_a1_001_temp
数据点数量: 120
时间范围: 2024-01-01 09:00:00 到 2024-01-01 10:00:00
数值范围: 24.5 到 26.3
平均值: 25.42

UID: ac_a1_001_power
数据点数量: 120
时间范围: 2024-01-01 09:00:00 到 2024-01-01 10:00:00
数值范围: 3.2 到 4.8
平均值: 4.05
```

---

### 完整示例 2：写入预测数据

```python
from datetime import datetime, timedelta
from utils.data_read_write import create_data_writer

# 1. 创建数据写入器（假设已有 datacenter, influxdb_client, ctx）
writer = create_data_writer(
    datacenter=datacenter,
    config_path="configs/influxdb_read_write_config.yaml",
    influxdb_client=prediction_client,
    ctx=ctx
)

# 2. 准备预测数据
# 假设我们预测未来 1 小时的温度，每分钟一个点
now = datetime.now()
predictions = []

for i in range(60):  # 60 分钟
    future_time = now + timedelta(minutes=i)
    # 假设预测值是 25 + 0.01 * i（温度逐渐上升）
    predicted_value = 25.0 + 0.01 * i

    predictions.append({
        'timestamp': future_time,
        'value': predicted_value
    })

# 3. 构建预测数据字典
prediction_data = {
    'room_uid': 'CR_A1',
    'horizon': '1h',
    'predictions': predictions
}

# 4. 写入预测数据
success = writer.write_prediction_data(
    prediction_data=prediction_data,
    data_type='temperature_prediction'
)

# 5. 检查结果
if success:
    print(f"成功写入 {len(predictions)} 个预测数据点")
else:
    print("预测数据写入失败")
```

**预期输出**：
```
成功写入 60 个预测数据点
```

---

### 完整示例 3：写入优化控制指令

```python
from datetime import datetime
from utils.data_read_write import create_data_writer

# 1. 创建数据写入器
writer = create_data_writer(
    datacenter=datacenter,
    config_path="configs/influxdb_read_write_config.yaml",
    influxdb_client=optimization_client,
    ctx=ctx
)

# 2. 准备控制指令
# 假设我们要控制空调 AC_A1_001 的温度设定值和风速
control_commands = {
    'device_uid': 'AC_A1_001',
    'commands': [
        {
            'control_uid': 'ac_a1_001_on_setpoint',  # 温度设定值
            'value': 24.5,
            'timestamp': datetime.now()
        },
        {
            'control_uid': 'ac_a1_001_fan_speed',    # 风速
            'value': 3,  # 假设 1-5 档
            'timestamp': datetime.now()
        }
    ]
}

# 3. 写入控制指令
success = writer.write_optimization_commands(control_commands)

# 4. 检查结果
if success:
    print(f"成功写入 {len(control_commands['commands'])} 个控制指令")
    for cmd in control_commands['commands']:
        print(f"  - {cmd['control_uid']}: {cmd['value']}")
else:
    print("控制指令写入失败")
```

**预期输出**：
```
成功写入 2 个控制指令
  - ac_a1_001_on_setpoint: 24.5
  - ac_a1_001_fan_speed: 3
```

---

### 完整示例 4：读取特定机房的数据

```python
# 读取机房 CR_A1 的所有数据
room_data = reader.read_room_data("CR_A1")

# 统计数据
print(f"机房 CR_A1 共有 {len(room_data)} 个遥测点")

# 分析每个遥测点
for uid, df in room_data.items():
    # 计算统计信息
    mean_value = df['value'].mean()
    max_value = df['value'].max()
    min_value = df['value'].min()

    print(f"\n{uid}:")
    print(f"  平均值: {mean_value:.2f}")
    print(f"  最大值: {max_value:.2f}")
    print(f"  最小值: {min_value:.2f}")

    # 检查是否有异常值（例如，超过平均值 2 倍标准差）
    std_value = df['value'].std()
    threshold = mean_value + 2 * std_value

    abnormal_points = df[df['value'] > threshold]
    if len(abnormal_points) > 0:
        print(f"  ⚠️ 发现 {len(abnormal_points)} 个异常值")
```

---

## Python 语法和函数详解

### 1. 字典的 `get()` 方法

```python
config.get('key', default_value)
```

**作用**：从字典中获取值，如果键不存在，返回默认值（而不是抛出异常）。

**示例**：
```python
config = {'mode': 'time_range', 'timeout': 30}

# 使用 get() 方法（推荐）
mode = config.get('mode', 'default_mode')
print(mode)  # 输出：time_range

retry = config.get('retry', 3)  # 键不存在，返回默认值 3
print(retry)  # 输出：3

# 直接访问（不推荐，键不存在会报错）
# mode = config['mode']  # 如果键不存在，会抛出 KeyError
```

---

### 2. f-string 格式化字符串

```python
f"字符串 {变量} 更多文本"
```

**作用**：在字符串中嵌入变量的值，Python 3.6+ 支持。

**示例**：
```python
name = "张三"
age = 25

# f-string 格式化
message = f"我叫{name}，今年{age}岁"
print(message)  # 输出：我叫张三，今年25岁

# 可以在 {} 中使用表达式
print(f"明年我{age + 1}岁")  # 输出：明年我26岁

# 格式化数字
value = 3.14159
print(f"圆周率约等于 {value:.2f}")  # 输出：圆周率约等于 3.14
# .2f 表示保留 2 位小数
```

---

### 3. 列表推导式（List Comprehension）

```python
[表达式 for 变量 in 可迭代对象 if 条件]
```

**作用**：用简洁的语法创建列表。

**示例**：
```python
# 传统方式
squares = []
for i in range(10):
    squares.append(i ** 2)

# 列表推导式（更简洁）
squares = [i ** 2 for i in range(10)]
print(squares)  # 输出：[0, 1, 4, 9, 16, 25, 36, 49, 64, 81]

# 带条件的列表推导式
even_squares = [i ** 2 for i in range(10) if i % 2 == 0]
print(even_squares)  # 输出：[0, 4, 16, 36, 64]

# 在 data_read_write.py 中的实际应用
batches = [
    uids[i:i + max_uids_per_query]
    for i in range(0, len(uids), max_uids_per_query)
]
# 这行代码将 uids 列表分成多个批次
```

---

### 4. `with` 语句（上下文管理器）

```python
with 上下文管理器 as 变量:
    # 代码块
```

**作用**：自动管理资源（如文件、数据库连接），确保资源在使用后被正确释放。

**示例**：
```python
# 文件操作
with open('config.yaml', 'r', encoding='utf-8') as f:
    content = f.read()
# 文件会自动关闭，即使发生异常

# critical_operation
with critical_operation(ctx):
    # 执行关键操作
    influxdb_client.write_points(data)
# 操作完成后，计数器会自动减少
```

**为什么使用 with？**
- 自动清理资源（如关闭文件）
- 即使发生异常，也能确保资源被释放
- 代码更简洁、更安全

---

### 5. `isinstance()` 函数

```python
isinstance(对象, 类型)
```

**作用**：检查对象是否是指定类型的实例。

**示例**：
```python
from datetime import datetime

# 检查类型
timestamp = datetime.now()
print(isinstance(timestamp, datetime))  # 输出：True
print(isinstance(timestamp, str))       # 输出：False

# 在 data_read_write.py 中的应用
if isinstance(timestamp, datetime):
    # 如果是 datetime 对象，转换为时间戳
    timestamp_ns = int(timestamp.timestamp() * 1e9)
else:
    # 如果已经是时间戳，直接转换为纳秒级
    timestamp_ns = int(timestamp * 1e9)
```

---

### 6. `range()` 函数

```python
range(start, stop, step)
```

**作用**：生成一个整数序列。

**示例**：
```python
# range(stop)：从 0 到 stop-1
for i in range(5):
    print(i)  # 输出：0, 1, 2, 3, 4

# range(start, stop)：从 start 到 stop-1
for i in range(2, 5):
    print(i)  # 输出：2, 3, 4

# range(start, stop, step)：从 start 到 stop-1，步长为 step
for i in range(0, 10, 2):
    print(i)  # 输出：0, 2, 4, 6, 8

# 在 data_read_write.py 中的应用
for i in range(0, len(points), batch_size):
    batch = points[i:i + batch_size]
    # 处理批次
```

---

### 7. 异常处理（try-except）

```python
try:
    # 可能出错的代码
except 异常类型 as e:
    # 处理异常
```

**作用**：捕获和处理异常，防止程序崩溃。

**示例**：
```python
try:
    # 尝试读取文件
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
except FileNotFoundError:
    print("文件不存在")
except yaml.YAMLError as e:
    print(f"YAML 格式错误: {e}")
except Exception as e:
    print(f"未知错误: {e}")
```

**常见异常类型**：
- `FileNotFoundError`：文件不存在
- `ValueError`：值错误（如类型转换失败）
- `KeyError`：字典键不存在
- `Exception`：所有异常的基类（捕获所有异常）

---

### 8. 类型提示中的 `Optional`

```python
from typing import Optional

def function(param: Optional[str]) -> Optional[int]:
    pass
```

**作用**：表示参数或返回值可以是指定类型或 `None`。

**示例**：
```python
from typing import Optional

def find_user(user_id: int) -> Optional[dict]:
    """
    查找用户
    返回值可以是字典（找到用户）或 None（未找到）
    """
    if user_id == 1:
        return {'name': '张三', 'age': 25}
    else:
        return None  # 未找到用户

# 使用
user = find_user(1)
if user is not None:
    print(user['name'])
else:
    print("用户不存在")
```

**`Optional[T]` 等价于 `Union[T, None]`**

---

### 9. 字典的 `items()` 方法

```python
for key, value in dict.items():
    # 处理键值对
```

**作用**：遍历字典的键值对。

**示例**：
```python
data = {'name': '张三', 'age': 25, 'city': '北京'}

# 遍历键值对
for key, value in data.items():
    print(f"{key}: {value}")

# 输出：
# name: 张三
# age: 25
# city: 北京

# 在 data_read_write.py 中的应用
for uid, df in telemetry_data.items():
    print(f"UID: {uid}, 数据点数: {len(df)}")
```

---

### 10. 列表切片（Slicing）

```python
list[start:stop:step]
```

**作用**：获取列表的一部分。

**示例**：
```python
numbers = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]

# 获取前 5 个元素
print(numbers[:5])  # 输出：[0, 1, 2, 3, 4]

# 获取从索引 3 到 7 的元素
print(numbers[3:8])  # 输出：[3, 4, 5, 6, 7]

# 获取从索引 2 开始，每隔 2 个元素
print(numbers[2::2])  # 输出：[2, 4, 6, 8]

# 在 data_read_write.py 中的应用
batch = points[i:i + batch_size]
# 获取从索引 i 开始的 batch_size 个元素
```

---

## 总结

### 文件的核心功能

1. **数据读取**：从 InfluxDB 批量读取遥测数据
   - 支持读取整个数据中心、单个机房或单个设备的数据
   - 支持两种读取模式：时间范围和最近 N 点
   - 实现批量查询优化

2. **数据写入**：向 InfluxDB 批量写入数据
   - 写入预测数据（温度、能耗、PUE 等）
   - 写入优化控制指令
   - 实现批量写入和重试机制
   - 使用 `critical_operation` 保护写入操作

### 使用建议

1. **使用便捷函数**：优先使用 `create_data_reader()` 和 `create_data_writer()` 创建读写器
2. **配置文件**：将读写配置放在 `influxdb_read_write_config.yaml` 中，便于管理
3. **异常处理**：在调用读写方法时，使用 `try-except` 捕获异常
4. **数据验证**：读取数据后，检查是否为空或是否有异常值
5. **批量操作**：尽量使用批量读写，提高效率

### 常见问题

**Q1：读取数据时返回空字典怎么办？**
- 检查 InfluxDB 中是否有数据
- 检查时间范围配置是否正确
- 检查 UID 是否正确

**Q2：写入数据失败怎么办？**
- 检查 InfluxDB 连接是否正常
- 检查数据格式是否正确
- 查看日志中的错误信息
- 检查重试配置是否合理

**Q3：如何提高读写性能？**
- 调整 `max_uids_per_query` 和 `batch_size` 参数
- 使用合适的时间范围（不要一次读取太多数据）
- 启用并行查询（如果支持）

---

**文档版本**：1.0
**最后更新**：2025-11-07
**作者**：Augment Agent

