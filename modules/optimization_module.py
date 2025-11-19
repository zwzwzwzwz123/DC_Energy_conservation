import pandas as pd
import time
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING, Union
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


def _is_timeseries_mapping(data: Any) -> bool:
    """判断输入是否为 {uid: DataFrame} 的结构"""
    if not isinstance(data, dict):
        return False
    return all(isinstance(df, pd.DataFrame) for df in data.values())


def _merge_timeseries_dict_to_dataframe(data_dict: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    将 {uid: DataFrame} 的结构合并为单一 DataFrame，列名使用 uid
    方便与原有的优化流程兼容
    """
    frames = []
    for uid, df in data_dict.items():
        if df is None or df.empty:
            continue

        df_local = df.copy()

        # 检测时间列
        time_col = None
        for candidate in ('_time', 'timestamp', 'time'):
            if candidate in df_local.columns:
                time_col = candidate
                break
        if time_col is None:
            time_col = df_local.columns[0]

        # 检测数值列
        value_col = None
        for candidate in ('value', '_value', 'reading'):
            if candidate in df_local.columns:
                value_col = candidate
                break
        if value_col is None:
            value_col = df_local.columns[-1]

        normalized = df_local[[time_col, value_col]].copy()
        normalized.columns = ['_time', str(uid)]
        frames.append(normalized)

    if not frames:
        raise ValueError("无法从输入数据中提取任何测点")

    merged = frames[0]
    for frame in frames[1:]:
        merged = pd.merge(merged, frame, on='_time', how='outer')

    merged.sort_values('_time', inplace=True)
    merged.ffill(inplace=True)
    merged.reset_index(drop=True, inplace=True)
    return merged


def _standardize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """统一 DataFrame 的列名格式并复制一份安全副本"""
    standardized = df.copy()
    standardized.columns = [str(col) for col in standardized.columns]
    return standardized


def _normalize_input_data(data: Union[pd.DataFrame, Dict[str, pd.DataFrame]], label: str) -> pd.DataFrame:
    """
    将输入规范化为 DataFrame。
    支持两种输入：
        1. 直接的 DataFrame
        2. {uid: DataFrame} 的字典结构（与 DataCenterDataReader 对齐）
    """
    if isinstance(data, pd.DataFrame):
        normalized = _standardize_dataframe(data)
    elif _is_timeseries_mapping(data):
        normalized = _standardize_dataframe(_merge_timeseries_dict_to_dataframe(data))
    else:
        raise TypeError(f"{label} 必须是 pandas.DataFrame 或 {{uid: DataFrame}} 的字典结构")

    if normalized.empty:
        raise ValueError(f"{label} 不能为空")
    return normalized


TEMPERATURE_SETTING_CANDIDATES = ['温度设定值', '温度设定点', '回风温度设定点（℃）', '送风温度设置点']
HUMIDITY_SETTING_CANDIDATES = ['湿度设置点', '湿度设定点', '回风湿度设定点（%）']
RETURN_TEMP_CANDIDATES = ['回风温度测量值（℃）', '回风温度测量值', '回风温度']
RETURN_HUMIDITY_CANDIDATES = ['回风湿度测量值（%）', '回风湿度测量值', '回风湿度']
POWER_READING_CANDIDATES = ['有功功率', '功耗', '监控功率', '有功电度']


# 定义优化模块的三种状态
class OptimizationState(Enum):
    IDLE = "idle"
    RUNNING = "running"
    RESETTING = "resetting"


# 定义数据记录类
@dataclass
class DataRecord:
    device_uid: str
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
                 is_reference: bool = False,
                 target_uid: Optional[str] = None,
                 device_config: Optional[Dict] = None):
        self.uid_config = uid_config
        self.logger = logger
        self.is_reference = is_reference

        if 'air_conditioners' not in self.uid_config:
            raise ValueError("UID配置格式不正确，缺少 'air_conditioners' 字段")

        self.state_lock = threading.Lock()
        self.params_lock = threading.Lock()

        self.air_conditioner_uids, self.air_conditioner_names = _get_air_conditioner_uids_and_names(self.uid_config)
        if not self.air_conditioner_uids:
            raise ValueError("空调UID列表为空")

        self.ac_uid = str(target_uid or self.air_conditioner_uids[0])
        if self.ac_uid not in self.air_conditioner_uids:
            raise ValueError(f"目标空调UID {self.ac_uid} 不在配置列表中")

        self.ac_index = self.air_conditioner_uids.index(self.ac_uid)
        air_conditioner_items = list(self.uid_config['air_conditioners'].items())
        config_key, config_value = air_conditioner_items[self.ac_index]
        self.ac_config = device_config or config_value
        self.ac_name = self.ac_config.get('device_name', config_key)

        self.logger.info(f"初始化空调控制器: {self.ac_name} (UID: {self.ac_uid})")

        self.setting_temperature_uid = self._require_device_point(TEMPERATURE_SETTING_CANDIDATES, "温度设定测点")
        self.setting_humidity_uid = self._require_device_point(HUMIDITY_SETTING_CANDIDATES, "湿度设定测点")
        self.return_temp_uid = self._get_device_point_uid(RETURN_TEMP_CANDIDATES)
        self.return_humidity_uid = self._get_device_point_uid(RETURN_HUMIDITY_CANDIDATES)
        self.device_power_uid = self._get_device_point_uid(POWER_READING_CANDIDATES)

        sensors = self.uid_config.get('sensors', {})
        if 'temperature_sensor_uid' not in sensors or 'humidity_sensor_uid' not in sensors:
            raise ValueError("配置文件中缺少温湿度传感器UID配置 (sensors.temperature_sensor_uid / sensors.humidity_sensor_uid)")

        self.temperature_sensor_uids = [str(uid) for uid in sensors['temperature_sensor_uid']]
        self.humidity_sensor_uids = [str(uid) for uid in sensors['humidity_sensor_uid']]
        self.power_sensor_uids = [str(uid) for uid in sensors.get('energy_consumption_uid', [])]
        self.power_meter_index = (self.ac_index % len(self.power_sensor_uids)) if self.power_sensor_uids else None

        self.state = OptimizationState.IDLE
        self.result_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.stabilization_time = 1 if is_reference else 300
        self.historical_data: List[DataRecord] = []
        self.max_historical_records = 1000
        self.previous_best_params = None
        self.active_thread: Optional[threading.Thread] = None

    def _get_device_point_uid(self, candidates: List[str]) -> Optional[str]:
        measurement_points = self.ac_config.get('measurement_points', {})
        for name in candidates:
            if name in measurement_points:
                return str(measurement_points[name])
        return None

    def _require_device_point(self, candidates: List[str], description: str) -> str:
        uid = self._get_device_point_uid(candidates)
        if uid is None:
            raise ValueError(f"{self.ac_name} 缺少必要测点: {description}")
        return uid

    def _prepare_dataframe(self, data: Union[pd.DataFrame, Dict[str, pd.DataFrame]], label: str) -> pd.DataFrame:
        return _normalize_input_data(data, label)

    def _safe_row_value(self, row: pd.Series, column: Optional[str], default: Optional[float] = None) -> Optional[float]:
        if column is None or column not in row.index:
            return default
        value = row[column]
        if pd.isna(value):
            return default
        return float(value)

    def _mean_from_row(self, row: pd.Series, columns: List[str]) -> Optional[float]:
        values = [float(row[col]) for col in columns if col in row.index and not pd.isna(row[col])]
        if not values:
            return None
        return sum(values) / len(values)

    def _extract_power_value(self, row: pd.Series, power_cols: List[str]) -> Optional[float]:
        if self.device_power_uid and self.device_power_uid in row.index and not pd.isna(row[self.device_power_uid]):
            return float(row[self.device_power_uid])

        if self.power_meter_index is None or not power_cols:
            return None

        if self.power_meter_index < len(power_cols):
            column = power_cols[self.power_meter_index]
            if column in row.index and not pd.isna(row[column]):
                return float(row[column])
        return None

    @staticmethod
    def _wrap_optional(value: Optional[float]) -> List[float]:
        return [value] if value is not None else []

    def _filter_existing(self, frame: pd.DataFrame, columns: List[str]) -> List[str]:
        return [col for col in columns if col in frame.columns]

    def _resolve_sensor_columns(self, frame: pd.DataFrame) -> Dict[str, List[str]]:
        return {
            'temp': self._filter_existing(frame, self.temperature_sensor_uids),
            'humidity': self._filter_existing(frame, self.humidity_sensor_uids),
            'power': self._filter_existing(frame, self.power_sensor_uids),
        }

    @staticmethod
    def _coerce_timestamp(value: Any) -> float:
        if hasattr(value, "timestamp"):
            return float(value.timestamp())
        try:
            return float(value)
        except (TypeError, ValueError):
            return time.time()

    def _append_history(self, record: DataRecord) -> None:
        self.historical_data.append(record)
        if len(self.historical_data) > self.max_historical_records:
            self.historical_data.pop(0)

    def add_historical_data(self, data: Union[pd.DataFrame, Dict[str, pd.DataFrame]]) -> None:
        """添加历史数据，支持 DataFrame 或 {uid: DataFrame} 输入"""
        try:
            frame = self._prepare_dataframe(data, "historical_data")
            columns = self._resolve_sensor_columns(frame)

            required = [self.setting_temperature_uid, self.setting_humidity_uid]
            missing = [col for col in required if col not in frame.columns]
            if missing:
                raise ValueError(f"历史数据缺少必要列: {missing}")

            self.historical_data.clear()

            for _, row in frame.iterrows():
                set_temp_value = row[self.setting_temperature_uid]
                set_humidity_value = row[self.setting_humidity_uid]
                if pd.isna(set_temp_value) or pd.isna(set_humidity_value):
                    continue

                avg_temp = self._mean_from_row(row, columns['temp'])
                avg_humidity = self._mean_from_row(row, columns['humidity'])
                final_temp = self._safe_row_value(row, self.return_temp_uid, avg_temp)
                final_humidity = self._safe_row_value(row, self.return_humidity_uid, avg_humidity)
                power_value = self._extract_power_value(row, columns['power']) or 0.0

                record = DataRecord(
                    device_uid=self.ac_uid,
                    set_temp=int(round(float(set_temp_value))),
                    set_humidity=int(round(float(set_humidity_value))),
                    final_temp=float(final_temp if final_temp is not None else 0.0),
                    final_humidity=float(final_humidity if final_humidity is not None else 0.0),
                    power=float(power_value),
                    timestamp=self._coerce_timestamp(row.get('_time', time.time())),
                    is_optimization_result=False
                )
                self._append_history(record)

            self.logger.info(f"{self.ac_name} 已载入 {len(self.historical_data)} 条历史数据")
        except Exception as e:
            self.logger.error(f"添加历史数据时发生错误: {str(e)}")
            raise

    def get_system_state(self, current_data: Union[pd.DataFrame, Dict[str, pd.DataFrame]]) -> Tuple[list, list, list, list, list, list]:
        """获取当前空调的实时状态"""
        try:
            frame = self._prepare_dataframe(current_data, "current_data")
            row = frame.iloc[-1]
            columns = self._resolve_sensor_columns(frame)

            avg_temp = self._mean_from_row(row, columns['temp'])
            avg_humidity = self._mean_from_row(row, columns['humidity'])
            return_temp_value = self._safe_row_value(row, self.return_temp_uid)
            return_humidity_value = self._safe_row_value(row, self.return_humidity_uid)
            power_value = self._extract_power_value(row, columns['power'])

            return (
                self._wrap_optional(avg_temp),
                self._wrap_optional(return_temp_value),
                self._wrap_optional(power_value),
                [[0]] if power_value is not None else [],
                self._wrap_optional(avg_humidity),
                self._wrap_optional(return_humidity_value)
            )
        except Exception as e:
            self.logger.error(f"获取系统状态时发生错误: {str(e)}")
            raise

    def wait_for_stabilization(self) -> None:
        """等待系统稳定"""
        time.sleep(self.stabilization_time)

    def register_optimization_thread(self, thread: Optional[threading.Thread]) -> None:
        """记录当前优化线程，便于重置时正确等待"""
        with self.state_lock:
            self.active_thread = thread

    def reset(self) -> Optional[Dict]:
        """重置控制器状态并返回上一次的最优参数"""
        self.logger.info("开始重置优化过程...")

        with self.state_lock:
            self.state = OptimizationState.RESETTING
            active_thread = self.active_thread

        self.stop_event.set()

        if active_thread and active_thread.is_alive():
            self.logger.info("等待优化线程结束...")
            active_thread.join(timeout=30)
            if active_thread.is_alive():
                self.logger.warning("优化线程未能在超时时间内结束")

        with self.params_lock:
            previous_params = self.previous_best_params

        self.stop_event.clear()
        with self.state_lock:
            self.state = OptimizationState.IDLE
            self.active_thread = None

        if previous_params:
            self.logger.info(f"重置完成，返回上一个最优状态参数 {previous_params}")
            return previous_params

        self.logger.warning("重置完成，但没有可用的上一个最优状态")
        return None

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
                    self.controller.register_optimization_thread(None)

            self.optimization_thread = threading.Thread(target=optimization_loop, daemon=True)
            self.controller.register_optimization_thread(self.optimization_thread)
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

            uid_to_config = {}
            for idx, (ac_key, ac_info) in enumerate(uid_config['air_conditioners'].items()):
                measurement_points = ac_info.get('measurement_points', {})
                if measurement_points:
                    device_uid = str(next(iter(measurement_points.values())))
                else:
                    device_uid = str(ac_info.get('device_name', ac_key))
                uid_to_config[device_uid] = ac_info

            for uid, name in zip(ac_uids, ac_names):
                controller = ACController(
                    uid_config,
                    logger,
                    is_reference,
                    target_uid=uid,
                    device_config=uid_to_config.get(str(uid))
                )
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


def run_optimization(
        uid_config: dict,
        parameter_config: dict,
        security_boundary_config: dict,
        current_data: Union[pd.DataFrame, Dict[str, pd.DataFrame]],
        logger: logging.Logger,
        historical_data: Optional[Union[pd.DataFrame, Dict[str, pd.DataFrame]]] = None,
        is_reference: bool = False,
        ac_manager: Optional[ACInstanceManager] = None,
        timeout_seconds: Optional[float] = None,
        progress_callback: Optional[callable] = None,
        use_cache: bool = False,
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
        current_data: 当前系统状态数据（pandas.DataFrame 或 {uid: DataFrame}）
        logger: 日志记录器
        historical_data: 历史数据（pandas.DataFrame 或 {uid: DataFrame}，可选）。如果为None，将使用current_data作为历史数据
        is_reference: 是否为参考优化（快速模式，用于测试）
        ac_manager: 空调实例管理器（可选）。如果为None则自动创建新实例
        timeout_seconds: 优化超时时间（秒）。如果为None则使用默认值（600秒）
        progress_callback: 进度回调函数，签名为 callback(ac_index, ac_total, ac_name, status)
        use_cache: 是否使用优化结果缓存（暂未实现）
        initial_params: 初始参数字典（可选），格式为 {'set_temp': int, 'set_humidity': int}

    Returns:
        dict: 优化后的参数字典，包含以下键：
            - 'air_conditioner_setting_temperature': List[int] - 每台空调的温度设定值
            - 'air_conditioner_setting_humidity': List[int] - 每台空调的湿度设定值
            - 'air_conditioner_cooling_mode': List[int] - 每台空调的制冷模式
            - 'optimization_metadata': Dict - 优化元数据（可选）

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

    # 基本验证与数据规范化
    if current_data is None:
        raise ValueError("current_data 不能为空")

    current_data = _normalize_input_data(current_data, "current_data")

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
    else:
        historical_data = _normalize_input_data(historical_data, "historical_data")

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

        # 添加优化元数据
        best_params['optimization_metadata'] = {
            'timestamp': time.time(),
            'is_reference': is_reference,
            'ac_count': len(best_params['air_conditioner_setting_temperature']),
            'success': True
        }

        logger.info("="*60)
        logger.info("优化流程完成")
        logger.info(f"优化了 {len(best_params['air_conditioner_setting_temperature'])} 台空调")
        logger.info("="*60)

        return best_params

    except Exception as e:
        logger.error(f"优化流程失败: {str(e)}")
        raise RuntimeError(f"优化流程执行失败: {str(e)}") from e


def start_optimization_process(
        uid_config: dict,
        parameter_config: dict,
        security_boundary_config: dict,
        optimization_input: Union[pd.DataFrame, Dict[str, pd.DataFrame]],
        current_data: Union[pd.DataFrame, Dict[str, pd.DataFrame]],
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
        optimization_input: 历史数据（pandas.DataFrame 或 {uid: DataFrame}，必须提供）
        current_data: 当前系统状态数据（pandas.DataFrame 或 {uid: DataFrame}，必须提供）
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
    optimization_input = _normalize_input_data(optimization_input, "optimization_input")
    current_data = _normalize_input_data(current_data, "current_data")

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
