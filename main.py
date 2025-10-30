"""
    数据中心节能项目主程序
"""
import sys
import os
from pathlib import Path

# 添加项目根目录到系统路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from utils import initialization, data_reading_writing
import yaml
import atexit
import time
from threading import Thread

# ==================== 初始化 ====================
def load_configs():
    """加载所有配置文件"""
    config_dir = project_root / "configs"
    
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

def initialize():
    """初始化系统"""
    # 1. 初始化日志
    logger = initialization.init_logger()
    logger.info("="*60)
    logger.info("系统启动")
    logger.info("="*60)
    logger.info("成功初始化日志系统")
    
    # 2. 加载配置文件
    logger.info("开始加载配置文件...")
    configs = load_configs()
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
        initialization.init_influxdb_client(influxdb_config)
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
    
    # 6. 返回所有必要的对象
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

# 执行初始化
logger, configs, clients = initialize()
influxdb_config = configs['influxdb']
uid_config = configs['uid']
security_boundary_config = configs['security_boundary']

print("\n" + "="*60)
print("✓ 系统初始化完成")
print(f"✓ 机房: {uid_config.get('room_name', '未知')}")
print(f"✓ 空调数量: {len(uid_config.get('air_conditioners', {}))}")
print("="*60 + "\n")

# ==================== 数据读写示例 ====================
"""
以下是数据读写的使用示例，取消注释即可使用

# 1. 数据读取示例（新格式）
query_result = data_reading_writing.reading_data_query(
    influxdb_config, 
    uid_config,
    clients['dc_status'],
    query_range="-1h",  # 查询最近1小时的数据
    query_measurement=None,  # None表示查询所有测点
    enable_unified_sampling=True,
    target_interval_seconds=30
)
logger.info(f"查询到 {len(query_result)} 条数据")

# 2. 数据写入示例（新格式）
setting_data = {
    "佳力图KN10空调4-3-9": {
        "温度设定值": 25.0,
        "湿度设置值": 50.0,
        "开关机命令": 1
    },
    "艾特空调4-1-4": {
        "送风温度设置点": 26.0,
        "湿度设定点": 55.0,
        "监控开关机": 1
    }
}

data_reading_writing.setting_data_writing(
    influxdb_config, 
    uid_config, 
    setting_data, 
    clients['setting']
)
logger.info("成功写入设置数据")
"""


# ==================== 主程序 ====================
def main():
    """主程序入口"""
    logger.info("主程序开始运行")
    
    # TODO: 在这里添加你的业务逻辑
    # 例如：启动多线程、运行优化模块、预测模块等
    
    print("✓ 系统运行中...")
    print("✓ 按 Ctrl+C 停止程序\n")
    
    try:
        # 保持主程序运行
        while True:
            time.sleep(60)  # 每分钟检查一次
            
    except KeyboardInterrupt:
        logger.info("接收到中断信号，程序终止")
        print("\n✓ 程序已安全退出")


# ==================== 程序入口 ====================
if __name__ == "__main__":
    main()
