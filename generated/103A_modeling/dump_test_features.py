# -*- coding: utf-8 -*-
"""
dump_test_features

拉取与 pipeline_template 相同流程的输入特征，输出测试集对应时刻的特征到 CSV，
便于检查特征是否恒定导致预测值相同。
"""
import argparse
from pathlib import Path

import pandas as pd

import generated_103A_modeling.pipeline_template as p


def build_ac_requests(mapping):
    ac_requests = []
    for ac_no, items in mapping.get("air_conditioners", {}).items():
        for it in items:
            param_uid = it.get("param")
            if not param_uid:
                continue
            tag = it.get("tag")
            col_name = f"ac{ac_no}_{tag}" if tag else f"ac{ac_no}_{param_uid}"
            ac_requests.append((param_uid, col_name))
    return ac_requests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", help="ISO8601，缺省取 stop 前 365 天")
    parser.add_argument("--stop", help="ISO8601，缺省为当前 UTC")
    parser.add_argument("--every", default="5m")
    parser.add_argument("--lags", type=int, default=3)
    parser.add_argument("--field", default="value")
    parser.add_argument("--measurement-template", default="{uid}")
    parser.add_argument("--client-key", default="influxdb_dc_status_data")
    parser.add_argument(
        "--output", default=Path(__file__).with_name("artifacts") / "test_features.csv"
    )
    args = parser.parse_args()

    mapping = p.load_mapping(p.MAPPING_PATH)
    sensor_uids = [r["uid"] for r in mapping.get("sensors", [])]
    ac_requests = build_ac_requests(mapping)
    if not sensor_uids or not ac_requests:
        raise RuntimeError("映射中缺少传感器或空调设定点，请检查 uid_mapping.json")

    ac_uids = [u for u, _ in ac_requests]
    ac_col_rename = {u: col for u, col in ac_requests}

    ac_df = p.fetch_timeseries(
        ac_uids,
        args.start,
        args.stop,
        args.every,
        field=args.field,
        measurement_template=args.measurement_template,
        client_key=args.client_key,
    )
    sensor_df = p.fetch_timeseries(
        sensor_uids,
        args.start,
        args.stop,
        args.every,
        field=args.field,
        measurement_template=args.measurement_template,
        client_key=args.client_key,
    )

    ac_df = p.fill_timeseries(ac_df)
    sensor_df = p.fill_timeseries(sensor_df)
    if not ac_df.empty:
        ac_df = ac_df.rename(columns=ac_col_rename)

    # 丢弃恒定特征，避免后续 dropna 误导
    ac_df = p.drop_constant_features(ac_df, "空调特征")
    if set(ac_df.columns) <= {"time"}:
        raise RuntimeError("空调特征列全部为常数或缺失，检查 measurement/field 或时间范围")

    constant_sensors = [
        c for c in sensor_df.columns
        if c != "time" and sensor_df[c].nunique(dropna=True) <= 1
    ]
    if constant_sensors:
        raise RuntimeError(f"传感器列恒定，无法训练：{constant_sensors}；请检查 Influx 配置或时间范围")

    ac_feat = p.build_feature_matrix(ac_df, lags=args.lags)
    dataset = p.align_and_join(ac_feat, sensor_df)
    if dataset.empty:
        raise RuntimeError("对齐后数据为空，可能是时间窗口或聚合粒度不匹配")

    feature_cols = [c for c in ac_feat.columns if c != "time"]
    target_cols = [c for c in sensor_df.columns if c != "time"]

    for col in feature_cols + target_cols:
        if dataset[col].notna().sum() == 0:
            raise RuntimeError(f"列 {col} 全为空，无法输出特征，请检查 Influx 配置或时间范围")

    constant_features = [c for c in feature_cols if dataset[c].nunique(dropna=True) <= 1]
    if constant_features:
        print(f"警告: 特征列恒定：{constant_features}")

    train_df, test_df = p.split_train_test(dataset, test_ratio=0.2)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    test_df[["time"] + feature_cols].to_csv(out_path, index=False, encoding="utf-8")

    print(f"输出测试集特征 {len(test_df)} 行 -> {out_path}")
    print("各特征唯一值数量（测试集）：")
    uniq = {c: test_df[c].nunique(dropna=True) for c in feature_cols}
    for k, v in uniq.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
