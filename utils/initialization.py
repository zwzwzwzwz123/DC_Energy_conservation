import logging
from logging.handlers import TimedRotatingFileHandler
import os
import yaml
import atexit
from pathlib import Path
from influxdb import InfluxDBClient


def load_configs(project_root):
    """
    加载所有配置文件
    
    Args:
        project_root: 项目根目录路径
        
    Returns:
        dict: 包含所有配置的字典
    """
    config_dir = Path(project_root) / "configs"
    
    configs = {}
    config_files = {
        'influxdb': 'influxdb_config.yaml',
        'security_boundary': 'security_boundary_config.yaml',
        'uid': 'uid_config.yaml'
    }
    
    for config_name, filename in config_files.items():
        config_path = config_dir / filename
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                configs[config_name] = yaml.safe_load(f)
        else:
            raise FileNotFoundError(f"配置文件不存在: {config_path}")
    
    return configs


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


def init_system(project_root):
    """
    完整的系统初始化
    
    Args:
        project_root: 项目根目录路径
        
    Returns:
        tuple: (logger, configs, clients)
            - logger: 日志对象
            - configs: 配置字典
            - clients: 数据库客户端字典
    """
    # 1. 初始化日志
    logger = init_logger()
    logger.info("="*60)
    logger.info("系统启动")
    logger.info("="*60)
    logger.info("成功初始化日志系统")
    
    # 2. 加载配置文件
    logger.info("开始加载配置文件...")
    configs = load_configs(project_root)
    logger.info(f"成功加载配置文件: {list(configs.keys())}")
    
    # 3. 打印配置信息
    if 'uid' in configs:
        room_name = configs['uid'].get('room_name', '未知')
        ac_count = len(configs['uid'].get('air_conditioners', {}))
        logger.info(f"机房: {room_name}, 空调数量: {ac_count}")
    
    # 4. 初始化InfluxDB客户端
    logger.info("开始初始化 InfluxDB 客户端...")
    influxdb_config = configs['influxdb']
    dc_status_data_client, prediction_data_client, setting_data_client, reference_data_client = (
        init_influxdb_client(influxdb_config)
    )
    
    # 5. 注册客户端关闭回调
    atexit.register(lambda: [
        client.close() for client in [
            dc_status_data_client,
            prediction_data_client,
            setting_data_client,
            reference_data_client
        ] if hasattr(client, 'close')
    ])
    logger.info("成功初始化 InfluxDB 客户端")
    
    # 6. 构建客户端字典
    clients = {
        'dc_status': dc_status_data_client,
        'prediction': prediction_data_client,
        'setting': setting_data_client,
        'reference': reference_data_client
    }
    
    logger.info("="*60)
    logger.info("系统初始化完成")
    logger.info("="*60)
    
    return logger, configs, clients
