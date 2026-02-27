"""
Build UID mapping for the chiller system.

- Reads sheet1 (输入) as model inputs.
- Reads sheet2 (输出) as model targets.
- Exports mapping to JSON/CSV under generated/chiller_modeling/.
"""
from pathlib import Path
import json
from typing import Dict, List

import pandas as pd

SRC_EXCEL = Path("uid") / "\u51b7\u6c34\u673a\u7ec4BA\u7cfb\u7edf\u4fe1\u606f.xlsx"
SHEET_INPUT = "\u8f93\u5165"
SHEET_OUTPUT = "\u8f93\u51fa"

OUT_JSON = Path(__file__).with_name("uid_mapping_chiller.json")
OUT_CSV = Path(__file__).with_name("uid_mapping_chiller.csv")


def load_inputs(xls: pd.ExcelFile) -> List[Dict]:
    df = xls.parse(SHEET_INPUT)
    required = {"\u6d4b\u70b9\u540d\u79f0", "uid"}
    if not required.issubset(df.columns):
        raise KeyError(f"输入表缺少列: 需要 {required}, 实际 {set(df.columns)}")
    records = []
    for _, row in df.iterrows():
        name = row.get("\u6d4b\u70b9\u540d\u79f0")
        uid = row.get("uid")
        if pd.isna(name) or pd.isna(uid):
            continue
        records.append({"name": str(name), "uid": str(uid), "category": "input"})
    return records


def load_outputs(xls: pd.ExcelFile) -> List[Dict]:
    # 输出表没有表头，两列依次为 name / uid
    df = xls.parse(SHEET_OUTPUT, header=None, names=["name", "uid"])
    records = []
    for _, row in df.iterrows():
        name = row.get("name")
        uid = row.get("uid")
        if pd.isna(name) or pd.isna(uid):
            continue
        records.append({"name": str(name), "uid": str(uid), "category": "output"})
    return records


def validate_uniqueness(records: List[Dict]) -> None:
    seen = {}
    dups = []
    for rec in records:
        uid = rec["uid"]
        if uid in seen:
            dups.append(uid)
        else:
            seen[uid] = rec["name"]
    if dups:
        raise ValueError(f"UID 重复: {sorted(set(dups))}")


def write_outputs(mapping: Dict) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame(mapping["raw_records"]).to_csv(OUT_CSV, index=False, encoding="utf-8")


def main():
    if not SRC_EXCEL.exists():
        raise FileNotFoundError(f"未找到源文件: {SRC_EXCEL}")
    xls = pd.ExcelFile(SRC_EXCEL)
    inputs = load_inputs(xls)
    outputs = load_outputs(xls)
    all_records = inputs + outputs
    if not inputs:
        raise RuntimeError("输入测点为空，请检查 Excel 的输入 sheet")
    if not outputs:
        raise RuntimeError("输出测点为空，请检查 Excel 的输出 sheet")
    validate_uniqueness(all_records)
    mapping = {"inputs": inputs, "outputs": outputs, "raw_records": all_records}
    write_outputs(mapping)
    print(f"完成: 输入 {len(inputs)} 个, 输出 {len(outputs)} 个 -> {OUT_JSON} / {OUT_CSV}")


if __name__ == "__main__":
    main()
