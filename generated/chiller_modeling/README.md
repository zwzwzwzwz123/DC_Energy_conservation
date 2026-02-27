# 冷水机组建模脚本

本目录与 103A 机房建模分开，针对 `uid/冷水机组BA系统信息.xlsx` 的输入/输出测点。
- `uid_mapping_builder_chiller.py`：解析 Excel（sheet1=输入，sheet2=输出），生成 `uid_mapping_chiller.json` / `uid_mapping_chiller.csv`。
- `train_chiller_model.py`：读取映射，从 InfluxDB 拉取输入/输出时序，构造滞后/序列特征并训练模型（linear / lstsq / mlp / rf / xgb / lstm / gru / transformer / patchtst）。产出模型、指标、预测。
- `dump_raw_timeseries_chiller.py`：按映射拉取原始（未聚合）时序，导出长表 CSV，便于数据检查。
- `uid_mapping_chiller.json` / `uid_mapping_chiller.csv`：运行 builder 后生成。
- `artifacts_chiller/`：训练脚本输出模型与结果。

## 使用步骤
1. 生成映射  
   ```bash
   python generated/chiller_modeling/uid_mapping_builder_chiller.py
   ```

2. 配置 InfluxDB  
   编辑 `configs/utils_config.yaml`，补充 `_common` 或 `influxdb_dc_status_data` 的 host/port/username/password/database。

3. 训练示例（常规回归，同步对齐）  
   ```bash
   python generated/chiller_modeling/train_chiller_model.py \
     --start "2024-12-01T00:00:00Z" \
     --stop "2024-12-31T00:00:00Z" \
     --every "5m" \
     --model rf \
     --lags 2
   ```
   - `--model`：linear / lstsq / mlp / rf / xgb / lstm / gru / transformer / patchtst  
   - `--measurement-template`：默认 `{uid}`，可按需改为模板字符串。  
   - `--field`：Influx 数值字段名，默认 `value`。  
   - 滞后策略：自动对“运行/启停/状态/模式/变频/频率/开度/给定/设定/阀/泵/塔/机组/开关”等控制/状态类列加滞后，其余只用当前值；可用 `--lags` 设定滞后阶数，设 0 可关闭（仅在非时序模型场景作用于输入列）。

4. LSTM/GRU/Transformer/PatchTST（自动启用时序模式：特征时间 t -> 目标时间 t+1Δ...t+7Δ，含输出自回归）  
   ```bash
   python generated/chiller_modeling/train_chiller_model.py \
     --start "2024-12-01T00:00:00Z" \
     --stop "2024-12-31T00:00:00Z" \
     --every "5m" \
     --model lstm \
     --seq-len 21 \
     --target-lags 7 \
     --horizon "5m"
   ```
   - 选择 `--model lstm/gru/transformer/patchtst` 自动：多步预测 t+1Δ...t+7Δ，输出历史（`--target-lags`）作为特征，`--seq-len` 作为序列长度（建议窗口=seq-len×every，例如 21×5m≈1.75h）。  
   - `--horizon` 表示单步间隔 Δ（默认等于 `--every`），预测步数固定为 7。  
   - 其他模型仍按同步回归方式（不平移目标）。

5. 导出原始数据（长表）  
   ```bash
   python generated/chiller_modeling/dump_raw_timeseries_chiller.py --start "2024-12-01T00:00:00Z" --stop "2024-12-31T00:00:00Z"
   ```
   - 输出：`generated/chiller_modeling/artifacts_chiller/raw_timeseries.csv`（列：time, uid, value）

> 训练前请确保 Excel 已更新、映射已重建，避免旧 UID 造成空数据。
