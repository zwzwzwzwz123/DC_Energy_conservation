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
    将单个测点的 DataFrame 重采样到统一频率。

    参数:
        df: 包含 timestamp/value 的 DataFrame
        freq: 目标采样周期（如 "1min"）
        agg: 聚合方式，默认均值

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


def build_aligned_matrix(
    data_map: Dict[str, pd.DataFrame],
    alias_to_uid: Dict[str, str],
    freq: str,
    max_missing_rate: float,
    max_consecutive_missing: int,
    logger: Optional[logging.Logger] = None,
) -> Tuple[Optional[pd.DataFrame], List[Tuple[str, str]]]:
    """
    将 {uid: DataFrame} 按映射转换为对齐后的矩阵，含缺失率/连续缺失校验。

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

        series = resample_series(df, freq)
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

        series = series.replace([np.inf, -np.inf], np.nan).ffill().bfill()
        series_dict[alias] = series

    if not series_dict:
        if logger:
            logger.error("无可用测点构建矩阵")
        return None, skipped

    matrix = pd.concat(series_dict.values(), axis=1, join="inner")
    matrix.columns = list(series_dict.keys())
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
]
