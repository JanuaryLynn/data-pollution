#!/usr/bin/env python3
"""Portable NetLogo 6.4 batch execution with verified, identity-preserving resume.

Default is a dry run.  Add --execute to run selected batches.  Raw CSVs and logs
are immutable per attempt; only outputs/run_status.csv is a replaceable view.
The frozen design/run_manifest.csv is never modified by this script.
"""
from __future__ import annotations

import argparse
import atexit
from collections import defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time

from build_jobs import (METRICS, MODEL_VERSION, ROOT, make_experiment, phase_of,
                        read_csv, read_design, sha256, write_xml)

SCHEMA = "ABM-verified-runner-v1"
_ACTIVE_LOCK: Path | None = None
NA = {"NA", "N/A", "NaN", "nan", ""}
ERROR_PATTERN = re.compile(
    r"(?im)(?:^\s*(?:Exception(?: in thread)?|Error:|RUNTIME ERROR)|"
    r"(?:CompilerException|ExtensionException|LogoException|OutOfMemoryError)|"
    r"Run\s*#?\d+.*(?:error|exception))"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def release_lock() -> None:
    global _ACTIVE_LOCK
    if _ACTIVE_LOCK is not None:
        try:
            _ACTIVE_LOCK.unlink(missing_ok=True)
        finally:
            _ACTIVE_LOCK = None


def acquire_lock(outputs: Path) -> None:
    global _ACTIVE_LOCK
    outputs.mkdir(parents=True, exist_ok=True)
    lock = outputs / ".runner.lock"
    try:
        with lock.open("x", encoding="utf-8") as stream:
            json.dump({"pid": os.getpid(), "host": platform.node(), "created_at_utc": utc_now()}, stream)
    except FileExistsError as exc:
        raise ValueError(f"Another invocation owns {lock}. After a crash, confirm no runner/Java "
                         "process is still writing before removing this lock.") from exc
    _ACTIVE_LOCK = lock
    atexit.register(release_lock)


def json_write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic replacement is for metadata only, never a raw simulation artifact.
    with tempfile.NamedTemporaryFile("w", dir=path.parent, encoding="utf-8",
                                     delete=False) as stream:
        json.dump(data, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
        temporary = Path(stream.name)
    temporary.replace(path)


def clean(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        value = value[1:-1]
    return value


def number(value: str) -> float:
    result = float(clean(value))
    if not math.isfinite(result):
        raise ValueError(f"Non-finite number: {value}")
    return result


def integer(value: str) -> int:
    result = number(value)
    if result != int(result):
        raise ValueError(f"Expected integer: {value}")
    return int(result)


def close(actual: float, expected: float) -> bool:
    return math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-8)


def headless_command(launcher: Path) -> list[str]:
    """Return the launcher prefix while preserving its invocation basename."""
    prefix = [str(launcher)]
    if launcher.name in {"NetLogo_Console", "NetLogo_Console.exe"}:
        prefix.append("--headless")
    return prefix


def launch_working_directory(launcher: Path, project_root: Path) -> Path:
    """Console locates its application bundle relative to the install folder."""
    if len(headless_command(launcher)) == 2:
        return launcher.expanduser().absolute().parent
    return project_root


def runtime_information(launcher: Path) -> tuple[dict, dict]:
    """Hash launcher, libraries and bundled runtime without a simulation."""
    invocation_path = launcher.expanduser().absolute()
    launcher = invocation_path.resolve()
    if not launcher.is_file():
        raise ValueError(f"NetLogo launcher does not exist: {launcher}")
    if not os.access(launcher, os.X_OK):
        raise ValueError(f"NetLogo launcher is not executable: {launcher}")
    home = invocation_path.parent
    # Official Linux and macOS launchers keep libraries in their own folder or
    # the adjacent app directory.  Runtime helper layouts can use either.
    roots = [home]
    if home.name == "bin":
        roots.append(home.parent)
    if launcher.parent.name == "MacOS":
        roots.append(launcher.parent.parent)
    files = {launcher}
    for base in roots:
        for pattern in ("**/*.jar", "**/*.nls", "**/*.cfg", "**/release",
                        "**/libjvm.dylib", "**/libjvm.so", "**/jvm.dll", "**/lib/modules"):
            files.update(p.resolve() for p in base.glob(pattern) if p.is_file())
    inventory = []
    for path in sorted(files):
        try:
            relative = str(path.relative_to(home))
        except ValueError:
            try:
                relative = str(path.relative_to(home.parent))
            except ValueError:
                relative = "external:" + str(path)
        inventory.append({"file": relative, "sha256": sha256(path)})
    java_candidates = []
    is_console = len(headless_command(invocation_path)) == 2
    if not is_console:
        java_candidates = [home / "runtime/bin/java", home / "jre/bin/java",
                           home / "runtime/Contents/Home/bin/java"]
        if os.environ.get("JAVA_HOME"):
            java_candidates.append(Path(os.environ["JAVA_HOME"]) / "bin/java")
        found_java = shutil.which("java")
        if found_java:
            java_candidates.append(Path(found_java))
    java_versions = []
    for path in java_candidates:
        if path.is_file() and str(path.resolve()) not in [x["path"] for x in java_versions]:
            try:
                result = subprocess.run([str(path), "-version"], capture_output=True,
                                        text=True, timeout=10, check=False)
                java_versions.append({"path": str(path.resolve()),
                                      "version": (result.stdout + result.stderr).strip(),
                                      "binary_sha256": sha256(path)})
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise ValueError(f"Cannot inspect Java runtime {path}: {exc}") from exc
    signature = {"expected_netlogo": "6.4.0", "launcher_kind": "console" if is_console else "headless_script", "files": inventory,
                 "java": [{k: v for k, v in item.items() if k != "path"} for item in java_versions]}
    information = {"launcher": str(launcher), "launcher_invocation": str(invocation_path), "python": sys.version,
                   "platform": platform.platform(), "java_candidates": java_versions,
                   "runtime_file_count": len(inventory)}
    return signature, information


def fingerprints(root: Path, launcher: Path) -> tuple[dict, dict]:
    names = ["protocol/ABM_step1_protocol.json", "design/conditions.csv",
             "design/run_manifest.csv", "jobs/job_index.csv",
             "model/exp_code_v2.0.nls", "model/ABM_revision_v2.0.nlogo",
             "scripts/build_jobs.py", "scripts/run_experiments.py"]
    files = {name: sha256(root / name) for name in names}
    runtime, info = runtime_information(launcher)
    return {"schema": SCHEMA, "model_version": MODEL_VERSION,
            "file_sha256": files, "runtime": runtime}, info


def check_manifest_binding(root: Path, manifest: list[dict[str, str]]) -> None:
    expected = {"model_source_sha256": sha256(root / "model/exp_code_v2.0.nls"),
                "protocol_sha256": sha256(root / "protocol/ABM_step1_protocol.json"),
                "conditions_file_sha256": sha256(root / "design/conditions.csv"),
                "model_version": MODEL_VERSION}
    for field, value in expected.items():
        if any(row.get(field) != value for row in manifest):
            raise ValueError(f"Manifest {field} does not match the current frozen file/version. "
                             "Resolve the design/code version before executing.")


def check_row(row: dict[str, str], condition: dict[str, str], run: dict[str, str],
              parameters: list[dict]) -> dict:
    """Validate a single row independently of NetLogo's exit code."""
    for parameter in parameters:
        name = parameter["name"]
        if parameter["type"] == "enum":
            if clean(row[name]) != condition[name]:
                raise ValueError(f"Parameter mismatch: {name}")
        elif not close(number(row[name]), float(condition[name])):
            raise ValueError(f"Parameter mismatch: {name}")
    if integer(row["run-seed"]) != int(run["seed"]):
        raise ValueError("run-seed differs from frozen manifest")
    if clean(row["model-version"]) != MODEL_VERSION:
        raise ValueError("model-version differs from frozen manifest")
    step = integer(row["[step]"])
    limit = int(condition["max-ticks"])
    if not 0 <= step <= limit:
        raise ValueError(f"Step outside 0..{limit}")
    n = int(condition["num-nodes"])
    ints = ["observation-count", "initial-polluted-count", "pollution-count",
            "polluted-pre-review", "count-wrongly-removed", "step-reviews", "step-tp",
            "step-fp", "step-tn", "step-fn", "cumulative-reviews", "cumulative-tp",
            "cumulative-fp", "cumulative-tn", "cumulative-fn", "step-clean-reviews",
            "cumulative-clean-reviews", "legal-action-opportunities", "active-review-steps",
            "network-node-count", "network-edge-count", "count-isolates",
            "count-super-spreaders", "legal-load", "audit-load"]
    data = {name: integer(row[name]) for name in ints}
    if any(value < 0 for value in data.values()):
        raise ValueError("Negative count")
    if data["network-node-count"] != n or data["observation-count"] != step:
        raise ValueError("Node or observation count mismatch")
    for name in ("pollution-count", "initial-polluted-count", "polluted-pre-review",
                 "count-wrongly-removed", "step-reviews", "count-isolates",
                 "count-super-spreaders", "legal-load", "audit-load"):
        if data[name] > n:
            raise ValueError(f"{name} exceeds N")
    if data["initial-polluted-count"] != math.floor(n * float(condition["p0"]) / 100 + 0.5):
        raise ValueError("Initial pollution does not match p0")
    if data["count-super-spreaders"] != math.floor(n * float(condition["super-ratio"]) / 100 + 0.5):
        raise ValueError("Superspreader count mismatch")
    if data["legal-load"] != math.floor(n * float(condition["legal-strength"]) / 100 + 0.5):
        raise ValueError("Rounded legal review capacity mismatch")
    if data["audit-load"] != math.floor(n * float(condition["platform-speed"]) / 100 + 0.5):
        raise ValueError("Rounded platform review capacity mismatch")
    for prefix in ("step", "cumulative"):
        if data[f"{prefix}-reviews"] != sum(data[f"{prefix}-{c}"] for c in ("tp", "fp", "tn", "fn")):
            raise ValueError(f"{prefix} confusion totals do not equal reviews")
        if data[f"{prefix}-clean-reviews"] != data[f"{prefix}-tn"] + data[f"{prefix}-fp"]:
            raise ValueError(f"{prefix} clean exposure mismatch")
    if data["count-wrongly-removed"] > data["cumulative-fp"]:
        raise ValueError("Distinct wronged nodes exceed false-positive events")
    if data["pollution-count"] != data["polluted-pre-review"] - data["step-tp"]:
        raise ValueError("Pollution change during review differs from TP")
    if data["step-tp"] + data["step-fn"] > data["polluted-pre-review"]:
        raise ValueError("Reviewed polluted count exceeds available polluted nodes")
    if data["step-tn"] + data["step-fp"] > n - data["polluted-pre-review"]:
        raise ValueError("Reviewed clean count exceeds available clean nodes")
    actor = condition["treatment"]
    tau = int(condition["legal-response-time"])
    if step == 0 or actor == "none":
        expected_reviews = 0
    elif actor == "legal":
        expected_reviews = data["legal-load"] if (step - 1) % tau == 0 else 0
    elif condition["platform-workload-mode"] == "fixed":
        expected_reviews = data["audit-load"]
    else:
        expected_reviews = min(n, data["audit-load"],
                               math.floor(float(condition["demand-kappa"]) * data["polluted-pre-review"] + 0.5))
    if data["step-reviews"] != expected_reviews:
        raise ValueError("Actual review workload disagrees with the scheduled rule")
    opportunities = (1 + (step - 1) // tau) if actor == "legal" and step else 0
    if data["legal-action-opportunities"] != opportunities:
        raise ValueError("Legal action opportunity count mismatch")
    if data["active-review-steps"] > step:
        raise ValueError("Active review steps exceed elapsed steps")
    if actor == "none" and data["cumulative-reviews"]:
        raise ValueError("No-treatment run contains review events")
    if actor == "legal" and data["cumulative-reviews"] != opportunities * data["legal-load"]:
        raise ValueError("Cumulative legal workload mismatch")
    if actor == "platform" and condition["platform-workload-mode"] == "fixed" and data["cumulative-reviews"] != step * data["audit-load"]:
        raise ValueError("Cumulative platform workload mismatch")
    if not close(number(row["mean-degree"]), 2 * data["network-edge-count"] / n):
        raise ValueError("Mean degree differs from 2M/N")
    values = {name: number(row[name]) for name in ("effectiveness", "over-removal-rate",
              "net-effectiveness", "current-pollution-rate", "actual-review-coverage")}
    E, O = 100 - 100 * data["pollution-count"] / n, 100 * data["count-wrongly-removed"] / n
    expected = {"effectiveness": E, "over-removal-rate": O,
                "net-effectiveness": E - float(condition["lambda-weight"]) * O,
                "current-pollution-rate": 100 - E,
                "actual-review-coverage": 100 * data["step-reviews"] / n}
    if any(not close(values[name], value) for name, value in expected.items()):
        raise ValueError("E/O/net-effectiveness/pollution/workload formula mismatch")
    denominator = data["cumulative-tp"] + data["cumulative-fp"]
    if clean(row["precision-defined?"]).lower() != str(denominator > 0).lower():
        raise ValueError("precision-defined? mismatch")
    if denominator:
        if not close(number(row["removal-precision"]), 100 * data["cumulative-tp"] / denominator):
            raise ValueError("PR formula mismatch")
    elif clean(row["removal-precision"]) not in NA:
        raise ValueError("PR with zero denominator must be NA")
    for name in ("mean-effectiveness", "mean-net-effectiveness"):
        if step:
            values[name] = number(row[name])
            low = 0 if name == "mean-effectiveness" else -100 * float(condition["lambda-weight"])
            if not low - 1e-8 <= values[name] <= 100 + 1e-8:
                raise ValueError(f"{name} outside possible range")
        elif clean(row[name]) not in NA:
            raise ValueError("Step-0 time means must be NA")
    # Diagnostics must be finite. Empty superspreader/ordinary groups may return
    # NA only at explicit 0/100% boundary tests, not in the frozen formal design.
    for name in ("max-degree", "degree-sd", "mean-super-degree", "mean-ordinary-degree"):
        if name == "mean-super-degree" and data["count-super-spreaders"] == 0 and clean(row[name]) in NA:
            continue
        if name == "mean-ordinary-degree" and data["count-super-spreaders"] == n and clean(row[name]) in NA:
            continue
        if number(row[name]) < 0:
            raise ValueError(f"Negative network diagnostic {name}")
    data.update(values)
    data["step"] = step
    data["behavior_run"] = integer(row["[run number]"])
    return data


def validate_table(path: Path, expected_runs: list[dict[str, str]],
                   conditions: dict[int, dict[str, str]], parameters: list[dict]) -> tuple[dict, dict, list]:
    """Return completed identities, per-run problems, and file-level problems."""
    expected = {(int(r["condition_id"]), int(r["replicate_id"])): r for r in expected_runs}
    issues = defaultdict(list)
    global_issues = []
    fatal_file = False
    observations = defaultdict(dict)
    behavior_ids = {}
    run_hashes = defaultdict(dict)
    if not path.is_file():
        return {}, {r["run_id"]: ["No output CSV"] for r in expected_runs}, []
    try:
        with path.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.reader(stream)
            first = next(reader, [])
            if not first or "NetLogo 6.4.0" not in first[0]:
                return {}, {}, ["Output is not a NetLogo 6.4.0 BehaviorSpace table"]
            header = None
            for index, row in enumerate(reader):
                if row and row[0] == "[run number]":
                    header = row
                    break
                if index > 40:
                    break
            if header is None:
                return {}, {}, ["Missing BehaviorSpace CSV header"]
            required = {"[run number]", "[step]", "condition-id", "replicate-id", *METRICS,
                        *(p["name"] for p in parameters)}
            if len(set(header)) != len(header) or not required.issubset(header):
                return {}, {}, [f"Duplicate or missing columns: {sorted(required - set(header))}"]
            for line, values in enumerate(reader, start=8):
                if not values:
                    continue
                if len(values) != len(header):
                    global_issues.append(f"Malformed/truncated CSV record near line {line}")
                    continue
                row = dict(zip(header, values))
                try:
                    key = integer(row["condition-id"]), integer(row["replicate-id"])
                except ValueError:
                    global_issues.append(f"Invalid identity near line {line}")
                    fatal_file = True
                    continue
                if key not in expected:
                    global_issues.append(f"Unexpected condition/replicate {key} near line {line}")
                    fatal_file = True
                    continue
                run = expected[key]
                rid = run["run_id"]
                try:
                    data = check_row(row, conditions[key[0]], run, parameters)
                    step = data["step"]
                    if step in observations[key]:
                        raise ValueError(f"Duplicate step {step}")
                    bid = data["behavior_run"]
                    if bid in behavior_ids and behavior_ids[bid] != key:
                        raise ValueError("BehaviorSpace run number maps to multiple identities")
                    behavior_ids[bid] = key
                    if observations[key] and next(iter(observations[key].values()))["behavior_run"] != bid:
                        raise ValueError("One identity maps to multiple BehaviorSpace run numbers")
                    observations[key][step] = data
                    canonical = {k: clean(v) for k, v in row.items() if k != "[run number]"}
                    run_hashes[key][step] = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()
                except (KeyError, ValueError, TypeError) as exc:
                    if len(issues[rid]) < 8:
                        issues[rid].append(f"Line {line}: {exc}")
    except (OSError, UnicodeError, csv.Error) as exc:
        global_issues.append(f"Cannot read complete output: {exc}")
        fatal_file = True
    completed = {}
    for key, run in expected.items():
        rid = run["run_id"]
        maximum = int(run.get("expected_final_step", conditions[key[0]]["max-ticks"]))
        expected_steps = list(range(maximum + 1)) if phase_of(run) == "grid" else [maximum]
        actual = sorted(observations[key])
        if actual != expected_steps:
            issues[rid].append(f"Incomplete steps: expected {len(expected_steps)}, found {len(actual)}")
        if issues[rid]:
            continue
        rows = observations[key]
        if phase_of(run) == "grid":
            running_E = running_net = 0.0
            previous = None
            active = 0
            for step in actual:
                current = rows[step]
                if step == 0:
                    if any(current[f"cumulative-{name}"] for name in ("reviews", "tp", "fp", "tn", "fn")):
                        issues[rid].append("Step-0 counters are not zero")
                else:
                    for name in ("reviews", "tp", "fp", "tn", "fn"):
                        if current[f"cumulative-{name}"] != previous[f"cumulative-{name}"] + current[f"step-{name}"]:
                            issues[rid].append(f"Cumulative {name} increment mismatch at {step}")
                    if current["count-wrongly-removed"] < previous["count-wrongly-removed"]:
                        issues[rid].append("Ever-wronged count decreased")
                    running_E += current["effectiveness"]
                    running_net += current["net-effectiveness"]
                    if not close(current["mean-effectiveness"], running_E / step) or not close(current["mean-net-effectiveness"], running_net / step):
                        issues[rid].append(f"Running mean mismatch at {step}")
                    active += current["step-reviews"] > 0
                if current["active-review-steps"] != active:
                    issues[rid].append(f"Active review steps mismatch at {step}")
                if previous and any(current[name] != previous[name] for name in
                                    ("network-node-count", "network-edge-count", "count-isolates", "count-super-spreaders", "initial-polluted-count")):
                    issues[rid].append("Static network/initial-state diagnostics changed")
                previous = current
        if not issues[rid]:
            digest = hashlib.sha256("".join(run_hashes[key][step] for step in actual).encode()).hexdigest()
            completed[rid] = {"rows": len(actual), "result_sha256": digest,
                              "behavior_run": rows[maximum]["behavior_run"]}
    # Bad identity/structure makes the entire file untrustworthy. Complete rows
    # from an interrupted process can otherwise be retained and retried by ID.
    if fatal_file:
        completed = {}
    return completed, {rid: problem for rid, problem in issues.items() if problem}, global_issues[:20]


def scan_attempts(outputs: Path, manifest: list[dict[str, str]], conditions: dict,
                  parameters: list[dict], fingerprint: dict) -> tuple[dict, dict, list]:
    by_id = {r["run_id"]: r for r in manifest}
    completed, problems, attempts = {}, {}, []
    for metadata_file in sorted((outputs / "attempts").glob("*/attempt.json")):
        metadata = json.loads(metadata_file.read_text())
        if metadata.get("fingerprint") != fingerprint:
            raise ValueError(f"Different model/design/runtime fingerprint in {metadata_file}")
        expected = [by_id[rid] for rid in metadata["run_ids"]]
        csv_path = metadata_file.parent / "raw.csv"
        recorded_raw_hash = metadata.get("raw_csv_sha256")
        if recorded_raw_hash and (not csv_path.is_file() or sha256(csv_path) != recorded_raw_hash):
            raise ValueError(f"Previously recorded immutable raw CSV changed: {csv_path}")
        if sha256(metadata_file.parent / "missing_runs.xml") != metadata["xml_sha256"]:
            raise ValueError(f"Recorded attempt XML changed: {metadata_file.parent}")
        if csv_path.is_file() and not recorded_raw_hash:
            metadata["raw_csv_sha256"] = sha256(csv_path)
            metadata["sealed_after_interruption_at_utc"] = utc_now()
            json_write(metadata_file, metadata)
        valid, invalid, file_issues = validate_table(csv_path, expected, conditions, parameters)
        log_path = metadata_file.parent / "netlogo.log"
        log_text = log_path.read_text(errors="replace") if log_path.exists() else ""
        diagnostic = bool(ERROR_PATTERN.search(log_text))
        report = {"attempt": metadata_file.parent.name, "valid_runs": len(valid),
                  "expected_runs": len(expected), "invalid_runs": len(invalid),
                  "file_issues": file_issues, "runtime_error_in_log": diagnostic,
                  "returncode": metadata.get("returncode"),
                  "checked_at_utc": utc_now()}
        json_write(metadata_file.parent / "validation.json", report | {"run_issues": invalid})
        attempts.append(report)
        problems.update(invalid)
        for rid, info in valid.items():
            if rid in completed and completed[rid]["result_sha256"] != info["result_sha256"]:
                raise ValueError(f"Conflicting valid results for {rid}; do not pool or choose one")
            if rid not in completed:
                completed[rid] = info | {"source_csv": str(csv_path.relative_to(outputs)),
                                          "attempt": metadata_file.parent.name}
    return completed, problems, attempts


def write_status(outputs: Path, manifest: list[dict[str, str]], completed: dict,
                 problems: dict) -> None:
    target = outputs / "run_status.csv"
    temporary = outputs / "run_status.csv.tmp"
    fields = ["run_id", "condition_id", "replicate_id", "seed", "status", "rows",
              "source_csv", "behavior_run", "result_sha256", "attempt", "last_problem"]
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for run in manifest:
            rid = run["run_id"]
            state = {k: run[k] for k in ("run_id", "condition_id", "replicate_id", "seed")}
            if rid in completed:
                state.update(completed[rid])
                state.update(status="complete", last_problem="")
            else:
                state.update(status="retry_pending" if rid in problems else "pending",
                             last_problem="; ".join(problems.get(rid, []))[:800])
            writer.writerow(state)
    temporary.replace(target)


def remaining_for_job(job: dict, manifest_by_condition: dict, complete: dict) -> list[dict]:
    return [run for cid in map(int, job["condition_ids"].split(";"))
            for run in manifest_by_condition[cid] if run["run_id"] not in complete]


def command_for(launcher: Path, model: Path, xml: Path, experiment: str,
                table: Path, threads: int) -> list[str]:
    # The official Console executable loads the bundled runtime itself.  Its
    # --headless switch is not a BehaviorSpace option for netlogo-headless.sh.
    prefix = headless_command(launcher)
    return prefix + ["--model", str(model), "--setup-file", str(xml),
            "--experiment", experiment, "--table", str(table), "--threads", str(threads)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--netlogo-headless", type=Path,
                        help="NetLogo 6.4.0 netlogo-headless.sh or official NetLogo_Console (Mac/Linux)")
    parser.add_argument("--phase", choices=("grid", "p4", "all"), default="grid")
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--limit-batches", type=int, help="Maximum pending batches this invocation")
    parser.add_argument("--outputs", type=Path, help="Fresh or matching existing output directory")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true", help="Execute; without this flag nothing runs")
    mode.add_argument("--dry-run", action="store_true", help="List pending jobs, execute nothing")
    parser.add_argument("--validate-only", action="store_true", help="Revalidate existing attempts only")
    args = parser.parse_args()
    if args.threads < 1 or (args.limit_batches is not None and args.limit_batches < 1):
        parser.error("threads and limit-batches must be positive")
    if args.validate_only and args.execute:
        parser.error("--validate-only cannot be combined with --execute")
    root = args.root.resolve()
    outputs = (args.outputs or root / "outputs").resolve()
    _, parameters, conditions, manifest, by_condition = read_design(root)
    jobs = read_csv(root / "jobs/job_index.csv")
    for job in jobs:
        if sha256(root / job["xml_path"]) != job["xml_sha256"]:
            raise ValueError(f"Job XML changed after indexing: {job['xml_path']}")
    jobs = [j for j in jobs if args.phase == "all" or j["phase"] == args.phase]
    complete, problems, attempts = {}, {}, []
    binding = outputs / "execution_binding.json"
    # Preserve the official Console basename even when it is a symlink.
    launcher = args.netlogo_headless.expanduser().absolute() if args.netlogo_headless else None
    fingerprint = info = None
    if args.execute or args.validate_only or binding.exists():
        if launcher is None:
            parser.error("--netlogo-headless is required to execute or validate/resume existing outputs")
        check_manifest_binding(root, manifest)
        fingerprint, info = fingerprints(root, launcher)
        acquire_lock(outputs)
        if binding.exists():
            existing = json.loads(binding.read_text())
            if existing["fingerprint"] != fingerprint:
                raise ValueError("Model/configuration/runner/runtime changed; use a NEW output directory. "
                                 "Existing raw results are preserved and will not be mixed.")
        elif args.validate_only:
            raise ValueError("No execution_binding.json in the output directory")
        elif args.execute:
            if outputs.exists() and any(p.name != ".runner.lock" for p in outputs.iterdir()):
                raise ValueError("Nonempty unbound output directory; choose a fresh directory")
            outputs.mkdir(parents=True, exist_ok=True)
            json_write(binding, {"created_at_utc": utc_now(), "fingerprint": fingerprint,
                                 "environment": info})
        if binding.exists():
            complete, problems, attempts = scan_attempts(outputs, manifest, conditions, parameters, fingerprint)
            write_status(outputs, manifest, complete, problems)
    pending = [(job, remaining_for_job(job, by_condition, complete)) for job in jobs]
    pending = [(job, rows) for job, rows in pending if rows]
    total_pending_batches = len(pending)
    total_pending_runs = sum(len(rows) for _, rows in pending)
    if args.limit_batches:
        pending = pending[:args.limit_batches]
    print(json.dumps({"mode": "validate_only" if args.validate_only else "execute" if args.execute else "dry_run",
                      "phase": args.phase, "already_validated_runs_all_phases": len(complete),
                      "pending_batches_selected_phase": total_pending_batches,
                      "pending_runs_selected_phase": total_pending_runs,
                      "this_invocation_batches": len(pending),
                      "this_invocation_runs": sum(len(rows) for _, rows in pending),
                      "jobs": [{"job_id": job["job_id"], "missing_runs": len(rows)} for job, rows in pending]}, indent=2))
    if not args.execute or args.validate_only:
        if args.validate_only:
            json_write(outputs / "validation_summary.json", {"checked_at_utc": utc_now(),
                       "valid_runs": len(complete), "total_manifest_runs": len(manifest), "attempts": attempts})
            return 0 if not total_pending_runs else 2
        return 0
    failed_batches = 0
    for job, missing in pending:
        attempt_id = f"{job['job_id']}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
        folder = outputs / "attempts" / attempt_id
        folder.mkdir(parents=True, exist_ok=False)
        grouped = defaultdict(list)
        for run in missing:
            grouped[int(run["condition_id"])].append(run)
        xml = folder / "missing_runs.xml"
        write_xml(xml, make_experiment(attempt_id, job["phase"],
                  [conditions[cid] for cid in sorted(grouped)], grouped, parameters))
        command = command_for(launcher, root / "model/ABM_revision_v2.0.nlogo", xml,
                              attempt_id, folder / "raw.csv", args.threads)
        metadata = {"schema": SCHEMA, "job_id": job["job_id"], "attempt_id": attempt_id,
                    "fingerprint": fingerprint, "environment": info,
                    "run_ids": [r["run_id"] for r in missing], "command": command,
                    "working_directory": str(launch_working_directory(launcher, root)),
                    "xml_sha256": sha256(xml), "started_at_utc": utc_now(),
                    "threads": args.threads, "returncode": None, "state": "running"}
        json_write(folder / "attempt.json", metadata)
        print(f"Running {job['job_id']}: {len(missing)} missing runs; raw output: {folder / 'raw.csv'}", flush=True)
        started = time.monotonic()
        interrupted = False
        with (folder / "netlogo.log").open("x", encoding="utf-8") as log:
            try:
                process = subprocess.Popen(command, cwd=launch_working_directory(launcher, root), stdout=log, stderr=subprocess.STDOUT,
                                           start_new_session=True)
                try:
                    returncode = process.wait()
                except KeyboardInterrupt:
                    interrupted = True
                    # A launcher can create Java children. Terminate the entire
                    # process group so raw.csv cannot change after validation.
                    import signal
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        returncode = process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        returncode = process.wait()
            except OSError as exc:
                log.write(f"Launcher error: {exc}\n")
                returncode = 127
        metadata.update(returncode=returncode, state="interrupted" if interrupted else "finished",
                        ended_at_utc=utc_now(), duration_seconds=round(time.monotonic() - started, 3),
                        raw_csv_sha256=sha256(folder / "raw.csv") if (folder / "raw.csv").is_file() else None)
        json_write(folder / "attempt.json", metadata)
        valid, invalid, file_issues = validate_table(folder / "raw.csv", missing, conditions, parameters)
        log_errors = bool(ERROR_PATTERN.search((folder / "netlogo.log").read_text(errors="replace")))
        problems.update(invalid)
        for rid, result in valid.items():
            complete[rid] = result | {"source_csv": str((folder / "raw.csv").relative_to(outputs)),
                                      "attempt": attempt_id}
        report = {"checked_at_utc": utc_now(), "valid_runs": len(valid),
                  "expected_runs": len(missing), "run_issues": invalid,
                  "file_issues": file_issues, "runtime_error_in_log": log_errors,
                  "returncode": returncode}
        json_write(folder / "validation.json", report)
        write_status(outputs, manifest, complete, problems)
        batch_ok = len(valid) == len(missing) and returncode == 0 and not log_errors and not file_issues
        failed_batches += not batch_ok
        print(f"Validated {len(valid)}/{len(missing)} runs; exit={returncode}; runtime_error={log_errors}", flush=True)
        if not batch_ok:
            print(f"Inspect {folder / 'validation.json'} and {folder / 'netlogo.log'}. "
                  "The next invocation retries only missing/invalid identities.", file=sys.stderr)
            # Do not repeat a shared configuration/runtime failure across 64 jobs.
            break
        if interrupted:
            break
    json_write(outputs / "execution_summary.json", {"updated_at_utc": utc_now(),
               "validated_runs_all_phases": len(complete), "total_manifest_runs": len(manifest),
               "failed_batches_this_invocation": failed_batches})
    return 1 if failed_batches else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
