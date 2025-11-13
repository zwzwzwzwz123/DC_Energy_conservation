"""
随机搜索优化器
随机采样参数空间，找到最优解
"""

import pandas as pd
import random
from typing import Dict
from .base_optimizer import BaseOptimizer


class RandomSearchOptimizer(BaseOptimizer):
    """
    随机搜索优化器
    在参数空间中随机采样，评估性能
    """
    
    def __init__(self,
                 controller,
                 parameter_config: Dict,
                 security_boundary_config: Dict):
        """
        初始化随机搜索优化器
        
        Args:
            controller: ACController 实例
            parameter_config: 参数配置字典
            security_boundary_config: 安全边界配置字典
        """
        super().__init__(controller, parameter_config, security_boundary_config)
        
        # 从配置文件读取随机搜索参数
        opt_config = parameter_config.get("optimization_module", {})
        random_config = opt_config.get("random_search", {})
        
        self.n_iterations = int(random_config.get("n_iterations", opt_config.get("max_trials", 50)))
        self.seed = random_config.get("seed", None)
        self.historical_weight = float(opt_config.get("historical_weight", 0.3))
        
        # 设置随机种子（如果提供）
        if self.seed is not None:
            random.seed(self.seed)
        
    def optimize(self, current_data: pd.DataFrame) -> Dict:
        """
        执行随机搜索优化
        
        Args:
            current_data: 当前系统状态数据
            
        Returns:
            Dict: 最优参数字典
        """
        self.logger.info(f"开始随机搜索优化，共 {self.n_iterations} 次迭代...")
        
        best_objective = float('inf')
        best_params = None
        
        for iteration in range(self.n_iterations):
            # 检查停止信号
            if self.controller.stop_event.is_set():
                self.logger.info("检测到停止信号，中断随机搜索")
                break
            
            # 随机采样参数
            set_temp = random.randint(self.min_temp, self.max_temp)
            set_humidity = random.randint(self.min_humidity, self.max_humidity)
            cooling_mode = random.choice([0, 1])
            
            # 评估参数
            objective = self._evaluate_params(
                set_temp, set_humidity, cooling_mode, current_data
            )
            
            # 更新最优参数
            if objective < best_objective:
                best_objective = objective
                best_params = {
                    'set_temp': set_temp,
                    'set_humidity': set_humidity,
                    'cooling_mode': cooling_mode
                }
                self.logger.info(
                    f"发现更优参数 [迭代 {iteration + 1}/{self.n_iterations}]: "
                    f"temp={set_temp}, humidity={set_humidity}, mode={cooling_mode}, "
                    f"objective={objective:.2f}"
                )
            
            # 每 10 次迭代记录一次进度
            if (iteration + 1) % 10 == 0:
                progress = ((iteration + 1) / self.n_iterations) * 100
                self.logger.info(f"随机搜索进度: {progress:.1f}% ({iteration + 1}/{self.n_iterations})")
        
        # 保存最优参数
        if best_params is not None:
            self.best_params = best_params
            self.best_objective = best_objective
            self.logger.info(
                f"随机搜索完成，最优参数: {self.best_params}, 目标值: {self.best_objective:.2f}"
            )
        else:
            self.logger.warning("随机搜索未找到有效参数，使用默认参数")
            self.best_params = self.get_best_params()
        
        return self.best_params
    
    def _evaluate_params(self, set_temp: int, set_humidity: int,
                        cooling_mode: int, current_data: pd.DataFrame) -> float:
        """
        评估参数

        Args:
            set_temp: 设定温度
            set_humidity: 设定湿度
            cooling_mode: 制冷模式
            current_data: 当前系统状态数据

        Returns:
            float: 目标函数值
        """
        try:
            # 计算历史数据的目标值
            historical_objective = self.calculate_objective_from_historical(
                set_temp, set_humidity, cooling_mode
            )

            # 获取当前系统状态
            current_temps, return_temps, power_values, power_groups, current_humidity, return_humidity = \
                self.controller.get_system_state(current_data)

            # 估计最终温湿度（基于设定值）
            final_temp_estimate = set_temp
            final_humidity_estimate = set_humidity

            # 检查安全约束（使用估计的最终状态）
            if final_temp_estimate > self.max_safe_temp:
                return float('inf')
            if not (self.min_safe_humidity <= final_humidity_estimate <= self.max_safe_humidity):
                return float('inf')

            # 计算目标函数值
            if historical_objective > 0:
                real_time_objective = sum(power_values) if power_values else 0
                combined_objective = (1 - self.historical_weight) * real_time_objective + \
                                   self.historical_weight * historical_objective
            else:
                combined_objective = sum(power_values) if power_values else float('inf')

            return combined_objective

        except Exception as e:
            self.logger.error(f"评估参数时发生错误: {str(e)}")
            return float('inf')

