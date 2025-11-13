"""
优化器工厂
根据配置创建相应的优化器实例
"""

from typing import Dict
import logging
from .base_optimizer import BaseOptimizer
from .bayesian_optimizer import BayesianOptimizer
from .rl_optimizer import RLOptimizer
from .grid_search_optimizer import GridSearchOptimizer
from .random_search_optimizer import RandomSearchOptimizer
from .genetic_optimizer import GeneticOptimizer


class OptimizerFactory:
    """
    优化器工厂类
    使用工厂模式创建不同类型的优化器
    """
    
    # 支持的优化算法映射
    OPTIMIZER_MAP = {
        'bayesian': BayesianOptimizer,
        'reinforcement_learning': RLOptimizer,
        'rl': RLOptimizer,  # 简写
        'grid_search': GridSearchOptimizer,
        'random_search': RandomSearchOptimizer,
        'genetic': GeneticOptimizer,
    }
    
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
                - 'bayesian': 贝叶斯优化
                - 'reinforcement_learning' 或 'rl': 强化学习优化
                - 'grid_search': 网格搜索
                - 'random_search': 随机搜索
                - 'genetic': 遗传算法
            controller: ACController 实例
            parameter_config: 参数配置字典
            security_boundary_config: 安全边界配置字典
            logger: 日志记录器（可选）
            
        Returns:
            BaseOptimizer: 优化器实例
            
        Raises:
            ValueError: 如果算法名称不支持
        """
        # 转换为小写并去除空格
        algorithm = algorithm.lower().strip()
        
        # 检查算法是否支持
        if algorithm not in OptimizerFactory.OPTIMIZER_MAP:
            supported_algorithms = ', '.join(OptimizerFactory.OPTIMIZER_MAP.keys())
            raise ValueError(
                f"不支持的优化算法: '{algorithm}'. "
                f"支持的算法: {supported_algorithms}"
            )
        
        # 创建优化器实例
        optimizer_class = OptimizerFactory.OPTIMIZER_MAP[algorithm]
        optimizer = optimizer_class(
            controller=controller,
            parameter_config=parameter_config,
            security_boundary_config=security_boundary_config
        )
        
        if logger:
            logger.info(f"成功创建优化器: {optimizer_class.__name__} (算法: {algorithm})")
        
        return optimizer
    
    @staticmethod
    def get_supported_algorithms() -> list:
        """
        获取支持的优化算法列表
        
        Returns:
            list: 支持的算法名称列表
        """
        return list(OptimizerFactory.OPTIMIZER_MAP.keys())
    
    @staticmethod
    def get_algorithm_description(algorithm: str) -> str:
        """
        获取算法描述
        
        Args:
            algorithm: 算法名称
            
        Returns:
            str: 算法描述
        """
        descriptions = {
            'bayesian': '贝叶斯优化 - 使用 Optuna 的 TPE 采样器，适合小规模参数空间的高效优化',
            'reinforcement_learning': '强化学习优化 - 使用 PPO 算法，适合需要与环境交互学习的场景',
            'rl': '强化学习优化 - 使用 PPO 算法（reinforcement_learning 的简写）',
            'grid_search': '网格搜索 - 遍历所有参数组合，保证找到全局最优解，但计算量大',
            'random_search': '随机搜索 - 随机采样参数空间，计算效率高，适合快速探索',
            'genetic': '遗传算法 - 模拟自然进化过程，适合复杂的非线性优化问题',
        }
        
        algorithm = algorithm.lower().strip()
        return descriptions.get(algorithm, "未知算法")

