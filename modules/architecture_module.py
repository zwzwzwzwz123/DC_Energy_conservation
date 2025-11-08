"""
数据中心架构模型模块

本模块定义了数据中心的完整层次结构模型：
- 基础抽象类：Attribute, Device, EnvironmentSensor
- 具体设备类：风冷系统设备、水冷系统设备
- 系统级类：CoolingSystem, AirCooledSystem, WaterCooledSystem
- 容器类：ComputerRoom, DataCenter

设计原则：
1. 层次化建模：清晰体现数据中心 → 机房 → 系统 → 设备 → 属性的层次结构
2. 统一的属性管理：所有可观测/可调控属性通过 Attribute 类统一管理
3. 容错机制：通过 is_available 标志优雅处理缺失设备和属性
4. 便捷访问：提供丰富的查询方法，支持按 uid、类型等方式查找
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Type, Any


# ==================== 基础抽象类 ====================

@dataclass
class Attribute:
    """
    属性基类 - 表示设备或环境的单个可观测/可调控属性
    
    属性:
        name: 属性名称，如"空调开关状态"
        uid: 属性唯一标识符，对应 InfluxDB 的 measurement
        attr_type: 属性类型
            - "telesignaling": 遥信(可观测，状态型)
            - "telemetry": 遥测(可观测，数值型)
            - "telecontrol": 遥控(可调控，状态型)
            - "teleadjusting": 遥调(可调控，数值型)
            - "others": 其他
        field_key: 读取时使用的 field_key，可选值: "value", "abs_value", "origin_value"
        value: 当前值(从 InfluxDB 读取后存储)
        unit: 单位(可选)，如"℃"、"kW"、"rpm"等
        description: 属性描述(可选)
    
    使用示例:
        attr = Attribute(
            name="空调送风温度",
            uid="ac_a1_001_supply_temp",
            attr_type="telemetry",
            field_key="value",
            unit="℃"
        )
    """
    name: str
    uid: str
    attr_type: str  # "telesignaling", "telemetry", "telecontrol", "teleadjusting", "others"
    field_key: str = "value"
    value: Optional[float] = None
    unit: Optional[str] = None
    description: Optional[str] = None


@dataclass
class Device:
    """
    设备基类 - 所有设备的抽象父类
    
    属性:
        device_name: 设备名称，如"A1-AC-001"
        device_uid: 设备唯一标识符
        device_type: 设备类型，如"AC_AirCooled", "COMP", "CH"等
        location: 设备位置描述(可选)
        attributes: 属性字典 {属性名称: Attribute对象}
        is_available: 设备是否可用(用于容错)，默认为 True
    
    方法:
        add_attribute: 添加属性
        get_attribute: 获取属性(容错：属性不存在返回None)
        get_observable_uids: 获取所有可观测属性的uid列表
        get_regulable_uids: 获取所有可调控属性的uid列表
    """
    device_name: str
    device_uid: str
    device_type: str
    location: Optional[str] = None
    attributes: Dict[str, Attribute] = field(default_factory=dict)
    is_available: bool = True

    def add_attribute(self, attr: Attribute) -> None:
        """添加属性到设备"""
        self.attributes[attr.name] = attr

    def get_attribute(self, attr_name: str) -> Optional[Attribute]:
        """
        获取属性(容错：属性不存在返回None)
        
        参数:
            attr_name: 属性名称
        
        返回:
            Optional[Attribute]: 属性对象，不存在则返回 None
        """
        return self.attributes.get(attr_name)

    def get_observable_uids(self) -> List[str]:
        """
        获取所有可观测属性的uid列表(用于数据读取)

        返回:
            List[str]: 可观测属性的 uid 列表(包括 telemetry 和 telesignaling)
        """
        return [attr.uid for attr in self.attributes.values()
                if attr.attr_type in ["telemetry", "telesignaling"]]

    def get_regulable_uids(self) -> List[str]:
        """
        获取所有可调控属性的uid列表(用于控制指令写入)

        返回:
            List[str]: 可调控属性的 uid 列表(包括 telecontrol 和 teleadjusting)
        """
        return [attr.uid for attr in self.attributes.values()
                if attr.attr_type in ["telecontrol", "teleadjusting"]]


@dataclass
class EnvironmentSensor:
    """
    环境传感器类 - 用于温度、湿度等环境监测

    属性:
        sensor_name: 传感器名称
        sensor_uid: 传感器唯一标识符
        sensor_type: 传感器类型，默认为"environment"
        location: 传感器位置(可选)
        attributes: 属性字典 {属性名称: Attribute对象}

    方法:
        add_attribute: 添加属性
        get_attribute: 获取属性
        get_all_uids: 获取所有属性的uid列表
    """
    sensor_name: str
    sensor_uid: str
    sensor_type: str = "environment"
    location: Optional[str] = None
    attributes: Dict[str, Attribute] = field(default_factory=dict)

    def add_attribute(self, attr: Attribute) -> None:
        """添加属性到传感器"""
        self.attributes[attr.name] = attr

    def get_attribute(self, attr_name: str) -> Optional[Attribute]:
        """获取属性(容错)"""
        return self.attributes.get(attr_name)

    def get_all_uids(self) -> List[str]:
        """
        获取所有属性的uid列表
        
        返回:
            List[str]: 所有属性的 uid 列表
        """
        return [attr.uid for attr in self.attributes.values()]


# ==================== 风冷系统设备类 ====================

class AirConditioner_AirCooled(Device):
    """
    风冷系统 - 室内空调
    
    典型属性包括：
    - 遥信/遥测：空调开关状态、送风温度、回风温度、风机转速、有功功率等
    - 遥控/遥调：开机设定点、关机设定点、送风温度设定点、风机转速设定点等
    """

    def __init__(self, device_name: str, device_uid: str, location: str = None, is_available: bool = True):
        super().__init__(
            device_name=device_name,
            device_uid=device_uid,
            device_type="AC_AirCooled",
            location=location,
            is_available=is_available
        )


class Compressor(Device):
    """
    风冷系统 - 压缩机

    典型属性包括：
    - 遥信/遥测：开关状态、频率、有功功率、累计能耗等
    - 遥控/遥调：开机设定点、关机设定点、频率设定点等
    """

    def __init__(self, device_name: str, device_uid: str, location: str = None, is_available: bool = True):
        super().__init__(
            device_name=device_name,
            device_uid=device_uid,
            device_type="COMP",
            location=location,
            is_available=is_available
        )


class Condenser(Device):
    """
    风冷系统 - 冷凝器

    典型属性包括：
    - 遥信/遥测：温度、压力、风机转速、有功功率等
    - 遥控/遥调：风机最小/最大转速设定点等
    """

    def __init__(self, device_name: str, device_uid: str, location: str = None, is_available: bool = True):
        super().__init__(
            device_name=device_name,
            device_uid=device_uid,
            device_type="COND",
            location=location,
            is_available=is_available
        )


class ExpansionValve(Device):
    """
    风冷系统 - 膨胀阀

    典型属性包括：
    - 遥信/遥测：开度
    - 遥控/遥调：开度设定点
    """

    def __init__(self, device_name: str, device_uid: str, location: str = None, is_available: bool = True):
        super().__init__(
            device_name=device_name,
            device_uid=device_uid,
            device_type="EV",
            location=location,
            is_available=is_available
        )


# ==================== 水冷系统设备类 ====================

class AirConditioner_WaterCooled(Device):
    """
    水冷系统 - 室内空调

    典型属性包括：
    - 遥信/遥测：开关状态、送风温度、回风温度、风机转速、水阀开度、
                冷冻水出/回水温度、有功功率等
    - 遥控/遥调：开机设定点、关机设定点、送风温度设定点、风机转速设定点、
                水阀开度设定点等
    """

    def __init__(self, device_name: str, device_uid: str, location: str = None, is_available: bool = True):
        super().__init__(
            device_name=device_name,
            device_uid=device_uid,
            device_type="AC_WaterCooled",
            location=location,
            is_available=is_available
        )


class Chiller(Device):
    """
    水冷系统 - 冷水机组

    典型属性包括：
    - 遥信/遥测：开关状态、负荷百分比、用电量、冷冻水出/回水温度、
                冷却水出/回水温度、有功功率等
    - 遥控/遥调：开机设定点、关机设定点、冷冻水出水温度设定点等
    """

    def __init__(self, device_name: str, device_uid: str, location: str = None, is_available: bool = True):
        super().__init__(
            device_name=device_name,
            device_uid=device_uid,
            device_type="CH",
            location=location,
            is_available=is_available
        )


class ChilledWaterPump(Device):
    """
    水冷系统 - 冷冻水泵

    典型属性包括：
    - 遥信/遥测：开关状态、用电量、压力、频率反馈、有功功率等
    - 遥控/遥调：开机设定点、关机设定点、频率设定点、压差设定点等
    """

    def __init__(self, device_name: str, device_uid: str, location: str = None, is_available: bool = True):
        super().__init__(
            device_name=device_name,
            device_uid=device_uid,
            device_type="CHWP",
            location=location,
            is_available=is_available
        )


class CoolingWaterPump(Device):
    """
    水冷系统 - 冷却水泵

    典型属性包括：
    - 遥信/遥测：开关状态、用电量、压力、频率反馈、有功功率等
    - 遥控/遥调：开机设定点、关机设定点、频率设定点、压差设定点等
    """

    def __init__(self, device_name: str, device_uid: str, location: str = None, is_available: bool = True):
        super().__init__(
            device_name=device_name,
            device_uid=device_uid,
            device_type="CWP",
            location=location,
            is_available=is_available
        )


class CoolingTower(Device):
    """
    水冷系统 - 冷却塔

    典型属性包括：
    - 遥信/遥测：开关状态、出水温度、回水温度、风机转速、有功功率等
    - 遥控/遥调：开机设定点、关机设定点、风机转速设定点、出水温度设定点等
    """

    def __init__(self, device_name: str, device_uid: str, location: str = None, is_available: bool = True):
        super().__init__(
            device_name=device_name,
            device_uid=device_uid,
            device_type="CT",
            location=location,
            is_available=is_available
        )


# ==================== 系统级类 ====================

@dataclass
class CoolingSystem:
    """
    空调系统基类

    属性:
        system_name: 系统名称
        system_uid: 系统唯一标识符
        system_type: 系统类型，"AirCooled" 或 "WaterCooled"
        devices: 设备字典 {设备类型: [Device对象列表]}
        is_available: 系统是否可用(用于容错)，默认为 True

    方法:
        add_device: 添加设备到系统
        get_devices_by_type: 获取指定类型的所有设备
        get_all_devices: 获取系统内所有设备
    """
    system_name: str
    system_uid: str
    system_type: str
    devices: Dict[str, List[Device]] = field(default_factory=dict)
    is_available: bool = True

    def add_device(self, device: Device) -> None:
        """
        添加设备到系统

        参数:
            device: 设备对象
        """
        if device.device_type not in self.devices:
            self.devices[device.device_type] = []
        self.devices[device.device_type].append(device)

    def get_devices_by_type(self, device_type: str) -> List[Device]:
        """
        获取指定类型的所有设备

        参数:
            device_type: 设备类型，如"AC_AirCooled", "COMP"等

        返回:
            List[Device]: 设备列表，不存在则返回空列表
        """
        return self.devices.get(device_type, [])

    def get_all_devices(self, include_unavailable: bool = True) -> List[Device]:
        """
        获取系统内所有设备

        参数:
            include_unavailable: 是否包含不可用的设备，默认 True

        返回:
            List[Device]: 设备列表（根据参数过滤）
        """
        all_devices = []
        for device_list in self.devices.values():
            all_devices.extend(device_list)

        # 根据参数过滤不可用的设备
        if not include_unavailable:
            all_devices = [d for d in all_devices if d.is_available]

        return all_devices


class AirCooledSystem(CoolingSystem):
    """
    风冷空调系统

    包含设备类型：
    - AC_AirCooled: 室内空调
    - COMP: 压缩机
    - COND: 冷凝器
    - EV: 膨胀阀
    """

    def __init__(self, system_name: str, system_uid: str, is_available: bool = True):
        super().__init__(
            system_name=system_name,
            system_uid=system_uid,
            system_type="AirCooled",
            is_available=is_available
        )


class WaterCooledSystem(CoolingSystem):
    """
    水冷空调系统

    包含设备类型：
    - AC_WaterCooled: 室内空调
    - CH: 冷水机组
    - CHWP: 冷冻水泵
    - CWP: 冷却水泵
    - CT: 冷却塔
    """

    def __init__(self, system_name: str, system_uid: str, is_available: bool = True):
        super().__init__(
            system_name=system_name,
            system_uid=system_uid,
            system_type="WaterCooled",
            is_available=is_available
        )


# ==================== 容器类 ====================

@dataclass
class ComputerRoom:
    """
    机房类 - 表示数据中心内的单个机房

    属性:
        room_name: 机房名称
        room_uid: 机房唯一标识符
        room_type: 机房类型，"AirCooled"(风冷) / "WaterCooled"(水冷) / "Mixed"(混合)
        location: 机房位置(可选)
        air_cooled_systems: 风冷空调系统列表
        water_cooled_systems: 水冷空调系统列表
        environment_sensors: 环境传感器列表
        room_attributes: 机房级别属性字典(如总能耗)
        is_available: 机房是否可用(用于容错)

    方法:
        add_air_cooled_system: 添加风冷空调系统
        add_water_cooled_system: 添加水冷空调系统
        add_environment_sensor: 添加环境传感器
        add_room_attribute: 添加机房级别属性
        get_all_systems: 获取机房内所有空调系统
        get_all_devices: 获取机房内所有设备
        get_all_observable_uids: 获取机房内所有可观测属性的uid列表
        get_all_regulable_uids: 获取机房内所有可调控属性的uid列表
        get_device_by_uid: 根据设备uid查找设备
        get_system_by_uid: 根据系统uid查找系统
    """
    room_name: str
    room_uid: str
    room_type: str  # "AirCooled", "WaterCooled", "Mixed"
    location: Optional[str] = None
    air_cooled_systems: List[AirCooledSystem] = field(default_factory=list)
    water_cooled_systems: List[WaterCooledSystem] = field(default_factory=list)
    environment_sensors: List[EnvironmentSensor] = field(default_factory=list)
    room_attributes: Dict[str, Attribute] = field(default_factory=dict)
    is_available: bool = True

    def add_air_cooled_system(self, system: AirCooledSystem) -> None:
        """添加风冷空调系统"""
        self.air_cooled_systems.append(system)

    def add_water_cooled_system(self, system: WaterCooledSystem) -> None:
        """添加水冷空调系统"""
        self.water_cooled_systems.append(system)

    def add_environment_sensor(self, sensor: EnvironmentSensor) -> None:
        """添加环境传感器"""
        self.environment_sensors.append(sensor)

    def add_room_attribute(self, attr: Attribute) -> None:
        """添加机房级别属性"""
        self.room_attributes[attr.name] = attr

    def get_all_systems(self, include_unavailable: bool = False) -> List[CoolingSystem]:
        """
        获取机房内所有空调系统

        参数:
            include_unavailable: 是否包含不可用的系统，默认 False（只返回可用系统）

        返回:
            List[CoolingSystem]: 空调系统列表（根据参数过滤）
        """
        all_systems = self.air_cooled_systems + self.water_cooled_systems

        if not include_unavailable:
            all_systems = [s for s in all_systems if s.is_available]

        return all_systems

    def get_all_devices(self, include_unavailable: bool = False) -> List[Device]:
        """
        获取机房内所有设备

        参数:
            include_unavailable: 是否包含不可用的设备，默认 False（只返回可用设备）

        返回:
            List[Device]: 设备列表（根据参数过滤）
        """
        devices = []
        for system in self.get_all_systems(include_unavailable=include_unavailable):
            devices.extend(system.get_all_devices(include_unavailable=include_unavailable))
        return devices

    def get_all_observable_uids(self, include_unavailable: bool = False) -> List[str]:
        """
        获取机房内所有可观测属性的uid列表(包括设备、传感器、机房属性)

        参数:
            include_unavailable: 是否包含不可用设备的属性，默认 False（只返回可用设备的属性）

        返回:
            List[str]: 所有可观测属性的 uid 列表
        """
        uids = []

        # 设备属性（根据参数决定是否包含不可用设备）
        for device in self.get_all_devices(include_unavailable=include_unavailable):
            uids.extend(device.get_observable_uids())

        # 环境传感器属性
        for sensor in self.environment_sensors:
            uids.extend(sensor.get_all_uids())

        # 机房级别属性
        for attr in self.room_attributes.values():
            if attr.attr_type in ["telemetry", "telesignaling"]:
                uids.append(attr.uid)

        return uids

    def get_all_regulable_uids(self, include_unavailable: bool = False) -> List[str]:
        """
        获取机房内所有可调控属性的uid列表

        参数:
            include_unavailable: 是否包含不可用设备的属性，默认 False（只返回可用设备的属性）

        返回:
            List[str]: 所有可调控属性的 uid 列表
        """
        uids = []
        # 根据参数决定是否包含不可用设备的可调控属性
        for device in self.get_all_devices(include_unavailable=include_unavailable):
            uids.extend(device.get_regulable_uids())
        return uids

    def get_device_by_uid(self, device_uid: str) -> Optional[Device]:
        """
        根据设备uid查找设备(容错)

        参数:
            device_uid: 设备唯一标识符

        返回:
            Optional[Device]: 设备对象，不存在则返回 None
        """
        for device in self.get_all_devices(include_unavailable=True):
            if device.device_uid == device_uid:
                return device
        return None

    def get_system_by_uid(self, system_uid: str) -> Optional[CoolingSystem]:
        """
        根据系统uid查找系统(容错)

        参数:
            system_uid: 系统唯一标识符

        返回:
            Optional[CoolingSystem]: 系统对象，不存在则返回 None
        """
        for system in self.get_all_systems(include_unavailable=True):
            if system.system_uid == system_uid:
                return system
        return None

    def get_available_devices(self) -> List[Device]:
        """
        获取机房内所有可用的设备

        返回:
            List[Device]: 可用设备的列表
        """
        return self.get_all_devices(include_unavailable=False)

    def get_unavailable_devices(self) -> List[Device]:
        """
        获取机房内所有不可用的设备

        返回:
            List[Device]: 不可用设备的列表
        """
        return [device for device in self.get_all_devices(include_unavailable=True) if not device.is_available]

    def get_available_systems(self) -> List[CoolingSystem]:
        """
        获取机房内所有可用的空调系统

        返回:
            List[CoolingSystem]: 可用系统的列表
        """
        return self.get_all_systems(include_unavailable=False)

    def get_unavailable_systems(self) -> List[CoolingSystem]:
        """
        获取机房内所有不可用的空调系统

        返回:
            List[CoolingSystem]: 不可用系统的列表
        """
        return [system for system in self.get_all_systems(include_unavailable=True) if not system.is_available]


@dataclass
class DataCenter:
    """
    数据中心类 - 顶层容器类

    属性:
        dc_name: 数据中心名称
        dc_uid: 数据中心唯一标识符
        location: 数据中心位置(可选)
        computer_rooms: 机房列表
        environment_sensors: 数据中心级别环境传感器列表
        dc_attributes: 数据中心级别属性字典(如总能耗)

    方法:
        add_computer_room: 添加机房
        add_environment_sensor: 添加环境传感器
        add_dc_attribute: 添加数据中心级别属性
        get_all_rooms: 获取所有机房
        get_all_devices: 获取数据中心内所有设备
        get_all_observable_uids: 获取数据中心内所有可观测属性的uid列表
        get_all_regulable_uids: 获取数据中心内所有可调控属性的uid列表
        get_room_by_uid: 根据机房uid查找机房
        get_device_by_uid: 根据设备uid在整个数据中心查找设备
        get_statistics: 获取数据中心统计信息
    """
    dc_name: str
    dc_uid: str
    location: Optional[str] = None
    computer_rooms: List[ComputerRoom] = field(default_factory=list)
    environment_sensors: List[EnvironmentSensor] = field(default_factory=list)
    dc_attributes: Dict[str, Attribute] = field(default_factory=dict)

    def add_computer_room(self, room: ComputerRoom) -> None:
        """添加机房"""
        self.computer_rooms.append(room)

    def add_environment_sensor(self, sensor: EnvironmentSensor) -> None:
        """添加环境传感器"""
        self.environment_sensors.append(sensor)

    def add_dc_attribute(self, attr: Attribute) -> None:
        """添加数据中心级别属性"""
        self.dc_attributes[attr.name] = attr

    def get_all_rooms(self, include_unavailable: bool = False) -> List[ComputerRoom]:
        """
        获取所有机房

        参数:
            include_unavailable: 是否包含不可用的机房，默认 False（只返回可用机房）

        返回:
            List[ComputerRoom]: 机房列表（根据参数过滤）
        """
        if not include_unavailable:
            return [room for room in self.computer_rooms if room.is_available]
        return self.computer_rooms

    def get_all_devices(self, include_unavailable: bool = False) -> List[Device]:
        """
        获取数据中心内所有设备

        参数:
            include_unavailable: 是否包含不可用的设备，默认 False（只返回可用设备）

        返回:
            List[Device]: 设备列表（根据参数过滤）
        """
        devices = []
        for room in self.get_all_rooms(include_unavailable=include_unavailable):
            devices.extend(room.get_all_devices(include_unavailable=include_unavailable))
        return devices

    def get_all_observable_uids(self, include_unavailable: bool = False) -> List[str]:
        """
        获取数据中心内所有可观测属性的uid列表

        参数:
            include_unavailable: 是否包含不可用设备的属性，默认 False（只返回可用设备的属性）

        返回:
            List[str]: 所有遥测属性的 uid 列表
        """
        uids = []

        # 机房属性（根据参数决定是否包含不可用机房和设备）
        for room in self.get_all_rooms(include_unavailable=include_unavailable):
            uids.extend(room.get_all_observable_uids(include_unavailable=include_unavailable))

        # 数据中心级别环境传感器
        for sensor in self.environment_sensors:
            uids.extend(sensor.get_all_uids())

        # 数据中心级别属性
        for attr in self.dc_attributes.values():
            if attr.attr_type in ["telemetry", "telesignaling"]:
                uids.append(attr.uid)

        return uids

    def get_all_regulable_uids(self, include_unavailable: bool = False) -> List[str]:
        """
        获取数据中心内所有可调控属性的uid列表

        参数:
            include_unavailable: 是否包含不可用设备的属性，默认 False（只返回可用设备的属性）

        返回:
            List[str]: 所有控制属性的 uid 列表
        """
        uids = []
        for room in self.get_all_rooms(include_unavailable=include_unavailable):
            uids.extend(room.get_all_regulable_uids(include_unavailable=include_unavailable))
        return uids

    def get_room_by_uid(self, room_uid: str) -> Optional[ComputerRoom]:
        """
        根据机房uid查找机房(容错)

        参数:
            room_uid: 机房唯一标识符

        返回:
            Optional[ComputerRoom]: 机房对象，不存在则返回 None
        """
        for room in self.computer_rooms:
            if room.room_uid == room_uid:
                return room
        return None

    def get_available_rooms(self) -> List[ComputerRoom]:
        """
        获取所有可用的机房

        返回:
            List[ComputerRoom]: 可用机房的列表
        """
        return self.get_all_rooms(include_unavailable=False)

    def get_unavailable_rooms(self) -> List[ComputerRoom]:
        """
        获取所有不可用的机房

        返回:
            List[ComputerRoom]: 不可用机房的列表
        """
        return [room for room in self.get_all_rooms(include_unavailable=True) if not room.is_available]

    def get_device_by_uid(self, device_uid: str) -> Optional[Device]:
        """
        根据设备uid在整个数据中心查找设备(容错)

        参数:
            device_uid: 设备唯一标识符

        返回:
            Optional[Device]: 设备对象，不存在则返回 None
        """
        for room in self.computer_rooms:
            device = room.get_device_by_uid(device_uid)
            if device:
                return device
        return None

    def get_statistics(self) -> Dict[str, Any]:
        """
        获取数据中心统计信息

        返回:
            Dict: 统计信息字典，包含：
                - total_rooms: 机房总数
                - available_rooms: 可用机房数量
                - unavailable_rooms: 不可用机房数量
                - total_air_cooled_systems: 风冷系统总数
                - available_air_cooled_systems: 可用风冷系统数量
                - unavailable_air_cooled_systems: 不可用风冷系统数量
                - total_water_cooled_systems: 水冷系统总数
                - available_water_cooled_systems: 可用水冷系统数量
                - unavailable_water_cooled_systems: 不可用水冷系统数量
                - total_devices: 设备总数
                - available_devices: 可用设备数量
                - unavailable_devices: 不可用设备数量
                - total_observable_points: 可观测点总数（只统计可用设备）
                - total_regulable_points: 可调控点总数（只统计可用设备）
        """
        stats = {
            "total_rooms": len(self.computer_rooms),
            "available_rooms": 0,
            "unavailable_rooms": 0,
            "total_air_cooled_systems": 0,
            "available_air_cooled_systems": 0,
            "unavailable_air_cooled_systems": 0,
            "total_water_cooled_systems": 0,
            "available_water_cooled_systems": 0,
            "unavailable_water_cooled_systems": 0,
            "total_devices": 0,
            "available_devices": 0,
            "unavailable_devices": 0,
            # 遥测点和控制点只统计可用设备的（默认 include_unavailable=False）
            "total_observable_points": len(self.get_all_observable_uids(include_unavailable=False)),
            "total_regulable_points": len(self.get_all_regulable_uids(include_unavailable=False))
        }

        # 遍历所有机房（包括不可用的）以进行完整统计
        for room in self.get_all_rooms(include_unavailable=True):
            # 统计机房可用性
            if room.is_available:
                stats["available_rooms"] += 1
            else:
                stats["unavailable_rooms"] += 1

            # 统计风冷系统（包括不可用的）
            for system in room.air_cooled_systems:
                stats["total_air_cooled_systems"] += 1
                if system.is_available:
                    stats["available_air_cooled_systems"] += 1
                else:
                    stats["unavailable_air_cooled_systems"] += 1

            # 统计水冷系统（包括不可用的）
            for system in room.water_cooled_systems:
                stats["total_water_cooled_systems"] += 1
                if system.is_available:
                    stats["available_water_cooled_systems"] += 1
                else:
                    stats["unavailable_water_cooled_systems"] += 1

            # 统计设备可用性（包括不可用的）
            for device in room.get_all_devices(include_unavailable=True):
                stats["total_devices"] += 1
                if device.is_available:
                    stats["available_devices"] += 1
                else:
                    stats["unavailable_devices"] += 1

        return stats
