# -*- coding: utf-8 -*-
"""
uid_mapping_builder

读取 `uid/103A机房建模信息整理.xlsx`（多 sheet），生成建模用的 UID 映射：
- 末端空调：根据“特征”包含温/湿判定为传感器，其余为空调特征
- 列头柜：映射为 cabinet_feed
- 冷冻水：暂存为 other

输出：generated/103A_modeling/uid_mapping.json 和 uid_mapping.csv
"""
import json
import re
from pathlib import Path
from typing import Dict, List

import pandas as pd

SRC_EXCEL = Path("uid") / "103A机房建模信息整理.xlsx"
OUT_JSON = Path(__file__).with_name("uid_mapping.json")
OUT_CSV = Path(__file__).with_name("uid_mapping.csv")

SHEET_AC = "末端空调"
SHEET_CHW = "冷冻水"
SHEET_CABINET = "列头柜"
SHEET_THS = "温湿度计"

COL_NAME_AC = "设备名称"
COL_FEATURE_AC = "特征"
COL_UID_AC = "uid"

COL_NAME_OTHER = "Unnamed: 0"
COL_UID_OTHER = "uid"


def load_sheets(path: Path) -> Dict[str, pd.DataFrame]:
    if not path.exists():
        raise FileNotFoundError(f"源文件不存在: {path}")
    xls = pd.ExcelFile(path)
    sheets = {}
    for name in xls.sheet_names:
        if name == SHEET_THS:
            # 温湿度计 sheet 可能无表头，强制 header=None 保留首行数据
            sheets[name] = xls.parse(name, header=None)
        else:
            sheets[name] = xls.parse(name)
    return sheets


def classify_feature(feature: str) -> str:
    text = str(feature)
    if "设定" in text or "设定点" in text:
        return "ac_setpoint"
    return "ac_feature"


def normalize_ac(df: pd.DataFrame) -> List[Dict]:
    records = []
    for _, row in df.iterrows():
        name = row.get(COL_NAME_AC)
        feature = row.get(COL_FEATURE_AC)
        uid = row.get(COL_UID_AC)
        if pd.isna(uid) or pd.isna(name):
            continue
        category = classify_feature(feature)
        rec = {
            "name": str(name),
            "uid": str(uid),
            "tag": None if pd.isna(feature) else str(feature),
            "category": category,
        }
        records.append(rec)
    return records


def normalize_cabinet(df: pd.DataFrame) -> List[Dict]:
    records = []
    for _, row in df.iterrows():
        name = row.get(COL_NAME_OTHER)
        uid = row.get(COL_UID_OTHER)
        if pd.isna(uid) or pd.isna(name):
            continue
        records.append(
            {
                "name": str(name),
                "uid": str(uid),
                "tag": None,
                "category": "cabinet_feed",
            }
        )
    return records


def normalize_chw(df: pd.DataFrame) -> List[Dict]:
    records = []
    for _, row in df.iterrows():
        name = row.get(COL_NAME_OTHER)
        uid = row.get(COL_UID_OTHER)
        if pd.isna(uid) or pd.isna(name):
            continue
        records.append(
            {
                "name": str(name),
                "uid": str(uid),
                "tag": None,
                "category": "extra_feature",
            }
        )
    return records


def normalize_ths(df: pd.DataFrame) -> List[Dict]:
    # 预期三列：名称、标签（如温/湿）、uid（无表头，header=None）
    records = []
    for _, row in df.iterrows():
        if len(row) < 3:
            continue
        name, tag, uid = row.iloc[0], row.iloc[1], row.iloc[2]
        if pd.isna(uid) or pd.isna(name):
            continue
        records.append(
            {
                "name": str(name),
                "uid": str(uid),
                "tag": None if pd.isna(tag) else str(tag),
                "category": "temp_humidity_sensor",
            }
        )
    return records


def normalize_all(sheets: Dict[str, pd.DataFrame]) -> Dict:
    records = []
    extra_features = []
    if SHEET_AC in sheets:
        records.extend(normalize_ac(sheets[SHEET_AC]))
    if SHEET_CABINET in sheets:
        records.extend(normalize_cabinet(sheets[SHEET_CABINET]))
    if SHEET_CHW in sheets:
        extra_features.extend(normalize_chw(sheets[SHEET_CHW]))
    if SHEET_THS in sheets:
        records.extend(normalize_ths(sheets[SHEET_THS]))

    ac = {}
    sensors = []
    cabinets = []
    others = []

    for rec in records:
        if rec["category"] == "ac_setpoint":
            m = re.search(r"(\d+)#", rec["name"])
            ac_no = m.group(1) if m else rec["name"]
            ac.setdefault(ac_no, []).append({"param": rec["uid"], "tag": rec["tag"]})
        elif rec["category"] == "temp_humidity_sensor":
            sensors.append(rec)
        elif rec["category"] == "cabinet_feed":
            cabinets.append(rec)
        else:
            others.append(rec)

    return {
        "raw_records": records,
        "air_conditioners": ac,
        "sensors": sensors,
        "cabinets": cabinets,
        "others": others,
        "extra_features": extra_features,
    }


def write_outputs(mapping: Dict) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = [
        {"name": r["name"], "uid": r["uid"], "tag": r["tag"], "category": r["category"]}
        for r in mapping["raw_records"]
    ]
    pd.DataFrame(rows).to_csv(OUT_CSV, index=False, encoding="utf-8")


def main():
    sheets = load_sheets(SRC_EXCEL)
    mapping = normalize_all(sheets)
    write_outputs(mapping)
    print(f"完成：{OUT_JSON} 和 {OUT_CSV}")
    print(
        f"AC参数: {len(mapping['air_conditioners'])}，传感器: {len(mapping['sensors'])}，列头柜: {len(mapping['cabinets'])}，其他: {len(mapping['others'])}"
    )


if __name__ == "__main__":
    main()
