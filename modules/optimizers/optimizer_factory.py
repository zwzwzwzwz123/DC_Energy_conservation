"""
优化器工厂
根据配置创建相应的优化器实例
"""

from typing import Dict, Optional
import logging
from .base_optimizer import BaseOptimizer
from .grid_search_optimizer import GridSearchOptimizer
from .random_search_optimizer import RandomSearchOptimizer

# 尝试导入需要外部依赖的优化器
try:
    from .bayesian_optimizer import BayesianOptimizer
    _BAYESIAN_AVAILABLE = True
except ImportError:
    BayesianOptimizer = None  # type: ignore
    _BAYESIAN_AVAILABLE = False

try:
    from .genetic_optimizer import GeneticOptimizer
    _GENETIC_AVAILABLE = True
except ImportError:
    GeneticOptimizer = None  # type: ignore
    _GENETIC_AVAILABLE = False

try:
    from .rl_optimizer import RLOptimizer
    _RL_AVAILABLE = True
except ImportError:
    RLOptimizer = None  # type: ignore
    _RL_AVAILABLE = False


class OptimizerFactory:
    """
    优化器工厂类
    使用工厂模式创建不同类型的优化器
    支持优雅降级：如果某些优化器的依赖未安装，会自动回退到可用的优化器
    """

    # 优化器映射表缓存（延迟初始化，避免类定义时出错）
    _optimizer_map_cache: Optional[Dict[str, Optional[type]]] = None

    @classmethod
    def get_optimizer_map(cls) -> Dict[str, Optional[type]]:
        """
        获取优化器映射表（延迟初始化，线程安全）

        Returns:
            Dict[str, Optional[type]]: 算法名称到优化器类的映射
        """
        if cls._optimizer_map_cache is None:
            cls._optimizer_map_cache = cls._build_optimizer_map()
        return cls._optimizer_map_cache

    @staticmethod
    def _build_optimizer_map() -> Dict[str, Optional[type]]:
        """
        构建优化器映射表（动态检测可用的优化器）

        Returns:
            Dict[str, Optional[type]]: 算法名称到优化器类的映射
        """
        optimizer_map = {
            'grid_search': GridSearchOptimizer,
            'random_search': RandomSearchOptimizer,
        }

        if _BAYESIAN_AVAILABLE:
            optimizer_map['bayesian'] = BayesianOptimizer

        if _GENETIC_AVAILABLE:
            optimizer_map['genetic'] = GeneticOptimizer

        if _RL_AVAILABLE:
            optimizer_map['reinforcement_learning'] = RLOptimizer
            optimizer_map['rl'] = RLOptimizer  # 简写

        return optimizer_map
    
    @staticmethod
    def create_optimizer(
        algorithm: str,
        controller,
        parameter_config: Dict,
        security_boundary_config: Dict,
        logger: logging.Logger = None
    ) -> BaseOptimizer:
        """
        创建优化器实例

        Args:
            algorithm: 优化算法名称
                支持的算法:
                - 'bayesian': 贝叶斯优化（需要 optuna）
                - 'reinforcement_learning' 或 'rl': 强化学习优化（需要 torch, numpy）
                - 'grid_search': 网格搜索（无外部依赖）
                - 'random_search': 随机搜索（无外部依赖）
                - 'genetic': 遗传算法（需要 numpy）
            controller: ACController 实例
            parameter_config: 参数配置字典
            security_boundary_config: 安全边界配置字典
            logger: 日志记录器（可选）

        Returns:
            BaseOptimizer: 优化器实例

        Raises:
            ValueError: 如果算法名称不支持或依赖未安装
        """
        # 转换为小写并去除空格
        algorithm = algorithm.lower().strip()

        # 获取优化器映射表（使用类方法，避免直接访问类属性）
        optimizer_map = OptimizerFactory.get_optimizer_map()

        # 检查算法是否支持
        if algorithm not in optimizer_map:
            supported_algorithms = ', '.join(optimizer_map.keys())
            error_msg = (
                f"不支持的优化算法: '{algorithm}'. "
                f"当前可用的算法: {supported_algorithms}"
            )

            # 提供依赖安装提示
            if algorithm in ['bayesian'] and not _BAYESIAN_AVAILABLE:
                error_msg += "\n提示: 贝叶斯优化需要安装 optuna: pip install optuna>=3.0.0"
            elif algorithm in ['reinforcement_learning', 'rl'] and not _RL_AVAILABLE:
                error_msg += "\n提示: 强化学习需要安装 torch 和 numpy: pip install torch>=2.0.0 numpy>=1.24.0"
            elif algorithm in ['genetic'] and not _GENETIC_AVAILABLE:
                error_msg += "\n提示: 遗传算法需要安装 numpy: pip install numpy>=1.24.0"

            if logger:
                logger.error(error_msg)
            raise ValueError(error_msg)

        # 创建优化器实例
        optimizer_class = optimizer_map[algorithm]

        try:
            optimizer = optimizer_class(
                controller=controller,
                parameter_config=parameter_config,
                security_boundary_config=security_boundary_config
            )

            if logger:
                logger.info(f"成功创建优化器: {optimizer_class.__name__} (算法: {algorithm})")

            return optimizer

        except Exception as e:
            error_msg = f"创建优化器失败: {str(e)}"
            if logger:
                logger.error(error_msg)
            raise ValueError(error_msg)
    
    @classmethod
    def get_supported_algorithms(cls) -> list:
        """
        获取当前可用的优化算法列表（根据已安装的依赖动态确定）

        Returns:
            list: 支持的算法名称列表
        """
        return list(cls.get_optimizer_map().keys())

    @staticmethod
    def get_all_algorithms_info() -> Dict[str, Dict[str, str]]:
        """
        获取所有算法的信息（包括不可用的）

        Returns:
            dict: 算法信息字典，包含名称、描述、依赖、可用性
        """
        all_algorithms = {
            'bayesian': {
                'name': '贝叶斯优化',
                'description': '使用 Optuna 的 TPE 采样器，适合小规模参数空间的高效优化',
                'dependencies': 'optuna>=3.0.0',
                'available': _BAYESIAN_AVAILABLE
            },
            'reinforcement_learning': {
                'name': '强化学习优化',
                'description': '使用 PPO 算法，适合需要与环境交互学习的场景',
                'dependencies': 'torch>=2.0.0, numpy>=1.24.0',
                'available': _RL_AVAILABLE
            },
            'rl': {
                'name': '强化学习优化（简写）',
                'description': '与 reinforcement_learning 相同',
                'dependencies': 'torch>=2.0.0, numpy>=1.24.0',
                'available': _RL_AVAILABLE
            },
            'grid_search': {
                'name': '网格搜索',
                'description': '遍历所有参数组合，保证找到全局最优解，但计算量大',
                'dependencies': '无',
                'available': True
            },
            'random_search': {
                'name': '随机搜索',
                'description': '随机采样参数空间，计算效率高，适合快速探索',
                'dependencies': '无',
                'available': True
            },
            'genetic': {
                'name': '遗传算法',
                'description': '模拟自然进化过程，适合复杂的非线性优化问题',
                'dependencies': 'numpy>=1.24.0',
                'available': _GENETIC_AVAILABLE
            },
        }
        return all_algorithms

    @staticmethod
    def get_algorithm_description(algorithm: str) -> str:
        """
        获取算法描述

        Args:
            algorithm: 算法名称

        Returns:
            str: 算法描述
        """
        all_info = OptimizerFactory.get_all_algorithms_info()
        algorithm = algorithm.lower().strip()

        if algorithm in all_info:
            info = all_info[algorithm]
            status = "✓ 可用" if info['available'] else f"✗ 不可用（需要: {info['dependencies']}）"
            return f"{info['name']} - {info['description']} [{status}]"

        return "未知算法"

