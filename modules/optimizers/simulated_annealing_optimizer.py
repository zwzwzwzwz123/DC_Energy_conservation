"""
模拟退火优化器
使用模拟退火算法在参数空间中搜索低功耗配置
"""

import math
import random
from typing import Dict, Tuple
import pandas as pd

from .base_optimizer import BaseOptimizer


class SimulatedAnnealingOptimizer(BaseOptimizer):
    """
    模拟退火优化器
    通过逐步降温的随机搜索在离散参数空间中找到近似全局最优解
    """

    def __init__(
        self,
        controller,
        parameter_config: Dict,
        security_boundary_config: Dict
    ):
        """
        初始化模拟退火优化器

        Args:
            controller: ACController 实例
            parameter_config: 参数配置字典
            security_boundary_config: 安全边界配置字典
        """
        super().__init__(controller, parameter_config, security_boundary_config)

        opt_config = parameter_config.get("optimization_module", {})
        sa_config = opt_config.get("simulated_annealing", {})

        # 退火相关参数
        self.initial_temperature = float(sa_config.get("initial_temperature", 10.0))
        self.min_temperature = float(sa_config.get("min_temperature", 0.5))
        self.cooling_rate = float(sa_config.get("cooling_rate", 0.85))
        self.max_iterations = int(sa_config.get("max_iterations", opt_config.get("max_trials", 50)))
        self.iterations_per_temp = int(sa_config.get("iterations_per_temp", 5))

        # 邻域生成步长
        self.temp_step = int(sa_config.get("temperature_step", 1))
        self.humidity_step = int(sa_config.get("humidity_step", 5))

        self.historical_weight = float(opt_config.get("historical_weight", 0.3))

    def optimize(self, current_data: pd.DataFrame) -> Dict:
        """
        执行模拟退火优化

        Args:
            current_data: 当前系统状态数据

        Returns:
            Dict: 最优参数字典
        """
        self.logger.info(
            "开始模拟退火优化: "
            f"初始温度={self.initial_temperature}, 最小温度={self.min_temperature}, "
            f"降温率={self.cooling_rate}, 最大迭代={self.max_iterations}"
        )

        # 初始化解，使用当前最优或默认安全参数
        current_params = self._get_initial_params()
        current_objective = self._evaluate_params(
            current_params['set_temp'],
            current_params['set_humidity'],
            current_params['cooling_mode'],
            current_data
        )

        best_params = current_params
        best_objective = current_objective

        temperature = self.initial_temperature
        iteration = 0

        while temperature > self.min_temperature and iteration < self.max_iterations:
            if self.controller.stop_event.is_set():
                self.logger.info("检测到停止信号，中断模拟退火优化")
                break

            for _ in range(self.iterations_per_temp):
                iteration += 1
                neighbor_params = self._generate_neighbor(current_params)
                objective = self._evaluate_params(
                    neighbor_params['set_temp'],
                    neighbor_params['set_humidity'],
                    neighbor_params['cooling_mode'],
                    current_data
                )

                delta = objective - current_objective
                accept = delta < 0
                if not accept:
                    # 以一定概率接受更差解，避免早熟收敛
                    accept_probability = math.exp(-delta / temperature) if temperature > 0 else 0
                    accept = random.random() < accept_probability

                if accept:
                    current_params = neighbor_params
                    current_objective = objective

                if objective < best_objective:
                    best_objective = objective
                    best_params = neighbor_params
                    self.logger.info(
                        f"迭代 {iteration}: 发现更优参数 "
                        f"temp={neighbor_params['set_temp']}, "
                        f"humidity={neighbor_params['set_humidity']}, "
                        f"mode={neighbor_params['cooling_mode']}, "
                        f"objective={objective:.2f}, 温度={temperature:.3f}"
                    )

                if iteration >= self.max_iterations:
                    break

            temperature *= self.cooling_rate

        # 保存最优结果
        self.best_params = best_params
        self.best_objective = best_objective

        self.logger.info(
            f"模拟退火优化完成，迭代 {iteration} 次，"
            f"最优参数 {self.best_params}, 目标值 {self.best_objective:.2f}"
        )
        return self.best_params

    def _get_initial_params(self) -> Dict:
        """
        获取初始参数，确保落在安全范围内
        """
        initial = self.best_params or {
            'set_temp': 24,
            'set_humidity': 50,
            'cooling_mode': 1
        }

        # 裁剪到安全边界
        initial['set_temp'] = min(max(initial['set_temp'], self.min_temp), self.max_temp)
        initial['set_humidity'] = min(max(initial['set_humidity'], self.min_humidity), self.max_humidity)
        initial['cooling_mode'] = 1 if initial['cooling_mode'] not in (0, 1) else initial['cooling_mode']
        return initial

    def _generate_neighbor(self, params: Dict) -> Dict:
        """
        基于当前参数生成邻域解，保持在安全边界内
        """
        # 温度和湿度以步长为单位轻微扰动
        delta_temp = random.choice([-self.temp_step, 0, self.temp_step])
        delta_humidity = random.choice([-self.humidity_step, 0, self.humidity_step])
        delta_mode = random.choice([0, 1])  # 随机保持或切换模式

        new_temp = min(max(params['set_temp'] + delta_temp, self.min_temp), self.max_temp)
        new_humidity = min(max(params['set_humidity'] + delta_humidity, self.min_humidity), self.max_humidity)
        new_mode = params['cooling_mode'] if delta_mode == 0 else 1 - params['cooling_mode']

        # 确保生成的参数仍然满足安全约束
        if not self.is_safe_params(new_temp, new_humidity):
            return params

        return {
            'set_temp': new_temp,
            'set_humidity': new_humidity,
            'cooling_mode': new_mode
        }

    def _evaluate_params(
        self,
        set_temp: int,
        set_humidity: int,
        cooling_mode: int,
        current_data: pd.DataFrame
    ) -> float:
        """
        评估参数组合的目标函数值
        """
        try:
            historical_objective = self.calculate_objective_from_historical(
                set_temp, set_humidity, cooling_mode
            )

            current_temps, return_temps, power_values, power_groups, current_humidity, return_humidity = \
                self.controller.get_system_state(current_data)

            # 基于设定值估计最终状态，并检查安全约束
            if set_temp > self.max_safe_temp:
                return float('inf')
            if not (self.min_safe_humidity <= set_humidity <= self.max_safe_humidity):
                return float('inf')

            real_time_objective = sum(power_values) if power_values else 0
            if historical_objective > 0:
                combined_objective = (1 - self.historical_weight) * real_time_objective + \
                    self.historical_weight * historical_objective
            else:
                combined_objective = real_time_objective if real_time_objective > 0 else float('inf')

            return combined_objective
        except Exception as exc:
            self.logger.error(f"评估参数时发生错误: {str(exc)}")
            return float('inf')
