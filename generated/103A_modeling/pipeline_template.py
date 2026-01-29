"""
pipeline_template

- 读取 `uid_mapping.json`
- 从 InfluxDB 1.8 拉取时序（设定点 + 温湿度传感器）
- 特征构造（滞后）
- 拟合多输出模型（linear / lstsq / mlp / lstm / tree-based / boosting）
- 输出模型、评估指标、预测结果
"""
import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

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
        raise FileNotFoundError(f'缺少映射文件: {path}，请先运行 uid_mapping_builder.py')
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
    # Influx returns columns 'time' and 'value'
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


def _fill_timeseries_base(df: pd.DataFrame) -> pd.DataFrame:
    """Fill missing values per column to avoid losing samples."""
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


def fill_timeseries(df: pd.DataFrame) -> pd.DataFrame:
    """包装填充函数，先检查列名是否重复，避免重复列导致后续操作歧义。"""
    if df.empty:
        return df
    cols = list(df.columns)
    dupes = [c for c in cols if cols.count(c) > 1 and c != 'time']
    if dupes:
        raise RuntimeError(f'列名重复，无法填充：{sorted(set(dupes))}')
    return _fill_timeseries_base(df)


def ensure_datetime(df: pd.DataFrame) -> pd.DataFrame:
    """确保 time 列为 datetime 类型。"""
    if df.empty:
        return df
    out = df.copy()
    out['time'] = pd.to_datetime(out['time'])
    return out


def shift_targets(target_df: pd.DataFrame, horizon: pd.Timedelta) -> pd.DataFrame:
    """将目标时间前移 horizon，使特征时间 t 对应目标 t+Δ。"""
    if target_df.empty:
        return target_df
    df = target_df.copy()
    df['time'] = pd.to_datetime(df['time']) - horizon
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
            if col == 'time':
                continue
            renamed[col] = f"{col}__t+{k}"
        shifted = shifted.rename(columns=renamed)
        merged = shifted if merged is None else merged.merge(shifted, on='time', how='inner')
    return merged


def build_feature_matrix(ac_df: pd.DataFrame, lags: int = 3) -> pd.DataFrame:
    feat = ac_df.copy().sort_values('time').reset_index(drop=True)
    for col in feat.columns:
        if col == 'time':
            continue
        for k in range(1, lags + 1):
            feat[f'{col}_lag{k}'] = feat[col].shift(k)
    feat = feat.dropna().reset_index(drop=True)
    return feat


def build_lstm_sequences(df: pd.DataFrame, feature_cols: List[str], lags: int) -> np.ndarray:
    """
    根据 lag 特征重排为 (n_samples, seq_len, n_base_features) 的序列输入，顺序为最远 lag 到当前值。
    """
    base_features = [c for c in feature_cols if '_lag' not in c]
    seq_len = lags + 1
    seq_mats = []
    for f in base_features:
        cols = [f"{f}_lag{k}" for k in range(lags, 0, -1)] + [f]
        for c in cols:
            if c not in df.columns:
                raise RuntimeError(f"LSTM 序列缺失列 {c}，请检查 lags 或特征构造")
        seq_mats.append(df[cols].to_numpy())
    # stack to shape (n_samples, seq_len, n_base_features)
    seq_arr = np.stack(seq_mats, axis=2)
    return seq_arr


def build_lstm_sequences_table(df: pd.DataFrame, feature_cols: List[str], seq_len: int):
    """将表格数据转换为 LSTM 输入序列 (n_samples, seq_len, n_features)。"""
    if seq_len <= 0:
        seq_len = 1
    df_sorted = df.sort_values('time').reset_index(drop=True)
    if len(df_sorted) < seq_len:
        raise RuntimeError(f"样本过少，无法构造序列：seq_len={seq_len}，样本={len(df_sorted)}")
    arr = df_sorted[feature_cols].to_numpy()
    seqs = []
    for i in range(seq_len - 1, len(df_sorted)):
        seqs.append(arr[i - seq_len + 1: i + 1])
    seq_arr = np.stack(seqs, axis=0)
    trimmed_df = df_sorted.iloc[seq_len - 1:].reset_index(drop=True)
    return seq_arr, trimmed_df


def slugify(name: str) -> str:
    s = re.sub(r"[^0-9A-Za-z_]+", "_", name)
    s = s.strip("_")
    return s or "col"


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
        hidden_layer_sizes=(128, 64),
        activation='relu',
        max_iter=600,
        alpha=5e-4,
        early_stopping=True,
        validation_fraction=0.2,
        random_state=42,
    )
    model.fit(Xs, Y)
    return {'type': 'mlp', 'scaler': scaler, 'model': model}


def predict_mlp(model_bundle, X: np.ndarray) -> np.ndarray:
    Xs = model_bundle['scaler'].transform(X)
    return model_bundle['model'].predict(Xs)


def train_lstm(X_seq: np.ndarray, Y: np.ndarray, epochs: int = 60, lr: float = 1e-3, hidden_size: int = 32):
    try:
        import torch
        from torch import nn
    except ImportError as exc:
        raise ImportError("缺少依赖 torch，无法使用 lstm 模型；请安装 torch") from exc

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    scaler = StandardScaler()
    N, T, F = X_seq.shape
    Xs_flat = scaler.fit_transform(X_seq.reshape(N, T * F))
    Xs = Xs_flat.reshape(N, T, F)

    X_tensor = torch.tensor(Xs, dtype=torch.float32).to(device)  # (batch, seq, feat)
    Y_tensor = torch.tensor(Y, dtype=torch.float32).to(device)

    input_dim = F
    seq_len = T
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
        'seq_len': seq_len,
        'device': str(device),
    }


def predict_lstm(model_bundle, X_seq: np.ndarray) -> np.ndarray:
    import torch
    from torch import nn

    scaler = model_bundle['scaler']
    input_dim = model_bundle['input_dim']
    hidden_size = model_bundle['hidden_size']
    output_dim = model_bundle['output_dim']
    seq_len = model_bundle['seq_len']
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

    N, T, F = X_seq.shape
    if T != seq_len or F != input_dim:
        raise RuntimeError(f"LSTM 输入维度不符：期望 (.*, {seq_len}, {input_dim})，实际 ({N}, {T}, {F})")
    Xs_flat = scaler.transform(X_seq.reshape(N, T * F))
    Xs = Xs_flat.reshape(N, T, F)
    X_tensor = torch.tensor(Xs, dtype=torch.float32).to(device)
    model.eval()
    with torch.no_grad():
        preds = model(X_tensor).cpu().numpy()
    return preds


def train_gru(X_seq: np.ndarray, Y: np.ndarray, epochs: int = 60, lr: float = 1e-3, hidden_size: int = 32):
    try:
        import torch
        from torch import nn
    except ImportError as exc:
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
            idx = perm[i:i + batch_size]
            xb = X_tensor[idx]
            yb = Y_tensor[idx]
            optimizer.zero_grad()
            pred = model(xb)
            loss = criterion(pred, yb)
            loss.backward()
            optimizer.step()

    return {
        'type': 'gru',
        'scaler': scaler,
        'state_dict': model.state_dict(),
        'hidden_size': hidden_size,
        'input_dim': F,
        'output_dim': output_dim,
        'seq_len': T,
        'device': str(device),
    }


def predict_gru(model_bundle, X_seq: np.ndarray) -> np.ndarray:
    import torch
    from torch import nn

    scaler = model_bundle['scaler']
    input_dim = model_bundle['input_dim']
    hidden_size = model_bundle['hidden_size']
    output_dim = model_bundle['output_dim']
    seq_len = model_bundle['seq_len']
    state_dict = model_bundle['state_dict']

    class GRUReg(nn.Module):
        def __init__(self, input_dim, hidden_size, output_dim):
            super().__init__()
            self.gru = nn.GRU(input_size=input_dim, hidden_size=hidden_size, batch_first=True)
            self.fc = nn.Linear(hidden_size, output_dim)

        def forward(self, x):
            out, _ = self.gru(x)
            out = out[:, -1, :]
            return self.fc(out)

    device = torch.device(model_bundle.get('device', 'cpu'))
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
    except ImportError as exc:
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
            idx = perm[i:i + batch_size]
            xb = X_tensor[idx]
            yb = Y_tensor[idx]
            optimizer.zero_grad()
            pred = model(xb)
            loss = criterion(pred, yb)
            loss.backward()
            optimizer.step()

    return {
        'type': 'transformer',
        'scaler': scaler,
        'state_dict': model.state_dict(),
        'input_dim': F,
        'output_dim': output_dim,
        'seq_len': T,
        'd_model': d_model,
        'nhead': nhead,
        'num_layers': num_layers,
        'dim_feedforward': dim_feedforward,
        'dropout': dropout,
        'device': str(device),
    }


def predict_transformer(model_bundle, X_seq: np.ndarray) -> np.ndarray:
    import torch
    from torch import nn

    scaler = model_bundle['scaler']
    input_dim = model_bundle['input_dim']
    output_dim = model_bundle['output_dim']
    seq_len = model_bundle['seq_len']
    d_model = model_bundle['d_model']
    nhead = model_bundle['nhead']
    num_layers = model_bundle['num_layers']
    dim_feedforward = model_bundle['dim_feedforward']
    dropout = model_bundle['dropout']
    state_dict = model_bundle['state_dict']

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

    device = torch.device(model_bundle.get('device', 'cpu'))
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
    patch_root = Path(__file__).resolve().parents[2] / 'models' / 'PatchTST' / 'PatchTST_supervised'
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
    except ImportError as exc:
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
            configs.n_heads = 2
            configs.d_model = 32
            configs.d_ff = 64
            configs.dropout = 0.1
            configs.fc_dropout = 0.1
            configs.head_dropout = 0.1
            configs.individual = False
            configs.patch_len = patch_len
            configs.stride = stride
            configs.padding_patch = 'end'
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
    batch_size = min(8, len(X_tensor))
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
        'type': 'patchtst',
        'scaler': scaler,
        'state_dict': model.state_dict(),
        'input_dim': F,
        'target_dim': target_dim,
        'seq_len': T,
        'pred_len': pred_len,
        'patch_len': patch_len,
        'stride': stride,
        'device': str(device),
    }


def predict_patchtst(model_bundle, X_seq: np.ndarray) -> np.ndarray:
    import torch
    from torch import nn

    PatchTSTModel = _load_patchtst_model()
    scaler = model_bundle['scaler']
    input_dim = model_bundle['input_dim']
    target_dim = model_bundle['target_dim']
    seq_len = model_bundle['seq_len']
    pred_len = model_bundle['pred_len']
    patch_len = model_bundle['patch_len']
    stride = model_bundle['stride']
    state_dict = model_bundle['state_dict']

    class PatchTSTReg(nn.Module):
        def __init__(self, input_dim: int, target_dim: int, seq_len: int, pred_len: int):
            super().__init__()
            configs = type("Cfg", (), {})()
            configs.enc_in = input_dim
            configs.seq_len = seq_len
            configs.pred_len = pred_len
            configs.e_layers = 2
            configs.n_heads = 2
            configs.d_model = 32
            configs.d_ff = 64
            configs.dropout = 0.1
            configs.fc_dropout = 0.1
            configs.head_dropout = 0.1
            configs.individual = False
            configs.patch_len = patch_len
            configs.stride = stride
            configs.padding_patch = 'end'
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

    device = torch.device(model_bundle.get('device', 'cpu'))
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


def train_decision_tree(X: np.ndarray, Y: np.ndarray):
    model = MultiOutputRegressor(
        DecisionTreeRegressor(
            random_state=42,
            max_depth=8,
            min_samples_leaf=4,
        )
    )
    model.fit(X, Y)
    return {'type': 'dt', 'model': model}


def predict_decision_tree(model_bundle, X: np.ndarray) -> np.ndarray:
    return model_bundle['model'].predict(X)


def train_random_forest(X: np.ndarray, Y: np.ndarray):
    model = MultiOutputRegressor(
        RandomForestRegressor(
            n_estimators=250,
            max_depth=10,
            min_samples_leaf=4,
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
        n_estimators=400,
        learning_rate=0.05,
        num_leaves=31,
        max_depth=10,
        subsample=0.8,
        colsample_bytree=0.8,
        bagging_freq=1,
        reg_lambda=2.0,
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
        iterations=500,
        depth=6,
        learning_rate=0.05,
        loss_function='RMSE',
        l2_leaf_reg=5.0,
        random_seed=42,
        verbose=False,
    )
    model = MultiOutputRegressor(base)
    model.fit(X, Y)
    return {'type': 'cat', 'model': model}


def predict_catboost(model_bundle, X: np.ndarray) -> np.ndarray:
    return model_bundle['model'].predict(X)


def evaluate(y_true: np.ndarray, y_pred: np.ndarray, target_cols: List[str], sensor_meta: Dict) -> Dict:
    mse = np.mean((y_true - y_pred) ** 2, axis=0)
    mae = np.mean(np.abs(y_true - y_pred), axis=0)

    def error_pct(mae_val: float, mean_val: float) -> float:
        if mean_val is None or np.isnan(mean_val):
            return float("nan")
        denom = abs(float(mean_val))
        if denom <= 1e-12:
            return float("nan")
        return float(mae_val / denom * 100.0)

    overall = {
        'mse_mean': float(np.mean(mse)),
        'mae_mean': float(np.mean(mae)),
        '误差百分比': error_pct(float(np.mean(mae)), float(np.mean(y_true))),
    }

    def classify(meta: Dict) -> str:
        tag = str(meta.get('tag') or '')
        name = str(meta.get('name') or '')
        # 优先用 tag 做互斥判别
        if ('温' in tag) and ('湿' not in tag):
            return 'temperature'
        if ('湿' in tag) and ('温' not in tag):
            return 'humidity'
        # 其次用 name
        if ('温度' in name) and ('湿' not in name):
            return 'temperature'
        if ('湿度' in name) and ('温' not in name):
            return 'humidity'
        # 含“温湿度”等混合的，不分组
        return 'other'

    groups = {'temperature': [], 'humidity': []}
    for idx, col in enumerate(target_cols):
        base_col = col.split('__t+')[0]
        meta = sensor_meta.get(base_col, {})
        g = classify(meta)
        if g in groups:
            groups[g].append(idx)

    def _group_stats(indices: List[int]):
        if not indices:
            return None
        g_mse = float(np.mean((y_true[:, indices] - y_pred[:, indices]) ** 2))
        g_mae = float(np.mean(np.abs(y_true[:, indices] - y_pred[:, indices])))
        g_mean = float(np.mean(y_true[:, indices]))
        return {
            'mse_mean': g_mse,
            'mae_mean': g_mae,
            '误差百分比': error_pct(g_mae, g_mean),
            'count': len(indices),
        }

    group_metrics = {}
    for k, idxs in groups.items():
        stats = _group_stats(idxs)
        if stats:
            group_metrics[k] = stats

    return {
        'per_target_mse': mse.tolist(),
        'per_target_mae': mae.tolist(),
        'overall': overall,
        'groups': group_metrics,
    }


def _pick_chinese_font() -> str:
    try:
        from matplotlib import font_manager
    except Exception:
        return ""
    candidates = [
        "Microsoft YaHei",
        "SimHei",
        "SimSun",
        "Noto Sans CJK SC",
        "Source Han Sans SC",
        "Arial Unicode MS",
    ]
    available = {f.name for f in font_manager.fontManager.ttflist}
    for name in candidates:
        if name in available:
            return name
    return ""


def plot_predictions(
    test_time: np.ndarray,
    y_true: np.ndarray,
    y_pred: np.ndarray,
    target_cols: List[str],
    sensor_meta: Dict,
    model_name: str,
    out_dir: Path,
    horizon_td: Optional[pd.Timedelta] = None,
    history_df: Optional[pd.DataFrame] = None,
    seq_len: Optional[int] = None,
    sample_indices: Optional[List[int]] = None,
):
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("缺少 matplotlib，跳过预测可视化")
        return

    font_name = _pick_chinese_font()
    if font_name:
        plt.rcParams["font.sans-serif"] = [font_name]
    plt.rcParams["axes.unicode_minus"] = False

    model_name = model_name or "model"
    out_dir = Path(out_dir) / "plots"
    out_dir.mkdir(exist_ok=True)
    model_dir = out_dir / slugify(model_name)
    model_dir.mkdir(exist_ok=True)

    y_true_arr = np.asarray(y_true)
    y_pred_arr = np.asarray(y_pred)
    if y_true_arr.ndim == 1:
        y_true_arr = y_true_arr.reshape(-1, 1)
    if y_pred_arr.ndim == 1:
        y_pred_arr = y_pred_arr.reshape(-1, 1)

    times = pd.to_datetime(test_time, errors="coerce")
    if pd.isna(times).all():
        times = np.arange(len(test_time))

    is_multi_step = any("__t+" in col for col in target_cols)
    if is_multi_step and history_df is not None and seq_len and horizon_td is not None:
        hist_df = history_df.copy()
        hist_df["time"] = pd.to_datetime(hist_df["time"], errors="coerce", utc=True).dt.tz_convert(None)
        hist_df = hist_df.dropna(subset=["time"]).sort_values("time").reset_index(drop=True)
        if hist_df.empty:
            return
        hist_times = hist_df["time"].to_numpy()

        def _find_time_index(values: np.ndarray, target: pd.Timestamp) -> Optional[int]:
            if values.size == 0 or pd.isna(target):
                return None
            target64 = np.datetime64(target)
            idx = np.searchsorted(values, target64)
            if idx < len(values) and values[idx] == target64:
                return int(idx)
            if idx > 0 and values[idx - 1] == target64:
                return int(idx - 1)
            diffs = np.abs(values.astype("datetime64[ns]").astype("int64") - target64.astype("datetime64[ns]").astype("int64"))
            if diffs.size == 0:
                return None
            return int(diffs.argmin())

        grouped = {}
        for idx, col in enumerate(target_cols):
            if "__t+" not in col:
                continue
            base_col, step_label = col.split("__t+", 1)
            try:
                step_n = int(step_label)
            except ValueError:
                continue
            grouped.setdefault(base_col, []).append((step_n, idx))

        if not grouped:
            return

        if not sample_indices:
            sample_indices = [len(times) - 1] if len(times) > 0 else []

        for base_col, step_items in grouped.items():
            if base_col not in hist_df.columns:
                continue
            step_items = sorted(step_items, key=lambda x: x[0])
            step_idxs = [idx for _, idx in step_items]
            steps = len(step_idxs)
            meta = sensor_meta.get(base_col, {})
            name = meta.get("name") or meta.get("tag") or ""
            title = base_col if not name else f"{base_col} {name}"

            for sample_idx in sample_indices:
                if sample_idx < 0 or sample_idx >= len(times):
                    continue
                base_time = pd.to_datetime(times[sample_idx], errors="coerce", utc=True)
                if not pd.isna(base_time):
                    base_time = base_time.tz_convert(None)
                pos = _find_time_index(hist_times, base_time)
                if pos is None:
                    continue
                start_idx = pos - seq_len + 1
                if start_idx < 0:
                    continue
                hist_slice = slice(start_idx, pos + 1)
                hist_vals = hist_df.iloc[hist_slice][base_col].to_numpy()
                hist_plot_times = hist_times[hist_slice]
                true_seq = y_true_arr[sample_idx, step_idxs]
                pred_seq = y_pred_arr[sample_idx, step_idxs]
                forecast_times = [base_time + horizon_td * k for k in range(1, steps + 1)]

                fig, ax = plt.subplots(figsize=(12, 4))
                ax.plot(hist_plot_times, hist_vals, label="history", linewidth=1.4)
                ax.plot(forecast_times, true_seq, label="true", linewidth=1.4)
                ax.plot(forecast_times, pred_seq, label="pred", linewidth=1.4)
                ax.axvline(base_time, color="gray", linestyle="--", linewidth=1.0, alpha=0.8)
                ax.set_ylim(bottom=0)
                ax.set_title(title)
                ax.legend()
                ax.grid(True, alpha=0.3)
                ax.set_xlabel("time")
                ax.set_ylabel("value")
                fig.autofmt_xdate()
                fig.tight_layout()
                filename = f"{model_name}_{slugify(base_col)}_win{sample_idx}.png"
                fig.savefig(model_dir / filename, dpi=150)
                plt.close(fig)
        return

    for idx, col in enumerate(target_cols):
        base_col = col
        step_label = None
        if "__t+" in col:
            base_col, step_label = col.split("__t+", 1)
        meta = sensor_meta.get(base_col, {})
        name = meta.get("name") or meta.get("tag") or ""
        title = base_col if not name else f"{base_col} {name}"
        if step_label:
            title = f"{title} t+{step_label}"

        plot_time = times
        if step_label and horizon_td is not None and np.issubdtype(np.asarray(times).dtype, np.datetime64):
            try:
                step_n = int(step_label)
                plot_time = times + horizon_td * step_n
            except ValueError:
                plot_time = times

        fig, ax = plt.subplots(figsize=(12, 4))
        ax.plot(plot_time, y_true_arr[:, idx], label="真实值", linewidth=1.4)
        ax.plot(plot_time, y_pred_arr[:, idx], label="预测值", linewidth=1.4)
        ax.set_ylim(bottom=0)
        ax.set_title(title)
        ax.legend()
        ax.grid(True, alpha=0.3)
        ax.set_xlabel("time")
        ax.set_ylabel("value")
        fig.autofmt_xdate()
        fig.tight_layout()
        filename = f"{model_name}_{slugify(col)}.png"
        fig.savefig(model_dir / filename, dpi=150)
        plt.close(fig)


def split_train_test(dataset: pd.DataFrame, test_ratio: float = 0.2):
    """???????????????"""
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
    elif mtype == 'gru':
        joblib.dump(model_bundle, ARTIFACT_DIR / 'model_gru.pkl')
    elif mtype == 'transformer':
        joblib.dump(model_bundle, ARTIFACT_DIR / 'model_transformer.pkl')
    elif mtype == 'patchtst':
        joblib.dump(model_bundle, ARTIFACT_DIR / 'model_patchtst.pkl')
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
    parser.add_argument('--model', choices=['linear', 'lstsq', 'mlp', 'lstm', 'gru', 'transformer', 'patchtst', 'rf', 'dt', 'xgb', 'lgbm', 'cat'], default='linear')
    parser.add_argument('--lags', type=int, default=3, help='输入滞后阶数（用于特征构造）')
    parser.add_argument('--seq-len', type=int, default=None, help='(时序模型) 序列长度，默认 21（=7步×3）')
    parser.add_argument('--target-lags', type=int, default=None, help='(时序模型) 输出自回归阶数，默认 7')
    parser.add_argument('--horizon', default=None, help='(时序模型) 预测步长 Δ（单步间隔）；默认等于 every')
    parser.add_argument('--field', default='value', help='Influx 数值字段名，默认 value')
    parser.add_argument('--measurement-template', default='{uid}',
                        help='measurement 模板，默认与 uid 同名，可用 {uid} 占位')
    parser.add_argument('--client-key', default='influxdb_dc_status_data',
                        help='使用 utils_config.yaml 中的客户端键名，默认 influxdb_dc_status_data')
    args = parser.parse_args()

    seq_models = {'lstm', 'gru', 'transformer', 'patchtst'}
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

    # 默认时间范围：stop=当前UTC，start=往前一年
    now_utc = datetime.now(timezone.utc).replace(microsecond=0)
    stop = args.stop or now_utc.isoformat().replace('+00:00', 'Z')
    start = args.start or (now_utc - timedelta(days=365)).isoformat().replace('+00:00', 'Z')

    mapping = load_mapping(MAPPING_PATH)
    sensor_recs = mapping.get('sensors', [])
    sensor_uids = [r['uid'] for r in sensor_recs]
    sensor_meta = {r['uid']: r for r in sensor_recs}
    extra_features = mapping.get('extra_features', [])
    cabinet_recs = mapping.get('cabinets', [])
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
    extra_uids = [r['uid'] for r in extra_features]
    extra_col_rename = {}
    for idx, rec in enumerate(extra_features):
        base = slugify(rec.get('name') or f"extra_{idx}")
        # 强制唯一：加索引后缀
        col = f"extra_{base}_{idx}"
        extra_col_rename[rec['uid']] = col

    cabinet_uids = [r['uid'] for r in cabinet_recs]
    cabinet_col_rename = {}
    for idx, rec in enumerate(cabinet_recs):
        base = slugify(rec.get('name') or f"cab_{idx}")
        col = f"cab_{base}_{idx}"
        cabinet_col_rename[rec['uid']] = col

    print(f'拉取空调设定点 {len(ac_uids)} 个，传感器 {len(sensor_uids)} 个，额外特征 {len(extra_uids)} 个，列头柜 {len(cabinet_uids)} 个，时间范围 {start} ~ {stop}')
    ac_df = fetch_timeseries(ac_uids, start, stop, args.every,
                             field=args.field, measurement_template=args.measurement_template,
                             client_key=args.client_key)
    sensor_df = fetch_timeseries(sensor_uids, start, stop, args.every,
                                 field=args.field, measurement_template=args.measurement_template,
                                 client_key=args.client_key)
    extra_df = fetch_timeseries(extra_uids, start, stop, args.every,
                                 field=args.field, measurement_template=args.measurement_template,
                                 client_key=args.client_key) if extra_uids else pd.DataFrame()
    cabinet_df = fetch_timeseries(cabinet_uids, start, stop, args.every,
                                  field=args.field, measurement_template=args.measurement_template,
                                  client_key=args.client_key) if cabinet_uids else pd.DataFrame()

    # 填补缺失并标准化时间列
    ac_df = ensure_datetime(fill_timeseries(ac_df))
    sensor_df = ensure_datetime(fill_timeseries(sensor_df))
    extra_df = ensure_datetime(fill_timeseries(extra_df))
    cabinet_df = ensure_datetime(fill_timeseries(cabinet_df))

    # 将空调列名重命名为带 ac 编号的唯一名称，避免 merge 时列冲突
    if not ac_df.empty:
        ac_df = ac_df.rename(columns=ac_col_rename)
    if not extra_df.empty:
        extra_df = extra_df.rename(columns=extra_col_rename)
    if not cabinet_df.empty:
        cabinet_df = cabinet_df.rename(columns=cabinet_col_rename)

    if ac_df.empty or sensor_df.empty:
        raise RuntimeError('Influx 数据为空，请检查 measurement/field 或时间范围/客户端配置')

    # 仅对空调设定点做滞后；额外特征/列头柜不滞后
    base_ac_cols = [c for c in ac_df.columns if c != 'time']
    nonlag_df = ac_df[['time']].copy()
    if not extra_df.empty:
        nonlag_df = nonlag_df.merge(extra_df, on='time', how='outer')
        nonlag_df = fill_timeseries(nonlag_df)
    if not cabinet_df.empty:
        nonlag_df = nonlag_df.merge(cabinet_df, on='time', how='outer')
        nonlag_df = fill_timeseries(nonlag_df)

    ac_feat = build_feature_matrix(ac_df, lags=args.lags)
    feature_df = ac_feat.merge(nonlag_df, on='time', how='left')

    timeseries_mode = args.model in seq_models

    if timeseries_mode:
        # LSTM：加入输出历史（自回归）并平移目标到 t+Δ
        state_col_map = {uid: f"state_{uid}" for uid in sensor_uids}
        sensor_state_df = sensor_df.rename(columns=state_col_map)
        state_lag_df = build_feature_matrix(sensor_state_df, lags=max(args.target_lags, 0))

        feature_ts = feature_df.merge(state_lag_df, on='time', how='left')
        feature_ts = feature_ts.dropna().reset_index(drop=True)

        shifted_targets = build_multi_step_targets(sensor_df, horizon_step=horizon_td, steps=forecast_steps)
        dataset = align_and_join(feature_ts, shifted_targets)
        if dataset.empty:
            raise RuntimeError('对齐后数据为空，可能是时间窗口或聚合粒度不匹配')

        target_cols = [c for c in shifted_targets.columns if c != 'time']
        feature_cols = [c for c in dataset.columns if c not in ['time'] + target_cols]

        for col in feature_cols + target_cols:
            if dataset[col].notna().sum() == 0:
                raise RuntimeError(f'列 {col} 全为空，无法训练，请检查 Influx 配置或时间范围')

        seq_len = max(1, args.seq_len or window_steps)
        X_seq, seq_df = build_lstm_sequences_table(dataset, feature_cols, seq_len=seq_len)
        target_df = seq_df[target_cols]
        time_series = seq_df['time']

        n = len(seq_df)
        test_size = max(1, int(n * 0.2))
        train_size = n - test_size
        if train_size <= 0:
            raise RuntimeError('样本过少，无法划分训练/验证集')

        X_train = X_seq[:train_size]
        Y_train = target_df.iloc[:train_size].to_numpy()
        X_test = X_seq[train_size:]
        Y_test = target_df.iloc[train_size:].to_numpy()
        test_time = time_series.iloc[train_size:].to_numpy()
    else:
        dataset = align_and_join(feature_df, sensor_df)
        if dataset.empty:
            raise RuntimeError('对齐后数据为空，可能是时间窗口或聚合粒度不匹配')

        feature_cols = [c for c in feature_df.columns if c != 'time']
        target_cols = [c for c in sensor_df.columns if c != 'time']

        for col in feature_cols + target_cols:
            if dataset[col].notna().sum() == 0:
                raise RuntimeError(f'列 {col} 全为空，无法训练，请检查 Influx 配置或时间范围')

        train_df, test_df = split_train_test(dataset, test_ratio=0.2)

        X_train = train_df[feature_cols].to_numpy()
        Y_train = train_df[target_cols].to_numpy()
        X_test = test_df[feature_cols].to_numpy()
        Y_test = test_df[target_cols].to_numpy()
        test_time = test_df['time'].to_numpy()

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
    elif args.model == 'gru':
        model_bundle = train_gru(X_train, Y_train)
        preds = predict_gru(model_bundle, X_test)
    elif args.model == 'transformer':
        model_bundle = train_transformer(X_train, Y_train)
        preds = predict_transformer(model_bundle, X_test)
    elif args.model == 'patchtst':
        model_bundle = train_patchtst(X_train, Y_train, pred_len=forecast_steps)
        preds = predict_patchtst(model_bundle, X_test)
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

    metrics = evaluate(Y_test, preds, target_cols, sensor_meta)
    pred_df = pd.DataFrame(preds, columns=target_cols)
    pred_df.insert(0, 'time', test_time)

    save_artifacts(model_bundle, metrics, pred_df, model_name=args.model)
    sample_indices = None
    if timeseries_mode:
        total = len(test_time)
        sample_indices = [idx for idx in (total - 1, total - 2, total - 3) if idx >= 0]
    plot_predictions(
        test_time,
        Y_test,
        preds,
        target_cols,
        sensor_meta,
        args.model,
        ARTIFACT_DIR,
        horizon_td,
        history_df=sensor_df if timeseries_mode else None,
        seq_len=seq_len if timeseries_mode else None,
        sample_indices=sample_indices,
    )
    overall_print = dict(metrics['overall'])
    overall_pct = overall_print.get('误差百分比')
    if isinstance(overall_pct, (int, float, np.floating)) and not np.isnan(overall_pct):
        overall_print['误差百分比'] = f"{overall_pct}%"
    print('训练完成，整体指标：', overall_print)
    if metrics.get('groups'):
        if 'temperature' in metrics['groups']:
            temp_print = dict(metrics['groups']['temperature'])
            temp_pct = temp_print.get('误差百分比')
            if isinstance(temp_pct, (int, float, np.floating)) and not np.isnan(temp_pct):
                temp_print['误差百分比'] = f"{temp_pct}%"
            print('温度指标：', temp_print)
        if 'humidity' in metrics['groups']:
            hum_print = dict(metrics['groups']['humidity'])
            hum_pct = hum_print.get('误差百分比')
            if isinstance(hum_pct, (int, float, np.floating)) and not np.isnan(hum_pct):
                hum_print['误差百分比'] = f"{hum_pct}%"
            print('湿度指标：', hum_print)
    print(f'输出目录：{ARTIFACT_DIR}')


if __name__ == '__main__':
    main()
