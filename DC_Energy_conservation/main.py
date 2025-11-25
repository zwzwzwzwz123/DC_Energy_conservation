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
from typing import Dict, Any

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.initialization import init_multi_level_loggers, load_configs
from utils.influxdb_wrapper import init_influxdb_clients, InfluxDBClientWrapper
from utils.critical_operation import critical_operation, wait_for_critical_operations
from utils.architecture_config_parser import load_datacenter_from_config
from utils.data_read_write import create_data_reader, create_data_writer
from modules.architecture_module import DataCenter


@dataclass
class AppContext:
    """
    应用上下文类，封装所有全局状态

    属性:
        loggers: 所有日志器的字典
        dc_status_data_client: 数据中心状态数据客户端（读取可观测数据）
        prediction_data_client: 预测数据客户端（读写预测结果）
        optimization_data_client: 优化数据客户端（写入优化控制指令）
        shutdown_event: 关闭事件，用于优雅关闭线程

        # ========== 配置文件（全局只读） ==========
        main_config: 主配置字典，从 main_config.yaml 加载（线程参数、关闭超时等）
        uid_config: UID 配置字典，从 uid_config.yaml 加载（数据中心架构和UID映射）
        prediction_config: 预测模型配置字典，从 prediction_config.yaml 加载
        optimization_config: 优化模块配置字典，从 optimization_config.yaml 加载
        security_boundary_config: 安全边界配置字典，从 security_boundary_config.yaml 加载（控制范围、约束条件）
        utils_config: 工具配置字典，从 utils_config.yaml 加载（日志、InfluxDB连接配置）
        influxdb_read_write_config: InfluxDB读写配置字典，从 influxdb_read_write_config.yaml 加载（数据读写策略）

        # ========== 运行时状态 ==========
        critical_operation_lock: 保护关键操作计数器的锁
        critical_operation_count: 当前正在执行的关键操作数量
        datacenter: 数据中心对象（包含完整的层次结构）
        data_reader: 数据读取器（支持多客户端读取，使用 read_influxdb_data(client_key, config_key) 方法）
        data_writer: 数据写入器（支持多客户端写入，使用 write_influxdb_data(client_key, config_key, data) 方法）

    注意:
        - logging 模块本身是线程安全的，多个线程可以安全地使用同一个 logger
        - InfluxDBClientWrapper 的操作也是线程安全的（底层使用 requests 库）
        - shutdown_event 用于通知所有线程优雅退出
        - critical_operation_lock 和 critical_operation_count 用于保护关键操作（数据库写入、模型保存）
        - 所有配置文件在程序启动时加载，运行期间只读，天然线程安全
        - datacenter, data_reader, data_writer 是数据中心架构组件
        - data_reader 和 data_writer 现在支持多客户端架构，可以灵活选择不同的数据库进行读写
    """
    # 日志和客户端
    loggers: Dict[str, logging.Logger]
    dc_status_data_client: InfluxDBClientWrapper
    prediction_data_client: InfluxDBClientWrapper
    optimization_data_client: InfluxDBClientWrapper
    shutdown_event: Event

    # ========== 所有配置文件（全局只读） ==========
    main_config: Dict
    uid_config: Dict
    prediction_config: Dict
    optimization_config: Dict
    security_boundary_config: Dict
    utils_config: Dict
    influxdb_read_write_config: Dict

    # ========== 运行时状态 ==========
    critical_operation_lock: Lock = field(default_factory=Lock)
    critical_operation_count: int = 0
    datacenter: DataCenter = None
    data_reader: Any = None
    data_writer: Any = None


def validate_data_and_wait_on_error_retry(data, data_type, error_retry_wait, shutdown_event, logger):
    """
    验证数据有效性，如果数据无效则等待并返回控制标志

    参数:
        data: Dict[str, pd.DataFrame] - 要验证的数据字典
        data_type: str - 数据类型描述（用于日志，如"状态数据"、"预测结果"）
        error_retry_wait: int - 错误重试等待时间（秒）
        shutdown_event: Event - 关闭事件
        logger: Logger - 日志器

    返回:
        Tuple[bool, bool] - (should_continue, should_break)
            - should_continue=True: 数据无效，调用者应该 continue
            - should_break=True: 收到关闭信号，调用者应该 break
            - (False, False): 数据有效，调用者应该继续执行
    """
    # 检查数据是否为空
    if not data:
        logger.warning(f"没有读取到任何{data_type}，跳过本次训练")
        logger.info(f"等待 {error_retry_wait}秒后开始下一次训练")
        if shutdown_event.wait(timeout=error_retry_wait):
            return False, True  # should_break=True
        return True, False  # should_continue=True

    # 检查数据质量（检查是否有空的 DataFrame）
    valid_data_count = sum(1 for df in data.values() if not df.empty)
    logger.info(f"有效数据点数量: {valid_data_count}/{len(data)}")

    if valid_data_count == 0:
        logger.warning(f"读取到{data_type}，但所有{data_type}均无效 (例如均为空DataFrame)，跳过本次训练")
        logger.info(f"等待 {error_retry_wait}秒后开始下一次训练")
        if shutdown_event.wait(timeout=error_retry_wait):
            return False, True  # should_break=True
        return True, False  # should_continue=True

    # 数据有效
    return False, False


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
            # ==================== 数据读取阶段 ====================
            # 使用 DataCenterDataReader 读取数据中心状态数据
            logger.info("开始读取训练数据...")
            try:
                # 使用配置驱动方式读取所有可观测数据
                # 客户端键 "dc_status_data_client" 和配置键 "datacenter_latest_status" 定义在 influxdb_read_write_config.yaml 中
                observable_data = ctx.data_reader.read_influxdb_data("dc_status_data_client", "datacenter_latest_status")
                logger.info(f"成功读取 {len(observable_data)} 个可观测点的数据")

                # 数据验证
                should_continue, should_break = validate_data_and_wait_on_error_retry(
                    observable_data, "状态数据", error_retry_wait, ctx.shutdown_event, logger
                )
                if should_break:
                    break
                if should_continue:
                    continue

            except Exception as e:
                logger.error(f"读取训练数据失败: {e}，等待 {error_retry_wait}秒后开始下一次训练", exc_info=True)
                # 出错后等待再重试
                if ctx.shutdown_event.wait(timeout=error_retry_wait):
                    break
                continue

            # ==================== 数据预处理阶段 ====================
            # TODO: 实现数据预处理逻辑
            # 将 observable_data (Dict[str, pd.DataFrame]) 转换为训练所需的格式
            # 示例：
            #   training_features, training_labels = preprocess_data(observable_data)
            logger.info("数据预处理中...")

            # ==================== 模型训练阶段 ====================
            # TODO: 实现预测模型训练逻辑
            # ⚠️ 重要提醒 1：如果训练过程耗时很长（如模型训练），
            # 必须在训练循环中定期检查 ctx.shutdown_event.is_set()
            # 以便能够快速响应 Ctrl+C 退出信号。
            # 示例：
            #   for epoch in range(num_epochs):
            #       if ctx.shutdown_event.is_set():
            #           logger.info("检测到关闭信号，中断训练")
            #           break
            #       # 执行训练步骤...
            logger.info("模型训练中...")

            # ==================== 模型保存阶段 ====================
            # TODO: 实现模型保存逻辑
            # ⚠️ 重要提醒 2：对于关键操作（模型保存），
            # 必须使用 critical_operation 上下文管理器保护，确保这些操作不会被中断。
            # 示例：
            #   # 保护模型保存操作
            #   with critical_operation(ctx):
            #       model.save("checkpoint.pth")
            logger.info("预测训练完成")

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
            logger.error(f"预测训练线程出错: {e}，等待 {error_retry_wait}秒后开始下一次训练", exc_info=True)
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
            # ==================== 数据读取阶段 ====================
            # 使用 DataCenterDataReader 读取最新数据
            logger.info("开始读取推理数据...")
            try:
                # 使用配置驱动方式读取所有可观测数据
                # 客户端键 "dc_status_data_client" 和配置键 "datacenter_latest_status" 定义在 influxdb_read_write_config.yaml 中
                observable_data = ctx.data_reader.read_influxdb_data("dc_status_data_client", "datacenter_latest_status")
                logger.info(f"成功读取 {len(observable_data)} 个可观测点的数据")

                # 数据验证
                should_continue, should_break = validate_data_and_wait_on_error_retry(
                    observable_data, "状态数据", error_retry_wait, ctx.shutdown_event, logger
                )
                if should_break:
                    break
                if should_continue:
                    continue

            except Exception as e:
                logger.error(f"读取推理数据失败: {e}，等待 {error_retry_wait}秒后开始下一次训练", exc_info=True)
                if ctx.shutdown_event.wait(timeout=error_retry_wait):
                    break
                continue

            # ==================== 模型加载阶段 ====================
            # TODO: 实现预测模型加载逻辑
            # 示例：
            #   model = load_prediction_model("checkpoint.pth")
            logger.info("加载预测模型...")

            # ==================== 预测推理阶段 ====================
            # TODO: 实现预测推理逻辑
            # ⚠️ 重要提醒：如果推理过程耗时很长，
            # 必须在推理循环中定期检查 ctx.shutdown_event.is_set()
            # 示例：
            #   for batch in data_batches:
            #       if ctx.shutdown_event.is_set():
            #           logger.info("检测到关闭信号，中断推理")
            #           break
            #       # 执行推理步骤...
            logger.info("执行预测推理...")

            # ==================== 预测结果写入阶段 ====================
            logger.info("开始写入预测结果...")
            try:
                # 示例 1: 预测数据 - 按测点分离存储
                prediction_data_separate = {
                    'sensor_temp_A1': 25.5,
                    'sensor_temp_B2': 26.1
                }
                success1 = ctx.data_writer.write_influxdb_data(
                    'prediction_data_client',
                    'prediction_by_uid',
                    prediction_data_separate,
                    horizon='15mins'
                )
                if success1: logger.info("按测点分离存储预测数据写入成功")

                # 示例 2: 预测数据 - 统一存储格式
                prediction_data_unified = {
                    'sensor_temp_A1': '{"value": 25.5, "confidence": 0.95}',
                    'sensor_temp_B2': '{"value": 26.1, "confidence": 0.93}'
                }
                success2 = ctx.data_writer.write_influxdb_data(
                    'prediction_data_client',
                    'prediction_unified',
                    prediction_data_unified,
                    horizon='1h'
                )
                if success2: logger.info("统一存储格式预测数据写入成功")

            except Exception as e:
                logger.error(f"写入预测结果失败: {e}", exc_info=True)

            logger.info("预测推理完成")

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
            logger.error(f"预测推理线程出错: {e}，等待 {error_retry_wait}秒后开始下一次推理", exc_info=True)
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
            # ==================== 数据读取阶段 ====================
            # 1. 读取预测数据（从 prediction_data_client）
            logger.info("开始读取预测结果...")
            try:
                # 使用配置驱动方式读取最新预测数据
                # 客户端键 "prediction_data_client" 和配置键 "latest_predictions" 定义在 influxdb_read_write_config.yaml 中
                prediction_data = ctx.data_reader.read_influxdb_data("prediction_data_client", "latest_predictions")
                logger.info(f"成功读取 {len(prediction_data)} 个预测点的数据")

                # 数据验证
                should_continue, should_break = validate_data_and_wait_on_error_retry(
                    prediction_data, "预测结果", error_retry_wait, ctx.shutdown_event, logger
                )
                if should_break:
                    break
                if should_continue:
                    continue

            except Exception as e:
                logger.error(f"读取预测结果失败: {e}，等待 {error_retry_wait}秒后开始下一次训练", exc_info=True)
                if ctx.shutdown_event.wait(timeout=error_retry_wait):
                    break
                continue


            # 2. 读取当前状态数据（从 dc_status_data_client）
            logger.info("开始读取状态数据...")
            try:
                # 使用配置驱动方式读取最新状态数据
                # 客户端键 "dc_status_data_client" 和配置键 "datacenter_latest_status" 定义在 influxdb_read_write_config.yaml 中
                observable_data = ctx.data_reader.read_influxdb_data("dc_status_data_client", "datacenter_latest_status")
                logger.info(f"成功读取 {len(observable_data)} 个可观测点的数据")

                # 数据验证
                should_continue, should_break = validate_data_and_wait_on_error_retry(
                    observable_data, "状态数据", error_retry_wait, ctx.shutdown_event, logger
                )
                if should_break:
                    break
                if should_continue:
                    continue

            except Exception as e:
                logger.error(f"读取状态数据失败: {e}，等待 {error_retry_wait}秒后开始下一次训练", exc_info=True)
                if ctx.shutdown_event.wait(timeout=error_retry_wait):
                    break
                continue

            # ==================== 优化算法阶段 ====================
            # TODO: 实现优化算法逻辑
            # 根据预测数据和当前状态数据执行优化算法
            # ⚠️ 重要提醒：如果优化过程耗时很长（如强化学习优化），
            # 必须在优化循环中定期检查 ctx.shutdown_event.is_set()
            # 示例：
            #   for step in range(max_steps):
            #       if ctx.shutdown_event.is_set():
            #           logger.info("检测到关闭信号，中断优化")
            #           break
            #       # 执行优化步骤...
            #       # 与环境交互...
            logger.info("执行优化算法...")

            # ==================== 控制指令写入阶段 ====================
            logger.info("开始写入控制指令...")
            try:
                # 示例 3: 优化指令 - 按测点分离存储
                optimization_data_separate = {
                    'ac_a1_001_supply_temp_setpoint': 24.0,
                    'ac_a1_002_supply_temp_setpoint': 24.5
                }
                success3 = ctx.data_writer.write_influxdb_data(
                    'optimization_data_client',
                    'optimization_by_uid',
                    optimization_data_separate,
                    is_auto_execute=False
                )
                if success3: logger.info("按测点分离存储优化指令写入成功")

                # 示例 4: 优化指令 - 统一存储格式
                optimization_data_unified = {
                    'ac_a1_001_supply_temp_setpoint': '{"value": 24.0, "priority": "high"}',
                    'ac_a1_002_supply_temp_setpoint': '{"value": 24.5, "priority": "medium"}'
                }
                success4 = ctx.data_writer.write_influxdb_data(
                    'optimization_data_client',
                    'optimization_unified',
                    optimization_data_unified,
                    is_auto_execute=True
                )
                if success4: logger.info("统一存储格式优化指令写入成功")

            except Exception as e:
                logger.error(f"写入控制指令失败: {e}", exc_info=True)

            # ==================== 模型保存阶段（可选）====================
            # TODO: 如果使用强化学习，定期保存模型
            # ⚠️ 重要：对于模型保存操作，必须使用 critical_operation 保护
            # 示例：
            #   with critical_operation(ctx):
            #       rl_agent.save("rl_checkpoint.pth")

            logger.info("优化完成")

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
            logger.error(f"优化线程出错: {e}，等待 {error_retry_wait}秒后开始下一次优化", exc_info=True)
            if ctx.shutdown_event.wait(timeout=error_retry_wait):  # 出错后等待再重试
                break

    logger.info("优化线程已退出")


def initialize_system():
    """
    系统初始化函数 - 完成所有启动前的准备工作

    返回:
        AppContext: 包含所有初始化组件的应用上下文对象

    异常:
        如果初始化失败，会调用 sys.exit(1) 退出程序
    """
    print("=" * 60)
    print("数据中心节能项目启动中...")
    print("=" * 60)

    # 1. 加载配置文件
    print("\n[1/7] 加载配置文件...")
    main_config, prediction_config, optimization_config, security_boundary_config, uid_config, utils_config, influxdb_read_write_config = load_configs()
    print("✓ 配置文件加载成功")

    # 2. 初始化多层级日志系统
    print("\n[2/7] 初始化多层级日志系统...")
    try:
        loggers = init_multi_level_loggers(utils_config["logging"])
        print("✓ 多层级日志系统初始化成功")
        print(f"  - 全局日志: total_log.log")
        print(f"  - 主程序日志: main_log.log")
        print(f"  - InfluxDB日志: influxdb_log.log")
        print(f"  - 预测训练日志: prediction_training_log.log")
        print(f"  - 预测推理日志: prediction_inference_log.log")
        print(f"  - 优化日志: optimization_log.log")
        print(f"  - 架构解析器日志: architecture_parser_log.log")

        # 使用 main logger 记录主程序日志
        loggers["main"].info("数据中心节能项目启动")
    except Exception as e:
        print(f"✗ 日志系统初始化失败: {e}")
        sys.exit(1)

    # 3. 初始化 InfluxDB 客户端
    print("\n[3/7] 初始化 InfluxDB 客户端...")
    try:
        # 传入 influxdb logger，使 InfluxDB 相关日志自动写入 influxdb_log.log 和 total_log.log
        dc_status_data_client, prediction_data_client, optimization_data_client = init_influxdb_clients(
            utils_config, loggers["influxdb"]
        )
        # 使用 influxdb logger 记录 InfluxDB 相关日志
        loggers["main"].info("InfluxDB 客户端全部初始化成功")
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

    # 4. 加载数据中心配置
    print("\n[4/7] 加载数据中心配置...")
    try:
        datacenter = load_datacenter_from_config(uid_config, loggers["architecture_parser"])

        # 输出数据中心统计信息
        stats = datacenter.get_statistics()
        loggers["main"].info(f"数据中心配置加载成功: {datacenter.dc_name}")
        print(f"✓ 数据中心配置加载成功: {datacenter.dc_name}")
        print(f"  - 机房总数: {stats['total_rooms']}")
        print(f"  - 风冷系统总数: {stats['total_air_cooled_systems']}")
        print(f"  - 水冷系统总数: {stats['total_water_cooled_systems']}")
        print(f"  - 设备总数: {stats['total_devices']}")
        print(f"  - 可观测点总数: {stats['total_observable_points']}")
        print(f"  - 控制点总数: {stats['total_regulable_points']}")

        loggers["main"].info(f"  - 机房总数: {stats['total_rooms']}")
        loggers["main"].info(f"  - 风冷系统总数: {stats['total_air_cooled_systems']}")
        loggers["main"].info(f"  - 水冷系统总数: {stats['total_water_cooled_systems']}")
        loggers["main"].info(f"  - 设备总数: {stats['total_devices']}")
        loggers["main"].info(f"  - 可观测点总数: {stats['total_observable_points']}")
        loggers["main"].info(f"  - 控制点总数: {stats['total_regulable_points']}")
    except Exception as e:
        loggers["main"].error(f"数据中心配置加载失败: {e}", exc_info=True)
        print(f"✗ 数据中心配置加载失败: {e}")
        sys.exit(1)

    # 5. 创建数据读取器
    print("\n[5/7] 创建数据读取器...")
    try:
        # 构建客户端字典
        reader_clients = {
            'dc_status_data_client': dc_status_data_client,
            'prediction_data_client': prediction_data_client
        }

        data_reader = create_data_reader(
            datacenter=datacenter,
            read_write_config=influxdb_read_write_config,
            influxdb_clients=reader_clients,
            logger=loggers["influxdb"]
        )
        loggers["main"].info("数据读取器创建成功")
        print("✓ 数据读取器创建成功")
    except Exception as e:
        loggers["main"].error(f"数据读取器创建失败: {e}", exc_info=True)
        print(f"✗ 数据读取器创建失败: {e}")
        sys.exit(1)

    # 6. 创建应用上下文（只创建一次！）
    print("\n[6/7] 创建应用上下文...")
    shutdown_event = Event()
    try:
        ctx = AppContext(
            loggers=loggers,
            dc_status_data_client=dc_status_data_client,
            prediction_data_client=prediction_data_client,
            optimization_data_client=optimization_data_client,
            shutdown_event=shutdown_event,

            # ========== 所有配置文件 ==========
            main_config=main_config,
            uid_config=uid_config,
            prediction_config=prediction_config,
            optimization_config=optimization_config,
            security_boundary_config=security_boundary_config,
            utils_config=utils_config,
            influxdb_read_write_config=influxdb_read_write_config,

            datacenter=datacenter,
            data_reader=data_reader
            # 注意：此时 data_writer 还是 None，将在下一步创建并赋值
        )
        loggers["main"].info("应用上下文创建成功")
        print("✓ 应用上下文创建成功")
    except Exception as e:
        loggers["main"].error(f"应用上下文创建失败: {e}", exc_info=True)
        print(f"✗ 应用上下文创建失败: {e}")
        sys.exit(1)

    # 7. 创建数据写入器并更新到上下文
    print("\n[7/7] 创建数据写入器...")
    try:
        writer_clients = {
            'prediction_data_client': prediction_data_client,
            'optimization_data_client': optimization_data_client
        }
        data_writer = create_data_writer(
            datacenter=datacenter,
            read_write_config=influxdb_read_write_config,
            influxdb_clients=writer_clients,
            ctx=ctx,  # 传入唯一的 ctx 实例
            logger=loggers["influxdb"]
        )

        # 将创建好的 data_writer 赋值回唯一的 ctx 实例
        ctx.data_writer = data_writer

        loggers["main"].info("数据写入器创建成功并更新到上下文")
        print("✓ 数据写入器创建成功")
    except Exception as e:
        loggers["main"].error(f"数据写入器创建失败: {e}", exc_info=True)
        print(f"✗ 数据写入器创建失败: {e}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("初始化完成，启动多线程...")
    print("=" * 60)
    ctx.loggers["main"].info("系统初始化完成，准备启动多线程")

    return ctx


def main():
    """
    主函数 - 多线程架构
    """
    # 1. 初始化系统
    ctx = initialize_system()

    # 读取关闭超时配置
    shutdown_timeout = ctx.main_config.get("shutdown", {}).get("timeout", 30)

    # 2. 使用 ThreadPoolExecutor 管理线程
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
        # 使用 shutdown_event.wait() 代替 while True: time.sleep(3600)
        ctx.shutdown_event.wait()

    except KeyboardInterrupt:
        ctx.loggers["main"].info("接收到中断信号，开始关闭系统...")
        print("\n接收到退出信号，正在关闭系统...")

        # 设置关闭事件，通知所有线程退出
        ctx.shutdown_event.set()
        ctx.loggers["main"].info("已发送关闭信号到所有工作线程")

    except Exception as e:
        ctx.loggers["main"].error(f"程序运行出错: {e}", exc_info=True)
        print(f"\n程序运行出错: {e}")
        ctx.shutdown_event.set()  # 确保线程能够退出

    # 9. 清理资源，退出系统
    finally:
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
            ctx.dc_status_data_client.close()
            ctx.prediction_data_client.close()
            ctx.optimization_data_client.close()
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
