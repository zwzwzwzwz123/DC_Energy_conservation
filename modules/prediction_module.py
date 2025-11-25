"""
预测模块
---------
依据《孪生建模方案》实现的多场景、多目标预测流程：
1. 统一采样、缺失值约束、物理范围过滤
2. 单台空调 / 机房总空调 / 单台冷机 三类模型的特征—目标映射
3. 使用多输出回归器同时拟合功耗与温度类指标

关键设计要点（与方案对应）：
- 输入覆盖“控制动作/设定值”“执行结果”“环境扰动”
- 输出直接给出功耗、回风/送风温度、机房温度统计值等
- 默认 1min 采样，连续缺失不超过 5 个点，总缺失不超过 5%

使用方式（示例）：
    specs = build_default_specs()  # 或根据实际 UID 自定义
    predictor = TwinPredictor(specs, logger)
    ok_report = predictor.train_all(observable_data)
    predictions = predictor.predict_all(observable_data)
    # predictions 为 {model_name: {target_uid: value}}
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.multioutput import MultiOutputRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.neural_network import MLPRegressor
from sklearn.ensemble import GradientBoostingRegressor

from utils.data_processing import build_aligned_matrix

# ==================== 常量（与方案要求保持一致） ====================

DEFAULT_FREQ = "1min"  # 推荐统一采样周期
DEFAULT_MAX_MISSING_RATE = 0.05  # 总缺失率不超过 5%
DEFAULT_MAX_CONSECUTIVE_MISSING = 5  # 连续缺失不超过 5 个采样点


# ==================== 配置与规格定义 ====================

@dataclass
class TwinModelSpec:
    """
    单个模型的特征/目标映射与数据质量约束

    feature_map/target_map: {特征别名: influx uid}
    freq: 采样周期，用于重采样与对齐
    model_dir: 模型保存目录，为 None 时不落盘
    """

    name: str
    feature_map: Dict[str, str]
    target_map: Dict[str, str]
    freq: str = DEFAULT_FREQ
    max_missing_rate: float = DEFAULT_MAX_MISSING_RATE
    max_consecutive_missing: int = DEFAULT_MAX_CONSECUTIVE_MISSING
    model_dir: Optional[Path] = None
    base_estimator: Optional[object] = None
    estimator_name: str = "random_forest"  # 可选: random_forest, mlp, gradient_boosting 等
    estimator_params: Dict[str, object] = field(default_factory=dict)
    metadata: Dict[str, str] = field(default_factory=dict)

    def model_path(self) -> Optional[Path]:
        if not self.model_dir:
            return None
        self.model_dir.mkdir(parents=True, exist_ok=True)
        return self.model_dir / f"{self.name}.joblib"

# ==================== 核心模型类 ====================

def _create_estimator(
    name: str,
    params: Optional[Dict[str, object]],
    logger: logging.Logger,
) -> Tuple[object, bool]:
    """
    根据名称创建回归器。
    返回 (estimator, need_scaler)，便于在管道中按需添加标准化。
    """
    safe_params = params.copy() if params else {}
    key = (name or "random_forest").lower()

    if key in ("rf", "random_forest", "forest"):
        defaults = dict(
            n_estimators=240,
            max_depth=None,
            min_samples_leaf=2,
            random_state=42,
            n_jobs=-1,
        )
        defaults.update(safe_params)
        return RandomForestRegressor(**defaults), False

    if key in ("mlp", "mlp_regressor", "nn"):
        defaults = dict(
            hidden_layer_sizes=(128, 64),
            activation="relu",
            learning_rate_init=1e-3,
            max_iter=500,
            random_state=42,
        )
        defaults.update(safe_params)
        return MLPRegressor(**defaults), True

    if key in ("gbr", "gradient_boosting", "gbdt"):
        defaults = dict(random_state=42, n_estimators=300, learning_rate=0.05, max_depth=3)
        defaults.update(safe_params)
        return GradientBoostingRegressor(**defaults), False

    logger.warning(f"未知模型 {name}，回退到 RandomForestRegressor")
    return RandomForestRegressor(random_state=42, n_estimators=200), False


class TwinModel:
    """封装单个多目标预测模型的训练/推理/持久化流程。"""

    def __init__(self, spec: TwinModelSpec, logger: Optional[logging.Logger] = None):
        self.spec = spec
        self.logger = logger or logging.getLogger(__name__)

        if spec.base_estimator:
            estimator = spec.base_estimator
            need_scaler = False
        else:
            estimator, need_scaler = _create_estimator(spec.estimator_name, spec.estimator_params, self.logger)

        steps = [("imputer", SimpleImputer(strategy="median"))]
        if need_scaler:
            steps.append(("scaler", StandardScaler()))
        steps.append(("model", MultiOutputRegressor(estimator)))

        self.pipeline: Pipeline = Pipeline(steps)
        self.trained = False

    # ------------------------------------------------------------------ #
    # 数据准备
    # ------------------------------------------------------------------ #
    def _prepare_xy(
        self, data_map: Dict[str, pd.DataFrame]
    ) -> Optional[Tuple[pd.DataFrame, pd.DataFrame]]:
        """构建训练用特征矩阵 X 与目标矩阵 y。"""
        X, skipped_feat = build_aligned_matrix(
            data_map,
            self.spec.feature_map,
            self.spec.freq,
            self.spec.max_missing_rate,
            self.spec.max_consecutive_missing,
            self.logger,
        )
        y, skipped_target = build_aligned_matrix(
            data_map,
            self.spec.target_map,
            self.spec.freq,
            self.spec.max_missing_rate,
            self.spec.max_consecutive_missing,
            self.logger,
        )

        if skipped_feat:
            self.logger.warning(f"{self.spec.name}: 特征跳过 {skipped_feat}")
        if skipped_target:
            self.logger.warning(f"{self.spec.name}: 目标跳过 {skipped_target}")

        if X is None or y is None:
            return None

        # 对齐索引，保证 X 与 y 同步
        merged_index = X.index.intersection(y.index)
        X = X.loc[merged_index]
        y = y.loc[merged_index]

        # 再次清理
        X = X.replace([np.inf, -np.inf], np.nan)
        y = y.replace([np.inf, -np.inf], np.nan)
        mask = ~(X.isna().any(axis=1) | y.isna().any(axis=1))
        X = X.loc[mask]
        y = y.loc[mask]

        if X.empty or y.empty:
            self.logger.error(f"{self.spec.name}: 经过对齐后无有效样本")
            return None

        return X, y

    # ------------------------------------------------------------------ #
    # 训练 / 推理
    # ------------------------------------------------------------------ #
    def train(self, data_map: Dict[str, pd.DataFrame]) -> Tuple[bool, str]:
        """基于当前数据训练模型，返回 (是否成功, 说明)。"""
        prepared = self._prepare_xy(data_map)
        if prepared is None:
            return False, "数据不足或质量不达标"

        X, y = prepared
        self.logger.info(
            f"{self.spec.name}: 开始训练，样本 {len(X)}，特征 {list(self.spec.feature_map.keys())}，目标 {list(self.spec.target_map.keys())}"
        )
        self.pipeline.fit(X, y)
        self.trained = True

        # 持久化
        path = self.spec.model_path()
        if path:
            try:
                import joblib

                joblib.dump(self.pipeline, path)
                self.logger.info(f"{self.spec.name}: 模型已保存到 {path}")
            except Exception as exc:  # pragma: no cover - 保存失败不阻断流程
                self.logger.warning(f"{self.spec.name}: 模型保存失败 - {exc}")

        return True, "训练完成"

    def load_if_available(self) -> bool:
        """若存在已保存模型则加载，返回是否成功。"""
        path = self.spec.model_path()
        if not path or not path.exists():
            return False
        try:
            import joblib

            self.pipeline = joblib.load(path)
            self.trained = True
            self.logger.info(f"{self.spec.name}: 已加载持久化模型 {path}")
            return True
        except Exception as exc:
            self.logger.warning(f"{self.spec.name}: 模型加载失败 - {exc}")
            return False

    def predict(self, data_map: Dict[str, pd.DataFrame]) -> Optional[Dict[str, float]]:
        """
        使用最新一条特征数据进行推理。
        返回 {目标 uid: 预测值}，如无有效样本返回 None。
        """
        if not self.trained:
            self.logger.warning(f"{self.spec.name}: 未训练，跳过预测")
            return None

        feature_matrix, skipped = build_aligned_matrix(
            data_map,
            self.spec.feature_map,
            self.spec.freq,
            self.spec.max_missing_rate,
            self.spec.max_consecutive_missing,
            self.logger,
        )
        if skipped:
            self.logger.warning(f"{self.spec.name}: 推理特征跳过 {skipped}")

        if feature_matrix is None or feature_matrix.empty:
            self.logger.warning(f"{self.spec.name}: 无法构建推理特征")
            return None

        latest_row = feature_matrix.iloc[[-1]]
        preds = self.pipeline.predict(latest_row)[0]

        results: Dict[str, float] = {}
        for alias, value in zip(self.spec.target_map.keys(), preds):
            uid = self.spec.target_map[alias]
            results[uid] = float(value)
        return results


# ==================== 统一调度器 ====================

class TwinPredictor:
    """
    管理多场景预测模型：
    - 单台空调功率/回风/送风温度
    - 机房总空调功率 + 温度统计
    - 单台冷机功率
    """

    def __init__(self, specs: List[TwinModelSpec], logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
        self.models = {spec.name: TwinModel(spec, self.logger) for spec in specs}

    def load_all(self) -> Dict[str, bool]:
        """尝试加载所有已保存模型，返回 {name: 是否加载成功}。"""
        return {name: model.load_if_available() for name, model in self.models.items()}

    def train_all(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, str]:
        """批量训练所有模型，返回 {name: 状态描述}。"""
        status: Dict[str, str] = {}
        for name, model in self.models.items():
            ok, msg = model.train(data_map)
            status[name] = msg if ok else f"训练失败: {msg}"
        return status

    def predict_all(self, data_map: Dict[str, pd.DataFrame]) -> Dict[str, Dict[str, float]]:
        """
        对所有已训练模型执行推理，返回 {model_name: {target_uid: value}}。
        未训练或无数据的模型将被跳过。
        """
        results: Dict[str, Dict[str, float]] = {}
        for name, model in self.models.items():
            pred = model.predict(data_map)
            if pred:
                results[name] = pred
            else:
                self.logger.warning(f"{name}: 无预测结果")
        return results

    def flatten_predictions(self, predictions: Dict[str, Dict[str, float]]) -> Dict[str, float]:
        """
        将 predict_all 的结构拍平，便于直接写入 influx（uid -> value）。
        """
        merged: Dict[str, float] = {}
        for pred in predictions.values():
            merged.update(pred)
        return merged


# ==================== 默认规格（依据方案） ====================

def _default_model_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "checkpoints" / "prediction"


def build_default_specs(estimator_config: Optional[Dict[str, object]] = None) -> List[TwinModelSpec]:
    """
    依据方案文档预置三类模型的特征/目标映射。
    可在此处或外部配置中将 UID 替换为现场对应测点。

    参数:
        estimator_config: 可选的估计器配置 dict，例如
            {
                "name": "mlp",  # 或 random_forest / gradient_boosting
                "params": {...} # 对应 sklearn 模型参数
            }
    """
    model_dir = _default_model_dir()
    est_name = "random_forest"
    est_params: Dict[str, object] = {}
    if estimator_config:
        est_name = estimator_config.get("name", est_name)
        est_params = estimator_config.get("params", {}) or {}

    single_ac_spec = TwinModelSpec(
        name="single_air_conditioner",
        # 控制动作 / 执行结果 / 环境扰动
        feature_map={
            "chw_supply_temp_setpoint": "48dec2b7_15d8_46bd_9ca5_425d08eb9e3e",  # 放冷泵变频温度设定
            "chw_supply_temp": "26aa984f_ddc1_4c33_9c96_b3313aad2a72",  # 冷冻总管回水平均温度（作为末端温度代表）
            "pump_or_flow_feedback": "a616e7a5_256e_474b_845a_1d2a90501361",  # 冷冻流量/泵频
            "supply_temp_setpoint": "ac_supply_temp_setpoint",  # 需按现场 UID 替换
            "humidity_setpoint": "ac_humidity_setpoint",  # 需按现场 UID 替换
            "fan_speed_feedback": "ac_fan_speed_feedback",  # 需按现场 UID 替换
            "water_valve_opening": "ac_water_valve_opening",  # 需按现场 UID 替换
            "it_load_power": "room_it_total_power",  # 环境扰动
        },
        target_map={
            "ac_power": "ac_power",  # 单台空调功率
            "return_air_temp": "ac_return_air_temp",  # 回风温度
            "supply_air_temp": "ac_supply_air_temp",  # 送风温度
        },
        model_dir=model_dir,
        estimator_name=est_name,
        estimator_params=est_params,
        metadata={"scenario": "single_ac", "description": "单台空调功率 + 回/送风温度"},
    )

    room_spec = TwinModelSpec(
        name="room_multi_target",
        feature_map={
            "total_it_load": "room_it_total_power",
            "chw_supply_temp": "26aa984f_ddc1_4c33_9c96_b3313aad2a72",
            "header_pressure": "chilled_water_header_pressure",  # 如缺可替换为总管压差/泵频
            "avg_return_temp": "room_return_temp_mean",
            "avg_fan_speed": "room_fan_speed_mean",
            "avg_valve_opening": "room_valve_opening_mean",
        },
        target_map={
            "room_total_ac_power": "room_ac_total_power",
            "room_mean_temp": "room_mean_temp",
            "room_max_temp": "room_max_temp",
        },
        model_dir=model_dir,
        estimator_name=est_name,
        estimator_params=est_params,
        metadata={"scenario": "room", "description": "机房总功耗 + 温度统计"},
    )

    chiller_spec = TwinModelSpec(
        name="single_chiller",
        feature_map={
            "chw_supply_temp_setpoint": "48dec2b7_15d8_46bd_9ca5_425d08eb9e3e",
            "chw_return_temp_avg": "26aa984f_ddc1_4c33_9c96_b3313aad2a72",
            "chw_return_temp_1": "7c70b29c_173e_4b3a_9cb7_e49af1206593",
            "chw_return_temp_2": "aa95fde4_879a_468d_9a2a_cbd63121cb68",
            "cws_in_temp_1": "db8f1027_7dd8_4c30_8255_ccb5d86edbbb",
            "cws_in_temp_2": "61db6ac0_eeef_44d5_9f86_a7a2c07c74be",
            "cws_in_temp_3": "96767a02_149a_4d99_9e7f_118a155bacee",
            "cws_in_temp_4": "263ca4a7_70ae_4e17_8d22_58985fca090a",
            "chw_flow_1": "a616e7a5_256e_474b_845a_1d2a90501361",
            "chw_flow_2": "d4d52740_8708_4948_aeed_b31db72a55b2",
            "cws_flow_1": "d068e9c2_cc13_4429_8f00_74b9eb2e9efe",
            "cws_flow_2": "f33d9a62_38da_4eb6_b3ee_80860711640b",
        },
        target_map={
            "chiller_power": "chiller_power",  # 需替换为冷机功率测点 UID
        },
        model_dir=model_dir,
        estimator_name=est_name,
        estimator_params=est_params,
        metadata={"scenario": "chiller", "description": "单台冷机功率"},
    )

    return [single_ac_spec, room_spec, chiller_spec]


def build_specs_from_prediction_config(prediction_config: Optional[Dict[str, object]]) -> List[TwinModelSpec]:
    """
    辅助函数：直接从 prediction_config 读取 estimator 配置，便于通过配置切换模型。
    期望配置结构:
        prediction_model:
            estimator:
                name: "mlp"  # 或 "random_forest"/"gradient_boosting"
                params: {}   # sklearn 模型参数
    """
    pred_cfg = prediction_config.get("prediction_model", {}) if prediction_config else {}
    estimator_cfg = pred_cfg.get("estimator")
    return build_default_specs(estimator_cfg)


# ==================== 辅助输出 ====================

def export_spec_template(specs: List[TwinModelSpec]) -> str:
    """
    生成便于写入配置文件的 JSON 模板，帮助现场将 UID 填入。
    """
    payload = []
    for spec in specs:
        payload.append(
            {
                "name": spec.name,
                "feature_map": spec.feature_map,
                "target_map": spec.target_map,
                "freq": spec.freq,
                "max_missing_rate": spec.max_missing_rate,
                "max_consecutive_missing": spec.max_consecutive_missing,
            }
        )
    return json.dumps(payload, ensure_ascii=False, indent=2)
