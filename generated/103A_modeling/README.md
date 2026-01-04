# 103A 机房建模脚手架

本目录文件均为新增，不修改现有代码。包含：
- `uid_mapping_builder.py`：解析 `uid/103A机房建模信息整理xlsx.xlsx`，导出点位映射（json/csv）。
- `pipeline_template.py`：从 InfluxDB 拉取历史数据、特征构造、训练并预测温湿度（示例用 sklearn 线性回归 + numpy 最小二乘）。
- `uid_mapping.json` / `uid_mapping.csv`：运行 builder 后生成。

## 使用步骤
1. 生成点位映射
   ```bash
   python generated/103A_modeling/uid_mapping_builder.py
   ```
   输出：`generated/103A_modeling/uid_mapping.json` 和 `uid_mapping.csv`。

2. 配置 InfluxDB 连接与 bucket
   编辑 `pipeline_template.py` 顶部的 `INFLUX_CONFIG`，填写 url/token/org/bucket。

3. 训练并预测
   ```bash
   python generated/103A_modeling/pipeline_template.py --start "2024-12-01T00:00:00Z" --stop "2024-12-31T00:00:00Z" --model linear
   ```
   - `--model linear`：sklearn LinearRegression（带标准化）。
   - `--model lstsq`：numpy 最小二乘，适合快速试验。
   - 输出：`artifacts/model.pkl`、`artifacts/metrics.json`、`artifacts/predictions.parquet`。
   - Influx 1.8 连接复用 `configs/utils_config.yaml`，默认客户端键为 `influxdb_dc_status_data`，默认 measurement 模板 `{uid}`、字段 `value`。如需修改，命令行加 `--client-key`、`--measurement-template`、`--field`。

4. 后续扩展
   - 可替换特征工程或模型（如 XGBoost/GBDT），保持输入输出接口一致。
   - 如需多目标协调（温度+湿度），保持传感器列表顺序一致即可。
   - 当前 Influx 连接已更新为 `http://127.0.0.1:8077`（admin / Laimi@12345），历史数据范围 2025-10-30 ～ 2025-12-12，可按需调整 start/stop。

## 数据与特征
- 传感器：33 个温湿度点（热/冷通道 1~33，对应 uid/标签）。
- 空调设定：9 台空调 × 4 个设定点（回风湿度/回风温度/平均温度/最高温度），标签规则 `N2_S0_E{1-9}_A27/A28/A30/A31`。
- 额外点位：20 个列头柜回路（如后续需能耗关联，可自行加入）。

## 训练是否需要？
需要。模板会：
- 从 InfluxDB 拉取历史时序（设定点 + 传感器）。
- 对设定点做滞后特征（默认 3 个时间滞后）。
- 拟合传感器温度/湿度，输出模型与评估指标。

## 依赖
- pandas, numpy, scikit-learn, influxdb, PyYAML, pyarrow（导出 parquet）。
- 运行前：`pip install pandas numpy scikit-learn influxdb PyYAML pyarrow joblib`。
