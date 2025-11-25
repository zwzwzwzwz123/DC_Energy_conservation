"""
数据处理工具模块

提供通用的时序数据重采样、缺失校验与矩阵构建能力，便于预测/优化等模块复用。
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


def max_consecutive_nan(series: pd.Series) -> int:
    """
    计算序列中最长的连续缺失长度。

    参数:
        series: 输入序列

    返回:
        最长连续缺失段长度
    """
    max_run = current = 0
    for is_na in series.isna():
        if is_na:
            current += 1
            max_run = max(max_run, current)
        else:
            current = 0
    return max_run


def resample_series(df: pd.DataFrame, freq: str, agg: str = "mean") -> pd.Series:
    """
    将单个测点的 DataFrame 重采样到统一频率，并将时间戳对齐到目标频率的栅格。

    参数:
        df: 包含 timestamp/value 的 DataFrame
        freq: 目标采样周期（如 "1min"、"5min"）
        agg: 聚合方式，默认均值；支持 mean/sum/last

    行为:
        - 自动将时间戳转为 datetime(UTC)，并按 freq 对齐（floor）
        - 支持将原本非整分钟的时间（相差几秒）归并到对应栅格
        - 然后按目标频率重采样

    返回:
        重采样后的 Series（索引为时间戳）
    """
    if df is None or df.empty or "timestamp" not in df.columns or "value" not in df.columns:
        return pd.Series(dtype=float)

    tmp = df.copy()
    tmp["timestamp"] = pd.to_datetime(tmp["timestamp"], utc=True, errors="coerce")
    tmp = tmp.dropna(subset=["timestamp"])
    if tmp.empty:
        return pd.Series(dtype=float)

    tmp = tmp.sort_values("timestamp")
    # 先对齐到频率栅格（floor），将相差几秒的时间戳归并到同一时间点
    tmp["timestamp"] = tmp["timestamp"].dt.floor(freq)

    series = tmp.set_index("timestamp")["value"]

    # 支持简单的聚合选择，默认 mean
    if agg == "mean":
        series = series.resample(freq).mean()
    elif agg == "sum":
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
    """
    简单异常值处理。

    参数:
        series: 输入序列
        method: "zscore" 使用均值/标准差；"quantile" 使用分位裁剪；
                "none" 不做分布裁剪（但仍可用 hard_bounds）
        z_thresh: zscore 阈值
        lower_q/upper_q: 分位裁剪上下界
        hard_bounds: 显式上下界，如 {"lower": 0, "upper": 60}；None 表示不限制
    """
    if series.empty:
        return series

    s = series.copy()
    if method == "zscore":
        mu, std = s.mean(), s.std()
        if std == 0 or np.isnan(std):
            return s
        mask = (np.abs((s - mu) / std) > z_thresh)
        s[mask] = np.nan
    elif method == "quantile":
        lo, hi = s.quantile(lower_q), s.quantile(upper_q)
        s = s.clip(lower=lo, upper=hi)

    # 硬区间裁剪：超出范围直接置为 NaN
    if hard_bounds:
        lo = hard_bounds.get("lower")
        hi = hard_bounds.get("upper")
        if lo is not None:
            s = s.where(s >= lo, np.nan)
        if hi is not None:
            s = s.where(s <= hi, np.nan)
    return s


def frozen_check(series: pd.Series, max_flat_len: int = 10, epsilon: float = 1e-6) -> pd.Series:
    """
    死值检测：长时间不变的段落置为 NaN。

    参数:
        series: 输入序列
        max_flat_len: 超过该长度的平段视为卡死
        epsilon: 数值变动的容差
    """
    if series.empty:
        return series

    s = series.copy()
    # 使用 diff 向量化判断平段
    diff = s.diff().abs() <= epsilon
    # 连续 True 段落长度
    group = (diff != diff.shift()).cumsum()
    run_lengths = diff.groupby(group).transform("sum")
    mask = (diff) & (run_lengths > max_flat_len)
    s[mask] = np.nan
    return s


def fill_missing_segments(
    series: pd.Series,
    method: str = "linear",
    short_limit: int = 5,
    allow_edge: bool = True,
) -> pd.Series:
    """
    按缺失段长度填充短缺口，长缺口保留为 NaN，便于后续质量筛查。

    参数:
        series: 输入序列
        method: "linear" 使用时间插值；"mean" 用全局均值；其他返回原序列
        short_limit: 仅填充长度 <= short_limit 的连续缺失段
        allow_edge: 是否填充首尾的短缺口
    """
    if series.empty:
        return series

    s = series.copy()
    if method == "linear":
        s = s.interpolate(
            method="time",
            limit=short_limit,
            limit_direction="both" if allow_edge else "forward",
        )
        # 进一步使用有限窗口的前后填充，仍只针对短缺口
        s = s.ffill(limit=short_limit).bfill(limit=short_limit)
    elif method == "mean":
        mean_val = s.mean()
        s = s.fillna(mean_val)

    return s


def clean_series(
    series: pd.Series,
    alias: str,
    runtime_mask: Optional[pd.Series] = None,
    cfg: Optional[Dict[str, object]] = None,
) -> pd.Series:
    """
    组合清洗：死值检测 -> 硬区间/分位/ zscore -> 物理约束占位 -> 平滑。

    cfg 示例:
    {
        "frozen_check": {"max_flat_len": 10, "epsilon": 1e-6},
        "outlier": {  # 统一入口，先硬限再分布裁剪
            "method": "quantile",
            "lower_q": 0.01,
            "upper_q": 0.99,
            "hard_bounds": {"upper": 60},
        },
        "quantile_clipping": {...},  # 可选，基于运行掩码的分位
        "physics_constraint": null,  # 预留
        "smoothing": {"window": 3, "center": False},
        "avoid_setpoint_quantile": True,
        "exclude_columns": ["sp1", "manual_set"],  # 可显式排除列，不做分位/平滑
    }
    """
    if series.empty or cfg is None:
        return series

    s = series.copy()

    # 死值检测
    fc = cfg.get("frozen_check")
    if fc:
        s = frozen_check(
            s,
            max_flat_len=int(fc.get("max_flat_len", 10)),
            epsilon=float(fc.get("epsilon", 1e-6)),
        )

    # 是否跳过分位/平滑（避免 setpoint）或显式排除列
    exclude_cols = cfg.get("exclude_columns", []) or []
    is_setpoint = cfg.get("avoid_setpoint_quantile", True) and (
        "setpoint" in alias.lower() or "sp" == alias.lower() or alias.lower().endswith("_sp") or alias in exclude_cols
    )

    # 异常值：先硬限再分布裁剪
    out_cfg = cfg.get("outlier")
    if out_cfg:
        # 先硬限（如果提供）
        s = clip_outliers(
            s,
            method="none",
            hard_bounds=out_cfg.get("hard_bounds"),
        )
        # 再分布裁剪（zscore/quantile）
        s = clip_outliers(
            s,
            method=out_cfg.get("method", "zscore"),
            z_thresh=float(out_cfg.get("z_thresh", 4.0)),
            lower_q=float(out_cfg.get("lower_q", 0.01)),
            upper_q=float(out_cfg.get("upper_q", 0.99)),
            hard_bounds=out_cfg.get("hard_bounds"),
        )

    # 分位裁剪: 仅在非 setpoint 且 method=quantile 时基于运行段分布
    quant_cfg = cfg.get("quantile_clipping")
    if quant_cfg and not is_setpoint:
        method = quant_cfg.get("method", "quantile")
        if method == "quantile":
            q_lo = float(quant_cfg.get("lower_q", 0.01))
            q_hi = float(quant_cfg.get("upper_q", 0.99))
            # 如果有运行掩码，仅在运行段估计分位
            subset = s[runtime_mask] if runtime_mask is not None else s
            if subset.dropna().empty:
                lo, hi = s.quantile(q_lo), s.quantile(q_hi)
            else:
                lo, hi = subset.quantile(q_lo), subset.quantile(q_hi)
            s = s.clip(lower=lo, upper=hi)
        elif method == "zscore":
            s = clip_outliers(s, method="zscore", z_thresh=float(quant_cfg.get("z_thresh", 4.0)))

    # 物理逻辑占位（未来可扩展）
    # TODO: physics_constraint 针对关联传感器的检查

    # 平滑（避免对 setpoint 平滑）
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
) -> Tuple[Optional[pd.DataFrame], List[Tuple[str, str]]]:
    """
    将 {uid: DataFrame} 按映射转换为对齐后的矩阵，含缺失率/连续缺失校验。

    outlier_cfg 支持两种形式：
      - 全局配置：{"method": "...", "hard_bounds": {...}, ...}
      - 按别名覆盖：{"per_alias": {"temp": {...}, "power": {...}}, "method": "zscore", ...}
        先取 per_alias[alias]，找不到则回退全局

    参数:
        data_map: 输入数据字典，键为 uid，值为 DataFrame(timestamp/value)
        alias_to_uid: 别名 -> uid 映射（矩阵列名采用别名）
        freq: 重采样频率
        max_missing_rate: 允许的最大缺失率
        max_consecutive_missing: 允许的最长连续缺失点数
        logger: 可选日志器

    返回:
        (matrix, skipped)：
            - matrix: 对齐后的 DataFrame（index=timestamp, columns=alias），若无可用数据则为 None
            - skipped: List[(alias, uid)] 未通过质量校验或缺失的测点
    """
    series_dict: Dict[str, pd.Series] = {}
    skipped: List[Tuple[str, str]] = []

    for alias, uid in alias_to_uid.items():
        df = data_map.get(uid)
        if df is None or df.empty:
            skipped.append((alias, uid))
            if logger:
                logger.warning(f"[{alias}]({uid}) 数据缺失，跳过")
            continue

        series = resample_series(df, freq, agg=agg)
        if series.empty:
            skipped.append((alias, uid))
            if logger:
                logger.warning(f"[{alias}]({uid}) 重采样后无有效数据，跳过")
            continue

        missing_rate = series.isna().mean()
        max_gap = max_consecutive_nan(series)

        if missing_rate > max_missing_rate or max_gap > max_consecutive_missing:
            skipped.append((alias, uid))
            if logger:
                logger.warning(
                    f"[{alias}]({uid}) 缺失率 {missing_rate:.3f} 或连续缺失 {max_gap} 超限，跳过"
                )
            continue

        # 综合预处理（死值/分位/硬区间/平滑），如果提供的话
        if preprocess_cfg:
            series = clean_series(
                series,
                alias=alias,
                runtime_mask=(runtime_masks or {}).get(alias),
                cfg=preprocess_cfg,
            )

        # 额外的 per_alias 异常配置（与 preprocess_cfg 不冲突，可叠加）
        if outlier_cfg:
            per_alias_cfg = outlier_cfg.get("per_alias", {}) if isinstance(outlier_cfg, dict) else {}
            alias_cfg = per_alias_cfg.get(alias, {})
            base_cfg = outlier_cfg if isinstance(outlier_cfg, dict) else {}
            merged_cfg = {**base_cfg, **alias_cfg}
            s = clip_outliers(
                series,
                method=merged_cfg.get("method", "zscore"),
                z_thresh=float(merged_cfg.get("z_thresh", 4.0)),
                lower_q=float(merged_cfg.get("lower_q", 0.01)),
                upper_q=float(merged_cfg.get("upper_q", 0.99)),
                hard_bounds=merged_cfg.get("hard_bounds"),
            )
            series = s

        series = series.replace([np.inf, -np.inf], np.nan)

        # 填充短缺口，长缺口保留以便质量控制
        if fill_cfg:
            series = fill_missing_segments(
                series,
                method=fill_cfg.get("method", "linear"),
                short_limit=int(fill_cfg.get("short_limit", 5)),
                allow_edge=bool(fill_cfg.get("allow_edge", True)),
            )
        else:
            # 默认保留原逻辑：前后各一次填充
            series = series.ffill().bfill()

        series_dict[alias] = series

    if not series_dict:
        if logger:
            logger.error("无可用测点构建矩阵")
        return None, skipped

    join_how = join_how if join_how in ("inner", "outer") else "outer"
    matrix = pd.concat(series_dict.values(), axis=1, join=join_how)
    matrix.columns = list(series_dict.keys())

    if join_how == "outer":
        # 先用短缺口填充，再按缺失率过滤行
        if fill_cfg:
            filled_cols = []
            for col in matrix.columns:
                filled_cols.append(
                    fill_missing_segments(
                        matrix[col],
                        method=fill_cfg.get("method", "linear"),
                        short_limit=int(fill_cfg.get("short_limit", 5)),
                        allow_edge=bool(fill_cfg.get("allow_edge", True)),
                    )
                )
            matrix = pd.concat(filled_cols, axis=1)
            matrix.columns = list(series_dict.keys())

        row_missing = matrix.isna().mean(axis=1)
        matrix = matrix[row_missing <= max_missing_rate]

    matrix = matrix.dropna()

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
