"""
数据中心数据读写器模块

本模块负责从 InfluxDB 读取数据和向 InfluxDB 写入数据。

主要功能：
1. DataCenterDataReader: 根据配置从 InfluxDB 批量读取可观测数据
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
        read_all_observable_data: 读取所有可观测点数据
        read_room_data: 读取指定机房的所有数据
        read_device_data: 读取指定设备的所有数据
    """

    def __init__(
            self,
            datacenter: DataCenter,
            read_config: Dict,
            influxdb_clients: Dict[str, InfluxDBClientWrapper],
            logger: logging.Logger
    ):
        """
        初始化数据读取器

        参数:
            datacenter: DataCenter 对象
            read_config: 读取配置字典（来自 influxdb_read_write_config.yaml 的 read 部分）
            influxdb_clients: InfluxDB 客户端字典，键为客户端名称（如 'dc_status_data', 'prediction_data'）
            logger: 日志器（从调用方传入，通常是 loggers["influxdb"]）
        """
        self.datacenter = datacenter
        self.read_config = read_config
        self.influxdb_clients = influxdb_clients
        self.logger = logger

        # 获取默认配置
        default_config = read_config.get('default', {})
        self.default_mode = default_config.get('mode', 'time_range')
        self.default_field_key = default_config.get('default_field_key', 'value')
        self.default_time_range = default_config.get('time_range', {'duration': 1, 'unit': 'h'})
        self.default_last_n = default_config.get('last_n_points', {'count': 100})
        self.default_time_order = default_config.get('time_order', 'desc').lower()  # 默认降序（时间最新的放在最上面）
        self.default_include_unavailable = default_config.get('include_unavailable', False)  # 默认不包含不可用设备

        # 查询优化配置
        query_opt = read_config.get('query_optimization', {})
        self.enable_parallel_query = query_opt.get('enable_parallel_query', True)
        self.parallel_threads = query_opt.get('parallel_threads', 4)  # 新增：并行查询线程数
        self.max_uids_per_query = query_opt.get('max_uids_per_query', 100)

        self.logger.info(f"数据读取器初始化完成 - 数据中心: {datacenter.dc_name}")
        self.logger.info(f"  已注册客户端: {list(influxdb_clients.keys())}")
        self.logger.info(f"  默认读取模式: {self.default_mode}")
        self.logger.info(f"  默认 field_key: {self.default_field_key}")
        self.logger.info(
            f"  时间排序方式: {self.default_time_order} ({'升序' if self.default_time_order == 'asc' else '降序'})")
        self.logger.info(f"  查询优化配置:")
        self.logger.info(f"    并行查询: {'启用' if self.enable_parallel_query else '禁用'}")
        if self.enable_parallel_query:
            self.logger.info(f"    并行线程数: {self.parallel_threads}")
        self.logger.info(f"    单批最大uid数: {self.max_uids_per_query}")

    def read_all_observable_data(
        self,
        client: InfluxDBClientWrapper,
        mode: str,
        time_range: Dict[str, Any],
        last_n: Dict[str, Any],
        include_unavailable: bool = False
    ) -> Dict[str, pd.DataFrame]:
        """
        读取所有可观测点数据

        参数:
            client: InfluxDB 客户端
            mode: 读取模式（'time_range' 或 'last_n_points'）
            time_range: 时间范围配置（用于 time_range 模式）
            last_n: 最近数据点数配置（用于 last_n_points 模式）
            include_unavailable: 是否包含不可用设备/机房的数据，默认 False（只返回可用设备的属性）

        返回:
            Dict[str, pd.DataFrame]: uid -> DataFrame 的映射
                DataFrame 包含列: timestamp, value

        异常:
            Exception: 查询失败
        """
        self.logger.info("开始读取所有可观测数据...")

        # 获取所有可观测属性的 uid 列表
        all_uids = self.datacenter.get_all_observable_uids(include_unavailable=include_unavailable)
        self.logger.info(f"共有 {len(all_uids)} 个可观测点需要读取 (include_unavailable={include_unavailable})")

        if not all_uids:
            self.logger.warning("没有可观测点需要读取")
            return {}

        # 批量读取数据（将客户端和配置作为参数传递）
        result = self._batch_read_data(all_uids, client, mode, time_range, last_n)

        self.logger.info(f"成功读取 {len(result)} 个可观测点的数据")
        return result

    def read_room_data(
        self,
        room_uid: str,
        client: InfluxDBClientWrapper,
        mode: str,
        time_range: Dict[str, Any],
        last_n: Dict[str, Any],
        include_unavailable: bool = False
    ) -> Dict[str, pd.DataFrame]:
        """
        读取指定机房的所有数据

        参数:
            room_uid: 机房唯一标识符
            client: InfluxDB 客户端
            mode: 读取模式（'time_range' 或 'last_n_points'）
            time_range: 时间范围配置（用于 time_range 模式）
            last_n: 最近数据点数配置（用于 last_n_points 模式）
            include_unavailable: 是否包含不可用设备的数据，默认 False（只返回可用设备的属性）

        返回:
            Dict[str, pd.DataFrame]: uid -> DataFrame 的映射

        异常:
            ValueError: 机房不存在
        """
        room = self.datacenter.get_room_by_uid(room_uid)
        if not room:
            raise ValueError(f"机房不存在: {room_uid}")

        # 检查机房是否可用（如果不包含不可用机房）
        if not include_unavailable and not room.is_available:
            self.logger.warning(f"机房 {room.room_name} 不可用，跳过数据读取")
            return {}

        self.logger.info(f"开始读取机房数据: {room.room_name} (UID: {room_uid})")

        # 获取机房的所有可观测 uid
        room_uids = room.get_all_observable_uids(include_unavailable=include_unavailable)
        self.logger.info(f"机房 {room.room_name} 共有 {len(room_uids)} 个可观测点 (include_unavailable={include_unavailable})")

        if not room_uids:
            self.logger.warning(f"机房 {room.room_name} 没有可观测点")
            return {}

        # 批量读取数据（将客户端和配置作为参数传递）
        result = self._batch_read_data(room_uids, client, mode, time_range, last_n)

        self.logger.info(f"成功读取机房 {room.room_name} 的 {len(result)} 个可观测点数据")
        return result

    def read_device_data(
        self,
        device_uid: str,
        client: InfluxDBClientWrapper,
        mode: str,
        time_range: Dict[str, Any],
        last_n: Dict[str, Any],
        include_unavailable: bool = False
    ) -> Dict[str, pd.DataFrame]:
        """
        读取指定设备的所有数据

        参数:
            device_uid: 设备唯一标识符
            client: InfluxDB 客户端
            mode: 读取模式（'time_range' 或 'last_n_points'）
            time_range: 时间范围配置（用于 time_range 模式）
            last_n: 最近数据点数配置（用于 last_n_points 模式）
            include_unavailable: 是否读取不可用设备的数据，默认 False（不读取不可用设备）

        返回:
            Dict[str, pd.DataFrame]: uid -> DataFrame 的映射

        异常:
            ValueError: 设备不存在
        """
        device = self.datacenter.get_device_by_uid(device_uid)
        if not device:
            raise ValueError(f"设备不存在: {device_uid}")

        # 检查设备是否可用（如果不包含不可用设备）
        if not include_unavailable and not device.is_available:
            self.logger.warning(f"设备 {device.device_name} 不可用，跳过数据读取")
            return {}

        self.logger.info(f"开始读取设备数据: {device.device_name} (UID: {device_uid})")

        # 获取设备的所有可观测 uid
        device_uids = device.get_observable_uids()
        self.logger.info(f"设备 {device.device_name} 共有 {len(device_uids)} 个可观测点 (include_unavailable={include_unavailable})")

        if not device_uids:
            self.logger.warning(f"设备 {device.device_name} 没有可观测点")
            return {}

        # 批量读取数据（将客户端和配置作为参数传递）
        result = self._batch_read_data(device_uids, client, mode, time_range, last_n)

        self.logger.info(f"成功读取设备 {device.device_name} 的 {len(result)} 个可观测点数据")
        return result

    def read_specific_uids(
        self,
        uids: List[str],
        client: InfluxDBClientWrapper,
        mode: str,
        time_range: Dict[str, Any],
        last_n: Dict[str, Any]
    ) -> Dict[str, pd.DataFrame]:
        """
        读取指定 UID 列表的数据

        参数:
            uids: UID 列表
            client: InfluxDB 客户端
            mode: 读取模式（'time_range' 或 'last_n_points'）
            time_range: 时间范围配置（用于 time_range 模式）
            last_n: 最近数据点数配置（用于 last_n_points 模式）

        返回:
            Dict[str, pd.DataFrame]: uid -> DataFrame 的映射

        异常:
            ValueError: UID 列表为空
        """
        if not uids:
            raise ValueError("UID 列表不能为空")

        self.logger.info(f"开始读取指定的 {len(uids)} 个 UID 的数据")

        # 批量读取数据（将客户端和配置作为参数传递）
        result = self._batch_read_data(uids, client, mode, time_range, last_n)

        self.logger.info(f"成功读取 {len(result)} 个 UID 的数据")
        return result

    def read_influxdb_data(self, client_key: str, config_key: str) -> Dict[str, pd.DataFrame]:
        """
        根据客户端键和配置键从 InfluxDB 读取数据（统一数据读取接口）

        参数:
            client_key: 客户端键名（如 'dc_status_data_client', 'prediction_data_client'）
            config_key: 配置文件中该客户端下的配置键名
                       例如: "datacenter_latest_status", "latest_predictions"

        返回:
            Dict[str, pd.DataFrame]: uid -> DataFrame 的映射

        异常:
            ValueError: 客户端不存在、配置不存在或配置无效
        """
        self.logger.info(f"开始根据客户端 '{client_key}' 和配置键 '{config_key}' 读取数据")

        # 1. 验证客户端是否存在
        if client_key not in self.influxdb_clients:
            raise ValueError(f"客户端 '{client_key}' 不存在，可用客户端: {list(self.influxdb_clients.keys())}")

        # 2. 获取该客户端的配置
        if client_key not in self.read_config:
            raise ValueError(f"客户端 '{client_key}' 没有对应的读取配置")

        client_config = self.read_config[client_key]

        # 3. 读取配置项
        if config_key not in client_config:
            raise ValueError(f"配置键 '{config_key}' 不存在于客户端 '{client_key}' 的配置中")

        config = client_config[config_key]

        # 4. 验证配置：检查 read_method 是否存在
        if 'read_method' not in config:
            raise ValueError(f"配置键 '{config_key}' 缺少必填字段 'read_method'")

        read_method = config['read_method']
        valid_methods = ['read_all_observable_data', 'read_room_data', 'read_device_data', 'read_specific_uids']

        if read_method not in valid_methods:
            raise ValueError(
                f"配置键 '{config_key}' 的 read_method '{read_method}' 无效，"
                f"有效值为: {valid_methods}"
            )

        self.logger.info(f"  客户端: {client_key}")
        self.logger.info(f"  读取方法: {read_method}")

        # 5. 解析参数（优先使用配置项中的值,否则使用默认值）
        include_unavailable = config.get('include_unavailable', self.default_include_unavailable)
        room_uids = config.get('room_uids', [])
        device_uids = config.get('device_uids', [])
        specific_uids = config.get('specific_uids', [])

        # 6. 获取客户端（不再使用实例属性 _current_client，直接从字典获取）
        client = self.influxdb_clients[client_key]

        # 7. 解析配置参数（不再修改实例属性，而是作为局部变量）
        # 优先级：配置项 > 客户端默认配置 > 全局默认配置
        mode = self.default_mode
        time_range = self.default_time_range
        last_n = self.default_last_n

        # 如果客户端配置中有 default 配置，先应用客户端级别的默认配置
        if 'default' in client_config and isinstance(client_config['default'], dict):
            client_default = client_config['default']
            if 'mode' in client_default:
                mode = client_default['mode']
            if 'time_range' in client_default:
                time_range = client_default['time_range']
            if 'last_n_points' in client_default:
                last_n = client_default['last_n_points']

        # 如果配置项中指定了参数，覆盖客户端默认配置
        if 'mode' in config:
            mode = config['mode']
            self.logger.info(f"  使用配置指定的读取模式: {mode}")

        if 'time_range' in config:
            time_range = config['time_range']
            self.logger.info(f"  使用配置指定的时间范围: {time_range}")

        if 'last_n_points' in config:
            last_n = config['last_n_points']
            self.logger.info(f"  使用配置指定的最近数据点数: {last_n}")

        # 8. 路由调用：根据 read_method 调用相应的底层方法（传递配置参数）
        result = {}

        if read_method == 'read_all_observable_data':
            # 调用 read_all_observable_data 方法
            self.logger.info(f"  调用 read_all_observable_data(include_unavailable={include_unavailable})")
            result = self.read_all_observable_data(client, mode, time_range, last_n, include_unavailable)

        elif read_method == 'read_room_data':
            # 调用 read_room_data，遍历 room_uids
            if not room_uids:
                raise ValueError(f"配置键 '{config_key}' 使用 read_room_data 方法时，必须指定 room_uids")

            self.logger.info(f"  读取 {len(room_uids)} 个机房的数据: {room_uids}")

            for room_uid in room_uids:
                try:
                    room_data = self.read_room_data(room_uid, client, mode, time_range, last_n, include_unavailable)
                    result.update(room_data)
                except ValueError as e:
                    self.logger.warning(f"  读取机房 {room_uid} 失败: {e}")

        elif read_method == 'read_device_data':
            # 调用 read_device_data，遍历 device_uids
            if not device_uids:
                raise ValueError(f"配置键 '{config_key}' 使用 read_device_data 方法时，必须指定 device_uids")

            self.logger.info(f"  读取 {len(device_uids)} 个设备的数据: {device_uids}")

            for device_uid in device_uids:
                try:
                    device_data = self.read_device_data(device_uid, client, mode, time_range, last_n, include_unavailable)
                    result.update(device_data)
                except ValueError as e:
                    self.logger.warning(f"  读取设备 {device_uid} 失败: {e}")

        elif read_method == 'read_specific_uids':
            # 调用 read_specific_uids
            if not specific_uids:
                raise ValueError(f"配置键 '{config_key}' 使用 read_specific_uids 方法时，必须指定 specific_uids")

            self.logger.info(f"  读取 {len(specific_uids)} 个指定 UID 的数据")
            result = self.read_specific_uids(specific_uids, client, mode, time_range, last_n)

        self.logger.info(f"成功根据客户端 '{client_key}' 和配置键 '{config_key}' 读取 {len(result)} 个 UID 的数据")
        return result

    def _batch_read_data(
        self,
        uids: List[str],
        client: InfluxDBClientWrapper,
        mode: str,
        time_range: Dict[str, Any],
        last_n: Dict[str, Any]
    ) -> Dict[str, pd.DataFrame]:
        """
        批量读取数据（内部方法）

        参数:
            uids: uid 列表
            client: InfluxDB 客户端（由调用方传入，避免使用实例属性）
            mode: 读取模式（'time_range' 或 'last_n_points'）
            time_range: 时间范围配置（用于 time_range 模式）
            last_n: 最近数据点数配置（用于 last_n_points 模式）

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
                batch_result = self._read_batch(batch, client, mode, time_range, last_n)
                result.update(batch_result)
        else:
            # 一次性查询
            result = self._read_batch(uids, client, mode, time_range, last_n)

        return result

    def _query_single_uid(
        self,
        uid: str,
        client: InfluxDBClientWrapper,
        mode: str,
        time_range: Dict[str, Any],
        last_n: Dict[str, Any]
    ) -> Optional[pd.DataFrame]:
        """
        查询单个 uid 的数据（内部方法，用于并行查询）

        参数:
            uid: 属性唯一标识符
            client: InfluxDB 客户端（由调用方传入，避免使用实例属性，提高线程安全性）
            mode: 读取模式（'time_range' 或 'last_n_points'）
            time_range: 时间范围配置（用于 time_range 模式）
            last_n: 最近数据点数配置（用于 last_n_points 模式）

        返回:
            Optional[pd.DataFrame]: DataFrame 或 None（如果没有数据或查询失败）
        """
        try:
            # 构建查询语句（传递配置参数）
            query = self._build_query(uid, mode, time_range, last_n)

            # 执行查询（直接使用传入的客户端，无需从实例属性获取）
            query_result = client.query(query)

            # 解析查询结果
            df = self._parse_query_result(query_result, uid)

            if df is not None and not df.empty:
                return df
            else:
                self.logger.debug(f"uid {uid} 没有数据")
                return None

        except Exception as e:
            self.logger.warning(f"读取 uid {uid} 失败: {e}")
            return None

    def _read_batch(
        self,
        uids: List[str],
        client: InfluxDBClientWrapper,
        mode: str,
        time_range: Dict[str, Any],
        last_n: Dict[str, Any]
    ) -> Dict[str, pd.DataFrame]:
        """
        读取一批 uid 的数据（内部方法）
        支持并行查询和串行查询两种模式

        参数:
            uids: uid 列表
            client: InfluxDB 客户端（由调用方传入，避免使用实例属性）
            mode: 读取模式（'time_range' 或 'last_n_points'）
            time_range: 时间范围配置（用于 time_range 模式）
            last_n: 最近数据点数配置（用于 last_n_points 模式）

        返回:
            Dict[str, pd.DataFrame]: uid -> DataFrame 的映射
        """
        result = {}

        # 检查是否启用并行查询（且 uid 数量大于 1）
        if self.enable_parallel_query and len(uids) > 1:
            # 并行查询模式
            self.logger.debug(f"使用并行查询模式，线程数: {self.parallel_threads}，查询 {len(uids)} 个 uid")

            from concurrent.futures import ThreadPoolExecutor, as_completed

            with ThreadPoolExecutor(max_workers=self.parallel_threads) as executor:
                # 提交所有查询任务（将 client 和配置参数传递）
                future_to_uid = {
                    executor.submit(self._query_single_uid, uid, client, mode, time_range, last_n): uid
                    for uid in uids
                }

                # 收集查询结果
                for future in as_completed(future_to_uid):
                    uid = future_to_uid[future]
                    try:
                        df = future.result()
                        if df is not None:
                            result[uid] = df
                    except Exception as e:
                        self.logger.warning(f"并行查询 uid {uid} 时发生异常: {e}")

        else:
            # 串行查询模式（原有逻辑）
            if not self.enable_parallel_query:
                self.logger.debug(f"并行查询已禁用，使用串行查询模式")
            else:
                self.logger.debug(f"uid 数量为 {len(uids)}，使用串行查询模式")

            for uid in uids:
                df = self._query_single_uid(uid, client, mode, time_range, last_n)
                if df is not None:
                    result[uid] = df

        return result

    def _build_query(self, uid: str, mode: str, time_range: Dict[str, Any], last_n: Dict[str, Any]) -> str:
        """
        根据配置构建 InfluxDB 查询语句

        参数:
            uid: 属性唯一标识符
            mode: 读取模式（'time_range' 或 'last_n_points'）
            time_range: 时间范围配置（用于 time_range 模式）
            last_n: 最近数据点数配置（用于 last_n_points 模式）

        返回:
            str: InfluxDB 查询语句
        """
        # 获取 field_key（从实例属性读取，这是只读配置，不会被临时修改）
        field_key = self.default_field_key

        # 根据模式构建查询
        if mode == 'time_range':
            # time_range 模式
            duration = time_range.get('duration', 1)
            unit = time_range.get('unit', 'h')

            # 构建时间范围字符串
            time_range_str = f"{duration}{unit}"

            query = f"""
                SELECT "{field_key}" AS value
                FROM "{uid}"
                WHERE time > now() - {time_range_str}
                ORDER BY time ASC
            """

        elif mode == 'last_n_points':
            # last_n_points 模式
            count = last_n.get('count', 100)

            query = f"""
                SELECT "{field_key}" AS value
                FROM "{uid}"
                ORDER BY time DESC
                LIMIT {count}
            """

        else:
            self.logger.warning(f"未知的读取模式: {mode}/未设定读取模式，使用默认 time_range 模式")
            # 默认使用 time_range 模式
            duration = time_range.get('duration', 1)
            unit = time_range.get('unit', 'h')

            # 构建时间范围字符串
            time_range_str = f"{duration}{unit}"

            query = f"""
                SELECT "{field_key}" AS value
                FROM "{uid}"
                WHERE time > now() - {time_range_str}
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
            influxdb_clients: Dict[str, InfluxDBClientWrapper],
            ctx: Any,  # AppContext 对象
            logger: logging.Logger
    ):
        """
        初始化数据写入器

        参数:
            datacenter: DataCenter 对象
            write_config: 写入配置字典（来自 influxdb_read_write_config.yaml 的 write 部分）
            influxdb_clients: InfluxDB 客户端字典，键为客户端名称（如 'prediction_data_client', 'optimization_data_client'）
            ctx: AppContext 对象（用于 critical_operation）
            logger: 日志器（从调用方传入，通常是 loggers["influxdb"]）
        """
        self.datacenter = datacenter
        self.write_config = write_config
        self.influxdb_clients = influxdb_clients
        self.ctx = ctx
        self.logger = logger

        # 解析预测数据写入配置
        self.prediction_config = write_config.get('prediction_data_client', {})
        self.prediction_enabled = self.prediction_config.get('enabled', True)
        self.prediction_batch_size = self.prediction_config.get('batch_size', 100)
        self.prediction_retry_times = self.prediction_config.get('retry_times', 3)
        self.prediction_retry_interval = self.prediction_config.get('retry_interval', 2)
        self.prediction_retention_policy = self.prediction_config.get('retention_policy', 'autogen')

        # 解析优化控制指令写入配置
        self.optimization_config = write_config.get('optimization_data_client', {})
        self.optimization_enabled = self.optimization_config.get('enabled', True)
        self.optimization_batch_size = self.optimization_config.get('batch_size', 50)
        self.optimization_retry_times = self.optimization_config.get('retry_times', 3)
        self.optimization_retry_interval = self.optimization_config.get('retry_interval', 2)
        self.optimization_retention_policy = self.optimization_config.get('retention_policy', 'autogen')

        self.logger.info(f"数据写入器初始化完成 - 数据中心: {datacenter.dc_name}")
        self.logger.info(f"  已注册客户端: {list(influxdb_clients.keys())}")
        self.logger.info(f"  预测数据写入: {'启用' if self.prediction_enabled else '禁用'}")
        self.logger.info(f"  优化控制写入: {'启用' if self.optimization_enabled else '禁用'}")

    def write_influxdb_data(
            self,
            client_key: str,
            config_key: str,
            data: Dict[str, Any]
    ) -> bool:
        """
        统一的数据写入接口

        参数:
            client_key: 客户端键名（'prediction_data_client' 或 'optimization_data_client'）
            config_key: 写入配置的键（用于获取写入参数）
            data: 要写入的数据字典
                对于预测数据，格式为: {
                    'room_uid': 'CR_A1',
                    'horizon': '1h',
                    'data_type': 'temperature_prediction',
                    'predictions': [
                        {'timestamp': datetime, 'value': float},
                        ...
                    ]
                }
                对于优化控制指令，格式为: {
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
            ValueError: 客户端不存在、配置不存在或数据格式错误
        """
        self.logger.info(f"开始写入数据 - 客户端: {client_key}, 配置: {config_key}")

        # 1. 验证客户端是否存在
        if client_key not in self.influxdb_clients:
            raise ValueError(f"客户端 '{client_key}' 不存在，可用客户端: {list(self.influxdb_clients.keys())}")

        # 2. 获取客户端和数据库名称
        client = self.influxdb_clients[client_key]
        database = client.client_config['database']

        # 3. 获取写入配置
        if config_key not in self.write_config:
            raise ValueError(f"写入配置 '{config_key}' 不存在")

        config = self.write_config[config_key]
        enabled = config.get('enabled', True)
        batch_size = config.get('batch_size', 100)
        retry_times = config.get('retry_times', 3)
        retry_interval = config.get('retry_interval', 2)

        if not enabled:
            self.logger.warning(f"写入配置 '{config_key}' 已禁用")
            return False

        try:
            # 4. 根据客户端类型构建数据点
            points = []

            if client_key == 'prediction_data_client':
                # 预测数据写入逻辑
                points = self._build_prediction_points(data)
            elif client_key == 'optimization_data_client':
                # 优化控制指令写入逻辑
                points = self._build_optimization_points(data)
            else:
                raise ValueError(f"不支持的客户端类型: {client_key}")

            if not points:
                self.logger.warning("没有数据点需要写入")
                return True

            self.logger.info(f"构建了 {len(points)} 个数据点")

            # 5. 使用 critical_operation 保护写入操作
            with critical_operation(self.ctx):
                success = self._batch_write(
                    points=points,
                    client=client,
                    database=database,
                    batch_size=batch_size,
                    retry_times=retry_times,
                    retry_interval=retry_interval
                )

            if success:
                self.logger.info(f"成功写入 {len(points)} 个数据点到 {database}")
            else:
                self.logger.error(f"写入数据失败")

            return success

        except Exception as e:
            self.logger.error(f"写入数据异常: {e}", exc_info=True)
            return False

    def _build_prediction_points(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        构建预测数据点（内部方法）

        参数:
            data: 预测数据字典

        返回:
            List[Dict[str, Any]]: 数据点列表

        异常:
            ValueError: 数据格式错误
        """
        # 验证数据格式
        if 'predictions' not in data:
            raise ValueError("预测数据缺少 'predictions' 字段")

        predictions = data['predictions']
        if not predictions:
            self.logger.warning("预测数据为空")
            return []

        data_type = data.get('data_type', 'unknown')

        # 构建 measurement 名称
        if data_type == 'pue_prediction':
            measurement = f"dc_pue_pred_{data.get('horizon', '1h')}"
        else:
            room_uid = data.get('room_uid', 'unknown')
            horizon = data.get('horizon', '1h')

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

        return points

    def _build_optimization_points(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        构建优化控制指令数据点（内部方法）

        参数:
            data: 控制指令字典

        返回:
            List[Dict[str, Any]]: 数据点列表

        异常:
            ValueError: 数据格式错误
        """
        # 验证数据格式
        if 'commands' not in data:
            raise ValueError("控制指令缺少 'commands' 字段")

        commands = data['commands']
        if not commands:
            self.logger.warning("控制指令为空")
            return []

        device_uid = data.get('device_uid', 'unknown')

        # 检查设备是否可用
        if device_uid != 'unknown':
            device = self.datacenter.get_device_by_uid(device_uid)
            if device and not device.is_available:
                raise ValueError(f"设备 {device.device_name} 不可用，拒绝写入控制指令")

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

        return points

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
            timestamp: 时间戳（可选，默认为当前 UTC 时间）

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
        # 如果没有提供时间戳，使用当前 UTC 时间（与 InfluxDB 存储保持一致）
        if timestamp is None:
            from datetime import timezone
            timestamp = datetime.now(timezone.utc)

        # 转换为纳秒级时间戳
        if isinstance(timestamp, datetime):
            # datetime 转换为纳秒级时间戳
            # 对于 aware datetime（有时区信息），timestamp() 会正确转换为 UTC 时间戳
            # 对于 naive datetime（无时区信息），timestamp() 会假设为本地时区
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
            client: InfluxDBClientWrapper,
            database: str,
            batch_size: int,
            retry_times: int,
            retry_interval: int
    ) -> bool:
        """
        批量写入数据到 InfluxDB

        参数:
            points: Point 列表
            client: InfluxDB 客户端包装器
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
                client=client,
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
            client: InfluxDBClientWrapper,
            database: str,
            retry_times: int,
            retry_interval: int
    ) -> bool:
        """
        写入失败时自动重试

        参数:
            points: Point 列表
            client: InfluxDB 客户端包装器
            database: 目标数据库
            retry_times: 重试次数
            retry_interval: 重试间隔（秒）

        返回:
            bool: 写入是否成功
        """
        for attempt in range(retry_times + 1):
            try:
                # 执行写入
                client.write_points(
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
        influxdb_clients: Dict[str, InfluxDBClientWrapper],
        logger: logging.Logger
) -> DataCenterDataReader:
    """
    创建数据读取器（便捷函数）

    参数:
        datacenter: DataCenter 对象
        read_write_config: InfluxDB 读写配置字典（从 influxdb_read_write_config.yaml 加载）
        influxdb_clients: InfluxDB 客户端字典，键为客户端名称（如 'dc_status_data', 'prediction_data'）
        logger: 日志器（从调用方传入，通常是 loggers["influxdb"]）

    返回:
        DataCenterDataReader: 数据读取器对象

    示例:
        reader = create_data_reader(
            datacenter,
            influxdb_read_write_config,
            {'dc_status_data': dc_status_client, 'prediction_data': prediction_client},
            logger
        )
        data = reader.read_influxdb_data('dc_status_data', 'datacenter_latest_status')
    """
    read_config = read_write_config.get('read', {})
    return DataCenterDataReader(datacenter, read_config, influxdb_clients, logger)


def create_data_writer(
        datacenter: DataCenter,
        read_write_config: Dict,
        influxdb_clients: Dict[str, InfluxDBClientWrapper],
        ctx: Any,
        logger: logging.Logger
) -> DataCenterDataWriter:
    """
    创建数据写入器（便捷函数）

    参数:
        datacenter: DataCenter 对象
        read_write_config: InfluxDB 读写配置字典（从 influxdb_read_write_config.yaml 加载）
        influxdb_clients: InfluxDB 客户端字典，键为客户端名称（如 'prediction_data', 'optimization_data'）
        ctx: AppContext 对象
        logger: 日志器（从调用方传入，通常是 loggers["influxdb"]）

    返回:
        DataCenterDataWriter: 数据写入器对象

    示例:
        writer = create_data_writer(
            datacenter,
            influxdb_read_write_config,
            {'prediction_data_client': prediction_client, 'optimization_data_client': optimization_client},
            ctx,
            logger
        )
        writer.write_influxdb_data('prediction_data_client', 'prediction_data_client', prediction_data)
    """
    write_config = read_write_config.get('write', {})
    return DataCenterDataWriter(datacenter, write_config, influxdb_clients, ctx, logger)
