# main.py 重构说明

## 概述

已成功重构 `main.py`，删除了旧版本的预测和优化模块代码，保留了必要的初始化框架，完全适配新的 `uid_config.yaml` 格式。

---

## 重构内容

### ✅ 保留的核心功能

1. **系统初始化**
   - 日志系统初始化
   - 配置文件加载
   - InfluxDB 客户端初始化
   - 资源清理注册

2. **配置管理**
   - 动态配置文件加载
   - 错误处理和验证
   - 配置信息展示

3. **数据读写示例**
   - 完整的使用示例（注释形式）
   - 适配新格式的参数说明

### ❌ 删除的内容

1. **旧的预测模块**
   - 训练逻辑
   - 推理逻辑
   - 参数配置

2. **旧的优化模块**
   - 空调实例管理器
   - 优化循环
   - 参数配置

3. **旧的多线程逻辑**
   - 线程1（实时优化）
   - 线程2（模型训练）
   - 线程3（参考优化）

---

## 文件结构

```python
main.py
├── 导入模块
├── 初始化函数
│   ├── load_configs()      # 加载配置文件
│   └── initialize()        # 系统初始化
├── 执行初始化
├── 数据读写示例（注释）
└── 主程序
    └── main()              # 主程序入口
```

---

## 使用说明

### 1. 启动程序

```bash
python main.py
```

### 2. 输出示例

```
============================================================
✓ 系统初始化完成
✓ 机房: 1号楼IDC机房
✓ 空调数量: 92
============================================================

✓ 系统运行中...
✓ 按 Ctrl+C 停止程序
```

### 3. 日志输出

日志文件位置：`logs/run.log`

```
2025-10-30 10:00:00 - INFO - ============================================================
2025-10-30 10:00:00 - INFO - 系统启动
2025-10-30 10:00:00 - INFO - ============================================================
2025-10-30 10:00:00 - INFO - 成功初始化日志系统
2025-10-30 10:00:01 - INFO - 开始加载配置文件...
2025-10-30 10:00:01 - INFO - 成功加载配置文件: ['influxdb', 'security_boundary', 'uid']
2025-10-30 10:00:01 - INFO - 机房: 1号楼IDC机房, 空调数量: 92
2025-10-30 10:00:02 - INFO - 开始初始化 InfluxDB 客户端...
2025-10-30 10:00:02 - INFO - 成功初始化 InfluxDB 客户端
2025-10-30 10:00:02 - INFO - ============================================================
2025-10-30 10:00:02 - INFO - 系统初始化完成
2025-10-30 10:00:02 - INFO - ============================================================
2025-10-30 10:00:02 - INFO - 主程序开始运行
```

---

## 核心代码说明

### 1. 配置文件加载

```python
def load_configs():
    """加载所有配置文件"""
    config_dir = project_root / "configs"
    
    configs = {}
    config_files = {
        'influxdb': 'influxdb_config.yaml',
        'security_boundary': 'security_boundary_config.yaml',
        'uid': 'uid_config.yaml'
    }
    
    for config_name, filename in config_files.items():
        config_path = config_dir / filename
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                configs[config_name] = yaml.safe_load(f)
        else:
            raise FileNotFoundError(f"配置文件不存在: {config_path}")
    
    return configs
```

**特点：**
- 动态加载配置
- 文件存在性检查
- 清晰的错误提示

---

### 2. 系统初始化

```python
def initialize():
    """初始化系统"""
    # 1. 初始化日志
    logger = initialization.init_logger()
    
    # 2. 加载配置文件
    configs = load_configs()
    
    # 3. 初始化数据库客户端
    dc_status_data_client, prediction_data_client, \
    setting_data_client, reference_data_client = \
        initialization.init_influxdb_client(configs['influxdb'])
    
    # 4. 注册资源清理
    atexit.register(lambda: [client.close() for client in [...]])
    
    # 5. 返回所有对象
    return logger, configs, clients
```

**特点：**
- 步骤清晰
- 自动资源清理
- 完整的日志记录

---

### 3. 全局变量

```python
# 执行初始化
logger, configs, clients = initialize()

# 提取常用配置
influxdb_config = configs['influxdb']
uid_config = configs['uid']
security_boundary_config = configs['security_boundary']

# 客户端字典
clients = {
    'dc_status': dc_status_data_client,
    'prediction': prediction_data_client,
    'setting': setting_data_client,
    'reference': reference_data_client
}
```

**用法：**
```python
# 访问配置
room_name = uid_config['room_name']

# 访问客户端
data = data_reading_writing.reading_data_query(
    influxdb_config,
    uid_config,
    clients['dc_status'],  # 使用客户端
    query_range="-1h"
)
```

---

## 数据读写示例

### 读取数据（新格式）

```python
# 查询所有测点
query_result = data_reading_writing.reading_data_query(
    influxdb_config, 
    uid_config,
    clients['dc_status'],
    query_range="-1h",
    query_measurement=None,  # None = 查询所有
    enable_unified_sampling=True,
    target_interval_seconds=30
)

# 查询特定测点
query_result = data_reading_writing.reading_data_query(
    influxdb_config, 
    uid_config,
    clients['dc_status'],
    query_range="-1h",
    query_measurement=['温度设定值', '湿度设置值'],  # 指定测点
    enable_unified_sampling=True,
    target_interval_seconds=30
)
```

---

### 写入数据（新格式）

```python
# 构建数据字典（新格式）
setting_data = {
    "佳力图KN10空调4-3-9": {
        "温度设定值": 25.0,
        "湿度设置值": 50.0,
        "开关机命令": 1
    },
    "艾特空调4-1-4": {
        "送风温度设置点": 26.0,
        "湿度设定点": 55.0,
        "监控开关机": 1
    }
}

# 写入数据库
data_reading_writing.setting_data_writing(
    influxdb_config, 
    uid_config, 
    setting_data, 
    clients['setting']
)
```

---

## 后续开发指南

### 1. 添加预测模块

```python
# 在 modules/prediction_module.py 中实现
def start_prediction_training(uid_config, training_data, logger):
    """训练预测模型"""
    pass

def start_prediction_inference(uid_config, inference_data, logger):
    """执行预测推理"""
    pass
```

**在 main.py 中调用：**
```python
from modules import prediction_module

# 训练
prediction_module.start_prediction_training(
    uid_config=uid_config,
    training_data=training_data,
    logger=logger
)

# 推理
result = prediction_module.start_prediction_inference(
    uid_config=uid_config,
    inference_data=inference_data,
    logger=logger
)
```

---

### 2. 添加优化模块

```python
# 在 modules/optimization_module.py 中实现
def start_optimization_process(uid_config, optimization_input, logger):
    """执行优化"""
    pass
```

**在 main.py 中调用：**
```python
from modules import optimization_module

result = optimization_module.start_optimization_process(
    uid_config=uid_config,
    optimization_input=optimization_input,
    logger=logger
)
```

---

### 3. 添加多线程

```python
def main():
    """主程序入口"""
    logger.info("主程序开始运行")
    
    # 创建线程
    thread_1 = Thread(target=optimization_thread)
    thread_2 = Thread(target=training_thread)
    thread_3 = Thread(target=prediction_thread)
    
    # 设置为守护线程
    thread_1.daemon = True
    thread_2.daemon = True
    thread_3.daemon = True
    
    # 启动线程
    thread_1.start()
    thread_2.start()
    thread_3.start()
    
    # 保持主线程运行
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("程序终止")
```

---

## 优势

### ✅ 清晰的结构
- 功能模块化
- 代码易读易维护
- 注释详细

### ✅ 完全适配新格式
- 支持新的 uid_config.yaml
- 兼容旧格式
- 自动检测格式类型

### ✅ 良好的扩展性
- 易于添加新模块
- 清晰的接口定义
- 完整的示例代码

### ✅ 健壮的错误处理
- 配置文件验证
- 资源自动清理
- 完整的日志记录

---

## 配置文件要求

### 必须存在的配置文件

1. **configs/influxdb_config.yaml** - 数据库配置
2. **configs/uid_config.yaml** - UID 配置（新格式）
3. **configs/security_boundary_config.yaml** - 安全边界配置

### 可选的配置文件

- **configs/parameter_config.yaml** - 参数配置（如需要预测/优化模块）

---

## 测试建议

### 1. 测试初始化

```bash
python main.py
```

检查是否正确输出：
- ✓ 系统初始化完成
- ✓ 机房名称
- ✓ 空调数量

### 2. 测试数据读取

取消注释示例代码中的数据读取部分：

```python
query_result = data_reading_writing.reading_data_query(
    influxdb_config, 
    uid_config,
    clients['dc_status'],
    query_range="-1h",
    query_measurement=None,
    enable_unified_sampling=True,
    target_interval_seconds=30
)
logger.info(f"查询到 {len(query_result)} 条数据")
```

### 3. 测试数据写入

取消注释示例代码中的数据写入部分。

---

## 常见问题

### Q: 如何添加新的配置文件？

A: 在 `load_configs()` 函数中添加：

```python
config_files = {
    'influxdb': 'influxdb_config.yaml',
    'security_boundary': 'security_boundary_config.yaml',
    'uid': 'uid_config.yaml',
    'my_config': 'my_config.yaml'  # 新增
}
```

### Q: 如何访问空调配置？

A: 使用新格式的配置：

```python
air_conditioners = uid_config['air_conditioners']

# 遍历所有空调
for ac_name, ac_info in air_conditioners.items():
    device_name = ac_info['device_name']
    measurement_points = ac_info['measurement_points']
    print(f"{device_name}: {len(measurement_points)} 个测点")
```

### Q: 如何在后台运行？

A: Linux/macOS:
```bash
nohup python main.py > output.log 2>&1 &
```

Windows:
```powershell
Start-Process python -ArgumentList "main.py" -WindowStyle Hidden
```

---

## 总结

✅ **重构完成！**

- 删除了所有旧的预测和优化模块代码
- 保留了必要的初始化框架
- 完全适配新的配置格式
- 提供了清晰的扩展接口
- 包含完整的使用示例

现在您可以：
1. 直接运行 `main.py` 测试初始化
2. 根据需要添加预测模块
3. 根据需要添加优化模块
4. 使用提供的示例代码进行数据读写

---

**更新时间：** 2025-10-30  
**版本：** v2.0

