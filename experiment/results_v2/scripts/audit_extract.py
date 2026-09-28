#!/usr/bin/env python3
"""Offline verification and extraction of the frozen ABM v2.0 formal outputs.

This program never launches NetLogo and never writes inside --project or
--outputs. It imports the frozen runner's read-only table validator, verifies
the original Mac execution metadata, then emits one row per independent run.
Requires Python 3.10+ and its standard library only.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import time
import xml.etree.ElementTree as ET

BASE = Path(__file__).resolve().parents[1]
IDENTITY = ["condition_id", "replicate_id", "run_id", "seed"]
FINAL = {
    "E_mean": "mean-effectiveness", "O_final": "over-removal-rate",
    "E_final": "effectiveness", "PR_final": "removal-precision",
    "PR_defined": "precision-defined?", "net_E_mean": "mean-net-effectiveness",
    "net_E_final": "net-effectiveness", "cumulative_reviews": "cumulative-reviews",
    "cumulative_tp": "cumulative-tp", "cumulative_fp": "cumulative-fp",
    "cumulative_tn": "cumulative-tn", "cumulative_fn": "cumulative-fn",
    "clean_review_exposure": "cumulative-clean-reviews",
    "distinct_wronged": "count-wrongly-removed",
    "final_pollution_count": "pollution-count",
    "initial_polluted_count": "initial-polluted-count",
    "mean_degree": "mean-degree", "max_degree": "max-degree",
    "degree_sd": "degree-sd", "network_edges": "network-edge-count",
    "count_isolates": "count-isolates", "mean_super_degree": "mean-super-degree",
    "mean_ordinary_degree": "mean-ordinary-degree", "super_count": "count-super-spreaders",
    "legal_action_opportunities": "legal-action-opportunities",
    "active_review_steps": "active-review-steps",
}
TRAJECTORY = {
    "E": "effectiveness", "O": "over-removal-rate", "net_E": "net-effectiveness",
    "PR": "removal-precision", "PR_defined": "precision-defined?",
    "E_mean_to_step": "mean-effectiveness", "net_E_mean_to_step": "mean-net-effectiveness",
}
NETWORK_STATIC = ["mean-degree", "max-degree", "degree-sd", "mean-super-degree", "mean-ordinary-degree"]


def require(truth, message):
    if not truth:
        raise ValueError(message)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def semantic_xml(element):
    return (element.tag, tuple(sorted(element.attrib.items())), (element.text or "").strip(),
            tuple(semantic_xml(child) for child in element))


def table_rows(path):
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = csv.reader(f)
        for row in rows:
            if row and row[0] == "[run number]":
                header = row
                break
        else:
            raise ValueError(f"Missing data header in {path}")
        for values in rows:
            if values:
                require(len(values) == len(header), f"Malformed data in {path}")
                yield dict(zip(header, values))


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def audit(args):
    started = time.monotonic()
    project, outputs, out = (p.resolve() for p in (args.project, args.outputs, args.out))
    require(out != outputs and not out.is_relative_to(outputs), "--out must be outside source outputs")
    require(out != project and not out.is_relative_to(project), "--out must be outside frozen project")
    (out / "audit").mkdir(parents=True, exist_ok=True)
    (out / "processed").mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(project / "scripts"))
    # Suppress bytecode writes in the immutable implementation directory.
    sys.dont_write_bytecode = True
    import run_experiments as runner
    import build_jobs as jobs_module

    protocol, parameters, conditions, manifest, grouped = jobs_module.read_design(project)
    runner.check_manifest_binding(project, manifest)
    by_run = {r["run_id"]: r for r in manifest}
    require(len(by_run) == len(manifest) == 95850, "Manifest count/identity mismatch")
    require(len(conditions) == 3195, "Frozen condition count mismatch")
    require(len({r["seed"] for r in manifest}) == len(manifest), "Seeds are not globally unique")
    binding = read_json(outputs / "execution_binding.json")
    fingerprint = binding["fingerprint"]
    require(fingerprint["schema"] == runner.SCHEMA, "Runner schema mismatch")
    require(fingerprint["model_version"] == jobs_module.MODEL_VERSION, "Model version mismatch")
    bound_checks = []
    for name, expected in fingerprint["file_sha256"].items():
        actual = digest(project / name)
        require(actual == expected, f"Frozen project hash mismatch: {name}")
        bound_checks.append({"file": name, "expected_sha256": expected, "actual_sha256": actual, "matches": True})
    require(len(bound_checks) == 8, "Unexpected protected file count")
    indexed_jobs = jobs_module.read_csv(project / "jobs/job_index.csv")
    job_by_id = {j["job_id"]: j for j in indexed_jobs}
    require(len(indexed_jobs) == len(job_by_id) == 64, "Job index count mismatch")
    for job in indexed_jobs:
        require(digest(project / job["xml_path"]) == job["xml_sha256"], "Frozen job XML hash mismatch")

    inventory = []
    for path in sorted(p for p in outputs.rglob("*") if p.is_file()):
        inventory.append({"file": path.relative_to(outputs).as_posix(), "bytes": path.stat().st_size, "sha256": digest(path)})
    original_hashes = {r["file"]: r["sha256"] for r in inventory}
    runtime = fingerprint["runtime"]
    runtime_files = runtime["files"]
    require(runtime["expected_netlogo"] == "6.4.0", "Unexpected NetLogo version")
    require(binding["environment"]["runtime_file_count"] == len(runtime_files), "Runtime inventory count mismatch")
    require(all(re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) for item in runtime_files), "Invalid recorded runtime digest")
    require(len({item["file"] for item in runtime_files}) == len(runtime_files), "Duplicate recorded runtime file")
    statuses = jobs_module.read_csv(outputs / "run_status.csv")
    status_by_run = {s["run_id"]: s for s in statuses}
    require(len(statuses) == len(status_by_run) == len(manifest), "Run status count or duplicate mismatch")
    require(set(status_by_run) == set(by_run), "Run status identities disagree with manifest")
    require(all(s["status"] == "complete" and not s["last_problem"] for s in statuses), "Run status contains incomplete or problematic runs")
    attempt_files = sorted((outputs / "attempts").glob("*/attempt.json"))
    require(len(attempt_files) == 64, "Expected exactly 64 attempts for received complete run")

    metrics_fields = list(dict.fromkeys(IDENTITY + ["phase"] + list(FINAL) +
                       ["final_step", "observed_rows", "source_csv", "result_sha256"] + list(next(iter(conditions.values())))))
    trajectory_map = dict(TRAJECTORY)
    mapped = set(trajectory_map.values()) | {"run-seed", "model-version"}
    for metric in jobs_module.METRICS:
        if metric not in mapped:
            trajectory_map[metric.replace("-", "_").replace("?", "")] = metric
    trajectory_fields = IDENTITY + ["step"] + list(trajectory_map)
    metrics_tmp = out / "processed/run_metrics.csv.tmp"
    trajectory_tmp = out / "processed/grid_trajectories.csv.gz.tmp"
    seen_runs, seen_jobs = set(), set()
    attempts_report, final_missing = [], Counter()
    phase_counts, row_counts = Counter(), Counter()
    last_cid_rep = (0, 0)
    with metrics_tmp.open("w", newline="", encoding="utf-8") as metrics_file, \
         trajectory_tmp.open("wb") as binary_file, \
         gzip.GzipFile(fileobj=binary_file, mode="wb", filename="", mtime=0) as compressed, \
         io.TextIOWrapper(compressed, encoding="utf-8", newline="") as trajectory_file:
        metrics_writer = csv.DictWriter(metrics_file, fieldnames=metrics_fields)
        trajectory_writer = csv.DictWriter(trajectory_file, fieldnames=trajectory_fields)
        metrics_writer.writeheader()
        trajectory_writer.writeheader()
        for index, meta_path in enumerate(attempt_files, start=1):
            meta = read_json(meta_path)
            folder = meta_path.parent
            require(meta["attempt_id"] == folder.name, "Attempt directory identity mismatch")
            require(meta["fingerprint"] == fingerprint, f"Execution fingerprint mismatch in {folder.name}")
            require(meta["environment"] == binding["environment"], f"Execution environment changed in {folder.name}")
            require(meta["state"] == "finished" and meta["returncode"] == 0, f"Unsuccessful attempt {folder.name}")
            require(meta["job_id"] in job_by_id and meta["job_id"] not in seen_jobs, "Missing/duplicate job identity")
            seen_jobs.add(meta["job_id"])
            job = job_by_id[meta["job_id"]]
            phase = job["phase"]
            expected_ids = [r["run_id"] for cid in map(int, job["condition_ids"].split(";")) for r in grouped[cid]]
            require(meta["run_ids"] == expected_ids, f"Attempt-to-job run list mismatch in {folder.name}")
            require(not seen_runs.intersection(expected_ids), "Duplicate run across attempts")
            seen_runs.update(expected_ids)
            expected_runs = [by_run[rid] for rid in expected_ids]
            raw_path = folder / "raw.csv"
            require(original_hashes[raw_path.relative_to(outputs).as_posix()] == meta["raw_csv_sha256"], "Raw CSV recorded hash mismatch")
            require(original_hashes[(folder / "missing_runs.xml").relative_to(outputs).as_posix()] == meta["xml_sha256"], "Attempt XML recorded hash mismatch")
            xml_root = ET.parse(folder / "missing_runs.xml").getroot()
            rebuilt = jobs_module.make_experiment(folder.name, phase,
                       [conditions[cid] for cid in sorted({int(r["condition_id"]) for r in expected_runs})], grouped, parameters)
            require(xml_root.tag == "experiments" and len(xml_root) == 1 and
                    semantic_xml(xml_root[0]) == semantic_xml(rebuilt), "Attempt XML semantics differ from frozen job")
            valid, invalid, file_issues = runner.validate_table(raw_path, expected_runs, conditions, parameters)
            require(not invalid and not file_issues and set(valid) == set(expected_ids),
                    f"Raw table validation failed in {folder.name}: {list(invalid.items())[:2]} {file_issues}")
            log = (folder / "netlogo.log").read_text(encoding="utf-8", errors="replace")
            require(not runner.ERROR_PATTERN.search(log), f"Runtime error in {folder.name}")
            archived_validation = read_json(folder / "validation.json")
            require(archived_validation["valid_runs"] == len(valid) and archived_validation["invalid_runs"] == 0 and
                    not archived_validation["file_issues"] and not archived_validation["runtime_error_in_log"],
                    f"Archived validation report contradicts raw table: {folder.name}")
            relative_csv = raw_path.relative_to(outputs).as_posix()
            for rid, result in valid.items():
                source_status = status_by_run[rid]
                require(all(source_status[k] == by_run[rid][k] for k in IDENTITY), "Run status identity mismatch")
                require(source_status["source_csv"] == relative_csv and source_status["attempt"] == folder.name,
                        "Run status source provenance mismatch")
                require(source_status["result_sha256"] == result["result_sha256"] and
                        int(source_status["rows"]) == result["rows"] and
                        int(source_status["behavior_run"]) == result["behavior_run"], "Run status digest/count mismatch")
            finals, network_states, independent_sums = {}, {}, defaultdict(lambda: [0.0, 0.0, 0])
            batch_rows = 0
            for row in table_rows(raw_path):
                batch_rows += 1
                cid, rep, step = (runner.integer(row[k]) for k in ("condition-id", "replicate-id", "[step]"))
                rid = f"c{cid:04d}_r{rep:02d}"
                identity = {k: by_run[rid][k] for k in IDENTITY}
                if phase == "grid":
                    network_state = tuple(row[k] for k in NETWORK_STATIC)
                    require(rid not in network_states or network_states[rid] == network_state,
                            f"Network degree diagnostics changed over time: {rid}")
                    network_states[rid] = network_state
                    trajectory_writer.writerow(identity | {"step": step} |
                                               {dst: runner.clean(row[src]) for dst, src in trajectory_map.items()})
                    if step > 0:
                        values = independent_sums[rid]
                        values[0] += runner.number(row["effectiveness"])
                        values[1] += runner.number(row["net-effectiveness"])
                        values[2] += 1
                if step == int(conditions[cid]["max-ticks"]):
                    require(rid not in finals, "Duplicate final row")
                    final_row = identity | {"phase": phase} | {dst: runner.clean(row[src]) for dst, src in FINAL.items()} | {
                        "final_step": step, "observed_rows": valid[rid]["rows"], "source_csv": relative_csv,
                        "result_sha256": valid[rid]["result_sha256"]} | conditions[cid]
                    finals[rid] = final_row
                    for field in FINAL:
                        if final_row[field] in runner.NA:
                            final_missing[field] += 1
            require(set(finals) == set(expected_ids), "Missing final metrics")
            require(batch_rows == int(job["expected_data_rows"]), "Batch observation count mismatch")
            for rid in expected_ids:
                final_row = finals[rid]
                if phase == "grid":
                    sE, sNet, n_steps = independent_sums[rid]
                    require(n_steps == 50 and runner.close(sE / n_steps, float(final_row["E_mean"])) and
                            runner.close(sNet / n_steps, float(final_row["net_E_mean"])), "Independent final mean verification failed")
                cid_rep = int(final_row["condition_id"]), int(final_row["replicate_id"])
                require(cid_rep > last_cid_rep, "Noncanonical output order")
                last_cid_rep = cid_rep
                metrics_writer.writerow(final_row)
            phase_counts[phase] += len(valid)
            row_counts[phase] += batch_rows
            attempts_report.append({"attempt": folder.name, "job_id": meta["job_id"], "phase": phase,
                "expected_runs": len(expected_runs), "validated_runs": len(valid), "data_rows": batch_rows,
                "raw_csv_sha256": meta["raw_csv_sha256"], "xml_sha256": meta["xml_sha256"],
                "duration_seconds": meta["duration_seconds"], "returncode": meta["returncode"], "log_bytes": (folder / "netlogo.log").stat().st_size,
                "raw_validation": "passed", "xml_semantic_match": True, "run_status_match": True})
            print(f"Audited {index:02d}/64 {meta['job_id']}: {len(valid)} runs, {batch_rows} rows", flush=True)

    require(seen_runs == set(by_run) and seen_jobs == set(job_by_id), "Final identity coverage incomplete")
    require(phase_counts == {"grid": 5850, "p4": 90000}, "Phase run totals differ from frozen design")
    require(row_counts == {"grid": 298350, "p4": 90000}, "Phase observation totals differ from frozen design")
    for name in ("execution_summary.json", "validation_summary.json"):
        summary = read_json(outputs / name)
        require(summary["total_manifest_runs"] == 95850, "Execution summary total mismatch")
        require(summary.get("valid_runs", summary.get("validated_runs_all_phases")) == 95850, "Execution summary completion mismatch")
    archived_summary = read_json(outputs / "validation_summary.json")
    require(len(archived_summary["attempts"]) == 64, "Archived validation summary attempt count mismatch")
    for report in archived_summary["attempts"]:
        require(report["invalid_runs"] == 0 and not report["file_issues"] and not report["runtime_error_in_log"] and
                report["valid_runs"] == report["expected_runs"], "Archived validation summary contains errors")
    unchanged = all(digest(outputs / name) == value for name, value in original_hashes.items())
    require(unchanged, "An original source artifact changed during analysis")
    metrics_path = out / "processed/run_metrics.csv"
    trajectory_path = out / "processed/grid_trajectories.csv.gz"
    metrics_tmp.replace(metrics_path)
    trajectory_tmp.replace(trajectory_path)
    with (out / "audit/source_inventory.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["file", "bytes", "sha256"])
        w.writeheader(); w.writerows(inventory)
    with (out / "audit/attempt_audit.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(attempts_report[0]))
        w.writeheader(); w.writerows(attempts_report)
    limitations = [
        "Runtime binary hashes are recorded in the supplied Mac metadata and consistent across all attempts; the remote Mac installation itself was not independently rehashed.",
        "P4 stores only step-50 output. Its E_mean and net_E_mean are the model's running means over steps 1–50; their full trajectories cannot be reconstructed from this archive. Grid means were independently recomputed from 50 observations.",
        "Digest agreement establishes internal provenance consistency, not a cryptographic proof that the simulation was executed on the reported physical device.",
        "Thirty independent seeds are used per condition. Replicate labels across different conditions do not identify paired runs.",
        "No old v1.8 data are pooled. Distinct ever-wronged accounts are distinct from repeated false-positive events.",
    ]
    report = {"schema": "ABM-v2-formal-output-offline-audit-v1", "status": "passed",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "protocol_version": protocol["version"], "model_version": jobs_module.MODEL_VERSION,
        "conditions": len(conditions), "replicates_per_condition": 30, "validated_runs": len(seen_runs),
        "batches": len(attempts_report), "runs_by_phase": dict(phase_counts), "data_rows_by_phase": dict(row_counts),
        "total_data_rows": sum(row_counts.values()), "duplicate_run_ids": 0, "missing_run_ids": 0,
        "invalid_runs": 0, "invalid_files": 0, "unique_seeds": len({r["seed"] for r in manifest}),
        "undefined_final_outcomes": dict(final_missing), "protected_file_checks": bound_checks,
        "frozen_job_xml_hashes_checked": len(indexed_jobs), "source_files": len(inventory),
        "original_source_files_unchanged": unchanged,
        "runtime_environment_recorded": binding["environment"], "runtime_inventory_files": len(runtime_files),
        "runtime_binaries_independently_available": False,
        "outputs": {"processed/run_metrics.csv": {"rows": len(seen_runs), "sha256": digest(metrics_path)},
                    "processed/grid_trajectories.csv.gz": {"rows": row_counts["grid"], "sha256": digest(trajectory_path)}},
        "limitations": limitations, "elapsed_seconds": round(time.monotonic() - started, 3),
        "analysis_script_sha256": digest(Path(__file__)), "python_version": sys.version}
    if args.archive and args.archive.is_file():
        report["input_archive"] = {"filename": args.archive.name, "bytes": args.archive.stat().st_size, "sha256": digest(args.archive)}
    write_json(out / "audit/data_audit.json", report)
    write_json(out / "audit/data_dictionary.json", {"unit": "one independent simulated run unless noted", "missing_value": "NA",
       "run_metrics_columns": metrics_fields, "run_metrics_reporter_map": FINAL,
       "grid_trajectories_columns": trajectory_fields, "grid_trajectory_reporter_map": trajectory_map,
       "E_mean": "Arithmetic mean of effectiveness at steps 1..50; step 0 excluded.",
       "O_final": "100 times distinct ever-wronged accounts / N at step 50; not FP event frequency.",
       "PR_final": "100 cumulative TP / (cumulative TP + cumulative FP), NA when denominator is zero.",
       "clean_review_exposure": "Cumulative clean-account review events (TN + FP); repeated accounts may contribute repeatedly.",
       "PR_defined": "Literal true/false, denotes whether cumulative TP + FP is positive.",
       "phase": "grid includes all trajectory-based P1/P2/P3/P5/P6 and robustness modules; p4 is LHS end-only data.",
       "parameter_metadata": "Condition metadata and parameters retain exact original column names/values."})
    print(json.dumps({k: report[k] for k in ("status", "validated_runs", "total_data_rows", "undefined_final_outcomes", "elapsed_seconds")}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=BASE.parent / "implementation", help="Frozen experiment project directory")
    parser.add_argument("--outputs", type=Path, default=BASE / "source/outputs", help="Read-only extracted outputs directory")
    parser.add_argument("--out", type=Path, default=BASE, help="Analysis result directory, outside project and source outputs")
    parser.add_argument("--archive", type=Path, help="Optional original ZIP for input provenance hash")
    args = parser.parse_args()
    try:
        audit(args)
    except Exception as exc:
        (args.out / "audit").mkdir(parents=True, exist_ok=True)
        write_json(args.out / "audit/data_audit_failed.json", {"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
        raise


if __name__ == "__main__":
    main()
