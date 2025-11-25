"""
初始化模块
提供 config 文件加载和日志系统的初始化功能
"""

import logging
from logging.handlers import TimedRotatingFileHandler
import os
import sys
import yaml
from pathlib import Path
from typing import Dict, Tuple


def load_configs() -> Tuple[Dict, Dict, Dict, Dict, Dict, Dict, Dict]:
    """
    Load all config files.

    Returns:
        (main_config, prediction_config, optimization_config, security_boundary_config,
         uid_config, utils_config, influxdb_read_write_config)
    """
    project_root = Path(__file__).parent.parent
    config_dir = project_root / "configs"

    with open(config_dir / "main_config.yaml", "r", encoding="utf-8") as f:
        main_config = yaml.safe_load(f) or {}

    with open(config_dir / "prediction_config.yaml", "r", encoding="utf-8") as f:
        prediction_config = yaml.safe_load(f) or {}

    with open(config_dir / "optimization_config.yaml", "r", encoding="utf-8") as f:
        optimization_config = yaml.safe_load(f) or {}

    with open(config_dir / "security_boundary_config.yaml", "r", encoding="utf-8") as f:
        security_boundary_config = yaml.safe_load(f) or {}

    with open(config_dir / "uid_config.yaml", "r", encoding="utf-8") as f:
        uid_config = yaml.safe_load(f) or {}

    with open(config_dir / "utils_config.yaml", "r", encoding="utf-8") as f:
        utils_config = yaml.safe_load(f) or {}

    with open(config_dir / "influxdb_read_write_config.yaml", "r", encoding="utf-8") as f:
        influxdb_read_write_config = yaml.safe_load(f) or {}

    return (
        main_config,
        prediction_config,
        optimization_config,
        security_boundary_config,
        uid_config,
        utils_config,
        influxdb_read_write_config,
    )

def init_multi_level_loggers(log_config: Dict) -> Dict[str, logging.Logger]:
    """
    初始化多层级日志系统

    创建一个根日志器和5个子日志器，形成层级结构：
    - 根日志器（total_running_log）：捕获所有模块的日志
    - 子日志器：各自记录对应模块的日志，同时自动传播到根日志器

    优势：
    - 只需调用一次 logger.info()，日志会自动写入模块日志和全局日志
    - 避免重复代码：logger_total.info() 和 logger_module.info()
    - 线程安全：logging 模块本身是线程安全的

    参数:
        log_config: 日志配置字典，从 utils_config.yaml 读取
                   包含以下键:
                   - default: 默认配置字典
                     - console_output: 是否输出到控制台 (true/false)
                     - rotation_when: 日志轮转时间单位 (midnight, H, D, W0-W6)
                     - rotation_interval: 日志轮转间隔
                     - backup_count: 保留的备份文件数量
                   - loggers: 各日志器的独立配置（可选）
                     - 键为日志器名称（如 "total", "main"）
                     - 值为该日志器的配置字典，用于覆盖默认配置

    返回:
        Dict[str, logging.Logger]: 包含所有日志器的字典
            {
                "total": 根日志器（记录所有日志）,
                "main": main.py 日志器,
                "influxdb": influxdb_wrapper.py 日志器,
                "prediction_training": 预测训练线程日志器,
                "prediction_inference": 预测推理线程日志器,
                "optimization": 优化线程日志器,
                "architecture_parser": 架构解析器日志器
            }

    使用示例:
        # 在 main.py 中初始化
        loggers = init_multi_level_loggers(utils_config["logging"])

        # 在各个模块中使用
        loggers["main"].info("主程序启动")  # 同时写入 main_log.log 和 total_running_log.log
        loggers["optimization"].info("优化完成")  # 同时写入 optimization_log.log 和 total_running_log.log

    异常:
        OSError: 日志目录创建失败
        Exception: 日志系统初始化失败
    """
    try:
        # 获取默认配置
        default_config = log_config.get("default", {})

        # 获取日志位置并创建目录
        project_root = Path(__file__).parent.parent
        log_path = project_root / "logs"
        log_path.mkdir(parents=True, exist_ok=True)

        default_console_output = default_config.get("console_output", True)
        default_rotation_when = default_config.get("rotation_when", "midnight")
        default_rotation_interval = default_config.get("rotation_interval", 1)
        default_backup_count = default_config.get("backup_count", 7)

        # 获取各日志器的独立配置
        loggers_config = log_config.get("loggers", {})

        # 定义日志器配置：{简化名称: (完整logger名称, 日志文件名)}
        logger_configs = {
            "total": ("log_total", "total_log.log"),
            "main": ("log_total.main", "main_log.log"),
            "influxdb": ("log_total.influxdb", "influxdb_log.log"),
            "prediction_training": ("log_total.prediction_training", "prediction_training_log.log"),
            "prediction_inference": ("log_total.prediction_inference", "prediction_inference_log.log"),
            "optimization": ("log_total.optimization", "optimization_log.log"),
            "architecture_parser": ("log_total.architecture_parser", "architecture_parser_log.log")
        }

        # 日志格式：包含时间、logger名称、级别、消息
        log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        date_format = "%Y-%m-%d %H:%M:%S"
        formatter = logging.Formatter(log_format, datefmt=date_format)

        # 存储所有日志器
        loggers = {}

        # 创建根日志器（total_log）
        root_logger_name, root_log_file = logger_configs["total"]
        root_logger = logging.getLogger(root_logger_name)

        # 获取根日志器的配置（如果有独立配置则使用，否则使用默认配置）
        root_config = loggers_config.get("total", {})
        root_console_output = root_config.get("console_output", default_console_output)
        root_rotation_when = root_config.get("rotation_when", default_rotation_when)
        root_rotation_interval = root_config.get("rotation_interval", default_rotation_interval)
        root_backup_count = root_config.get("backup_count", default_backup_count)

        # 避免重复初始化
        if not root_logger.handlers:
            root_logger.setLevel(logging.DEBUG)  # 收集所有级别的日志
            root_logger.propagate = False  # 根日志器不向上传播

            # 根日志器添加控制台处理器（避免重复输出，只在根日志器添加）
            if root_console_output:
                console_handler = logging.StreamHandler()
                console_handler.setLevel(logging.INFO)  # 控制台只显示 INFO 及以上级别
                console_handler.setFormatter(formatter)
                root_logger.addHandler(console_handler)

            # 根日志器添加文件处理器
            root_file_handler = TimedRotatingFileHandler(
                filename=str(log_path / root_log_file),
                encoding="utf-8",
                when=root_rotation_when,
                interval=root_rotation_interval,
                backupCount=root_backup_count
            )
            root_file_handler.setLevel(logging.DEBUG)  # 文件记录所有级别
            root_file_handler.setFormatter(formatter)
            root_logger.addHandler(root_file_handler)

        loggers["total"] = root_logger

        # 创建子日志器（main, influxdb, prediction_training, prediction_inference, optimization）
        for key, (logger_name, log_file) in logger_configs.items():
            if key == "total":
                continue  # 跳过根日志器

            child_logger = logging.getLogger(logger_name)

            # 获取该日志器的配置（如果有独立配置则使用，否则使用默认配置）
            child_config = loggers_config.get(key, {})
            child_rotation_when = child_config.get("rotation_when", default_rotation_when)
            child_rotation_interval = child_config.get("rotation_interval", default_rotation_interval)
            child_backup_count = child_config.get("backup_count", default_backup_count)

            # 避免重复初始化
            if not child_logger.handlers:
                child_logger.setLevel(logging.DEBUG)  # 收集所有级别的日志
                child_logger.propagate = True  # 子日志器向父日志器传播（关键设置）

                # 子日志器只添加文件处理器（不添加控制台处理器，避免重复输出）
                child_file_handler = TimedRotatingFileHandler(
                    filename=str(log_path / log_file),
                    encoding="utf-8",
                    when=child_rotation_when,
                    interval=child_rotation_interval,
                    backupCount=child_backup_count
                )
                child_file_handler.setLevel(logging.DEBUG)  # 文件记录所有级别
                child_file_handler.setFormatter(formatter)
                child_logger.addHandler(child_file_handler)

            loggers[key] = child_logger

        # 记录初始化成功信息
        root_logger.info("=" * 80)
        root_logger.info("多层级日志系统初始化成功")
        root_logger.info("日志文件列表:")
        for key, (_, log_file) in logger_configs.items():
            # 获取该日志器的实际配置
            if key == "total":
                actual_backup = root_backup_count
            else:
                child_config = loggers_config.get(key, {})
                actual_backup = child_config.get("backup_count", default_backup_count)
            root_logger.info(f"  - {key:25s} -> {log_file:30s} (保留 {actual_backup} 天)")
        root_logger.info("=" * 80)

        return loggers

    except OSError as e:
        raise OSError(f"日志目录创建失败: {e}")
    except Exception as e:
        raise Exception(f"多层级日志系统初始化失败: {e}")
