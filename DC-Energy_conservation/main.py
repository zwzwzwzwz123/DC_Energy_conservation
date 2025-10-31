"""
数据中心节能项目 - 主程序入口
"""

import sys
import time
from pathlib import Path
from threading import Thread

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.initialization import init_logger, load_configs
from utils.influxdb_wrapper import init_influxdb_clients

# 全局变量，用于在线程间共享
logger = None
dc_status_client = None
prediction_client = None
optimization_client = None


def prediction_training_thread():
    """预测训练线程 - 从 InfluxDB 读取数据中心状态并训练预测模型"""
    global logger, dc_status_client

    while True:
        try:
            # TODO: 实现预测训练逻辑
            # 1. 从 dc_status_client 读取数据中心状态数据
            # 2. 数据预处理
            # 3. 训练预测模型
            # 4. 保存模型
            logger.info("预测训练线程运行中...")
            time.sleep(3600)  # 每小时训练一次
        except Exception as e:
            logger.error(f"预测训练线程出错: {e}", exc_info=True)
            time.sleep(60)  # 出错后等待1分钟再重试


def prediction_inference_thread():
    """预测推理线程 - 执行预测模型并写入结果"""
    global logger, dc_status_client, prediction_client

    while True:
        try:
            # TODO: 实现预测推理逻辑
            # 1. 从 dc_status_client 读取最新数据
            # 2. 加载预测模型
            # 3. 执行预测
            # 4. 将预测结果写入 prediction_client
            logger.info("预测推理线程运行中...")
            time.sleep(300)  # 每5分钟预测一次
        except Exception as e:
            logger.error(f"预测推理线程出错: {e}", exc_info=True)
            time.sleep(60)  # 出错后等待1分钟再重试


def optimization_thread():
    """优化线程 - 执行优化算法并写入控制指令"""
    global logger, dc_status_client, prediction_client, optimization_client

    while True:
        try:
            # TODO: 实现优化逻辑
            # 1. 从 prediction_client 读取预测数据
            # 2. 执行优化算法
            # 3. 从 dc_status_client 读取状态数据
            # 4. 执行优化算法
            # 5. 生成控制指令
            # 6. 将控制指令写入 optimization_client
            logger.info("优化线程运行中...")
            time.sleep(600)  # 每10分钟优化一次
        except Exception as e:
            logger.error(f"优化线程出错: {e}", exc_info=True)
            time.sleep(60)  # 出错后等待1分钟再重试


def main():
    """
    主函数 - 多线程架构
    """
    global logger, dc_status_client, prediction_client, optimization_client

    print("=" * 60)
    print("数据中心节能项目启动中...")
    print("=" * 60)

    # 1. 加载配置文件
    print("\n[1/3] 加载配置文件...")
    main_config, models_config, modules_config, utils_config, security_boundary_config, uid_config = load_configs()
    print("✓ 配置文件加载成功")

    # 2. 初始化日志系统
    print("\n[2/3] 初始化日志系统...")
    try:
        logger = init_logger(utils_config["logging"])
        print("✓ 日志系统初始化成功")
        logger.info("=" * 60)
        logger.info("数据中心节能项目启动")
        logger.info("=" * 60)
    except Exception as e:
        print(f"✗ 日志系统初始化失败: {e}")
        sys.exit(1)

    # 3. 初始化 InfluxDB 客户端
    print("\n[3/3] 初始化 InfluxDB 客户端...")
    try:
        dc_status_client, prediction_client, optimization_client = init_influxdb_clients(utils_config)
        logger.info("InfluxDB 客户端初始化成功")
        print("✓ InfluxDB 客户端初始化成功")
        logger.info(f"  - 数据中心状态数据数据库: {utils_config['InfluxDB']['influxdb_dc_status_data']['database']}")
        logger.info(f"  - 预测数据数据库: {utils_config['InfluxDB']['influxdb_prediction_data']['database']}")
        logger.info(f"  - 优化数据数据库: {utils_config['InfluxDB']['influxdb_optimization_data']['database']}")
    except Exception as e:
        logger.error(f"InfluxDB 客户端初始化失败: {e}")
        print(f"✗ InfluxDB 客户端初始化失败: {e}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("初始化完成，启动多线程...")
    print("=" * 60)
    logger.info("系统初始化完成")

    # 4. 创建并启动子线程
    try:
        # 创建三个子线程
        thread_prediction_training = Thread(target=prediction_training_thread, name="PredictionTraining")
        thread_prediction_inference = Thread(target=prediction_inference_thread, name="PredictionInference")
        thread_optimization = Thread(target=optimization_thread, name="Optimization")

        # 设置为守护线程（主线程退出时自动结束）
        thread_prediction_training.daemon = True
        thread_prediction_inference.daemon = True
        thread_optimization.daemon = True

        # 启动子线程
        thread_prediction_training.start()
        logger.info("✓ 预测训练线程已启动")

        thread_prediction_inference.start()
        logger.info("✓ 预测推理线程已启动")

        thread_optimization.start()
        logger.info("✓ 优化线程已启动")

        logger.info("成功启动多线程循环")
        print("✓ 所有子线程已启动")
        print("\n主程序运行中... (按 Ctrl+C 退出)")

        # 保持主线程存活
        while True:
            time.sleep(3600)  # 主线程每小时检查一次

    except KeyboardInterrupt:
        logger.info("接收到中断信号，程序终止")
        print("\n接收到退出信号，正在关闭系统...")
    except Exception as e:
        logger.error(f"程序运行出错: {e}", exc_info=True)
        print(f"\n程序运行出错: {e}")
    finally:
        # 清理资源
        logger.info("关闭 InfluxDB 连接...")
        print("正在关闭 InfluxDB 连接...")
        try:
            dc_status_client.close()
            prediction_client.close()
            optimization_client.close()
            logger.info("InfluxDB 连接已关闭")
        except Exception as e:
            logger.error(f"关闭连接时出错: {e}")

        logger.info("系统已关闭")
        print("系统已关闭")


if __name__ == "__main__":
    main()
