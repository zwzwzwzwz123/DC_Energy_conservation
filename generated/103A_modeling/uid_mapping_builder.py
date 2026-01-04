"""
uid_mapping_builder

从 `uid/103A机房建模信息整理xlsx.xlsx` 读取点位，生成便于建模的映射。
输出：generated/103A_modeling/uid_mapping.json 与 uid_mapping.csv
"""
import json
import re
from pathlib import Path
from typing import Dict

import pandas as pd

SRC_EXCEL = Path("uid") / "103A机房建模信息整理xlsx.xlsx"
OUT_JSON = Path(__file__).with_name("uid_mapping.json")
OUT_CSV = Path(__file__).with_name("uid_mapping.csv")

COL_NAME = "设备名称"
COL_UID = "uid"
COL_TAG = "Unnamed: 3"
KW_AC = "空调"
KW_TH = "温湿度"
KW_CABINET = "列头柜"


def load_raw(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"源文件不存在: {path}")
    return pd.read_excel(path)


def classify_row(name: str) -> str:
    name = str(name)
    if KW_AC in name:
        return "ac_setpoint"
    if KW_TH in name:
        return "temp_humidity_sensor"
    if KW_CABINET in name:
        return "cabinet_feed"
    return "other"


def normalize(df: pd.DataFrame) -> Dict:
    if COL_NAME not in df.columns or COL_UID not in df.columns:
        raise ValueError("列名不匹配，请检查源文件格式")

    records = []
    for _, row in df.iterrows():
        name = row[COL_NAME]
        uid = row[COL_UID]
        tag = row.get(COL_TAG)
        category = classify_row(name)
        if pd.isna(uid):
            continue
        rec = {
            "name": str(name),
            "uid": str(uid),
            "tag": None if pd.isna(tag) else str(tag),
            "category": category,
        }
        records.append(rec)

    ac = {}
    sensors = []
    cabinets = []
    others = []

    for rec in records:
        if rec["category"] == "ac_setpoint":
            m = re.search(r"(\d+)#", rec["name"])
            ac_no = m.group(1) if m else rec["name"]
            ac.setdefault(ac_no, []).append(
                {
                    "param": rec["uid"],
                    "tag": rec["tag"],
                }
            )
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
    df = load_raw(SRC_EXCEL)
    mapping = normalize(df)
    write_outputs(mapping)
    print(f"完成：{OUT_JSON} 和 {OUT_CSV}")
    print(
        f"AC 台数：{len(mapping['air_conditioners'])}，传感器：{len(mapping['sensors'])}，列头柜：{len(mapping['cabinets'])}，其他：{len(mapping['others'])}"
    )


if __name__ == "__main__":
    main()
