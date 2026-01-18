"""
Dump raw timeseries for chiller inputs/outputs to CSV (long format: time, uid, value).
- Reads uid_mapping_chiller.json
- InfluxDB 1.8 query without aggregation (ordered by time)
"""
import argparse
import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List

import pandas as pd
from influxdb import InfluxDBClient

THIS_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = THIS_DIR / "train_chiller_model.py"
MAPPING_PATH = THIS_DIR / "uid_mapping_chiller.json"


def load_template_module():
    spec = importlib.util.spec_from_file_location("train_chiller_model", TEMPLATE_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 {TEMPLATE_PATH}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["train_chiller_model"] = mod
    spec.loader.exec_module(mod)
    return mod


def build_uid_meta(mapping):
    """返回 {uid: name}，便于导出时带上中文标签。"""
    meta = {}
    for rec in mapping.get("inputs", []):
        meta[rec["uid"]] = rec.get("name")
    for rec in mapping.get("outputs", []):
        meta[rec["uid"]] = rec.get("name")
    return meta


def fetch_raw(uid: str, start: str, stop: str, field: str, measurement_template: str, client: InfluxDBClient) -> pd.DataFrame:
    measurement = measurement_template.format(uid=uid)
    q = (
        f'SELECT "{field}" AS value '
        f'FROM "{measurement}" '
        f"WHERE time >= '{start}' AND time <= '{stop}' "
        f"ORDER BY time ASC"
    )
    result = client.query(q)
    points = list(result.get_points())
    if not points:
        return pd.DataFrame(columns=["time", "uid", "value"])
    df = pd.DataFrame(points)
    df["uid"] = uid
    return df[["time", "uid", "value"]]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", help="ISO8601，缺省取 stop 前 365 天")
    parser.add_argument("--stop", help="ISO8601，缺省为当前 UTC")
    parser.add_argument("--field", default="value", help="Influx 数值字段名，默认 value")
    parser.add_argument("--measurement-template", default="{uid}", help="measurement 模板，默认与 uid 同名，可用 {uid} 占位")
    parser.add_argument("--client-key", default="influxdb_dc_status_data", help="configs/utils_config.yaml 中的客户端键名")
    parser.add_argument("--output", default=THIS_DIR / "artifacts_chiller" / "raw_timeseries.csv")
    args = parser.parse_args()

    now_utc = datetime.now(timezone.utc).replace(microsecond=0)
    stop = args.stop or now_utc.isoformat().replace("+00:00", "Z")
    start = args.start or (now_utc - timedelta(days=365)).isoformat().replace("+00:00", "Z")

    mod = load_template_module()
    mapping = mod.load_mapping(MAPPING_PATH)
    uid_meta = build_uid_meta(mapping)
    all_uids = sorted(uid_meta.keys())
    if not all_uids:
        raise RuntimeError("映射中没有可用的 UID，请检查 uid_mapping_chiller.json")

    creds = mod.load_influx_credentials(args.client_key)
    client = InfluxDBClient(
        host=creds["host"],
        port=creds["port"],
        username=creds["username"],
        password=creds["password"],
        database=creds["database"],
        timeout=10,
    )

    dfs = []
    for uid in all_uids:
        df = fetch_raw(uid, start, stop, args.field, args.measurement_template, client)
        if df.empty:
            print(f"警告: {uid} 在时间窗内无数据")
        else:
            df["name"] = uid_meta.get(uid)
        dfs.append(df)
    client.close()

    if not dfs:
        raise RuntimeError("无数据可写出")

    merged = pd.concat(dfs, ignore_index=True)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(out_path, index=False, encoding="utf-8")
    print(f"完成，写出 {len(merged)} 行 -> {out_path}")


if __name__ == "__main__":
    main()
