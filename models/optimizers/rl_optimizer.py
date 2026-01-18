"""
强化学习优化器
使用 PPO (Proximal Policy Optimization) 或 DQN (Deep Q-Network) 算法
"""

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from typing import Dict, Optional, Tuple
from collections import deque
import random
from .base_optimizer import BaseOptimizer


class ACEnvironment:
    """
    空调控制环境
    将空调优化问题建模为强化学习环境
    """
    
    def __init__(self, controller, security_boundary_config: Dict):
        """
        初始化环境
        
        Args:
            controller: ACController 实例
            security_boundary_config: 安全边界配置
        """
        self.controller = controller
        
        # 动作空间：温度、湿度、制冷模式
        self.min_temp = int(security_boundary_config.get("minimum_air_conditioner_setting_temperature", 16))
        self.max_temp = int(security_boundary_config.get("maximum_air_conditioner_setting_temperature", 30))
        self.min_humidity = int(security_boundary_config.get("minimum_air_conditioner_setting_humidity", 30))
        self.max_humidity = int(security_boundary_config.get("maximum_air_conditioner_setting_humidity", 70))
        
        # 安全约束
        self.max_safe_temp = float(security_boundary_config.get("maximum_safe_indoor_temperature", 28.0))
        self.min_safe_humidity = float(security_boundary_config.get("minimum_safe_indoor_humidity", 30.0))
        self.max_safe_humidity = float(security_boundary_config.get("maximum_safe_indoor_humidity", 70.0))
        
        # 状态空间维度：当前温度、当前湿度、当前功耗、设定温度、设定湿度
        self.state_dim = 5
        # 动作空间维度：温度调整、湿度调整、制冷模式
        self.action_dim = 3
        
        self.current_data = None
        self.current_state = None
        
    def reset(self, current_data: pd.DataFrame) -> np.ndarray:
        """
        重置环境
        
        Args:
            current_data: 当前系统状态数据
            
        Returns:
            np.ndarray: 初始状态
        """
        self.current_data = current_data
        
        # 获取当前系统状态
        temps, _, powers, _, humidity, _ = self.controller.get_system_state(current_data)
        
        avg_temp = sum(temps) / len(temps) if temps else 24.0
        avg_humidity = sum(humidity) / len(humidity) if humidity else 50.0
        avg_power = sum(powers) / len(powers) if powers else 0.0
        
        # 状态：[当前温度, 当前湿度, 当前功耗, 设定温度, 设定湿度]
        self.current_state = np.array([
            avg_temp / 30.0,  # 归一化
            avg_humidity / 100.0,
            avg_power / 10000.0,  # 假设最大功耗 10kW
            24.0 / 30.0,  # 初始设定温度
            50.0 / 100.0  # 初始设定湿度
        ], dtype=np.float32)
        
        return self.current_state
    
    def step(self, action: np.ndarray) -> Tuple[np.ndarray, float, bool]:
        """
        执行动作
        
        Args:
            action: 动作数组 [温度调整, 湿度调整, 制冷模式]
            
        Returns:
            Tuple[np.ndarray, float, bool]: (下一个状态, 奖励, 是否结束)
        """
        # 解析动作
        temp_delta = int(action[0] * 5 - 2.5)  # -2 到 +2 度
        humidity_delta = int(action[1] * 10 - 5)  # -5 到 +5 %
        cooling_mode = 1 if action[2] > 0.5 else 0
        
        # 计算新的设定值
        current_set_temp = int(self.current_state[3] * 30.0)
        current_set_humidity = int(self.current_state[4] * 100.0)
        
        new_set_temp = np.clip(current_set_temp + temp_delta, self.min_temp, self.max_temp)
        new_set_humidity = np.clip(current_set_humidity + humidity_delta, self.min_humidity, self.max_humidity)
        
        # 模拟应用设定（实际环境中会调用 controller.apply_settings）
        # 这里我们使用历史数据来估计结果
        
        # 获取新状态
        temps, _, powers, _, humidity, _ = self.controller.get_system_state(self.current_data)
        
        avg_temp = sum(temps) / len(temps) if temps else new_set_temp
        avg_humidity = sum(humidity) / len(humidity) if humidity else new_set_humidity
        avg_power = sum(powers) / len(powers) if powers else 0.0
        
        # 更新状态
        next_state = np.array([
            avg_temp / 30.0,
            avg_humidity / 100.0,
            avg_power / 10000.0,
            new_set_temp / 30.0,
            new_set_humidity / 100.0
        ], dtype=np.float32)
        
        # 计算奖励
        reward = self._calculate_reward(avg_temp, avg_humidity, avg_power)
        
        # 判断是否结束（这里简单设置为 False，实际可以根据时间步数判断）
        done = False
        
        self.current_state = next_state
        
        return next_state, reward, done
    
    def _calculate_reward(self, temp: float, humidity: float, power: float) -> float:
        """
        计算奖励函数
        
        奖励设计：
        - 主要目标：最小化功耗
        - 约束：温度和湿度必须在安全范围内
        
        Args:
            temp: 当前温度
            humidity: 当前湿度
            power: 当前功耗
            
        Returns:
            float: 奖励值
        """
        # 基础奖励：功耗越低越好
        reward = -power / 1000.0  # 归一化
        
        # 惩罚：违反温度约束
        if temp > self.max_safe_temp:
            reward -= 10.0 * (temp - self.max_safe_temp)
        
        # 惩罚：违反湿度约束
        if humidity < self.min_safe_humidity:
            reward -= 5.0 * (self.min_safe_humidity - humidity)
        elif humidity > self.max_safe_humidity:
            reward -= 5.0 * (humidity - self.max_safe_humidity)
        
        return reward


class PolicyNetwork(nn.Module):
    """
    策略网络（Actor）
    """
    
    def __init__(self, state_dim: int, action_dim: int, hidden_dim: int = 128):
        super(PolicyNetwork, self).__init__()
        self.fc1 = nn.Linear(state_dim, hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, hidden_dim)
        self.fc3 = nn.Linear(hidden_dim, action_dim)
        
    def forward(self, state):
        x = torch.relu(self.fc1(state))
        x = torch.relu(self.fc2(x))
        action = torch.sigmoid(self.fc3(x))  # 输出 [0, 1] 范围
        return action


class ValueNetwork(nn.Module):
    """
    价值网络（Critic）
    """
    
    def __init__(self, state_dim: int, hidden_dim: int = 128):
        super(ValueNetwork, self).__init__()
        self.fc1 = nn.Linear(state_dim, hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, hidden_dim)
        self.fc3 = nn.Linear(hidden_dim, 1)
        
    def forward(self, state):
        x = torch.relu(self.fc1(state))
        x = torch.relu(self.fc2(x))
        value = self.fc3(x)
        return value


class RLOptimizer(BaseOptimizer):
    """
    强化学习优化器
    使用 PPO 算法
    """
    
    def __init__(self,
                 controller,
                 parameter_config: Dict,
                 security_boundary_config: Dict):
        """
        初始化强化学习优化器
        
        Args:
            controller: ACController 实例
            parameter_config: 参数配置字典
            security_boundary_config: 安全边界配置字典
        """
        super().__init__(controller, parameter_config, security_boundary_config)
        
        # 从配置文件读取强化学习参数
        opt_config = parameter_config.get("optimization_module", {})
        rl_config = opt_config.get("reinforcement_learning", {})
        
        self.algorithm = rl_config.get("algorithm", "PPO")
        self.learning_rate = float(rl_config.get("learning_rate", 0.0003))
        self.gamma = float(rl_config.get("gamma", 0.99))
        self.episodes = int(rl_config.get("episodes", 100))
        self.max_steps = int(rl_config.get("max_steps_per_episode", 200))
        self.model_save_path = rl_config.get("model_save_path", "./models/rl_optimizer.pth")
        
        # 创建环境
        self.env = ACEnvironment(controller, security_boundary_config)
        
        # 创建网络
        self.policy_net = PolicyNetwork(self.env.state_dim, self.env.action_dim)
        self.value_net = ValueNetwork(self.env.state_dim)
        
        # 优化器
        self.policy_optimizer = optim.Adam(self.policy_net.parameters(), lr=self.learning_rate)
        self.value_optimizer = optim.Adam(self.value_net.parameters(), lr=self.learning_rate)
        
        # 经验回放
        self.memory = deque(maxlen=10000)
        
    def optimize(self, current_data: pd.DataFrame) -> Dict:
        """
        执行强化学习优化
        
        Args:
            current_data: 当前系统状态数据
            
        Returns:
            Dict: 最优参数字典
        """
        self.logger.info(f"开始强化学习优化 ({self.algorithm})...")
        
        best_reward = float('-inf')
        best_action = None
        
        for episode in range(self.episodes):
            # 检查停止信号
            if self.controller.stop_event.is_set():
                self.logger.info("检测到停止信号，中断强化学习优化")
                break
            
            # 重置环境
            state = self.env.reset(current_data)
            episode_reward = 0
            
            for step in range(self.max_steps):
                # 在内层循环也检查停止信号
                if self.controller.stop_event.is_set():
                    self.logger.info("检测到停止信号，中断当前回合")
                    break

                # 选择动作
                with torch.no_grad():
                    state_tensor = torch.FloatTensor(state).unsqueeze(0)
                    action = self.policy_net(state_tensor).squeeze(0).numpy()

                # 执行动作
                next_state, reward, done = self.env.step(action)
                episode_reward += reward

                # 存储经验
                self.memory.append((state, action, reward, next_state, done))

                # 更新状态
                state = next_state

                if done:
                    break
            
            # 训练网络
            if len(self.memory) >= 32:
                self._train_step()
            
            # 记录最佳动作
            if episode_reward > best_reward:
                best_reward = episode_reward
                best_action = action
            
            if episode % 10 == 0:
                self.logger.info(f"Episode {episode}/{self.episodes}, Reward: {episode_reward:.2f}")
        
        # 将最佳动作转换为参数
        if best_action is not None:
            self.best_params = self._action_to_params(best_action, current_data)
        else:
            self.best_params = self.get_best_params()
        
        self.logger.info(f"强化学习优化完成，最优参数: {self.best_params}")
        
        return self.best_params
    
    def _train_step(self):
        """
        训练步骤（PPO 算法）
        """
        # 从经验回放中采样
        batch_size = min(32, len(self.memory))
        batch = random.sample(self.memory, batch_size)
        
        states = torch.FloatTensor([x[0] for x in batch])
        actions = torch.FloatTensor([x[1] for x in batch])
        rewards = torch.FloatTensor([x[2] for x in batch])
        next_states = torch.FloatTensor([x[3] for x in batch])
        
        # 计算价值目标
        with torch.no_grad():
            next_values = self.value_net(next_states).squeeze()
            value_targets = rewards + self.gamma * next_values
        
        # 更新价值网络
        values = self.value_net(states).squeeze()
        value_loss = nn.MSELoss()(values, value_targets)
        
        self.value_optimizer.zero_grad()
        value_loss.backward()
        self.value_optimizer.step()
        
        # 更新策略网络（简化版 PPO）
        predicted_actions = self.policy_net(states)
        advantages = value_targets - values.detach()
        
        policy_loss = -torch.mean(torch.sum(predicted_actions * actions, dim=1) * advantages)
        
        self.policy_optimizer.zero_grad()
        policy_loss.backward()
        self.policy_optimizer.step()
    
    def _action_to_params(self, action: np.ndarray, current_data: pd.DataFrame) -> Dict:
        """
        将动作转换为参数
        
        Args:
            action: 动作数组
            current_data: 当前数据
            
        Returns:
            Dict: 参数字典
        """
        # 获取当前状态
        state = self.env.current_state
        
        set_temp = int(state[3] * 30.0)
        set_humidity = int(state[4] * 100.0)
        cooling_mode = 1 if action[2] > 0.5 else 0
        
        return {
            'set_temp': set_temp,
            'set_humidity': set_humidity,
            'cooling_mode': cooling_mode
        }

