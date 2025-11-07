#!/usr/bin/env python3
"""Console-only analysis for server CSV logs."""

from __future__ import annotations

from pathlib import Path

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
def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    logs_path = project_root / "Server" / "logs"
    try:
        latest_log = max(logs_path.glob(LOG_PATTERN), key=lambda entry: entry.stat().st_mtime)
    except ValueError as exc:
        raise FileNotFoundError("No server_log_*.csv files found in Server/logs/") from exc

    frame = pd.read_csv(latest_log)
    missing_columns = EXPECTED_COLUMNS.difference(frame.columns)
    if missing_columns:
        raise ValueError(f"CSV {latest_log.name} missing columns: {sorted(missing_columns)}")

    for column in ("msg_type", "device_id", "seq"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").astype("Int64")

    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame["cpu_time_ms"] = pd.to_numeric(frame["cpu_time_ms"], errors="coerce")
    frame["packet_size"] = pd.to_numeric(frame["packet_size"], errors="coerce")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
    frame["arrival_time"] = pd.to_datetime(frame["arrival_time"], errors="coerce")

    for flag_column in ("duplicate_flag", "gap_flag", "delayed_flag"):
        frame[flag_column] = pd.to_numeric(frame[flag_column], errors="coerce").fillna(0).astype(int)

    frame = frame.dropna(subset=["msg_type", "device_id", "seq", "timestamp", "arrival_time"])
    frame = frame.sort_values(["device_id", "arrival_time", "seq"]).reset_index(drop=True)

    total_packets = int(len(frame))
    duplicate_packets = int(frame["duplicate_flag"].sum())
    gap_packets = int(frame["gap_flag"].sum())
    delayed_packets = int(frame["delayed_flag"].sum())
    received_packets = total_packets - duplicate_packets
    expected_packets = total_packets + gap_packets
    expected_packets = expected_packets if expected_packets else total_packets or 1

    received_pct = received_packets / expected_packets * 100.0
    duplicate_pct = duplicate_packets / expected_packets * 100.0
    loss_pct = gap_packets / expected_packets * 100.0

    metrics_rows = [
        ("log_file", latest_log.relative_to(project_root).as_posix(), ""),
        ("total_packets", total_packets, ""),
        ("received_packets", received_packets, f"{received_pct:.2f}% of expected"),
        ("duplicate_packets", duplicate_packets, f"{duplicate_pct:.2f}% of expected"),
        ("gap_flagged_packets", gap_packets, f"{loss_pct:.2f}% loss estimate"),
        ("delayed_packets", delayed_packets, ""),
        ("unique_devices", int(frame["device_id"].nunique()), ""),
        ("unique_msg_types", int(frame["msg_type"].nunique()), ""),
    ]

    if frame["packet_size"].notna().any():
        metrics_rows.append(("total_bytes", float(frame["packet_size"].sum()), ""))
        metrics_rows.append(("avg_packet_size", float(frame["packet_size"].mean()), ""))

    if frame["cpu_time_ms"].notna().any():
        metrics_rows.append(("avg_cpu_time_ms", float(frame["cpu_time_ms"].mean()), ""))
        metrics_rows.append(("median_cpu_time_ms", float(frame["cpu_time_ms"].median()), ""))

    print("\nMetric overview:\n")
    print(pd.DataFrame(metrics_rows, columns=["metric", "value", "note"]).to_string(index=False, justify="left"))

    frame["latency_s"] = (frame["arrival_time"] - frame["timestamp"]).dt.total_seconds()
    per_device_rows = []
    for device_id, group in frame.groupby("device_id", dropna=False):
        packets = int(group.shape[0])
        duplicates = int(group["duplicate_flag"].sum())
        gaps = int(group["gap_flag"].sum())
        received = packets - duplicates
        expected = packets + gaps if (packets + gaps) else packets or 1
        loss_rate = gaps / expected * 100.0
        recv_rate = received / expected * 100.0
        duplicate_rate = duplicates / expected * 100.0

        average_latency_ms = (group["latency_s"].mean() * 1000.0) if group["latency_s"].notna().any() else float("nan")
        average_cpu_ms = group["cpu_time_ms"].mean() if group["cpu_time_ms"].notna().any() else float("nan")
        average_packet_size = group["packet_size"].mean() if group["packet_size"].notna().any() else float("nan")

        per_device_rows.append({
            "device_id": int(device_id) if device_id == device_id else "nan",
            "packets": packets,
            "received": received,
            "received_pct": recv_rate,
            "lost": gaps,
            "loss_pct": loss_rate,
            "duplicates": duplicates,
            "duplicate_pct": duplicate_rate,
            "avg_latency_ms": average_latency_ms,
            "avg_cpu_ms": average_cpu_ms,
            "avg_packet_size": average_packet_size,
        })

    if per_device_rows:
        device_frame = pd.DataFrame(per_device_rows).set_index("device_id").sort_index()
        print("\nPer-device analysis:\n")
        print(device_frame.to_string(float_format=lambda value: f"{value:.2f}" if pd.notna(value) else "nan"))
    else:
        print("\nPer-device analysis:\nNo device records available.")

    per_msg_rows = []
    for msg_type, group in frame.groupby("msg_type", dropna=False):
        packets = int(group.shape[0])
        duplicates = int(group["duplicate_flag"].sum())
        gaps = int(group["gap_flag"].sum())
        received = packets - duplicates
        expected = packets + gaps if (packets + gaps) else packets or 1
        loss_rate = gaps / expected * 100.0
        recv_rate = received / expected * 100.0
        duplicate_rate = duplicates / expected * 100.0

        average_latency_ms = (group["latency_s"].mean() * 1000.0) if group["latency_s"].notna().any() else float("nan")
        average_cpu_ms = group["cpu_time_ms"].mean() if group["cpu_time_ms"].notna().any() else float("nan")
        average_packet_size = group["packet_size"].mean() if group["packet_size"].notna().any() else float("nan")

        per_msg_rows.append({
            "msg_type": int(msg_type) if msg_type == msg_type else "nan",
            "packets": packets,
            "received": received,
            "received_pct": recv_rate,
            "lost": gaps,
            "loss_pct": loss_rate,
            "duplicates": duplicates,
            "duplicate_pct": duplicate_rate,
            "avg_latency_ms": average_latency_ms,
            "avg_cpu_ms": average_cpu_ms,
            "avg_packet_size": average_packet_size,
        })

    if per_msg_rows:
        msg_frame = pd.DataFrame(per_msg_rows).set_index("msg_type").sort_index()
        print("\nPer message-type analysis:\n")
        print(msg_frame.to_string(float_format=lambda value: f"{value:.2f}" if pd.notna(value) else "nan"))

    summary_rows = [{
        "packets": total_packets,
        "received": received_packets,
        "received_pct": received_pct,
        "lost": gap_packets,
        "loss_pct": loss_pct,
        "devices": int(frame["device_id"].nunique()),
        "msg_types": int(frame["msg_type"].nunique()),
    }]
    print("\nSummary:\n")
    print(pd.DataFrame(summary_rows).to_string(index=False, float_format=lambda value: f"{value:.2f}"))


if __name__ == "__main__":
    main()


@dataclass
class MetricEntry:
    value: Optional[float]
    note: Optional[str] = None


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _logs_dir() -> Path:
    return _project_root() / "Server" / "logs"


def _latest_log_file(candidates: Iterable[Path]) -> Path:
    try:
        return max(candidates, key=lambda path: path.stat().st_mtime)
    except ValueError:
        raise FileNotFoundError("No server_log_*.csv files found in Server/logs/")


def _load_dataset(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = EXPECTED_COLUMNS.difference(df.columns)
    if missing:
        raise ValueError(f"CSV {path.name} missing columns: {sorted(missing)}")

    for col in ("msg_type", "device_id", "seq"):
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df["cpu_time_ms"] = pd.to_numeric(df["cpu_time_ms"], errors="coerce")
    df["packet_size"] = pd.to_numeric(df["packet_size"], errors="coerce")
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["arrival_time"] = pd.to_datetime(df["arrival_time"], errors="coerce")

    for flag in ("duplicate_flag", "gap_flag", "delayed_flag"):
        df[flag] = pd.to_numeric(df[flag], errors="coerce").fillna(0).astype(int)

    df = df.dropna(subset=["msg_type", "device_id", "seq", "timestamp", "arrival_time"])
    return df.sort_values(["device_id", "arrival_time", "seq"]).reset_index(drop=True)


def _latency_series(df: pd.DataFrame) -> pd.Series:
    return (df["arrival_time"] - df["timestamp"]).dt.total_seconds().dropna()


def _sequence_gap_count(df: pd.DataFrame) -> int:
    window = df[["device_id", "seq"]].copy()
    window["prev_seq"] = window.groupby("device_id")["seq"].shift(1)
    window["delta"] = window["seq"] - window["prev_seq"]
    window.loc[window["delta"] <= 0, "delta"] = 1
    return int((window["delta"] - 1).clip(lower=0).sum())


def _summarise(df: pd.DataFrame) -> Tuple[Dict[str, MetricEntry], List[str]]:
    metrics: Dict[str, MetricEntry] = {}
    notes: List[str] = []

    total = int(len(df))
    dup = int(df["duplicate_flag"].sum())
    gap = int(df["gap_flag"].sum())
    delayed = int(df["delayed_flag"].sum())

    metrics["total_packets"] = MetricEntry(float(total))
    metrics["unique_devices"] = MetricEntry(float(df["device_id"].nunique()))
    metrics["unique_msg_types"] = MetricEntry(float(df["msg_type"].nunique()))
    metrics["duplicates"] = MetricEntry(float(dup))
    metrics["gap_flags"] = MetricEntry(float(gap))
    metrics["delayed_flags"] = MetricEntry(float(delayed))
    metrics["duplicate_rate"] = MetricEntry(dup / total if total else math.nan)
    metrics["sequence_gap_estimate"] = MetricEntry(float(_sequence_gap_count(df)))

    if df["packet_size"].notna().any():
        metrics["total_bytes"] = MetricEntry(float(df["packet_size"].sum()))
        metrics["avg_packet_size"] = MetricEntry(float(df["packet_size"].mean()))
        metrics["p95_packet_size"] = MetricEntry(float(df["packet_size"].quantile(0.95)))

    if df["cpu_time_ms"].notna().any():
        metrics["avg_cpu_time_ms"] = MetricEntry(float(df["cpu_time_ms"].mean()))
        metrics["median_cpu_time_ms"] = MetricEntry(float(df["cpu_time_ms"].median()))
        metrics["p95_cpu_time_ms"] = MetricEntry(float(df["cpu_time_ms"].quantile(0.95)))

    latency = _latency_series(df)
    if latency.empty:
        notes.append("Latency could not be derived; timestamp or arrival_time invalid")
    else:
        metrics["median_latency_ms"] = MetricEntry(latency.median() * 1000.0)
        metrics["p95_latency_ms"] = MetricEntry(latency.quantile(0.95) * 1000.0)

    return metrics, notes


def _per_device_table(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    per_device = df.copy()
    per_device["latency_s"] = (per_device["arrival_time"] - per_device["timestamp"]).dt.total_seconds()
    group = per_device.groupby("device_id", dropna=False)

    table = pd.DataFrame({
        "packets": group.size(),
        "duplicates": group["duplicate_flag"].sum(),
        "duplicate_rate": group["duplicate_flag"].mean(),
        "gap_flags": group["gap_flag"].sum(),
        "delayed_flags": group["delayed_flag"].sum(),
        "median_latency_ms": group["latency_s"].median() * 1000.0,
        "p95_latency_ms": group["latency_s"].quantile(0.95) * 1000.0,
    })

    if per_device["value"].notna().any():
        table["value_mean"] = group["value"].mean()
        table["value_min"] = group["value"].min()
        table["value_max"] = group["value"].max()

    if per_device["cpu_time_ms"].notna().any():
        table["avg_cpu_ms"] = group["cpu_time_ms"].mean()
        table["p95_cpu_ms"] = group["cpu_time_ms"].quantile(0.95)

    if per_device["packet_size"].notna().any():
        table["avg_pkt_size"] = group["packet_size"].mean()
        table["total_bytes"] = group["packet_size"].sum()

    return table.sort_index()


def _per_msg_type_table(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    series_latency = (df["arrival_time"] - df["timestamp"]).dt.total_seconds()
    msg_group = df.copy()
    msg_group["latency_s"] = series_latency
    group = msg_group.groupby("msg_type", dropna=False)

    table = pd.DataFrame({
        "packets": group.size(),
        "duplicate_rate": group["duplicate_flag"].mean(),
        "median_latency_ms": group["latency_s"].median() * 1000.0,
    })

    if msg_group["cpu_time_ms"].notna().any():
        table["avg_cpu_ms"] = group["cpu_time_ms"].mean()

    if msg_group["packet_size"].notna().any():
        table["avg_pkt_size"] = group["packet_size"].mean()

    return table.sort_index()


def _print_metrics(metrics: Dict[str, MetricEntry]) -> None:
    frame = pd.DataFrame(
        [(key, entry.value, entry.note or "") for key, entry in metrics.items()],
        columns=["metric", "value", "note"],
    ).sort_values("metric")
    print("\nMetric overview:\n")
    print(frame.to_string(index=False, justify="left"))


def main() -> None:
    root = _project_root()
    logs_dir = _logs_dir()
    latest = _latest_log_file(logs_dir.glob(LOG_PATTERN))
    print(f"Using log file: {latest.relative_to(root)}")

    df = _load_dataset(latest)
    metrics, notes = _summarise(df)
    _print_metrics(metrics)
    if notes:
        print("\nNotes:")
        for item in notes:
            print(f"  - {item}")

    per_device = _per_device_table(df)
    if not per_device.empty:
        print("\nPer-device analysis:\n")
        print(
            per_device.to_string(
                float_format=lambda x: f"{x:.2f}" if pd.notna(x) else "nan"
            )
        )
    else:
        print("\nPer-device analysis:\nNo device records available.")

    per_msg_type = _per_msg_type_table(df)
    if not per_msg_type.empty:
        print("\nPer message-type analysis:\n")
        print(
            per_msg_type.to_string(
                float_format=lambda x: f"{x:.2f}" if pd.notna(x) else "nan"
            )
        )

    summary = {
        "packets": int(len(df)),
        "devices": int(df["device_id"].nunique()),
        "msg_types": int(df["msg_type"].nunique()),
    }
    print("\nSummary:\n")
    print(pd.DataFrame([summary]).to_string(index=False, justify="left"))


if __name__ == "__main__":
    main()
