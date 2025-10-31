"""
数据中心节能项目 - 主程序入口
"""

import sys
import time
import logging
from pathlib import Path
from threading import Thread, Event
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Dict

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.initialization import init_multi_level_loggers, load_configs
from utils.influxdb_wrapper import init_influxdb_clients, InfluxDBClientWrapper


@dataclass
class AppContext:
    """
    应用上下文类，封装所有全局状态

    属性:
        loggers: 所有日志器的字典
        dc_status_client: 数据中心状态数据客户端
        prediction_client: 预测数据客户端
        optimization_client: 优化数据客户端
        shutdown_event: 关闭事件，用于优雅关闭线程

    注意:
        - logging 模块本身是线程安全的，多个线程可以安全地使用同一个 logger
        - InfluxDBClientWrapper 的操作也是线程安全的（底层使用 requests 库）
        - shutdown_event 用于通知所有线程优雅退出
    """
    loggers: Dict[str, logging.Logger]
    dc_status_client: InfluxDBClientWrapper
    prediction_client: InfluxDBClientWrapper
    optimization_client: InfluxDBClientWrapper
    shutdown_event: Event


def prediction_training_thread(ctx: AppContext):
    """
    预测训练线程 - 从 InfluxDB 读取数据中心状态并训练预测模型

    参数:
        ctx: 应用上下文，包含 loggers、InfluxDB 客户端和 shutdown_event
    """
    logger = ctx.loggers["prediction_training"]
    logger.info("预测训练线程已启动")

    while not ctx.shutdown_event.is_set():
        try:
            # TODO: 实现预测训练逻辑
            # 1. 从 ctx.dc_status_client 读取数据中心状态数据
            # 2. 数据预处理
            # 3. 训练预测模型
            # 4. 保存模型
            logger.info("预测训练线程运行中...")

            # 使用 wait() 代替 sleep()，以便能够响应 shutdown_event
            if ctx.shutdown_event.wait(timeout=3600):  # 每小时训练一次
                break  # 收到关闭信号，退出循环
        except Exception as e:
            logger.error(f"预测训练线程出错: {e}", exc_info=True)
            if ctx.shutdown_event.wait(timeout=60):  # 出错后等待1分钟再重试
                break

    logger.info("预测训练线程已退出")


def prediction_inference_thread(ctx: AppContext):
    """
    预测推理线程 - 执行预测模型并写入结果

    参数:
        ctx: 应用上下文，包含 loggers、InfluxDB 客户端和 shutdown_event
    """
    logger = ctx.loggers["prediction_inference"]
    logger.info("预测推理线程已启动")

    while not ctx.shutdown_event.is_set():
        try:
            # TODO: 实现预测推理逻辑
            # 1. 从 ctx.dc_status_client 读取最新数据
            # 2. 加载预测模型
            # 3. 执行预测
            # 4. 将预测结果写入 ctx.prediction_client
            logger.info("预测推理线程运行中...")

            # 使用 wait() 代替 sleep()，以便能够响应 shutdown_event
            if ctx.shutdown_event.wait(timeout=300):  # 每5分钟预测一次
                break  # 收到关闭信号，退出循环
        except Exception as e:
            logger.error(f"预测推理线程出错: {e}", exc_info=True)
            if ctx.shutdown_event.wait(timeout=60):  # 出错后等待1分钟再重试
                break

    logger.info("预测推理线程已退出")


def optimization_thread(ctx: AppContext):
    """
    优化线程 - 执行优化算法并写入控制指令

    参数:
        ctx: 应用上下文，包含 loggers、InfluxDB 客户端和 shutdown_event
    """
    logger = ctx.loggers["optimization"]
    logger.info("优化线程已启动")

    while not ctx.shutdown_event.is_set():
        try:
            # TODO: 实现优化逻辑
            # 1. 从 ctx.prediction_client 读取预测数据
            # 2. 根据预测数据执行优化算法
            # 3. 生成控制指令
            # 4. 将控制指令写入 ctx.optimization_client
            # 5. 从 ctx.dc_status_client 读取状态数据，与环境不断交互进行强化学习
            # 6. 不断生成控制指令
            # 7. 不断将控制指令写入 ctx.optimization_client
            logger.info("优化线程运行中...")

            # 使用 wait() 代替 sleep()，以便能够响应 shutdown_event
            if ctx.shutdown_event.wait(timeout=600):  # 每10分钟优化一次
                break  # 收到关闭信号，退出循环
        except Exception as e:
            logger.error(f"优化线程出错: {e}", exc_info=True)
            if ctx.shutdown_event.wait(timeout=60):  # 出错后等待1分钟再重试
                break

    logger.info("优化线程已退出")


def main():
    """
    主函数 - 多线程架构
    """
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
        print(f"  - 全局日志: total_log.log")
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
        # 传入 influxdb logger，使 InfluxDB 相关日志自动写入 influxdb_log.log 和 total_log.log
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

    # 创建关闭事件
    shutdown_event = Event()

    # 创建应用上下文
    ctx = AppContext(
        loggers=loggers,
        dc_status_client=dc_status_client,
        prediction_client=prediction_client,
        optimization_client=optimization_client,
        shutdown_event=shutdown_event
    )

    print("\n" + "=" * 60)
    print("初始化完成，启动多线程...")
    print("=" * 60)
    ctx.loggers["main"].info("系统初始化完成，准备启动多线程")

    # 4. 使用 ThreadPoolExecutor 管理线程
    executor = None
    try:
        # 创建线程池（3个工作线程）
        executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="Worker")

        # 提交三个任务到线程池
        future_prediction_training = executor.submit(prediction_training_thread, ctx)
        future_prediction_inference = executor.submit(prediction_inference_thread, ctx)
        future_optimization = executor.submit(optimization_thread, ctx)

        ctx.loggers["main"].info("✓ 所有工作线程已提交到线程池")
        print("✓ 所有工作线程已启动")
        print("\n主程序运行中... (按 Ctrl+C 退出)")

        # 保持主线程存活，等待中断信号
        while True:
            time.sleep(10)  # 短暂休眠，以便快速响应中断信号

    except KeyboardInterrupt:
        ctx.loggers["main"].info("接收到中断信号，开始关闭系统...")
        print("\n接收到退出信号，正在关闭系统...")

        # 设置关闭事件，通知所有线程退出
        shutdown_event.set()
        ctx.loggers["main"].info("已发送关闭信号到所有工作线程")

    except Exception as e:
        ctx.loggers["main"].error(f"程序运行出错: {e}", exc_info=True)
        print(f"\n程序运行出错: {e}")
        shutdown_event.set()  # 确保线程能够退出

    finally:
        # 清理资源
        if executor:
            ctx.loggers["main"].info("等待所有工作线程退出...")
            print("等待所有工作线程退出...")

            # 关闭线程池，等待所有线程完成
            executor.shutdown(wait=True, cancel_futures=True)
            ctx.loggers["main"].info("所有工作线程已退出")
            print("✓ 所有工作线程已退出")

        # 关闭 InfluxDB 连接
        print("正在关闭 InfluxDB 连接...")
        try:
            ctx.dc_status_client.close()
            ctx.prediction_client.close()
            ctx.optimization_client.close()
            ctx.loggers["influxdb"].info("InfluxDB 连接已关闭")
            print("✓ InfluxDB 连接已关闭")
        except Exception as e:
            ctx.loggers["influxdb"].error(f"关闭连接时出错: {e}")

        ctx.loggers["main"].info("系统已关闭")
        print("✓ 系统已关闭")


if __name__ == "__main__":
    main()
