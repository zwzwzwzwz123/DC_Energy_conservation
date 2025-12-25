"""时序数据重采样、清洗与对齐的工具函数集合。

集中封装了常用的缺失值处理、异常检测、分位裁剪以及多测点对齐逻辑，便于在
训练与推理阶段复用一致的数据预处理流程。
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


def max_consecutive_nan(series: pd.Series) -> int:
    """计算序列中连续 NaN 的最长长度。

    参数:
        series: 待检测的一维数值序列。

    返回:
        最长连续缺失段的长度（样本点数）。
    """
    max_run = 0
    current = 0
    for is_nan in series.isna():
        if is_nan:
            current += 1
            max_run = max(max_run, current)
        else:
            current = 0
    return max_run


def resample_series(df: pd.DataFrame, freq: str, agg: str = "mean") -> pd.Series:
    """将单个测点的 timestamp/value 数据按指定频率重采样。

    参数:
        df: 包含 timestamp 和 value 两列的原始测点数据。
        freq: 目标采样周期，示例 "1min"、"5min"。
        agg: 重采样的聚合方式，支持 mean/sum/last。

    返回:
        处理后的 Series（索引为重采样后的时间戳）。
    """
    if df is None or df.empty or "timestamp" not in df.columns or "value" not in df.columns:
        return pd.Series(dtype=float)

    tmp = df.copy()
    tmp["timestamp"] = pd.to_datetime(tmp["timestamp"], utc=True, errors="coerce")
    tmp = tmp.dropna(subset=["timestamp"])
    if tmp.empty:
        return pd.Series(dtype=float)

    tmp = tmp.sort_values("timestamp")
    tmp["timestamp"] = tmp["timestamp"].dt.floor(freq)
    series = tmp.set_index("timestamp")["value"]

    agg = (agg or "mean").lower()
    if agg == "sum":
        series = series.resample(freq).sum()
    elif agg == "last":
        series = series.resample(freq).last()
    else:
        series = series.resample(freq).mean()

    return series.astype(float)


def clip_outliers(
    series: pd.Series,
    method: str = "zscore",
    z_thresh: float = 4.0,
    lower_q: float = 0.01,
    upper_q: float = 0.99,
    hard_bounds: Optional[Dict[str, Optional[float]]] = None,
) -> pd.Series:
    """执行基础的异常值剔除，并可附加硬上下限过滤。

    参数:
        series: 待处理的序列。
        method: "zscore" 或 "quantile"；"none" 表示仅按硬阈值清洗。
        z_thresh: zscore 阈值。
        lower_q/upper_q: 分位点裁剪阈值。
        hard_bounds: 可选的硬性上下限字典，例如 {"lower": 0, "upper": 100}。

    返回:
        剔除了异常值（以 NaN 代替）的序列。
    """
    if series.empty:
        return series

    s = series.copy()
    if method == "zscore":
        mu = s.mean()
        std = s.std()
        if std and not np.isnan(std):
            mask = (np.abs((s - mu) / std) > z_thresh)
            s[mask] = np.nan
    elif method == "quantile":
        lo = s.quantile(lower_q)
        hi = s.quantile(upper_q)
        s = s.clip(lower=lo, upper=hi)

    if hard_bounds:
        lo = hard_bounds.get("lower")
        hi = hard_bounds.get("upper")
        if lo is not None:
            s = s.where(s >= lo, np.nan)
        if hi is not None:
            s = s.where(s <= hi, np.nan)

    return s


def frozen_check(series: pd.Series, max_flat_len: int = 10, epsilon: float = 1e-6) -> pd.Series:
    """将变化小于阈值且持续过长的“冻结”区间置为 NaN。

    参数:
        series: 待分析的序列。
        max_flat_len: 允许的最大平坦段长度（含）。
        epsilon: 认为“无变化”的绝对差阈值。

    返回:
        处理后的序列，长时间无波动的片段被置为 NaN。
    """
    if series.empty:
        return series

    s = series.copy()
    diff = s.diff().abs() <= epsilon
    groups = (diff != diff.shift()).cumsum()
    run_lengths = diff.groupby(groups).transform("sum")
    mask = diff & (run_lengths > max_flat_len)
    s[mask] = np.nan
    return s


def fill_missing_segments(
    series: pd.Series,
    method: str = "linear",
    short_limit: int = 5,
    allow_edge: bool = True,
) -> pd.Series:
    """仅填补较短的缺口，较长的缺口继续保持 NaN。

    参数:
        series: 待补齐的序列。
        method: "linear"/"mean"/"ffill"/"none"。
        short_limit: 允许填补的连续缺失点数上限。
        allow_edge: True 时允许填补序列两端的短缺口。

    返回:
        填补后的序列。
    """
    if series.empty:
        return series

    s = series.copy()
    method = (method or "linear").lower()
    if method == "linear":
        s = s.interpolate(
            method="time",
            limit=short_limit,
            limit_direction="both" if allow_edge else "forward",
        )
        s = s.ffill(limit=short_limit).bfill(limit=short_limit)
    elif method == "mean":
        mean_val = s.mean()
        s = s.fillna(mean_val)
    elif method == "ffill":
        s = s.ffill(limit=short_limit)
        if allow_edge:
            s = s.bfill(limit=short_limit)

    return s


def clean_series(
    series: pd.Series,
    alias: str,
    runtime_mask: Optional[pd.Series] = None,
    cfg: Optional[Dict[str, object]] = None,
) -> pd.Series:
    """按配置依次执行冻结检测、异常值处理、分位裁剪与平滑。

    参数:
        series: 待处理序列。
        alias: 测点别名，便于根据名称判定 setpoint 或特例。
        runtime_mask: 运行区间掩码，可用于限定计算分位点。
        cfg: 处理配置，支持 frozen_check/outlier/quantile_clipping/smoothing 等键。

    返回:
        清洗后的序列。
    """
    if series.empty or cfg is None:
        return series

    s = series.copy()
    frozen_cfg = cfg.get("frozen_check")
    if frozen_cfg:
        s = frozen_check(
            s,
            max_flat_len=int(frozen_cfg.get("max_flat_len", 10)),
            epsilon=float(frozen_cfg.get("epsilon", 1e-6)),
        )

    exclude_cols = cfg.get("exclude_columns", []) or []
    alias_lower = alias.lower()
    is_setpoint = cfg.get("avoid_setpoint_quantile", True) and (
        "setpoint" in alias_lower
        or alias_lower.endswith("_sp")
        or alias_lower == "sp"
        or alias in exclude_cols
    )

    out_cfg = cfg.get("outlier")
    if out_cfg:
        s = clip_outliers(
            s,
            method="none",
            hard_bounds=out_cfg.get("hard_bounds"),
        )
        s = clip_outliers(
            s,
            method=out_cfg.get("method", "zscore"),
            z_thresh=float(out_cfg.get("z_thresh", 4.0)),
            lower_q=float(out_cfg.get("lower_q", 0.01)),
            upper_q=float(out_cfg.get("upper_q", 0.99)),
            hard_bounds=out_cfg.get("hard_bounds"),
        )

    quant_cfg = cfg.get("quantile_clipping")
    if quant_cfg and not is_setpoint:
        method = quant_cfg.get("method", "quantile")
        if method == "quantile":
            q_lo = float(quant_cfg.get("lower_q", 0.01))
            q_hi = float(quant_cfg.get("upper_q", 0.99))
            subset = s[runtime_mask] if runtime_mask is not None else s
            if subset.dropna().empty:
                lo, hi = s.quantile(q_lo), s.quantile(q_hi)
            else:
                lo, hi = subset.quantile(q_lo), subset.quantile(q_hi)
            s = s.clip(lower=lo, upper=hi)
        elif method == "zscore":
            s = clip_outliers(
                s,
                method="zscore",
                z_thresh=float(quant_cfg.get("z_thresh", 4.0)),
            )

    smooth_cfg = cfg.get("smoothing")
    if smooth_cfg and not is_setpoint:
        window = int(smooth_cfg.get("window", 1))
        if window > 1:
            s = s.rolling(window=window, center=bool(smooth_cfg.get("center", False)), min_periods=1).mean()

    return s


def build_aligned_matrix(
    data_map: Dict[str, pd.DataFrame],
    alias_to_uid: Dict[str, str],
    freq: str,
    max_missing_rate: float,
    max_consecutive_missing: int,
    logger: Optional[logging.Logger] = None,
    outlier_cfg: Optional[Dict[str, object]] = None,
    agg: str = "mean",
    fill_cfg: Optional[Dict[str, object]] = None,
    preprocess_cfg: Optional[Dict[str, object]] = None,
    runtime_masks: Optional[Dict[str, pd.Series]] = None,
    join_how: str = "outer",
    per_alias_thresholds: Optional[Dict[str, Dict[str, float]]] = None,
    row_missing_tolerance: Optional[float] = None,
) -> Tuple[Optional[pd.DataFrame], List[Tuple[str, str]]]:
    """将 {别名 -> uid} 的多测点数据重采样、清洗后对齐成统一矩阵。

    参数:
        data_map: uid -> DataFrame(timestamp/value) 的原始数据映射。
        alias_to_uid: 需要组装的别名与 uid 对应关系。
        freq/max_missing_rate/max_consecutive_missing: 重采样频率及缺失约束。
        logger: 可选日志器，用于记录被跳过的测点。
        outlier_cfg/preprocess_cfg/fill_cfg: 额外的清洗与缺口填补配置。
        runtime_masks: 别名 -> mask 序列，常用于限定运行区间。
        join_how: "outer"/"inner"，控制对齐方式。
        per_alias_thresholds: 针对特定别名的缺失阈值覆写。
        row_missing_tolerance: 行级缺失比例上限，大于该阈值的时间戳会被丢弃。

    返回:
        (对齐后的矩阵, 被跳过的 (alias, uid) 列表)。
    """
    series_dict: Dict[str, pd.Series] = {}
    skipped: List[Tuple[str, str]] = []
    per_alias_thresholds = per_alias_thresholds or {}
    join_how = join_how if join_how in ("inner", "outer") else "outer"

    if fill_cfg is None:
        effective_fill_cfg = {"method": "linear", "short_limit": 3, "allow_edge": False}
    else:
        effective_fill_cfg = fill_cfg.copy()

    row_limit = max_missing_rate if row_missing_tolerance is None else float(row_missing_tolerance)
    row_limit = max(0.0, min(1.0, row_limit))

    for alias, uid in alias_to_uid.items():
        df = data_map.get(uid)
        if df is None or df.empty:
            skipped.append((alias, uid))
            if logger:
                logger.warning(f"[{alias}]({uid}) 无可用数据，跳过")
            continue

        series = resample_series(df, freq, agg=agg)
        if series.empty:
            skipped.append((alias, uid))
            if logger:
                logger.warning(f"[{alias}]({uid}) 重采样后无可用数据，跳过")
            continue

        alias_cfg = per_alias_thresholds.get(alias, {})
        alias_missing_limit = float(alias_cfg.get("max_missing_rate", max_missing_rate))
        alias_gap_limit = int(alias_cfg.get("max_consecutive_missing", max_consecutive_missing))

        missing_rate = series.isna().mean()
        max_gap = max_consecutive_nan(series)
        if missing_rate > alias_missing_limit or max_gap > alias_gap_limit:
            skipped.append((alias, uid))
            if logger:
                logger.warning(
                    f"[{alias}]({uid}) 缺失率 {missing_rate:.3f} 或连续缺失 {max_gap} 超限，跳过"
                )
            continue

        if preprocess_cfg:
            series = clean_series(
                series,
                alias=alias,
                runtime_mask=(runtime_masks or {}).get(alias),
                cfg=preprocess_cfg,
            )

        if outlier_cfg:
            per_alias_cfg = outlier_cfg.get("per_alias", {}) if isinstance(outlier_cfg, dict) else {}
            alias_outlier_cfg = per_alias_cfg.get(alias, {})
            base_cfg = outlier_cfg if isinstance(outlier_cfg, dict) else {}
            merged_cfg = {**base_cfg, **alias_outlier_cfg}
            series = clip_outliers(
                series,
                method=merged_cfg.get("method", "zscore"),
                z_thresh=float(merged_cfg.get("z_thresh", 4.0)),
                lower_q=float(merged_cfg.get("lower_q", 0.01)),
                upper_q=float(merged_cfg.get("upper_q", 0.99)),
                hard_bounds=merged_cfg.get("hard_bounds"),
            )

        series = series.replace([np.inf, -np.inf], np.nan)

        fill_method = (effective_fill_cfg or {}).get("method", "linear")
        if fill_method and fill_method.lower() != "none":
            series = fill_missing_segments(
                series,
                method=fill_method,
                short_limit=int((effective_fill_cfg or {}).get("short_limit", 5)),
                allow_edge=bool((effective_fill_cfg or {}).get("allow_edge", True)),
            )

        series_dict[alias] = series

    if not series_dict:
        if logger:
            logger.error("无法构建任何可用测点矩阵")
        return None, skipped

    matrix = pd.concat(series_dict.values(), axis=1, join=join_how).sort_index()
    matrix.columns = list(series_dict.keys())
    matrix = matrix.dropna(axis=1, how="all")

    if matrix.empty:
        if logger:
            logger.error("对齐后无有效列")
        return None, skipped

    if join_how == "outer" and row_limit < 1.0:
        row_missing = matrix.isna().mean(axis=1)
        matrix = matrix[row_missing <= row_limit]

    matrix = matrix.loc[~matrix.index.duplicated(keep="last")]

    if matrix.empty:
        if logger:
            logger.error("对齐后无有效样本")
        return None, skipped

    return matrix, skipped


__all__ = [
    "max_consecutive_nan",
    "resample_series",
    "build_aligned_matrix",
    "clip_outliers",
    "frozen_check",
    "fill_missing_segments",
    "clean_series",
]
