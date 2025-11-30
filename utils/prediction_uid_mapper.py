"""
预测 UID 自动映射脚本

根据 uid_config.yaml 中的真实测点名称，自动为预测模块的
TwinModelSpec 填充 feature_map/target_map，避免手动逐个配置。

使用方式：
    python utils/prediction_uid_mapper.py \
        --uid-config configs/uid_config.yaml \
        --output configs/prediction_specs_generated.json

可选：
    --rules-file <path>  自定义别名与关键字的匹配规则（YAML/JSON）

输出：
    - 终端打印匹配结果摘要
    - 若指定 --output，会写入包含所有 TwinModelSpec 的 JSON
      以及每个 alias 的匹配来源，便于手工调整。
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
import sys

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.architecture_module import Attribute, DataCenter
from modules.prediction_module import TwinModelSpec, build_default_specs
from utils.architecture_config_parser import load_datacenter_from_config

LOGGER = logging.getLogger("prediction_uid_mapper")


def _normalize_text(text: str) -> str:
    """统一处理名称，便于模糊匹配。"""
    if not text:
        return ""
    lowered = text.lower()
    # 只保留字母、数字与中文，去掉空格/符号
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", lowered)


def _collect_attribute_records(datacenter: DataCenter) -> Tuple[List[Dict[str, str]], Dict[str, Dict[str, object]]]:
    """遍历数据中心，收集所有属性及其来源路径，供匹配使用。"""
    records: List[Dict[str, str]] = []
    ac_devices: Dict[str, Dict[str, object]] = {}
    device_records: Dict[str, List[Dict[str, str]]] = {}

    def add_record(
        attr: Attribute,
        source: str,
        room=None,
        system=None,
        device=None,
    ) -> None:
        if not attr or not attr.uid:
            return
        record = {
            "name": attr.name or "",
            "uid": attr.uid,
            "source": source,
            "normalized": _normalize_text(attr.name or ""),
            "device_uid": getattr(device, "device_uid", None),
            "device_type": getattr(device, "device_type", None),
            "room_uid": getattr(room, "room_uid", None),
            "room_name": getattr(room, "room_name", None),
        }
        records.append(record)
        if device and device.device_uid:
            device_records.setdefault(device.device_uid, []).append(record)

    # 数据中心级别属性
    for attr in datacenter.dc_attributes.values():
        add_record(attr, f"DataCenter:{datacenter.dc_name}")
    for sensor in datacenter.environment_sensors:
        for attr in sensor.attributes.values():
            add_record(attr, f"DataCenterSensor:{sensor.sensor_name}")

    for room in datacenter.computer_rooms:
        room_prefix = f"Room:{room.room_name}"
        for attr in room.room_attributes.values():
            add_record(attr, f"{room_prefix}/RoomAttribute", room=room)
        for sensor in room.environment_sensors:
            for attr in sensor.attributes.values():
                add_record(attr, f"{room_prefix}/Sensor:{sensor.sensor_name}", room=room)
        for system in room.air_cooled_systems + room.water_cooled_systems:
            system_prefix = f"{room_prefix}/System:{system.system_name}"
            for devices in system.devices.values():
                for device in devices:
                    device_prefix = f"{system_prefix}/Device:{device.device_name}"
                    for attr in device.attributes.values():
                        add_record(attr, device_prefix, room=room, system=system, device=device)
                    if device.device_type in ("AC_AirCooled", "AC_WaterCooled"):
                        ac_devices.setdefault(
                            device.device_uid,
                            {
                                "device_name": device.device_name,
                                "device_uid": device.device_uid,
                                "room_name": room.room_name,
                                "room_uid": room.room_uid,
                                "system_name": system.system_name,
                                "system_uid": getattr(system, "system_uid", None),
                                "device_type": device.device_type,
                            },
                        )

    for uid, info in ac_devices.items():
        info["records"] = device_records.get(uid, [])

    return records, ac_devices


DEFAULT_ALIAS_RULES: Dict[str, List[List[str]]] = {
    # 单台空调
    "chw_supply_temp_setpoint": [["供", "水", "设定"], ["出水", "设定"]],
    "chw_supply_temp": [["供", "水", "温度"], ["出水", "温度"]],
    "pump_or_flow_feedback": [["冷冻", "流量"], ["泵", "频"]],
    "supply_temp_setpoint": [["送风", "设定"], ["出风", "设定"]],
    "humidity_setpoint": [["湿度", "设定"]],
    "fan_speed_feedback": [["风机", "转速"], ["风机", "频率"]],
    "water_valve_opening": [["水阀", "开"], ["阀门", "开度"]],
    "it_load_power": [["it", "功率"], ["it", "负荷"], ["信息化", "功率"]],
    "ac_power": [["空调", "功率"]],
    "return_air_temp": [["回风", "温度"], ["回风", "temp"]],
    "supply_air_temp": [["送风", "温度"], ["出风", "温度"]],
    # 机房
    "total_it_load": [["it", "功率"], ["it", "负荷"]],
    "header_pressure": [["总管", "压力"], ["集管", "压力"]],
    "avg_return_temp": [["回风", "温度"], ["回风", "平均"]],
    "avg_fan_speed": [["风机", "平均"], ["风机", "转速"]],
    "avg_valve_opening": [["阀", "开度", "平均"]],
    "room_total_ac_power": [["空调", "总", "功率"], ["总", "功率", "空调"]],
    "room_mean_temp": [["机房", "平均", "温度"]],
    "room_max_temp": [["机房", "最高", "温度"], ["机房", "最大", "温度"]],
    # 冷机
    "chw_return_temp_avg": [["回水", "平均", "温度"], ["回水", "温度"]],
    "chw_return_temp_1": [["冷冻", "回水", "1"]],
    "chw_return_temp_2": [["冷冻", "回水", "2"]],
    "cws_in_temp_1": [["冷却", "进水", "1"]],
    "cws_in_temp_2": [["冷却", "进水", "2"]],
    "cws_in_temp_3": [["冷却", "进水", "3"]],
    "cws_in_temp_4": [["冷却", "进水", "4"]],
    "chw_flow_1": [["冷冻", "流量", "1"], ["冷冻", "泵", "1"]],
    "chw_flow_2": [["冷冻", "流量", "2"], ["冷冻", "泵", "2"]],
    "cws_flow_1": [["冷却", "流量", "1"], ["冷却", "泵", "1"]],
    "cws_flow_2": [["冷却", "流量", "2"], ["冷却", "泵", "2"]],
    "chiller_power": [["冷机", "功率"], ["制冷机", "功率"]],
}

DEVICE_SPECIFIC_FEATURE_ALIASES = {"supply_temp_setpoint", "humidity_setpoint", "fan_speed_feedback", "water_valve_opening"}
DEVICE_SPECIFIC_TARGET_ALIASES = {"ac_power", "return_air_temp", "supply_air_temp"}
ALWAYS_KEEP_UNMATCHED_TARGETS = {"ac_power"}
COMMENT_MAP = {
    "room_multi_target": "机房整体模型",
    "single_chiller": "冷水机组模型",
}


def _merge_rules(
    default_rules: Dict[str, List[List[str]]],
    custom_rules: Optional[Dict[str, Iterable[Iterable[str]]]],
) -> Dict[str, List[List[str]]]:
    if not custom_rules:
        return default_rules

    merged = {key: list(val) for key, val in default_rules.items()}
    for alias, patterns in custom_rules.items():
        merged.setdefault(alias, [])
        for rule in patterns:
            merged[alias].append([_normalize_text(token) for token in rule])
    return merged


def _match_attribute(
    records: List[Dict[str, str]],
    alias: str,
    rules: Dict[str, List[List[str]]],
    candidate_records: Optional[List[Dict[str, str]]] = None,
) -> Optional[Tuple[Dict[str, str], int]]:
    """
    根据别名的关键字规则寻找最佳匹配的属性。
    返回 (record, score)；未匹配时返回 None。
    """
    patterns = rules.get(alias)
    if not patterns:
        return None

    best_record: Optional[Dict[str, str]] = None
    best_score = 0

    pool = candidate_records if candidate_records is not None else records

    for rec in pool:
        name_norm = rec["normalized"]
        score = 0
        for pattern in patterns:
            if all(token in name_norm for token in pattern):
                score = max(score, len(pattern))
        if score > best_score:
            best_score = score
            best_record = rec

    if best_record and best_score > 0:
        return best_record, best_score
    return None


def _spec_to_dict(spec: TwinModelSpec) -> Dict[str, object]:
    payload = asdict(spec)
    # dataclasses.asdict 会把 Path 转成 Path，需要转 str
    if payload.get("model_dir"):
        payload["model_dir"] = str(payload["model_dir"])
    return payload


def auto_fill_specs(
    datacenter: DataCenter,
    prediction_config_path: Path,
    custom_rules: Optional[Dict[str, Iterable[Iterable[str]]]] = None,
) -> Tuple[List[Dict[str, object]], Dict[str, Dict[str, str]]]:
    with prediction_config_path.open("r", encoding="utf-8") as f:
        prediction_cfg = yaml.safe_load(f) or {}

    pred_cfg = prediction_cfg.get("prediction_model", {}) if prediction_cfg else {}
    estimator_cfg = pred_cfg.get("estimator")

    base_specs = build_default_specs(estimator_cfg)
    records, ac_devices = _collect_attribute_records(datacenter)
    merged_rules = _merge_rules(DEFAULT_ALIAS_RULES, custom_rules)
    match_report: Dict[str, Dict[str, str]] = {}

    single_ac_template: Optional[TwinModelSpec] = None
    final_specs: List[TwinModelSpec] = []

    for spec in base_specs:
        if spec.name == "single_air_conditioner":
            single_ac_template = spec
        else:
            final_specs.append(spec)

    def record_match(
        key: str,
        alias: str,
        current_uid: str,
        match: Optional[Tuple[Dict[str, str], int]],
        keep_if_unmatched: bool = False,
    ) -> Optional[str]:
        if match:
            rec, score = match
            match_report[key] = {
                "uid": rec["uid"],
                "name": rec["name"],
                "source": rec["source"],
                "score": score,
            }
            return rec["uid"]
        if keep_if_unmatched:
            match_report[key] = {
                "uid": current_uid,
                "name": "未匹配，保留原值",
                "source": "",
                "score": 0,
            }
            return current_uid
        match_report[key] = {
            "uid": None,
            "name": "未匹配，已移除",
            "source": "",
            "score": 0,
        }
        return None

    # 填充非单台空调的规格
    for spec in final_specs:
        comment = COMMENT_MAP.get(spec.name)
        if comment:
            spec.metadata = {**(spec.metadata or {}), "comment": comment}
        new_feature_map: Dict[str, str] = {}
        for alias, current_uid in list(spec.feature_map.items()):
            match = _match_attribute(records, alias, merged_rules)
            uid_val = record_match(f"{spec.name}:{alias}", alias, current_uid, match)
            if uid_val:
                new_feature_map[alias] = uid_val
        spec.feature_map = new_feature_map

        new_target_map: Dict[str, str] = {}
        for alias, current_uid in list(spec.target_map.items()):
            match = _match_attribute(records, alias, merged_rules)
            uid_val = record_match(
                f"{spec.name}:{alias}",
                alias,
                current_uid,
                match,
                keep_if_unmatched=(alias in ALWAYS_KEEP_UNMATCHED_TARGETS),
            )
            if uid_val:
                new_target_map[alias] = uid_val
        spec.target_map = new_target_map

    # 针对每台空调生成独立 spec
    if single_ac_template and ac_devices:
        global_aliases = [alias for alias in single_ac_template.feature_map if alias not in DEVICE_SPECIFIC_FEATURE_ALIASES]
        global_matches: Dict[str, Optional[Tuple[Dict[str, str], int]]] = {
            alias: _match_attribute(records, alias, merged_rules) for alias in global_aliases
        }

        for device_uid, info in ac_devices.items():
            spec = deepcopy(single_ac_template)
            spec.name = f"{single_ac_template.name}__{device_uid}"
            spec.metadata = {
                **(spec.metadata or {}),
                "device_uid": device_uid,
                "device_name": info.get("device_name"),
                "room_uid": info.get("room_uid"),
                "room_name": info.get("room_name"),
                "system_uid": info.get("system_uid"),
                "system_name": info.get("system_name"),
                "comment": f"{info.get('room_name') or ''}-{info.get('device_name') or ''} 空调模型",
            }
            device_records = info.get("records") or []

            new_feature_map: Dict[str, str] = {}
            for alias, current_uid in list(spec.feature_map.items()):
                if alias in DEVICE_SPECIFIC_FEATURE_ALIASES:
                    match = _match_attribute(records, alias, merged_rules, device_records)
                else:
                    match = global_matches.get(alias)
                uid_val = record_match(f"{spec.name}:{alias}", alias, current_uid, match)
                if uid_val:
                    new_feature_map[alias] = uid_val
            spec.feature_map = new_feature_map

            new_target_map: Dict[str, str] = {}
            for alias, current_uid in list(spec.target_map.items()):
                if alias in DEVICE_SPECIFIC_TARGET_ALIASES:
                    match = _match_attribute(records, alias, merged_rules, device_records)
                else:
                    match = _match_attribute(records, alias, merged_rules)
                uid_val = record_match(
                    f"{spec.name}:{alias}",
                    alias,
                    current_uid,
                    match,
                    keep_if_unmatched=(alias in ALWAYS_KEEP_UNMATCHED_TARGETS),
                )
                if uid_val:
                    new_target_map[alias] = uid_val
            spec.target_map = new_target_map

            final_specs.append(spec)

    return [_spec_to_dict(spec) for spec in final_specs], match_report


def load_custom_rules(path: Optional[Path]) -> Optional[Dict[str, List[List[str]]]]:
    if not path:
        return None
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    aliases = data.get("aliases") or {}
    parsed: Dict[str, List[List[str]]] = {}
    for alias, patterns in aliases.items():
        parsed[alias] = []
        for pattern in patterns:
            if isinstance(pattern, str):
                pattern_tokens = [_normalize_text(pattern)]
            else:
                pattern_tokens = [_normalize_text(token) for token in pattern]
            parsed[alias].append([token for token in pattern_tokens if token])
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser(description="Auto map prediction model aliases to actual UIDs.")
    parser.add_argument(
        "--uid-config",
        type=Path,
        default=Path("configs/uid_config.yaml"),
        help="路径：数据中心 UID 配置（默认 configs/uid_config.yaml）",
    )
    parser.add_argument(
        "--prediction-config",
        type=Path,
        default=Path("configs/prediction_config.yaml"),
        help="路径：预测配置文件（用于读取估计器参数）",
    )
    parser.add_argument(
        "--rules-file",
        type=Path,
        help="可选：自定义匹配规则（YAML/JSON，结构为 aliases -> alias -> [[关键词...], ...]）",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="可选：将生成的 spec 与匹配报告写入 JSON 文件",
    )

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    with args.uid_config.open("r", encoding="utf-8") as f:
        uid_cfg = yaml.safe_load(f)
    arch_logger = logging.getLogger("prediction_uid_mapper.arch")
    arch_logger.setLevel(logging.ERROR)
    datacenter = load_datacenter_from_config(uid_cfg, arch_logger)

    custom_rules = load_custom_rules(args.rules_file)

    specs, report = auto_fill_specs(datacenter, args.prediction_config, custom_rules)

    payload = {"specs": specs, "matches": report}
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    print(text)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(f"\n已将映射结果写入 {args.output}")


if __name__ == "__main__":
    main()
