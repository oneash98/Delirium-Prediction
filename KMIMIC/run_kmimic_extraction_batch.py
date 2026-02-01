"""
Batch runner for `1-Data_extraction_KMIMIC.py`.

Why this exists:
- `1-Data_extraction_KMIMIC.py` runs a single KMIMIC folder per invocation
  (via env vars like KMIMIC_FOLDER).
- This script loops over multiple folders (e.g. 440-442) and invokes the
  extraction script once per folder, writing outputs into per-folder dirs.

Example:
  python "run_kmimic_extraction_batch.py" \
    --kmimic-root /path/to/KMIMIC_EMR \
    --output-root /path/to/preprocessed \
    --folders 440 441 442
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--script",
        default=str(Path(__file__).with_name("1-2_Data_extraction_KMIMIC.py")),
        help="Path to 1-Data_extraction_KMIMIC.py",
    )
    parser.add_argument(
        "--kmimic-root",
        default=os.getenv("KMIMIC_ROOT", ""),
        help="Base directory that contains KMIMIC_EMR subfolders (e.g., .../KMIMIC_EMR).",
    )
    parser.add_argument(
        "--output-root",
        default=os.getenv("OUTPUT_ROOT", ""),
        help="Base output directory; per-folder outputs go under OUTPUT_ROOT/<folder>.",
    )
    parser.add_argument(
        "--folders",
        nargs="+",
        type=str,
        help="Folder numbers to run (e.g., 440 441 442).",
    )
    parser.add_argument(
        "--range",
        nargs=2,
        type=int,
        metavar=("START", "END"),
        help="Inclusive numeric range of folders (e.g., --range 440 442).",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python executable to use for subprocess runs.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the per-folder command/env and exit without running.",
    )
    return parser.parse_args()


def folder_list(args: argparse.Namespace) -> list[str]:
    if args.folders and args.range:
        raise SystemExit("Use either --folders or --range, not both.")
    if args.folders:
        return [str(x) for x in args.folders]
    if args.range:
        start, end = args.range
        if end < start:
            raise SystemExit("--range END must be >= START.")
        return [str(x) for x in range(start, end + 1)]
    raise SystemExit("Provide either --folders or --range.")


def main() -> int:
    args = parse_args()
    folders = folder_list(args)

    script_path = Path(args.script)
    if not script_path.exists():
        raise SystemExit(f"Script not found: {script_path}")

    base_env = os.environ.copy()
    if args.kmimic_root:
        base_env["KMIMIC_ROOT"] = args.kmimic_root
    if args.output_root:
        # Keep OUTPUT_ROOT for backwards compatibility, but the extraction script
        # reads OUT_ROOT.
        base_env["OUTPUT_ROOT"] = args.output_root
        base_env["OUT_ROOT"] = args.output_root

    failures: list[str] = []
    for folder in folders:
        env = base_env.copy()
        # 1-2_Data_extraction_KMIMIC.py uses DISCHARGED_DATE to select the
        # KMIMIC_EMR subfolder (e.g. KMIMIC_ROOT/<DISCHARGED_DATE>).
        env["DISCHARGED_DATE"] = str(folder)
        # Also set KMIMIC_FOLDER for any older scripts that expect it.
        env["KMIMIC_FOLDER"] = str(folder)
        print(f"\n=== DISCHARGED_DATE={folder} (KMIMIC_FOLDER={folder}) ===", flush=True)
        try:
            cmd = [args.python, str(script_path)]
            if args.dry_run:
                print("DRY RUN:", " ".join(cmd), flush=True)
                continue
            subprocess.run(cmd, env=env, check=True)
        except subprocess.CalledProcessError as e:
            failures.append(f"{folder} (exit={e.returncode})")

    if failures:
        print("\nFailed folders:", ", ".join(failures), file=sys.stderr)
        return 1

    print("\nAll folders completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
