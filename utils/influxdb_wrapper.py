"""
InfluxDB 客户端包装器
提供带自动重连功能的 InfluxDB 客户端
"""

import logging
import time
from typing import Dict, Tuple, List, Any
from influxdb import InfluxDBClient
import requests.exceptions

logger = logging.getLogger(__name__)


class InfluxDBClientWrapper:
    """
    InfluxDB 客户端包装器，提供自动重连功能

    当网络中断后恢复时，客户端能够自动重新连接到 InfluxDB 服务器
    重连机制在执行查询或写入操作时触发（懒加载重连）
    """

    def __init__(self, client_config: Dict, reconnect_config: Dict):
        """
        初始化 InfluxDB 客户端包装器

        参数:
            client_config: 客户端配置字典
                          包含 host, port, username, password, database
            reconnect_config: 重连配置字典
                            包含 max_retries, retry_interval, timeout
        """
        self.client_config = client_config
        self.reconnect_config = reconnect_config
        self.client = None
        self._connect()

    def _connect(self) -> None:
        """
        建立 InfluxDB 连接

        异常:
            Exception: 连接失败
        """
        try:
            host = self.client_config["host"]
            port = self.client_config["port"]
            username = self.client_config["username"]
            password = self.client_config["password"]
            database = self.client_config["database"]
            timeout = self.reconnect_config.get("timeout", 10)

            # 创建 InfluxDB 1.8 客户端
            self.client = InfluxDBClient(
                host=host,
                port=port,
                username=username,
                password=password,
                database=database,
                timeout=timeout
            )

            # 测试连接
            self.client.ping()
            logger.info(f"InfluxDB 连接成功: {host}:{port}/{database}")

        except Exception as e:
            logger.error(f"InfluxDB 连接失败: {e}")
            raise

    def _reconnect(self) -> bool:
        """
        尝试重新连接到 InfluxDB

        返回:
            bool: 重连是否成功
        """
        max_retries = self.reconnect_config.get("max_retries", 3)
        retry_interval = self.reconnect_config.get("retry_interval", 5)

        for attempt in range(1, max_retries + 1):
            try:
                logger.warning(f"尝试重新连接 InfluxDB (第 {attempt}/{max_retries} 次)...")
                self._connect()
                logger.info("InfluxDB 重连成功")
                return True
            except Exception as e:
                logger.error(f"重连失败 (第 {attempt}/{max_retries} 次): {e}")
                if attempt < max_retries:
                    logger.info(f"等待 {retry_interval} 秒后重试...")
                    time.sleep(retry_interval)

        logger.error(f"InfluxDB 重连失败，已达到最大重试次数 ({max_retries})")
        return False

    def query(self, query_str: str, *args, **kwargs) -> Any:
        """
        执行查询操作，带自动重连功能

        参数:
            query_str: 查询语句
            *args, **kwargs: 传递给 InfluxDBClient.query() 的其他参数

        返回:
            查询结果

        异常:
            Exception: 查询失败且重连失败
        """
        try:
            return self.client.query(query_str, *args, **kwargs)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, Exception) as e:
            logger.warning(f"查询操作失败，尝试重连: {e}")

            # 尝试重连
            if self._reconnect():
                # 重连成功，重试查询
                try:
                    return self.client.query(query_str, *args, **kwargs)
                except Exception as retry_error:
                    logger.error(f"重连后查询仍然失败: {retry_error}")
                    raise
            else:
                # 重连失败
                raise Exception(f"查询失败且重连失败: {e}")

    def write_points(self, points: List[Dict], *args, **kwargs) -> bool:
        """
        写入数据点，带自动重连功能

        参数:
            points: 数据点列表
            *args, **kwargs: 传递给 InfluxDBClient.write_points() 的其他参数

        返回:
            bool: 写入是否成功

        异常:
            Exception: 写入失败且重连失败
        """
        try:
            return self.client.write_points(points, *args, **kwargs)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, Exception) as e:
            logger.warning(f"写入操作失败，尝试重连: {e}")

            # 尝试重连
            if self._reconnect():
                # 重连成功，重试写入
                try:
                    return self.client.write_points(points, *args, **kwargs)
                except Exception as retry_error:
                    logger.error(f"重连后写入仍然失败: {retry_error}")
                    raise
            else:
                # 重连失败
                raise Exception(f"写入失败且重连失败: {e}")

    def close(self) -> None:
        """关闭 InfluxDB 连接"""
        if self.client:
            self.client.close()
            logger.info("InfluxDB 连接已关闭")


def _init_single_influxdb_client(client_config: Dict, reconnect_config: Dict) -> InfluxDBClientWrapper:
    """
    初始化单个 InfluxDB 客户端（内部函数）

    参数:
        client_config: 单个客户端的配置字典
                      包含 host, port, username, password, database
        reconnect_config: 重连配置字典
                        包含 max_retries, retry_interval, timeout

    返回:
        InfluxDBClientWrapper: 包装后的 InfluxDB 客户端对象

    异常:
        KeyError: 配置参数缺失
        Exception: 数据库连接失败
    """
    try:
        return InfluxDBClientWrapper(client_config, reconnect_config)
    except KeyError as e:
        raise KeyError(f"InfluxDB 配置参数缺失: {e}")
    except Exception as e:
        raise Exception(f"InfluxDB 客户端初始化失败 (database: {client_config.get('database', 'unknown')}): {e}")


def init_influxdb_clients(utils_config: Dict) -> Tuple[
    InfluxDBClientWrapper, InfluxDBClientWrapper, InfluxDBClientWrapper]:
    """
    初始化 InfluxDB 1.8 客户端（带自动重连功能）

    参数:
        utils_config: 包含 InfluxDB 配置字典，从 utils.yaml 读取
                     包含三个客户端的配置:
                     - InfluxDB.influxdb_dc_status_data: 数据中心状态数据客户端配置
                     - InfluxDB.influxdb_prediction_data: 预测数据客户端配置
                     - InfluxDB.influxdb_optimization_data: 优化数据客户端配置
                     - InfluxDB.influxdb_reconnect: 重连配置

    返回:
        Tuple[InfluxDBClientWrapper, InfluxDBClientWrapper, InfluxDBClientWrapper]:
            (dc_status_data_client, prediction_data_client, optimization_data_client)
            - dc_status_data_client: 数据中心状态数据客户端（读取）
            - prediction_data_client: 预测数据客户端（读写）
            - optimization_data_client: 优化数据客户端（写入）

    异常:
        KeyError: 配置参数缺失
        Exception: 客户端初始化失败

    注意:
        InfluxDB 1.8 中读取和写入使用同一个客户端对象
    """
    try:
        # 获取重连配置
        reconnect_config = utils_config["InfluxDB"].get("influxdb_reconnect", {
            "max_retries": 3,
            "retry_interval": 5,
            "timeout": 10
        })

        # 初始化数据中心状态数据客户端（读取）
        dc_status_data_client = _init_single_influxdb_client(
            utils_config["InfluxDB"]["influxdb_dc_status_data"], reconnect_config
        )

        # 初始化预测数据客户端（读写）
        prediction_data_client = _init_single_influxdb_client(
            utils_config["InfluxDB"]["influxdb_prediction_data"], reconnect_config
        )

        # 初始化优化数据客户端（写入）
        optimization_data_client = _init_single_influxdb_client(
            utils_config["InfluxDB"]["influxdb_optimization_data"], reconnect_config
        )

        return (
            dc_status_data_client,
            prediction_data_client,
            optimization_data_client
        )

    except KeyError as e:
        raise KeyError(f"InfluxDB 配置缺失: {e}")
    except Exception as e:
        raise Exception(f"InfluxDB 客户端初始化失败: {e}")
