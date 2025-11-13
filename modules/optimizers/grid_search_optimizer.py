"""
网格搜索优化器
遍历所有可能的参数组合，找到最优解
"""

import pandas as pd
import itertools
from typing import Dict, List
from .base_optimizer import BaseOptimizer


class GridSearchOptimizer(BaseOptimizer):
    """
    网格搜索优化器
    系统地遍历参数空间中的所有组合
    """
    
    def __init__(self,
                 controller,
                 parameter_config: Dict,
                 security_boundary_config: Dict):
        """
        初始化网格搜索优化器
        
        Args:
            controller: ACController 实例
            parameter_config: 参数配置字典
            security_boundary_config: 安全边界配置字典
        """
        super().__init__(controller, parameter_config, security_boundary_config)
        
        # 从配置文件读取网格搜索参数
        opt_config = parameter_config.get("optimization_module", {})
        grid_config = opt_config.get("grid_search", {})
        
        self.temp_step = int(grid_config.get("temperature_step", 1))
        self.humidity_step = int(grid_config.get("humidity_step", 5))
        self.historical_weight = float(opt_config.get("historical_weight", 0.3))
        
        # 生成搜索网格
        self.temp_grid = list(range(self.min_temp, self.max_temp + 1, self.temp_step))
        self.humidity_grid = list(range(self.min_humidity, self.max_humidity + 1, self.humidity_step))
        self.cooling_mode_grid = [0, 1]
        
        self.total_combinations = len(self.temp_grid) * len(self.humidity_grid) * len(self.cooling_mode_grid)
        
    def optimize(self, current_data: pd.DataFrame) -> Dict:
        """
        执行网格搜索优化
        
        Args:
            current_data: 当前系统状态数据
            
        Returns:
            Dict: 最优参数字典
        """
        self.logger.info(f"开始网格搜索优化，共 {self.total_combinations} 种参数组合...")
        
        best_objective = float('inf')
        best_params = None
        evaluated_count = 0
        
        # 遍历所有参数组合
        for set_temp, set_humidity, cooling_mode in itertools.product(
            self.temp_grid, self.humidity_grid, self.cooling_mode_grid
        ):
            # 检查停止信号
            if self.controller.stop_event.is_set():
                self.logger.info("检测到停止信号，中断网格搜索")
                break
            
            # 评估当前参数组合
            objective = self._evaluate_combination(
                set_temp, set_humidity, cooling_mode, current_data
            )
            
            evaluated_count += 1
            
            # 更新最优参数
            if objective < best_objective:
                best_objective = objective
                best_params = {
                    'set_temp': set_temp,
                    'set_humidity': set_humidity,
                    'cooling_mode': cooling_mode
                }
                self.logger.info(
                    f"发现更优参数 [{evaluated_count}/{self.total_combinations}]: "
                    f"temp={set_temp}, humidity={set_humidity}, mode={cooling_mode}, "
                    f"objective={objective:.2f}"
                )
            
            # 每评估 10% 的组合，记录一次进度
            if evaluated_count % max(1, self.total_combinations // 10) == 0:
                progress = (evaluated_count / self.total_combinations) * 100
                self.logger.info(f"网格搜索进度: {progress:.1f}% ({evaluated_count}/{self.total_combinations})")
        
        # 保存最优参数
        if best_params is not None:
            self.best_params = best_params
            self.best_objective = best_objective
            self.logger.info(
                f"网格搜索完成，评估了 {evaluated_count} 种组合，"
                f"最优参数: {self.best_params}, 目标值: {self.best_objective:.2f}"
            )
        else:
            self.logger.warning("网格搜索未找到有效参数，使用默认参数")
            self.best_params = self.get_best_params()
        
        return self.best_params
    
    def _evaluate_combination(self, set_temp: int, set_humidity: int,
                             cooling_mode: int, current_data: pd.DataFrame) -> float:
        """
        评估单个参数组合

        Args:
            set_temp: 设定温度
            set_humidity: 设定湿度
            cooling_mode: 制冷模式
            current_data: 当前系统状态数据

        Returns:
            float: 目标函数值
        """
        try:
            # 使用基类的统一评估方法
            # 注意：由于暂时忽略实际控制，这里使用历史数据和当前数据的组合评估

            # 计算历史数据的目标值
            historical_objective = self.calculate_objective_from_historical(
                set_temp, set_humidity, cooling_mode
            )

            # 获取当前系统状态（模拟应用参数前）
            current_temps, return_temps, power_values, power_groups, current_humidity, return_humidity = \
                self.controller.get_system_state(current_data)

            # 模拟应用参数后的状态
            # 注意：在实际控制启用后，应该调用 self.controller.apply_settings()
            # 然后等待稳定后再获取最终状态
            # 这里暂时使用历史数据估计最终状态

            # 估计最终温湿度（基于历史数据）
            final_temp_estimate = set_temp  # 简化估计：假设最终温度接近设定温度
            final_humidity_estimate = set_humidity  # 简化估计：假设最终湿度接近设定湿度

            # 检查安全约束（使用估计的最终状态）
            if final_temp_estimate > self.max_safe_temp:
                return float('inf')
            if not (self.min_safe_humidity <= final_humidity_estimate <= self.max_safe_humidity):
                return float('inf')

            # 计算目标函数值
            if historical_objective > 0:
                # 如果有历史数据，主要使用历史数据
                real_time_objective = sum(power_values) if power_values else 0
                combined_objective = (1 - self.historical_weight) * real_time_objective + \
                                   self.historical_weight * historical_objective
            else:
                # 如果没有历史数据，使用当前功耗作为估计
                combined_objective = sum(power_values) if power_values else float('inf')

            return combined_objective

        except Exception as e:
            self.logger.error(f"评估参数组合时发生错误: {str(e)}")
            return float('inf')

