"""
pipeline_template

- 读取 `uid_mapping.json`
- 从 InfluxDB 1.8 拉取时序（设定点 + 温湿度传感器）
- 特征构造（滞后）
- 拟合多输出模型（linear 或 lstsq）
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
from sklearn.preprocessing import StandardScaler
from sklearn.multioutput import MultiOutputRegressor
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


def save_artifacts(model_bundle, metrics: Dict, predictions: pd.DataFrame):
    ARTIFACT_DIR.mkdir(exist_ok=True)
    if model_bundle['type'] == 'linear':
        joblib.dump(model_bundle, ARTIFACT_DIR / 'model_linear.pkl')
    else:
        np.savez(ARTIFACT_DIR / 'model_lstsq.npz', **model_bundle)
    (ARTIFACT_DIR / 'metrics.json').write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding='utf-8')
    predictions.to_csv(ARTIFACT_DIR / 'predictions.csv', index=False, encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', help='ISO8601，如 2024-12-01T00:00:00Z；缺省取当前时间往前一年')
    parser.add_argument('--stop', help='ISO8601；缺省则取当前时间')
    parser.add_argument('--every', default='5m', help='聚合窗口，例如 5m/15m/1h')
    parser.add_argument('--model', choices=['linear', 'lstsq'], default='linear')
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
    else:
        model_bundle = train_lstsq(X_train, Y_train)
        preds = predict_lstsq(model_bundle, X_test)

    metrics = evaluate(Y_test, preds)
    pred_df = pd.DataFrame(preds, columns=target_cols)
    pred_df.insert(0, 'time', test_df['time'].to_numpy())

    save_artifacts(model_bundle, metrics, pred_df)
    print('训练完成，指标：', metrics['overall'])
    print(f'输出目录：{ARTIFACT_DIR}')


if __name__ == '__main__':
    main()
