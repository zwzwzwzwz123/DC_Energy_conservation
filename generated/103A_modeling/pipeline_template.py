"""
pipeline_template

- 读取 `uid_mapping.json`
- 从 InfluxDB 1.8 拉取时序（设定点 + 温湿度传感器）
- 特征构造（滞后）
- 拟合多输出模型（linear / lstsq / mlp / lstm）
- 输出模型、评估指标、预测结果
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.tree import DecisionTreeRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.multioutput import MultiOutputRegressor
from sklearn.neural_network import MLPRegressor
import joblib
import yaml
from influxdb import InfluxDBClient

MAPPING_PATH = Path(__file__).with_name('uid_mapping.json')
ARTIFACT_DIR = Path(__file__).with_name('artifacts')
ARTIFACT_DIR.mkdir(exist_ok=True)
# project root is two levels up from this file (generated/103A_modeling)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
UTILS_CONFIG_PATH = PROJECT_ROOT / 'configs' / 'utils_config.yaml'


def load_mapping(path: Path) -> Dict:
    if not path.exists():
        raise FileNotFoundError(f'缺少映射文件: {path}, 请先运行 uid_mapping_builder.py')
    return json.loads(path.read_text(encoding='utf-8'))


def load_influx_credentials(client_key: str) -> Dict:
    if not UTILS_CONFIG_PATH.exists():
        raise FileNotFoundError(f'未找到 Influx 配置: {UTILS_CONFIG_PATH}')
    cfg = yaml.safe_load(UTILS_CONFIG_PATH.read_text(encoding='utf-8')) or {}
    influx_cfg = cfg.get('InfluxDB', {})
    common = influx_cfg.get('_common', {})
    client_cfg = influx_cfg.get(client_key, {})
    merged = {**common, **client_cfg}
    required = ['host', 'port', 'username', 'password', 'database']
    missing = [k for k in required if k not in merged]
    if missing:
        raise KeyError(f'Influx 配置缺少字段: {missing}')
    return merged


def build_query(uid: str, start: str, stop: str, every: str, field: str, measurement: str) -> str:
    """
    measurement 默认为 uid（与写入测点同名）。按时间窗口做 mean 聚合。
    """
    return (
        f'SELECT mean("{field}") AS value '
        f'FROM "{measurement}" '
        f"WHERE time >= '{start}' AND time <= '{stop}' "
        f"GROUP BY time({every}) fill(null)"
    )


def _query_one_uid(client: InfluxDBClient, uid: str, start: str, stop: str, every: str,
                   field: str, measurement_template: str) -> pd.DataFrame:
    measurement = measurement_template.format(uid=uid)
    q = build_query(uid, start, stop, every, field, measurement)
    result = client.query(q)
    points = list(result.get_points())
    if not points:
        return pd.DataFrame(columns=['time', uid])
    df = pd.DataFrame(points)
    if df.empty:
        return pd.DataFrame(columns=['time', uid])
    # Influx 返回列名为 'time' 和 'value'
    df = df.rename(columns={'value': uid})
    return df[['time', uid]]


def fetch_timeseries(uids: List[str], start: str, stop: str, every: str,
                     field: str, measurement_template: str, client_key: str) -> pd.DataFrame:
    creds = load_influx_credentials(client_key)
    client = InfluxDBClient(
        host=creds['host'],
        port=creds['port'],
        username=creds['username'],
        password=creds['password'],
        database=creds['database'],
        timeout=10,
    )
    dfs: List[pd.DataFrame] = []
    for uid in uids:
        dfs.append(_query_one_uid(client, uid, start, stop, every, field, measurement_template))
    client.close()
    if not dfs:
        return pd.DataFrame()
    merged = dfs[0]
    for df in dfs[1:]:
        merged = merged.merge(df, on='time', how='outer')
    merged = merged.sort_values('time').reset_index(drop=True)
    return merged


def fill_timeseries(df: pd.DataFrame) -> pd.DataFrame:
    """Fill missing values per column to avoid losing全部样本."""
    if df.empty:
        return df
    filled = df.sort_values('time').reset_index(drop=True).copy()
    for col in filled.columns:
        if col == 'time':
            continue
        series = filled[col]
        if series.notna().sum() == 0:
            # 保留全空列，由后续检查统一处理
            continue
        filled[col] = series.ffill().bfill()
    return filled


def build_feature_matrix(ac_df: pd.DataFrame, lags: int = 3) -> pd.DataFrame:
    feat = ac_df.copy().sort_values('time').reset_index(drop=True)
    for col in feat.columns:
        if col == 'time':
            continue
        for k in range(1, lags + 1):
            feat[f'{col}_lag{k}'] = feat[col].shift(k)
    feat = feat.dropna().reset_index(drop=True)
    return feat


def align_and_join(ac_feat: pd.DataFrame, sensor_df: pd.DataFrame) -> pd.DataFrame:
    df = ac_feat.merge(sensor_df, on='time', how='inner')
    df = df.dropna().reset_index(drop=True)
    return df


def train_linear(X: np.ndarray, Y: np.ndarray):
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    model = MultiOutputRegressor(LinearRegression())
    model.fit(Xs, Y)
    return {'type': 'linear', 'scaler': scaler, 'model': model}


def predict_linear(model_bundle, X: np.ndarray) -> np.ndarray:
    Xs = model_bundle['scaler'].transform(X)
    return model_bundle['model'].predict(Xs)


def train_lstsq(X: np.ndarray, Y: np.ndarray):
    # 添加截距项，避免强制过原点
    Xb = np.hstack([np.ones((X.shape[0], 1)), X])
    coef, _, _, _ = np.linalg.lstsq(Xb, Y, rcond=None)
    return {'type': 'lstsq', 'coef': coef}


def predict_lstsq(model_bundle, X: np.ndarray) -> np.ndarray:
    Xb = np.hstack([np.ones((X.shape[0], 1)), X])
    return Xb @ model_bundle['coef']


def train_mlp(X: np.ndarray, Y: np.ndarray):
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    model = MLPRegressor(
        hidden_layer_sizes=(256, 128),
        activation='relu',
        max_iter=800,
        alpha=1e-4,
        early_stopping=True,
        random_state=42,
    )
    model.fit(Xs, Y)
    return {'type': 'mlp', 'scaler': scaler, 'model': model}


def predict_mlp(model_bundle, X: np.ndarray) -> np.ndarray:
    Xs = model_bundle['scaler'].transform(X)
    return model_bundle['model'].predict(Xs)


def train_lstm(X: np.ndarray, Y: np.ndarray, epochs: int = 80, lr: float = 1e-3, hidden_size: int = 64):
    try:
        import torch
        from torch import nn
    except ImportError as exc:
        raise ImportError("缺少依赖 torch，无法使用 lstm 模型；请安装 torch") from exc

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)

    # 将特征视为单步序列（滞后信息已在特征中编码）
    X_tensor = torch.tensor(Xs, dtype=torch.float32).unsqueeze(1).to(device)  # (batch, seq=1, feat)
    Y_tensor = torch.tensor(Y, dtype=torch.float32).to(device)

    input_dim = X.shape[1]
    output_dim = Y.shape[1]

    class LSTMReg(nn.Module):
        def __init__(self, input_dim, hidden_size, output_dim):
            super().__init__()
            self.lstm = nn.LSTM(input_size=input_dim, hidden_size=hidden_size, batch_first=True)
            self.fc = nn.Linear(hidden_size, output_dim)

        def forward(self, x):
            out, _ = self.lstm(x)
            # 取最后时间步（这里只有 1 步）
            out = out[:, -1, :]
            return self.fc(out)

    model = LSTMReg(input_dim, hidden_size, output_dim).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = nn.MSELoss()

    model.train()
    batch_size = min(256, len(X_tensor))
    for epoch in range(epochs):
        perm = torch.randperm(len(X_tensor))
        for i in range(0, len(X_tensor), batch_size):
            idx = perm[i:i + batch_size]
            xb = X_tensor[idx]
            yb = Y_tensor[idx]
            optimizer.zero_grad()
            pred = model(xb)
            loss = criterion(pred, yb)
            loss.backward()
            optimizer.step()

    return {
        'type': 'lstm',
        'scaler': scaler,
        'state_dict': model.state_dict(),
        'hidden_size': hidden_size,
        'input_dim': input_dim,
        'output_dim': output_dim,
        'device': str(device),
    }


def predict_lstm(model_bundle, X: np.ndarray) -> np.ndarray:
    import torch
    from torch import nn

    scaler = model_bundle['scaler']
    input_dim = model_bundle['input_dim']
    hidden_size = model_bundle['hidden_size']
    output_dim = model_bundle['output_dim']
    state_dict = model_bundle['state_dict']

    class LSTMReg(nn.Module):
        def __init__(self, input_dim, hidden_size, output_dim):
            super().__init__()
            self.lstm = nn.LSTM(input_size=input_dim, hidden_size=hidden_size, batch_first=True)
            self.fc = nn.Linear(hidden_size, output_dim)

        def forward(self, x):
            out, _ = self.lstm(x)
            out = out[:, -1, :]
            return self.fc(out)

    device = torch.device(model_bundle.get('device', 'cpu'))
    model = LSTMReg(input_dim, hidden_size, output_dim).to(device)
    model.load_state_dict(state_dict)

    Xs = scaler.transform(X)
    X_tensor = torch.tensor(Xs, dtype=torch.float32).unsqueeze(1).to(device)
    model.eval()
    with torch.no_grad():
        preds = model(X_tensor).cpu().numpy()
    return preds


def train_decision_tree(X: np.ndarray, Y: np.ndarray):
    model = MultiOutputRegressor(
        DecisionTreeRegressor(
            random_state=42,
            max_depth=12,
            min_samples_leaf=2,
        )
    )
    model.fit(X, Y)
    return {'type': 'dt', 'model': model}


def predict_decision_tree(model_bundle, X: np.ndarray) -> np.ndarray:
    return model_bundle['model'].predict(X)


def train_random_forest(X: np.ndarray, Y: np.ndarray):
    model = MultiOutputRegressor(
        RandomForestRegressor(
            n_estimators=300,
            max_depth=12,
            min_samples_leaf=2,
            max_features='sqrt',
            random_state=42,
            n_jobs=-1,
        )
    )
    model.fit(X, Y)
    return {'type': 'rf', 'model': model}


def predict_random_forest(model_bundle, X: np.ndarray) -> np.ndarray:
    return model_bundle['model'].predict(X)


def train_xgb(X: np.ndarray, Y: np.ndarray):
    try:
        import xgboost as xgb
    except ImportError as exc:
        raise ImportError("缺少依赖 xgboost，无法使用 xgb 模型；请安装 xgboost") from exc

    base = xgb.XGBRegressor(
        n_estimators=500,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.9,
        colsample_bytree=0.9,
        min_child_weight=1.0,
        reg_lambda=1.0,
        reg_alpha=0.0,
        random_state=42,
        n_jobs=-1,
        objective='reg:squarederror',
    )
    model = MultiOutputRegressor(base)
    model.fit(X, Y)
    return {'type': 'xgb', 'model': model}


def predict_xgb(model_bundle, X: np.ndarray) -> np.ndarray:
    return model_bundle['model'].predict(X)


def train_lgbm(X: np.ndarray, Y: np.ndarray):
    try:
        import lightgbm as lgb
    except ImportError as exc:
        raise ImportError("缺少依赖 lightgbm，无法使用 lgbm 模型；请安装 lightgbm") from exc

    base = lgb.LGBMRegressor(
        n_estimators=500,
        learning_rate=0.05,
        num_leaves=63,
        max_depth=-1,
        subsample=0.9,
        colsample_bytree=0.9,
        bagging_freq=1,
        reg_lambda=1.0,
        random_state=42,
    )
    model = MultiOutputRegressor(base)
    model.fit(X, Y)
    return {'type': 'lgbm', 'model': model}


def predict_lgbm(model_bundle, X: np.ndarray) -> np.ndarray:
    return model_bundle['model'].predict(X)


def train_catboost(X: np.ndarray, Y: np.ndarray):
    try:
        import catboost
    except ImportError as exc:
        raise ImportError("缺少依赖 catboost，无法使用 cat 模型；请安装 catboost") from exc

    base = catboost.CatBoostRegressor(
        iterations=600,
        depth=7,
        learning_rate=0.05,
        loss_function='RMSE',
        l2_leaf_reg=3.0,
        random_seed=42,
        verbose=False,
    )
    model = MultiOutputRegressor(base)
    model.fit(X, Y)
    return {'type': 'cat', 'model': model}


def predict_catboost(model_bundle, X: np.ndarray) -> np.ndarray:
    return model_bundle['model'].predict(X)


def evaluate(y_true: np.ndarray, y_pred: np.ndarray) -> Dict:
    mse = np.mean((y_true - y_pred) ** 2, axis=0).tolist()
    mae = np.mean(np.abs(y_true - y_pred), axis=0).tolist()
    overall = {
        'mse_mean': float(np.mean(mse)),
        'mae_mean': float(np.mean(mae)),
    }
    return {'per_target_mse': mse, 'per_target_mae': mae, 'overall': overall}


def split_train_test(dataset: pd.DataFrame, test_ratio: float = 0.2):
    """Chronological split to avoid泄漏."""
    n = len(dataset)
    test_size = max(1, int(n * test_ratio))
    train_size = n - test_size
    if train_size <= 0:
        raise RuntimeError('样本过少，无法划分训练/验证集')
    train = dataset.iloc[:train_size].reset_index(drop=True)
    test = dataset.iloc[train_size:].reset_index(drop=True)
    return train, test


def save_artifacts(model_bundle, metrics: Dict, predictions: pd.DataFrame, model_name: str):
    ARTIFACT_DIR.mkdir(exist_ok=True)
    mtype = model_name or model_bundle.get('type', 'model')
    if mtype == 'linear':
        joblib.dump(model_bundle, ARTIFACT_DIR / 'model_linear.pkl')
    elif mtype == 'mlp':
        joblib.dump(model_bundle, ARTIFACT_DIR / 'model_mlp.pkl')
    elif mtype == 'lstm':
        # 保存 state_dict + scaler，避免本地类无法 pickle 的问题
        joblib.dump(model_bundle, ARTIFACT_DIR / 'model_lstm.pkl')
    elif mtype == 'rf':
        joblib.dump(model_bundle, ARTIFACT_DIR / 'model_rf.pkl')
    elif mtype == 'dt':
        joblib.dump(model_bundle, ARTIFACT_DIR / 'model_dt.pkl')
    elif mtype == 'xgb':
        joblib.dump(model_bundle, ARTIFACT_DIR / 'model_xgb.pkl')
    elif mtype == 'lgbm':
        joblib.dump(model_bundle, ARTIFACT_DIR / 'model_lgbm.pkl')
    elif mtype == 'cat':
        joblib.dump(model_bundle, ARTIFACT_DIR / 'model_cat.pkl')
    else:
        np.savez(ARTIFACT_DIR / 'model_lstsq.npz', **model_bundle)
    (ARTIFACT_DIR / f'metrics_{mtype}.json').write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding='utf-8')
    predictions.to_csv(ARTIFACT_DIR / f'predictions_{mtype}.csv', index=False, encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', help='ISO8601，如 2024-12-01T00:00:00Z；缺省取当前时间往前一年')
    parser.add_argument('--stop', help='ISO8601；缺省则取当前时间')
    parser.add_argument('--every', default='5m', help='聚合窗口，例如 5m/15m/1h')
    parser.add_argument('--model', choices=['linear', 'lstsq', 'mlp', 'lstm', 'rf', 'dt', 'xgb', 'lgbm', 'cat'], default='linear')
    parser.add_argument('--lags', type=int, default=3, help='设定点滞后阶数')
    parser.add_argument('--field', default='value', help='Influx 数值字段名，默认 value')
    parser.add_argument('--measurement-template', default='{uid}',
                        help='measurement 模板，默认与 uid 同名，可用 {uid} 占位')
    parser.add_argument('--client-key', default='influxdb_dc_status_data',
                        help='使用 utils_config.yaml 中的客户端键名，默认 influxdb_dc_status_data')
    args = parser.parse_args()

    # 默认时间范围：stop=当前UTC，start=往前一年
    now_utc = datetime.now(timezone.utc).replace(microsecond=0)
    stop = args.stop or now_utc.isoformat().replace('+00:00', 'Z')
    start = args.start or (now_utc - timedelta(days=365)).isoformat().replace('+00:00', 'Z')

    mapping = load_mapping(MAPPING_PATH)
    sensor_uids = [r['uid'] for r in mapping.get('sensors', [])]
    ac_requests = []
    for ac_no, items in mapping.get('air_conditioners', {}).items():
        for it in items:
            param_uid = it.get('param')
            if not param_uid:
                continue
            tag = it.get('tag')
            col_name = f"ac{ac_no}_{tag}" if tag else f"ac{ac_no}_{param_uid}"
            ac_requests.append((param_uid, col_name))

    if not sensor_uids or not ac_requests:
        raise RuntimeError('映射中缺少传感器或空调设定点，请检查 uid_mapping.json')

    ac_uids = [u for u, _ in ac_requests]
    ac_col_rename = {u: col for u, col in ac_requests}

    print(f'拉取空调设定点 {len(ac_uids)} 个，传感器 {len(sensor_uids)} 个，时间范围 {start} ~ {stop}')
    ac_df = fetch_timeseries(ac_uids, start, stop, args.every,
                             field=args.field, measurement_template=args.measurement_template,
                             client_key=args.client_key)
    sensor_df = fetch_timeseries(sensor_uids, start, stop, args.every,
                                 field=args.field, measurement_template=args.measurement_template,
                                 client_key=args.client_key)

    # 填补缺失，避免内连接后样本过少
    ac_df = fill_timeseries(ac_df)
    sensor_df = fill_timeseries(sensor_df)

    # 将空调列名重命名为带 ac 编号的唯一名称，避免 merge 时列冲突
    if not ac_df.empty:
        ac_df = ac_df.rename(columns=ac_col_rename)

    if ac_df.empty or sensor_df.empty:
        raise RuntimeError('Influx 数据为空，请检查 measurement/field 或时间范围/客户端配置')

    ac_feat = build_feature_matrix(ac_df, lags=args.lags)
    dataset = align_and_join(ac_feat, sensor_df)
    if dataset.empty:
        raise RuntimeError('对齐后数据为空，可能是时间窗口或聚合粒度不匹配')

    feature_cols = [c for c in ac_feat.columns if c != 'time']
    target_cols = [c for c in sensor_df.columns if c != 'time']

    # 检查传感器/设定点是否全空
    for col in feature_cols + target_cols:
        if dataset[col].notna().sum() == 0:
            raise RuntimeError(f'列 {col} 全为空，无法训练，请检查 Influx 配置或时间范围')

    train_df, test_df = split_train_test(dataset, test_ratio=0.2)

    X_train = train_df[feature_cols].to_numpy()
    Y_train = train_df[target_cols].to_numpy()
    X_test = test_df[feature_cols].to_numpy()
    Y_test = test_df[target_cols].to_numpy()

    if args.model == 'linear':
        model_bundle = train_linear(X_train, Y_train)
        preds = predict_linear(model_bundle, X_test)
    elif args.model == 'lstsq':
        model_bundle = train_lstsq(X_train, Y_train)
        preds = predict_lstsq(model_bundle, X_test)
    elif args.model == 'mlp':
        model_bundle = train_mlp(X_train, Y_train)
        preds = predict_mlp(model_bundle, X_test)
    elif args.model == 'lstm':
        model_bundle = train_lstm(X_train, Y_train)
        preds = predict_lstm(model_bundle, X_test)
    elif args.model == 'rf':
        model_bundle = train_random_forest(X_train, Y_train)
        preds = predict_random_forest(model_bundle, X_test)
    elif args.model == 'dt':
        model_bundle = train_decision_tree(X_train, Y_train)
        preds = predict_decision_tree(model_bundle, X_test)
    elif args.model == 'xgb':
        model_bundle = train_xgb(X_train, Y_train)
        preds = predict_xgb(model_bundle, X_test)
    elif args.model == 'lgbm':
        model_bundle = train_lgbm(X_train, Y_train)
        preds = predict_lgbm(model_bundle, X_test)
    else:  # cat
        model_bundle = train_catboost(X_train, Y_train)
        preds = predict_catboost(model_bundle, X_test)

    metrics = evaluate(Y_test, preds)
    pred_df = pd.DataFrame(preds, columns=target_cols)
    pred_df.insert(0, 'time', test_df['time'].to_numpy())

    save_artifacts(model_bundle, metrics, pred_df, model_name=args.model)
    print('训练完成，指标：', metrics['overall'])
    print(f'输出目录：{ARTIFACT_DIR}')


if __name__ == '__main__':
    main()
