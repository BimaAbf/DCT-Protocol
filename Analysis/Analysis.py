#!/usr/bin/env python3
"""Console analysis for the newest server log, with corrected expectations."""

from __future__ import annotations

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
    "batch_index",
}

MSG_STARTUP = 0x01
MSG_TIME_SYNC = 0x03
MSG_KEYFRAME = 0x04
MSG_DATA_DELTA = 0x05
MSG_HEARTBEAT = 0x06
MSG_SHUTDOWN = 0x0B

MESSAGE_NAMES = {
    MSG_STARTUP: "MSG_STARTUP",
    MSG_TIME_SYNC: "MSG_TIME_SYNC",
    MSG_KEYFRAME: "MSG_KEYFRAME",
    MSG_DATA_DELTA: "MSG_DATA_DELTA",
    MSG_HEARTBEAT: "MSG_HEARTBEAT",
    MSG_SHUTDOWN: "MSG_SHUTDOWN",
}

TYPE_SHORT_NAMES = {
    MSG_STARTUP: "startup",
    MSG_TIME_SYNC: "time_sync",
    MSG_KEYFRAME: "keyframe",
    MSG_DATA_DELTA: "data_delta",
    MSG_HEARTBEAT: "heartbeat",
    MSG_SHUTDOWN: "shutdown",
}

EXPECTED_MSG_TYPES = list(MESSAGE_NAMES.keys())
DEFAULT_DELTA_THRESHOLD = 5


def _latest_log(paths: Iterable[Path]) -> Path:
    try:
        # Filter out empty files and get the latest non-empty log
        non_empty_paths = [p for p in paths if p.stat().st_size > 0]
        if not non_empty_paths:
            raise FileNotFoundError("No non-empty server_log_*.csv files found in Server/logs/")
        return max(non_empty_paths, key=lambda entry: entry.stat().st_mtime)
    except ValueError as exc:  # pragma: no cover - defensive
        raise FileNotFoundError("No server_log_*.csv files found in Server/logs/") from exc


def _load_dataset(path: Path) -> pd.DataFrame:
    # Check if file is empty before trying to parse
    if path.stat().st_size == 0:
        raise ValueError(f"CSV {path.name} is empty. No data to analyze. Run a test first.")
    
    try:
        frame = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        raise ValueError(f"CSV {path.name} is empty or has no valid data. Run a test first.")
    
    if frame.empty:
        raise ValueError(f"CSV {path.name} contains no data rows. Run a test first.")
    
    missing = EXPECTED_COLUMNS.difference(frame.columns)
    if missing:
        raise ValueError(f"CSV {path.name} missing columns: {sorted(missing)}")

    for col in ("msg_type", "device_id", "seq"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce").astype("Int64")

    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
    frame["arrival_time"] = pd.to_datetime(frame["arrival_time"], errors="coerce")

    for flag in ("duplicate_flag", "gap_flag", "delayed_flag"):
        frame[flag] = pd.to_numeric(frame[flag], errors="coerce").fillna(0).astype(int)

    frame["packet_size"] = pd.to_numeric(frame["packet_size"], errors="coerce")
    frame["cpu_time_ms"] = pd.to_numeric(frame["cpu_time_ms"], errors="coerce")
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame["batch_index"] = pd.to_numeric(frame.get("batch_index", 0), errors="coerce").fillna(0).astype(int)

    frame = frame.dropna(subset=["msg_type", "device_id", "seq", "timestamp", "arrival_time"])
    return frame.sort_values(["device_id", "seq", "batch_index", "arrival_time"]).reset_index(drop=True)


def _sequence_gap_count(frame: pd.DataFrame) -> int:
    missing = 0
    unique_rows = frame[frame["duplicate_flag"] == 0]
    for _, group in unique_rows.groupby("device_id"):
        ordered = group.sort_values("seq")
        diffs = ordered["seq"].diff().dropna()
        diffs = diffs.where(diffs > 0, 1)  # treat resets or wrap-around as fresh sequences
        missing += int((diffs - 1).clip(lower=0).sum())
    return missing


def _rate_breakdown(unique_count: int, duplicate_count: int, gap_count: int) -> dict[str, float]:
    expected = unique_count + gap_count
    if expected > 0:
        received_pct = unique_count / expected * 100.0
        loss_pct = gap_count / expected * 100.0
        duplicate_pct = duplicate_count / expected * 100.0
    else:
        received_pct = loss_pct = duplicate_pct = float("nan")
    return {
        "expected": expected,
        "received_pct": received_pct,
        "loss_pct": loss_pct,
        "duplicate_pct": duplicate_pct,
    }


def _group_summary(label_key: str, frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()

    rows: list[dict[str, float | int | str]] = []
    for label, group in frame.groupby(label_key, dropna=False):
        duplicate_count = int(group["duplicate_flag"].sum())
        unique_count = int((group["duplicate_flag"] == 0).sum())
        gap_count = _sequence_gap_count(group)
        rates = _rate_breakdown(unique_count, duplicate_count, gap_count)

        latency_ms = (group["arrival_time"] - group["timestamp"]).dt.total_seconds().dropna() * 1000.0
        cpu_series = group.loc[group["duplicate_flag"] == 0, "cpu_time_ms"].dropna()
        size_series = group.loc[group["duplicate_flag"] == 0, "packet_size"].dropna()

        rows.append({
            label_key: int(label) if label == label else "nan",
            "packets": int(group.shape[0]),
            "expected": rates["expected"],
            "received": unique_count,
            "lost": gap_count,
            "duplicates": duplicate_count,
            "received_pct": rates["received_pct"],
            "loss_pct": rates["loss_pct"],
            "duplicate_pct": rates["duplicate_pct"],
            "avg_latency_ms": float(latency_ms.mean()) if not latency_ms.empty else float("nan"),
            "avg_cpu_ms": float(cpu_series.mean()) if not cpu_series.empty else float("nan"),
            "avg_packet_size": float(size_series.mean()) if not size_series.empty else float("nan"),
        })

    return pd.DataFrame(rows).set_index(label_key).sort_index()


def _estimate_delta_threshold(group: pd.DataFrame) -> int:
    typed = group.sort_values(["seq", "batch_index"])
    min_diff = None
    last_value = None
    for _, row in typed.iterrows():
        value = row.get("value")
        if pd.isna(value):
            continue
        if row["msg_type"] == MSG_DATA_DELTA and last_value is not None:
            diff = abs(float(value) - float(last_value))
            if diff > 0:
                min_diff = diff if min_diff is None else min(min_diff, diff)
        if row["msg_type"] in {MSG_DATA_DELTA, MSG_KEYFRAME}:
            last_value = value
    if min_diff is None:
        return DEFAULT_DELTA_THRESHOLD
    estimate = int(round(min_diff)) - 1
    if estimate <= 0:
        return DEFAULT_DELTA_THRESHOLD
    return estimate


def _expected_counts_for_device(group: pd.DataFrame) -> tuple[dict[int, int], dict[str, int]]:
    if group.empty:
        return ({msg: 0 for msg in EXPECTED_MSG_TYPES}, {"total_expected": 0, "delta_threshold": DEFAULT_DELTA_THRESHOLD})

    max_seq = pd.to_numeric(group["seq"], errors="coerce").dropna()
    if max_seq.empty:
        return ({msg: 0 for msg in EXPECTED_MSG_TYPES}, {"total_expected": 0, "delta_threshold": DEFAULT_DELTA_THRESHOLD})

    # Check if a MSG_SHUTDOWN packet exists for this device
    shutdown_packets = group[group["msg_type"] == MSG_SHUTDOWN]
    if not shutdown_packets.empty:
        # Use the shutdown packet's sequence number as the definitive total expected count
        shutdown_seq = pd.to_numeric(shutdown_packets["seq"], errors="coerce").dropna()
        if not shutdown_seq.empty:
            total_expected = int(shutdown_seq.max()) + 1
        else:
            total_expected = int(max_seq.max()) + 1
            print(f"[Warning] MSG_SHUTDOWN found but seq invalid. Tail loss may be undetected.")
    else:
        # Fall back to max sequence seen, but warn about potential tail loss
        total_expected = int(max_seq.max()) + 1
        device_id = group["device_id"].iloc[0] if not group.empty else "unknown"
        print(f"[Warning] No MSG_SHUTDOWN for device {device_id}. Tail loss may be undetected.")

    expected = {msg: 0 for msg in EXPECTED_MSG_TYPES}

    expected_startup = 1 if total_expected >= 1 else 0
    expected_time_sync = 0
    if total_expected >= 2:
        expected_time_sync = 1 + ((total_expected - 1) // 100)
    expected_keyframe = 0
    if total_expected >= 3:
        multiples_of_10 = (total_expected - 1) // 10
        multiples_of_100 = (total_expected - 1) // 100
        expected_keyframe = 1 + max(multiples_of_10 - multiples_of_100, 0)

    core_budget = total_expected - (expected_startup + expected_time_sync + expected_keyframe)
    if core_budget < 0:
        core_budget = 0

    delta_threshold = _estimate_delta_threshold(group)
    if delta_threshold <= 0:
        heartbeat_prob = 1.0
    else:
        total_range = 20 * delta_threshold + 1
        heartbeat_prob = (2 * delta_threshold + 1) / total_range

    expected_heartbeat = int(round(core_budget * heartbeat_prob))
    expected_heartbeat = min(core_budget, max(expected_heartbeat, 0))
    expected_data_delta = core_budget - expected_heartbeat

    expected[MSG_STARTUP] = expected_startup
    expected[MSG_TIME_SYNC] = expected_time_sync
    expected[MSG_KEYFRAME] = expected_keyframe
    expected[MSG_HEARTBEAT] = expected_heartbeat
    expected[MSG_DATA_DELTA] = expected_data_delta

    meta = {
        "total_expected": total_expected,
        "delta_threshold": delta_threshold,
    }
    return expected, meta


def _collect_expectations(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    device_records: list[tuple[int, dict[str, int]]] = []
    expected_totals = {msg: 0 for msg in EXPECTED_MSG_TYPES}
    observed_totals = {msg: 0 for msg in EXPECTED_MSG_TYPES}

    for device_id, group in frame.groupby("device_id"):
        expected_counts, meta = _expected_counts_for_device(group)
        observed_counts = group["msg_type"].value_counts().to_dict()

        recorded_packets = int(group.shape[0])
        total_expected = meta["total_expected"]
        device_row: dict[str, int] = {
            "expected_packets": total_expected,
            "recorded_packets": recorded_packets,
            "missing_packets": total_expected - recorded_packets,
            "delta_thresh_est": meta["delta_threshold"],
        }

        for msg in EXPECTED_MSG_TYPES:
            short = TYPE_SHORT_NAMES[msg]
            exp_val = int(expected_counts.get(msg, 0))
            rec_val = int(observed_counts.get(msg, 0))
            device_row[f"exp_{short}"] = exp_val
            device_row[f"rec_{short}"] = rec_val
            device_row[f"miss_{short}"] = exp_val - rec_val
            expected_totals[msg] += exp_val
            observed_totals[msg] += rec_val

        device_records.append((device_id, device_row))

    if device_records:
        device_df = pd.DataFrame.from_dict({device: row for device, row in device_records}, orient="index").sort_index()
    else:
        device_df = pd.DataFrame()

    msg_rows = []
    for msg in EXPECTED_MSG_TYPES:
        exp_total = expected_totals[msg]
        rec_total = observed_totals.get(msg, 0)
        missing = exp_total - rec_total
        missing_pct = (missing / exp_total * 100.0) if exp_total else float("nan")
        msg_rows.append({
            "msg_name": MESSAGE_NAMES[msg],
            "expected": exp_total,
            "recorded": rec_total,
            "missing": missing,
            "missing_pct": missing_pct,
        })

    msg_df = pd.DataFrame(msg_rows).set_index("msg_name") if msg_rows else pd.DataFrame()
    return msg_df, device_df


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    logs_dir = project_root / "Server" / "logs"
    latest_log = _latest_log(logs_dir.glob(LOG_PATTERN))

    frame = _load_dataset(latest_log)

    # Calculate metrics using shutdown-based expected counts
    total_expected = 0
    total_unique_received = 0
    total_duplicates = 0
    has_shutdown_warning = False
    
    for device_id, group in frame.groupby("device_id"):
        # Check for MSG_SHUTDOWN to get true expected count
        shutdown_packets = group[group["msg_type"] == MSG_SHUTDOWN]
        if not shutdown_packets.empty:
            shutdown_seq = pd.to_numeric(shutdown_packets["seq"], errors="coerce").dropna()
            if not shutdown_seq.empty:
                device_expected = int(shutdown_seq.max()) + 1
            else:
                device_expected = int(group["seq"].max()) + 1
                has_shutdown_warning = True
        else:
            device_expected = int(group["seq"].max()) + 1
            has_shutdown_warning = True
        
        total_expected += device_expected
        total_unique_received += int((group["duplicate_flag"] == 0).sum())
        total_duplicates += int(group["duplicate_flag"].sum())
    
    if has_shutdown_warning:
        print("WARNING: No shutdown packet received for one or more devices. Tail loss detection unreliable.")
    
    # Calculate rates using corrected formulas
    total_received = total_unique_received + total_duplicates  # Total packets in log
    total_lost = total_expected - total_unique_received
    
    if total_expected > 0:
        loss_pct = (total_lost / total_expected) * 100.0
        received_pct = (total_unique_received / total_expected) * 100.0
    else:
        loss_pct = received_pct = float("nan")
    
    # Duplicate % = Total Duplicates / Total Received (as per requirement)
    if total_received > 0:
        duplicate_pct = (total_duplicates / total_received) * 100.0
    else:
        duplicate_pct = float("nan")

    non_duplicate = frame[frame["duplicate_flag"] == 0]
    bytes_series = non_duplicate["packet_size"].dropna()
    cpu_series = non_duplicate["cpu_time_ms"].dropna()

    metrics_rows = [
        ("log_file", latest_log.relative_to(project_root).as_posix(), ""),
        ("packets_expected", float(total_expected), "from shutdown seq or max seq"),
        ("packets_recorded", float(frame.shape[0]), "rows in log (includes duplicates)"),
        ("packets_received", float(total_unique_received), f"{received_pct:.2f}% of expected"),
        ("packets_lost", float(total_lost), f"{loss_pct:.2f}% of expected"),
        ("duplicates", float(total_duplicates), f"{duplicate_pct:.2f}% of received"),
        ("loss_rate", loss_pct / 100.0 if total_expected > 0 else float("nan"), "fraction of expected"),
        ("duplicate_rate", duplicate_pct / 100.0 if total_received > 0 else float("nan"), "fraction of received"),
        ("cpu_ms_per_report", float(cpu_series.mean()) if not cpu_series.empty else float("nan"), "non-duplicates"),
        ("bytes_per_report", float(bytes_series.mean()) if not bytes_series.empty else float("nan"), "non-duplicates"),
    ]

    metrics_df = pd.DataFrame(metrics_rows, columns=["metric", "value", "note"])

    print("\nMetric overview:\n")
    print(metrics_df.to_string(index=False, justify="left"))

    device_table = _group_summary("device_id", frame)
    if not device_table.empty:
        print("\nPer-device analysis:\n")
        print(device_table.to_string(float_format=lambda x: f"{x:.2f}" if pd.notna(x) else "nan"))
    else:
        print("\nPer-device analysis:\nNo device records available.")

    msg_expectations, _ = _collect_expectations(frame)

    if not msg_expectations.empty:
        print("\nExpected vs recorded by message type:\n")
        print(msg_expectations.to_string(float_format=lambda x: f"{x:.2f}" if pd.notna(x) else "nan"))

    summary_rows = [{
        "packets": int(frame.shape[0]),
        "expected": total_expected,
        "received": float(total_unique_received),
        "received_pct": received_pct,
        "lost": float(total_lost),
        "loss_pct": loss_pct,
        "duplicates": float(total_duplicates),
        "duplicate_pct": duplicate_pct,
        "devices": int(frame["device_id"].nunique()),
        "msg_types": int(frame["msg_type"].nunique()),
    }]
    summary_df = pd.DataFrame(summary_rows)
    print("\nSummary:\n")
    print(summary_df.to_string(index=False, float_format=lambda x: f"{x:.2f}"))

    export_rows = []
    metrics_export = metrics_df.copy()
    metrics_export.insert(0, "section", "metrics")
    export_rows.append(metrics_export)

    if not device_table.empty:
        device_export = device_table.reset_index().rename(columns={"index": "device_id"})
        device_export.insert(0, "section", "per_device")
        export_rows.append(device_export)

    if not msg_expectations.empty:
        msg_export = msg_expectations.reset_index().rename(columns={"index": "msg_name"})
        msg_export.insert(0, "section", "msg_expectations")
        export_rows.append(msg_export)

    summary_export = summary_df.copy()
    summary_export.insert(0, "section", "summary")
    export_rows.append(summary_export)

    combined = pd.concat(export_rows, ignore_index=True, sort=False)
    export_dir = project_root / "Analysis"
    export_dir.mkdir(parents=True, exist_ok=True)
    log_stem = latest_log.stem.replace("server_log_", "")
    output_path = export_dir / f"analysis_output_{log_stem}.csv"
    combined.to_csv(output_path.as_posix(), index=False)
    print(f"\nAnalysis exported to {output_path.relative_to(project_root)}")


if __name__ == "__main__":
    main()
