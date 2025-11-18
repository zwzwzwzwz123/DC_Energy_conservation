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


# ==================== 辅助函数 ====================

def _get_air_conditioner_uids_and_names(uid_config: Dict) -> Tuple[List[str], List[str]]:
    """
    从UID配置中提取空调的UID和名称列表

    参数:
        uid_config: UID配置字典（新格式，包含 'air_conditioners' 字段）

    返回:
        Tuple[List[str], List[str]]: (UID列表, 名称列表)
        - UID列表：每台空调的第一个测点UID（作为设备标识）
        - 名称列表：每台空调的设备名称

    示例:
        uid_config = {
            "air_conditioners": {
                "空调1": {
                    "device_name": "空调1",
                    "measurement_points": {"温度": "uid1", "湿度": "uid2"}
                },
                "空调2": {
                    "device_name": "空调2",
                    "measurement_points": {"温度": "uid3", "湿度": "uid4"}
                }
            }
        }
        uids, names = _get_air_conditioner_uids_and_names(uid_config)
        # uids = ["uid1", "uid3"]
        # names = ["空调1", "空调2"]
    """
    if 'air_conditioners' not in uid_config:
        raise ValueError("UID配置中缺少 'air_conditioners' 字段")

    air_conditioners = uid_config['air_conditioners']
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
            # 如果没有测点，使用设备名称作为UID
            uids.append(device_name)

    return uids, names


def _extract_uids_from_air_conditioners(uid_config: Dict, point_names: List[str]) -> List[str]:
    """
    从UID配置中提取指定测点名称的UID列表

    参数:
        uid_config: UID配置字典（新格式，包含 'air_conditioners' 字段）
        point_names: 要提取的测点名称列表（支持多个候选名称）

    返回:
        List[str]: 每台空调对应测点的UID列表（按空调顺序）

    示例:
        uid_config = {
            "air_conditioners": {
                "空调1": {
                    "measurement_points": {"温度设定值": "uid1", "湿度设定值": "uid2"}
                },
                "空调2": {
                    "measurement_points": {"温度设定点": "uid3", "湿度设定点": "uid4"}
                }
            }
        }
        uids = _extract_uids_from_air_conditioners(uid_config, ['温度设定值', '温度设定点'])
        # uids = ["uid1", "uid3"]
    """
    if 'air_conditioners' not in uid_config:
        raise ValueError("UID配置中缺少 'air_conditioners' 字段")

    air_conditioners = uid_config['air_conditioners']
    uids = []

    for ac_name, ac_info in air_conditioners.items():
        measurement_points = ac_info.get('measurement_points', {})

        # 尝试匹配任意一个候选测点名称
        found_uid = None
        for point_name in point_names:
            if point_name in measurement_points:
                found_uid = measurement_points[point_name]
                break

        if found_uid:
            uids.append(found_uid)
        else:
            # 如果没有找到匹配的测点，记录警告但继续处理
            # 这里不抛出异常，因为某些空调可能没有某些测点
            pass

    return uids


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

        # 添加线程安全锁
        self.state_lock = threading.Lock()
        self.params_lock = threading.Lock()

        # 设备UID初始化 - 使用新配置格式
        if 'air_conditioners' not in self.uid_config:
            raise ValueError("UID配置格式不正确，缺少 'air_conditioners' 字段")

        self.logger.info("开始解析空调UID配置")

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

        # 状态和数据处理初始化
        self.state = OptimizationState.IDLE
        self.result_queue = queue.Queue()
        self.stop_event = threading.Event()
        # 根据是否为参考优化设置不同的稳定时间
        self.stabilization_time = 1 if is_reference else 300  # 参考优化1秒钟，实际优化5分钟
        self.historical_data: List[DataRecord] = []
        self.max_historical_records = 1000  # 最多保留1000条历史记录
        # 根据uid确定空调数量
        # self.number_of_ac = len(self.air_conditioner_uids)
        self.previous_best_params = None  # 添加存储上一个最优状态的属性

    def add_historical_data(self, data: pd.DataFrame) -> None:
        """添加历史数据，每台空调一条记录，根据电表分组正确分配能耗数据"""
        try:
            self.historical_data.clear()
            
            # ==================== 获取温度传感器UID ====================
            if 'sensors' not in self.uid_config or 'temperature_sensor_uid' not in self.uid_config['sensors']:
                raise ValueError("配置文件中缺少温度传感器UID配置 (sensors.temperature_sensor_uid)")

            temp_uids = self.uid_config['sensors']['temperature_sensor_uid']
            self.logger.info(f"读取到 {len(temp_uids)} 个温度传感器")
            
            # 温度传感器列名需要去掉前缀，直接使用UID（因为InfluxDB中可能直接用UID作为measurement）
            temp_cols = [str(uid) for uid in temp_uids]
            
            # 获取空调设备的UID列表
            ac_uids = self.air_conditioner_uids
            
            # ==================== 获取空调设定温度的列名 ====================
            set_temp_uids = self.setting_temperature_uids
            set_temp_cols = [str(uid) for uid in set_temp_uids]
            
            # ==================== 获取能耗数据的UID ====================
            if 'sensors' in self.uid_config and 'energy_consumption_uid' in self.uid_config['sensors']:
                power_uids = self.uid_config['sensors']['energy_consumption_uid']
                self.logger.info(f"读取到 {len(power_uids)} 个能耗采集点")
            else:
                self.logger.warning("配置文件中未找到能耗数据配置 (sensors.energy_consumption_uid)，将无法计算功耗")
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
            if 'sensors' not in self.uid_config or 'humidity_sensor_uid' not in self.uid_config['sensors']:
                raise ValueError("配置文件中缺少湿度传感器UID配置 (sensors.humidity_sensor_uid)")

            humidity_uids = self.uid_config['sensors']['humidity_sensor_uid']
            self.logger.info(f"读取到 {len(humidity_uids)} 个湿度传感器")
            
            humidity_cols = [str(uid) for uid in humidity_uids]
            
            # ==================== 获取空调设定湿度的列名 ====================
            set_humidity_uids = self.air_conditioner_setting_humidity_uids
            set_humidity_cols = [str(uid) for uid in set_humidity_uids]
            # ==================== 遍历数据并创建历史记录 ====================
            for _, row in data.iterrows():
                # 计算所有温度传感器的平均温度
                avg_temp = row[temp_cols].mean()
                # 计算所有湿度传感器的平均湿度
                avg_humidity = row[humidity_cols].mean()
                
                # 遍历每台空调
                for i, _uid in enumerate(ac_uids):
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
            if 'sensors' not in self.uid_config or 'temperature_sensor_uid' not in self.uid_config['sensors']:
                raise ValueError("配置文件中缺少温度传感器UID配置 (sensors.temperature_sensor_uid)")

            temp_uids = self.uid_config['sensors']['temperature_sensor_uid']
            
            temp_cols = [str(uid) for uid in temp_uids]
            temp_list = [row[col] for col in temp_cols]

            # ==================== 获取回风温度数据 ====================
            # 回风温度：从空调测点中提取"回风温度测量值（℃）"
            return_temp_point_names = ['回风温度测量值（℃）', '回风温度测量值', '回风温度']
            return_temp_uids = _extract_uids_from_air_conditioners(self.uid_config, return_temp_point_names)

            if return_temp_uids:
                return_temp_cols = [str(uid) for uid in return_temp_uids]
                return_temps = [row[col] for col in return_temp_cols]
            else:
                self.logger.warning("未找到回风温度配置，使用空列表")
                return_temps = []

            # ==================== 获取功耗数据 ====================
            if 'sensors' in self.uid_config and 'energy_consumption_uid' in self.uid_config['sensors']:
                power_uids = self.uid_config['sensors']['energy_consumption_uid']
                power_cols = [str(uid) for uid in power_uids]
                power_values = [row[col] for col in power_cols]
            else:
                self.logger.warning("配置文件中未找到能耗数据配置 (sensors.energy_consumption_uid)")
                power_values = []

            # ==================== 获取湿度传感器数据 ====================
            if 'sensors' not in self.uid_config or 'humidity_sensor_uid' not in self.uid_config['sensors']:
                raise ValueError("配置文件中缺少湿度传感器UID配置 (sensors.humidity_sensor_uid)")

            humidity_uids = self.uid_config['sensors']['humidity_sensor_uid']
            
            humidity_cols = [str(uid) for uid in humidity_uids]
            humidity_list = [row[col] for col in humidity_cols]

            # ==================== 获取回风湿度数据 ====================
            # 回风湿度：从空调测点中提取"回风湿度测量值（%）"
            return_humidity_point_names = ['回风湿度测量值（%）', '回风湿度测量值', '回风湿度']
            return_humidity_uids = _extract_uids_from_air_conditioners(self.uid_config, return_humidity_point_names)

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
        self.logger.info("开始重置优化过程...")

        with self.state_lock:
            self.state = OptimizationState.RESETTING

        self.stop_event.set()

        # 等待优化过程完全停止（添加超时保护）
        # 注意：这里等待的是外部优化线程结束，而不是状态变化
        # 状态需要在这个方法中手动设置
        timeout = 30  # 30秒超时
        start_time = time.time()

        while time.time() - start_time < timeout:
            # 这里简单等待一段时间，让优化线程有机会响应停止信号
            # 实际的线程等待应该在 DynamicOptimizer.stop() 中处理
            time.sleep(0.1)
            # 可以添加额外的检查逻辑，例如检查优化线程是否还在运行
            break  # 暂时直接退出，避免长时间等待

        # 保存上一个最优状态
        with self.params_lock:
            previous_params = self.previous_best_params

        # 清理状态
        self.stop_event.clear()
        with self.state_lock:
            self.state = OptimizationState.IDLE

        if previous_params:
            self.logger.info(f"重置完成，返回上一个最优状态参数: {previous_params}")
            return previous_params
        else:
            self.logger.warning("重置完成，但没有可用的上一个最优状态")
            return None


# 定义动态优化器类（重构版本，支持多种优化算法）
class DynamicOptimizer:
    """
    动态优化器类
    支持多种优化算法的统一接口
    """

    def __init__(self,
                 controller: ACController,
                 parameter_config: Dict,
                 security_boundary_config: Dict):
        self.controller = controller
        self.logger = controller.logger
        self.parameter_config = parameter_config
        self.security_boundary_config = security_boundary_config

        # 从配置文件读取优化算法类型
        optimization_params = parameter_config.get("optimization_module", {})
        self.algorithm = optimization_params.get("algorithm", "bayesian")

        # 延迟导入优化器工厂（运行时导入）
        from .optimizers import OptimizerFactory

        # 创建具体的优化器实例
        try:
            self.optimizer = OptimizerFactory.create_optimizer(
                algorithm=self.algorithm,
                controller=controller,
                parameter_config=parameter_config,
                security_boundary_config=security_boundary_config,
                logger=self.logger
            )
            self.logger.info(f"成功创建优化器: {self.algorithm}")
        except ValueError as e:
            self.logger.error(f"创建优化器失败: {str(e)}")
            # 回退到贝叶斯优化
            self.logger.warning("回退到默认的贝叶斯优化算法")
            self.algorithm = "bayesian"
            self.optimizer = OptimizerFactory.create_optimizer(
                algorithm="bayesian",
                controller=controller,
                parameter_config=parameter_config,
                security_boundary_config=security_boundary_config,
                logger=self.logger
            )

        # 保留一些通用属性以兼容旧代码
        self.historical_weight = float(optimization_params.get("historical_weight", 0.3))
        self.max_safe_temp = float(security_boundary_config.get("maximum_safe_indoor_temperature", 28.0))
        self.min_safe_humidity = float(security_boundary_config.get("minimum_safe_indoor_humidity", 30.0))
        self.max_safe_humidity = float(security_boundary_config.get("maximum_safe_indoor_humidity", 70.0))
        self.min_humidity = int(security_boundary_config.get("minimum_air_conditioner_setting_humidity", 30))
        self.max_humidity = int(security_boundary_config.get("maximum_air_conditioner_setting_humidity", 70))

        self.optimization_thread = None
        self.initial_params = None
        self.temp_reset_params = None

        self.logger.info(f"优化器初始化完成: "
                         f"algorithm={self.algorithm}, "
                         f"max_safe_temp={self.max_safe_temp}, "
                         f"min_safe_humidity={self.min_safe_humidity}, "
                         f"max_safe_humidity={self.max_safe_humidity}, "
                         f"historical_weight={self.historical_weight}")

    def set_initial_params(self, set_temp: int, set_humidity: int = None) -> None:
        """设置初始参数"""
        if not (16 <= set_temp <= 30):
            raise ValueError("设定温度必须在16-30℃范围内")

        # 检查温度安全约束
        if set_temp > self.max_safe_temp:
            self.logger.warning(
                f"设定温度 {set_temp}℃ 超过安全上限 {self.max_safe_temp}℃，"
                f"优化过程可能无法找到满足约束的解"
            )

        if set_humidity is None:
            set_humidity = 50  # 使用默认湿度值50%

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

    def get_best_params(self) -> Optional[Dict]:
        """
        安全地获取当前最优参数，等待优化完成
        使用新的优化器接口
        """
        # 等待优化线程完成
        if self.optimization_thread and self.optimization_thread.is_alive():
            self.logger.info("等待优化过程完成...")
            self.optimization_thread.join(timeout=600)  # 最多等待10分钟

            if self.optimization_thread.is_alive():
                self.logger.error("优化过程超时，强制停止")
                self.controller.stop_event.set()

                # 再等待一小段时间让线程响应停止信号
                self.optimization_thread.join(timeout=5)

                if self.optimization_thread.is_alive():
                    self.logger.error("线程未能响应停止信号，可能存在僵尸线程")

                # 重置状态
                with self.controller.state_lock:
                    self.controller.state = OptimizationState.IDLE

                return None

        # 从优化器获取最优参数
        try:
            best_params = self.optimizer.get_best_params()
            if best_params:
                self.logger.info(f"获取到最优参数: {best_params}")
            else:
                self.logger.warning("优化器未返回有效参数")
            return best_params
        except Exception as e:
            self.logger.error(f"获取最优参数时发生错误: {str(e)}")
            return None

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
    def __init__(self):
        self.ac_instances = {}

    def initialize_instances(self,
                             uid_config: Dict,
                             parameter_config: Dict,
                             security_boundary_config: Dict,
                             logger: logging.Logger,
                             is_reference: bool = False) -> None:
        """初始化所有空调实例（支持新格式配置）"""
        try:
            # 清除现有实例
            self.ac_instances.clear()

            # 获取空调UID列表（支持新格式配置）
            ac_uids, ac_names = _get_air_conditioner_uids_and_names(uid_config)
            if not ac_uids:
                raise ValueError("空调UID列表为空")

            for uid, name in zip(ac_uids, ac_names):
                controller = ACController(uid_config, logger, is_reference)
                optimizer = DynamicOptimizer(controller, parameter_config, security_boundary_config)
                self.ac_instances[str(uid)] = optimizer  # 确保uid是字符串
                logger.info(f"成功创建空调 {name} (UID: {uid}) 的优化器实例")

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

    注意：此函数仅计算优化参数，不执行实际控制。
    实际的参数应用由主函数负责写入InfluxDB。

    Args:
        uid_config: UID配置信息（支持新格式配置）
        parameter_config: 参数配置信息
        security_boundary_config: 安全边界配置信息
        optimization_input: 历史数据（过去60分钟）
        current_data: 当前系统状态数据
        logger: 日志记录器
        is_reference: 是否为参考优化
        ac_manager: 空调实例管理器，如果为None则每次创建新实例
    Returns:
        dict: 包含每台空调优化后的设定温度、湿度和制冷模式
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

        for idx, (uid, name) in enumerate(zip(ac_uids, ac_names)):
            logger.info(f"正在优化空调 [{idx+1}/{len(ac_uids)}]: {name} (UID: {uid})")

            try:
                # 获取优化器实例
                optimizer = ac_manager.get_instance(uid)

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

            except Exception as e:
                logger.error(f"优化空调 {name} (UID: {uid}) 时发生错误: {str(e)}")
                # 使用默认参数
                best_params['air_conditioner_setting_temperature'].append(24)
                best_params['air_conditioner_setting_humidity'].append(50)
                best_params['air_conditioner_cooling_mode'].append(1)
                logger.warning(f"空调 {name} 使用默认参数: 温度=24℃, 湿度=50%, 制冷模式=1")

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