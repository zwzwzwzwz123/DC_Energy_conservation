"""
数据中心数据读写器模块

本模块负责从 InfluxDB 读取数据和向 InfluxDB 写入数据。

主要功能：
1. DataCenterDataReader: 根据配置从 InfluxDB 批量读取遥测数据
2. DataCenterDataWriter: 批量写入预测数据和优化控制指令到 InfluxDB

"""

import logging
import yaml
import time
import pandas as pd
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta

from modules.architecture_module import DataCenter, ComputerRoom, Device, Attribute
from utils.influxdb_wrapper import InfluxDBClientWrapper
from utils.critical_operation import critical_operation


class DataCenterDataReader:
    """
    数据中心数据读取器

    功能：
        - 根据 influxdb_read_write_config.yaml 从 InfluxDB 批量读取数据
        - 支持 time_range 和 last_n_points 两种读取模式
        - 支持为不同属性指定不同的 field_key
        - 实现批量查询优化

    属性:
        datacenter: DataCenter 对象
        read_config: 读取配置字典
        influxdb_client: InfluxDB 客户端包装器
        default_mode: 默认读取模式
        default_field_key: 默认 field_key

    方法:
        read_all_observable_data: 读取所有遥测数据
        read_room_data: 读取指定机房的所有数据
        read_device_data: 读取指定设备的所有数据
    """

    def __init__(
            self,
            datacenter: DataCenter,
            read_config: Dict,
            influxdb_client: InfluxDBClientWrapper,
            logger: logging.Logger
    ):
        """
        初始化数据读取器

        参数:
            datacenter: DataCenter 对象
            read_config: 读取配置字典（来自 influxdb_read_write_config.yaml 的 read 部分）
            influxdb_client: InfluxDB 客户端包装器
            logger: 日志器（从调用方传入，通常是 loggers["influxdb"]）
        """
        self.datacenter = datacenter
        self.read_config = read_config
        self.influxdb_client = influxdb_client
        self.logger = logger

        # 获取默认配置
        default_config = read_config.get('default', {})
        self.default_mode = default_config.get('mode', 'time_range')
        self.default_field_key = default_config.get('default_field_key', 'value')
        self.default_time_range = default_config.get('time_range', {'duration': 1, 'unit': 'h'})
        self.default_last_n = default_config.get('last_n_points', {'count': 100})
        self.default_time_order = default_config.get('time_order', 'desc').lower()  # 默认降序（时间最新的放在最上面）

        # 查询优化配置
        query_opt = read_config.get('query_optimization', {})
        self.enable_parallel_query = query_opt.get('enable_parallel_query', True)
        self.max_uids_per_query = query_opt.get('max_uids_per_query', 100)
        self.query_timeout = query_opt.get('query_timeout', 30)

        self.logger.info(f"数据读取器初始化完成 - 数据中心: {datacenter.dc_name}")
        self.logger.info(f"  默认读取模式: {self.default_mode}")
        self.logger.info(f"  默认 field_key: {self.default_field_key}")
        self.logger.info(
            f"  时间排序方式: {self.default_time_order} ({'升序' if self.default_time_order == 'asc' else '降序'})")

    def read_all_observable_data(self) -> Dict[str, pd.DataFrame]:
        """
        读取所有遥测数据

        返回:
            Dict[str, pd.DataFrame]: uid -> DataFrame 的映射
                DataFrame 包含列: timestamp, value

        异常:
            Exception: 查询失败
        """
        self.logger.info("开始读取所有可观测数据...")

        # 获取所有遥测属性的 uid 列表
        all_uids = self.datacenter.get_all_observable_uids(include_unavailable=False)
        self.logger.info(f"共有 {len(all_uids)} 个遥测点需要读取")

        if not all_uids:
            self.logger.warning("没有遥测点需要读取")
            return {}

        # 批量读取数据
        result = self._batch_read_data(all_uids)

        self.logger.info(f"成功读取 {len(result)} 个遥测点的数据")
        return result

    def read_room_data(self, room_uid: str) -> Dict[str, pd.DataFrame]:
        """
        读取指定机房的所有数据

        参数:
            room_uid: 机房唯一标识符

        返回:
            Dict[str, pd.DataFrame]: uid -> DataFrame 的映射

        异常:
            ValueError: 机房不存在
        """
        room = self.datacenter.get_room_by_uid(room_uid)
        if not room:
            raise ValueError(f"机房不存在: {room_uid}")

        # 检查机房是否可用
        if not room.is_available:
            self.logger.warning(f"机房 {room.room_name} 不可用，跳过数据读取")
            return {}

        self.logger.info(f"开始读取机房数据: {room.room_name} (UID: {room_uid})")

        # 获取机房的所有遥测 uid
        room_uids = room.get_all_observable_uids()
        self.logger.info(f"机房 {room.room_name} 共有 {len(room_uids)} 个遥测点")

        if not room_uids:
            self.logger.warning(f"机房 {room.room_name} 没有遥测点")
            return {}

        # 批量读取数据
        result = self._batch_read_data(room_uids)

        self.logger.info(f"成功读取机房 {room.room_name} 的 {len(result)} 个遥测点数据")
        return result

    def read_device_data(self, device_uid: str) -> Dict[str, pd.DataFrame]:
        """
        读取指定设备的所有数据

        参数:
            device_uid: 设备唯一标识符

        返回:
            Dict[str, pd.DataFrame]: uid -> DataFrame 的映射

        异常:
            ValueError: 设备不存在
        """
        device = self.datacenter.get_device_by_uid(device_uid)
        if not device:
            raise ValueError(f"设备不存在: {device_uid}")

        # 检查设备是否可用
        if not device.is_available:
            self.logger.warning(f"设备 {device.device_name} 不可用，跳过数据读取")
            return {}

        self.logger.info(f"开始读取设备数据: {device.device_name} (UID: {device_uid})")

        # 获取设备的所有遥测 uid
        device_uids = device.get_observable_uids()
        self.logger.info(f"设备 {device.device_name} 共有 {len(device_uids)} 个遥测点")

        if not device_uids:
            self.logger.warning(f"设备 {device.device_name} 没有遥测点")
            return {}

        # 批量读取数据
        result = self._batch_read_data(device_uids)

        self.logger.info(f"成功读取设备 {device.device_name} 的 {len(result)} 个遥测点数据")
        return result

    def _batch_read_data(self, uids: List[str]) -> Dict[str, pd.DataFrame]:
        """
        批量读取数据（内部方法）

        参数:
            uids: uid 列表

        返回:
            Dict[str, pd.DataFrame]: uid -> DataFrame 的映射
        """
        result = {}

        # 如果 uid 数量超过阈值，分批查询
        if len(uids) > self.max_uids_per_query:
            self.logger.info(f"uid 数量 ({len(uids)}) 超过阈值 ({self.max_uids_per_query})，开启分批查询")

            # 分批
            batches = [
                uids[i:i + self.max_uids_per_query]
                for i in range(0, len(uids), self.max_uids_per_query)
            ]

            for i, batch in enumerate(batches):
                self.logger.debug(f"查询批次 {i + 1}/{len(batches)}，包含 {len(batch)} 个 uid")
                batch_result = self._read_batch(batch)
                result.update(batch_result)
        else:
            # 一次性查询
            result = self._read_batch(uids)

        return result

    def _read_batch(self, uids: List[str]) -> Dict[str, pd.DataFrame]:
        """
        读取一批 uid 的数据（内部方法）

        参数:
            uids: uid 列表

        返回:
            Dict[str, pd.DataFrame]: uid -> DataFrame 的映射
        """
        result = {}

        for uid in uids:
            try:
                # 构建查询语句
                query = self._build_query(uid)

                # 执行查询
                query_result = self.influxdb_client.query(query)

                # 解析查询结果
                df = self._parse_query_result(query_result, uid)

                if df is not None and not df.empty:
                    result[uid] = df
                else:
                    self.logger.debug(f"uid {uid} 没有数据")

            except Exception as e:
                self.logger.warning(f"读取 uid {uid} 失败: {e}")

        return result

    def _build_query(self, uid: str) -> str:
        """
        根据配置构建 InfluxDB 查询语句

        参数:
            uid: 属性唯一标识符

        返回:
            str: InfluxDB 查询语句
        """
        # 获取 field_key（默认为 "value"）
        field_key = self.default_field_key

        # 根据模式构建查询
        if self.default_mode == 'time_range':
            # time_range 模式
            duration = self.default_time_range.get('duration', 1)
            unit = self.default_time_range.get('unit', 'h')

            # 构建时间范围字符串
            time_range_str = f"{duration}{unit}"

            query = f"""
                SELECT "{field_key}" AS value
                FROM "{uid}"
                WHERE time > now() - {time_range_str}
                ORDER BY time ASC
            """

        elif self.default_mode == 'last_n_points':
            # last_n_points 模式
            count = self.default_last_n.get('count', 100)

            query = f"""
                SELECT "{field_key}" AS value
                FROM "{uid}"
                ORDER BY time DESC
                LIMIT {count}
            """

        else:
            # 默认使用 time_range 模式
            self.logger.warning(f"未知的读取模式: {self.default_mode}/未设定读取模式，使用默认 time_range 模式")
            query = f"""
                SELECT "{field_key}" AS value
                FROM "{uid}"
                WHERE time > now() - 1h
                ORDER BY time ASC
            """

        return query.strip()

    def _parse_query_result(self, query_result: Any, uid: str) -> Optional[pd.DataFrame]:
        """
        解析查询结果并转换为 DataFrame

        参数:
            query_result: InfluxDB 查询结果
            uid: 属性唯一标识符

        返回:
            Optional[pd.DataFrame]: DataFrame 或 None（如果没有数据）
                DataFrame 包含列: timestamp, value
        """
        try:
            # InfluxDB 查询结果是一个 ResultSet 对象
            # 需要转换为 DataFrame
            if not query_result:
                return None

            # 获取第一个结果集
            points = list(query_result.get_points(measurement=uid))

            if not points:
                return None

            # 转换为 DataFrame
            df = pd.DataFrame(points)

            # 确保包含 time 和 value 列
            if 'time' not in df.columns or 'value' not in df.columns:
                self.logger.warning(f"查询结果缺少必要的列: {df.columns.tolist()}")
                return None

            # 重命名列
            df = df.rename(columns={'time': 'timestamp'})

            # 转换时间戳为 datetime
            df['timestamp'] = pd.to_datetime(df['timestamp'])

            # 只保留 timestamp 和 value 列
            df = df[['timestamp', 'value']]

            # 按时间排序（根据配置的排序方式）
            ascending = (self.default_time_order == 'asc')
            df = df.sort_values('timestamp', ascending=ascending).reset_index(drop=True)

            return df

        except Exception as e:
            self.logger.error(f"解析查询结果失败 (uid: {uid}): {e}")
            return None


class DataCenterDataWriter:
    """
    数据中心数据写入器

    功能：
        - 批量写入预测数据到 InfluxDB
        - 批量写入优化控制指令到 InfluxDB
        - 实现批量写入和重试机制
        - 使用 critical_operation 保护写入操作（线程安全）

    属性:
        datacenter: DataCenter 对象
        write_config: 写入配置字典
        influxdb_client: InfluxDB 客户端包装器
        ctx: AppContext 对象（用于 critical_operation）
        prediction_config: 预测数据写入配置
        optimization_config: 优化控制指令写入配置

    方法:
        write_prediction_data: 写入预测数据
        write_optimization_commands: 写入优化控制指令
    """

    def __init__(
            self,
            datacenter: DataCenter,
            write_config: Dict,
            influxdb_client: InfluxDBClientWrapper,
            ctx: Any,  # AppContext 对象
            logger: logging.Logger
    ):
        """
        初始化数据写入器

        参数:
            datacenter: DataCenter 对象
            write_config: 写入配置字典（来自 influxdb_read_write_config.yaml 的 write 部分）
            influxdb_client: InfluxDB 客户端包装器
            ctx: AppContext 对象（用于 critical_operation）
            logger: 日志器（从调用方传入，通常是 loggers["influxdb"]）
        """
        self.datacenter = datacenter
        self.write_config = write_config
        self.influxdb_client = influxdb_client
        self.ctx = ctx
        self.logger = logger

        # 解析预测数据写入配置
        self.prediction_config = write_config.get('prediction', {})
        self.prediction_enabled = self.prediction_config.get('enabled', True)
        self.prediction_database = self.prediction_config.get('database', 'iot_origin_prediction')
        self.prediction_batch_size = self.prediction_config.get('batch_size', 100)
        self.prediction_retry_times = self.prediction_config.get('retry_times', 3)
        self.prediction_retry_interval = self.prediction_config.get('retry_interval', 2)
        self.prediction_retention_policy = self.prediction_config.get('retention_policy', 'autogen')

        # 解析优化控制指令写入配置
        self.optimization_config = write_config.get('optimization', {})
        self.optimization_enabled = self.optimization_config.get('enabled', True)
        self.optimization_database = self.optimization_config.get('database', 'iot_origin_optimization')
        self.optimization_batch_size = self.optimization_config.get('batch_size', 50)
        self.optimization_retry_times = self.optimization_config.get('retry_times', 3)
        self.optimization_retry_interval = self.optimization_config.get('retry_interval', 2)
        self.optimization_retention_policy = self.optimization_config.get('retention_policy', 'autogen')

        self.logger.info(f"数据写入器初始化完成 - 数据中心: {datacenter.dc_name}")
        self.logger.info(f"  预测数据写入: {'启用' if self.prediction_enabled else '禁用'}")
        self.logger.info(f"  预测数据库: {self.prediction_database}")
        self.logger.info(f"  优化控制写入: {'启用' if self.optimization_enabled else '禁用'}")
        self.logger.info(f"  优化数据库: {self.optimization_database}")

    def write_prediction_data(
            self,
            prediction_data: Dict[str, Any],
            data_type: str
    ) -> bool:
        """
        写入预测数据

        参数:
            prediction_data: 预测数据字典
                格式: {
                    'room_uid': 'CR_A1',
                    'horizon': '1h',  # 预测时间范围
                    'predictions': [
                        {'timestamp': datetime, 'value': float},
                        ...
                    ]
                }
            data_type: 数据类型（如 "temperature_prediction", "energy_prediction", "pue_prediction"）

        返回:
            bool: 写入是否成功

        异常:
            ValueError: 预测数据格式错误
        """
        if not self.prediction_enabled:
            self.logger.warning("预测数据写入已禁用")
            return False

        self.logger.info(f"开始写入预测数据 - 类型: {data_type}")

        try:
            # 验证数据格式
            if 'predictions' not in prediction_data:
                raise ValueError("预测数据缺少 'predictions' 字段")

            predictions = prediction_data['predictions']
            if not predictions:
                self.logger.warning("预测数据为空，跳过写入")
                return True

            # 构建 measurement 名称
            # 格式: {room_uid}_temp_pred_{horizon} 或 dc_pue_pred_{horizon}
            if data_type == 'pue_prediction':
                measurement = f"dc_pue_pred_{prediction_data.get('horizon', '1h')}"
            else:
                room_uid = prediction_data.get('room_uid', 'unknown')
                horizon = prediction_data.get('horizon', '1h')

                if data_type == 'temperature_prediction':
                    measurement = f"{room_uid}_temp_pred_{horizon}"
                elif data_type == 'energy_prediction':
                    measurement = f"{room_uid}_energy_pred_{horizon}"
                else:
                    measurement = f"{room_uid}_{data_type}_{horizon}"

            # 构建 Points
            points = []
            for pred in predictions:
                point = self._build_point(
                    measurement=measurement,
                    fields={'value': pred['value']},
                    tags={'data_type': data_type},
                    timestamp=pred['timestamp']
                )
                points.append(point)

            self.logger.info(f"构建了 {len(points)} 个预测数据点")

            # 使用 critical_operation 保护写入操作
            with critical_operation(self.ctx):
                success = self._batch_write(
                    points=points,
                    database=self.prediction_database,
                    batch_size=self.prediction_batch_size,
                    retry_times=self.prediction_retry_times,
                    retry_interval=self.prediction_retry_interval
                )

            if success:
                self.logger.info(f"成功写入 {len(points)} 个预测数据点到 {self.prediction_database}")
            else:
                self.logger.error(f"写入预测数据失败")

            return success

        except Exception as e:
            self.logger.error(f"写入预测数据异常: {e}")
            return False

    def write_optimization_commands(
            self,
            control_commands: Dict[str, Any]
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

        异常:
            ValueError: 控制指令格式错误
        """
        if not self.optimization_enabled:
            self.logger.warning("优化控制指令写入已禁用")
            return False

        self.logger.info("开始写入优化控制指令")

        try:
            # 验证数据格式
            if 'commands' not in control_commands:
                raise ValueError("控制指令缺少 'commands' 字段")

            commands = control_commands['commands']
            if not commands:
                self.logger.warning("控制指令为空，跳过写入")
                return True

            device_uid = control_commands.get('device_uid', 'unknown')

            # 检查设备是否可用
            if device_uid != 'unknown':
                device = self.datacenter.get_device_by_uid(device_uid)
                if device and not device.is_available:
                    self.logger.error(f"设备 {device.device_name} 不可用，拒绝写入控制指令")
                    return False

            # 构建 Points
            points = []
            for cmd in commands:
                # measurement 使用控制属性的 uid
                measurement = cmd['control_uid']

                point = self._build_point(
                    measurement=measurement,
                    fields={'value': cmd['value']},
                    tags={
                        'device_uid': device_uid,
                        'control_type': 'optimization'
                    },
                    timestamp=cmd.get('timestamp', datetime.now())
                )
                points.append(point)

            self.logger.info(f"构建了 {len(points)} 个控制指令点")

            # 使用 critical_operation 保护写入操作
            with critical_operation(self.ctx):
                success = self._batch_write(
                    points=points,
                    database=self.optimization_database,
                    batch_size=self.optimization_batch_size,
                    retry_times=self.optimization_retry_times,
                    retry_interval=self.optimization_retry_interval
                )

            if success:
                self.logger.info(f"成功写入 {len(points)} 个控制指令到 {self.optimization_database}")
            else:
                self.logger.error(f"写入控制指令失败")

            return success

        except Exception as e:
            self.logger.error(f"写入控制指令异常: {e}")
            return False

    def _build_point(
            self,
            measurement: str,
            fields: Dict[str, Any],
            tags: Optional[Dict[str, str]] = None,
            timestamp: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        构建 InfluxDB Point 对象（框架实现）

        参数:
            measurement: measurement 名称
            fields: 字段字典（如 {'value': 25.0}）
            tags: 标签字典（可选）
            timestamp: 时间戳（可选，默认为当前时间）

        返回:
            Dict[str, Any]: Point 字典格式
                {
                    'measurement': str,
                    'tags': dict,
                    'fields': dict,
                    'time': int (纳秒级时间戳)
                }

        注意:
            这是基本框架实现，具体的 Point 构造逻辑后续可以完善
        """
        # 如果没有提供时间戳，使用当前时间
        if timestamp is None:
            timestamp = datetime.now()

        # 转换为纳秒级时间戳
        if isinstance(timestamp, datetime):
            # datetime 转换为纳秒级时间戳
            timestamp_ns = int(timestamp.timestamp() * 1e9)
        else:
            # 假设已经是时间戳（秒级），转换为纳秒级
            timestamp_ns = int(timestamp * 1e9)

        # 构建 Point 字典
        point = {
            'measurement': measurement,
            'tags': tags if tags else {},
            'fields': fields,
            'time': timestamp_ns
        }

        return point

    def _batch_write(
            self,
            points: List[Dict[str, Any]],
            database: str,
            batch_size: int,
            retry_times: int,
            retry_interval: int
    ) -> bool:
        """
        批量写入数据到 InfluxDB

        参数:
            points: Point 列表
            database: 目标数据库
            batch_size: 批量大小
            retry_times: 重试次数
            retry_interval: 重试间隔（秒）

        返回:
            bool: 写入是否成功
        """
        if not points:
            self.logger.warning("没有数据需要写入")
            return True

        self.logger.info(f"开始批量写入 {len(points)} 个数据点到数据库 {database}")

        # 分批写入
        total_batches = (len(points) + batch_size - 1) // batch_size

        for i in range(0, len(points), batch_size):
            batch = points[i:i + batch_size]
            batch_num = i // batch_size + 1

            self.logger.debug(f"写入批次 {batch_num}/{total_batches}，包含 {len(batch)} 个数据点")

            # 调用重试写入
            success = self._retry_write(
                points=batch,
                database=database,
                retry_times=retry_times,
                retry_interval=retry_interval
            )

            if not success:
                self.logger.error(f"批次 {batch_num} 写入失败")
                return False

        self.logger.info(f"成功写入所有 {len(points)} 个数据点")
        return True

    def _retry_write(
            self,
            points: List[Dict[str, Any]],
            database: str,
            retry_times: int,
            retry_interval: int
    ) -> bool:
        """
        写入失败时自动重试

        参数:
            points: Point 列表
            database: 目标数据库
            retry_times: 重试次数
            retry_interval: 重试间隔（秒）

        返回:
            bool: 写入是否成功
        """
        for attempt in range(retry_times + 1):
            try:
                # 执行写入
                self.influxdb_client.write_points(
                    points=points,
                    database=database,
                    time_precision='n',  # 纳秒级精度
                    batch_size=len(points)
                )

                # 写入成功
                if attempt > 0:
                    self.logger.info(f"重试第 {attempt} 次后写入成功")

                return True

            except Exception as e:
                if attempt < retry_times:
                    self.logger.warning(f"写入失败（第 {attempt + 1} 次尝试）: {e}，{retry_interval} 秒后重试...")
                    time.sleep(retry_interval)
                else:
                    self.logger.error(f"写入失败，已达到最大重试次数 ({retry_times}): {e}")
                    return False

        return False


# ==================== 便捷函数 ====================


def create_data_reader(
        datacenter: DataCenter,
        read_write_config: Dict,
        influxdb_client: InfluxDBClientWrapper,
        logger: logging.Logger
) -> DataCenterDataReader:
    """
    创建数据读取器（便捷函数）

    参数:
        datacenter: DataCenter 对象
        read_write_config: InfluxDB 读写配置字典（从 influxdb_read_write_config.yaml 加载）
        influxdb_client: InfluxDB 客户端包装器
        logger: 日志器（从调用方传入，通常是 loggers["influxdb"]）

    返回:
        DataCenterDataReader: 数据读取器对象

    示例:
        reader = create_data_reader(datacenter, influxdb_read_write_config, client, logger)
        data = reader.read_all_observable_data()
    """
    read_config = read_write_config.get('read', {})
    return DataCenterDataReader(datacenter, read_config, influxdb_client, logger)


def create_data_writer(
        datacenter: DataCenter,
        read_write_config: Dict,
        influxdb_client: InfluxDBClientWrapper,
        ctx: Any,
        logger: logging.Logger
) -> DataCenterDataWriter:
    """
    创建数据写入器（便捷函数）

    参数:
        datacenter: DataCenter 对象
        read_write_config: InfluxDB 读写配置字典（从 influxdb_read_write_config.yaml 加载）
        influxdb_client: InfluxDB 客户端包装器
        ctx: AppContext 对象
        logger: 日志器（从调用方传入，通常是 loggers["influxdb"]）

    返回:
        DataCenterDataWriter: 数据写入器对象

    示例:
        writer = create_data_writer(datacenter, influxdb_read_write_config, client, ctx, logger)
        writer.write_prediction_data(prediction_data, "temperature_prediction")
    """
    write_config = read_write_config.get('write', {})
    return DataCenterDataWriter(datacenter, write_config, influxdb_client, ctx, logger)
