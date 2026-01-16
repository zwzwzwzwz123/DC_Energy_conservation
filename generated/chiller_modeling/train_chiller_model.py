"""
Chiller modeling pipeline

- Uses uid_mapping_chiller.json to determine inputs/outputs (sheet1/2 of 冷水机组BA系统信息.xlsx).
- Pulls timeseries from InfluxDB (1.8) with configurable measurement template/field.
- Builds lag features on inputs and trains selectable models (linear / lstsq / mlp / rf / xgb).
- Writes artifacts to generated/chiller_modeling/artifacts_chiller.
"""
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd
import yaml
from influxdb import InfluxDBClient
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.multioutput import MultiOutputRegressor
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler

MAPPING_PATH = Path(__file__).with_name("uid_mapping_chiller.json")
ARTIFACT_DIR = Path(__file__).with_name("artifacts_chiller")
ARTIFACT_DIR.mkdir(exist_ok=True)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
UTILS_CONFIG_PATH = PROJECT_ROOT / "configs" / "utils_config.yaml"


def load_mapping(path: Path) -> Dict:
    if not path.exists():
        raise FileNotFoundError(f"缺少映射文件: {path}，请先运行 uid_mapping_builder_chiller.py")
    mapping = json.loads(path.read_text(encoding="utf-8"))
    inputs = mapping.get("inputs", [])
    outputs = mapping.get("outputs", [])
    if not inputs or not outputs:
        raise RuntimeError("映射文件中输入/输出列表为空")
    return mapping


def load_influx_credentials(client_key: str) -> Dict:
    if not UTILS_CONFIG_PATH.exists():
        raise FileNotFoundError(f"未找到 Influx 配置: {UTILS_CONFIG_PATH}")
    cfg = yaml.safe_load(UTILS_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    influx_cfg = cfg.get("InfluxDB", {})
    common = influx_cfg.get("_common", {})
    client_cfg = influx_cfg.get(client_key, {})
    merged = {**common, **client_cfg}
    required = ["host", "port", "username", "password", "database"]
    missing = [k for k in required if k not in merged]
    if missing:
        raise KeyError(f"Influx 配置缺少字段: {missing}")
    return merged


def build_query(uid: str, start: str, stop: str, every: str, field: str, measurement: str) -> str:
    return (
        f'SELECT mean("{field}") AS value '
        f'FROM "{measurement}" '
        f"WHERE time >= '{start}' AND time <= '{stop}' "
        f"GROUP BY time({every}) fill(null)"
    )


def _query_one_uid(
    client: InfluxDBClient, uid: str, start: str, stop: str, every: str, field: str, measurement_template: str
) -> pd.DataFrame:
    measurement = measurement_template.format(uid=uid)
    q = build_query(uid, start, stop, every, field, measurement)
    result = client.query(q)
    points = list(result.get_points())
    if not points:
        return pd.DataFrame(columns=["time", uid])
    df = pd.DataFrame(points)
    if df.empty:
        return pd.DataFrame(columns=["time", uid])
    df = df.rename(columns={"value": uid})
    return df[["time", uid]]


def fetch_timeseries(
    uids: List[str],
    start: str,
    stop: str,
    every: str,
    field: str,
    measurement_template: str,
    client_key: str,
) -> pd.DataFrame:
    creds = load_influx_credentials(client_key)
    client = InfluxDBClient(
        host=creds["host"],
        port=creds["port"],
        username=creds["username"],
        password=creds["password"],
        database=creds["database"],
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
        merged = merged.merge(df, on="time", how="outer")
    merged = merged.sort_values("time").reset_index(drop=True)
    return merged


def fill_timeseries(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    filled = df.sort_values("time").reset_index(drop=True).copy()
    for col in filled.columns:
        if col == "time":
            continue
        series = filled[col]
        if series.notna().sum() == 0:
            continue
        filled[col] = series.ffill().bfill()
    return filled


def should_lag(name: str) -> bool:
    """
    需要滞后的典型特征：控制/执行/状态类。
    - 运行/启停/状态/模式等状态位
    - 变频/频率/开度/给定/设定等控制量
    - 阀/泵/塔/机组相关执行量
    """
    text = str(name)
    include_keys = ["运行", "启停", "状态", "模式", "变频", "频率", "开度", "给定", "设定", "阀", "泵", "塔", "机组", "开关"]
    exclude_keys = ["平均", "累积", "累计", "能耗", "计量"]  # 平滑缓变量，一般可不滞后
    if any(k in text for k in exclude_keys):
        return False
    return any(k in text for k in include_keys)


def build_feature_matrix_selective(df: pd.DataFrame, lag_uids: List[str], lags: int) -> pd.DataFrame:
    """
    对需要滞后的列添加滞后，其余只保留当前值。
    """
    base = df.copy().sort_values("time").reset_index(drop=True)
    feat = base[["time"]].copy()
    for col in base.columns:
        if col == "time":
            continue
        feat[col] = base[col]
        if lags > 0 and col in lag_uids:
            for k in range(1, lags + 1):
                feat[f"{col}_lag{k}"] = base[col].shift(k)
    feat = feat.dropna().reset_index(drop=True)
    return feat


def align_dataset(feature_df: pd.DataFrame, target_df: pd.DataFrame) -> pd.DataFrame:
    merged = feature_df.merge(target_df, on="time", how="inner")
    merged = merged.dropna().reset_index(drop=True)
    return merged


def split_train_test(dataset: pd.DataFrame, test_ratio: float = 0.2) -> Tuple[pd.DataFrame, pd.DataFrame]:
    n = len(dataset)
    test_size = max(1, int(n * test_ratio))
    train_size = n - test_size
    if train_size <= 0:
        raise RuntimeError("样本过少，无法划分训练/验证集")
    train = dataset.iloc[:train_size].reset_index(drop=True)
    test = dataset.iloc[train_size:].reset_index(drop=True)
    return train, test


def train_linear(X: np.ndarray, Y: np.ndarray):
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    model = MultiOutputRegressor(LinearRegression())
    model.fit(Xs, Y)
    return {"type": "linear", "scaler": scaler, "model": model}


def predict_linear(bundle, X: np.ndarray) -> np.ndarray:
    Xs = bundle["scaler"].transform(X)
    return bundle["model"].predict(Xs)


def train_lstsq(X: np.ndarray, Y: np.ndarray):
    Xb = np.hstack([np.ones((X.shape[0], 1)), X])
    coef, _, _, _ = np.linalg.lstsq(Xb, Y, rcond=None)
    return {"type": "lstsq", "coef": coef}


def predict_lstsq(bundle, X: np.ndarray) -> np.ndarray:
    Xb = np.hstack([np.ones((X.shape[0], 1)), X])
    return Xb @ bundle["coef"]


def train_mlp(X: np.ndarray, Y: np.ndarray):
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    model = MLPRegressor(
        hidden_layer_sizes=(128, 64),
        activation="relu",
        max_iter=600,
        alpha=5e-4,
        early_stopping=True,
        validation_fraction=0.2,
        random_state=42,
    )
    model.fit(Xs, Y)
    return {"type": "mlp", "scaler": scaler, "model": model}


def predict_mlp(bundle, X: np.ndarray) -> np.ndarray:
    Xs = bundle["scaler"].transform(X)
    return bundle["model"].predict(Xs)


def train_random_forest(X: np.ndarray, Y: np.ndarray):
    model = MultiOutputRegressor(
        RandomForestRegressor(
            n_estimators=250,
            max_depth=10,
            min_samples_leaf=4,
            max_features="sqrt",
            random_state=42,
            n_jobs=-1,
        )
    )
    model.fit(X, Y)
    return {"type": "rf", "model": model}


def predict_random_forest(bundle, X: np.ndarray) -> np.ndarray:
    return bundle["model"].predict(X)


def train_xgb(X: np.ndarray, Y: np.ndarray):
    try:
        import xgboost as xgb
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError("缺少 xgboost，请先安装") from exc

    base = xgb.XGBRegressor(
        n_estimators=400,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=5.0,
        reg_lambda=2.0,
        reg_alpha=0.5,
        random_state=42,
        n_jobs=-1,
        objective="reg:squarederror",
    )
    model = MultiOutputRegressor(base)
    model.fit(X, Y)
    return {"type": "xgb", "model": model}


def predict_xgb(bundle, X: np.ndarray) -> np.ndarray:
    return bundle["model"].predict(X)


def evaluate(y_true: np.ndarray, y_pred: np.ndarray, target_cols: List[str], target_meta: Dict[str, Dict]) -> Dict:
    mse = np.mean((y_true - y_pred) ** 2, axis=0)
    mae = np.mean(np.abs(y_true - y_pred), axis=0)
    per_target = []
    for idx, col in enumerate(target_cols):
        meta = target_meta.get(col, {})
        per_target.append(
            {
                "uid": col,
                "name": meta.get("name"),
                "mse": float(mse[idx]),
                "mae": float(mae[idx]),
            }
        )
    overall = {"mse_mean": float(np.mean(mse)), "mae_mean": float(np.mean(mae))}
    return {"overall": overall, "per_target": per_target}


def save_artifacts(model_bundle, metrics: Dict, predictions: pd.DataFrame, model_name: str):
    ARTIFACT_DIR.mkdir(exist_ok=True)
    if model_name == "linear":
        joblib.dump(model_bundle, ARTIFACT_DIR / "model_linear.pkl")
    elif model_name == "mlp":
        joblib.dump(model_bundle, ARTIFACT_DIR / "model_mlp.pkl")
    elif model_name == "rf":
        joblib.dump(model_bundle, ARTIFACT_DIR / "model_rf.pkl")
    elif model_name == "xgb":
        joblib.dump(model_bundle, ARTIFACT_DIR / "model_xgb.pkl")
    else:
        np.savez(ARTIFACT_DIR / "model_lstsq.npz", **model_bundle)
    (ARTIFACT_DIR / f"metrics_{model_name}.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    predictions.to_csv(ARTIFACT_DIR / f"predictions_{model_name}.csv", index=False, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", help="ISO8601，默认 stop 往前 365 天")
    parser.add_argument("--stop", help="ISO8601，默认当前 UTC")
    parser.add_argument("--every", default="5m", help="聚合窗口，例如 5m/15m/1h")
    parser.add_argument("--lags", type=int, default=3, help="输入特征时间滞后阶数，0 表示不加滞后")
    parser.add_argument(
        "--model", choices=["linear", "lstsq", "mlp", "rf", "xgb"], default="linear", help="训练模型类型"
    )
    parser.add_argument("--test-ratio", type=float, default=0.2, help="验证集比例")
    parser.add_argument("--field", default="value", help="Influx 数值字段名，默认 value")
    parser.add_argument(
        "--measurement-template", default="{uid}", help="measurement 模板，默认与 uid 同名，可用 {uid} 占位"
    )
    parser.add_argument(
        "--client-key", default="influxdb_dc_status_data", help="configs/utils_config.yaml 中的客户端键名"
    )
    parser.add_argument("--mapping", default=str(MAPPING_PATH), help="自定义映射路径，可覆盖默认路径")
    args = parser.parse_args()

    now_utc = datetime.now(timezone.utc).replace(microsecond=0)
    stop = args.stop or now_utc.isoformat().replace("+00:00", "Z")
    start = args.start or (now_utc - timedelta(days=365)).isoformat().replace("+00:00", "Z")

    mapping = load_mapping(Path(args.mapping))
    input_recs = mapping.get("inputs", [])
    output_recs = mapping.get("outputs", [])
    input_uids = [r["uid"] for r in input_recs]
    output_uids = [r["uid"] for r in output_recs]
    target_meta = {r["uid"]: r for r in output_recs}

    print(f"拉取输入 {len(input_uids)} 个，输出 {len(output_uids)} 个，时间范围 {start} ~ {stop}")
    input_df = fetch_timeseries(
        input_uids, start, stop, args.every, field=args.field, measurement_template=args.measurement_template, client_key=args.client_key
    )
    output_df = fetch_timeseries(
        output_uids, start, stop, args.every, field=args.field, measurement_template=args.measurement_template, client_key=args.client_key
    )

    input_df = fill_timeseries(input_df)
    output_df = fill_timeseries(output_df)

    if input_df.empty or output_df.empty:
        raise RuntimeError("Influx 数据为空，请检查 measurement/field 或时间范围")

    # 仅对需要滞后的输入列加滞后
    lag_uids = [rec["uid"] for rec in input_recs if should_lag(rec.get("name", ""))]
    if lag_uids:
        print(f"滞后特征列: {len(lag_uids)} 个 / 输入 {len(input_uids)} 个")
    else:
        print("未识别到需要滞后的输入特征，特征仅使用当前值")
    feature_df = build_feature_matrix_selective(input_df, lag_uids=lag_uids, lags=max(args.lags, 0))
    dataset = align_dataset(feature_df, output_df)
    if dataset.empty:
        raise RuntimeError("对齐后的数据为空，可能是时间粒度或窗口导致无交集")

    feature_cols = [c for c in dataset.columns if c != "time" and c not in output_df.columns]
    target_cols = [c for c in output_df.columns if c != "time"]

    for col in feature_cols + target_cols:
        if dataset[col].notna().sum() == 0:
            raise RuntimeError(f"列 {col} 全为空，无法训练")

    train_df, test_df = split_train_test(dataset, test_ratio=args.test_ratio)
    X_train = train_df[feature_cols].to_numpy()
    Y_train = train_df[target_cols].to_numpy()
    X_test = test_df[feature_cols].to_numpy()
    Y_test = test_df[target_cols].to_numpy()

    if args.model == "linear":
        model_bundle = train_linear(X_train, Y_train)
        preds = predict_linear(model_bundle, X_test)
    elif args.model == "lstsq":
        model_bundle = train_lstsq(X_train, Y_train)
        preds = predict_lstsq(model_bundle, X_test)
    elif args.model == "mlp":
        model_bundle = train_mlp(X_train, Y_train)
        preds = predict_mlp(model_bundle, X_test)
    elif args.model == "rf":
        model_bundle = train_random_forest(X_train, Y_train)
        preds = predict_random_forest(model_bundle, X_test)
    else:  # xgb
        model_bundle = train_xgb(X_train, Y_train)
        preds = predict_xgb(model_bundle, X_test)

    metrics = evaluate(Y_test, preds, target_cols, target_meta)
    pred_df = pd.DataFrame(preds, columns=target_cols)
    pred_df.insert(0, "time", test_df["time"].to_numpy())

    save_artifacts(model_bundle, metrics, pred_df, model_name=args.model)
    print("训练完成，整体指标:", metrics["overall"])
    print(f"输出目录: {ARTIFACT_DIR}")


if __name__ == "__main__":
    main()
