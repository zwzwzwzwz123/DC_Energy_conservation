"""
Plot raw timeseries CSV into per-uid line charts.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager


SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
CHINESE_FONT_CANDIDATES = [
    "Microsoft YaHei",
    "SimHei",
    "PingFang SC",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "WenQuanYi Micro Hei",
    "STHeiti",
    "Arial Unicode MS",
]


def safe_filename(text: str) -> str:
    text = text.strip()
    if not text:
        return "uid"
    return SAFE_NAME_RE.sub("_", text)


def configure_chinese_font() -> str | None:
    available = {f.name for f in font_manager.fontManager.ttflist}
    for name in CHINESE_FONT_CANDIDATES:
        if name in available:
            plt.rcParams["font.sans-serif"] = [name]
            plt.rcParams["axes.unicode_minus"] = False
            return name
    plt.rcParams["axes.unicode_minus"] = False
    return None


def load_timeseries(input_path: Path) -> pd.DataFrame:
    df = pd.read_csv(input_path)
    required = {"time", "uid", "value"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)} in {input_path}")

    df = df.copy()
    df["uid"] = df["uid"].astype(str)
    df["time"] = pd.to_datetime(df["time"], errors="coerce", utc=True)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["time", "uid", "value"])
    df = df.sort_values(["uid", "time"])
    return df


def plot_uid(group: pd.DataFrame, output_path: Path, title: str, dpi: int) -> None:
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(group["time"], group["value"], linewidth=1)
    ax.set_title(title)
    ax.set_xlabel("time")
    ax.set_ylabel("value")
    ax.grid(True, linestyle="--", alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)


def build_title(uid: str, group: pd.DataFrame) -> str:
    if "name" not in group.columns:
        return uid
    names = group["name"].dropna().astype(str).unique()
    if len(names) == 0:
        return uid
    return f"{uid} - {names[0]}"


def plot_from_csv(
    input_path: Path,
    output_dir: Path | None = None,
    image_format: str = "png",
    dpi: int = 150,
    max_points: int = 0,
) -> Path:
    configure_chinese_font()
    output_dir = output_dir or input_path.parent / "raw_plots"
    output_dir.mkdir(parents=True, exist_ok=True)

    df = load_timeseries(input_path)
    uid_count = df["uid"].nunique()
    if uid_count == 0:
        raise RuntimeError(f"No uid data found in {input_path}")

    for uid, group in df.groupby("uid", sort=False):
        if max_points and len(group) > max_points:
            step = max(1, len(group) // max_points)
            group = group.iloc[::step].copy()
        title = build_title(uid, group)
        file_name = f"{safe_filename(uid)}.{image_format}"
        output_path = output_dir / file_name
        plot_uid(group, output_path, title, dpi)

    print(f"Saved {uid_count} plot(s) to {output_dir}")
    return output_dir


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default=Path(__file__).with_name("artifacts_chiller") / "raw_timeseries.csv",
        help="Raw timeseries CSV path.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory to store per-uid plots. Defaults to input directory / raw_plots.",
    )
    parser.add_argument("--format", default="png", help="Image format (png, jpg, svg).")
    parser.add_argument("--dpi", type=int, default=150, help="Image DPI.")
    parser.add_argument(
        "--max-points",
        type=int,
        default=0,
        help="Optional downsample per uid to at most N points (0 = no limit).",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output_dir) if args.output_dir else None
    plot_from_csv(
        input_path,
        output_dir=output_dir,
        image_format=args.format,
        dpi=args.dpi,
        max_points=args.max_points,
    )


if __name__ == "__main__":
    main()
