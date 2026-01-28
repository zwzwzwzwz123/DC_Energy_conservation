"""
Chiller modeling pipeline

- Pulls timeseries from InfluxDB (1.8) with configurable measurement template/field.
- Builds lag features on inputs and trains selectable models (linear / lstsq / mlp / rf / xgb / lstm).
- Writes artifacts to generated/chiller_modeling/artifacts_chiller.
"""
import argparse
import json
import sys
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


CUMULATIVE_KEYS = ["电能", "有功", "电量", "能耗", "累计", "总量", "meter", "energy"]


def is_cumulative(name: str) -> bool:
    """简单基于名称判断是否为累积量（电能/能耗类）。"""
    text = str(name).lower()
    return any(k in text for k in CUMULATIVE_KEYS)


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


def ensure_datetime(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out["time"] = pd.to_datetime(out["time"])
    return out


def apply_cumulative_diff(df: pd.DataFrame, cum_cols: List[str]) -> pd.DataFrame:
    """对累积量做差分（遇到回绕/复位则置 NaN）。"""
    if df.empty or not cum_cols:
        return df
    out = df.sort_values("time").reset_index(drop=True).copy()
    for col in cum_cols:
        if col not in out.columns:
            continue
        diffed = out[col].diff()
        diffed = diffed.where(diffed >= 0)  # 回绕视为缺失
        out[col] = diffed
    return out


def shift_targets(target_df: pd.DataFrame, horizon: pd.Timedelta) -> pd.DataFrame:
    """
    将目标时间向前平移 horizon，使特征时间 t 对应目标 t+horizon。
    """
    if target_df.empty:
        return target_df
    df = target_df.copy()
    df["time"] = pd.to_datetime(df["time"]) - horizon
    return df


def build_multi_step_targets(target_df: pd.DataFrame, horizon_step: pd.Timedelta, steps: int) -> pd.DataFrame:
    """构造多步预测目标（t+1Δ ... t+stepsΔ），列名追加 __t+{k}。"""
    if target_df.empty:
        return target_df
    if steps <= 0:
        raise RuntimeError(f"steps 必须为正数，当前={steps}")
    merged = None
    for k in range(1, steps + 1):
        shifted = shift_targets(target_df, horizon=horizon_step * k)
        renamed = {}
        for col in shifted.columns:
            if col == "time":
                continue
            renamed[col] = f"{col}__t+{k}"
        shifted = shifted.rename(columns=renamed)
        merged = shifted if merged is None else merged.merge(shifted, on="time", how="inner")
    return merged


def drop_constant_columns(df: pd.DataFrame, exclude_cols: List[str], min_range: float = 1e-6) -> pd.DataFrame:
    """移除恒定或近恒定列（范围<=min_range），time 列与 exclude_cols 不处理。"""
    keep = ["time"]
    for col in df.columns:
        if col in exclude_cols or col == "time":
            keep.append(col)
            continue
        series = df[col]
        if series.notna().sum() == 0:
            continue
        rng = series.max() - series.min()
        if pd.isna(rng) or rng <= min_range:
            continue  # 丢弃恒值列
        keep.append(col)
    return df[keep]


def drop_constant_with_meta(df: pd.DataFrame, uid_to_name: Dict[str, str], min_range: float = 1e-6,
                            dominance: float = 0.995):
    """
    移除恒定/近恒定列并返回剔除列表（uid, name）。
    - 恒定：非空唯一值为 1 个
    - 近恒定：max-min <= min_range，或占比最高值 >= dominance 且范围 <= 1
    """
    if df.empty:
        return df, []
    keep_cols = ["time"]
    removed = []
    for col in df.columns:
        if col == "time":
            continue
        series = df[col].dropna()
        if series.empty:
            removed.append(col)
            continue
        uniq = series.unique()
        rng = series.max() - series.min()
        dom = series.value_counts(normalize=True).iloc[0]
        cond_const = len(uniq) == 1
        cond_near_const = (rng <= min_range) or (dom >= dominance and rng <= 1)
        if cond_const or cond_near_const:
            removed.append(col)
            continue
        keep_cols.append(col)
    return df[keep_cols], removed


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


def build_lstm_sequences_table(df: pd.DataFrame, feature_cols: List[str], seq_len: int):
    """将表格数据转换为 LSTM 输入序列 (n_samples, seq_len, n_features)。"""
    if seq_len <= 0:
        seq_len = 1
    df_sorted = df.sort_values("time").reset_index(drop=True)
    if len(df_sorted) < seq_len:
        raise RuntimeError(f"样本过少，无法构造序列：seq_len={seq_len}，样本={len(df_sorted)}")
    arr = df_sorted[feature_cols].to_numpy()
    seqs = []
    for i in range(seq_len - 1, len(df_sorted)):
        seqs.append(arr[i - seq_len + 1 : i + 1])
    seq_arr = np.stack(seqs, axis=0)
    trimmed_df = df_sorted.iloc[seq_len - 1 :].reset_index(drop=True)
    return seq_arr, trimmed_df


def train_lstm(X_seq: np.ndarray, Y: np.ndarray, epochs: int = 60, lr: float = 1e-3, hidden_size: int = 64):
    try:
        import torch
        from torch import nn
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError("缺少依赖 torch，无法使用 lstm 模型；请安装 torch") from exc

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    scaler = StandardScaler()
    N, T, F = X_seq.shape
    Xs_flat = scaler.fit_transform(X_seq.reshape(N, T * F))
    Xs = Xs_flat.reshape(N, T, F)

    X_tensor = torch.tensor(Xs, dtype=torch.float32).to(device)
    Y_tensor = torch.tensor(Y, dtype=torch.float32).to(device)

    output_dim = Y.shape[1]

    class LSTMReg(nn.Module):
        def __init__(self, input_dim, hidden_size, output_dim):
            super().__init__()
            self.lstm = nn.LSTM(input_size=input_dim, hidden_size=hidden_size, batch_first=True)
            self.fc = nn.Linear(hidden_size, output_dim)

        def forward(self, x):
            out, _ = self.lstm(x)
            out = out[:, -1, :]
            return self.fc(out)

    model = LSTMReg(F, hidden_size, output_dim).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = nn.MSELoss()

    model.train()
    batch_size = min(256, len(X_tensor))
    for epoch in range(epochs):
        perm = torch.randperm(len(X_tensor))
        for i in range(0, len(X_tensor), batch_size):
            idx = perm[i : i + batch_size]
            xb = X_tensor[idx]
            yb = Y_tensor[idx]
            optimizer.zero_grad()
            pred = model(xb)
            loss = criterion(pred, yb)
            loss.backward()
            optimizer.step()

    return {
        "type": "lstm",
        "scaler": scaler,
        "state_dict": model.state_dict(),
        "hidden_size": hidden_size,
        "input_dim": F,
        "output_dim": output_dim,
        "seq_len": T,
        "device": str(device),
    }


def predict_lstm(bundle, X_seq: np.ndarray) -> np.ndarray:
    import torch
    from torch import nn

    scaler = bundle["scaler"]
    input_dim = bundle["input_dim"]
    hidden_size = bundle["hidden_size"]
    output_dim = bundle["output_dim"]
    seq_len = bundle["seq_len"]
    state_dict = bundle["state_dict"]

    class LSTMReg(nn.Module):
        def __init__(self, input_dim, hidden_size, output_dim):
            super().__init__()
            self.lstm = nn.LSTM(input_size=input_dim, hidden_size=hidden_size, batch_first=True)
            self.fc = nn.Linear(hidden_size, output_dim)

        def forward(self, x):
            out, _ = self.lstm(x)
            out = out[:, -1, :]
            return self.fc(out)

    device = torch.device(bundle.get("device", "cpu"))
    model = LSTMReg(input_dim, hidden_size, output_dim).to(device)
    model.load_state_dict(state_dict)

    N, T, F = X_seq.shape
    if T != seq_len or F != input_dim:
        raise RuntimeError(f"LSTM 输入维度不符：期望 (*, {seq_len}, {input_dim})，实际 ({N}, {T}, {F})")
    Xs_flat = scaler.transform(X_seq.reshape(N, T * F))
    Xs = Xs_flat.reshape(N, T, F)
    X_tensor = torch.tensor(Xs, dtype=torch.float32).to(device)
    model.eval()
    with torch.no_grad():
        preds = model(X_tensor).cpu().numpy()
    return preds


def train_gru(X_seq: np.ndarray, Y: np.ndarray, epochs: int = 60, lr: float = 1e-3, hidden_size: int = 64):
    try:
        import torch
        from torch import nn
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError("缺少依赖 torch，无法使用 gru 模型；请安装 torch") from exc

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    scaler = StandardScaler()
    N, T, F = X_seq.shape
    Xs_flat = scaler.fit_transform(X_seq.reshape(N, T * F))
    Xs = Xs_flat.reshape(N, T, F)

    X_tensor = torch.tensor(Xs, dtype=torch.float32).to(device)
    Y_tensor = torch.tensor(Y, dtype=torch.float32).to(device)

    output_dim = Y.shape[1]

    class GRUReg(nn.Module):
        def __init__(self, input_dim, hidden_size, output_dim):
            super().__init__()
            self.gru = nn.GRU(input_size=input_dim, hidden_size=hidden_size, batch_first=True)
            self.fc = nn.Linear(hidden_size, output_dim)

        def forward(self, x):
            out, _ = self.gru(x)
            out = out[:, -1, :]
            return self.fc(out)

    model = GRUReg(F, hidden_size, output_dim).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = nn.MSELoss()

    model.train()
    batch_size = min(256, len(X_tensor))
    for epoch in range(epochs):
        perm = torch.randperm(len(X_tensor))
        for i in range(0, len(X_tensor), batch_size):
            idx = perm[i : i + batch_size]
            xb = X_tensor[idx]
            yb = Y_tensor[idx]
            optimizer.zero_grad()
            pred = model(xb)
            loss = criterion(pred, yb)
            loss.backward()
            optimizer.step()

    return {
        "type": "gru",
        "scaler": scaler,
        "state_dict": model.state_dict(),
        "hidden_size": hidden_size,
        "input_dim": F,
        "output_dim": output_dim,
        "seq_len": T,
        "device": str(device),
    }


def predict_gru(bundle, X_seq: np.ndarray) -> np.ndarray:
    import torch
    from torch import nn

    scaler = bundle["scaler"]
    input_dim = bundle["input_dim"]
    hidden_size = bundle["hidden_size"]
    output_dim = bundle["output_dim"]
    seq_len = bundle["seq_len"]
    state_dict = bundle["state_dict"]

    class GRUReg(nn.Module):
        def __init__(self, input_dim, hidden_size, output_dim):
            super().__init__()
            self.gru = nn.GRU(input_size=input_dim, hidden_size=hidden_size, batch_first=True)
            self.fc = nn.Linear(hidden_size, output_dim)

        def forward(self, x):
            out, _ = self.gru(x)
            out = out[:, -1, :]
            return self.fc(out)

    device = torch.device(bundle.get("device", "cpu"))
    model = GRUReg(input_dim, hidden_size, output_dim).to(device)
    model.load_state_dict(state_dict)

    N, T, F = X_seq.shape
    if T != seq_len or F != input_dim:
        raise RuntimeError(f"GRU 输入维度不符：期望 (*, {seq_len}, {input_dim})，实际 ({N}, {T}, {F})")
    Xs_flat = scaler.transform(X_seq.reshape(N, T * F))
    Xs = Xs_flat.reshape(N, T, F)
    X_tensor = torch.tensor(Xs, dtype=torch.float32).to(device)
    model.eval()
    with torch.no_grad():
        preds = model(X_tensor).cpu().numpy()
    return preds


def train_transformer(
    X_seq: np.ndarray,
    Y: np.ndarray,
    epochs: int = 60,
    lr: float = 5e-4,
    d_model: int = 64,
    nhead: int = 4,
    num_layers: int = 2,
    dim_feedforward: int = 256,
    dropout: float = 0.1,
):
    try:
        import torch
        from torch import nn
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError("缺少依赖 torch，无法使用 transformer 模型；请安装 torch") from exc

    if d_model % nhead != 0:
        raise ValueError(f"d_model={d_model} 必须能被 nhead={nhead} 整除")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    scaler = StandardScaler()
    N, T, F = X_seq.shape
    Xs_flat = scaler.fit_transform(X_seq.reshape(N, T * F))
    Xs = Xs_flat.reshape(N, T, F)

    X_tensor = torch.tensor(Xs, dtype=torch.float32).to(device)
    Y_tensor = torch.tensor(Y, dtype=torch.float32).to(device)

    output_dim = Y.shape[1]

    class TransformerReg(nn.Module):
        def __init__(self, input_dim, output_dim, seq_len):
            super().__init__()
            self.input_proj = nn.Linear(input_dim, d_model)
            self.pos_embed = nn.Parameter(torch.zeros(1, seq_len, d_model))
            encoder_layer = nn.TransformerEncoderLayer(
                d_model=d_model,
                nhead=nhead,
                dim_feedforward=dim_feedforward,
                dropout=dropout,
                batch_first=True,
            )
            self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
            self.fc = nn.Linear(d_model, output_dim)

        def forward(self, x):
            x = self.input_proj(x) + self.pos_embed
            x = self.encoder(x)
            out = x[:, -1, :]
            return self.fc(out)

    model = TransformerReg(F, output_dim, seq_len=T).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = nn.MSELoss()

    model.train()
    batch_size = min(256, len(X_tensor))
    for epoch in range(epochs):
        perm = torch.randperm(len(X_tensor))
        for i in range(0, len(X_tensor), batch_size):
            idx = perm[i : i + batch_size]
            xb = X_tensor[idx]
            yb = Y_tensor[idx]
            optimizer.zero_grad()
            pred = model(xb)
            loss = criterion(pred, yb)
            loss.backward()
            optimizer.step()

    return {
        "type": "transformer",
        "scaler": scaler,
        "state_dict": model.state_dict(),
        "input_dim": F,
        "output_dim": output_dim,
        "seq_len": T,
        "d_model": d_model,
        "nhead": nhead,
        "num_layers": num_layers,
        "dim_feedforward": dim_feedforward,
        "dropout": dropout,
        "device": str(device),
    }


def predict_transformer(bundle, X_seq: np.ndarray) -> np.ndarray:
    import torch
    from torch import nn

    scaler = bundle["scaler"]
    input_dim = bundle["input_dim"]
    output_dim = bundle["output_dim"]
    seq_len = bundle["seq_len"]
    d_model = bundle["d_model"]
    nhead = bundle["nhead"]
    num_layers = bundle["num_layers"]
    dim_feedforward = bundle["dim_feedforward"]
    dropout = bundle["dropout"]
    state_dict = bundle["state_dict"]

    if d_model % nhead != 0:
        raise ValueError(f"d_model={d_model} 必须能被 nhead={nhead} 整除")

    class TransformerReg(nn.Module):
        def __init__(self, input_dim, output_dim, seq_len):
            super().__init__()
            self.input_proj = nn.Linear(input_dim, d_model)
            self.pos_embed = nn.Parameter(torch.zeros(1, seq_len, d_model))
            encoder_layer = nn.TransformerEncoderLayer(
                d_model=d_model,
                nhead=nhead,
                dim_feedforward=dim_feedforward,
                dropout=dropout,
                batch_first=True,
            )
            self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
            self.fc = nn.Linear(d_model, output_dim)

        def forward(self, x):
            x = self.input_proj(x) + self.pos_embed
            x = self.encoder(x)
            out = x[:, -1, :]
            return self.fc(out)

    device = torch.device(bundle.get("device", "cpu"))
    model = TransformerReg(input_dim, output_dim, seq_len=seq_len).to(device)
    model.load_state_dict(state_dict)

    N, T, F = X_seq.shape
    if T != seq_len or F != input_dim:
        raise RuntimeError(f"Transformer 输入维度不符：期望 (*, {seq_len}, {input_dim})，实际 ({N}, {T}, {F})")
    Xs_flat = scaler.transform(X_seq.reshape(N, T * F))
    Xs = Xs_flat.reshape(N, T, F)
    X_tensor = torch.tensor(Xs, dtype=torch.float32).to(device)
    model.eval()
    with torch.no_grad():
        preds = model(X_tensor).cpu().numpy()
    return preds


def _load_patchtst_model():
    patch_root = PROJECT_ROOT / "models" / "PatchTST" / "PatchTST_supervised"
    if not patch_root.exists():
        raise ImportError(f"未找到 PatchTST 源码目录: {patch_root}")
    if str(patch_root) not in sys.path:
        sys.path.insert(0, str(patch_root))
    try:
        from models.PatchTST import Model as PatchTSTModel
    except Exception as exc:
        raise ImportError("无法导入 PatchTST 模型，请检查源码依赖") from exc
    return PatchTSTModel


def train_patchtst(X_seq: np.ndarray, Y: np.ndarray, pred_len: int = 7, epochs: int = 60, lr: float = 5e-4):
    try:
        import torch
        from torch import nn
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError("缺少依赖 torch，无法使用 patchtst 模型；请安装 torch") from exc

    PatchTSTModel = _load_patchtst_model()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    scaler = StandardScaler()
    N, T, F = X_seq.shape
    if pred_len <= 0:
        raise RuntimeError(f"pred_len 必须为正数，当前={pred_len}")
    if Y.shape[1] % pred_len != 0:
        raise RuntimeError("PatchTST 需要按步数整除目标维度，请检查 target_cols 构造顺序")
    target_dim = Y.shape[1] // pred_len

    Xs_flat = scaler.fit_transform(X_seq.reshape(N, T * F))
    Xs = Xs_flat.reshape(N, T, F)
    Y_seq = Y.reshape(N, pred_len, target_dim)

    X_tensor = torch.tensor(Xs, dtype=torch.float32).to(device)
    Y_tensor = torch.tensor(Y_seq, dtype=torch.float32).to(device)

    patch_len = min(max(4, T // 3), 6)
    stride = max(1, patch_len // 2)

    class PatchTSTReg(nn.Module):
        def __init__(self, input_dim: int, target_dim: int, seq_len: int, pred_len: int):
            super().__init__()
            configs = type("Cfg", (), {})()
            configs.enc_in = input_dim
            configs.seq_len = seq_len
            configs.pred_len = pred_len
            configs.e_layers = 2
            configs.n_heads = 4
            configs.d_model = 64
            configs.d_ff = 128
            configs.dropout = 0.1
            configs.fc_dropout = 0.1
            configs.head_dropout = 0.1
            configs.individual = False
            configs.patch_len = patch_len
            configs.stride = stride
            configs.padding_patch = "end"
            configs.revin = True
            configs.affine = True
            configs.subtract_last = False
            configs.decomposition = False
            configs.kernel_size = 25
            self.model = PatchTSTModel(configs)
            self.proj = nn.Linear(input_dim, target_dim)

        def forward(self, x):
            out = self.model(x)
            return self.proj(out)

    model = PatchTSTReg(F, target_dim, T, pred_len).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = nn.MSELoss()

    model.train()
    batch_size = min(32, len(X_tensor))
    for epoch in range(epochs):
        perm = torch.randperm(len(X_tensor))
        for i in range(0, len(X_tensor), batch_size):
            idx = perm[i : i + batch_size]
            xb = X_tensor[idx]
            yb = Y_tensor[idx]
            optimizer.zero_grad()
            pred = model(xb)
            loss = criterion(pred, yb)
            loss.backward()
            optimizer.step()

    return {
        "type": "patchtst",
        "scaler": scaler,
        "state_dict": model.state_dict(),
        "input_dim": F,
        "target_dim": target_dim,
        "seq_len": T,
        "pred_len": pred_len,
        "patch_len": patch_len,
        "stride": stride,
        "device": str(device),
    }


def predict_patchtst(bundle, X_seq: np.ndarray) -> np.ndarray:
    import torch
    from torch import nn

    PatchTSTModel = _load_patchtst_model()
    scaler = bundle["scaler"]
    input_dim = bundle["input_dim"]
    target_dim = bundle["target_dim"]
    seq_len = bundle["seq_len"]
    pred_len = bundle["pred_len"]
    patch_len = bundle["patch_len"]
    stride = bundle["stride"]
    state_dict = bundle["state_dict"]

    class PatchTSTReg(nn.Module):
        def __init__(self, input_dim: int, target_dim: int, seq_len: int, pred_len: int):
            super().__init__()
            configs = type("Cfg", (), {})()
            configs.enc_in = input_dim
            configs.seq_len = seq_len
            configs.pred_len = pred_len
            configs.e_layers = 2
            configs.n_heads = 4
            configs.d_model = 64
            configs.d_ff = 128
            configs.dropout = 0.1
            configs.fc_dropout = 0.1
            configs.head_dropout = 0.1
            configs.individual = False
            configs.patch_len = patch_len
            configs.stride = stride
            configs.padding_patch = "end"
            configs.revin = True
            configs.affine = True
            configs.subtract_last = False
            configs.decomposition = False
            configs.kernel_size = 25
            self.model = PatchTSTModel(configs)
            self.proj = nn.Linear(input_dim, target_dim)

        def forward(self, x):
            out = self.model(x)
            return self.proj(out)

    device = torch.device(bundle.get("device", "cpu"))
    model = PatchTSTReg(input_dim, target_dim, seq_len, pred_len).to(device)
    model.load_state_dict(state_dict)

    N, T, F = X_seq.shape
    if T != seq_len or F != input_dim:
        raise RuntimeError(f"PatchTST 输入维度不符：期望 (*, {seq_len}, {input_dim})，实际 ({N}, {T}, {F})")
    Xs_flat = scaler.transform(X_seq.reshape(N, T * F))
    Xs = Xs_flat.reshape(N, T, F)
    X_tensor = torch.tensor(Xs, dtype=torch.float32).to(device)
    model.eval()
    with torch.no_grad():
        preds_seq = model(X_tensor).cpu().numpy()
    return preds_seq.reshape(N, pred_len * target_dim)


def evaluate(y_true: np.ndarray, y_pred: np.ndarray, target_cols: List[str], target_meta: Dict[str, Dict]) -> Dict:
    mse = np.mean((y_true - y_pred) ** 2, axis=0)
    mae = np.mean(np.abs(y_true - y_pred), axis=0)
    per_target = []
    groups = {"energy": [], "temperature": [], "flow": [], "other": []}

    def error_pct(mae_val: float, mean_val: float) -> float:
        if mean_val is None or np.isnan(mean_val):
            return float("nan")
        denom = abs(float(mean_val))
        if denom <= 1e-12:
            return float("nan")
        return float(mae_val / denom * 100.0)

    def classify(meta: Dict) -> str:
        name = str(meta.get("name", ""))
        lname = name.lower()
        if is_cumulative(name):
            return "energy"
        if "温度" in name:
            return "temperature"
        if "流量" in name:
            return "flow"
        # 兜底
        if "temp" in lname:
            return "temperature"
        if "flow" in lname:
            return "flow"
        return "other"

    for idx, col in enumerate(target_cols):
        base_col, step_label = col, None
        if "__t+" in col:
            base_col, step_label = col.split("__t+", 1)
        meta = target_meta.get(base_col, {})
        group = classify(meta)
        name = meta.get("name")
        if name and step_label:
            name = f"{name}__t+{step_label}"
        per_target.append(
            {
                "uid": col,
                "name": name,
                "mse": float(mse[idx]),
                "mae": float(mae[idx]),
                "group": group,
            }
        )
        groups[group].append(idx)

    def group_stats(idxs: List[int]):
        if not idxs:
            return None
        g_mse = float(np.mean((y_true[:, idxs] - y_pred[:, idxs]) ** 2))
        g_mae = float(np.mean(np.abs(y_true[:, idxs] - y_pred[:, idxs])))
        g_mean = float(np.mean(y_true[:, idxs]))
        return {
            "mse_mean": g_mse,
            "mae_mean": g_mae,
            "误差百分比": error_pct(g_mae, g_mean),
            "count": len(idxs),
        }

    group_metrics = {}
    for g, idxs in groups.items():
        stats = group_stats(idxs)
        if stats:
            group_metrics[g] = stats

    overall_mean = float(np.mean(y_true))
    overall = {
        "mse_mean": float(np.mean(mse)),
        "mae_mean": float(np.mean(mae)),
        "误差百分比": error_pct(float(np.mean(mae)), overall_mean),
    }
    return {"overall": overall, "per_target": per_target, "groups": group_metrics}


def save_artifacts(model_bundle, metrics: Dict, predictions: pd.DataFrame, model_name: str):
    ARTIFACT_DIR.mkdir(exist_ok=True)
    if model_name == "linear":
        joblib.dump(model_bundle, ARTIFACT_DIR / "model_linear.pkl")
    elif model_name == "mlp":
        joblib.dump(model_bundle, ARTIFACT_DIR / "model_mlp.pkl")
    elif model_name == "lstm":
        joblib.dump(model_bundle, ARTIFACT_DIR / "model_lstm.pkl")
    elif model_name == "gru":
        joblib.dump(model_bundle, ARTIFACT_DIR / "model_gru.pkl")
    elif model_name == "transformer":
        joblib.dump(model_bundle, ARTIFACT_DIR / "model_transformer.pkl")
    elif model_name == "patchtst":
        joblib.dump(model_bundle, ARTIFACT_DIR / "model_patchtst.pkl")
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
    parser.add_argument("--lags", type=int, default=3, help="输入特征滞后阶数（用于特征构造）")
    parser.add_argument("--seq-len", type=int, default=None, help="时序模型序列长度，默认 21（=7步×3）")
    parser.add_argument("--target-lags", type=int, default=None, help="输出状态自回归滞后阶数（时序模型默认 7）")
    parser.add_argument("--horizon", default=None, help="预测步长 Δ（单步间隔）；默认等于 every")
    parser.add_argument(
        "--model", choices=["linear", "lstsq", "mlp", "rf", "xgb", "lstm", "gru", "transformer", "patchtst"], default="linear", help="训练模型类型"
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

    seq_models = {"lstm", "gru", "transformer", "patchtst"}
    forecast_steps = 7
    window_steps = forecast_steps * 3
    if args.seq_len is None and args.model in seq_models:
        args.seq_len = window_steps
    if args.target_lags is None:
        args.target_lags = forecast_steps if args.model in seq_models else 3
    every_td = pd.to_timedelta(args.every)
    if args.horizon:
        horizon_td = pd.to_timedelta(args.horizon)
    else:
        horizon_td = every_td

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

    input_df = ensure_datetime(fill_timeseries(input_df))
    output_df = ensure_datetime(fill_timeseries(output_df))

    # 对输出中的累积量（电能/能耗等）做差分，避免累积值主导误差
    cum_output_uids = [r["uid"] for r in output_recs if is_cumulative(r.get("name", ""))]
    if cum_output_uids:
        print(f"检测到累积量输出 {len(cum_output_uids)} 个，将做差分")
        output_df = apply_cumulative_diff(output_df, cum_output_uids)

    # 移除恒定/近恒定输入/输出列，记录剔除列表
    uid_name_map = {r["uid"]: r.get("name") for r in input_recs + output_recs}
    input_df, removed_inputs = drop_constant_with_meta(input_df, uid_name_map, min_range=1e-6, dominance=0.995)
    output_df, removed_outputs = drop_constant_with_meta(output_df, uid_name_map, min_range=1e-6, dominance=0.995)
    if removed_inputs:
        print("剔除恒定/近恒定输入:", [f"{uid_name_map.get(u, u)}({u})" for u in removed_inputs])
    if removed_outputs:
        print("剔除恒定/近恒定输出:", [f"{uid_name_map.get(u, u)}({u})" for u in removed_outputs])

    if input_df.empty or output_df.empty:
        raise RuntimeError("Influx 数据为空，请检查 measurement/field 或时间范围")

    timeseries_mode = args.model in seq_models

    if timeseries_mode:
        # LSTM: 使用当前输入+状态，构造序列，预测未来 t+Δ 的输出
        state_col_map = {uid: f"state_{uid}" for uid in output_uids}
        base_feat_df = input_df.merge(output_df.rename(columns=state_col_map), on="time", how="left")
        shifted_targets = build_multi_step_targets(output_df, horizon_step=horizon_td, steps=forecast_steps)
        merged = base_feat_df.merge(shifted_targets, on="time", how="inner")
        merged = merged.dropna().reset_index(drop=True)
        if merged.empty:
            raise RuntimeError("对齐后的数据为空，可能是时间粒度或聚合粒度不匹配")

        target_cols = [c for c in shifted_targets.columns if c != "time"]
        feature_cols = [c for c in merged.columns if c not in ["time"] + target_cols]

        for col in feature_cols + target_cols:
            if merged[col].notna().sum() == 0:
                raise RuntimeError(f"列 {col} 全为空，无法训练")

        seq_len = max(1, args.seq_len or window_steps)
        X_seq, seq_df = build_lstm_sequences_table(merged, feature_cols, seq_len=seq_len)
        target_df = seq_df[target_cols]
        time_series = seq_df["time"]

        n = len(seq_df)
        test_size = max(1, int(n * args.test_ratio))
        train_size = n - test_size
        if train_size <= 0:
            raise RuntimeError("样本过少，无法划分训练/验证集")
        X_train = X_seq[:train_size]
        Y_train = target_df.iloc[:train_size].to_numpy()
        X_test = X_seq[train_size:]
        Y_test = target_df.iloc[train_size:].to_numpy()
        test_time = time_series.iloc[train_size:].to_numpy()
    else:
        # 非时序模式：输入滞后 + 同步输出
        # 仅对需要滞后的输入列加滞后
        lag_uids = [rec["uid"] for rec in input_recs if should_lag(rec.get("name", ""))]
        if lag_uids:
            print(f"滞后特征列: {len(lag_uids)} 个 / 输入 {len(input_uids)} 个")
        else:
            print("未识别到需要滞后的输入特征，特征仅使用当前值")
        feature_df = build_feature_matrix_selective(input_df, lag_uids=lag_uids, lags=max(args.lags, 0))
        dataset = align_dataset(feature_df, output_df)
        if dataset.empty:
            raise RuntimeError("对齐后的数据为空，可能是时间窗口或聚合粒度不匹配")
        target_cols = [c for c in output_df.columns if c != "time"]
        feature_cols = [c for c in dataset.columns if c != "time" and c not in target_cols]

        for col in feature_cols + target_cols:
            if dataset[col].notna().sum() == 0:
                raise RuntimeError(f"列 {col} 全为空，无法训练")

        train_df, test_df = split_train_test(dataset, test_ratio=args.test_ratio)
        X_train = train_df[feature_cols].to_numpy()
        Y_train = train_df[target_cols].to_numpy()
        X_test = test_df[feature_cols].to_numpy()
        Y_test = test_df[target_cols].to_numpy()
        test_time = test_df["time"].to_numpy()

    if args.model == "linear":
        model_bundle = train_linear(X_train, Y_train)
        preds = predict_linear(model_bundle, X_test)
    elif args.model == "lstsq":
        x_scaler = StandardScaler()
        X_train_s = x_scaler.fit_transform(X_train)
        X_test_s = x_scaler.transform(X_test)
        model_bundle = train_lstsq(X_train_s, Y_train)
        model_bundle["x_scaler"] = x_scaler
        preds = predict_lstsq(model_bundle, X_test_s)
    elif args.model == "mlp":
        model_bundle = train_mlp(X_train, Y_train)
        preds = predict_mlp(model_bundle, X_test)
    elif args.model == "rf":
        model_bundle = train_random_forest(X_train, Y_train)
        preds = predict_random_forest(model_bundle, X_test)
    elif args.model == "xgb":
        model_bundle = train_xgb(X_train, Y_train)
        preds = predict_xgb(model_bundle, X_test)
    elif args.model == "lstm":
        model_bundle = train_lstm(X_train, Y_train)
        preds = predict_lstm(model_bundle, X_test)
    elif args.model == "gru":
        model_bundle = train_gru(X_train, Y_train)
        preds = predict_gru(model_bundle, X_test)
    elif args.model == "transformer":
        model_bundle = train_transformer(X_train, Y_train)
        preds = predict_transformer(model_bundle, X_test)
    else:  # patchtst
        model_bundle = train_patchtst(X_train, Y_train, pred_len=forecast_steps)
        preds = predict_patchtst(model_bundle, X_test)

    metrics = evaluate(Y_test, preds, target_cols, target_meta)
    pred_df = pd.DataFrame(preds, columns=target_cols)
    if timeseries_mode:
        pred_df.insert(0, "time", time_series.iloc[train_size:].to_numpy())
    else:
        pred_df.insert(0, "time", test_df["time"].to_numpy())

    save_artifacts(model_bundle, metrics, pred_df, model_name=args.model)
    overall_print = dict(metrics["overall"])
    overall_pct = overall_print.get("误差百分比")
    if isinstance(overall_pct, (int, float, np.floating)) and not np.isnan(overall_pct):
        overall_print["误差百分比"] = f"{overall_pct}%"
    print("训练完成，整体指标:", overall_print)
    if metrics.get("groups"):
        for g, st in metrics["groups"].items():
            st_print = dict(st)
            st_pct = st_print.get("误差百分比")
            if isinstance(st_pct, (int, float, np.floating)) and not np.isnan(st_pct):
                st_print["误差百分比"] = f"{st_pct}%"
            print(f"{g} 指标:", st_print)
    print(f"输出目录: {ARTIFACT_DIR}")


if __name__ == "__main__":
    main()
