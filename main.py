"""
数据中心节能项目主程序
"""
import sys
from pathlib import Path

# 添加项目根目录到系统路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from utils import initialization, data_reading_writing
import time
from threading import Thread

# ==================== 系统初始化 ====================
logger, configs, clients = initialization.init_system(project_root)

# 提取常用配置
influxdb_config = configs['influxdb']
uid_config = configs['uid']
security_boundary_config = configs['security_boundary']

# 打印初始化信息
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
