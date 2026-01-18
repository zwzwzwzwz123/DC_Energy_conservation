"""
将 uid 目录下的两份 Excel（空调、温湿度）解析成架构化的 uid_config.yaml。

生成的配置遵循 modules/architecture_module.py 定义的层次结构，便于
utils/architecture_config_parser.py 直接加载。
"""

from pathlib import Path
import re
from typing import Dict, List, Optional, Tuple

import pandas as pd
import yaml


PROJECT_ROOT = Path(__file__).resolve().parent.parent
UID_DIR = PROJECT_ROOT / "uid"
OUTPUT_PATH = PROJECT_ROOT / "configs" / "uid_config.yaml"

# 映射采集点类型到属性类型
POINT_TYPE_TO_ATTR_TYPE = {
    "AI": "telemetry",
    "DI": "telesignaling",
    "AO": "teleadjusting",
    "DO": "telecontrol",
}


def _safe_str(value: object) -> Optional[str]:
    """将单元格转换为字符串并剔除空值。"""
    if value is None or pd.isna(value):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return str(value).strip()


def _slugify(name: str, prefix: str) -> str:
    """将中文名称转成可作 uid 的字符串。"""
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", name)
    cleaned = cleaned.strip("_") or prefix
    return f"{prefix}_{cleaned}"


def _find_excel_files() -> Tuple[Path, Path]:
    """在 uid 目录中自动识别空调表与温湿度表。"""
    env_file = None
    ac_file = None

    for path in UID_DIR.glob("*.xls"):
        # 只读取前两行即可判断列头
        preview = pd.read_excel(path, header=None, nrows=2)
        header_row = " ".join(preview.iloc[1].astype(str).tolist())

        if "point.unit" in header_row:
            env_file = path
        else:
            ac_file = path

    if not env_file or not ac_file:
        raise FileNotFoundError("未能在 uid 目录下同时找到空调和温湿度 Excel 文件")

    return env_file, ac_file


def _load_structured_table(path: Path) -> pd.DataFrame:
    """
    读取 Excel 并使用“字段名”行作为表头，跳过随后的说明行。
    """
    raw = pd.read_excel(path, header=None)

    header_row_idx = None
    for idx, row in raw.iterrows():
        if row.astype(str).str.contains("device.node_name", na=False).any():
            header_row_idx = idx
            break

    if header_row_idx is None:
        raise ValueError(f"未在 {path.name} 中找到字段名行")

    headers = raw.iloc[header_row_idx].tolist()
    data_start = header_row_idx + 4  # 跳过：字段含义、填写说明、数据类型

    df = raw.iloc[data_start:].copy()
    df.columns = headers
    df = df.dropna(how="all")
    return df


def _map_attr_type(point_type: Optional[str]) -> str:
    if not point_type:
        return "others"
    return POINT_TYPE_TO_ATTR_TYPE.get(point_type.upper(), "others")


def build_environment_sensors(df: pd.DataFrame) -> List[Dict]:
    sensors = []
    location_col = "*space_complete_name" if "*space_complete_name" in df.columns else None

    for (device_name, device_uid), group in df.groupby(["*device.node_name", "device.uid"]):
        attrs: List[Dict[str, str]] = []
        for _, row in group.iterrows():
            attr_name = _safe_str(row.get("*point.node_name"))
            attr_uid = _safe_str(row.get("point.uid"))
            if not attr_name or not attr_uid:
                continue

            node_type = _safe_str(row.get("*point.node_type"))
            unit = _safe_str(row.get("point.unit")) if "point.unit" in row else None

            attr = {
                "name": attr_name,
                "uid": attr_uid,
                "attr_type": _map_attr_type(node_type),
                "field_key": "value",
            }
            if unit:
                attr["unit"] = unit
            attrs.append(attr)

        sensor = {
            "sensor_name": _safe_str(device_name) or str(device_uid),
            "sensor_uid": _safe_str(device_uid) or "",
            "location": _safe_str(group[location_col].iloc[0]) if location_col else None,
            "attributes": attrs,
        }
        sensors.append(sensor)

    return sensors


def build_air_conditioners(df: pd.DataFrame) -> List[Dict]:
    air_conditioners = []
    location_col = "*space_complete_name" if "*space_complete_name" in df.columns else None

    for (device_name, device_uid), group in df.groupby(["*device.node_name", "device.uid"]):
        attrs: List[Dict[str, str]] = []
        for _, row in group.iterrows():
            attr_name = _safe_str(row.get("*point.node_name"))
            attr_uid = _safe_str(row.get("point.uid"))
            if not attr_name or not attr_uid:
                continue

            node_type = _safe_str(row.get("*point.node_type"))

            attr = {
                "name": attr_name,
                "uid": attr_uid,
                "attr_type": _map_attr_type(node_type),
                "field_key": "value",
            }
            attrs.append(attr)

        ac = {
            "device_name": _safe_str(device_name) or str(device_uid),
            "device_uid": _safe_str(device_uid) or "",
            "location": _safe_str(group[location_col].iloc[0]) if location_col else None,
            "is_available": True,
            "attributes": attrs,
        }
        air_conditioners.append(ac)

    return air_conditioners


def derive_room_and_dc_info(env_df: pd.DataFrame, ac_df: pd.DataFrame) -> Dict[str, str]:
    """从空间路径推断数据中心/机房名称与 uid。"""

    def _pick_space(df: pd.DataFrame) -> Optional[str]:
        if "*space_complete_name" not in df.columns:
            return None
        values = df["*space_complete_name"].dropna().tolist()
        return _safe_str(values[0]) if values else None

    space_path = _pick_space(env_df) or _pick_space(ac_df)

    room_name = "默认机房"
    datacenter_name = "默认数据中心"
    if space_path:
        parts = [p for p in space_path.split("/") if p]
        if parts:
            datacenter_name = parts[0]
            room_name = parts[-1]

    return {
        "datacenter_name": datacenter_name,
        "datacenter_uid": _slugify(datacenter_name, "DC"),
        "room_name": room_name,
        "room_uid": _slugify(room_name, "CR"),
        "system_name": f"{room_name}水冷空调系统",
        "system_uid": f"{_slugify(room_name, 'WC')}_001",
        "location": space_path,
    }


def assemble_uid_config(env_sensors: List[Dict], air_conditioners: List[Dict], meta: Dict[str, str]) -> Dict:
    """按 architecture_config_parser 需要的格式构建配置字典。"""
    room_entry = {
        "room_name": meta["room_name"],
        "room_uid": meta["room_uid"],
        "room_type": "WaterCooled",
        "location": meta["location"],
        "environment_sensors": env_sensors,
        "water_cooled_systems": [
            {
                "system_name": meta["system_name"],
                "system_uid": meta["system_uid"],
                "is_available": True,
                "air_conditioners": air_conditioners,
            }
        ],
    }

    config = {
        "datacenter": {
            "name": meta["datacenter_name"],
            "uid": meta["datacenter_uid"],
            "location": meta["location"],
            "computer_rooms": [room_entry],
        }
    }
    return config


def main() -> None:
    env_path, ac_path = _find_excel_files()
    print(f"检测到温湿度文件: {env_path.name}")
    print(f"检测到空调文件: {ac_path.name}")

    env_df = _load_structured_table(env_path)
    ac_df = _load_structured_table(ac_path)

    env_sensors = build_environment_sensors(env_df)
    air_conditioners = build_air_conditioners(ac_df)
    meta = derive_room_and_dc_info(env_df, ac_df)

    uid_config = assemble_uid_config(env_sensors, air_conditioners, meta)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        yaml.safe_dump(uid_config, f, allow_unicode=True, sort_keys=False, indent=2)

    print("\nuid_config.yaml 生成完成")
    print(f"数据中心: {meta['datacenter_name']} ({meta['datacenter_uid']})")
    print(f"机房: {meta['room_name']} ({meta['room_uid']})")
    print(f"环境传感器数量: {len(env_sensors)}")
    print(f"空调数量: {len(air_conditioners)}")
    print(f"输出路径: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
