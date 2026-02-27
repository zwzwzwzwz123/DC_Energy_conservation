"""
基础优化器抽象类
定义所有优化器必须实现的统一接口
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional
import pandas as pd
import logging


class BaseOptimizer(ABC):
    """
    优化器基类，所有具体优化器都必须继承此类
    
    统一接口设计:
    - optimize(): 执行优化过程
    - get_best_params(): 获取最优参数
    - stop(): 停止优化过程
    """
    
    def __init__(self,
                 controller,  # ACController 实例
                 parameter_config: Dict,
                 security_boundary_config: Dict):
        """
        初始化优化器
        
        Args:
            controller: ACController 实例，用于控制空调和获取系统状态
            parameter_config: 参数配置字典
            security_boundary_config: 安全边界配置字典
        """
        self.controller = controller
        self.logger = controller.logger
        self.parameter_config = parameter_config
        self.security_boundary_config = security_boundary_config
        
        # 从安全边界配置读取约束条件
        self.min_temp = int(security_boundary_config.get("minimum_air_conditioner_setting_temperature", 16))
        self.max_temp = int(security_boundary_config.get("maximum_air_conditioner_setting_temperature", 30))
        self.min_humidity = int(security_boundary_config.get("minimum_air_conditioner_setting_humidity", 30))
        self.max_humidity = int(security_boundary_config.get("maximum_air_conditioner_setting_humidity", 70))
        
        # 安全约束
        self.max_safe_temp = float(security_boundary_config.get("maximum_safe_indoor_temperature", 28.0))
        self.min_safe_humidity = float(security_boundary_config.get("minimum_safe_indoor_humidity", 30.0))
        self.max_safe_humidity = float(security_boundary_config.get("maximum_safe_indoor_humidity", 70.0))
        
        # 最优参数存储
        self.best_params: Optional[Dict] = None
        self.best_objective: float = float('inf')
        
    @abstractmethod
    def optimize(self, current_data: pd.DataFrame) -> Dict:
        """
        执行优化过程
        
        Args:
            current_data: 当前系统状态数据
            
        Returns:
            Dict: 最优参数字典，包含:
                - set_temp: 设定温度
                - set_humidity: 设定湿度
                - cooling_mode: 制冷模式
        """
        pass
    
    def get_best_params(self) -> Dict:
        """
        获取最优参数
        
        Returns:
            Dict: 最优参数字典
        """
        if self.best_params is None:
            # 返回默认参数
            return {
                'set_temp': 24,
                'set_humidity': 50,
                'cooling_mode': 1
            }
        return self.best_params
    
    def stop(self):
        """
        停止优化过程
        子类可以重写此方法以实现特定的停止逻辑
        """
        self.controller.stop_event.set()
        self.logger.info(f"{self.__class__.__name__} 优化过程已停止")
    
    def evaluate_params(self, set_temp: int, set_humidity: int, cooling_mode: int,
                       current_data: pd.DataFrame) -> float:
        """
        评估给定参数的目标函数值（基于历史数据，不执行实际控制）

        注意：此方法不会实际控制设备，仅基于历史数据和当前状态进行评估

        Args:
            set_temp: 设定温度
            set_humidity: 设定湿度
            cooling_mode: 制冷模式
            current_data: 当前系统状态数据

        Returns:
            float: 目标函数值（功耗，越小越好）
        """
        try:
            # 计算历史数据的目标值
            historical_objective = self.calculate_objective_from_historical(
                set_temp, set_humidity, cooling_mode
            )

            # 获取当前系统状态
            current_temps, return_temps, power_values, power_groups, current_humidity, return_humidity = \
                self.controller.get_system_state(current_data)

            # 计算当前平均温度和湿度
            avg_temp = sum(current_temps) / len(current_temps) if current_temps else 0
            avg_humidity = sum(current_humidity) / len(current_humidity) if current_humidity else 0

            # 检查安全约束（使用设定值作为预期最终状态）
            # 注意：这是一个简化假设，实际最终状态可能与设定值有偏差
            if set_temp > self.max_safe_temp:
                return float('inf')  # 违反温度约束
            if not (self.min_safe_humidity <= set_humidity <= self.max_safe_humidity):
                return float('inf')  # 违反湿度约束

            # 如果有历史数据，主要使用历史数据的功耗
            if historical_objective > 0:
                # 组合历史数据和当前功耗（历史数据权重更高）
                current_power = sum(power_values) if power_values else 0
                # 使用70%历史数据 + 30%当前功耗作为评估
                combined_objective = 0.7 * historical_objective + 0.3 * current_power
                return combined_objective
            else:
                # 如果没有匹配的历史数据，使用当前功耗作为估计
                # 但给予一定的惩罚，因为缺乏历史验证
                current_power = sum(power_values) if power_values else 0
                if current_power > 0:
                    return current_power * 1.2  # 增加20%的不确定性惩罚
                else:
                    # 如果连当前功耗都没有，返回一个较大的值
                    return 10000.0

        except Exception as e:
            self.logger.error(f"评估参数时发生错误: {str(e)}")
            return float('inf')
    
    def calculate_objective_from_historical(self, set_temp: int, set_humidity: int, 
                                           cooling_mode: int = 1) -> float:
        """
        从历史数据计算目标值
        
        Args:
            set_temp: 设定温度
            set_humidity: 设定湿度
            cooling_mode: 制冷模式
            
        Returns:
            float: 历史数据的平均功耗
        """
        if not self.controller.historical_data:
            return 0.0
        
        total_power = 0.0
        count = 0
        
        # 定义误差范围
        temp_tolerance = 0.5
        humidity_tolerance = 5.0
        
        for data in self.controller.historical_data:
            data_cooling_mode = getattr(data, 'cooling_mode', 1)
            
            if (abs(data.set_temp - set_temp) <= temp_tolerance and
                abs(data.set_humidity - set_humidity) <= humidity_tolerance and
                data_cooling_mode == cooling_mode):
                # 检查历史数据是否满足安全约束
                if (data.final_temp <= self.max_safe_temp and
                    self.min_safe_humidity <= data.final_humidity <= self.max_safe_humidity):
                    total_power += data.power
                    count += 1
        
        return total_power / count if count > 0 else 0.0
    
    def is_safe_params(self, set_temp: int, set_humidity: int) -> bool:
        """
        检查参数是否在安全范围内
        
        Args:
            set_temp: 设定温度
            set_humidity: 设定湿度
            
        Returns:
            bool: 参数是否安全
        """
        return (self.min_temp <= set_temp <= self.max_temp and
                self.min_humidity <= set_humidity <= self.max_humidity)

