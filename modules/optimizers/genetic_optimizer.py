"""
遗传算法优化器
使用遗传算法进行参数优化
"""

import pandas as pd
import random
import numpy as np
from typing import Dict, List, Tuple
from .base_optimizer import BaseOptimizer


class Individual:
    """
    个体类，表示一个候选解
    """
    
    def __init__(self, set_temp: int, set_humidity: int, cooling_mode: int):
        self.set_temp = set_temp
        self.set_humidity = set_humidity
        self.cooling_mode = cooling_mode
        self.fitness = float('inf')  # 适应度（目标函数值，越小越好）
    
    def to_dict(self) -> Dict:
        """转换为字典格式"""
        return {
            'set_temp': self.set_temp,
            'set_humidity': self.set_humidity,
            'cooling_mode': self.cooling_mode
        }
    
    def __repr__(self):
        return f"Individual(temp={self.set_temp}, humidity={self.set_humidity}, mode={self.cooling_mode}, fitness={self.fitness:.2f})"


class GeneticOptimizer(BaseOptimizer):
    """
    遗传算法优化器
    使用选择、交叉、变异操作进化种群
    """
    
    def __init__(self,
                 controller,
                 parameter_config: Dict,
                 security_boundary_config: Dict):
        """
        初始化遗传算法优化器
        
        Args:
            controller: ACController 实例
            parameter_config: 参数配置字典
            security_boundary_config: 安全边界配置字典
        """
        super().__init__(controller, parameter_config, security_boundary_config)
        
        # 从配置文件读取遗传算法参数
        opt_config = parameter_config.get("optimization_module", {})
        genetic_config = opt_config.get("genetic", {})
        
        self.population_size = int(genetic_config.get("population_size", 50))
        self.generations = int(genetic_config.get("generations", 30))
        self.mutation_rate = float(genetic_config.get("mutation_rate", 0.1))
        self.crossover_rate = float(genetic_config.get("crossover_rate", 0.8))
        self.historical_weight = float(opt_config.get("historical_weight", 0.3))
        
        self.population: List[Individual] = []
        
    def optimize(self, current_data: pd.DataFrame) -> Dict:
        """
        执行遗传算法优化
        
        Args:
            current_data: 当前系统状态数据
            
        Returns:
            Dict: 最优参数字典
        """
        self.logger.info(
            f"开始遗传算法优化，种群大小={self.population_size}, 代数={self.generations}..."
        )
        
        # 初始化种群
        self._initialize_population()
        
        # 评估初始种群
        self._evaluate_population(current_data)
        
        best_individual = min(self.population, key=lambda ind: ind.fitness)
        self.logger.info(f"初始种群最优个体: {best_individual}")
        
        # 进化过程
        for generation in range(self.generations):
            # 检查停止信号
            if self.controller.stop_event.is_set():
                self.logger.info("检测到停止信号，中断遗传算法优化")
                break
            
            # 选择
            parents = self._selection()
            
            # 交叉和变异，生成新种群
            offspring = []
            for i in range(0, len(parents), 2):
                if i + 1 < len(parents):
                    child1, child2 = self._crossover(parents[i], parents[i + 1])
                    offspring.extend([child1, child2])
                else:
                    offspring.append(parents[i])
            
            # 变异
            for individual in offspring:
                self._mutate(individual)
            
            # 评估新种群
            self.population = offspring
            self._evaluate_population(current_data)
            
            # 精英保留：保留上一代最优个体
            self.population.append(best_individual)
            self.population.sort(key=lambda ind: ind.fitness)
            self.population = self.population[:self.population_size]
            
            # 更新最优个体
            current_best = self.population[0]
            if current_best.fitness < best_individual.fitness:
                best_individual = current_best
                self.logger.info(f"第 {generation + 1} 代发现更优个体: {best_individual}")
            
            # 每 5 代记录一次进度
            if (generation + 1) % 5 == 0:
                avg_fitness = sum(ind.fitness for ind in self.population) / len(self.population)
                self.logger.info(
                    f"第 {generation + 1}/{self.generations} 代: "
                    f"最优适应度={best_individual.fitness:.2f}, 平均适应度={avg_fitness:.2f}"
                )
        
        # 保存最优参数
        self.best_params = best_individual.to_dict()
        self.best_objective = best_individual.fitness
        
        self.logger.info(
            f"遗传算法优化完成，最优参数: {self.best_params}, 目标值: {self.best_objective:.2f}"
        )
        
        return self.best_params
    
    def _initialize_population(self):
        """初始化种群"""
        self.population = []
        for _ in range(self.population_size):
            set_temp = random.randint(self.min_temp, self.max_temp)
            set_humidity = random.randint(self.min_humidity, self.max_humidity)
            cooling_mode = random.choice([0, 1])
            individual = Individual(set_temp, set_humidity, cooling_mode)
            self.population.append(individual)
    
    def _evaluate_population(self, current_data: pd.DataFrame):
        """评估种群中所有个体的适应度"""
        for individual in self.population:
            individual.fitness = self._evaluate_individual(individual, current_data)
    
    def _evaluate_individual(self, individual: Individual, current_data: pd.DataFrame) -> float:
        """
        评估单个个体的适应度
        
        Args:
            individual: 个体
            current_data: 当前系统状态数据
            
        Returns:
            float: 适应度值（目标函数值）
        """
        try:
            # 计算历史数据的目标值
            historical_objective = self.calculate_objective_from_historical(
                individual.set_temp, individual.set_humidity, individual.cooling_mode
            )
            
            # 获取当前系统状态
            current_temps, return_temps, power_values, power_groups, current_humidity, return_humidity = \
                self.controller.get_system_state(current_data)

            # 估计最终温湿度（基于设定值）
            final_temp_estimate = individual.set_temp
            final_humidity_estimate = individual.set_humidity

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
            self.logger.error(f"评估个体时发生错误: {str(e)}")
            return float('inf')
    
    def _selection(self) -> List[Individual]:
        """
        选择操作（锦标赛选择）
        
        Returns:
            List[Individual]: 选中的父代个体列表
        """
        parents = []
        tournament_size = 3
        
        for _ in range(self.population_size):
            # 随机选择 tournament_size 个个体
            tournament = random.sample(self.population, tournament_size)
            # 选择适应度最好的个体
            winner = min(tournament, key=lambda ind: ind.fitness)
            parents.append(winner)
        
        return parents
    
    def _crossover(self, parent1: Individual, parent2: Individual) -> Tuple[Individual, Individual]:
        """
        交叉操作（单点交叉）
        
        Args:
            parent1: 父代个体1
            parent2: 父代个体2
            
        Returns:
            Tuple[Individual, Individual]: 两个子代个体
        """
        if random.random() < self.crossover_rate:
            # 执行交叉
            child1 = Individual(
                set_temp=parent1.set_temp,
                set_humidity=parent2.set_humidity,
                cooling_mode=parent1.cooling_mode
            )
            child2 = Individual(
                set_temp=parent2.set_temp,
                set_humidity=parent1.set_humidity,
                cooling_mode=parent2.cooling_mode
            )
        else:
            # 不交叉，直接复制
            child1 = Individual(parent1.set_temp, parent1.set_humidity, parent1.cooling_mode)
            child2 = Individual(parent2.set_temp, parent2.set_humidity, parent2.cooling_mode)
        
        return child1, child2
    
    def _mutate(self, individual: Individual):
        """
        变异操作
        
        Args:
            individual: 个体
        """
        # 温度变异
        if random.random() < self.mutation_rate:
            individual.set_temp = random.randint(self.min_temp, self.max_temp)
        
        # 湿度变异
        if random.random() < self.mutation_rate:
            individual.set_humidity = random.randint(self.min_humidity, self.max_humidity)
        
        # 制冷模式变异
        if random.random() < self.mutation_rate:
            individual.cooling_mode = 1 - individual.cooling_mode  # 0 <-> 1

