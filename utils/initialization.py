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


def load_configs() -> Tuple[Dict, Dict, Dict, Dict, Dict, Dict]:
    """
    加载所有配置文件

    返回:
        Tuple[Dict, Dict, Dict, Dict, Dict, Dict]:
            (main_config, models_config, modules_config, utils_config,
             security_boundary_config, uid_config)
            - main_config: main.py 配置（从 main.yaml 加载）
            - models_config: 模型配置（从 models.yaml 加载）
            - modules_config: 模块配置（从 modules.yaml 加载）
            - security_boundary_config: 安全边界配置（从 security_boundary_config.yaml 加载）
            - uid_config: UID 配置（从 uid_config.yaml 加载）
            - utils_config: 工具配置，包含 InfluxDB 和日志配置（从 utils.yaml 加载）

    异常:
        FileNotFoundError: 配置文件未找到
        yaml.YAMLError: 配置文件格式错误
        Exception: 其他加载错误
    """
    # 获取项目根目录（utils 的父目录）
    project_root = Path(__file__).parent.parent
    config_dir = project_root / "configs"

    try:
        # 加载 main.yaml
        with open(config_dir / "main.yaml", "r", encoding="utf-8") as f:
            main_config = yaml.safe_load(f) or {}

        # 加载 models.yaml
        with open(config_dir / "models.yaml", "r", encoding="utf-8") as f:
            models_config = yaml.safe_load(f) or {}

        # 加载 modules.yaml
        with open(config_dir / "modules.yaml", "r", encoding="utf-8") as f:
            modules_config = yaml.safe_load(f) or {}

        # 加载 security_boundary_config.yaml
        with open(config_dir / "security_boundary_config.yaml", "r", encoding="utf-8") as f:
            security_boundary_config = yaml.safe_load(f) or {}

        # 加载 uid_config.yaml
        with open(config_dir / "uid_config.yaml", "r", encoding="utf-8") as f:
            uid_config = yaml.safe_load(f) or {}

        # 加载 utils.yaml（包含 InfluxDB 和日志配置）
        with open(config_dir / "utils.yaml", "r", encoding="utf-8") as f:
            utils_config = yaml.safe_load(f) or {}

        return main_config, models_config, modules_config, security_boundary_config, uid_config, utils_config

    except FileNotFoundError as e:
        raise FileNotFoundError(f"配置文件未找到: {e}")
    except yaml.YAMLError as e:
        raise yaml.YAMLError(f"配置文件格式错误: {e}")
    except Exception as e:
        raise Exception(f"加载配置文件失败: {e}")


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
        log_config: 日志配置字典，从 utils.yaml 读取
                   包含以下键:
                   - console_output: 是否输出到控制台 (true/false)
                   - rotation_when: 日志轮转时间单位 (midnight, H, D, W0-W6)
                   - rotation_interval: 日志轮转间隔
                   - backup_count: 保留的备份文件数量

    返回:
        Dict[str, logging.Logger]: 包含所有日志器的字典
            {
                "total": 根日志器（记录所有日志）,
                "main": main.py 日志器,
                "influxdb": influxdb_wrapper.py 日志器,
                "prediction_training": 预测训练线程日志器,
                "prediction_inference": 预测推理线程日志器,
                "optimization": 优化线程日志器
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
        # 获取配置参数
        log_dir = "./logs"
        console_output = log_config.get("console_output", True)
        rotation_when = log_config.get("rotation_when", "midnight")
        rotation_interval = log_config.get("rotation_interval", 1)
        backup_count = log_config.get("backup_count", 7)

        # 创建日志目录
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)

        # 定义日志器配置：{简化名称: (完整logger名称, 日志文件名)}
        logger_configs = {
            "total": ("log_total_running", "total_running_log.log"),
            "main": ("log_main", "main_log.log"),
            "influxdb": ("log_influxdb", "influxdb_log.log"),
            "prediction_training": ("log_prediction_training", "prediction_training_log.log"),
            "prediction_inference": ("log_prediction_inference", "prediction_inference_log.log"),
            "optimization": ("log_optimization", "optimization_log.log")
        }

        # 日志格式：包含时间、logger名称、级别、消息
        log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        date_format = "%Y-%m-%d %H:%M:%S"
        formatter = logging.Formatter(log_format, datefmt=date_format)

        # 存储所有日志器
        loggers = {}

        # 创建根日志器（total_running_log）
        root_logger_name, root_log_file = logger_configs["total"]
        root_logger = logging.getLogger(root_logger_name)

        # 避免重复初始化
        if not root_logger.handlers:
            root_logger.setLevel(logging.DEBUG)  # 收集所有级别的日志
            root_logger.propagate = False  # 根日志器不向上传播

            # 根日志器添加控制台处理器（避免重复输出，只在根日志器添加）
            if console_output:
                console_handler = logging.StreamHandler()
                console_handler.setLevel(logging.INFO)  # 控制台只显示 INFO 及以上级别
                console_handler.setFormatter(formatter)
                root_logger.addHandler(console_handler)

            # 根日志器添加文件处理器
            root_file_handler = TimedRotatingFileHandler(
                filename=str(log_path / root_log_file),
                encoding="utf-8",
                when=rotation_when,
                interval=rotation_interval,
                backupCount=backup_count
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

            # 避免重复初始化
            if not child_logger.handlers:
                child_logger.setLevel(logging.DEBUG)  # 收集所有级别的日志
                child_logger.propagate = True  # 子日志器向父日志器传播（关键设置）

                # 子日志器只添加文件处理器（不添加控制台处理器，避免重复输出）
                child_file_handler = TimedRotatingFileHandler(
                    filename=str(log_path / log_file),
                    encoding="utf-8",
                    when=rotation_when,
                    interval=rotation_interval,
                    backupCount=backup_count
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
            root_logger.info(f"  - {key:25s} -> {log_file}")
        root_logger.info("=" * 80)

        return loggers

    except OSError as e:
        raise OSError(f"日志目录创建失败: {e}")
    except Exception as e:
        raise Exception(f"多层级日志系统初始化失败: {e}")
