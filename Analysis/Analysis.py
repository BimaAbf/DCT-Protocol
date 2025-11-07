"""Utility script for exploring server telemetry logs.

The script locates the most recent server CSV log, computes key packet
health metrics, and produces high level visualisations.  It attempts to
recover all metrics listed in the requirements, flagging any values that
cannot be derived from the available data.
"""

from __future__ import annotations

import math
import os
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from dotenv import load_dotenv


@dataclass
class MetricResult:
	"""Container for a computed metric and an optional diagnostic note."""

	value: Optional[float]
	note: Optional[str] = None


def _project_root() -> Path:
	return Path(__file__).resolve().parent.parent


def _logs_dir() -> Path:
	return _project_root() / "Server" / "logs"


def _latest_log_file(log_dir: Path) -> Path:
	csv_files = list(log_dir.glob("server_log_*.csv"))
	if not csv_files:
		raise FileNotFoundError(f"No server_log_*.csv files found in {log_dir}")
	return max(csv_files, key=lambda path: path.stat().st_mtime)


def _load_protocol_sizes(project_root: Path) -> Tuple[Optional[int], Optional[int], List[str]]:
	dotenv_path = project_root / ".env"
	load_dotenv(dotenv_path)

	header_size = None
	max_packet_size = None
	issues: List[str] = []

	header_format = os.getenv("HEADER_FORMAT")
	if header_format:
		try:
			header_size = struct.calcsize(header_format)
		except struct.error as exc:
			issues.append(f"Failed to interpret HEADER_FORMAT '{header_format}': {exc}")
	else:
		issues.append("HEADER_FORMAT not present in .env; cannot recover header size")

	max_packet_value = os.getenv("MAX_PACKET_SIZE")
	if max_packet_value:
		try:
			max_packet_size = int(max_packet_value, 0)
		except ValueError as exc:
			issues.append(f"MAX_PACKET_SIZE value '{max_packet_value}' invalid: {exc}")
	else:
		issues.append("MAX_PACKET_SIZE not present in .env")

	return header_size, max_packet_size, issues


def _load_dataset(log_path: Path) -> pd.DataFrame:
	df = pd.read_csv(log_path)
	expected_columns = {
		"device_id",
		"seq",
		"timestamp",
		"arrival_time",
		"duplicate_flag",
		"gap_flag",
		"delayed_flag",
	}

	missing = expected_columns.difference(df.columns)
	if missing:
		raise ValueError(f"Log file {log_path.name} missing columns: {sorted(missing)}")

	df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
	df["arrival_time"] = pd.to_datetime(df["arrival_time"], errors="coerce")

	for flag_column in ("duplicate_flag", "gap_flag", "delayed_flag"):
		df[flag_column] = pd.to_numeric(df[flag_column], errors="coerce").fillna(0).astype(int)

	df = df.sort_values(["device_id", "arrival_time", "seq"]).reset_index(drop=True)
	return df


def _compute_sequence_gaps(df: pd.DataFrame) -> int:
	# Identify explicit missing sequence numbers per device.
	df = df.copy()
	df["prev_seq"] = df.groupby("device_id")["seq"].shift(1)
	df["delta"] = df["seq"] - df["prev_seq"]
	df.loc[df["delta"] <= 0, "delta"] = 1  # Reset on device start or wraparound.
	missing = (df["delta"] - 1).clip(lower=0)
	return int(missing.sum())


def _compute_latency_stats(df: pd.DataFrame) -> pd.Series:
	latency = (df["arrival_time"] - df["timestamp"]).dt.total_seconds()
	return latency.dropna()


def _compute_metrics(
	df: pd.DataFrame, header_size: Optional[int]
) -> Tuple[Dict[str, MetricResult], List[str]]:
	notes: List[str] = []
	total_packets = int(len(df))
	duplicates = int(df["duplicate_flag"].sum())
	gap_flag_count = int(df["gap_flag"].sum())
	missing_sequences = _compute_sequence_gaps(df)

	deduplicated_packets = total_packets - duplicates
	duplicate_rate = duplicates / total_packets if total_packets else math.nan

	metrics: Dict[str, MetricResult] = {
		"packets_received": MetricResult(deduplicated_packets),
		"duplicate_rate": MetricResult(duplicate_rate),
		"sequence_gap_count": MetricResult(missing_sequences),
	}

	# gap_flag is a server-side indicator; surface for reference.
	if gap_flag_count != missing_sequences:
		notes.append(
			"gap_flag count differs from reconstructed missing sequence count; review server gap detection"
		)

	if header_size is not None:
		approx_mean_bytes = header_size
		payload_columns = [col for col in df.columns if col.lower() in {"payload_bytes", "payload_len", "total_bytes"}]
		if payload_columns:
			payload_mean = float(df[payload_columns[0]].mean())
			approx_mean_bytes = header_size + payload_mean
		else:
			notes.append(
				"Payload size column not present; bytes_per_report estimated using header size only"
			)
		metrics["bytes_per_report"] = MetricResult(approx_mean_bytes)
	else:
		metrics["bytes_per_report"] = MetricResult(
			None, "Header size unavailable; load HEADER_FORMAT in .env to enable this metric"
		)

	metrics["cpu_ms_per_report"] = MetricResult(
		None,
		"CPU timing is not logged in server CSV; instrument the server to collect processing durations",
	)

	latency = _compute_latency_stats(df)
	if not latency.empty:
		metrics["median_latency_ms"] = MetricResult(latency.median() * 1000.0)
		metrics["p95_latency_ms"] = MetricResult(latency.quantile(0.95) * 1000.0)
	else:
		notes.append("Latency calculation skipped; timestamp or arrival_time fields missing valid data")

	return metrics, notes


def _render_metrics(metrics: Dict[str, MetricResult]) -> None:
	rows = []
	for key, result in metrics.items():
		rows.append((key, result.value, result.note or ""))
	table = pd.DataFrame(rows, columns=["metric", "value", "note"])
	print("\nComputed Metrics:\n")
	print(table.to_string(index=False, justify="left"))


def _plot_results(df: pd.DataFrame, latency: pd.Series, output_dir: Path) -> None:
	output_dir.mkdir(parents=True, exist_ok=True)

	clean_df = df[df["duplicate_flag"] == 0]
	if clean_df.empty:
		print("Skipping per-device plots: no packets available in the log.")
	else:
		packets_by_device = clean_df.groupby("device_id").size().sort_values(ascending=False)
		if packets_by_device.empty:
			print("Skipping packets-per-device plot: aggregation returned no data.")
		else:
			fig, ax = plt.subplots(figsize=(8, 4))
			packets_by_device.plot(kind="bar", ax=ax, color="#1f77b4")
			ax.set_title("Packets Received per Device")
			ax.set_xlabel("device_id")
			ax.set_ylabel("packets")
			ax.grid(axis="y", linestyle="--", alpha=0.5)
			fig.tight_layout()
			fig.savefig(output_dir / "packets_by_device.png", dpi=150)

	if df.empty:
		print("Skipping duplicate-rate plot: log file is empty.")
	else:
		duplicate_rate = df.groupby("device_id")["duplicate_flag"].mean().sort_values(ascending=False)
		if duplicate_rate.empty:
			print("Skipping duplicate-rate plot: no per-device data.")
		else:
			fig, ax = plt.subplots(figsize=(8, 4))
			duplicate_rate.plot(kind="bar", ax=ax, color="#d62728")
			ax.set_title("Duplicate Rate per Device")
			ax.set_xlabel("device_id")
			ax.set_ylabel("duplicate rate")
			ax.grid(axis="y", linestyle="--", alpha=0.5)
			fig.tight_layout()
			fig.savefig(output_dir / "duplicate_rate_by_device.png", dpi=150)

	if latency.empty:
		print("Skipping latency plots: no valid latency samples available.")
	else:
		fig, ax = plt.subplots(figsize=(8, 4))
		ax.hist(latency, bins=30, color="#2ca02c", alpha=0.8)
		ax.set_title("Latency Distribution (seconds)")
		ax.set_xlabel("seconds")
		ax.set_ylabel("frequency")
		fig.tight_layout()
		fig.savefig(output_dir / "latency_histogram.png", dpi=150)

		fig, ax = plt.subplots(figsize=(8, 4))
		ax.plot(df["arrival_time"], latency, marker="o", linestyle="", alpha=0.3)
		ax.set_title("Latency Over Time")
		ax.set_xlabel("arrival_time")
		ax.set_ylabel("latency (seconds)")
		fig.autofmt_xdate()
		fig.tight_layout()
		fig.savefig(output_dir / "latency_over_time.png", dpi=150)

	plt.close("all")


def main() -> None:
	project_root = _project_root()
	logs_dir = _logs_dir()
	latest_log = _latest_log_file(logs_dir)
	print(f"Using log file: {latest_log.relative_to(project_root)}")

	header_size, max_packet_size, env_issues = _load_protocol_sizes(project_root)
	if env_issues:
		print("Environment notes:")
		for item in env_issues:
			print(f"  - {item}")

	df = _load_dataset(latest_log)
	metrics, notes = _compute_metrics(df, header_size)
	_render_metrics(metrics)

	if notes:
		print("\nAnalysis notes:")
		for note in notes:
			print(f"  - {note}")

	latency_series = _compute_latency_stats(df)
	figures_dir = Path(__file__).resolve().parent / "figures"
	_plot_results(df, latency_series, figures_dir)
	print(f"\nPlots saved under {figures_dir.relative_to(project_root)}")

	derived = {
		"total_packets": int(len(df)),
		"unique_devices": int(df["device_id"].nunique()),
		"max_packet_size": max_packet_size,
	}
	summary = pd.DataFrame([derived])
	print("\nContext summary:\n")
	print(summary.to_string(index=False, justify="left"))


if __name__ == "__main__":
	main()
