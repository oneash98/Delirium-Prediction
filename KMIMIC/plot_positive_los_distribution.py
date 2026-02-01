import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def _guess_los_column(df: pd.DataFrame, los_col: str | None) -> str:
    if los_col:
        if los_col not in df.columns:
            raise ValueError(f"--los-col '{los_col}' not found. Available: {list(df.columns)}")
        return los_col

    candidates = [
        "los",
        "LOS",
        "icu_los",
        "icu_los_hours",
        "los_hours",
        "los_days",
        "lengthofstay",
        "Length of stay",
        "unitdischargeoffset",  # eICU-style (minutes)
        "hospital_los",
        "hospital_los_days",
        "hospital_los_hours",
    ]

    for c in candidates:
        if c in df.columns:
            return c

    raise ValueError(
        "Could not infer LOS column. Pass it explicitly with --los-col. "
        f"Available columns: {list(df.columns)}"
    )


def _to_hours(series: pd.Series, unit: str) -> np.ndarray:
    vals = pd.to_numeric(series, errors="coerce").dropna().to_numpy(dtype=float)
    if unit == "hours":
        return vals
    if unit == "days":
        return vals * 24.0
    if unit == "minutes":
        return vals / 60.0
    raise ValueError(f"Unknown unit: {unit} (expected hours|days|minutes)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plot LOS distribution for positive patients.",
    )
    parser.add_argument(
        "--pos-csv",
        type=Path,
        required=True,
        help="Path to positive CSV (e.g., pos_mimic_imputed_24los.csv).",
    )
    parser.add_argument(
        "--los-col",
        type=str,
        default=None,
        help="LOS column name. If omitted, script will try to infer it.",
    )
    parser.add_argument(
        "--unit",
        type=str,
        choices=["hours", "days", "minutes"],
        default="hours",
        help="Unit of LOS column (used for x-axis + conversion).",
    )
    parser.add_argument(
        "--bins",
        type=int,
        default=50,
        help="Histogram bin count.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("positive_los_distribution.png"),
        help="Output image path.",
    )
    args = parser.parse_args()

    df = pd.read_csv(args.pos_csv)
    los_col = _guess_los_column(df, args.los_col)
    los_hours = _to_hours(df[los_col], unit=args.unit)

    if los_hours.size == 0:
        raise ValueError(f"No numeric LOS values found in column '{los_col}'.")

    p5, p50, p95 = np.percentile(los_hours, [5, 50, 95])
    print(f"Positive rows: {len(df)}")
    print(f"LOS column: {los_col} (unit={args.unit} -> plotted as hours)")
    print(f"LOS hours: mean={los_hours.mean():.2f}, std={los_hours.std():.2f}")
    print(f"LOS hours: p5={p5:.2f}, p50={p50:.2f}, p95={p95:.2f}")

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    axes[0].hist(los_hours, bins=args.bins, color="#4C78A8", alpha=0.85)
    axes[0].set_title("Positive LOS (Histogram)")
    axes[0].set_xlabel("LOS (hours)")
    axes[0].set_ylabel("Count")

    axes[1].boxplot(los_hours, vert=True, showfliers=True)
    axes[1].set_title("Positive LOS (Boxplot)")
    axes[1].set_ylabel("LOS (hours)")

    fig.suptitle("LOS Distribution (Positive)", fontsize=14)
    fig.tight_layout()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=200, bbox_inches="tight")
    print(f"Saved: {args.out}")


if __name__ == "__main__":
    main()

