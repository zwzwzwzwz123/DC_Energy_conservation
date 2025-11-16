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
        self.default_last_n_points = default_config.get('last_n_points', {'count': 100})
        self.default_time_order = default_config.get('time_order', 'desc').lower()  # 默认降序（时间最新的放在最上面）
        self.default_include_unavailable = default_config.get('include_unavailable', False)  # 默认不包含不可用设备
        self.default_tag_filters = default_config.get('tag_filters', {})  # 默认 Tag 过滤配置

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
        last_n_points: Dict[str, Any],
        include_unavailable: bool = False,
        tag_filters: Dict[str, Any] = None
    ) -> Dict[str, pd.DataFrame]:
        """
        读取所有可观测点数据

        参数:
            client: InfluxDB 客户端
            mode: 读取模式（'time_range' 或 'last_n_points'）
            time_range: 时间范围配置（用于 time_range 模式）
            last_n_points: 最近数据点数配置（用于 last_n_points 模式）
            include_unavailable: 是否包含不可用设备/机房的数据，默认 False（只返回可用设备的属性）
            tag_filters: Tag Set 过滤配置，默认 None（不过滤）

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
        if tag_filters is None:
            tag_filters = {}
        result = self._batch_read_data(all_uids, client, mode, time_range, last_n_points, tag_filters)

        self.logger.info(f"成功读取 {len(result)} 个可观测点的数据")
        return result

    def read_room_data(
        self,
        room_uid: str,
        client: InfluxDBClientWrapper,
        mode: str,
        time_range: Dict[str, Any],
        last_n_points: Dict[str, Any],
        include_unavailable: bool = False,
        tag_filters: Dict[str, Any] = None
    ) -> Dict[str, pd.DataFrame]:
        """
        读取指定机房的所有数据

        参数:
            room_uid: 机房唯一标识符
            client: InfluxDB 客户端
            mode: 读取模式（'time_range' 或 'last_n_points'）
            time_range: 时间范围配置（用于 time_range 模式）
            last_n_points: 最近数据点数配置（用于 last_n_points 模式）
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
        if tag_filters is None:
            tag_filters = {}
        result = self._batch_read_data(room_uids, client, mode, time_range, last_n_points, tag_filters)

        self.logger.info(f"成功读取机房 {room.room_name} 的 {len(result)} 个可观测点数据")
        return result

    def read_device_data(
        self,
        device_uid: str,
        client: InfluxDBClientWrapper,
        mode: str,
        time_range: Dict[str, Any],
        last_n_points: Dict[str, Any],
        include_unavailable: bool = False,
        tag_filters: Dict[str, Any] = None
    ) -> Dict[str, pd.DataFrame]:
        """
        读取指定设备的所有数据

        参数:
            device_uid: 设备唯一标识符
            client: InfluxDB 客户端
            mode: 读取模式（'time_range' 或 'last_n_points'）
            time_range: 时间范围配置（用于 time_range 模式）
            last_n_points: 最近数据点数配置（用于 last_n_points 模式）
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
        if tag_filters is None:
            tag_filters = {}
        result = self._batch_read_data(device_uids, client, mode, time_range, last_n_points, tag_filters)

        self.logger.info(f"成功读取设备 {device.device_name} 的 {len(result)} 个可观测点数据")
        return result

    def read_specific_uids(
        self,
        uids: List[str],
        client: InfluxDBClientWrapper,
        mode: str,
        time_range: Dict[str, Any],
        last_n_points: Dict[str, Any],
        tag_filters: Dict[str, Any] = None
    ) -> Dict[str, pd.DataFrame]:
        """
        读取指定 UID 列表的数据

        参数:
            uids: UID 列表
            client: InfluxDB 客户端
            mode: 读取模式（'time_range' 或 'last_n_points'）
            time_range: 时间范围配置（用于 time_range 模式）
            last_n_points: 最近数据点数配置（用于 last_n_points 模式）

        返回:
            Dict[str, pd.DataFrame]: uid -> DataFrame 的映射

        异常:
            ValueError: UID 列表为空
        """
        if not uids:
            raise ValueError("UID 列表不能为空")

        self.logger.info(f"开始读取指定的 {len(uids)} 个 UID 的数据")

        # 批量读取数据（将客户端和配置作为参数传递）
        if tag_filters is None:
            tag_filters = {}
        result = self._batch_read_data(uids, client, mode, time_range, last_n_points, tag_filters)

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

        # 1. 获取并解析配置
        try:
            client, config, read_params = self._get_read_config(client_key, config_key)
        except ValueError as e:
            self.logger.error(f"获取读取配置失败: {e}")
            raise

        # 2. 验证 read_method
        read_method = config.get('read_method')
        if not read_method:
            raise ValueError(f"配置键 '{config_key}' 缺少必填字段 'read_method'")

        valid_methods = ['read_all_observable_data', 'read_room_data', 'read_device_data', 'read_specific_uids']
        if read_method not in valid_methods:
            raise ValueError(
                f"配置键 '{config_key}' 的 read_method '{read_method}' 无效，"
                f"有效值为: {valid_methods}"
            )

        self.logger.info(f"  客户端: {client_key}")
        self.logger.info(f"  读取方法: {read_method}")

        # 3. 从解析后的参数中获取值
        mode = read_params['mode']
        time_range = read_params['time_range']
        last_n_points = read_params['last_n_points']
        include_unavailable = read_params['include_unavailable']
        tag_filters = read_params['tag_filters']

        # 4. 获取特定于方法的参数
        room_uids = config.get('room_uids', [])
        device_uids = config.get('device_uids', [])
        specific_uids = config.get('specific_uids', [])

        # 5. 路由调用
        result = {}

        if read_method == 'read_all_observable_data':
            # 调用 read_all_observable_data
            self.logger.info(f"  调用 read_all_observable_data(include_unavailable={include_unavailable})")
            result = self.read_all_observable_data(client, mode, time_range, last_n_points, include_unavailable, tag_filters)

        elif read_method == 'read_room_data':
            # 调用 read_room_data
            if not room_uids:
                raise ValueError(f"配置键 '{config_key}' 使用 read_room_data 方法时，必须指定 room_uids")
            self.logger.info(f"  读取 {len(room_uids)} 个机房的数据: {room_uids}")
            for room_uid in room_uids:
                try:
                    room_data = self.read_room_data(room_uid, client, mode, time_range, last_n_points, include_unavailable, tag_filters)
                    result.update(room_data)
                except ValueError as e:
                    self.logger.warning(f"  读取机房 {room_uid} 失败: {e}")

        elif read_method == 'read_device_data':
            # 调用 read_device_data
            if not device_uids:
                raise ValueError(f"配置键 '{config_key}' 使用 read_device_data 方法时，必须指定 device_uids")
            self.logger.info(f"  读取 {len(device_uids)} 个设备的数据: {device_uids}")
            for device_uid in device_uids:
                try:
                    device_data = self.read_device_data(device_uid, client, mode, time_range, last_n_points, include_unavailable, tag_filters)
                    result.update(device_data)
                except ValueError as e:
                    self.logger.warning(f"  读取设备 {device_uid} 失败: {e}")

        elif read_method == 'read_specific_uids':
            # 调用 read_specific_uids
            if not specific_uids:
                raise ValueError(f"配置键 '{config_key}' 使用 read_specific_uids 方法时，必须指定 specific_uids")
            self.logger.info(f"  读取 {len(specific_uids)} 个指定 UID 的数据")
            result = self.read_specific_uids(specific_uids, client, mode, time_range, last_n_points, tag_filters)

        self.logger.info(f"成功根据客户端 '{client_key}' 和配置键 '{config_key}' 读取 {len(result)} 个 UID 的数据")
        return result

    def _get_read_config(self, client_key: str, config_key: str) -> Tuple[InfluxDBClientWrapper, Dict, Dict]:
        """
        获取读取配置（内部方法）

        参数:
            client_key: 客户端键名
            config_key: 配置键名

        返回:
            Tuple[InfluxDBClientWrapper, Dict, Dict]: (客户端, 配置, 读取参数)

        异常:
            ValueError: 客户端或配置不存在
        """
        # 1. 验证客户端是否存在
        if client_key not in self.influxdb_clients:
            raise ValueError(f"客户端 '{client_key}' 不存在，可用客户端: {list(self.influxdb_clients.keys())}")
        client = self.influxdb_clients[client_key]

        # 2. 获取客户端配置
        if client_key not in self.read_config:
            raise ValueError(f"客户端 '{client_key}' 没有对应的读取配置")
        client_config = self.read_config[client_key]

        # 3. 读取并验证配置项
        if config_key not in client_config:
            raise ValueError(f"配置键 '{config_key}' 不存在于客户端 '{client_key}' 的配置中")
        config = client_config[config_key]

        # 4. 解析读取参数（优先级：配置项 > 客户端默认 > 全局默认）
        read_params = {
            'mode': self.default_mode,
            'time_range': self.default_time_range,
            'last_n_points': self.default_last_n_points,
            'include_unavailable': self.default_include_unavailable,
            'tag_filters': self.default_tag_filters
        }

        # 应用客户端级别的默认配置
        if 'default' in client_config and isinstance(client_config['default'], dict):
            client_default = client_config['default']
            for key in read_params:
                if key in client_default:
                    read_params[key] = client_default[key]

        # 应用配置项级别的配置（最高优先级）
        for key in read_params:
            if key in config:
                read_params[key] = config[key]

        return client, config, read_params

    def _batch_read_data(
        self,
        uids: List[str],
        client: InfluxDBClientWrapper,
        mode: str,
        time_range: Dict[str, Any],
        last_n_points: Dict[str, Any],
        tag_filters: Dict[str, Any] = None
    ) -> Dict[str, pd.DataFrame]:
        """
        批量读取数据（内部方法）

        参数:
            uids: uid 列表
            client: InfluxDB 客户端（由调用方传入，避免使用实例属性）
            mode: 读取模式（'time_range' 或 'last_n_points'）
            time_range: 时间范围配置（用于 time_range 模式）
            last_n_points: 最近数据点数配置（用于 last_n_points 模式）
            tag_filters: Tag Set 过滤配置（用于添加 WHERE 条件）

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
                batch_result = self._read_batch(batch, client, mode, time_range, last_n_points, tag_filters)
                result.update(batch_result)
        else:
            # 一次性查询
            result = self._read_batch(uids, client, mode, time_range, last_n_points, tag_filters)

        return result

    def _query_single_uid(
        self,
        uid: str,
        client: InfluxDBClientWrapper,
        mode: str,
        time_range: Dict[str, Any],
        last_n_points: Dict[str, Any],
        tag_filters: Dict[str, Any] = None
    ) -> Optional[pd.DataFrame]:
        """
        查询单个 uid 的数据（内部方法，用于并行查询）

        参数:
            uid: 属性唯一标识符
            client: InfluxDB 客户端（由调用方传入，避免使用实例属性，提高线程安全性）
            mode: 读取模式（'time_range' 或 'last_n_points'）
            time_range: 时间范围配置（用于 time_range 模式）
            last_n_points: 最近数据点数配置（用于 last_n_points 模式）
            tag_filters: Tag Set 过滤配置（用于添加 WHERE 条件）

        返回:
            Optional[pd.DataFrame]: DataFrame 或 None（如果没有数据或查询失败）
        """
        try:
            # 构建查询语句（传递配置参数）
            query = self._build_query(uid, mode, time_range, last_n_points, tag_filters)

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
        last_n_points: Dict[str, Any],
        tag_filters: Dict[str, Any] = None
    ) -> Dict[str, pd.DataFrame]:
        """
        读取一批 uid 的数据（内部方法）
        支持并行查询和串行查询两种模式

        参数:
            uids: uid 列表
            client: InfluxDB 客户端（由调用方传入，避免使用实例属性）
            mode: 读取模式（'time_range' 或 'last_n_points'）
            time_range: 时间范围配置（用于 time_range 模式）
            last_n_points: 最近数据点数配置（用于 last_n_points 模式）
            tag_filters: Tag Set 过滤配置（用于添加 WHERE 条件）

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
                    executor.submit(self._query_single_uid, uid, client, mode, time_range, last_n_points, tag_filters): uid
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
                df = self._query_single_uid(uid, client, mode, time_range, last_n_points, tag_filters)
                if df is not None:
                    result[uid] = df

        return result

    def _build_query(self, uid: str, mode: str, time_range: Dict[str, Any], last_n_points: Dict[str, Any], tag_filters: Dict[str, Any] = None) -> str:
        """
        根据配置构建 InfluxDB 查询语句

        参数:
            uid: 属性唯一标识符
            mode: 读取模式（'time_range' 或 'last_n_points'）
            time_range: 时间范围配置（用于 time_range 模式）
            last_n_points: 最近数据点数配置（用于 last_n_points 模式）
            tag_filters: Tag Set 过滤配置（用于添加 WHERE 条件）

        返回:
            str: InfluxDB 查询语句
        """
        # 获取 field_key（从实例属性读取，这是只读配置，不会被临时修改）
        field_key = self.default_field_key

        # 构建 Tag 过滤条件
        tag_conditions = []
        if tag_filters:
            for tag_key, tag_value in tag_filters.items():
                if isinstance(tag_value, list):
                    # 多值匹配：tag_key IN ('value1', 'value2')
                    values_str = "', '".join(str(v) for v in tag_value)
                    tag_conditions.append(f'"{tag_key}" IN (\'{values_str}\')')
                else:
                    # 单值匹配：tag_key = 'value'
                    tag_conditions.append(f'"{tag_key}" = \'{tag_value}\'')

        # 根据模式构建查询
        if mode == 'time_range':
            # time_range 模式
            duration = time_range.get('duration', 1)
            unit = time_range.get('unit', 'h')

            # 构建时间范围字符串
            time_range_str = f"{duration}{unit}"

            # 构建 WHERE 条件
            where_conditions = [f"time > now() - {time_range_str}"]
            where_conditions.extend(tag_conditions)
            where_clause = " AND ".join(where_conditions)

            query = f"""
                SELECT "{field_key}" AS value
                FROM "{uid}"
                WHERE {where_clause}
                ORDER BY time ASC
            """

        elif mode == 'last_n_points':
            # last_n_points 模式
            count = last_n_points.get('count', 100)

            if tag_conditions:
                # 有 Tag 过滤条件时，需要先过滤再限制数量
                where_clause = " AND ".join(tag_conditions)
                query = f"""
                    SELECT "{field_key}" AS value
                    FROM "{uid}"
                    WHERE {where_clause}
                    ORDER BY time DESC
                    LIMIT {count}
                """
            else:
                # 无 Tag 过滤条件时，直接限制数量
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

            # 构建 WHERE 条件
            where_conditions = [f"time > now() - {time_range_str}"]
            where_conditions.extend(tag_conditions)
            where_clause = " AND ".join(where_conditions)

            query = f"""
                SELECT "{field_key}" AS value
                FROM "{uid}"
                WHERE {where_clause}
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
        - 支持两种预测数据写入模式：按测点分离存储和统一存储格式
        - 支持两种优化控制指令写入模式：按测点分离存储和统一存储格式
        - 实现批量写入和重试机制
        - 使用 critical_operation 保护写入操作（线程安全）
        - 采用 client_key -> config_key 的两级配置结构

    属性:
        datacenter: DataCenter 对象
        write_config: 写入配置字典
        influxdb_clients: InfluxDB 客户端字典
        ctx: AppContext 对象（用于 critical_operation）
        logger: 日志器

    方法:
        write_influxdb_data: 统一的数据写入接口（唯一外部调用方法）
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

        # 获取默认配置
        default_config = write_config.get('default', {})
        self.default_batch_size = default_config.get('batch_size', 100)
        self.default_retry_times = default_config.get('retry_times', 3)
        self.default_retry_interval = default_config.get('retry_interval', 2)

        self.logger.info(f"数据写入器初始化完成 - 数据中心: {datacenter.dc_name}")
        self.logger.info(f"  已注册客户端: {list(influxdb_clients.keys())}")
        self.logger.info(f"  默认配置:")
        self.logger.info(f"    批量大小: {self.default_batch_size}")
        self.logger.info(f"    重试次数: {self.default_retry_times}")
        self.logger.info(f"    重试间隔: {self.default_retry_interval}秒")



    def write_influxdb_data(
            self,
            client_key: str,
            config_key: str,
            main_data: Dict[str, Any],
            **kwargs
    ) -> bool:
        """
        统一的数据写入接口（核心实现）

        参数:
            client_key: 客户端键名（如 'prediction_data_client'）
            config_key: 写入配置的键（如 'prediction_by_uid'）
            main_data: 主要的数据字典，例如 {'uid1': value1, 'uid2': value2}
            **kwargs: 其他与数据点构建相关的参数，例如 horizon="15mins"

        返回:
            bool: 写入是否成功
        """
        self.logger.info(f"开始写入数据 - 客户端: {client_key}, 配置: {config_key}")

        # 1. 验证和获取配置
        try:
            client, config, write_params = self._get_write_config(client_key, config_key)
        except ValueError as e:
            self.logger.error(f"获取写入配置失败: {e}")
            raise

        # 2. 构建数据点
        try:
            # 将 kwargs 传递给 _build_points
            points = self._build_points(config, main_data, **kwargs)
            if not points:
                self.logger.warning("没有构建任何数据点，写入操作终止")
                return True
            self.logger.info(f"成功构建 {len(points)} 个数据点")
        except Exception as e:
            self.logger.error(f"构建数据点时发生异常: {e}", exc_info=True)
            return False

        # 3. 批量写入
        database_name = client.get_database_name()
        with critical_operation(self.ctx):
            success = self._batch_write(
                points=points,
                client=client,
                database=database_name,
                batch_size=write_params['batch_size'],
                retry_times=write_params['retry_times'],
                retry_interval=write_params['retry_interval']
            )

        if success:
            self.logger.info(f"成功将 {len(points)} 个数据点写入数据库 '{database_name}'")
        else:
            self.logger.error(f"写入数据到数据库 '{database_name}' 失败")

        return success

    def _get_write_config(self, client_key: str, config_key: str) -> Tuple[InfluxDBClientWrapper, Dict, Dict]:
        """
        获取写入配置（内部方法）

        参数:
            client_key: 客户端键名
            config_key: 配置键名

        返回:
            Tuple[InfluxDBClientWrapper, Dict, Dict]: (客户端, 配置, 写入参数)

        异常:
            ValueError: 客户端或配置不存在
        """
        # 验证客户端是否存在
        if client_key not in self.influxdb_clients:
            raise ValueError(f"客户端 '{client_key}' 不存在，可用客户端: {list(self.influxdb_clients.keys())}")

        # 获取客户端
        client = self.influxdb_clients[client_key]

        # 验证客户端配置是否存在
        if client_key not in self.write_config:
            raise ValueError(f"客户端 '{client_key}' 没有对应的写入配置")

        client_config = self.write_config[client_key]

        # 验证配置键是否存在
        if config_key not in client_config:
            raise ValueError(f"配置键 '{config_key}' 不存在于客户端 '{client_key}' 的配置中")

        config = client_config[config_key]

        # 解析写入参数（优先级：配置项 > 客户端默认 > 全局默认）
        write_params = {
            'batch_size': self.default_batch_size,
            'retry_times': self.default_retry_times,
            'retry_interval': self.default_retry_interval
        }

        # 应用客户端级别的默认配置
        if 'default' in client_config and isinstance(client_config['default'], dict):
            client_default = client_config['default']
            for key in write_params:
                if key in client_default:
                    write_params[key] = client_default[key]

        # 应用配置项级别的配置（最高优先级）
        for key in write_params:
            if key in config:
                write_params[key] = config[key]

        return client, config, write_params

    def _build_points(self, config: Dict, main_data: Dict[str, Any], **kwargs) -> List[Dict[str, Any]]:
        """
        根据配置构建数据点（内部方法）

        参数:
            config: 写入配置
            main_data: 主要的数据字典
            **kwargs: 其他与数据点构建相关的参数

        返回:
            List[Dict[str, Any]]: 数据点列表

        异常:
            ValueError: 配置或数据格式错误
        """
        write_mode = config.get('write_mode')
        if not write_mode:
            raise ValueError("配置中缺少 'write_mode' 字段")

        points = []

        if write_mode == 'separate_by_uid':
            # 模式一：按测点分离存储
            points = self._build_separate_points(config, main_data, **kwargs)
        elif write_mode == 'unified_format':
            # 模式二：统一存储格式
            points = self._build_unified_points(config, main_data, **kwargs)
        else:
            raise ValueError(f"不支持的写入模式: {write_mode}")

        return points

    def _build_separate_points(self, config: Dict, main_data: Dict[str, Any], **kwargs) -> List[Dict[str, Any]]:
        """
        构建按测点分离存储的数据点（通用内部方法）

        参数:
            config: 写入配置
            main_data: 主要数据字典
            **kwargs: 其他与数据点构建相关的参数

        返回:
            List[Dict[str, Any]]: 数据点列表
        """
        points = []
        from datetime import timezone
        current_time = datetime.now(timezone.utc)

        measurement_template = config.get('measurement_template', '{uid}')
        tag_set_config = config.get('tag_set', {})
        field_set_config = config.get('field_set', {})

        for uid, value in main_data.items():
            # 将 kwargs 与 uid 和 value 合并，用于模板格式化
            format_params = {**kwargs, 'uid': uid, 'value': value}

            # 构建 measurement
            measurement = measurement_template.format(**format_params)

            # 构建 tags
            tags = {}
            for tag_key, tag_template in tag_set_config.items():
                tags[tag_key] = str(tag_template).format(**format_params)

            # 构建 fields
            fields = {}
            for field_key, field_template in field_set_config.items():
                # 如果模板是 '{value}'，直接使用 value，否则格式化字符串
                if field_template == '{value}':
                    fields[field_key] = value
                else:
                    fields[field_key] = str(field_template).format(**format_params)

            # 构建数据点
            point = self._build_point(
                measurement=measurement,
                fields=fields,
                tags=tags,
                timestamp=current_time
            )
            points.append(point)

        return points

    def _build_unified_points(self, config: Dict, main_data: Dict[str, Any], **kwargs) -> List[Dict[str, Any]]:
        """
        构建统一存储格式的数据点（通用内部方法）

        参数:
            config: 写入配置
            main_data: 主要数据字典
            **kwargs: 其他与数据点构建相关的参数

        返回:
            List[Dict[str, Any]]: 数据点列表
        """
        points = []
        from datetime import timezone
        current_time = datetime.now(timezone.utc)

        measurement_name = config.get('measurement_name', 'default_measurement')
        tag_set_config = config.get('tag_set', {})
        field_set_config = config.get('field_set', {})

        for uid, content in main_data.items():
            # 将 kwargs 与 uid 和 content 合并，用于模板格式化
            format_params = {**kwargs, 'uid': uid, 'json_content': content}

            # 构建 tags
            tags = {}
            for tag_key, tag_template in tag_set_config.items():
                tags[tag_key] = str(tag_template).format(**format_params)

            # 构建 fields
            fields = {}
            for field_key, field_template in field_set_config.items():
                # 如果模板是 '{json_content}'，直接使用 content，否则格式化字符串
                if field_template == '{json_content}':
                    fields[field_key] = content
                else:
                    fields[field_key] = str(field_template).format(**format_params)

            # 构建数据点
            point = self._build_point(
                measurement=measurement_name,
                fields=fields,
                tags=tags,
                timestamp=current_time
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
