import optuna
import numpy as np
import yaml
import pandas as pd
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import threading
import queue
from datetime import datetime, timedelta
import logging
from utils.data_reading_writing import (
    _extract_uids_from_air_conditioners,
    _get_air_conditioner_uids_and_names,
    _map_measurement_points_to_uids
)


# 定义优化模块的三种状态
class OptimizationState(Enum):
    IDLE = "idle"
    RUNNING = "running"
    RESETTING = "resetting"


# 定义数据记录类
@dataclass
class DataRecord:
    set_temp: int
    set_humidity: int  # 新增湿度设定值
    final_temp: float
    final_humidity: float  # 新增最终湿度值
    power: float
    timestamp: float
    cooling_mode: int = 1  # 制冷模式：0=空闲模式, 1=制冷模式
    is_optimization_result: bool = False  # 用于区分是优化结果还是历史数据


# 定义空调控制器类
class ACController:
    def __init__(self,
                 uid_config: Dict,
                 logger: logging.Logger,
                 is_reference: bool = False):  # 添加is_reference参数
        # 配置初始化
        self.uid_config = uid_config
        self.logger = logger
        self.is_reference = is_reference

        # 设备UID初始化 - 适配新配置格式
        # 检查配置格式：旧格式包含 'device_uid'，新格式包含 'air_conditioners'
        if 'device_uid' in self.uid_config:
            # 旧格式
            self.logger.info("检测到旧格式的UID配置")
            self.air_conditioner_uids = self.uid_config['device_uid']['air_conditioner_uid']
            self.setting_temperature_uids = self.uid_config['dc_status_data_uid']['air_conditioner_setting_temperature_uid']
            self.onoff_setting_uids = self.uid_config['dc_status_data_uid']['air_conditioner_cooling_mode_uid']
            self.air_conditioner_setting_humidity_uids = self.uid_config['dc_status_data_uid']['air_conditioner_setting_humidity_uid']
        elif 'air_conditioners' in self.uid_config:
            # 新格式
            self.logger.info("检测到新格式的UID配置")
            # 获取空调UID和名称
            self.air_conditioner_uids, self.air_conditioner_names = _get_air_conditioner_uids_and_names(self.uid_config)
            self.logger.info(f"成功提取 {len(self.air_conditioner_uids)} 台空调的UID")
            
            # 提取温度设定值的UID（支持多种测点名称）
            temp_point_names = ['温度设定值', '温度设定点', '回风温度设定点（℃）', '送风温度设置点']
            self.setting_temperature_uids = _extract_uids_from_air_conditioners(self.uid_config, temp_point_names)
            
            # 提取开关机/制冷模式的UID
            onoff_point_names = ['监控开关机', '监控开关机状态', '开关机命令']
            self.onoff_setting_uids = _extract_uids_from_air_conditioners(self.uid_config, onoff_point_names)
            
            # 提取湿度设定值的UID
            humidity_point_names = ['湿度设置值', '湿度设定点', '回风湿度设定点（%）']
            self.air_conditioner_setting_humidity_uids = _extract_uids_from_air_conditioners(self.uid_config, humidity_point_names)
        else:
            raise ValueError("UID配置格式不正确，缺少 'device_uid' 或 'air_conditioners' 字段")

        # 状态和数据处理初始化
        self.state = OptimizationState.IDLE
        self.result_queue = queue.Queue()
        self.stop_event = threading.Event()
        # 根据是否为参考优化设置不同的稳定时间
        self.stabilization_time = 1 if is_reference else 300  # 参考优化1秒钟，实际优化5分钟
        self.historical_data: List[DataRecord] = []
        # 根据uid确定空调数量
        # self.number_of_ac = len(self.air_conditioner_uids)
        self.previous_best_params = None  # 添加存储上一个最优状态的属性

    def add_historical_data(self, data: pd.DataFrame) -> None:
        """添加历史数据，每台空调一条记录，根据电表分组正确分配能耗数据"""
        try:
            self.historical_data.clear()
            
            # ==================== 获取温度传感器UID ====================
            # 支持新格式（sensors）和旧格式（dc_status_data_uid）
            if 'sensors' in self.uid_config and 'temperature_sensor_uid' in self.uid_config['sensors']:
                # 新格式：从 sensors 读取
                temp_uids = self.uid_config['sensors']['temperature_sensor_uid']
                self.logger.info(f"从新格式配置读取到 {len(temp_uids)} 个温度传感器")
            elif 'dc_status_data_uid' in self.uid_config and 'indoor_temperature_sensor_uid' in self.uid_config['dc_status_data_uid']:
                # 旧格式：从 dc_status_data_uid 读取
                temp_uids = self.uid_config['dc_status_data_uid']['indoor_temperature_sensor_uid']
                self.logger.info(f"从旧格式配置读取到 {len(temp_uids)} 个温度传感器")
            else:
                raise ValueError("配置文件中缺少温度传感器UID配置")
            
            # 温度传感器列名需要去掉前缀，直接使用UID（因为InfluxDB中可能直接用UID作为measurement）
            temp_cols = [str(uid) for uid in temp_uids]
            
            # 获取空调设备的UID列表
            ac_uids = self.air_conditioner_uids
            
            # ==================== 获取空调设定温度的列名 ====================
            # 新格式使用 self.setting_temperature_uids，旧格式从配置读取
            if 'device_uid' in self.uid_config:
                # 旧格式
                set_temp_uids = self.uid_config["dc_status_data_uid"]["air_conditioner_setting_temperature_uid"]
            else:
                # 新格式
                set_temp_uids = self.setting_temperature_uids
            set_temp_cols = [str(uid) for uid in set_temp_uids]
            
            # ==================== 获取能耗数据的UID ====================
            # 能耗数据：优先使用新格式（如果存在），否则使用旧格式
            if 'sensors' in self.uid_config and 'energy_consumption_uid' in self.uid_config['sensors']:
                # 新格式：从 sensors 读取能耗
                power_uids = self.uid_config['sensors']['energy_consumption_uid']
                self.logger.info(f"从新格式配置读取到 {len(power_uids)} 个能耗采集点")
            elif 'dc_status_data_uid' in self.uid_config and 'energy_consumption_collection_uid' in self.uid_config['dc_status_data_uid']:
                # 旧格式：从 dc_status_data_uid 读取
                power_uids = self.uid_config['dc_status_data_uid']['energy_consumption_collection_uid']
                self.logger.info(f"从旧格式配置读取到 {len(power_uids)} 个能耗采集点")
            else:
                self.logger.warning("配置文件中未找到能耗数据配置，将无法计算功耗")
                power_uids = []
            
            power_cols = [str(uid) for uid in power_uids]

            # ==================== 定义空调与电表的对应关系 ====================
            # 注意：这个映射关系需要根据实际的电表配置调整
            # 目前新配置中有9台空调，需要确定它们的电表分组关系
            # 如果没有明确的分组信息，可以假设每台空调独立或需要用户配置
            if power_uids:
                # 简化处理：假设所有空调平均分配到可用的电表
                num_ac = len(ac_uids)
                num_power = len(power_uids)
                ac_to_power_mapping = {}
                for i in range(num_ac):
                    # 按顺序循环分配到电表
                    ac_to_power_mapping[i] = i % num_power
                self.logger.info(f"自动生成空调-电表映射关系: {num_ac}台空调 -> {num_power}个电表")
            else:
                ac_to_power_mapping = {}

            # ==================== 获取湿度传感器UID ====================
            # 支持新格式（sensors）和旧格式（dc_status_data_uid）
            if 'sensors' in self.uid_config and 'humidity_sensor_uid' in self.uid_config['sensors']:
                # 新格式：从 sensors 读取
                humidity_uids = self.uid_config['sensors']['humidity_sensor_uid']
                self.logger.info(f"从新格式配置读取到 {len(humidity_uids)} 个湿度传感器")
            elif 'dc_status_data_uid' in self.uid_config and 'indoor_humidity_sensor_uid' in self.uid_config['dc_status_data_uid']:
                # 旧格式：从 dc_status_data_uid 读取
                humidity_uids = self.uid_config['dc_status_data_uid']['indoor_humidity_sensor_uid']
                self.logger.info(f"从旧格式配置读取到 {len(humidity_uids)} 个湿度传感器")
            else:
                raise ValueError("配置文件中缺少湿度传感器UID配置")
            
            humidity_cols = [str(uid) for uid in humidity_uids]
            
            # ==================== 获取空调设定湿度的列名 ====================
            # 新格式使用 self.air_conditioner_setting_humidity_uids，旧格式从配置读取
            if 'device_uid' in self.uid_config:
                # 旧格式
                set_humidity_uids = self.uid_config["dc_status_data_uid"]["air_conditioner_setting_humidity_uid"]
            else:
                # 新格式
                set_humidity_uids = self.air_conditioner_setting_humidity_uids
            set_humidity_cols = [str(uid) for uid in set_humidity_uids]
            # ==================== 遍历数据并创建历史记录 ====================
            for _, row in data.iterrows():
                # 计算所有温度传感器的平均温度
                avg_temp = row[temp_cols].mean()
                # 计算所有湿度传感器的平均湿度
                avg_humidity = row[humidity_cols].mean()
                
                # 遍历每台空调
                for i, uid in enumerate(ac_uids):
                    # 确保索引不越界
                    if i >= len(set_temp_cols) or i >= len(set_humidity_cols):
                        self.logger.warning(f"空调索引{i}超出设定值列表范围，跳过该空调")
                        continue
                    
                    # 获取该空调的设定温度、设定湿度
                    set_temp = row[set_temp_cols[i]]  # 设定温度
                    set_humidity = row[set_humidity_cols[i]]  # 设定湿度
                    
                    # 获取功耗数据（如果有）
                    if power_cols and i in ac_to_power_mapping:
                        power_index = ac_to_power_mapping[i]
                        if power_index < len(power_cols):
                            power = row[power_cols[power_index]]  # 根据映射关系获取对应电表的功耗
                        else:
                            power = 0.0  # 如果电表索引越界，使用0
                            self.logger.warning(f"电表索引{power_index}越界，使用默认值0")
                    else:
                        power = 0.0  # 如果没有功耗配置，使用0

                    # 创建一条历史数据记录
                    record = DataRecord(
                        set_temp=int(set_temp),  # 设定温度取整数
                        set_humidity=int(set_humidity),  # 设定湿度取整数
                        final_temp=float(avg_temp),  # 最终温度(所有传感器平均值)
                        final_humidity=float(avg_humidity),  # 最终湿度(所有传感器平均值)
                        power=float(power),  # 根据电表分组获取的功耗
                        timestamp=row.get('_time', time.time()),  # 时间戳,如果没有则用当前时间
                        is_optimization_result=False  # 标记为历史数据而非优化结果
                    )
                    self.historical_data.append(record)
            
            power_info = f"根据电表分组分配功耗" if power_cols else "无功耗数据"
            self.logger.info(f"成功添加{len(self.historical_data)}条历史数据（每台空调一条，{power_info}）")
        except Exception as e:
            self.logger.error(f"添加历史数据时发生错误: {str(e)}")
            raise

    def get_system_state(self, current_data: pd.DataFrame) -> Tuple[list, list, list, list, list, list]:
        """
        获取当前系统状态
        Returns:
            Tuple[list, list, list, list, list, list]:
            - 所有温度探头的温度列表
            - 回风温度列表（每台空调）
            - 功耗列表（电表的值）
            - 功耗分组信息（标记哪些空调共用电表）
            - 所有湿度传感器的湿度列表
            - 回风湿度列表（每台空调）
        """
        try:
            row = current_data.iloc[-1]
            
            # ==================== 获取温度传感器数据 ====================
            # 支持新格式（sensors）和旧格式（dc_status_data_uid）
            if 'sensors' in self.uid_config and 'temperature_sensor_uid' in self.uid_config['sensors']:
                temp_uids = self.uid_config['sensors']['temperature_sensor_uid']
            elif 'dc_status_data_uid' in self.uid_config and 'indoor_temperature_sensor_uid' in self.uid_config['dc_status_data_uid']:
                temp_uids = self.uid_config['dc_status_data_uid']['indoor_temperature_sensor_uid']
            else:
                raise ValueError("配置文件中缺少温度传感器UID配置")
            
            temp_cols = [str(uid) for uid in temp_uids]
            temp_list = [row[col] for col in temp_cols]

            # ==================== 获取回风温度数据 ====================
            # 回风温度：从空调测点中提取"回风温度测量值（℃）"
            return_temp_point_names = ['回风温度测量值（℃）', '回风温度测量值', '回风温度']
            return_temp_uids = _extract_uids_from_air_conditioners(self.uid_config, return_temp_point_names)
            
            # 如果没有找到，尝试从旧格式读取
            if not return_temp_uids and 'dc_status_data_uid' in self.uid_config and 'return_air_temperature_uid' in self.uid_config['dc_status_data_uid']:
                return_temp_uids = self.uid_config['dc_status_data_uid']['return_air_temperature_uid']
            
            if return_temp_uids:
                return_temp_cols = [str(uid) for uid in return_temp_uids]
                return_temps = [row[col] for col in return_temp_cols]
            else:
                self.logger.warning("未找到回风温度配置，使用空列表")
                return_temps = []

            # ==================== 获取功耗数据 ====================
            if 'sensors' in self.uid_config and 'energy_consumption_uid' in self.uid_config['sensors']:
                power_uids = self.uid_config['sensors']['energy_consumption_uid']
            elif 'dc_status_data_uid' in self.uid_config and 'energy_consumption_collection_uid' in self.uid_config['dc_status_data_uid']:
                power_uids = self.uid_config['dc_status_data_uid']['energy_consumption_collection_uid']
            else:
                power_uids = []
                self.logger.warning("配置文件中未找到能耗数据配置")
            
            if power_uids:
                power_cols = [str(uid) for uid in power_uids]
                power_values = [row[col] for col in power_cols]
            else:
                power_values = []

            # ==================== 获取湿度传感器数据 ====================
            if 'sensors' in self.uid_config and 'humidity_sensor_uid' in self.uid_config['sensors']:
                humidity_uids = self.uid_config['sensors']['humidity_sensor_uid']
            elif 'dc_status_data_uid' in self.uid_config and 'indoor_humidity_sensor_uid' in self.uid_config['dc_status_data_uid']:
                humidity_uids = self.uid_config['dc_status_data_uid']['indoor_humidity_sensor_uid']
            else:
                raise ValueError("配置文件中缺少湿度传感器UID配置")
            
            humidity_cols = [str(uid) for uid in humidity_uids]
            humidity_list = [row[col] for col in humidity_cols]

            # ==================== 获取回风湿度数据 ====================
            # 回风湿度：从空调测点中提取"回风湿度测量值（%）"
            return_humidity_point_names = ['回风湿度测量值（%）', '回风湿度测量值', '回风湿度']
            return_humidity_uids = _extract_uids_from_air_conditioners(self.uid_config, return_humidity_point_names)
            
            # 如果没有找到，尝试从旧格式读取
            if not return_humidity_uids and 'dc_status_data_uid' in self.uid_config and 'return_air_humidity_uid' in self.uid_config['dc_status_data_uid']:
                return_humidity_uids = self.uid_config['dc_status_data_uid']['return_air_humidity_uid']
            
            if return_humidity_uids:
                return_humidity_cols = [str(uid) for uid in return_humidity_uids]
                return_humidity_list = [row[col] for col in return_humidity_cols]
            else:
                self.logger.warning("未找到回风湿度配置，使用空列表")
                return_humidity_list = []

            # ==================== 定义功耗分组信息 ====================
            # 根据空调数量和电表数量自动生成分组
            num_ac = len(self.air_conditioner_uids)
            num_power = len(power_values)
            
            if num_power > 0:
                power_groups = []
                for power_idx in range(num_power):
                    # 找出使用该电表的所有空调
                    group = [ac_idx for ac_idx in range(num_ac) if ac_idx % num_power == power_idx]
                    power_groups.append(group)
            else:
                # 如果没有功耗数据，每台空调独立
                power_groups = [[i] for i in range(num_ac)]

            self.logger.info(f"成功获取系统状态: temp_sensors={len(temp_list)}, "
                             f"humidity_sensors={len(humidity_list)}, "
                             f"return_temps={len(return_temps)}, "
                             f"return_humidity={len(return_humidity_list)}, "
                             f"power_meters={len(power_values)}")

            return temp_list, return_temps, power_values, power_groups, humidity_list, return_humidity_list
        except Exception as e:
            self.logger.error(f"获取系统状态时发生错误: {str(e)}")
            raise

    def wait_for_stabilization(self) -> None:
        """等待系统稳定"""
        time.sleep(self.stabilization_time)

    def reset(self) -> Optional[Dict]:
        """重置优化过程并返回上一个最优状态参数"""
        self.state = OptimizationState.RESETTING
        self.stop_event.set()

        # 等待优化过程完全停止
        while self.state != OptimizationState.IDLE:
            time.sleep(0.1)

        # 获取上一个最优状态
        if self.previous_best_params:
            self.logger.info(f"已获取上一个最优状态参数: {self.previous_best_params}")
            return self.previous_best_params
        else:
            self.logger.warning("没有可用的上一个最优状态")
            return None

        self.stop_event.clear()
        self.state = OptimizationState.IDLE


# 定义动态优化器类
class DynamicOptimizer:
    def __init__(self,
                 controller: ACController,
                 parameter_config: Dict,
                 security_boundary_config: Dict):
        self.controller = controller
        self.logger = controller.logger

        # 从配置文件读取参数
        optimization_params = parameter_config["optimization_module"]
        # 移除目标温度和湿度设置，改为边界约束
        self.historical_weight = float(optimization_params.get("historical_weight", 0.3))

        # 从安全边界配置读取温度上限和湿度区间
        self.max_safe_temp = float(security_boundary_config.get("maximum_safe_temperature", 28.0))  # 温度安全上限
        self.min_safe_humidity = float(security_boundary_config.get("minimum_safe_humidity", 40.0))  # 湿度安全下限
        self.max_safe_humidity = float(security_boundary_config.get("maximum_safe_humidity", 60.0))  # 湿度安全上限

        # 从安全边界配置读取空调设定范围
        self.min_humidity = int(security_boundary_config.get("minimum_air_conditioner_setting_humidity", 30))
        self.max_humidity = int(security_boundary_config.get("maximum_air_conditioner_setting_humidity", 70))

        self.study = None
        self.optimization_thread = None
        self.initial_params = None  # 添加初始参数属性
        self.temp_reset_params = None  # 添加临时重置参数属性

        self.logger.info(f"优化器初始化完成: "
                         f"max_safe_temp={self.max_safe_temp}, "
                         f"min_safe_humidity={self.min_safe_humidity}, "
                         f"max_safe_humidity={self.max_safe_humidity}, "
                         f"historical_weight={self.historical_weight}")

    def set_initial_params(self, set_temp: int, set_humidity: int = None) -> None:
        """设置初始参数"""
        if not (16 <= set_temp <= 30):
            raise ValueError("设定温度必须在16-30℃范围内")

        if set_humidity is None:
            set_humidity = 50  # 使用默认湿度值50%

        if not (self.min_humidity <= set_humidity <= self.max_humidity):
            raise ValueError(f"设定湿度必须在{self.min_humidity}-{self.max_humidity}%范围内")

        self.initial_params = {'set_temp': set_temp, 'set_humidity': set_humidity}
        self.logger.info(f"已设置初始参数: 温度={set_temp}℃, 湿度={set_humidity}%")

    def calculate_objective_from_historical(self, set_temp: int, set_humidity: int, cooling_mode: int = 1) -> float:
        """从历史数据计算目标值 - 以最小化功耗为主要目标"""
        if not self.controller.historical_data:
            return 0.0

        total_power = 0.0
        count = 0

        for data in self.controller.historical_data:
            # 定义误差范围
            temp_tolerance = 0.5
            humidity_tolerance = 5.0

            # 检查是否有制冷模式属性，如果没有则设为默认值1
            data_cooling_mode = getattr(data, 'cooling_mode', 1)

            if (abs(data.set_temp - set_temp) <= temp_tolerance and
                    abs(data.set_humidity - set_humidity) <= humidity_tolerance and
                    data_cooling_mode == cooling_mode):
                # 检查历史数据是否满足安全约束
                if (data.final_temp <= self.max_safe_temp and
                        self.min_safe_humidity <= data.final_humidity <= self.max_safe_humidity):
                    # 主要目标：最小化功耗
                    total_power += data.power
                    count += 1

        return total_power / count if count > 0 else 0.0

    def temporary_reset(self) -> Optional[Dict]:
        """临时重置到上一个最优状态，返回参数但不影响优化过程"""
        if self.controller.previous_best_params:
            self.logger.info(f"临时重置到上一个最优状态: {self.controller.previous_best_params}")
            return self.controller.previous_best_params
        else:
            self.logger.warning("没有可用的上一个最优状态用于临时重置")
            return None

    def objective(self, trial: optuna.Trial, current_data: pd.DataFrame) -> float:
        """优化目标函数"""
        if self.controller.stop_event.is_set():
            raise optuna.TrialPruned()

        # 获取当前系统状态（包含湿度数据）
        current_temps, return_temps, power_values, power_groups, current_humidity, return_humidity = self.controller.get_system_state(
            current_data)

        # 安全地获取参数：优先使用trial建议的参数，避免访问可能不存在的best_params
        set_temp = trial.suggest_int('set_temp', 16, 30)
        set_humidity = trial.suggest_int('set_humidity', self.min_humidity, self.max_humidity)
        cooling_mode = trial.suggest_int('cooling_mode', 0, 1)  # 0=空闲模式, 1=制冷模式

        # 如果有历史最优参数且当前不是第一个trial，可以考虑使用历史参数作为参考
        # 但为了避免"No trials are completed yet"错误，我们总是使用trial建议的参数

        try:
            # 计算历史数据的目标值（包含湿度和制冷模式）
            historical_objective = self.calculate_objective_from_historical(set_temp, set_humidity, cooling_mode)

            # 在等待稳定期间持续进行安全检查
            start_time = time.time()
            while time.time() - start_time < self.controller.stabilization_time:
                # 获取当前系统状态（包含湿度）
                current_temps, return_temps, power_values, power_groups, current_humidity, return_humidity = self.controller.get_system_state(
                    current_data)

                # 检查所有温度探头是否超过安全上限
                for temp in current_temps:
                    if temp > self.max_safe_temp:
                        self.logger.warning(f"温度超出安全上限: {temp:.2f}℃ > {self.max_safe_temp}℃")
                        # 临时重置到上一个最优状态
                        self.temporary_reset()
                        return float('inf')

                # 检查所有湿度传感器是否在安全区间内
                for humidity in current_humidity:
                    if humidity < self.min_safe_humidity or humidity > self.max_safe_humidity:
                        self.logger.warning(
                            f"湿度超出安全区间: {humidity:.2f}% (安全区间: {self.min_safe_humidity}%-{self.max_safe_humidity}%)")
                        # 临时重置到上一个最优状态
                        self.temporary_reset()
                        return float('inf')

                # 每10秒检查一次
                time.sleep(10)

            # 从传入的数据获取系统最终状态（包含湿度）
            final_temps, final_return_temps, final_power_values, final_power_groups, final_humidity, final_return_humidity = self.controller.get_system_state(
                current_data)
            avg_temp = sum(final_temps) / len(final_temps)  # 计算平均温度
            avg_humidity = sum(final_humidity) / len(final_humidity)  # 计算平均湿度

            # 检查最终状态是否满足安全约束
            if avg_temp > self.max_safe_temp:
                self.logger.warning(f"最终温度超出安全上限: {avg_temp:.2f}℃ > {self.max_safe_temp}℃")
                return float('inf')

            if avg_humidity < self.min_safe_humidity or avg_humidity > self.max_safe_humidity:
                self.logger.warning(
                    f"最终湿度超出安全区间: {avg_humidity:.2f}% (安全区间: {self.min_safe_humidity}%-{self.max_safe_humidity}%)")
                return float('inf')

            # 主要目标：最小化总功耗
            real_time_objective = sum(final_power_values)

            # 记录优化结果（包含制冷模式）
            record = DataRecord(
                set_temp=set_temp,
                set_humidity=set_humidity,
                final_temp=avg_temp,
                final_humidity=avg_humidity,
                power=sum(final_power_values),
                timestamp=time.time(),
                cooling_mode=cooling_mode,
                is_optimization_result=True
            )
            self.controller.historical_data.append(record)

            # 组合目标值：考虑历史数据和实时数据
            combined_objective = (1 - self.historical_weight) * real_time_objective + \
                                 self.historical_weight * historical_objective

            self.logger.info(f"优化目标值计算完成: set_temp={set_temp}, set_humidity={set_humidity}, "
                             f"cooling_mode={cooling_mode}, avg_temp={avg_temp:.2f}, avg_humidity={avg_humidity:.2f}, "
                             f"total_power={sum(final_power_values):.2f}, objective={combined_objective:.2f} "
                             f"(主要目标: 最小化功耗)")

            return combined_objective

        except Exception as e:
            self.logger.error(f"计算优化目标值时发生错误: {str(e)}")
            raise

    def start_optimization(self, current_data: pd.DataFrame) -> None:
        """启动优化过程，执行一次优化迭代"""
        if self.controller.state != OptimizationState.IDLE:
            self.logger.warning("优化已在运行中，跳过本次启动")
            return

        try:
            self.controller.state = OptimizationState.RUNNING
            self.study = optuna.create_study(direction='minimize')

            # 如果有初始参数，先应用初始参数
            if self.initial_params:
                try:
                    self.controller.logger.info(f"已应用并记录初始参数效果: 温度={self.initial_params['set_temp']}℃")
                except Exception as e:
                    self.logger.error(f"应用初始参数时发生错误: {str(e)}")

            def optimization_loop():
                try:
                    self.study.optimize(
                        lambda trial: self.objective(trial, current_data),
                        n_trials=20,  # 执行20次试验
                        callbacks=[lambda study, trial: self._check_stop_condition()],
                        timeout=300  # 5分钟超时
                    )
                    self.logger.info(f"优化完成，共完成 {len(self.study.trials)} 次试验")
                except optuna.TrialPruned:
                    self.logger.info("优化被提前停止")
                except Exception as e:
                    self.logger.error(f"优化过程中发生错误: {str(e)}")
                finally:
                    self.controller.state = OptimizationState.IDLE

            self.optimization_thread = threading.Thread(target=optimization_loop, daemon=True)
            self.optimization_thread.start()
            self.logger.info("优化过程已启动，执行多次迭代")

        except Exception as e:
            self.logger.error(f"启动优化过程时发生错误: {str(e)}")
            self.controller.state = OptimizationState.IDLE
            raise

    def _check_stop_condition(self) -> None:
        """检查是否需要停止优化"""
        if self.controller.stop_event.is_set():
            raise optuna.TrialPruned()

    def get_best_params(self) -> Optional[Dict]:
        """安全地获取当前最优参数，等待优化完成"""
        if self.study is None:
            self.logger.warning("Study未初始化，无法获取最优参数")
            return None

        # 等待优化线程完成
        if self.optimization_thread and self.optimization_thread.is_alive():
            self.logger.info("等待优化过程完成...")
            self.optimization_thread.join(timeout=600)  # 最多等待10分钟

            if self.optimization_thread.is_alive():
                self.logger.error("优化过程超时，强制停止")
                self.controller.stop_event.set()
                return None

        # 检查是否有完成的trial
        try:
            if len(self.study.trials) == 0:
                self.logger.warning("没有完成的优化试验，无法获取最优参数")
                return None

            # 检查是否有成功完成的trial
            completed_trials = [t for t in self.study.trials if t.state == optuna.trial.TrialState.COMPLETE]
            if len(completed_trials) == 0:
                self.logger.warning("没有成功完成的优化试验，无法获取最优参数")
                return None

            # 安全地获取最优参数
            best_params = self.study.best_params
            self.logger.info(f"获取到最优参数: {best_params}")
            return best_params

        except ValueError as e:
            if "No trials are completed yet" in str(e):
                self.logger.warning("优化试验尚未完成，无法获取最优参数")
                return None
            else:
                self.logger.error(f"获取最优参数时发生ValueError: {str(e)}")
                return None
        except Exception as e:
            self.logger.error(f"获取最优参数时发生未知错误: {str(e)}")
            return None

    def stop(self) -> None:
        """停止优化过程"""
        self.controller.reset()
        self.logger.info("优化过程已停止")

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
    def __init__(self):
        self.ac_instances = {}

    def initialize_instances(self,
                             uid_config: Dict,
                             parameter_config: Dict,
                             security_boundary_config: Dict,
                             logger: logging.Logger,
                             is_reference: bool = False) -> None:
        """初始化所有空调实例"""
        try:
            # 清除现有实例
            self.ac_instances.clear()

            # 获取空调UID列表
            ac_uids = uid_config['device_uid']['air_conditioner_uid']
            if not ac_uids:
                raise ValueError("空调UID列表为空")

            for uid in ac_uids:
                controller = ACController(uid_config, logger, is_reference)
                optimizer = DynamicOptimizer(controller, parameter_config, security_boundary_config)
                self.ac_instances[str(uid)] = optimizer  # 确保uid是字符串
                logger.info(f"成功创建空调 {uid} 的优化器实例")

            logger.info(f"成功初始化所有空调实例，共 {len(self.ac_instances)} 个实例")
        except Exception as e:
            logger.error(f"初始化空调实例时发生错误: {str(e)}")
            raise

    def get_instance(self, uid: str) -> Optional[DynamicOptimizer]:
        """获取指定空调的优化器实例"""
        uid = str(uid)  # 确保uid是字符串
        optimizer = self.ac_instances.get(uid)
        if optimizer is None:
            raise ValueError(f"未找到空调 {uid} 的优化器实例")
        return optimizer

    def get_all_instances(self) -> Dict[str, DynamicOptimizer]:
        """获取所有空调的优化器实例"""
        return self.ac_instances.copy()


def start_optimization_process(
        uid_config: dict,
        parameter_config: dict,
        security_boundary_config: dict,
        optimization_input: pd.DataFrame,
        current_data: pd.DataFrame,
        logger: logging.Logger,
        is_reference: bool = False,
        ac_manager: Optional[ACInstanceManager] = None
) -> dict:
    """
    启动优化过程，对所有空调进行优化。
    Args:
        uid_config: UID配置信息
        parameter_config: 参数配置信息
        security_boundary_config: 安全边界配置信息
        optimization_input: 历史数据（过去60分钟）
        current_data: 当前系统状态数据
        logger: 日志记录器
        is_reference: 是否为参考优化
        ac_manager: 空调实例管理器，如果为None则每次创建新实例
    Returns:
        dict: 包含每台空调优化后的设定温度和开关状态
    """
    try:
        # 初始化返回结果
        best_params = {
            'air_conditioner_setting_temperature': [],  # 6个值：每台空调一个
            'air_conditioner_setting_humidity': [],  # 6个值：每台空调一个
            'air_conditioner_cooling_mode': [],  # 8个值：每台制冷机一个
        }

        # 获取空调UID列表
        ac_uids = uid_config['device_uid']['air_conditioner_uid']
        if not ac_uids:
            raise ValueError("空调UID列表为空")

        # 如果没有提供ac_manager，则创建一个新的实例管理器
        if ac_manager is None:
            logger.info("未提供空调实例管理器，创建新的实例管理器")
            ac_manager = ACInstanceManager()
            ac_manager.initialize_instances(uid_config, parameter_config, security_boundary_config, logger,
                                            is_reference)

        # 定义空调与制冷机的映射关系
        # 艾特网能空调1#、2#每台有2个制冷机，其余每台有1个制冷机
        cooling_mode_mapping = {
            0: [0, 1],  # 艾特网能空调1# -> 制冷机1, 2
            1: [2, 3],  # 艾特网能空调2# -> 制冷机3, 4
            2: [4],  # 美的空调 -> 制冷机5
            3: [5],  # 维谛精密空调1 -> 制冷机6
            4: [6],  # 维谛空调2 -> 制冷机7
            5: [7]  # 维谛空调3 -> 制冷机8
        }

        # 按功耗分组进行优化
        # 第一组：艾特网能空调1#（单独电表）
        uid = ac_uids[0]
        logger.info(f"开始优化第一组空调：艾特网能空调1# (UID: {uid})")
        optimizer = ac_manager.get_instance(uid)
        # 更新历史数据
        optimizer.controller.add_historical_data(optimization_input)
        # 启动优化
        optimizer.start_optimization(current_data)
        # 安全地获取最优参数
        params = optimizer.get_safe_params()
        best_params['air_conditioner_setting_temperature'].append(params['set_temp'])
        best_params['air_conditioner_setting_humidity'].append(params['set_humidity'])
        # 艾特网能空调1#有2个制冷机，添加2个制冷模式值
        cooling_mode_value = params.get('cooling_mode', 1)  # 获取优化的制冷模式，默认为1
        for _ in cooling_mode_mapping[0]:  # 添加2个制冷机的值
            best_params['air_conditioner_cooling_mode'].append(cooling_mode_value)
        logger.info(
            f"空调 {uid} 优化完成，设定温度: {params['set_temp']}℃, 设定湿度: {params['set_humidity']}%, 制冷模式: {cooling_mode_value}")

        # 第二组：艾特网能空调2#和美的空调（共用电表）
        group2_uids = ac_uids[1:3]
        logger.info(f"开始优化第二组空调：艾特网能空调2#和美的空调 (UIDs: {group2_uids})")
        for i, uid in enumerate(group2_uids, start=1):  # i从1开始，对应索引1和2
            optimizer = ac_manager.get_instance(uid)
            # 更新历史数据
            optimizer.controller.add_historical_data(optimization_input)
            # 启动优化
            optimizer.start_optimization(current_data)
            # 安全地获取最优参数
            params = optimizer.get_safe_params()
            best_params['air_conditioner_setting_temperature'].append(params['set_temp'])
            best_params['air_conditioner_setting_humidity'].append(params['set_humidity'])
            # 根据映射关系添加制冷模式值
            cooling_mode_value = params.get('cooling_mode', 1)
            for _ in cooling_mode_mapping[i]:  # 艾特网能空调2#有2个制冷机，美的空调有1个
                best_params['air_conditioner_cooling_mode'].append(cooling_mode_value)
            logger.info(
                f"空调 {uid} 优化完成，设定温度: {params['set_temp']}℃, 设定湿度: {params['set_humidity']}%, 制冷模式: {cooling_mode_value}")

        # 第三组：维谛精密空调1、维谛空调2、维谛空调3（共用电表）
        group3_uids = ac_uids[3:]
        logger.info(f"开始优化第三组空调：维谛精密空调 (UIDs: {group3_uids})")
        for i, uid in enumerate(group3_uids, start=3):  # i从3开始，对应索引3、4、5
            optimizer = ac_manager.get_instance(uid)
            # 更新历史数据
            optimizer.controller.add_historical_data(optimization_input)
            # 启动优化
            optimizer.start_optimization(current_data)
            # 安全地获取最优参数
            params = optimizer.get_safe_params()
            best_params['air_conditioner_setting_temperature'].append(params['set_temp'])
            best_params['air_conditioner_setting_humidity'].append(params['set_humidity'])
            # 维谛空调每台有1个制冷机
            cooling_mode_value = params.get('cooling_mode', 1)
            for _ in cooling_mode_mapping[i]:  # 每台维谛空调有1个制冷机
                best_params['air_conditioner_cooling_mode'].append(cooling_mode_value)
            logger.info(
                f"空调 {uid} 优化完成，设定温度: {params['set_temp']}℃, 设定湿度: {params['set_humidity']}%, 制冷模式: {cooling_mode_value}")

        # 验证结果完整性
        expected_ac_count = len(ac_uids)  # 期望6台空调
        expected_cooling_mode_count = 8  # 期望8个制冷机

        actual_temp_count = len(best_params['air_conditioner_setting_temperature'])
        actual_humidity_count = len(best_params['air_conditioner_setting_humidity'])
        actual_cooling_mode_count = len(best_params['air_conditioner_cooling_mode'])

        if actual_temp_count != expected_ac_count:
            raise ValueError(f"温度设定结果数量不匹配：期望 {expected_ac_count} 个，实际 {actual_temp_count} 个")
        if actual_humidity_count != expected_ac_count:
            raise ValueError(f"湿度设定结果数量不匹配：期望 {expected_ac_count} 个，实际 {actual_humidity_count} 个")
        if actual_cooling_mode_count != expected_cooling_mode_count:
            raise ValueError(
                f"制冷模式结果数量不匹配：期望 {expected_cooling_mode_count} 个，实际 {actual_cooling_mode_count} 个")

        logger.info(
            f"所有空调优化完成 - 温度设定: {actual_temp_count}个, 湿度设定: {actual_humidity_count}个, 制冷模式: {actual_cooling_mode_count}个")
        return best_params
    except Exception as e:
        logger.error(f"优化过程发生错误: {str(e)}")
        raise