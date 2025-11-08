# architecture_module.py 详细说明文档

## 📋 目录
1. [整体概述](#整体概述)
2. [重要Python语法解释](#重要python语法解释)
3. [基础抽象类详解](#基础抽象类详解)
4. [设备类详解](#设备类详解)
5. [系统级类详解](#系统级类详解)
6. [容器类详解](#容器类详解)
7. [完整使用示例](#完整使用示例)
8. [查询函数与 is_available 过滤机制详解](#查询函数与-is_available-过滤机制详解)

---

## 1. 整体概述

### 1.1 模块作用
`architecture_module.py` 是数据中心架构建模的核心模块,它定义了数据中心的**完整层次结构模型**。

### 1.2 层次结构
```
数据中心 (DataCenter)
    └── 机房 (ComputerRoom)
            └── 空调系统 (CoolingSystem)
                    └── 设备 (Device)
                            └── 属性 (Attribute)
```

### 1.3 设计原则
1. **层次化建模**: 清晰体现从数据中心到属性的层次关系
2. **统一属性管理**: 所有可观测/可调控的属性通过 `Attribute` 类统一管理
3. **容错机制**: 通过 `is_available` 标志和 `Optional` 返回值优雅处理缺失数据
4. **便捷访问**: 提供丰富的查询方法,支持按 uid、类型等方式查找

### 1.4 主要类别
- **基础抽象类**: `Attribute`, `Device`, `EnvironmentSensor`
- **风冷系统设备**: `AirConditioner_AirCooled`, `Compressor`, `Condenser`, `ExpansionValve`
- **水冷系统设备**: `AirConditioner_WaterCooled`, `Chiller`, `ChilledWaterPump`, `CoolingWaterPump`, `CoolingTower`
- **系统级类**: `CoolingSystem`, `AirCooledSystem`, `WaterCooledSystem`
- **容器类**: `ComputerRoom`, `DataCenter`

---

## 2. 重要Python语法解释

### 2.1 `@dataclass` 装饰器

**是什么**: Python 3.7+ 引入的装饰器,用于自动生成类的特殊方法。

**作用**: 
- 自动生成 `__init__()` 方法
- 自动生成 `__repr__()` 方法(用于打印对象)
- 自动生成 `__eq__()` 方法(用于比较对象)
- 减少样板代码,让代码更简洁

**示例对比**:

```python
# 不使用 @dataclass (传统方式)
class Person:
    def __init__(self, name: str, age: int):
        self.name = name
        self.age = age
    
    def __repr__(self):
        return f"Person(name={self.name}, age={self.age})"

# 使用 @dataclass (简洁方式)
from dataclasses import dataclass

@dataclass
class Person:
    name: str
    age: int

# 两种方式效果相同
p = Person("张三", 25)
print(p)  # 输出: Person(name='张三', age=25)
```

### 2.2 `field(default_factory=dict)` 用法

**是什么**: `dataclass` 中用于设置可变默认值的特殊函数。

**为什么需要**: Python 中不能直接使用可变对象(如列表、字典)作为默认参数,否则会导致所有实例共享同一个对象。

**错误示例**:
```python
@dataclass
class MyClass:
    items: list = []  # ❌ 错误!所有实例会共享同一个列表
```

**正确示例**:
```python
from dataclasses import dataclass, field

@dataclass
class MyClass:
    items: list = field(default_factory=list)  # ✅ 正确!每个实例有独立的列表
```

**实际效果**:
```python
obj1 = MyClass()
obj2 = MyClass()
obj1.items.append(1)
print(obj1.items)  # [1]
print(obj2.items)  # [] - 不受影响
```

### 2.3 类型提示 (Type Hints)

**是什么**: Python 3.5+ 引入的类型标注系统,用于标明变量、参数、返回值的类型。

**常用类型**:
```python
from typing import Dict, List, Optional

# 基础类型
name: str = "张三"
age: int = 25
score: float = 98.5
is_student: bool = True

# 容器类型
names: List[str] = ["张三", "李四"]
scores: Dict[str, int] = {"张三": 90, "李四": 85}

# Optional 类型 (可以是指定类型或 None)
middle_name: Optional[str] = None  # 等价于 Union[str, None]
```

**在本模块中的应用**:
```python
def get_attribute(self, attr_name: str) -> Optional[Attribute]:
    # 参数 attr_name 必须是字符串
    # 返回值可能是 Attribute 对象,也可能是 None
    return self.attributes.get(attr_name)
```

### 2.4 `super().__init__()` 用法

**是什么**: 调用父类的初始化方法。

**作用**: 在子类中继承并扩展父类的初始化逻辑。

**示例**:
```python
class Animal:
    def __init__(self, name: str):
        self.name = name
        print(f"动物 {name} 被创建")

class Dog(Animal):
    def __init__(self, name: str, breed: str):
        super().__init__(name)  # 调用父类的 __init__
        self.breed = breed
        print(f"品种: {breed}")

dog = Dog("旺财", "金毛")
# 输出:
# 动物 旺财 被创建
# 品种: 金毛
```

### 2.5 列表推导式 (List Comprehension)

**是什么**: Python 中创建列表的简洁语法。

**基本语法**:
```python
# 传统方式
result = []
for item in items:
    if condition:
        result.append(transform(item))

# 列表推导式
result = [transform(item) for item in items if condition]
```

**在本模块中的应用**:
```python
def get_observable_uids(self) -> List[str]:
    # 从所有属性中筛选出可观测属性,并提取其 uid
    return [attr.uid for attr in self.attributes.values()
            if attr.attr_type in ["telemetry", "telesignaling"]]
```

**等价的传统写法**:
```python
def get_observable_uids(self) -> List[str]:
    result = []
    for attr in self.attributes.values():
        if attr.attr_type in ["telemetry", "telesignaling"]:
            result.append(attr.uid)
    return result
```

---

## 3. 基础抽象类详解

### 3.1 Attribute 类

**作用**: 表示设备或环境的单个可观测/可调控属性。

**类定义**:
```python
@dataclass
class Attribute:
    name: str                      # 属性名称
    uid: str                       # 唯一标识符
    attr_type: str                 # 属性类型
    field_key: str = "value"       # 读取字段
    value: Optional[float] = None  # 当前值
    unit: Optional[str] = None     # 单位
    description: Optional[str] = None  # 描述
```

**属性详解**:

| 属性名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| `name` | str | ✅ | 属性的中文名称 | "空调送风温度" |
| `uid` | str | ✅ | 唯一标识符,对应数据库中的 measurement | "ac_a1_001_supply_temp" |
| `attr_type` | str | ✅ | 属性类型,见下表 | "telemetry" |
| `field_key` | str | ❌ | 从数据库读取时使用的字段名 | "value" |
| `value` | Optional[float] | ❌ | 从数据库读取后存储的当前值 | 24.5 |
| `unit` | Optional[str] | ❌ | 单位 | "℃" |
| `description` | Optional[str] | ❌ | 详细描述 | "空调出风口温度传感器" |

**属性类型说明**:

| attr_type | 中文名 | 可观测/可调控 | 数据类型 | 用途 |
|-----------|--------|---------------|----------|------|
| `telesignaling` | 遥信 | 可观测 | 状态型 | 开关状态、报警信号等离散状态 |
| `telemetry` | 遥测 | 可观测 | 数值型 | 温度、功率、转速等连续数值 |
| `telecontrol` | 遥控 | 可调控 | 状态型 | 开机/关机指令等 |
| `teleadjusting` | 遥调 | 可调控 | 数值型 | 温度设定点、转速设定点等 |
| `others` | 其他 | - | - | 其他类型 |

**使用示例**:
```python
# 创建一个温度遥测属性
temp_attr = Attribute(
    name="空调送风温度",
    uid="ac_a1_001_supply_temp",
    attr_type="telemetry",
    field_key="value",
    unit="℃",
    description="A1区域空调001号机组送风温度"
)

# 模拟从数据库读取数据后赋值
temp_attr.value = 24.5
print(f"{temp_attr.name}: {temp_attr.value}{temp_attr.unit}")
# 输出: 空调送风温度: 24.5℃
```

### 3.2 Device 类

**作用**: 所有设备的抽象父类,定义了设备的通用属性和方法。

**类定义**:
```python
@dataclass
class Device:
    device_name: str                           # 设备名称
    device_uid: str                            # 设备唯一标识符
    device_type: str                           # 设备类型
    location: Optional[str] = None             # 位置
    attributes: Dict[str, Attribute] = field(default_factory=dict)  # 属性字典
    is_available: bool = True                  # 是否可用
```

**方法详解**:

#### 3.2.1 `add_attribute()` 方法

**作用**: 向设备添加属性。

**参数**:
- `attr` (Attribute): 要添加的属性对象

**返回值**: None

**实现逻辑**:
```python
def add_attribute(self, attr: Attribute) -> None:
    self.attributes[attr.name] = attr  # 以属性名称为键存储
```

**使用示例**:
```python
# 创建设备
ac = Device(
    device_name="A1-AC-001",
    device_uid="ac_a1_001",
    device_type="AC_AirCooled"
)

# 创建并添加属性
temp_attr = Attribute(name="送风温度", uid="ac_a1_001_supply_temp", attr_type="telemetry")
ac.add_attribute(temp_attr)

print(ac.attributes)  # {'送风温度': Attribute(...)}
```

#### 3.2.2 `get_attribute()` 方法

**作用**: 获取指定名称的属性(容错设计)。

**参数**:
- `attr_name` (str): 属性名称

**返回值**: 
- `Optional[Attribute]`: 找到返回属性对象,未找到返回 None

**实现逻辑**:
```python
def get_attribute(self, attr_name: str) -> Optional[Attribute]:
    return self.attributes.get(attr_name)  # 使用 dict.get() 方法,不存在返回 None
```

**为什么使用 `.get()` 而不是 `[]`**:
```python
# 使用 [] 访问不存在的键会抛出异常
try:
    attr = ac.attributes["不存在的属性"]  # ❌ 抛出 KeyError
except KeyError:
    print("属性不存在")

# 使用 .get() 返回 None,不会抛出异常
attr = ac.attributes.get("不存在的属性")  # ✅ 返回 None
if attr is None:
    print("属性不存在")
```

#### 3.2.3 `get_observable_uids()` 方法

**作用**: 获取所有可观测属性的 uid 列表(用于从数据库读取数据)。

**参数**: 无

**返回值**: 
- `List[str]`: 可观测属性的 uid 列表

**实现逻辑**:
```python
def get_observable_uids(self) -> List[str]:
    return [attr.uid for attr in self.attributes.values()
            if attr.attr_type in ["telemetry", "telesignaling"]]
```

**逐步解析**:
1. `self.attributes.values()`: 获取所有属性对象
2. `for attr in ...`: 遍历每个属性
3. `if attr.attr_type in ["telemetry", "telesignaling"]`: 筛选可观测类型
4. `attr.uid`: 提取 uid
5. `[...]`: 组成列表

**使用示例**:
```python
ac = Device(device_name="AC-001", device_uid="ac_001", device_type="AC")
ac.add_attribute(Attribute(name="温度", uid="temp_001", attr_type="telemetry"))
ac.add_attribute(Attribute(name="状态", uid="status_001", attr_type="telesignaling"))
ac.add_attribute(Attribute(name="设定点", uid="setpoint_001", attr_type="telecontrol"))

uids = ac.get_observable_uids()
print(uids)  # ['temp_001', 'status_001'] - 只包含可观测属性
```

#### 3.2.4 `get_regulable_uids()` 方法

**作用**: 获取所有可调控属性的 uid 列表(用于写入控制指令)。

**参数**: 无

**返回值**: 
- `List[str]`: 可调控属性的 uid 列表

**实现逻辑**:
```python
def get_regulable_uids(self) -> List[str]:
    return [attr.uid for attr in self.attributes.values()
            if attr.attr_type in ["telecontrol", "teleadjusting"]]
```

### 3.3 EnvironmentSensor 类

**作用**: 环境传感器类,用于温度、湿度等环境监测。

**类定义**:
```python
@dataclass
class EnvironmentSensor:
    sensor_name: str                           # 传感器名称
    sensor_uid: str                            # 传感器唯一标识符
    sensor_type: str = "environment"           # 传感器类型
    location: Optional[str] = None             # 位置
    attributes: Dict[str, Attribute] = field(default_factory=dict)  # 属性字典
```

**方法**: 与 Device 类似,包括 `add_attribute()`, `get_attribute()`, `get_all_uids()`

**使用示例**:
```python
# 创建环境传感器
sensor = EnvironmentSensor(
    sensor_name="A1区温度传感器",
    sensor_uid="env_sensor_a1_temp",
    location="A1区中央"
)

# 添加温度属性
temp_attr = Attribute(
    name="环境温度",
    uid="env_a1_temp",
    attr_type="telemetry",
    unit="℃"
)
sensor.add_attribute(temp_attr)

# 添加湿度属性
humidity_attr = Attribute(
    name="环境湿度",
    uid="env_a1_humidity",
    attr_type="telemetry",
    unit="%"
)
sensor.add_attribute(humidity_attr)

# 获取所有 uid
uids = sensor.get_all_uids()
print(uids)  # ['env_a1_temp', 'env_a1_humidity']
```

---

## 4. 设备类详解

所有具体设备类都继承自 `Device` 基类,主要区别在于 `device_type` 不同。

### 4.1 风冷系统设备

#### 4.1.1 AirConditioner_AirCooled (风冷空调)

**作用**: 表示风冷系统中的室内空调设备。

**类定义**:
```python
class AirConditioner_AirCooled(Device):
    def __init__(self, device_name: str, device_uid: str, location: str = None):
        super().__init__(
            device_name=device_name,
            device_uid=device_uid,
            device_type="AC_AirCooled",  # 固定类型
            location=location
        )
```

**典型属性**:
- 遥测: 送风温度、回风温度、风机转速、有功功率
- 遥信: 空调开关状态
- 遥控: 送风温度设定点、风机转速设定点
- 遥调: 开机设定点、关机设定点

**使用示例**:
```python
# 创建风冷空调
ac = AirConditioner_AirCooled(
    device_name="A1-AC-001",
    device_uid="ac_a1_001",
    location="A1区"
)

# 添加送风温度属性
ac.add_attribute(Attribute(
    name="送风温度",
    uid="ac_a1_001_supply_temp",
    attr_type="telemetry",
    unit="℃"
))

# 添加开关状态属性
ac.add_attribute(Attribute(
    name="开关状态",
    uid="ac_a1_001_status",
    attr_type="telesignaling"
))
```

#### 4.1.2 Compressor (压缩机)

**device_type**: "COMP"

**典型属性**:
- 遥测: 频率、有功功率、累计能耗
- 遥信: 开关状态
- 遥控: 频率设定点
- 遥调: 开机/关机设定点

#### 4.1.3 Condenser (冷凝器)

**device_type**: "COND"

**典型属性**:
- 遥测: 温度、压力、风机转速、有功功率
- 遥控: 风机最小/最大转速设定点

#### 4.1.4 ExpansionValve (膨胀阀)

**device_type**: "EV"

**典型属性**:
- 遥测: 开度
- 遥控: 开度设定点

### 4.2 水冷系统设备

#### 4.2.1 AirConditioner_WaterCooled (水冷空调)

**device_type**: "AC_WaterCooled"

**典型属性**:
- 遥测: 送风温度、回风温度、风机转速、水阀开度、冷冻水出/回水温度、有功功率
- 遥信: 开关状态
- 遥控: 送风温度设定点、风机转速设定点、水阀开度设定点
- 遥调: 开机/关机设定点

#### 4.2.2 Chiller (冷水机组)

**device_type**: "CH"

**典型属性**:
- 遥测: 负荷百分比、用电量、冷冻水出/回水温度、冷却水出/回水温度、有功功率
- 遥信: 开关状态
- 遥控: 冷冻水出水温度设定点
- 遥调: 开机/关机设定点

#### 4.2.3 ChilledWaterPump (冷冻水泵)

**device_type**: "CHWP"

**典型属性**:
- 遥测: 用电量、压力、频率反馈、有功功率
- 遥信: 开关状态
- 遥控: 频率设定点、压差设定点
- 遥调: 开机/关机设定点

#### 4.2.4 CoolingWaterPump (冷却水泵)

**device_type**: "CWP"

**典型属性**: 与冷冻水泵类似

#### 4.2.5 CoolingTower (冷却塔)

**device_type**: "CT"

**典型属性**:
- 遥测: 出水温度、回水温度、风机转速、有功功率
- 遥信: 开关状态
- 遥控: 风机转速设定点、出水温度设定点
- 遥调: 开机/关机设定点

---

## 5. 系统级类详解

### 5.1 CoolingSystem 类

**作用**: 空调系统基类,用于组织和管理一组相关设备。

**类定义**:
```python
@dataclass
class CoolingSystem:
    system_name: str                                    # 系统名称
    system_uid: str                                     # 系统唯一标识符
    system_type: str                                    # 系统类型
    devices: Dict[str, List[Device]] = field(default_factory=dict)  # 设备字典
```

**设备字典结构**:
```python
{
    "AC_AirCooled": [ac1, ac2, ac3],  # 同类型设备组成列表
    "COMP": [comp1, comp2],
    "COND": [cond1]
}
```

**方法详解**:

#### 5.1.1 `add_device()` 方法

**作用**: 向系统添加设备。

**参数**:
- `device` (Device): 要添加的设备对象

**返回值**: None

**实现逻辑**:
```python
def add_device(self, device: Device) -> None:
    # 如果该设备类型还没有列表,先创建空列表
    if device.device_type not in self.devices:
        self.devices[device.device_type] = []
    # 将设备添加到对应类型的列表中
    self.devices[device.device_type].append(device)
```

**逐步解析**:
1. 检查设备类型是否已存在于字典中
2. 如果不存在,创建一个空列表
3. 将设备添加到对应类型的列表中

**使用示例**:
```python
system = CoolingSystem(
    system_name="A1区空调系统",
    system_uid="system_a1",
    system_type="AirCooled"
)

# 添加第一台空调
ac1 = AirConditioner_AirCooled("AC-001", "ac_001")
system.add_device(ac1)
# 此时 system.devices = {"AC_AirCooled": [ac1]}

# 添加第二台空调
ac2 = AirConditioner_AirCooled("AC-002", "ac_002")
system.add_device(ac2)
# 此时 system.devices = {"AC_AirCooled": [ac1, ac2]}

# 添加压缩机
comp = Compressor("COMP-001", "comp_001")
system.add_device(comp)
# 此时 system.devices = {"AC_AirCooled": [ac1, ac2], "COMP": [comp]}
```

#### 5.1.2 `get_devices_by_type()` 方法

**作用**: 获取指定类型的所有设备。

**参数**:
- `device_type` (str): 设备类型,如 "AC_AirCooled", "COMP"

**返回值**:
- `List[Device]`: 设备列表,不存在则返回空列表

**实现逻辑**:
```python
def get_devices_by_type(self, device_type: str) -> List[Device]:
    return self.devices.get(device_type, [])  # 不存在返回空列表 []
```

**使用示例**:
```python
# 获取所有空调
acs = system.get_devices_by_type("AC_AirCooled")
print(f"共有 {len(acs)} 台空调")

# 获取不存在的设备类型
evs = system.get_devices_by_type("EV")
print(evs)  # [] - 返回空列表,不会报错
```

#### 5.1.3 `get_all_devices()` 方法

**作用**: 获取系统内所有设备(不区分类型)。

**参数**: 无

**返回值**:
- `List[Device]`: 所有设备的列表

**实现逻辑**:
```python
def get_all_devices(self) -> List[Device]:
    all_devices = []
    for device_list in self.devices.values():  # 遍历每个设备类型的列表
        all_devices.extend(device_list)        # 将列表中的设备添加到总列表
    return all_devices
```

**`extend()` vs `append()` 的区别**:
```python
list1 = [1, 2]
list2 = [3, 4]

# append() 将整个列表作为一个元素添加
list1.append(list2)
print(list1)  # [1, 2, [3, 4]]

# extend() 将列表中的每个元素分别添加
list1 = [1, 2]
list1.extend(list2)
print(list1)  # [1, 2, 3, 4]
```

### 5.2 AirCooledSystem 类

**作用**: 风冷空调系统,继承自 CoolingSystem。

**类定义**:
```python
class AirCooledSystem(CoolingSystem):
    def __init__(self, system_name: str, system_uid: str):
        super().__init__(
            system_name=system_name,
            system_uid=system_uid,
            system_type="AirCooled"  # 固定为风冷类型
        )
```

**包含设备类型**:
- AC_AirCooled: 室内空调
- COMP: 压缩机
- COND: 冷凝器
- EV: 膨胀阀

**使用示例**:
```python
# 创建风冷系统
air_system = AirCooledSystem(
    system_name="A1区风冷系统",
    system_uid="air_system_a1"
)

# 添加设备
air_system.add_device(AirConditioner_AirCooled("AC-001", "ac_001"))
air_system.add_device(Compressor("COMP-001", "comp_001"))
air_system.add_device(Condenser("COND-001", "cond_001"))
air_system.add_device(ExpansionValve("EV-001", "ev_001"))

# 查询设备
all_devices = air_system.get_all_devices()
print(f"风冷系统共有 {len(all_devices)} 台设备")
```

### 5.3 WaterCooledSystem 类

**作用**: 水冷空调系统,继承自 CoolingSystem。

**类定义**:
```python
class WaterCooledSystem(CoolingSystem):
    def __init__(self, system_name: str, system_uid: str):
        super().__init__(
            system_name=system_name,
            system_uid=system_uid,
            system_type="WaterCooled"  # 固定为水冷类型
        )
```

**包含设备类型**:
- AC_WaterCooled: 室内空调
- CH: 冷水机组
- CHWP: 冷冻水泵
- CWP: 冷却水泵
- CT: 冷却塔

**使用示例**:
```python
# 创建水冷系统
water_system = WaterCooledSystem(
    system_name="B1区水冷系统",
    system_uid="water_system_b1"
)

# 添加设备
water_system.add_device(AirConditioner_WaterCooled("AC-001", "ac_001"))
water_system.add_device(Chiller("CH-001", "ch_001"))
water_system.add_device(ChilledWaterPump("CHWP-001", "chwp_001"))
water_system.add_device(CoolingWaterPump("CWP-001", "cwp_001"))
water_system.add_device(CoolingTower("CT-001", "ct_001"))
```

---

## 6. 容器类详解

### 6.1 ComputerRoom 类

**作用**: 表示数据中心内的单个机房,可以包含多个空调系统。

**类定义**:
```python
@dataclass
class ComputerRoom:
    room_name: str                                      # 机房名称
    room_uid: str                                       # 机房唯一标识符
    room_type: str                                      # 机房类型
    location: Optional[str] = None                      # 位置
    air_cooled_systems: List[AirCooledSystem] = field(default_factory=list)
    water_cooled_systems: List[WaterCooledSystem] = field(default_factory=list)
    environment_sensors: List[EnvironmentSensor] = field(default_factory=list)
    room_attributes: Dict[str, Attribute] = field(default_factory=dict)
    is_available: bool = True                           # 是否可用
```

**机房类型**:
- "AirCooled": 纯风冷机房
- "WaterCooled": 纯水冷机房
- "Mixed": 混合机房(同时有风冷和水冷系统)

**重要方法详解**:

#### 6.1.1 `get_all_observable_uids()` 方法

**作用**: 获取机房内所有遥测属性的 uid 列表。

**参数**: 无

**返回值**:
- `List[str]`: 所有遥测属性的 uid 列表

**实现逻辑**:
```python
def get_all_observable_uids(self) -> List[str]:
    uids = []

    # 1. 收集设备属性
    for device in self.get_all_devices():
        uids.extend(device.get_observable_uids())

    # 2. 收集环境传感器属性
    for sensor in self.environment_sensors:
        uids.extend(sensor.get_all_uids())

    # 3. 收集机房级别属性
    for attr in self.room_attributes.values():
        if attr.attr_type in ["telemetry", "telesignaling"]:
            uids.append(attr.uid)

    return uids
```

**逐步解析**:
1. 创建空列表存储 uid
2. 遍历所有设备,收集可观测属性的 uid
3. 遍历所有环境传感器,收集其属性的 uid
4. 遍历机房级别属性,筛选可观测类型并收集 uid
5. 返回完整的 uid 列表

**为什么需要这个方法**:
在从数据库读取数据时,需要知道所有需要读取的 uid,这个方法可以一次性获取机房内所有需要监测的数据点。

#### 6.1.2 `get_device_by_uid()` 方法

**作用**: 根据设备 uid 查找设备。

**参数**:
- `device_uid` (str): 设备唯一标识符

**返回值**:
- `Optional[Device]`: 设备对象,不存在则返回 None

**实现逻辑**:
```python
def get_device_by_uid(self, device_uid: str) -> Optional[Device]:
    for device in self.get_all_devices():
        if device.device_uid == device_uid:
            return device  # 找到立即返回
    return None  # 遍历完未找到,返回 None
```

**使用示例**:
```python
room = ComputerRoom(room_name="A1机房", room_uid="room_a1", room_type="AirCooled")
# ... 添加系统和设备 ...

# 查找设备
device = room.get_device_by_uid("ac_001")
if device:
    print(f"找到设备: {device.device_name}")
else:
    print("设备不存在")
```

### 6.2 DataCenter 类

**作用**: 数据中心顶层容器类,包含多个机房。

**类定义**:
```python
@dataclass
class DataCenter:
    dc_name: str                                        # 数据中心名称
    dc_uid: str                                         # 数据中心唯一标识符
    location: Optional[str] = None                      # 位置
    computer_rooms: List[ComputerRoom] = field(default_factory=list)
    environment_sensors: List[EnvironmentSensor] = field(default_factory=list)
    dc_attributes: Dict[str, Attribute] = field(default_factory=dict)
```

**重要方法详解**:

#### 6.2.1 `get_all_observable_uids()` 方法

**作用**: 获取整个数据中心所有遥测属性的 uid 列表。

**实现逻辑**:

```python
def get_all_observable_uids(self) -> List[str]:
    uids = []

    # 1. 收集所有机房的遥测属性
    for room in self.computer_rooms:
        uids.extend(room.get_all_observable_uids())

    # 2. 收集数据中心级别环境传感器
    for sensor in self.environment_sensors:
        uids.extend(sensor.get_all_uids())

    # 3. 收集数据中心级别属性
    for attr in self.dc_attributes.values():
        if attr.attr_type in ["telemetry", "telesignaling"]:
            uids.append(attr.uid)

    return uids
```

**层次化收集**: 这个方法体现了层次化设计的优势,通过调用下层对象的方法,逐层收集所有数据点。

#### 6.2.2 `get_device_by_uid()` 方法

**作用**: 在整个数据中心范围内查找设备。

**实现逻辑**:
```python
def get_device_by_uid(self, device_uid: str) -> Optional[Device]:
    for room in self.computer_rooms:
        device = room.get_device_by_uid(device_uid)  # 在每个机房中查找
        if device:
            return device  # 找到立即返回
    return None  # 所有机房都未找到
```

**层次化查找**: 先遍历机房,再在每个机房中查找设备,体现了层次结构。

#### 6.2.3 `get_statistics()` 方法

**作用**: 获取数据中心的统计信息。

**参数**: 无

**返回值**:
- `Dict[str, Any]`: 统计信息字典

**实现逻辑**:

```python
def get_statistics(self) -> Dict[str, Any]:
    stats = {
        "total_rooms": len(self.computer_rooms),
        "total_air_cooled_systems": 0,
        "total_water_cooled_systems": 0,
        "total_devices": 0,
        "total_observable_points": len(self.get_all_observable_uids()),
        "total_regulable_points": len(self.get_all_regulable_uids())
    }

    # 遍历机房统计系统和设备数量
    for room in self.computer_rooms:
        stats["total_air_cooled_systems"] += len(room.air_cooled_systems)
        stats["total_water_cooled_systems"] += len(room.water_cooled_systems)
        stats["total_devices"] += len(room.get_all_devices())

    return stats
```

**返回示例**:
```python
{
    "total_rooms": 3,
    "total_air_cooled_systems": 5,
    "total_water_cooled_systems": 2,
    "total_devices": 45,
    "total_observable_points": 320,
    "total_regulable_points": 180
}
```

---

## 7. 完整使用示例

### 7.1 构建完整的数据中心模型

```python
from modules.architecture_module import *

# ========== 1. 创建数据中心 ==========
dc = DataCenter(
    dc_name="北京数据中心",
    dc_uid="dc_beijing",
    location="北京市海淀区"
)

# ========== 2. 创建机房 ==========
room_a1 = ComputerRoom(
    room_name="A1机房",
    room_uid="room_a1",
    room_type="AirCooled",
    location="A栋1层"
)

# ========== 3. 创建风冷系统 ==========
air_system = AirCooledSystem(
    system_name="A1区风冷系统1",
    system_uid="air_system_a1_01"
)

# ========== 4. 创建设备并添加属性 ==========
# 创建空调
ac = AirConditioner_AirCooled(
    device_name="A1-AC-001",
    device_uid="ac_a1_001",
    location="A1区北侧"
)

# 添加空调属性
ac.add_attribute(Attribute(
    name="送风温度",
    uid="ac_a1_001_supply_temp",
    attr_type="telemetry",
    field_key="value",
    unit="℃",
    description="空调送风温度传感器"
))

ac.add_attribute(Attribute(
    name="回风温度",
    uid="ac_a1_001_return_temp",
    attr_type="telemetry",
    field_key="value",
    unit="℃"
))

ac.add_attribute(Attribute(
    name="开关状态",
    uid="ac_a1_001_status",
    attr_type="telesignaling",
    field_key="value"
))

ac.add_attribute(Attribute(
    name="送风温度设定点",
    uid="ac_a1_001_supply_temp_setpoint",
    attr_type="telecontrol",
    field_key="value",
    unit="℃"
))

# 创建压缩机
comp = Compressor(
    device_name="A1-COMP-001",
    device_uid="comp_a1_001"
)

comp.add_attribute(Attribute(
    name="频率",
    uid="comp_a1_001_frequency",
    attr_type="telemetry",
    unit="Hz"
))

comp.add_attribute(Attribute(
    name="有功功率",
    uid="comp_a1_001_power",
    attr_type="telemetry",
    unit="kW"
))

# ========== 5. 组装层次结构 ==========
# 设备 → 系统
air_system.add_device(ac)
air_system.add_device(comp)

# 系统 → 机房
room_a1.add_air_cooled_system(air_system)

# 添加环境传感器到机房
env_sensor = EnvironmentSensor(
    sensor_name="A1机房温度传感器",
    sensor_uid="env_sensor_a1",
    location="A1机房中央"
)
env_sensor.add_attribute(Attribute(
    name="环境温度",
    uid="env_a1_temp",
    attr_type="telemetry",
    unit="℃"
))
room_a1.add_environment_sensor(env_sensor)

# 机房 → 数据中心
dc.add_computer_room(room_a1)

# ========== 6. 使用模型 ==========
# 获取所有需要监测的数据点
telemetry_uids = dc.get_all_observable_uids()
print(f"需要监测的数据点: {telemetry_uids}")
# 输出: ['ac_a1_001_supply_temp', 'ac_a1_001_return_temp', 'ac_a1_001_status',
#        'comp_a1_001_frequency', 'comp_a1_001_power', 'env_a1_temp']

# 获取所有可控制的数据点
control_uids = dc.get_all_regulable_uids()
print(f"可控制的数据点: {control_uids}")
# 输出: ['ac_a1_001_supply_temp_setpoint']

# 查找特定设备
device = dc.get_device_by_uid("ac_a1_001")
if device:
    print(f"找到设备: {device.device_name}, 类型: {device.device_type}")
    # 输出: 找到设备: A1-AC-001, 类型: AC_AirCooled

# 获取统计信息
stats = dc.get_statistics()
print(f"数据中心统计: {stats}")
# 输出: {'total_rooms': 1, 'total_air_cooled_systems': 1,
#        'total_water_cooled_systems': 0, 'total_devices': 2,
#        'total_observable_points': 6, 'total_regulable_points': 1}
```

### 7.2 模拟数据读取和更新

```python
# 模拟从数据库读取数据后更新属性值
def update_device_values(device: Device, data_dict: Dict[str, float]):
    """
    更新设备属性值

    参数:
        device: 设备对象
        data_dict: {uid: value} 字典
    """
    for attr in device.attributes.values():
        if attr.uid in data_dict:
            attr.value = data_dict[attr.uid]

# 模拟数据
data = {
    "ac_a1_001_supply_temp": 24.5,
    "ac_a1_001_return_temp": 26.8,
    "ac_a1_001_status": 1.0,
    "comp_a1_001_frequency": 45.2,
    "comp_a1_001_power": 12.5
}

# 更新空调数据
ac = dc.get_device_by_uid("ac_a1_001")
update_device_values(ac, data)

# 读取属性值
supply_temp = ac.get_attribute("送风温度")
if supply_temp:
    print(f"{supply_temp.name}: {supply_temp.value}{supply_temp.unit}")
    # 输出: 送风温度: 24.5℃
```

### 7.3 容错机制示例

```python
# 尝试获取不存在的属性
attr = ac.get_attribute("不存在的属性")
if attr is None:
    print("属性不存在,但程序不会崩溃")  # ✅ 优雅处理

# 尝试获取不存在的设备
device = dc.get_device_by_uid("不存在的设备")
if device is None:
    print("设备不存在,但程序不会崩溃")  # ✅ 优雅处理

# 标记设备不可用
ac.is_available = False
if not ac.is_available:
    print("设备不可用,跳过数据读取")  # ✅ 可以根据标志决定是否处理
```

---

## 8. 查询函数与 is_available 过滤机制详解

### 8.1 概述

`architecture_module.py` 中提供了丰富的查询函数，用于获取设备、UID、房间和系统等信息。这些函数对 `is_available` 字段的处理方式各不相同，理解这些差异对于正确使用模块至关重要。

**关键发现**：
- ✅ **获取所有项目的函数**（如 `get_all_devices()`、`get_all_rooms()`、`get_all_systems()`）默认返回所有项目，**包括** `is_available=False` 的项目
- ⚠️ **获取 UID 的函数**（如 `get_all_observable_uids()`、`get_all_regulable_uids()`）会**自动过滤**掉 `is_available=False` 的设备
- 🎯 **专门的过滤函数**（如 `get_available_devices()`、`get_unavailable_devices()`）提供明确的过滤功能

### 8.2 设备查询函数

以下函数用于获取设备对象：

| 函数名称 | 所在类 | 是否过滤 is_available=False | 说明 |
|---------|--------|---------------------------|------|
| `get_all_devices(include_unavailable=True)` | `CoolingSystem` | 可选过滤 | 默认返回所有设备（包括不可用）；当 `include_unavailable=False` 时过滤掉不可用设备 |
| `get_all_devices()` | `ComputerRoom` | ❌ 不过滤 | 返回机房内所有设备，**包括** `is_available=False` 的设备 |
| `get_available_devices()` | `ComputerRoom` | ✅ 过滤 | 只返回 `is_available=True` 的设备 |
| `get_unavailable_devices()` | `ComputerRoom` | ✅ 反向过滤 | 只返回 `is_available=False` 的设备 |
| `get_all_devices()` | `DataCenter` | ❌ 不过滤 | 返回数据中心内所有设备，**包括** `is_available=False` 的设备 |

**代码示例**：

<augment_code_snippet path="modules/architecture_module.py" mode="EXCERPT">
````python
# CoolingSystem.get_all_devices() - 第390-408行
def get_all_devices(self, include_unavailable: bool = True) -> List[Device]:
    all_devices = []
    for device_list in self.devices.values():
        all_devices.extend(device_list)

    # 根据参数过滤不可用的设备
    if not include_unavailable:
        all_devices = [d for d in all_devices if d.is_available]

    return all_devices
````
</augment_code_snippet>

<augment_code_snippet path="modules/architecture_module.py" mode="EXCERPT">
````python
# ComputerRoom.get_all_devices() - 第517-527行
def get_all_devices(self) -> List[Device]:
    devices = []
    for system in self.get_all_systems():
        devices.extend(system.get_all_devices(include_unavailable=True))  # 包含不可用设备
    return devices
````
</augment_code_snippet>

<augment_code_snippet path="modules/architecture_module.py" mode="EXCERPT">
````python
# ComputerRoom.get_available_devices() - 第598-605行
def get_available_devices(self) -> List[Device]:
    return [device for device in self.get_all_devices() if device.is_available]
````
</augment_code_snippet>

### 8.3 UID 查询函数

以下函数用于获取属性的唯一标识符（UID）列表：

| 函数名称 | 所在类 | 是否过滤 is_available=False | 说明 |
|---------|--------|---------------------------|------|
| `get_observable_uids()` | `Device` | ❌ 不过滤 | 返回该设备的所有可观测属性 UID，不检查设备的 `is_available` 状态 |
| `get_regulable_uids()` | `Device` | ❌ 不过滤 | 返回该设备的所有可调控属性 UID，不检查设备的 `is_available` 状态 |
| `get_all_observable_uids()` | `ComputerRoom` | ✅ **过滤** | **只收集** `is_available=True` 的设备的可观测属性 UID |
| `get_all_regulable_uids()` | `ComputerRoom` | ✅ **过滤** | **只收集** `is_available=True` 的设备的可调控属性 UID |
| `get_all_observable_uids()` | `DataCenter` | ✅ **过滤** | 通过调用 `ComputerRoom.get_all_observable_uids()`，间接过滤掉不可用设备 |
| `get_all_regulable_uids()` | `DataCenter` | ✅ **过滤** | 通过调用 `ComputerRoom.get_all_regulable_uids()`，间接过滤掉不可用设备 |

**⚠️ 重要提示**：`ComputerRoom` 和 `DataCenter` 级别的 UID 查询函数会**自动过滤**掉 `is_available=False` 的设备，这是为了确保只读取和控制可用的设备。

**代码示例**：

<augment_code_snippet path="modules/architecture_module.py" mode="EXCERPT">
````python
# Device.get_observable_uids() - 第102-110行
def get_observable_uids(self) -> List[str]:
    return [attr.uid for attr in self.attributes.values()
            if attr.attr_type in ["telemetry", "telesignaling"]]
````
</augment_code_snippet>

<augment_code_snippet path="modules/architecture_module.py" mode="EXCERPT">
````python
# ComputerRoom.get_all_observable_uids() - 第529-552行
def get_all_observable_uids(self) -> List[str]:
    uids = []

    # 设备属性（只收集可用设备的属性）
    for device in self.get_all_devices():
        if device.is_available:  # ⚠️ 关键：这里过滤掉不可用设备
            uids.extend(device.get_observable_uids())

    # 环境传感器属性
    for sensor in self.environment_sensors:
        uids.extend(sensor.get_all_uids())

    # 机房级别属性
    for attr in self.room_attributes.values():
        if attr.attr_type in ["telemetry", "telesignaling"]:
            uids.append(attr.uid)

    return uids
````
</augment_code_snippet>

<augment_code_snippet path="modules/architecture_module.py" mode="EXCERPT">
````python
# ComputerRoom.get_all_regulable_uids() - 第554-566行
def get_all_regulable_uids(self) -> List[str]:
    uids = []
    # 只收集可用设备的可调控属性
    for device in self.get_all_devices():
        if device.is_available:  # ⚠️ 关键：这里过滤掉不可用设备
            uids.extend(device.get_regulable_uids())
    return uids
````
</augment_code_snippet>

### 8.4 房间查询函数

以下函数用于获取机房对象：

| 函数名称 | 所在类 | 是否过滤 is_available=False | 说明 |
|---------|--------|---------------------------|------|
| `get_all_rooms()` | `DataCenter` | ❌ 不过滤 | 返回所有机房，**包括** `is_available=False` 的机房 |
| `get_available_rooms()` | `DataCenter` | ✅ 过滤 | 只返回 `is_available=True` 的机房 |
| `get_unavailable_rooms()` | `DataCenter` | ✅ 反向过滤 | 只返回 `is_available=False` 的机房 |

**代码示例**：

<augment_code_snippet path="modules/architecture_module.py" mode="EXCERPT">
````python
# DataCenter.get_all_rooms() - 第679-686行
def get_all_rooms(self) -> List[ComputerRoom]:
    return self.computer_rooms  # 直接返回所有机房，不过滤
````
</augment_code_snippet>

<augment_code_snippet path="modules/architecture_module.py" mode="EXCERPT">
````python
# DataCenter.get_available_rooms() - 第751-758行
def get_available_rooms(self) -> List[ComputerRoom]:
    return [room for room in self.computer_rooms if room.is_available]
````
</augment_code_snippet>

### 8.5 系统查询函数

以下函数用于获取空调系统对象：

| 函数名称 | 所在类 | 是否过滤 is_available=False | 说明 |
|---------|--------|---------------------------|------|
| `get_all_systems()` | `ComputerRoom` | ❌ 不过滤 | 返回所有空调系统，**包括** `is_available=False` 的系统 |
| `get_available_systems()` | `ComputerRoom` | ✅ 过滤 | 只返回 `is_available=True` 的系统 |
| `get_unavailable_systems()` | `ComputerRoom` | ✅ 反向过滤 | 只返回 `is_available=False` 的系统 |

**代码示例**：

<augment_code_snippet path="modules/architecture_module.py" mode="EXCERPT">
````python
# ComputerRoom.get_all_systems() - 第508-515行
def get_all_systems(self) -> List[CoolingSystem]:
    return self.air_cooled_systems + self.water_cooled_systems  # 直接返回所有系统，不过滤
````
</augment_code_snippet>

<augment_code_snippet path="modules/architecture_module.py" mode="EXCERPT">
````python
# ComputerRoom.get_available_systems() - 第616-623行
def get_available_systems(self) -> List[CoolingSystem]:
    return [system for system in self.get_all_systems() if system.is_available]
````
</augment_code_snippet>

### 8.6 过滤机制总结表

| 查询类型 | 默认行为 | 是否过滤不可用项 | 推荐使用场景 |
|---------|---------|----------------|-------------|
| **获取设备对象** | 返回所有设备 | ❌ 不过滤 | 需要完整设备列表时（如统计、审计） |
| **获取 UID 列表** | 只返回可用设备的 UID | ✅ **自动过滤** | 数据采集、设备控制（这是最常用的场景） |
| **获取房间对象** | 返回所有房间 | ❌ 不过滤 | 需要完整机房列表时 |
| **获取系统对象** | 返回所有系统 | ❌ 不过滤 | 需要完整系统列表时 |

### 8.7 使用建议

#### 8.7.1 数据采集场景

```python
# ✅ 推荐：使用 get_all_observable_uids() 自动过滤不可用设备
observable_uids = datacenter.get_all_observable_uids()
# 这些 UID 只包含可用设备的属性，可以直接用于数据读取
```

#### 8.7.2 设备控制场景

```python
# ✅ 推荐：使用 get_all_regulable_uids() 自动过滤不可用设备
regulable_uids = datacenter.get_all_regulable_uids()
# 这些 UID 只包含可用设备的可调控属性，避免向不可用设备发送控制指令
```

#### 8.7.3 统计分析场景

```python
# ✅ 推荐：使用 get_all_devices() 获取完整列表，然后手动分类
all_devices = datacenter.get_all_devices()
available_count = sum(1 for d in all_devices if d.is_available)
unavailable_count = sum(1 for d in all_devices if not d.is_available)

# 或者使用专门的过滤函数
available_devices = room.get_available_devices()
unavailable_devices = room.get_unavailable_devices()
```

#### 8.7.4 设备查找场景

```python
# ⚠️ 注意：get_device_by_uid() 不检查 is_available
device = datacenter.get_device_by_uid("ac_001")
if device:
    # 需要手动检查设备是否可用
    if device.is_available:
        print(f"设备 {device.device_name} 可用")
    else:
        print(f"设备 {device.device_name} 不可用")
```

### 8.8 关键注意事项

1. **UID 查询函数的特殊行为**：
   - `ComputerRoom.get_all_observable_uids()` 和 `get_all_regulable_uids()` 会**自动过滤**不可用设备
   - 这是设计上的考虑，确保数据采集和控制只针对可用设备
   - 如果需要获取所有设备（包括不可用）的 UID，需要先用 `get_all_devices()` 获取所有设备，然后手动调用每个设备的 `get_observable_uids()`

2. **设备对象查询的默认行为**：
   - `get_all_devices()`、`get_all_rooms()`、`get_all_systems()` 默认返回所有项目
   - 如果需要只获取可用项目，使用专门的 `get_available_*()` 函数

3. **一致性建议**：
   - 在数据采集和控制场景中，使用 `get_all_observable_uids()` 和 `get_all_regulable_uids()`，它们会自动处理可用性过滤
   - 在统计和审计场景中，使用 `get_all_*()` 函数获取完整列表，然后根据需要手动过滤

---

## 9. 总结

### 8.1 核心设计思想

1. **层次化建模**:
   - 数据中心 → 机房 → 系统 → 设备 → 属性
   - 每一层都有清晰的职责和接口

2. **统一属性管理**:
   - 所有可观测/可调控的数据点都通过 `Attribute` 类统一表示
   - 便于数据读取、存储和控制

3. **容错设计**:
   - 使用 `Optional` 类型和 `.get()` 方法避免异常
   - 使用 `is_available` 标志处理设备故障

4. **便捷查询**:
   - 提供丰富的查询方法(按 uid、类型等)
   - 支持层次化查询(从数据中心查找设备)

### 8.2 使用场景

1. **数据采集**: 使用 `get_all_observable_uids()` 获取所有需要监测的数据点
2. **设备控制**: 使用 `get_all_regulable_uids()` 获取所有可控制的数据点
3. **设备查询**: 使用 `get_device_by_uid()` 快速定位设备
4. **统计分析**: 使用 `get_statistics()` 获取整体概况

### 8.3 扩展建议

如果需要添加新的设备类型:
1. 继承 `Device` 基类
2. 在 `__init__()` 中设置 `device_type`
3. 在文档中说明典型属性

如果需要添加新的系统类型:
1. 继承 `CoolingSystem` 基类
2. 在 `__init__()` 中设置 `system_type`

### 8.4 关键Python语法回顾

| 语法 | 作用 | 示例 |
|------|------|------|
| `@dataclass` | 自动生成 `__init__` 等方法 | `@dataclass class MyClass:` |
| `field(default_factory=dict)` | 为可变类型设置默认值 | `items: list = field(default_factory=list)` |
| `Optional[Type]` | 表示可以是指定类型或 None | `name: Optional[str] = None` |
| `super().__init__()` | 调用父类的初始化方法 | `super().__init__(name="test")` |
| 列表推导式 | 简洁地创建列表 | `[x*2 for x in range(5) if x > 2]` |
| `.get()` 方法 | 安全地获取字典值 | `dict.get(key, default_value)` |
| `.extend()` 方法 | 将列表元素逐个添加 | `list1.extend(list2)` |

---

**文档版本**: 2.0
**最后更新**: 2025-11-08
**适用于**: architecture_module.py
**更新内容**: 新增第8章"查询函数与 is_available 过滤机制详解"，详细说明所有查询函数对 is_available 字段的处理方式

