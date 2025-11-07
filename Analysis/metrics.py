from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

import pandas as pd

LOG_PATTERN = "server_log_*.csv"
EXPECTED_COLUMNS = {
    "msg_type",
    "device_id",
    "seq",
    "timestamp",
    "arrival_time",
    "value",
    "duplicate_flag",
    "gap_flag",
    "delayed_flag",
    "cpu_time_ms",
    "packet_size",
}


def _latest_log(paths: Iterable[Path]) -> Path:
    try:
        return max(paths, key=lambda entry: entry.stat().st_mtime)
    except ValueError as exc:  # pragma: no cover - defensive
        raise FileNotFoundError("No server_log_*.csv files found in Server/logs/") from exc


def _sequence_gap_count(frame: pd.DataFrame) -> int:
    count = 0
    for _, group in frame.groupby("device_id"):
        ordered = group.sort_values("seq")
        diffs = ordered["seq"].diff().dropna()
        count += int(diffs.clip(lower=0).sub(1).clip(lower=0).sum())
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute baseline metrics from the latest server log.")
    parser.add_argument(
        "--log",
        type=Path,
        help="Path to server_log CSV (defaults to newest under Server/logs)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional CSV path to write the metric table.",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    log_path = args.log
    if log_path is None:
        logs_dir = project_root / "Server" / "logs"
        log_path = _latest_log(logs_dir.glob(LOG_PATTERN))
    if not log_path.exists():
        raise FileNotFoundError(f"Log file {log_path} does not exist")

    frame = pd.read_csv(log_path)
    missing = EXPECTED_COLUMNS.difference(frame.columns)
    if missing:
        raise ValueError(f"CSV {log_path.name} missing columns: {sorted(missing)}")

    frame["duplicate_flag"] = pd.to_numeric(frame["duplicate_flag"], errors="coerce").fillna(0).astype(int)
    frame["gap_flag"] = pd.to_numeric(frame["gap_flag"], errors="coerce").fillna(0).astype(int)
    frame["packet_size"] = pd.to_numeric(frame["packet_size"], errors="coerce")
    frame["cpu_time_ms"] = pd.to_numeric(frame["cpu_time_ms"], errors="coerce")
    frame["seq"] = pd.to_numeric(frame["seq"], errors="coerce").astype("Int64")
    frame["device_id"] = pd.to_numeric(frame["device_id"], errors="coerce").astype("Int64")

    total = int(len(frame))
    duplicates = int(frame["duplicate_flag"].sum())
    packets_received = total - duplicates
    duplicate_rate = duplicates / total if total else 0.0
    bytes_per_report = float(frame["packet_size"].mean()) if frame["packet_size"].notna().any() else float("nan")
    gap_count = _sequence_gap_count(frame)
    cpu_ms_per_report = (
        float(frame["cpu_time_ms"].mean()) if frame["cpu_time_ms"].notna().any() else float("nan")
    )

    metrics = [
        ("bytes_per_report", bytes_per_report),
        ("packets_received", float(packets_received)),
        ("duplicate_rate", duplicate_rate),
        ("sequence_gap_count", float(gap_count)),
        ("cpu_ms_per_report", cpu_ms_per_report),
    ]

    for name, value in metrics:
        if isinstance(value, float):
            print(f"{name}: {value:.6f}")
        else:
            print(f"{name}: {value}")

    if args.output:
        output_dir = args.output.parent
        output_dir.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(metrics, columns=["metric", "value"]).to_csv(args.output, index=False)


if __name__ == "__main__":
    main()
