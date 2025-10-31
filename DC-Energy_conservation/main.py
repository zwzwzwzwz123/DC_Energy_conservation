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

from utils.initialization import init_multi_level_loggers, load_configs
from utils.influxdb_wrapper import init_influxdb_clients

# 全局变量，用于在线程间共享
loggers = None  # 存储所有日志器的字典
dc_status_client = None
prediction_client = None
optimization_client = None


def prediction_training_thread(logger):
    """
    预测训练线程 - 从 InfluxDB 读取数据中心状态并训练预测模型

    参数:
        logger: 预测训练专用日志器（会自动同时写入 prediction_training_log.log 和 total_running_log.log）
    """
    global dc_status_client

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


def prediction_inference_thread(logger):
    """
    预测推理线程 - 执行预测模型并写入结果

    参数:
        logger: 预测推理专用日志器（会自动同时写入 prediction_inference_log.log 和 total_running_log.log）
    """
    global dc_status_client, prediction_client

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


def optimization_thread(logger):
    """
    优化线程 - 执行优化算法并写入控制指令

    参数:
        logger: 优化专用日志器（会自动同时写入 optimization_log.log 和 total_running_log.log）
    """
    global dc_status_client, prediction_client, optimization_client

    while True:
        try:
            # TODO: 实现优化逻辑
            # 1. 从 prediction_client 读取预测数据
            # 2. 根据预测数据执行优化算法
            # 3. 生成控制指令
            # 4. 将控制指令写入 optimization_client
            # 5. 从 dc_status_client 读取状态数据，与环境不断交互进行强化学习
            # 6. 不断生成控制指令
            # 7. 不断将控制指令写入 optimization_client
            logger.info("优化线程运行中...")
            time.sleep(600)  # 每10分钟优化一次
        except Exception as e:
            logger.error(f"优化线程出错: {e}", exc_info=True)
            time.sleep(60)  # 出错后等待1分钟再重试


def main():
    """
    主函数 - 多线程架构
    """
    global loggers, dc_status_client, prediction_client, optimization_client

    print("=" * 60)
    print("数据中心节能项目启动中...")
    print("=" * 60)

    # 1. 加载配置文件
    print("\n[1/3] 加载配置文件...")
    main_config, models_config, modules_config, security_boundary_config, uid_config, utils_config = load_configs()
    print("✓ 配置文件加载成功")

    # 2. 初始化多层级日志系统
    print("\n[2/3] 初始化多层级日志系统...")
    try:
        loggers = init_multi_level_loggers(utils_config["logging"])
        print("✓ 多层级日志系统初始化成功")
        print(f"  - 全局日志: total_running_log.log")
        print(f"  - 主程序日志: main_log.log")
        print(f"  - InfluxDB日志: influxdb_log.log")
        print(f"  - 预测训练日志: prediction_training_log.log")
        print(f"  - 预测推理日志: prediction_inference_log.log")
        print(f"  - 优化日志: optimization_log.log")

        # 使用 main logger 记录主程序日志
        loggers["main"].info("数据中心节能项目启动")
    except Exception as e:
        print(f"✗ 日志系统初始化失败: {e}")
        sys.exit(1)

    # 3. 初始化 InfluxDB 客户端
    print("\n[3/3] 初始化 InfluxDB 客户端...")
    try:
        # 传入 influxdb logger，使 InfluxDB 相关日志自动写入 influxdb_log.log 和 total_running_log.log
        dc_status_client, prediction_client, optimization_client = init_influxdb_clients(
            utils_config, loggers["influxdb"]
        )
        # 使用 influxdb logger 记录 InfluxDB 相关日志
        loggers["influxdb"].info("InfluxDB 客户端全部初始化成功")
        print("✓ InfluxDB 客户端初始化成功")
        loggers["influxdb"].info(
            f"  - 数据中心状态数据数据库: {utils_config['InfluxDB']['influxdb_dc_status_data']['database']}")
        loggers["influxdb"].info(
            f"  - 预测数据数据库: {utils_config['InfluxDB']['influxdb_prediction_data']['database']}")
        loggers["influxdb"].info(
            f"  - 优化数据数据库: {utils_config['InfluxDB']['influxdb_optimization_data']['database']}")
    except Exception as e:
        loggers["influxdb"].error(f"InfluxDB 客户端初始化失败: {e}")
        print(f"✗ InfluxDB 客户端初始化失败: {e}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("初始化完成，启动多线程...")
    print("=" * 60)
    loggers["main"].info("系统初始化完成，准备启动多线程")

    # 4. 创建并启动子线程（将对应的 logger 传递给各个线程）
    try:
        # 创建三个子线程，传入对应的日志器
        thread_prediction_training = Thread(
            target=prediction_training_thread,
            args=(loggers["prediction_training"],),  # 传入预测训练日志器
            name="PredictionTraining"
        )
        thread_prediction_inference = Thread(
            target=prediction_inference_thread,
            args=(loggers["prediction_inference"],),  # 传入预测推理日志器
            name="PredictionInference"
        )
        thread_optimization = Thread(
            target=optimization_thread,
            args=(loggers["optimization"],),  # 传入优化日志器
            name="Optimization"
        )

        # 设置为守护线程（主线程退出时自动结束）
        thread_prediction_training.daemon = True
        thread_prediction_inference.daemon = True
        thread_optimization.daemon = True

        # 启动子线程
        thread_prediction_training.start()
        loggers["main"].info("✓ 预测训练线程已启动")

        thread_prediction_inference.start()
        loggers["main"].info("✓ 预测推理线程已启动")

        thread_optimization.start()
        loggers["main"].info("✓ 优化线程已启动")

        loggers["main"].info("成功启动所有子线程")
        print("✓ 所有子线程已启动")
        print("\n主程序运行中... (按 Ctrl+C 退出)")

        # 保持主线程存活
        while True:
            time.sleep(3600)  # 主线程每小时检查一次

    except KeyboardInterrupt:
        loggers["main"].info("接收到中断信号，程序终止")
        print("\n接收到退出信号，正在关闭系统...")
    except Exception as e:
        loggers["main"].error(f"程序运行出错: {e}", exc_info=True)
        print(f"\n程序运行出错: {e}")
    finally:
        # 清理资源
        print("正在关闭 InfluxDB 连接...")
        try:
            dc_status_client.close()
            prediction_client.close()
            optimization_client.close()
            loggers["influxdb"].info("InfluxDB 连接已关闭")
        except Exception as e:
            loggers["influxdb"].error(f"关闭连接时出错: {e}")

        loggers["main"].info("系统已关闭")
        print("系统已关闭")


if __name__ == "__main__":
    main()
