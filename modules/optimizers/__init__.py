"""
优化器模块
提供多种优化算法的统一接口
注意：部分优化器依赖外部库，如果未安装相应的库，这些优化器将不可用。
- BayesianOptimizer: 需要 optuna
- RL_Optimizer: 需要 torch, numpy
- GeneticOptimizer: 需要 numpy
- GridSearchOptimizer: 无外部依赖
- RandomSearchOptimizer: 无外部依赖
"""

# 基础类和工厂（无外部依赖）
from .base_optimizer import BaseOptimizer
from .optimizer_factory import OptimizerFactory
# 无外部依赖的优化器（总是可用）
from .grid_search_optimizer import GridSearchOptimizer
from .random_search_optimizer import RandomSearchOptimizer
from .simulated_annealing_optimizer import SimulatedAnnealingOptimizer

# 尝试导入需要外部依赖的优化器
__all__ = [
    'BaseOptimizer',
    'OptimizerFactory',
    'GridSearchOptimizer',
    'RandomSearchOptimizer',
]

# 尝试导入 BayesianOptimizer（需要 optuna）
try:
    from .bayesian_optimizer import BayesianOptimizer
    __all__.append('BayesianOptimizer')
except ImportError:
    BayesianOptimizer = None  # type: ignore

# 尝试导入 GeneticOptimizer（需要 numpy）
try:
    from .genetic_optimizer import GeneticOptimizer
    __all__.append('GeneticOptimizer')
except ImportError:
    GeneticOptimizer = None  # type: ignore

# 尝试导入 RLOptimizer（需要 torch, numpy）
try:
    from .rl_optimizer import RLOptimizer
    __all__.append('RLOptimizer')
except ImportError:
    RLOptimizer = None  # type: ignore
