import logging
from logging.handlers import TimedRotatingFileHandler
import os
from influxdb import InfluxDBClient


def init_logger():
    """
    初始化日志
    """
    logger = logging.getLogger("my_logger")
    if logger.handlers:  # 避免重复添加处理器
        return logger
    logger.setLevel(logging.DEBUG)  # 收集所有级别日志
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")  # 日志格式
    log_dir = "../logs"
    os.makedirs(log_dir, exist_ok=True)  # 确保日志目录存在（新增代码）
    log_path = os.path.join(log_dir, "run.log")

    # 控制台日志
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)
    # 文件处理器日志
    file_handler = TimedRotatingFileHandler(log_path, encoding="utf-8", when="midnight", interval=1, backupCount=1)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    return logger


# region 初始化InfluxDB数据库输入输出客户端,InfluxDB 1.x
def _init_database_client(config):
    """
    初始化InfluxDB 1.x数据库客户端
    """
    host = config["host"]
    port = config["port"]
    username = config["username"]
    password = config["password"]
    database = config["database"]

    client = InfluxDBClient(
        host=host,
        port=port,
        username=username,
        password=password,
        database=database
    )
    return client


def init_influxdb_client(config):
    """
    初始化InfluxDB 1.x客户端并返回client对象
    返回：(读取client, 读取client, 写入client, 写入client, 写入client)
    注意：InfluxDB 1.x中读取和写入使用同一个客户端对象
    """
    dc_status_data_client = _init_database_client(config["influxdb_dc_status_data"])
    prediction_data_client = _init_database_client(config["influxdb_prediction_data"])
    setting_data_client = _init_database_client(config["influxdb_setting_data"])
    reference_data_client = _init_database_client(config["influxdb_reference_data"])

    # InfluxDB 1.x中读取和写入使用同一个客户端
    return (dc_status_data_client,  # 数据中心状态读取client
            prediction_data_client,  # 预测数据读取、写入client
            setting_data_client,  # 设置数据写入client
            reference_data_client)  # 参考数据写入client

# endregion
