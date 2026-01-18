"""
贝叶斯优化器
使用 Optuna 库实现贝叶斯优化算法
"""

import optuna
import pandas as pd
from typing import Dict, Optional
from .base_optimizer import BaseOptimizer


class BayesianOptimizer(BaseOptimizer):
    """
    贝叶斯优化器
    使用 Optuna 的 TPE (Tree-structured Parzen Estimator) 采样器
    """
    
    def __init__(self,
                 controller,
                 parameter_config: Dict,
                 security_boundary_config: Dict):
        """
        初始化贝叶斯优化器
        
        Args:
            controller: ACController 实例
            parameter_config: 参数配置字典
            security_boundary_config: 安全边界配置字典
        """
        super().__init__(controller, parameter_config, security_boundary_config)
        
        # 从配置文件读取贝叶斯优化参数
        opt_config = parameter_config.get("optimization_module", {})
        bayesian_config = opt_config.get("bayesian", {})
        
        self.n_trials = int(bayesian_config.get("n_trials", opt_config.get("max_trials", 20)))
        self.timeout = int(opt_config.get("timeout", 300))
        self.historical_weight = float(opt_config.get("historical_weight", 0.3))
        
        # Optuna 采样器选择
        sampler_name = bayesian_config.get("sampler", "TPE")
        if sampler_name == "TPE":
            self.sampler = optuna.samplers.TPESampler()
        elif sampler_name == "Random":
            self.sampler = optuna.samplers.RandomSampler()
        elif sampler_name == "Grid":
            # 网格采样器需要定义搜索空间
            search_space = {
                'set_temp': list(range(self.min_temp, self.max_temp + 1)),
                'set_humidity': list(range(self.min_humidity, self.max_humidity + 1, 5)),
                'cooling_mode': [0, 1]
            }
            self.sampler = optuna.samplers.GridSampler(search_space)
        else:
            self.sampler = optuna.samplers.TPESampler()
        
        self.study: Optional[optuna.Study] = None
        self.initial_params: Optional[Dict] = None
        
    def set_initial_params(self, params: Dict):
        """
        设置初始参数
        
        Args:
            params: 初始参数字典
        """
        self.initial_params = params
        
    def optimize(self, current_data: pd.DataFrame) -> Dict:
        """
        执行贝叶斯优化
        
        Args:
            current_data: 当前系统状态数据
            
        Returns:
            Dict: 最优参数字典
        """
        try:
            self.logger.info("开始贝叶斯优化...")
            
            # 创建 Optuna study
            self.study = optuna.create_study(
                direction='minimize',
                sampler=self.sampler
            )
            
            # 如果有初始参数，先评估初始参数
            if self.initial_params:
                try:
                    self.logger.info(f"评估初始参数: {self.initial_params}")
                    # 可以通过 enqueue_trial 将初始参数加入优化
                except Exception as e:
                    self.logger.error(f"应用初始参数时发生错误: {str(e)}")
            
            # 执行优化
            self.study.optimize(
                lambda trial: self._objective(trial, current_data),
                n_trials=self.n_trials,
                timeout=self.timeout,
                callbacks=[self._check_stop_condition]
            )
            
            # 获取最优参数
            if len(self.study.trials) > 0:
                best_trial = self.study.best_trial
                self.best_params = {
                    'set_temp': best_trial.params['set_temp'],
                    'set_humidity': best_trial.params['set_humidity'],
                    'cooling_mode': best_trial.params['cooling_mode']
                }
                self.best_objective = best_trial.value
                
                self.logger.info(f"贝叶斯优化完成，共完成 {len(self.study.trials)} 次试验")
                self.logger.info(f"最优参数: {self.best_params}, 目标值: {self.best_objective:.2f}")
            else:
                self.logger.warning("优化未完成任何试验，使用默认参数")
                self.best_params = self.get_best_params()
            
            return self.best_params
            
        except optuna.TrialPruned:
            self.logger.info("优化被提前停止")
            return self.get_best_params()
        except Exception as e:
            self.logger.error(f"贝叶斯优化过程中发生错误: {str(e)}")
            return self.get_best_params()
    
    def _objective(self, trial: optuna.Trial, current_data: pd.DataFrame) -> float:
        """
        Optuna 目标函数
        
        Args:
            trial: Optuna trial 对象
            current_data: 当前系统状态数据
            
        Returns:
            float: 目标函数值
        """
        if self.controller.stop_event.is_set():
            raise optuna.TrialPruned()
        
        # 建议参数
        set_temp = trial.suggest_int('set_temp', self.min_temp, self.max_temp)
        set_humidity = trial.suggest_int('set_humidity', self.min_humidity, self.max_humidity)
        cooling_mode = trial.suggest_int('cooling_mode', 0, 1)
        
        try:
            # 计算历史数据的目标值
            historical_objective = self.calculate_objective_from_historical(
                set_temp, set_humidity, cooling_mode
            )

            # 获取当前系统状态
            current_temps, return_temps, power_values, power_groups, current_humidity, return_humidity = \
                self.controller.get_system_state(current_data)

            # 注意：优化模块不执行实际控制，仅基于历史数据和当前状态进行评估
            # 实际的参数应用由主函数负责

            # 计算当前平均温度和湿度
            avg_temp = sum(current_temps) / len(current_temps) if current_temps else 0
            avg_humidity = sum(current_humidity) / len(current_humidity) if current_humidity else 0

            # 检查安全约束（使用设定值作为预期最终状态）
            if set_temp > self.max_safe_temp:
                return float('inf')
            if not (self.min_safe_humidity <= set_humidity <= self.max_safe_humidity):
                return float('inf')

            # 计算当前功耗
            current_power = sum(power_values) if power_values else 0

            # 组合历史数据和当前数据
            if historical_objective > 0:
                # 如果有历史数据，使用历史权重组合
                combined_objective = (1 - self.historical_weight) * current_power + \
                                   self.historical_weight * historical_objective
            else:
                # 如果没有历史数据，使用当前功耗并增加不确定性惩罚
                combined_objective = current_power * 1.2 if current_power > 0 else 10000.0

            # 记录试验结果
            self.logger.debug(
                f"Trial {trial.number}: temp={set_temp}, humidity={set_humidity}, "
                f"mode={cooling_mode}, objective={combined_objective:.2f} "
                f"(historical={historical_objective:.2f}, current={current_power:.2f})"
            )

            return combined_objective
            
        except Exception as e:
            self.logger.error(f"目标函数评估失败: {str(e)}")
            return float('inf')
    
    def _check_stop_condition(self, study: optuna.Study, trial: optuna.Trial):
        """
        检查停止条件
        
        Args:
            study: Optuna study 对象
            trial: Optuna trial 对象
        """
        if self.controller.stop_event.is_set():
            study.stop()
            self.logger.info("检测到停止信号，终止优化")

