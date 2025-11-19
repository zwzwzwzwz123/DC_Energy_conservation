"""
空调优化模块

本模块提供空调系统的智能优化功能，支持多种优化算法。

主要组件：
    OptimizationState: 优化状态枚举
    DataRecord: 历史数据记录模型
    ACController: 空调控制器，管理设备状态和历史数据
    DynamicOptimizer: 动态优化器，支持多种优化算法
    ACInstanceManager: 空调实例管理器

主要API：
    run_optimization(): 一行代码启动优化流程（推荐使用）
    start_optimization_process(): 核心优化逻辑（高级用法）

使用示例：
    >>> from modules.optimization_module import run_optimization
    >>>
    >>> # 最简单的调用方式
    >>> best_params = run_optimization(
    ...     uid_config=uid_config,
    ...     parameter_config=modules_config,
    ...     security_boundary_config=security_config,
    ...     current_data=current_data,
    ...     logger=logger
    ... )
    >>>
    >>> # 结果包含每台空调的优化参数
    >>> print(best_params['air_conditioner_setting_temperature'])
    >>> print(best_params['air_conditioner_setting_humidity'])

架构说明：
    本模块采用分层架构：
    1. 数据模型层：定义数据结构（OptimizationState, DataRecord）
    2. 工具函数层：提供配置解析和数据处理工具
    3. 核心业务层：实现优化逻辑（ACController, DynamicOptimizer）
    4. API层：提供高层接口（run_optimization等）

注意事项：
    - 本模块不执行实际的设备控制，只计算优化参数
    - 实际的参数应用由主程序负责写入InfluxDB
    - 支持多种优化算法，通过配置文件选择
"""

import pandas as pd
import time
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING
from dataclasses import dataclass
from enum import Enum
import threading
import queue
import logging

# 使用延迟导入避免在模块加载时就导入优化器（优化器可能依赖外部库）
# 只在类型检查时导入，运行时在需要时才导入
if TYPE_CHECKING:
    from .optimizers import OptimizerFactory, BaseOptimizer


# ============================================================================
# 常量定义
# ============================================================================

# 硬编码默认值（作为最后的回退，当配置文件不存在或配置项缺失时使用）
_FALLBACK_TEMPERATURE = 24  # 默认温度设定值（℃）
_FALLBACK_HUMIDITY = 50  # 默认湿度设定值（%）
_FALLBACK_COOLING_MODE = 1  # 默认制冷模式（1=制冷）
_FALLBACK_STABILIZATION_TIME = 300  # 默认稳定时间（秒）
_FALLBACK_REFERENCE_STABILIZATION_TIME = 1  # 参考模式稳定时间（秒）
_FALLBACK_MAX_HISTORICAL_RECORDS = 1000  # 最大历史记录数
_FALLBACK_OPTIMIZATION_TIMEOUT = 600  # 默认优化超时时间（秒）

# 配置键名（用于访问 uid_config 和 parameter_config）
CONFIG_KEY_AIR_CONDITIONERS = 'air_conditioners'
CONFIG_KEY_SENSORS = 'sensors'
CONFIG_KEY_TEMPERATURE_SENSOR = 'temperature_sensor_uid'
CONFIG_KEY_HUMIDITY_SENSOR = 'humidity_sensor_uid'
CONFIG_KEY_ENERGY_CONSUMPTION = 'energy_consumption_uid'
CONFIG_KEY_OPTIMIZATION_MODULE = 'optimization_module'


# ============================================================================
# 配置读取工具函数
# ============================================================================

def _get_optimization_config(parameter_config: Dict, key: str, default=None, logger: Optional[logging.Logger] = None):
    """
    从优化模块配置中获取值，支持嵌套键和默认值回退

    Args:
        parameter_config: 参数配置字典
        key: 配置键（支持嵌套，如 'defaults.temperature'）
        default: 默认值（如果配置不存在）
        logger: 日志记录器（可选）

    Returns:
        配置值或默认值

    Example:
        >>> config = {'optimization_module': {'defaults': {'temperature': 25}}}
        >>> _get_optimization_config(config, 'defaults.temperature', 24)
        25
        >>> _get_optimization_config(config, 'defaults.missing', 30)
        30
    """
    if not parameter_config:
        if logger:
            logger.warning(f"参数配置为空，使用默认值: {key}={default}")
        return default

    # 获取 optimization_module 配置
    opt_config = parameter_config.get(CONFIG_KEY_OPTIMIZATION_MODULE, {})
    if not opt_config:
        if logger:
            logger.warning(f"未找到 '{CONFIG_KEY_OPTIMIZATION_MODULE}' 配置，使用默认值: {key}={default}")
        return default

    # 处理嵌套键（如 'defaults.temperature'）
    keys = key.split('.')
    value = opt_config

    for k in keys:
        if isinstance(value, dict) and k in value:
            value = value[k]
        else:
            if logger:
                logger.debug(f"配置项 '{key}' 不存在，使用默认值: {default}")
            return default

    return value


def _load_optimization_defaults(parameter_config: Dict, logger: Optional[logging.Logger] = None) -> Dict:
    """
    加载优化模块的所有默认值配置

    Args:
        parameter_config: 参数配置字典
        logger: 日志记录器（可选）

    Returns:
        Dict: 包含所有默认值的字典
    """
    defaults = {
        'temperature': _get_optimization_config(
            parameter_config, 'defaults.temperature', _FALLBACK_TEMPERATURE, logger
        ),
        'humidity': _get_optimization_config(
            parameter_config, 'defaults.humidity', _FALLBACK_HUMIDITY, logger
        ),
        'cooling_mode': _get_optimization_config(
            parameter_config, 'defaults.cooling_mode', _FALLBACK_COOLING_MODE, logger
        ),
        'stabilization_time': _get_optimization_config(
            parameter_config, 'defaults.stabilization_time', _FALLBACK_STABILIZATION_TIME, logger
        ),
        'reference_stabilization_time': _get_optimization_config(
            parameter_config, 'defaults.reference_stabilization_time', _FALLBACK_REFERENCE_STABILIZATION_TIME, logger
        ),
        'optimization_timeout': _get_optimization_config(
            parameter_config, 'defaults.optimization_timeout', _FALLBACK_OPTIMIZATION_TIMEOUT, logger
        ),
        'max_historical_records': _get_optimization_config(
            parameter_config, 'defaults.max_historical_records', _FALLBACK_MAX_HISTORICAL_RECORDS, logger
        ),
    }

    if logger:
        logger.info(f"加载优化模块默认值配置: {defaults}")

    return defaults


# ============================================================================
# 数据模型
# ============================================================================

# ============================================================================
# 配置解析工具函数
# ============================================================================

def _validate_uid_config(uid_config: Dict) -> None:
    """
    验证UID配置的完整性

    Args:
        uid_config: UID配置字典

    Raises:
        ValueError: 如果配置不完整或格式错误
    """
    if not isinstance(uid_config, dict):
        raise ValueError("uid_config 必须是字典类型")

    if CONFIG_KEY_AIR_CONDITIONERS not in uid_config:
        raise ValueError(f"UID配置中缺少 '{CONFIG_KEY_AIR_CONDITIONERS}' 字段")

    air_conditioners = uid_config[CONFIG_KEY_AIR_CONDITIONERS]
    if not air_conditioners:
        raise ValueError("空调配置不能为空")


def _get_air_conditioner_uids_and_names(uid_config: Dict) -> Tuple[List[str], List[str]]:
    """
    从UID配置中提取空调的UID和名称列表

    Args:
        uid_config: UID配置字典（新格式，包含 'air_conditioners' 字段）

    Returns:
        Tuple[List[str], List[str]]: (UID列表, 名称列表)
            - UID列表：每台空调的第一个测点UID（作为设备标识）
            - 名称列表：每台空调的设备名称

    Raises:
        ValueError: 如果配置格式不正确

    Example:
        >>> uid_config = {
        ...     "air_conditioners": {
        ...         "空调1": {
        ...             "device_name": "空调1",
        ...             "measurement_points": {"温度": "uid1", "湿度": "uid2"}
        ...         }
        ...     }
        ... }
        >>> uids, names = _get_air_conditioner_uids_and_names(uid_config)
        >>> # uids = ["uid1"], names = ["空调1"]
    """
    _validate_uid_config(uid_config)

    air_conditioners = uid_config[CONFIG_KEY_AIR_CONDITIONERS]
    uids = []
    names = []

    for ac_name, ac_info in air_conditioners.items():
        # 获取设备名称
        device_name = ac_info.get('device_name', ac_name)
        names.append(device_name)

        # 获取第一个测点的UID作为设备标识
        measurement_points = ac_info.get('measurement_points', {})
        if measurement_points:
            # 取第一个测点的UID作为设备标识
            first_uid = next(iter(measurement_points.values()))
            uids.append(first_uid)
        else:
            # 如果没有测点，使用设备名称作为UID（向后兼容）
            uids.append(device_name)

    return uids, names


def _extract_uids_from_air_conditioners(uid_config: Dict, point_names: List[str]) -> List[str]:
    """
    从UID配置中提取指定测点名称的UID列表

    支持多个候选测点名称，按优先级匹配第一个找到的测点。
    如果某台空调没有任何匹配的测点，则跳过该空调（不添加到结果列表）。

    Args:
        uid_config: UID配置字典（新格式，包含 'air_conditioners' 字段）
        point_names: 要提取的测点名称列表（按优先级排序，支持多个候选名称）

    Returns:
        List[str]: 每台空调对应测点的UID列表（只包含找到测点的空调）

    Raises:
        ValueError: 如果配置格式不正确

    Example:
        >>> uid_config = {
        ...     "air_conditioners": {
        ...         "空调1": {
        ...             "measurement_points": {"温度设定值": "uid1", "湿度设定值": "uid2"}
        ...         },
        ...         "空调2": {
        ...             "measurement_points": {"温度设定点": "uid3", "湿度设定点": "uid4"}
        ...         }
        ...     }
        ... }
        >>> uids = _extract_uids_from_air_conditioners(uid_config, ['温度设定值', '温度设定点'])
        >>> # uids = ["uid1", "uid3"]
    """
    _validate_uid_config(uid_config)

    air_conditioners = uid_config[CONFIG_KEY_AIR_CONDITIONERS]
    uids = []

    for _ac_name, ac_info in air_conditioners.items():
        measurement_points = ac_info.get('measurement_points', {})

        # 尝试匹配任意一个候选测点名称（按优先级）
        found_uid = None
        for point_name in point_names:
            if point_name in measurement_points:
                found_uid = measurement_points[point_name]
                break

        # 只添加找到的UID（某些空调可能没有某些测点）
        if found_uid:
            uids.append(found_uid)

    return uids


def _get_sensor_uids(uid_config: Dict, sensor_type: str) -> List[str]:
    """
    统一的传感器UID获取函数

    Args:
        uid_config: UID配置字典
        sensor_type: 传感器类型键名（如 'temperature_sensor_uid'）

    Returns:
        List[str]: 传感器UID列表

    Raises:
        ValueError: 如果配置中缺少指定的传感器类型
    """
    if CONFIG_KEY_SENSORS not in uid_config:
        raise ValueError(f"配置文件中缺少 '{CONFIG_KEY_SENSORS}' 字段")

    sensors = uid_config[CONFIG_KEY_SENSORS]
    if sensor_type not in sensors:
        raise ValueError(f"配置文件中缺少传感器配置: {CONFIG_KEY_SENSORS}.{sensor_type}")

    return sensors[sensor_type]


def _create_uid_columns(uids: List[str]) -> List[str]:
    """
    统一的列名创建函数

    将UID列表转换为DataFrame列名列表（字符串格式）

    Args:
        uids: UID列表

    Returns:
        List[str]: 列名列表
    """
    return [str(uid) for uid in uids]


class OptimizationState(Enum):
    """
    优化模块的运行状态枚举

    状态说明：
        IDLE: 空闲状态，可以开始新的优化
        RUNNING: 正在运行优化过程
        RESETTING: 正在重置优化状态
    """
    IDLE = "idle"
    RUNNING = "running"
    RESETTING = "resetting"


@dataclass
class DataRecord:
    """
    历史数据记录模型

    用于存储空调运行的历史数据，包括设定值、实际值和功耗。

    属性：
        set_temp: 温度设定值（℃）
        set_humidity: 湿度设定值（%）
        final_temp: 最终温度值（℃）
        final_humidity: 最终湿度值（%）
        power: 功耗（W）
        timestamp: 时间戳
        cooling_mode: 制冷模式（0=空闲，1=制冷）
        is_optimization_result: 是否为优化结果（用于区分历史数据）
    """
    set_temp: int
    set_humidity: int
    final_temp: float
    final_humidity: float
    power: float
    timestamp: float
    cooling_mode: int = _FALLBACK_COOLING_MODE  # 使用回退默认值
    is_optimization_result: bool = False


# ============================================================================
# 核心类
# ============================================================================

class ACController:
    """
    空调控制器类

    负责管理空调设备的状态、历史数据和系统状态读取。

    主要职责：
        - 解析和存储空调UID配置
        - 管理历史数据
        - 读取当前系统状态
        - 管理优化状态（IDLE/RUNNING/RESETTING）
        - 提供线程安全的状态访问

    属性：
        uid_config: UID配置字典
        logger: 日志记录器
        is_reference: 是否为参考优化模式
        state: 当前优化状态
        historical_data: 历史数据记录列表
        previous_best_params: 上一次的最优参数
    """

    def __init__(self,
                 uid_config: Dict,
                 logger: logging.Logger,
                 is_reference: bool = False,
                 parameter_config: Optional[Dict] = None):
        """
        初始化空调控制器

        Args:
            uid_config: UID配置字典
            logger: 日志记录器
            is_reference: 是否为参考优化模式（快速测试模式）
            parameter_config: 参数配置字典（可选），用于读取默认值配置

        Raises:
            ValueError: 如果UID配置格式不正确
        """
        # 配置初始化
        self.uid_config = uid_config
        self.logger = logger
        self.is_reference = is_reference

        # 加载默认值配置
        self.defaults = _load_optimization_defaults(parameter_config or {}, logger)

        # 线程安全锁
        self.state_lock = threading.Lock()
        self.params_lock = threading.Lock()

        # 验证并解析UID配置
        _validate_uid_config(uid_config)
        self.logger.info("开始解析空调UID配置")

        # 获取空调UID和名称
        self.air_conditioner_uids, self.air_conditioner_names = _get_air_conditioner_uids_and_names(uid_config)
        self.logger.info(f"成功提取 {len(self.air_conditioner_uids)} 台空调的UID")

        # 提取各类测点的UID（支持多种测点名称）
        self.setting_temperature_uids = _extract_uids_from_air_conditioners(
            uid_config, ['温度设定值', '温度设定点', '回风温度设定点（℃）', '送风温度设置点']
        )
        self.onoff_setting_uids = _extract_uids_from_air_conditioners(
            uid_config, ['监控开关机', '监控开关机状态', '开关机命令']
        )
        self.air_conditioner_setting_humidity_uids = _extract_uids_from_air_conditioners(
            uid_config, ['湿度设置值', '湿度设定点', '回风湿度设定点（%）']
        )

        # 状态和数据初始化
        self.state = OptimizationState.IDLE
        self.result_queue = queue.Queue()
        self.stop_event = threading.Event()

        # 根据是否为参考优化设置不同的稳定时间（从配置读取）
        self.stabilization_time = (
            self.defaults['reference_stabilization_time'] if is_reference
            else self.defaults['stabilization_time']
        )

        # 历史数据存储（从配置读取最大记录数）
        self.historical_data: List[DataRecord] = []
        self.max_historical_records = self.defaults['max_historical_records']

        # 最优参数存储
        self.previous_best_params: Optional[Dict] = None

    def _extract_sensor_config(self) -> Dict:
        """
        提取传感器配置信息

        Returns:
            Dict: 包含所有传感器配置的字典

        Raises:
            ValueError: 如果缺少必要的传感器配置
        """
        config = {}

        # 温度传感器
        temp_uids = _get_sensor_uids(self.uid_config, CONFIG_KEY_TEMPERATURE_SENSOR)
        config['temperature_uids'] = temp_uids
        config['temperature_cols'] = _create_uid_columns(temp_uids)
        self.logger.info(f"读取到 {len(temp_uids)} 个温度传感器")

        # 湿度传感器
        humidity_uids = _get_sensor_uids(self.uid_config, CONFIG_KEY_HUMIDITY_SENSOR)
        config['humidity_uids'] = humidity_uids
        config['humidity_cols'] = _create_uid_columns(humidity_uids)
        self.logger.info(f"读取到 {len(humidity_uids)} 个湿度传感器")

        # 能耗传感器（可选）
        try:
            power_uids = _get_sensor_uids(self.uid_config, CONFIG_KEY_ENERGY_CONSUMPTION)
            config['power_uids'] = power_uids
            config['power_cols'] = _create_uid_columns(power_uids)
            self.logger.info(f"读取到 {len(power_uids)} 个能耗采集点")
        except ValueError:
            self.logger.warning("配置文件中未找到能耗数据配置，将无法计算功耗")
            config['power_uids'] = []
            config['power_cols'] = []

        # 空调设定值
        config['set_temp_uids'] = self.setting_temperature_uids
        config['set_temp_cols'] = _create_uid_columns(self.setting_temperature_uids)
        config['set_humidity_uids'] = self.air_conditioner_setting_humidity_uids
        config['set_humidity_cols'] = _create_uid_columns(self.air_conditioner_setting_humidity_uids)

        return config

    def _create_power_mapping(self, num_air_conditioners: int, num_power_meters: int) -> Dict[int, int]:
        """
        创建空调到电表的映射关系

        Args:
            num_air_conditioners: 空调数量
            num_power_meters: 电表数量

        Returns:
            Dict[int, int]: 空调索引到电表索引的映射
        """
        if num_power_meters == 0:
            return {}

        # 简化处理：按顺序循环分配到电表
        mapping = {i: i % num_power_meters for i in range(num_air_conditioners)}
        self.logger.info(f"自动生成空调-电表映射关系: {num_air_conditioners}台空调 -> {num_power_meters}个电表")
        return mapping

    def add_historical_data(self, data: pd.DataFrame) -> None:
        """
        添加历史数据

        从DataFrame中提取历史数据并转换为DataRecord列表。
        每台空调一条记录，根据电表分组正确分配能耗数据。

        Args:
            data: 历史数据DataFrame

        Raises:
            ValueError: 如果数据格式不正确或缺少必要字段
        """
        try:
            self.historical_data.clear()

            # 提取传感器配置
            sensor_config = self._extract_sensor_config()

            # 创建空调-电表映射
            num_ac = len(self.air_conditioner_uids)
            num_power = len(sensor_config['power_uids'])
            power_mapping = self._create_power_mapping(num_ac, num_power)

            # 遍历数据并创建历史记录
            records = self._create_historical_records(data, sensor_config, power_mapping)
            self._store_historical_records(records)

            power_info = "根据电表分组分配功耗" if sensor_config['power_cols'] else "无功耗数据"
            self.logger.info(f"成功添加{len(self.historical_data)}条历史数据（每台空调一条，{power_info}）")

        except Exception as e:
            self.logger.error(f"添加历史数据时发生错误: {str(e)}")
            raise

    def _create_historical_records(self, data: pd.DataFrame, sensor_config: Dict,
                                   power_mapping: Dict[int, int]) -> List[DataRecord]:
        """
        从DataFrame创建历史数据记录列表

        Args:
            data: 历史数据DataFrame
            sensor_config: 传感器配置字典
            power_mapping: 空调到电表的映射关系

        Returns:
            List[DataRecord]: 历史数据记录列表
        """
        records = []

        for _, row in data.iterrows():
            # 计算所有传感器的平均值
            avg_temp = row[sensor_config['temperature_cols']].mean()
            avg_humidity = row[sensor_config['humidity_cols']].mean()

            # 为每台空调创建一条记录
            for i, _uid in enumerate(self.air_conditioner_uids):
                # 验证索引范围
                if i >= len(sensor_config['set_temp_cols']) or i >= len(sensor_config['set_humidity_cols']):
                    self.logger.warning(f"空调索引{i}超出设定值列表范围，跳过该空调")
                    continue

                # 获取设定值
                set_temp = row[sensor_config['set_temp_cols'][i]]
                set_humidity = row[sensor_config['set_humidity_cols'][i]]

                # 获取功耗数据
                power = self._get_power_for_air_conditioner(
                    i, row, sensor_config['power_cols'], power_mapping
                )

                # 创建记录
                record = DataRecord(
                    set_temp=int(set_temp),
                    set_humidity=int(set_humidity),
                    final_temp=float(avg_temp),
                    final_humidity=float(avg_humidity),
                    power=float(power),
                    timestamp=row.get('_time', time.time()),
                    is_optimization_result=False
                )
                records.append(record)

        return records

    def _get_power_for_air_conditioner(self, ac_index: int, row: pd.Series,
                                       power_cols: List[str],
                                       power_mapping: Dict[int, int]) -> float:
        """
        获取指定空调的功耗数据

        Args:
            ac_index: 空调索引
            row: 数据行
            power_cols: 功耗列名列表
            power_mapping: 空调到电表的映射

        Returns:
            float: 功耗值
        """
        if not power_cols or ac_index not in power_mapping:
            return 0.0

        power_index = power_mapping[ac_index]
        if power_index >= len(power_cols):
            self.logger.warning(f"电表索引{power_index}越界，使用默认值0")
            return 0.0

        return row[power_cols[power_index]]

    def _store_historical_records(self, records: List[DataRecord]) -> None:
        """
        存储历史数据记录

        Args:
            records: 历史数据记录列表
        """
        self.historical_data.extend(records)

        # 限制历史记录数量
        if len(self.historical_data) > self.max_historical_records:
            self.historical_data = self.historical_data[-self.max_historical_records:]
            self.logger.info(f"历史记录超过上限，保留最近{self.max_historical_records}条")

    def _read_sensor_values(self, row: pd.Series, sensor_type: str) -> List[float]:
        """
        读取指定类型传感器的值

        Args:
            row: 数据行
            sensor_type: 传感器类型键名

        Returns:
            List[float]: 传感器值列表
        """
        uids = _get_sensor_uids(self.uid_config, sensor_type)
        cols = _create_uid_columns(uids)
        return [row[col] for col in cols]

    def _read_measurement_point_values(self, row: pd.Series, point_names: List[str]) -> List[float]:
        """
        读取指定测点的值

        Args:
            row: 数据行
            point_names: 测点名称列表（按优先级）

        Returns:
            List[float]: 测点值列表（只包含找到的测点）
        """
        uids = _extract_uids_from_air_conditioners(self.uid_config, point_names)
        if not uids:
            return []

        cols = _create_uid_columns(uids)
        return [row[col] for col in cols]

    def _calculate_power_groups(self, num_power_meters: int) -> List[List[int]]:
        """
        计算功耗分组信息

        Args:
            num_power_meters: 电表数量

        Returns:
            List[List[int]]: 功耗分组列表，每个分组包含使用同一电表的空调索引
        """
        num_ac = len(self.air_conditioner_uids)

        if num_power_meters > 0:
            # 根据空调数量和电表数量自动生成分组
            power_groups = []
            for power_idx in range(num_power_meters):
                # 找出使用该电表的所有空调
                group = [ac_idx for ac_idx in range(num_ac) if ac_idx % num_power_meters == power_idx]
                power_groups.append(group)
        else:
            # 如果没有功耗数据，每台空调独立
            power_groups = [[i] for i in range(num_ac)]

        return power_groups

    def get_system_state(self, current_data: pd.DataFrame) -> Tuple[list, list, list, list, list, list]:
        """
        获取当前系统状态

        Args:
            current_data: 当前数据DataFrame

        Returns:
            Tuple[list, list, list, list, list, list]: 包含以下元素的元组
                - 所有温度传感器的温度列表
                - 回风温度列表（每台空调）
                - 功耗列表（电表的值）
                - 功耗分组信息（标记哪些空调共用电表）
                - 所有湿度传感器的湿度列表
                - 回风湿度列表（每台空调）

        Raises:
            ValueError: 如果缺少必要的传感器配置
        """
        try:
            row = current_data.iloc[-1]

            # 读取温度传感器数据
            temp_list = self._read_sensor_values(row, CONFIG_KEY_TEMPERATURE_SENSOR)

            # 读取回风温度数据
            return_temps = self._read_measurement_point_values(
                row, ['回风温度测量值（℃）', '回风温度测量值', '回风温度']
            )
            if not return_temps:
                self.logger.warning("未找到回风温度配置，使用空列表")

            # 读取功耗数据（可选）
            try:
                power_values = self._read_sensor_values(row, CONFIG_KEY_ENERGY_CONSUMPTION)
            except ValueError:
                self.logger.warning("配置文件中未找到能耗数据配置")
                power_values = []

            # 读取湿度传感器数据
            humidity_list = self._read_sensor_values(row, CONFIG_KEY_HUMIDITY_SENSOR)

            # 读取回风湿度数据
            return_humidity_list = self._read_measurement_point_values(
                row, ['回风湿度测量值（%）', '回风湿度测量值', '回风湿度']
            )
            if not return_humidity_list:
                self.logger.warning("未找到回风湿度配置，使用空列表")

            # 计算功耗分组
            power_groups = self._calculate_power_groups(len(power_values))

            self.logger.info(
                f"成功获取系统状态: temp_sensors={len(temp_list)}, "
                f"humidity_sensors={len(humidity_list)}, "
                f"return_temps={len(return_temps)}, "
                f"return_humidity={len(return_humidity_list)}, "
                f"power_meters={len(power_values)}"
            )

            return temp_list, return_temps, power_values, power_groups, humidity_list, return_humidity_list

        except Exception as e:
            self.logger.error(f"获取系统状态时发生错误: {str(e)}")
            raise

    def wait_for_stabilization(self) -> None:
        """
        等待系统稳定

        在参考模式下等待1秒，在实际优化模式下等待5分钟。
        """
        self.logger.debug(f"等待系统稳定 ({self.stabilization_time}秒)...")
        time.sleep(self.stabilization_time)

    def reset(self) -> Optional[Dict]:
        """
        重置优化过程并返回上一个最优状态参数（线程安全版本）

        Returns:
            Optional[Dict]: 上一个最优状态参数，如果没有则返回None
        """
        self.logger.info("开始重置优化过程...")

        # 使用单个锁保护整个重置过程，避免竞态条件
        with self.state_lock:
            # 检查当前状态
            if self.state == OptimizationState.RESETTING:
                self.logger.warning("重置已在进行中，跳过本次重置")
                # 获取参数并返回
                with self.params_lock:
                    return self.previous_best_params

            # 保存旧状态并设置为重置中
            old_state = self.state
            self.state = OptimizationState.RESETTING
            self.logger.debug(f"状态从 {old_state} 切换到 RESETTING")

        try:
            # 发送停止信号
            self.stop_event.set()
            self.logger.debug("已发送停止信号")

            # 等待优化过程完全停止（添加超时保护）
            timeout = 30  # 30秒超时
            start_time = time.time()

            # 等待优化线程停止（如果存在）
            while time.time() - start_time < timeout:
                # 检查是否有正在运行的优化线程
                # 注意：这里假设优化线程会检查 stop_event 并及时退出
                time.sleep(0.1)

                # 简单等待后退出（实际的线程同步由 DynamicOptimizer 处理）
                # 如果需要更精确的线程同步，应该在 DynamicOptimizer 中实现
                break

            # 安全地获取上一个最优状态参数
            with self.params_lock:
                previous_params = self.previous_best_params
                if previous_params:
                    self.logger.info(f"已保存上一个最优状态参数")
                else:
                    self.logger.warning("没有可用的上一个最优状态")

            return previous_params

        finally:
            # 确保状态被正确恢复（即使发生异常）
            self.stop_event.clear()
            with self.state_lock:
                self.state = OptimizationState.IDLE
                self.logger.debug("状态已恢复为 IDLE")

            self.logger.info("重置完成")


class DynamicOptimizer:
    """
    动态优化器类

    支持多种优化算法的统一接口，负责管理优化过程和线程。

    主要职责：
        - 根据配置创建具体的优化器实例
        - 管理优化线程的生命周期
        - 提供统一的优化接口
        - 处理优化过程中的异常和超时

    支持的优化算法：
        - bayesian: 贝叶斯优化（默认）
        - reinforcement_learning: 强化学习
        - grid_search: 网格搜索
        - random_search: 随机搜索
        - genetic: 遗传算法

    属性：
        controller: ACController实例
        optimizer: 具体的优化器实例
        algorithm: 当前使用的优化算法名称
        optimization_thread: 优化线程
        initial_params: 初始参数
    """

    def __init__(self,
                 controller: ACController,
                 parameter_config: Dict,
                 security_boundary_config: Dict):
        """
        初始化动态优化器

        Args:
            controller: ACController实例
            parameter_config: 参数配置字典
            security_boundary_config: 安全边界配置字典
        """
        self.controller = controller
        self.logger = controller.logger
        self.parameter_config = parameter_config
        self.security_boundary_config = security_boundary_config

        # 从配置文件读取优化算法类型
        optimization_config = parameter_config.get(CONFIG_KEY_OPTIMIZATION_MODULE, {})
        self.algorithm = optimization_config.get("algorithm", "bayesian")

        # 延迟导入优化器工厂（运行时导入）
        from .optimizers import OptimizerFactory

        # 创建具体的优化器实例（带回退机制）
        self.optimizer = self._create_optimizer_with_fallback(
            OptimizerFactory, controller, parameter_config, security_boundary_config
        )

        # 读取安全边界配置
        self.historical_weight = float(optimization_config.get("historical_weight", 0.3))
        self.max_safe_temp = float(security_boundary_config.get("maximum_safe_indoor_temperature", 28.0))
        self.min_safe_humidity = float(security_boundary_config.get("minimum_safe_indoor_humidity", 30.0))
        self.max_safe_humidity = float(security_boundary_config.get("maximum_safe_indoor_humidity", 70.0))
        self.min_humidity = int(security_boundary_config.get("minimum_air_conditioner_setting_humidity", 30))
        self.max_humidity = int(security_boundary_config.get("maximum_air_conditioner_setting_humidity", 70))

        # 线程管理
        self.optimization_thread: Optional[threading.Thread] = None
        self.initial_params: Optional[Dict] = None
        self.temp_reset_params: Optional[Dict] = None

        self.logger.info(
            f"优化器初始化完成: algorithm={self.algorithm}, "
            f"max_safe_temp={self.max_safe_temp}, "
            f"min_safe_humidity={self.min_safe_humidity}, "
            f"max_safe_humidity={self.max_safe_humidity}, "
            f"historical_weight={self.historical_weight}"
        )

    def _create_optimizer_with_fallback(self, factory_class, controller,
                                       parameter_config, security_boundary_config):
        """
        创建优化器实例，失败时回退到默认算法

        Args:
            factory_class: 优化器工厂类
            controller: ACController实例
            parameter_config: 参数配置
            security_boundary_config: 安全边界配置

        Returns:
            BaseOptimizer: 优化器实例
        """
        try:
            optimizer = factory_class.create_optimizer(
                algorithm=self.algorithm,
                controller=controller,
                parameter_config=parameter_config,
                security_boundary_config=security_boundary_config,
                logger=self.logger
            )
            self.logger.info(f"成功创建优化器: {self.algorithm}")
            return optimizer

        except ValueError as e:
            self.logger.error(f"创建优化器失败: {str(e)}")
            self.logger.warning("回退到默认的贝叶斯优化算法")
            self.algorithm = "bayesian"

            return factory_class.create_optimizer(
                algorithm="bayesian",
                controller=controller,
                parameter_config=parameter_config,
                security_boundary_config=security_boundary_config,
                logger=self.logger
            )

    def set_initial_params(self, set_temp: int, set_humidity: int = None) -> None:
        """
        设置初始参数

        Args:
            set_temp: 初始温度设定值（℃），范围16-30
            set_humidity: 初始湿度设定值（%），如果为None则使用配置的默认值

        Raises:
            ValueError: 如果参数超出有效范围
        """
        # 验证温度范围
        if not (16 <= set_temp <= 30):
            raise ValueError("设定温度必须在16-30℃范围内")

        # 检查温度安全约束
        if set_temp > self.max_safe_temp:
            self.logger.warning(
                f"设定温度 {set_temp}℃ 超过安全上限 {self.max_safe_temp}℃，"
                f"优化过程可能无法找到满足约束的解"
            )

        # 设置默认湿度（从配置读取）
        if set_humidity is None:
            set_humidity = _get_optimization_config(
                self.parameter_config,
                'defaults.humidity',
                _FALLBACK_HUMIDITY,
                self.logger
            )

        # 验证湿度范围
        if not (self.min_humidity <= set_humidity <= self.max_humidity):
            raise ValueError(f"设定湿度必须在{self.min_humidity}-{self.max_humidity}%范围内")

        # 检查湿度安全约束
        if not (self.min_safe_humidity <= set_humidity <= self.max_safe_humidity):
            self.logger.warning(
                f"设定湿度 {set_humidity}% 超出安全范围 "
                f"[{self.min_safe_humidity}%, {self.max_safe_humidity}%]，"
                f"优化过程可能无法找到满足约束的解"
            )

        self.initial_params = {'set_temp': set_temp, 'set_humidity': set_humidity}
        self.logger.info(f"已设置初始参数: 温度={set_temp}℃, 湿度={set_humidity}%")

    def start_optimization(self, current_data: pd.DataFrame) -> None:
        """
        启动优化过程，执行一次优化迭代
        使用配置的优化算法进行优化
        """
        # 验证输入数据
        if current_data is None:
            raise ValueError("current_data 不能为 None")

        if current_data.empty:
            raise ValueError("current_data 不能为空 DataFrame")

        # 使用锁保护状态检查和修改
        with self.controller.state_lock:
            if self.controller.state != OptimizationState.IDLE:
                self.logger.warning("优化已在运行中，跳过本次启动")
                return

            self.controller.state = OptimizationState.RUNNING

        try:
            # 如果有初始参数，传递给优化器
            if self.initial_params and hasattr(self.optimizer, 'set_initial_params'):
                try:
                    self.optimizer.set_initial_params(self.initial_params)
                    self.logger.info(f"已设置初始参数: {self.initial_params}")
                except Exception as e:
                    self.logger.error(f"设置初始参数时发生错误: {str(e)}")

            def optimization_loop():
                try:
                    # 调用优化器的 optimize 方法
                    best_params = self.optimizer.optimize(current_data)

                    # 使用锁保护参数更新
                    with self.controller.params_lock:
                        self.controller.previous_best_params = best_params

                    self.logger.info(f"优化完成，最优参数: {best_params}")
                except Exception as e:
                    self.logger.error(f"优化过程中发生错误: {str(e)}")
                finally:
                    with self.controller.state_lock:
                        self.controller.state = OptimizationState.IDLE

            self.optimization_thread = threading.Thread(target=optimization_loop, daemon=True)
            self.optimization_thread.start()
            self.logger.info(f"优化过程已启动，使用算法: {self.algorithm}")

        except Exception as e:
            self.logger.error(f"启动优化过程时发生错误: {str(e)}")
            with self.controller.state_lock:
                self.controller.state = OptimizationState.IDLE
            raise

    def get_best_params(self, timeout: float = 600) -> Optional[Dict]:
        """
        安全地获取当前最优参数，等待优化完成（改进版，防止资源泄漏）

        Args:
            timeout: 等待超时时间（秒），默认 600 秒（10 分钟）

        Returns:
            Optional[Dict]: 最优参数，如果失败则返回 None
        """
        # 如果没有优化线程或线程已完成，直接返回结果
        if not self.optimization_thread or not self.optimization_thread.is_alive():
            return self._get_optimizer_result()

        # 等待优化线程完成
        self.logger.info(f"等待优化过程完成（最多 {timeout} 秒）...")
        self.optimization_thread.join(timeout=timeout)

        # 检查线程是否成功结束
        if self.optimization_thread.is_alive():
            self.logger.error(f"优化过程超时（{timeout} 秒），尝试停止...")

            # 第一步：发送停止信号
            self.controller.stop_event.set()

            # 第二步：再等待一小段时间让线程响应停止信号
            grace_period = 5  # 5 秒宽限期
            self.logger.debug(f"等待线程响应停止信号（{grace_period} 秒）...")
            self.optimization_thread.join(timeout=grace_period)

            # 第三步：检查线程是否停止
            if self.optimization_thread.is_alive():
                # 线程仍未停止，记录为僵尸线程
                self.logger.critical(
                    f"⚠️ 优化线程未能响应停止信号！"
                    f"线程 ID: {self.optimization_thread.ident}, "
                    f"线程名称: {self.optimization_thread.name}"
                )
                self.logger.critical(
                    "这可能导致资源泄漏。建议检查优化器实现是否正确处理停止信号。"
                )

                # 记录僵尸线程用于监控
                self._register_zombie_thread(self.optimization_thread)
            else:
                self.logger.info("线程已成功停止")

            # 第四步：重置状态
            with self.controller.state_lock:
                self.controller.state = OptimizationState.IDLE

            return None

        # 线程正常结束，获取结果
        self.logger.info("优化过程正常完成")
        return self._get_optimizer_result()

    def _get_optimizer_result(self) -> Optional[Dict]:
        """
        从优化器获取结果（内部辅助方法）

        Returns:
            Optional[Dict]: 最优参数
        """
        try:
            best_params = self.optimizer.get_best_params()
            if best_params:
                self.logger.info(f"获取到最优参数: {best_params}")
            else:
                self.logger.warning("优化器未返回有效参数")
            return best_params
        except Exception as e:
            self.logger.error(f"获取最优参数时发生错误: {str(e)}", exc_info=True)
            return None

    def _register_zombie_thread(self, thread: threading.Thread) -> None:
        """
        记录僵尸线程用于监控和调试

        Args:
            thread: 僵尸线程对象
        """
        if not hasattr(self, '_zombie_threads'):
            self._zombie_threads = []

        zombie_info = {
            'thread': thread,
            'thread_id': thread.ident,
            'thread_name': thread.name,
            'timestamp': time.time(),
            'algorithm': self.algorithm
        }
        self._zombie_threads.append(zombie_info)

        self.logger.warning(
            f"已记录僵尸线程 #{len(self._zombie_threads)}: "
            f"ID={thread.ident}, Name={thread.name}"
        )

    def get_zombie_threads_count(self) -> int:
        """
        获取僵尸线程数量（用于监控）

        Returns:
            int: 僵尸线程数量
        """
        return len(getattr(self, '_zombie_threads', []))

    def stop(self) -> None:
        """停止优化过程"""
        self.logger.info("开始停止优化过程...")

        # 1. 停止优化器
        self.optimizer.stop()

        # 2. 等待优化线程结束
        if self.optimization_thread and self.optimization_thread.is_alive():
            self.logger.info("等待优化线程结束...")
            self.optimization_thread.join(timeout=10)

            if self.optimization_thread.is_alive():
                self.logger.error("优化线程未能在超时时间内结束")

        # 3. 重置控制器状态
        self.controller.reset()

        self.logger.info("优化过程已完全停止")

    def reset_optimization(self) -> None:
        """完全重置优化模块，清除所有状态和历史数据"""
        self.logger.info("开始完全重置优化模块...")

        # 1. 停止优化
        self.stop()

        # 2. 清理所有状态
        self.optimizer.best_params = None
        self.optimizer.best_objective = float('inf')
        self.controller.historical_data.clear()

        with self.controller.params_lock:
            self.controller.previous_best_params = None

        self.initial_params = None
        self.temp_reset_params = None

        # 3. 重新创建优化器（确保优化器内部状态完全清空）
        try:
            self.optimizer = OptimizerFactory.create_optimizer(
                algorithm=self.algorithm,
                controller=self.controller,
                parameter_config=self.parameter_config,
                security_boundary_config=self.security_boundary_config,
                logger=self.logger
            )
            self.logger.info("优化器已重新创建")
        except Exception as e:
            self.logger.error(f"重新创建优化器失败: {str(e)}")

        self.logger.info("优化模块已完全重置")

    def get_safe_params(self, default_temp: int = 25, default_humidity: int = 50,
                        default_cooling_mode: int = 1) -> Dict:
        """安全地获取优化参数，如果优化失败则返回默认值"""
        try:
            params = self.get_best_params()
            if params and isinstance(params, dict):
                # 验证参数完整性
                required_keys = ['set_temp', 'set_humidity', 'cooling_mode']
                if all(key in params for key in required_keys):
                    self.logger.info(f"成功获取优化参数: {params}")
                    return params
                else:
                    self.logger.warning(f"优化参数不完整，缺少必要字段，使用默认参数")

            self.logger.warning(
                f"优化未完成或失败，使用默认参数: 温度={default_temp}℃, 湿度={default_humidity}%, 制冷模式={default_cooling_mode}")
            return {
                'set_temp': default_temp,
                'set_humidity': default_humidity,
                'cooling_mode': default_cooling_mode
            }
        except Exception as e:
            self.logger.error(f"获取优化参数时发生异常: {str(e)}，使用默认参数")
            return {
                'set_temp': default_temp,
                'set_humidity': default_humidity,
                'cooling_mode': default_cooling_mode
            }


class ACInstanceManager:
    """
    空调实例管理器

    负责管理多台空调的优化器实例，提供统一的实例创建和访问接口。

    主要职责：
        - 批量创建空调优化器实例
        - 提供实例查询接口
        - 管理实例生命周期

    属性：
        ac_instances: 空调UID到优化器实例的映射字典
    """

    def __init__(self):
        """初始化实例管理器"""
        self.ac_instances: Dict[str, DynamicOptimizer] = {}

    def initialize_instances(self,
                             uid_config: Dict,
                             parameter_config: Dict,
                             security_boundary_config: Dict,
                             logger: logging.Logger,
                             is_reference: bool = False) -> None:
        """
        初始化所有空调实例

        为每台空调创建独立的控制器和优化器实例。

        Args:
            uid_config: UID配置字典
            parameter_config: 参数配置字典
            security_boundary_config: 安全边界配置字典
            logger: 日志记录器
            is_reference: 是否为参考优化模式

        Raises:
            ValueError: 如果空调UID列表为空
            Exception: 其他初始化错误
        """
        try:
            # 清除现有实例
            self.ac_instances.clear()

            # 获取空调UID列表
            ac_uids, ac_names = _get_air_conditioner_uids_and_names(uid_config)
            if not ac_uids:
                raise ValueError("空调UID列表为空")

            # 为每台空调创建实例
            for uid, name in zip(ac_uids, ac_names):
                controller = ACController(uid_config, logger, is_reference, parameter_config)
                optimizer = DynamicOptimizer(controller, parameter_config, security_boundary_config)
                self.ac_instances[str(uid)] = optimizer  # 确保uid是字符串
                logger.info(f"成功创建空调 {name} (UID: {uid}) 的优化器实例")

            logger.info(f"成功初始化所有空调实例，共 {len(self.ac_instances)} 个实例")

        except Exception as e:
            logger.error(f"初始化空调实例时发生错误: {str(e)}")
            raise

    def get_instance(self, uid: str) -> DynamicOptimizer:
        """
        获取指定空调的优化器实例

        Args:
            uid: 空调UID

        Returns:
            DynamicOptimizer: 优化器实例

        Raises:
            ValueError: 如果未找到指定的实例
        """
        uid = str(uid)  # 确保uid是字符串
        optimizer = self.ac_instances.get(uid)
        if optimizer is None:
            raise ValueError(f"未找到空调 {uid} 的优化器实例")
        return optimizer

    def get_all_instances(self) -> Dict[str, DynamicOptimizer]:
        """
        获取所有空调的优化器实例

        Returns:
            Dict[str, DynamicOptimizer]: UID到优化器实例的映射字典（副本）
        """
        return self.ac_instances.copy()


# ============================================================================
# 辅助函数
# ============================================================================

def _enforce_safety_bounds(params: Dict, security_boundary_config: Dict,
                          logger: logging.Logger) -> Dict:
    """
    强制将参数限制在安全范围内（最后一道防线）

    这是一个关键的安全机制，确保即使优化器出错也不会返回危险参数。

    Args:
        params: 优化参数字典
        security_boundary_config: 安全边界配置
        logger: 日志记录器

    Returns:
        Dict: 经过边界检查的安全参数
    """
    # 读取安全边界配置
    min_temp = int(security_boundary_config.get("minimum_air_conditioner_setting_temperature", 16))
    max_temp = int(security_boundary_config.get("maximum_air_conditioner_setting_temperature", 30))
    min_humidity = int(security_boundary_config.get("minimum_air_conditioner_setting_humidity", 30))
    max_humidity = int(security_boundary_config.get("maximum_air_conditioner_setting_humidity", 70))

    # 创建副本，避免修改原始数据
    safe_params = {
        'air_conditioner_setting_temperature': params['air_conditioner_setting_temperature'].copy(),
        'air_conditioner_setting_humidity': params['air_conditioner_setting_humidity'].copy(),
        'air_conditioner_cooling_mode': params['air_conditioner_cooling_mode'].copy()
    }

    modified = False

    # 强制温度边界
    for i in range(len(safe_params['air_conditioner_setting_temperature'])):
        temp = safe_params['air_conditioner_setting_temperature'][i]
        if temp < min_temp:
            safe_params['air_conditioner_setting_temperature'][i] = min_temp
            logger.warning(f"⚠️ 空调 {i+1}: 温度 {temp}℃ 低于安全下限，强制设为 {min_temp}℃")
            modified = True
        elif temp > max_temp:
            safe_params['air_conditioner_setting_temperature'][i] = max_temp
            logger.warning(f"⚠️ 空调 {i+1}: 温度 {temp}℃ 高于安全上限，强制设为 {max_temp}℃")
            modified = True

    # 强制湿度边界
    for i in range(len(safe_params['air_conditioner_setting_humidity'])):
        humidity = safe_params['air_conditioner_setting_humidity'][i]
        if humidity < min_humidity:
            safe_params['air_conditioner_setting_humidity'][i] = min_humidity
            logger.warning(f"⚠️ 空调 {i+1}: 湿度 {humidity}% 低于安全下限，强制设为 {min_humidity}%")
            modified = True
        elif humidity > max_humidity:
            safe_params['air_conditioner_setting_humidity'][i] = max_humidity
            logger.warning(f"⚠️ 空调 {i+1}: 湿度 {humidity}% 高于安全上限，强制设为 {max_humidity}%")
            modified = True

    if modified:
        logger.warning("🔒 优化参数已被强制调整到安全范围内")
    else:
        logger.info("✓ 优化参数在安全范围内")

    return safe_params


def _validate_optimization_result(params: Dict, uid_config: Dict,
                                  logger: logging.Logger) -> bool:
    """
    验证优化结果的完整性和一致性

    Args:
        params: 优化参数字典
        uid_config: UID配置
        logger: 日志记录器

    Returns:
        bool: 结果是否有效
    """
    try:
        # 1. 检查必需的键
        required_keys = [
            'air_conditioner_setting_temperature',
            'air_conditioner_setting_humidity',
            'air_conditioner_cooling_mode'
        ]

        for key in required_keys:
            if key not in params:
                logger.error(f"❌ 优化结果缺少必需的键: {key}")
                return False

        # 2. 检查列表长度一致性
        temp_list = params['air_conditioner_setting_temperature']
        humidity_list = params['air_conditioner_setting_humidity']
        mode_list = params['air_conditioner_cooling_mode']

        if not (len(temp_list) == len(humidity_list) == len(mode_list)):
            logger.error(
                f"❌ 优化结果长度不一致: "
                f"温度={len(temp_list)}, 湿度={len(humidity_list)}, 模式={len(mode_list)}"
            )
            return False

        # 3. 检查与空调数量是否匹配
        expected_count = len(uid_config.get('air_conditioners', {}))
        if len(temp_list) != expected_count:
            logger.error(
                f"❌ 优化结果数量 ({len(temp_list)}) 与空调数量 ({expected_count}) 不匹配"
            )
            return False

        # 4. 检查数据类型
        for i, temp in enumerate(temp_list):
            if not isinstance(temp, (int, float)):
                logger.error(f"❌ 空调 {i+1} 的温度值类型错误: {type(temp)}")
                return False

        for i, humidity in enumerate(humidity_list):
            if not isinstance(humidity, (int, float)):
                logger.error(f"❌ 空调 {i+1} 的湿度值类型错误: {type(humidity)}")
                return False

        logger.info(f"✓ 优化结果验证通过（{len(temp_list)} 台空调）")
        return True

    except Exception as e:
        logger.error(f"❌ 优化结果验证失败: {str(e)}", exc_info=True)
        return False


def _get_safe_fallback_params(uid_config: Dict, parameter_config: Dict,
                              logger: logging.Logger) -> Dict:
    """
    获取安全的回退参数（当优化失败时使用）

    Args:
        uid_config: UID配置
        parameter_config: 参数配置
        logger: 日志记录器

    Returns:
        Dict: 安全的默认参数
    """
    num_acs = len(uid_config.get('air_conditioners', {}))

    # 从配置读取默认值
    defaults = _load_optimization_defaults(parameter_config, logger)
    default_temp = defaults['temperature']
    default_humidity = defaults['humidity']
    default_mode = defaults['cooling_mode']

    logger.warning(
        f"⚠️ 使用安全回退参数: 温度={default_temp}℃, "
        f"湿度={default_humidity}%, 模式={default_mode}"
    )

    return {
        'air_conditioner_setting_temperature': [default_temp] * num_acs,
        'air_conditioner_setting_humidity': [default_humidity] * num_acs,
        'air_conditioner_cooling_mode': [default_mode] * num_acs,
        'optimization_metadata': {
            'timestamp': time.time(),
            'is_reference': False,
            'ac_count': num_acs,
            'success': False,
            'fallback': True
        }
    }


# ============================================================================
# 高层API函数
# ============================================================================


def run_optimization(
        uid_config: dict,
        parameter_config: dict,
        security_boundary_config: dict,
        current_data: pd.DataFrame,
        logger: logging.Logger,
        historical_data: Optional[pd.DataFrame] = None,
        is_reference: bool = False,
        ac_manager: Optional[ACInstanceManager] = None,
        timeout_seconds: Optional[float] = None,
        progress_callback: Optional[callable] = None,
        initial_params: Optional[Dict] = None
) -> dict:
    """
    高层封装函数：一行代码启动整个优化流程

    这是优化模块的统一入口函数，封装了所有优化相关的初始化和执行逻辑。
    使用此函数，在 main.py 中只需一行代码即可完成优化。

    Args:
        uid_config: UID配置字典，包含空调和传感器的配置信息
        parameter_config: 模块参数配置，包含优化算法参数
        security_boundary_config: 安全边界配置，包含温湿度约束
        current_data: 当前系统状态数据（DataFrame格式）
        logger: 日志记录器
        historical_data: 历史数据（DataFrame格式，可选）。如果为None，将使用current_data作为历史数据
        is_reference: 是否为参考优化（快速模式，用于测试）
        ac_manager: 空调实例管理器（可选）。如果为None则自动创建新实例
        timeout_seconds: 优化超时时间（秒）。如果为None则使用默认值（600秒）
        progress_callback: 进度回调函数，签名为 callback(ac_index, ac_total, ac_name, status)
        initial_params: 初始参数字典（可选），格式为 {'set_temp': int, 'set_humidity': int}

    Returns:
        dict: 优化后的参数字典，包含以下键：
            - 'air_conditioner_setting_temperature': List[int] - 每台空调的温度设定值
            - 'air_conditioner_setting_humidity': List[int] - 每台空调的湿度设定值
            - 'air_conditioner_cooling_mode': List[int] - 每台空调的制冷模式
            - 'optimization_metadata': Dict - 优化元数据

    Raises:
        ValueError: 当输入参数无效时
        RuntimeError: 当优化过程失败时
        TimeoutError: 当优化超时时

    Example:
        >>> # 最简单的调用方式
        >>> best_params = run_optimization(
        ...     uid_config=uid_config,
        ...     parameter_config=modules_config,
        ...     security_boundary_config=security_config,
        ...     current_data=current_data,
        ...     logger=logger
        ... )

        >>> # 带历史数据和进度回调的调用
        >>> def on_progress(idx, total, name, status):
        ...     print(f"优化进度: [{idx}/{total}] {name} - {status}")
        >>>
        >>> best_params = run_optimization(
        ...     uid_config=uid_config,
        ...     parameter_config=modules_config,
        ...     security_boundary_config=security_config,
        ...     current_data=current_data,
        ...     historical_data=historical_data,
        ...     logger=logger,
        ...     timeout_seconds=300,
        ...     progress_callback=on_progress
        ... )
    """
    # ==================== 输入验证 ====================
    # 尝试导入验证器（如果可用）
    try:
        from utils.optimization_validator import validate_optimization_config

        # 执行配置验证
        is_valid = validate_optimization_config(
            uid_config=uid_config,
            parameter_config=parameter_config,
            security_boundary_config=security_boundary_config,
            current_data=current_data,
            logger=logger,
            print_report=False  # 不打印报告，只记录日志
        )

        if not is_valid:
            logger.warning("配置验证发现问题，但将继续执行优化")
    except ImportError:
        logger.debug("优化验证器不可用，跳过配置验证")
    except Exception as e:
        logger.warning(f"配置验证失败: {str(e)}，将继续执行优化")

    # 基本验证
    if current_data is None or current_data.empty:
        raise ValueError("current_data 不能为空")

    if not isinstance(uid_config, dict) or 'air_conditioners' not in uid_config:
        raise ValueError("uid_config 格式不正确，必须包含 'air_conditioners' 字段")

    if not isinstance(parameter_config, dict):
        raise ValueError("parameter_config 必须是字典类型")

    if not isinstance(security_boundary_config, dict):
        raise ValueError("security_boundary_config 必须是字典类型")

    # 如果没有提供历史数据，使用当前数据作为历史数据
    if historical_data is None:
        logger.info("未提供历史数据，使用当前数据作为历史数据")
        historical_data = current_data

    # 设置默认超时时间
    if timeout_seconds is None:
        timeout_seconds = 600  # 默认10分钟

    logger.info("="*60)
    logger.info("开始优化流程")
    logger.info(f"参考模式: {is_reference}")
    logger.info(f"超时时间: {timeout_seconds}秒")
    logger.info(f"历史数据: {len(historical_data)}条记录")
    logger.info(f"当前数据: {len(current_data)}条记录")
    logger.info("="*60)

    try:
        # 调用原有的优化函数
        best_params = start_optimization_process(
            uid_config=uid_config,
            parameter_config=parameter_config,
            security_boundary_config=security_boundary_config,
            optimization_input=historical_data,
            current_data=current_data,
            logger=logger,
            is_reference=is_reference,
            ac_manager=ac_manager,
            timeout_seconds=timeout_seconds,
            progress_callback=progress_callback,
            initial_params=initial_params
        )

        # ✨ 新增：强制安全边界检查（最后一道防线）
        logger.info("执行安全边界检查...")
        best_params = _enforce_safety_bounds(
            best_params,
            security_boundary_config,
            logger
        )

        # ✨ 新增：验证结果完整性
        logger.info("验证优化结果...")
        if not _validate_optimization_result(best_params, uid_config, logger):
            logger.error("优化结果验证失败，使用安全回退参数")
            return _get_safe_fallback_params(uid_config, parameter_config, logger)

        # 添加优化元数据
        best_params['optimization_metadata'] = {
            'timestamp': time.time(),
            'is_reference': is_reference,
            'ac_count': len(best_params['air_conditioner_setting_temperature']),
            'success': True,
            'fallback': False
        }

        logger.info("="*60)
        logger.info("✓ 优化流程完成")
        logger.info(f"✓ 优化了 {len(best_params['air_conditioner_setting_temperature'])} 台空调")
        logger.info("="*60)

        return best_params

    except Exception as e:
        logger.error(f"❌ 优化流程失败: {str(e)}", exc_info=True)
        logger.warning("使用安全回退参数")

        # ✨ 新增：失败时返回安全默认值，而不是抛出异常
        return _get_safe_fallback_params(uid_config, parameter_config, logger)


def start_optimization_process(
        uid_config: dict,
        parameter_config: dict,
        security_boundary_config: dict,
        optimization_input: pd.DataFrame,
        current_data: pd.DataFrame,
        logger: logging.Logger,
        is_reference: bool = False,
        ac_manager: Optional[ACInstanceManager] = None,
        timeout_seconds: Optional[float] = None,
        progress_callback: Optional[callable] = None,
        initial_params: Optional[Dict] = None
) -> dict:
    """
    启动优化过程，对所有空调进行优化（核心优化函数）。

    ⚠️ 重要提示：
    这是一个核心优化函数，通常不需要直接调用。
    对于大多数使用场景，推荐使用高层封装函数 `run_optimization()`。

    两个函数的关系：
    - `run_optimization()` (高层封装): 提供简化接口，自动处理配置验证、历史数据后备、
      优化元数据等，适合在 main.py 中使用
    - `start_optimization_process()` (核心逻辑): 执行实际的优化算法，提供更精细的控制，
      适合在其他高层函数中调用或需要自定义错误处理的场景

    使用建议：
    - 如果你在 main.py 中调用，使用 `run_optimization()`
    - 如果你需要精细控制或在其他封装函数中调用，使用此函数
    - 如果你不确定，使用 `run_optimization()`

    注意：此函数仅计算优化参数，不执行实际控制。
    实际的参数应用由主函数负责写入InfluxDB。

    Args:
        uid_config: UID配置信息（支持新格式配置）
        parameter_config: 参数配置信息
        security_boundary_config: 安全边界配置信息
        optimization_input: 历史数据（过去60分钟），必须提供
        current_data: 当前系统状态数据，必须提供
        logger: 日志记录器
        is_reference: 是否为参考优化（快速测试模式）
        ac_manager: 空调实例管理器，如果为None则每次创建新实例
        timeout_seconds: 优化超时时间（秒），如果为None则不设置超时
        progress_callback: 进度回调函数，签名为 callback(ac_index, ac_total, ac_name, status)
        initial_params: 初始参数字典，格式为 {'set_temp': int, 'set_humidity': int}

    Returns:
        dict: 包含每台空调优化后的设定温度、湿度和制冷模式，格式为：
            {
                'air_conditioner_setting_temperature': List[int],
                'air_conditioner_setting_humidity': List[int],
                'air_conditioner_cooling_mode': List[int]
            }

    Raises:
        ValueError: 当空调UID列表为空或结果数量不匹配时
        TimeoutError: 当优化过程超时时
        Exception: 其他优化过程中的错误

    Example:
        >>> # 直接调用（高级用法）
        >>> best_params = start_optimization_process(
        ...     uid_config=uid_config,
        ...     parameter_config=modules_config,
        ...     security_boundary_config=security_config,
        ...     optimization_input=historical_data,  # 必须提供
        ...     current_data=current_data,           # 必须提供
        ...     logger=logger,
        ...     timeout_seconds=300
        ... )

        >>> # 推荐用法（使用高层封装）
        >>> best_params = run_optimization(
        ...     uid_config=uid_config,
        ...     parameter_config=modules_config,
        ...     security_boundary_config=security_config,
        ...     current_data=current_data,
        ...     logger=logger
        ... )

    See Also:
        run_optimization(): 推荐使用的高层封装函数
    """
    try:
        # 初始化返回结果
        best_params = {
            'air_conditioner_setting_temperature': [],  # 每台空调一个温度值
            'air_conditioner_setting_humidity': [],  # 每台空调一个湿度值
            'air_conditioner_cooling_mode': [],  # 每台制冷机一个制冷模式值
        }

        # 获取空调UID列表（支持新格式配置）
        ac_uids, ac_names = _get_air_conditioner_uids_and_names(uid_config)
        if not ac_uids:
            raise ValueError("空调UID列表为空")

        logger.info(f"开始优化 {len(ac_uids)} 台空调: {ac_names}")

        # 如果没有提供ac_manager，则创建一个新的实例管理器
        if ac_manager is None:
            logger.info("未提供空调实例管理器，创建新的实例管理器")
            ac_manager = ACInstanceManager()
            ac_manager.initialize_instances(uid_config, parameter_config, security_boundary_config, logger,
                                            is_reference)

        # 遍历所有空调进行优化
        logger.info(f"开始对 {len(ac_uids)} 台空调进行优化...")

        # 记录优化开始时间（用于超时控制）
        optimization_start_time = time.time()

        for idx, (uid, name) in enumerate(zip(ac_uids, ac_names)):
            # 检查是否超时
            if timeout_seconds is not None:
                elapsed_time = time.time() - optimization_start_time
                if elapsed_time > timeout_seconds:
                    logger.error(f"优化过程超时（{elapsed_time:.1f}秒 > {timeout_seconds}秒），停止优化")
                    raise TimeoutError(f"优化过程超时: {elapsed_time:.1f}秒")

            logger.info(f"正在优化空调 [{idx+1}/{len(ac_uids)}]: {name} (UID: {uid})")

            # 调用进度回调
            if progress_callback is not None:
                try:
                    progress_callback(idx + 1, len(ac_uids), name, "开始优化")
                except Exception as e:
                    logger.warning(f"进度回调函数执行失败: {str(e)}")

            try:
                # 获取优化器实例
                optimizer = ac_manager.get_instance(uid)

                # 如果提供了初始参数，设置初始参数
                if initial_params is not None:
                    try:
                        optimizer.set_initial_params(
                            set_temp=initial_params.get('set_temp', 24),
                            set_humidity=initial_params.get('set_humidity', 50)
                        )
                        logger.info(f"已为空调 {name} 设置初始参数: {initial_params}")
                    except Exception as e:
                        logger.warning(f"设置初始参数失败: {str(e)}")

                # 更新历史数据
                optimizer.controller.add_historical_data(optimization_input)

                # 启动优化
                optimizer.start_optimization(current_data)

                # 安全地获取最优参数
                params = optimizer.get_safe_params()

                # 添加温度和湿度设定值
                best_params['air_conditioner_setting_temperature'].append(params['set_temp'])
                best_params['air_conditioner_setting_humidity'].append(params['set_humidity'])

                # 添加制冷模式值（每台空调一个制冷模式）
                cooling_mode_value = params.get('cooling_mode', 1)  # 默认为1（制冷模式）
                best_params['air_conditioner_cooling_mode'].append(cooling_mode_value)

                logger.info(
                    f"空调 {name} 优化完成 - "
                    f"温度: {params['set_temp']}℃, "
                    f"湿度: {params['set_humidity']}%, "
                    f"制冷模式: {cooling_mode_value}"
                )

                # 调用进度回调
                if progress_callback is not None:
                    try:
                        progress_callback(idx + 1, len(ac_uids), name, "优化完成")
                    except Exception as e:
                        logger.warning(f"进度回调函数执行失败: {str(e)}")

            except Exception as e:
                logger.error(f"优化空调 {name} (UID: {uid}) 时发生错误: {str(e)}")
                # 使用默认参数
                best_params['air_conditioner_setting_temperature'].append(24)
                best_params['air_conditioner_setting_humidity'].append(50)
                best_params['air_conditioner_cooling_mode'].append(1)
                logger.warning(f"空调 {name} 使用默认参数: 温度=24℃, 湿度=50%, 制冷模式=1")

                # 调用进度回调
                if progress_callback is not None:
                    try:
                        progress_callback(idx + 1, len(ac_uids), name, "使用默认参数")
                    except Exception as e:
                        logger.warning(f"进度回调函数执行失败: {str(e)}")

        # 验证结果完整性
        expected_ac_count = len(ac_uids)
        actual_temp_count = len(best_params['air_conditioner_setting_temperature'])
        actual_humidity_count = len(best_params['air_conditioner_setting_humidity'])
        actual_cooling_mode_count = len(best_params['air_conditioner_cooling_mode'])

        if actual_temp_count != expected_ac_count:
            raise ValueError(f"温度设定结果数量不匹配：期望 {expected_ac_count} 个，实际 {actual_temp_count} 个")
        if actual_humidity_count != expected_ac_count:
            raise ValueError(f"湿度设定结果数量不匹配：期望 {expected_ac_count} 个，实际 {actual_humidity_count} 个")
        if actual_cooling_mode_count != expected_ac_count:
            raise ValueError(f"制冷模式结果数量不匹配：期望 {expected_ac_count} 个，实际 {actual_cooling_mode_count} 个")

        logger.info(
            f"所有空调优化完成 - 温度设定: {actual_temp_count}个, 湿度设定: {actual_humidity_count}个, 制冷模式: {actual_cooling_mode_count}个")
        return best_params
    except Exception as e:
        logger.error(f"优化过程发生错误: {str(e)}")
        raise