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


def init_logger(log_config: Dict) -> logging.Logger:
    """
    初始化日志系统

    参数:
        log_config: 日志配置字典，从 utils.yaml 读取
                   包含以下键:
                   - logger_name: 日志器名称
                   - log_level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
                   - log_dir: 日志目录路径（相对于项目根目录）
                   - log_filename: 日志文件名
                   - console_output: 是否输出到控制台 (true/false)
                   - console_level: 控制台日志级别
                   - file_level: 文件日志级别
                   - log_format: 日志格式字符串
                   - date_format: 日期格式字符串
                   - rotation_when: 日志轮转时间单位 (midnight, H, D, W0-W6)
                   - rotation_interval: 日志轮转间隔
                   - backup_count: 保留的备份文件数量

    返回:
        logging.Logger: 配置好的日志器对象

    异常:
        KeyError: 配置参数缺失
        OSError: 日志目录创建失败
    """
    try:
        # 获取配置参数
        logger_name = "dc_logger"
        log_level = "INFO"
        log_dir = "./logs"
        log_filename = log_config.get("log_filename", "run.log")
        console_output = log_config.get("console_output", True)
        console_level = "DEBUG"
        file_level = "INFO"
        log_format = "%(asctime)s - %(levelname)s - %(message)s"
        date_format = "%Y-%m-%d %H:%M:%S"
        rotation_when = log_config.get("rotation_when", "midnight")
        rotation_interval = log_config.get("rotation_interval", 1)
        backup_count = log_config.get("backup_count", 7)

        # 创建日志器
        logger = logging.getLogger(logger_name)

        # 避免重复添加处理器
        if logger.handlers:
            return logger

        logger.setLevel(getattr(logging, log_level.upper()))  # 设置日志器级别（收集所有级别的日志）
        formatter = logging.Formatter(log_format, datefmt=date_format)  # 创建日志格式器

        # 创建日志目录（兼容 Windows 和 Linux）
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)

        # 完整的日志文件路径
        log_file_path = log_path / log_filename

        # 添加控制台处理器
        if console_output:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(getattr(logging, console_level.upper()))
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)

        # 添加文件处理器（支持按时间轮转）
        file_handler = TimedRotatingFileHandler(
            filename=str(log_file_path),
            encoding="utf-8",
            when=rotation_when,
            interval=rotation_interval,
            backupCount=backup_count
        )
        file_handler.setLevel(getattr(logging, file_level.upper()))
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        logger.info(f"日志系统初始化成功，日志文件: {log_file_path}")
        return logger

    except KeyError as e:
        raise KeyError(f"日志配置参数缺失: {e}")
    except OSError as e:
        raise OSError(f"日志目录创建失败: {e}")
    except Exception as e:
        raise Exception(f"日志系统初始化失败: {e}")
