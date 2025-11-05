"""
数据中心节能项目 - 主程序入口
"""

import sys
import time
import logging
from pathlib import Path
from threading import Thread, Event, Lock
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from typing import Dict

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.initialization import init_multi_level_loggers, load_configs
from utils.influxdb_wrapper import init_influxdb_clients, InfluxDBClientWrapper
from utils.critical_operation import critical_operation, wait_for_critical_operations


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
        main_config: 主配置字典，从 main.yaml 加载
        critical_operation_lock: 保护关键操作计数器的锁
        critical_operation_count: 当前正在执行的关键操作数量

    注意:
        - logging 模块本身是线程安全的，多个线程可以安全地使用同一个 logger
        - InfluxDBClientWrapper 的操作也是线程安全的（底层使用 requests 库）
        - shutdown_event 用于通知所有线程优雅退出
        - critical_operation_lock 和 critical_operation_count 用于保护关键操作（数据库写入、模型保存）
    """
    loggers: Dict[str, logging.Logger]
    dc_status_client: InfluxDBClientWrapper
    prediction_client: InfluxDBClientWrapper
    optimization_client: InfluxDBClientWrapper
    shutdown_event: Event
    main_config: Dict
    critical_operation_lock: Lock = field(default_factory=Lock)
    critical_operation_count: int = 0


def prediction_training_thread(ctx: AppContext):
    """
    预测训练线程 - 从 InfluxDB 读取数据中心状态并训练预测模型

    参数:
        ctx: 应用上下文，包含 loggers、InfluxDB 客户端和 shutdown_event
    """
    logger = ctx.loggers["prediction_training"]
    logger.info("预测训练线程已启动")

    # 从配置中读取线程参数
    thread_config = ctx.main_config.get("threads", {}).get("prediction_training", {})
    mode = thread_config.get("mode", "fixed_interval")
    interval = thread_config.get("interval", 3600)
    error_retry_wait = thread_config.get("error_retry_wait", 60)

    logger.info(f"预测训练线程配置: mode={mode}, interval={interval}秒, error_retry_wait={error_retry_wait}秒")

    while not ctx.shutdown_event.is_set():
        loop_start_time = time.time()  # 记录循环开始时间

        try:
            # TODO: 实现预测训练逻辑
            # 1. 从 ctx.dc_status_client 读取数据中心状态数据
            # 2. 数据预处理
            # 3. 训练预测模型
            # 4. 保存模型
            #
            # ⚠️ 重要提醒 1：如果训练过程耗时很长（如模型训练），
            # 必须在训练循环中定期检查 ctx.shutdown_event.is_set()
            # 以便能够快速响应 Ctrl+C 退出信号。
            # 示例：
            #   for epoch in range(num_epochs):
            #       if ctx.shutdown_event.is_set():
            #           logger.info("检测到关闭信号，中断训练")
            #           break
            #       # 执行训练步骤...
            #
            # ⚠️ 重要提醒 2：对于关键操作（数据库写入、模型保存），
            # 必须使用 critical_operation 上下文管理器保护，确保这些操作不会被中断。
            # 示例：
            #   # 保护数据库写入操作
            #   with critical_operation(ctx):
            #       ctx.dc_status_client.write_points(training_metrics)
            #
            #   # 保护模型保存操作
            #   with critical_operation(ctx):
            #       model.save("checkpoint.pth")
            #
            # 注意：不要在长时间运行的任务（如整个训练循环）中使用 critical_operation，
            # 只在真正关键的操作（如数据库写入、模型保存）处使用。
            logger.info("预测训练线程运行中...")

            # 根据运行模式决定是否等待
            if mode == "fixed_interval":
                # 固定时间间隔模式
                elapsed_time = time.time() - loop_start_time
                remaining_time = interval - elapsed_time

                if remaining_time > 0:
                    # 如果执行时间 < interval，等待剩余时间
                    logger.info(f"预测训练完成，已用时 {elapsed_time:.2f}秒，等待 {remaining_time:.2f}秒后开始下一次训练")
                    if ctx.shutdown_event.wait(timeout=remaining_time):
                        break  # 收到关闭信号，退出循环
                else:
                    # 如果执行时间 >= interval，立即开始下一次循环
                    logger.info(f"预测训练完成，已用时 {elapsed_time:.2f}秒（超过间隔 {interval}秒），立即开始下一次训练")
                    # 检查是否有关闭信号
                    if ctx.shutdown_event.is_set():
                        break
            else:
                # 连续运行模式 - 立即开始下一次循环
                elapsed_time = time.time() - loop_start_time
                logger.info(f"预测训练完成，已用时 {elapsed_time:.2f}秒，立即开始下一次训练（连续模式）")
                # 检查是否有关闭信号
                if ctx.shutdown_event.is_set():
                    break

        except Exception as e:
            logger.error(f"预测训练线程出错: {e}", exc_info=True)
            if ctx.shutdown_event.wait(timeout=error_retry_wait):  # 出错后等待再重试
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

    # 从配置中读取线程参数
    thread_config = ctx.main_config.get("threads", {}).get("prediction_inference", {})
    mode = thread_config.get("mode", "fixed_interval")
    interval = thread_config.get("interval", 60)
    error_retry_wait = thread_config.get("error_retry_wait", 60)

    logger.info(f"预测推理线程配置: mode={mode}, interval={interval}秒, error_retry_wait={error_retry_wait}秒")

    while not ctx.shutdown_event.is_set():
        loop_start_time = time.time()  # 记录循环开始时间

        try:
            # TODO: 实现预测推理逻辑
            # 1. 从 ctx.dc_status_client 读取最新数据
            # 2. 加载预测模型
            # 3. 执行预测
            # 4. 将预测结果写入 ctx.prediction_client
            #
            # ⚠️ 重要提醒 1：如果推理过程耗时很长，
            # 必须在推理循环中定期检查 ctx.shutdown_event.is_set()
            # 以便能够快速响应 Ctrl+C 退出信号。
            # 示例：
            #   for batch in data_batches:
            #       if ctx.shutdown_event.is_set():
            #           logger.info("检测到关闭信号，中断推理")
            #           break
            #       # 执行推理步骤...
            #
            # ⚠️ 重要提醒 2：对于关键操作（数据库写入），
            # 必须使用 critical_operation 上下文管理器保护。
            # 示例：
            #   # 保护预测结果写入操作
            #   with critical_operation(ctx):
            #       ctx.prediction_client.write_points(prediction_results)
            logger.info("预测推理线程运行中...")

            # 根据运行模式决定是否等待
            if mode == "fixed_interval":
                # 固定时间间隔模式
                elapsed_time = time.time() - loop_start_time
                remaining_time = interval - elapsed_time

                if remaining_time > 0:
                    # 如果执行时间 < interval，等待剩余时间
                    logger.info(f"预测推理完成，已用时 {elapsed_time:.2f}秒，等待 {remaining_time:.2f}秒后开始下一次推理")
                    if ctx.shutdown_event.wait(timeout=remaining_time):
                        break  # 收到关闭信号，退出循环
                else:
                    # 如果执行时间 >= interval，立即开始下一次循环
                    logger.info(f"预测推理完成，已用时 {elapsed_time:.2f}秒（超过间隔 {interval}秒），立即开始下一次推理")
                    # 检查是否有关闭信号
                    if ctx.shutdown_event.is_set():
                        break
            else:
                # 连续运行模式 - 立即开始下一次循环
                elapsed_time = time.time() - loop_start_time
                logger.info(f"预测推理完成，已用时 {elapsed_time:.2f}秒，立即开始下一次推理（连续模式）")
                # 检查是否有关闭信号
                if ctx.shutdown_event.is_set():
                    break

        except Exception as e:
            logger.error(f"预测推理线程出错: {e}", exc_info=True)
            if ctx.shutdown_event.wait(timeout=error_retry_wait):  # 出错后等待再重试
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

    # 从配置中读取线程参数
    thread_config = ctx.main_config.get("threads", {}).get("optimization", {})
    mode = thread_config.get("mode", "fixed_interval")
    interval = thread_config.get("interval", 600)
    error_retry_wait = thread_config.get("error_retry_wait", 60)

    logger.info(f"优化线程配置: mode={mode}, interval={interval}秒, error_retry_wait={error_retry_wait}秒")

    while not ctx.shutdown_event.is_set():
        loop_start_time = time.time()  # 记录循环开始时间

        try:
            # TODO: 实现优化逻辑
            # 1. 从 ctx.prediction_client 读取预测数据
            # 2. 根据预测数据执行优化算法
            # 3. 生成控制指令
            # 4. 将控制指令写入 ctx.optimization_client
            # 5. 从 ctx.dc_status_client 读取状态数据，与环境不断交互进行强化学习
            # 6. 不断生成控制指令
            # 7. 不断将控制指令写入 ctx.optimization_client
            #
            # ⚠️ 重要提醒 1：如果优化过程耗时很长（如强化学习优化），
            # 必须在优化循环中定期检查 ctx.shutdown_event.is_set()
            # 以便能够快速响应 Ctrl+C 退出信号。
            # 示例：
            #   for step in range(max_steps):
            #       if ctx.shutdown_event.is_set():
            #           logger.info("检测到关闭信号，中断优化")
            #           break
            #       # 执行优化步骤...
            #       # 与环境交互...
            #
            # ⚠️ 重要提醒 2：对于关键操作（数据库写入、模型保存），
            # 必须使用 critical_operation 上下文管理器保护。
            # 示例：
            #   # 保护控制指令写入操作
            #   with critical_operation(ctx):
            #       ctx.optimization_client.write_points(control_commands)
            #
            #   # 保护强化学习模型保存操作
            #   with critical_operation(ctx):
            #       rl_agent.save("rl_checkpoint.pth")
            logger.info("优化线程运行中...")

            # 根据运行模式决定是否等待
            if mode == "fixed_interval":
                # 固定时间间隔模式
                elapsed_time = time.time() - loop_start_time
                remaining_time = interval - elapsed_time

                if remaining_time > 0:
                    # 如果执行时间 < interval，等待剩余时间
                    logger.info(f"优化完成，已用时 {elapsed_time:.2f}秒，等待 {remaining_time:.2f}秒后开始下一次优化")
                    if ctx.shutdown_event.wait(timeout=remaining_time):
                        break  # 收到关闭信号，退出循环
                else:
                    # 如果执行时间 >= interval，立即开始下一次循环
                    logger.info(f"优化完成，已用时 {elapsed_time:.2f}秒（超过间隔 {interval}秒），立即开始下一次优化")
                    # 检查是否有关闭信号
                    if ctx.shutdown_event.is_set():
                        break
            else:
                # 连续运行模式 - 立即开始下一次循环
                elapsed_time = time.time() - loop_start_time
                logger.info(f"优化完成，已用时 {elapsed_time:.2f}秒，立即开始下一次优化（连续模式）")
                # 检查是否有关闭信号
                if ctx.shutdown_event.is_set():
                    break

        except Exception as e:
            logger.error(f"优化线程出错: {e}", exc_info=True)
            if ctx.shutdown_event.wait(timeout=error_retry_wait):  # 出错后等待再重试
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

    # 读取关闭超时配置
    shutdown_timeout = main_config.get("shutdown", {}).get("timeout", 30)

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
        shutdown_event=shutdown_event,
        main_config=main_config
    )

    print("\n" + "=" * 60)
    print("初始化完成，启动多线程...")
    print("=" * 60)
    ctx.loggers["main"].info("系统初始化完成，准备启动多线程")

    # 4. 使用 ThreadPoolExecutor 管理线程
    executor = None
    future_prediction_training = None
    future_prediction_inference = None
    future_optimization = None

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
            time.sleep(3600)

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
            # 第一步：等待关键操作完成
            ctx.loggers["main"].info(f"等待关键操作完成（最多等待 {shutdown_timeout} 秒）...")
            print(f"等待关键操作完成（最多等待 {shutdown_timeout} 秒）...")

            # 使用 wait_for_critical_operations 等待所有关键操作完成
            all_completed = wait_for_critical_operations(ctx, timeout=shutdown_timeout)

            if all_completed:
                ctx.loggers["main"].info("✓ 所有关键操作已完成")
                print("✓ 所有关键操作已完成")
            else:
                ctx.loggers["main"].warning(f"⚠ 等待超时（{shutdown_timeout} 秒），仍有关键操作未完成，但继续关闭")
                print(f"⚠ 等待超时（{shutdown_timeout} 秒），仍有关键操作未完成，但继续关闭")

            # 第二步：等待工作线程退出
            ctx.loggers["main"].info("等待所有工作线程退出（最多等待 5 秒）...")
            print("等待所有工作线程退出（最多等待 5 秒）...")

            # 关闭线程池，取消未开始的任务
            # 注意：cancel_futures=True 只能取消尚未开始的任务
            # 对于正在运行的任务，需要线程函数内部定期检查 shutdown_event
            executor.shutdown(wait=False, cancel_futures=True)

            # 等待最多 5 秒让线程优雅退出
            try:
                # 尝试等待所有任务完成，最多等待 5 秒
                futures = [future_prediction_training, future_prediction_inference, future_optimization]
                for i, future in enumerate(futures):
                    if future is None:
                        continue
                    try:
                        future.result(timeout=5)
                    except FutureTimeoutError:
                        thread_names = ["预测训练", "预测推理", "优化"]
                        ctx.loggers["main"].warning(f"{thread_names[i]}线程在 5 秒内未能退出，强制继续")
                    except Exception as e:
                        thread_names = ["预测训练", "预测推理", "优化"]
                        ctx.loggers["main"].error(f"{thread_names[i]}线程退出时出错: {e}")

                ctx.loggers["main"].info("所有工作线程已退出")
                print("✓ 所有工作线程已退出")
            except Exception as e:
                ctx.loggers["main"].warning(f"等待线程退出时出错: {e}，继续清理资源")
                print(f"⚠ 部分线程可能未完全退出，继续清理资源")

        # 第三步：关闭 InfluxDB 连接
        print("正在关闭 InfluxDB 连接...")
        try:
            ctx.dc_status_client.close()
            ctx.prediction_client.close()
            ctx.optimization_client.close()
            ctx.loggers["influxdb"].info("InfluxDB 连接已关闭")
            print("✓ InfluxDB 连接已关闭")
        except Exception as e:
            ctx.loggers["influxdb"].error(f"关闭连接时出错: {e}")

        # 第四步：刷新所有日志
        ctx.loggers["main"].info("刷新所有日志...")
        for logger_name, logger in ctx.loggers.items():
            for handler in logger.handlers:
                try:
                    handler.flush()
                except Exception as e:
                    print(f"⚠ 刷新 {logger_name} 日志时出错: {e}")

        ctx.loggers["main"].info("系统已关闭")
        print("✓ 系统已关闭")


if __name__ == "__main__":
    main()
