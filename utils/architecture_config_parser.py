"""
数据中心配置解析器模块

本模块负责解析 uid_config.yaml 配置文件，并构建完整的 DataCenter 对象层次结构。

主要功能：
1. 读取并解析 YAML 配置文件
2. 构建数据中心、机房、系统、设备、属性的完整层次结构
3. 提供完整的异常处理和容错机制
4. 记录解析过程中的关键信息和错误

"""

import logging
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional, Type

from modules.architecture_module import (
    DataCenter,
    ComputerRoom,
    CoolingSystem,
    AirCooledSystem,
    WaterCooledSystem,
    Device,
    AirConditioner_AirCooled,
    Compressor,
    Condenser,
    ExpansionValve,
    AirConditioner_WaterCooled,
    Chiller,
    ChilledWaterPump,
    CoolingWaterPump,
    CoolingTower,
    EnvironmentSensor,
    Attribute
)


class DataCenterConfigParser:
    """
    数据中心配置解析器

    功能：
        - 解析 uid_config 配置字典
        - 构建完整的 DataCenter 对象层次结构
        - 提供容错机制：单个设备或属性解析失败不影响整体

    属性：
        config: 配置字典（从 uid_config.yaml 加载）
        logger: 日志器实例

    方法：
        parse_datacenter: 解析整个数据中心配置并返回 DataCenter 对象
    """

    def __init__(self, uid_config: Dict, logger: logging.Logger):
        """
        初始化配置解析器

        参数:
            uid_config: uid_config 配置字典（已从 uid_config.yaml 加载）
            logger: 日志器实例

        异常:
            ValueError: 配置字典为空或格式错误
        """
        if not uid_config:
            error_msg = "uid_config 配置字典为空"
            logger.error(error_msg)
            raise ValueError(error_msg)

        self.config: Dict = uid_config
        self.logger: logging.Logger = logger

        self.logger.info("数据中心配置解析器初始化成功")

    def parse_datacenter(self) -> DataCenter:
        """
        解析整个数据中心配置并返回 DataCenter 对象

        返回:
            DataCenter: 完整的数据中心对象

        异常:
            ValueError: 配置文件缺少必填字段
        """
        if not self.config or 'datacenter' not in self.config:
            error_msg = "配置文件缺少 'datacenter' 字段"
            self.logger.error(error_msg)
            raise ValueError(error_msg)

        dc_config = self.config['datacenter']

        # 验证必填字段
        required_fields = ['name', 'uid']
        for field in required_fields:
            if field not in dc_config:
                error_msg = f"数据中心配置缺少必填字段: {field}"
                self.logger.error(error_msg)
                raise ValueError(error_msg)

        # 创建 DataCenter 对象
        datacenter = DataCenter(
            dc_name=dc_config['name'],
            dc_uid=dc_config['uid'],
            location=dc_config.get('location')
        )

        self.logger.info(f"开始解析数据中心: {datacenter.dc_name} (UID: {datacenter.dc_uid})")

        # 解析数据中心级别的环境传感器
        if 'environment_sensors' in dc_config:
            for sensor_config in dc_config['environment_sensors']:
                try:
                    sensor = self._parse_environment_sensor(sensor_config)
                    datacenter.add_environment_sensor(sensor)
                    self.logger.info(f"  添加数据中心环境传感器: {sensor.sensor_name}")
                except Exception as e:
                    self.logger.warning(f"  解析数据中心环境传感器（{sensor.sensor_name}）失败: {e}，跳过该传感器")

        # 解析数据中心级别的属性
        if 'datacenter_attributes' in dc_config:
            for attr_config in dc_config['datacenter_attributes']:
                try:
                    attr = self._parse_attribute(attr_config)
                    datacenter.add_dc_attribute(attr)
                    self.logger.info(f"  添加数据中心属性: {attr.name}")
                except Exception as e:
                    self.logger.warning(f"  解析数据中心属性（{attr.name}）失败: {e}，跳过该属性")

        # 解析机房列表
        if 'computer_rooms' in dc_config:
            for room_config in dc_config['computer_rooms']:
                try:
                    room = self._parse_computer_room(room_config)
                    datacenter.add_computer_room(room)
                    self.logger.info(f"  成功解析机房: {room.room_name} (UID: {room.room_uid})")
                except Exception as e:
                    self.logger.error(f"  解析机房（{room.room_name}）失败: {e}，跳过该机房")

        # 输出统计信息
        stats = datacenter.get_statistics()
        self.logger.info(f"数据中心解析完成: {datacenter.dc_name}")
        self.logger.info(f"  - 机房总数: {stats['total_rooms']}")
        self.logger.info(f"  - 风冷系统总数: {stats['total_air_cooled_systems']}")
        self.logger.info(f"  - 水冷系统总数: {stats['total_water_cooled_systems']}")
        self.logger.info(f"  - 设备总数: {stats['total_devices']}")
        self.logger.info(f"  - 可观测点总数: {stats['total_observable_points']}")
        self.logger.info(f"  - 可调控点总数: {stats['total_regulable_points']}")

        return datacenter

    def _parse_computer_room(self, room_config: Dict) -> ComputerRoom:
        """
        解析单个机房配置
        
        参数:
            room_config: 机房配置字典
        
        返回:
            ComputerRoom: 机房对象
        
        异常:
            ValueError: 配置缺少必填字段
        """
        # 验证必填字段
        required_fields = ['room_name', 'room_uid', 'room_type']
        for field in required_fields:
            if field not in room_config:
                raise ValueError(f"机房配置缺少必填字段: {field}")

        # 创建 ComputerRoom 对象
        room = ComputerRoom(
            room_name=room_config['room_name'],
            room_uid=room_config['room_uid'],
            room_type=room_config['room_type'],
            location=room_config.get('location'),
            is_available=room_config.get('is_available', True)
        )

        self.logger.info(f" 开始解析机房: {room.room_name}")

        # 解析机房级别的环境传感器
        if 'environment_sensors' in room_config:
            for sensor_config in room_config['environment_sensors']:
                try:
                    sensor = self._parse_environment_sensor(sensor_config)
                    room.add_environment_sensor(sensor)
                    self.logger.info(f"    添加环境传感器: {sensor.sensor_name}")
                except Exception as e:
                    self.logger.warning(f"    解析环境传感器失败: {e}，跳过该传感器")

        # 解析机房级别的属性
        if 'room_attributes' in room_config:
            for attr_config in room_config['room_attributes']:
                try:
                    attr = self._parse_attribute(attr_config)
                    room.add_room_attribute(attr)
                    self.logger.info(f"    添加机房属性: {attr.name}")
                except Exception as e:
                    self.logger.warning(f"    解析机房属性失败: {e}，跳过该属性")

        # 解析风冷系统
        if 'air_cooled_systems' in room_config:
            for system_config in room_config['air_cooled_systems']:
                try:
                    system = self._parse_air_cooled_system(system_config)
                    room.add_air_cooled_system(system)
                    self.logger.info(f"    添加风冷系统: {system.system_name}")
                except Exception as e:
                    self.logger.warning(f"    解析风冷系统失败: {e}，跳过该系统")

        # 解析水冷系统
        if 'water_cooled_systems' in room_config:
            for system_config in room_config['water_cooled_systems']:
                try:
                    system = self._parse_water_cooled_system(system_config)
                    room.add_water_cooled_system(system)
                    self.logger.info(f"    添加水冷系统: {system.system_name}")
                except Exception as e:
                    self.logger.warning(f"    解析水冷系统失败: {e}，跳过该系统")

        return room

    def _parse_air_cooled_system(self, system_config: Dict) -> AirCooledSystem:
        """
        解析风冷系统配置

        参数:
            system_config: 风冷系统配置字典

        返回:
            AirCooledSystem: 风冷系统对象

        异常:
            ValueError: 配置缺少必填字段
        """
        # 验证必填字段
        required_fields = ['system_name', 'system_uid']
        for field in required_fields:
            if field not in system_config:
                raise ValueError(f"风冷系统配置缺少必填字段: {field}")

        # 创建 AirCooledSystem 对象
        system = AirCooledSystem(
            system_name=system_config['system_name'],
            system_uid=system_config['system_uid'],
            is_available=system_config.get('is_available', True)
        )

        self.logger.info(f"    开始解析风冷系统: {system.system_name}")

        # 解析室内空调
        if 'air_conditioners' in system_config:
            for device_config in system_config['air_conditioners']:
                try:
                    device = self._parse_device(device_config, AirConditioner_AirCooled)
                    system.add_device(device)
                    self.logger.info(f"      添加室内空调: {device.device_name}")
                except Exception as e:
                    self.logger.warning(f"      解析室内空调失败: {e}，跳过该设备")

        # 解析压缩机
        if 'compressors' in system_config:
            for device_config in system_config['compressors']:
                try:
                    device = self._parse_device(device_config, Compressor)
                    system.add_device(device)
                    self.logger.info(f"      添加压缩机: {device.device_name}")
                except Exception as e:
                    self.logger.warning(f"      解析压缩机失败: {e}，跳过该设备")

        # 解析冷凝器
        if 'condensers' in system_config:
            for device_config in system_config['condensers']:
                try:
                    device = self._parse_device(device_config, Condenser)
                    system.add_device(device)
                    self.logger.info(f"      添加冷凝器: {device.device_name}")
                except Exception as e:
                    self.logger.warning(f"      解析冷凝器失败: {e}，跳过该设备")

        # 解析膨胀阀
        if 'expansion_valves' in system_config:
            for device_config in system_config['expansion_valves']:
                try:
                    device = self._parse_device(device_config, ExpansionValve)
                    system.add_device(device)
                    self.logger.info(f"      添加膨胀阀: {device.device_name}")
                except Exception as e:
                    self.logger.warning(f"      解析膨胀阀失败: {e}，跳过该设备")

        return system

    def _parse_water_cooled_system(self, system_config: Dict) -> WaterCooledSystem:
        """
        解析水冷系统配置

        参数:
            system_config: 水冷系统配置字典

        返回:
            WaterCooledSystem: 水冷系统对象

        异常:
            ValueError: 配置缺少必填字段
        """
        # 验证必填字段
        required_fields = ['system_name', 'system_uid']
        for field in required_fields:
            if field not in system_config:
                raise ValueError(f"水冷系统配置缺少必填字段: {field}")

        # 创建 WaterCooledSystem 对象
        system = WaterCooledSystem(
            system_name=system_config['system_name'],
            system_uid=system_config['system_uid'],
            is_available=system_config.get('is_available', True)
        )

        self.logger.info(f"    开始解析水冷系统: {system.system_name}")

        # 解析室内空调
        if 'air_conditioners' in system_config:
            for device_config in system_config['air_conditioners']:
                try:
                    device = self._parse_device(device_config, AirConditioner_WaterCooled)
                    system.add_device(device)
                    self.logger.info(f"      添加室内空调: {device.device_name}")
                except Exception as e:
                    self.logger.warning(f"      解析室内空调失败: {e}，跳过该设备")

        # 解析冷水机组
        if 'chillers' in system_config:
            for device_config in system_config['chillers']:
                try:
                    device = self._parse_device(device_config, Chiller)
                    system.add_device(device)
                    self.logger.info(f"      添加冷水机组: {device.device_name}")
                except Exception as e:
                    self.logger.warning(f"      解析冷水机组失败: {e}，跳过该设备")

        # 解析冷冻水泵
        if 'chilled_water_pumps' in system_config:
            for device_config in system_config['chilled_water_pumps']:
                try:
                    device = self._parse_device(device_config, ChilledWaterPump)
                    system.add_device(device)
                    self.logger.info(f"      添加冷冻水泵: {device.device_name}")
                except Exception as e:
                    self.logger.warning(f"      解析冷冻水泵失败: {e}，跳过该设备")

        # 解析冷却水泵
        if 'cooling_water_pumps' in system_config:
            for device_config in system_config['cooling_water_pumps']:
                try:
                    device = self._parse_device(device_config, CoolingWaterPump)
                    system.add_device(device)
                    self.logger.info(f"      添加冷却水泵: {device.device_name}")
                except Exception as e:
                    self.logger.warning(f"      解析冷却水泵失败: {e}，跳过该设备")

        # 解析冷却塔
        if 'cooling_towers' in system_config:
            for device_config in system_config['cooling_towers']:
                try:
                    device = self._parse_device(device_config, CoolingTower)
                    system.add_device(device)
                    self.logger.info(f"      添加冷却塔: {device.device_name}")
                except Exception as e:
                    self.logger.warning(f"      解析冷却塔失败: {e}，跳过该设备")

        return system

    def _parse_device(self, device_config: Dict, device_class: Type[Device]) -> Device:
        """
        解析设备配置（通用方法）

        参数:
            device_config: 设备配置字典
            device_class: 设备类（如 AirConditioner_AirCooled, Compressor 等）

        返回:
            Device: 设备对象

        异常:
            ValueError: 配置缺少必填字段
        """
        # 验证必填字段
        required_fields = ['device_name', 'device_uid']
        for field in required_fields:
            if field not in device_config:
                raise ValueError(f"设备配置缺少必填字段: {field}")

        # 创建设备对象
        device = device_class(
            device_name=device_config['device_name'],
            device_uid=device_config['device_uid'],
            location=device_config.get('location'),
            is_available=device_config.get('is_available', True)
        )

        # 解析设备属性
        if 'attributes' in device_config:
            for attr_config in device_config['attributes']:
                try:
                    attr = self._parse_attribute(attr_config)
                    device.add_attribute(attr)
                    self.logger.debug(f"        添加设备属性: {attr.name}")
                except Exception as e:
                    self.logger.warning(f"        解析设备属性失败: {e}，跳过该属性")

        return device

    def _parse_attribute(self, attr_config: Dict) -> Attribute:
        """
        解析属性配置

        参数:
            attr_config: 属性配置字典

        返回:
            Attribute: 属性对象

        异常:
            ValueError: 配置缺少必填字段
        """
        # 验证必填字段
        required_fields = ['name', 'uid', 'attr_type', 'field_key']
        for field in required_fields:
            if field not in attr_config:
                raise ValueError(f"属性配置缺少必填字段: {field}")

        # 创建属性对象
        attr = Attribute(
            name=attr_config['name'],
            uid=attr_config['uid'],
            attr_type=attr_config['attr_type'],
            field_key=attr_config['field_key'],
            unit=attr_config.get('unit'),
            description=attr_config.get('description')
        )

        return attr

    def _parse_environment_sensor(self, sensor_config: Dict) -> EnvironmentSensor:
        """
        解析环境传感器配置

        参数:
            sensor_config: 环境传感器配置字典

        返回:
            EnvironmentSensor: 环境传感器对象

        异常:
            ValueError: 配置缺少必填字段
        """
        # 验证必填字段
        required_fields = ['sensor_name', 'sensor_uid']
        for field in required_fields:
            if field not in sensor_config:
                raise ValueError(f"环境传感器配置缺少必填字段: {field}")

        # 创建环境传感器对象
        sensor = EnvironmentSensor(
            sensor_name=sensor_config['sensor_name'],
            sensor_uid=sensor_config['sensor_uid'],
            sensor_type=sensor_config.get('sensor_type', 'environment'),
            location=sensor_config.get('location')
        )

        # 解析传感器属性
        if 'attributes' in sensor_config:
            for attr_config in sensor_config['attributes']:
                try:
                    attr = self._parse_attribute(attr_config)
                    sensor.add_attribute(attr)
                    self.logger.debug(f"        添加传感器属性: {attr.name}")
                except Exception as e:
                    self.logger.warning(f"        解析传感器属性失败: {e}，跳过该属性")

        return sensor


# ==================== 便捷函数 ====================

def load_datacenter_from_config(uid_config: Dict, logger: logging.Logger) -> DataCenter:
    """
    从配置字典加载数据中心对象（便捷函数）

    参数:
        uid_config: uid_config 配置字典（已从 uid_config.yaml 加载）
        logger: 日志器实例

    返回:
        DataCenter: 完整的数据中心对象

    异常:
        ValueError: 配置字典为空或缺少必填字段

    示例:
        # 在 main.py 中使用
        # 加载数据中心配置
        datacenter = load_datacenter_from_config(uid_config, loggers["architecture_parser"])
    """
    parser = DataCenterConfigParser(uid_config, logger)
    return parser.parse_datacenter()


