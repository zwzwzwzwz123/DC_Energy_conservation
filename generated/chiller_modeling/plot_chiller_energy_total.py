import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from generated.chiller_modeling.train_chiller_model import (  # noqa: E402
    MAPPING_PATH,
    ensure_datetime,
    fetch_timeseries,
    fill_timeseries,
    is_chiller_energy_name,
    load_mapping,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2025-10-30T00:00:00Z")
    parser.add_argument("--stop", default="2025-12-12T23:59:59Z")
    parser.add_argument("--every", default="5m")
    parser.add_argument("--field", default="value")
    parser.add_argument("--measurement-template", default="{uid}")
    parser.add_argument("--client-key", default="influxdb_dc_status_data")
    parser.add_argument("--mapping", default=str(MAPPING_PATH))
    parser.add_argument("--out", default="generated/chiller_modeling/artifacts_chiller/plots")
    args = parser.parse_args()

    mapping = load_mapping(Path(args.mapping))
    output_recs = mapping.get("outputs", [])
    chiller_uids = [r["uid"] for r in output_recs if is_chiller_energy_name(r.get("name", ""))]
    if not chiller_uids:
        raise RuntimeError("未在 mapping 中找到冷水机组能耗输出")

    df = fetch_timeseries(
        chiller_uids,
        args.start,
        args.stop,
        args.every,
        field=args.field,
        measurement_template=args.measurement_template,
        client_key=args.client_key,
        diff_uids=set(chiller_uids),
    )
    df = ensure_datetime(fill_timeseries(df))
    if df.empty:
        raise RuntimeError("拉取数据为空")

    total = df[chiller_uids].sum(axis=1, min_count=1)
    plot_df = pd.DataFrame({"time": df["time"], "chiller_energy_total": total})

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:
        raise RuntimeError("缺少 matplotlib，无法绘图") from exc

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(plot_df["time"], plot_df["chiller_energy_total"], label="chiller_energy_total")
    ax.set_title("chiller_energy_total 冷水机组总能耗")
    ax.set_xlabel("time")
    ax.set_ylabel("value")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    out_path = out_dir / "chiller_energy_total_20251030_20251212.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    plot_df.to_csv(out_dir / "chiller_energy_total_20251030_20251212.csv", index=False, encoding="utf-8")
    print(f"输出: {out_path}")


if __name__ == "__main__":
    main()
