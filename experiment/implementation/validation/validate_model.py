#!/usr/bin/env python3
"""Small, independent NetLogo validation. Never starts a formal experiment.

Usage: python validation/validate_model.py --netlogo /path/NetLogo_Console
NetLogo_Console uses bundled Java; netlogo-headless.sh remains supported.
Run outputs are isolated in validation/work/. No formal manifest row is consumed.
The optional --prepare-only writes diagnostic inputs but does not claim a pass.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
STATE = "(map [node -> (list [who] of node [polluted?] of node [wrongly-removed?] of node [super-spreader?] of node)] sort turtles)"
EDGES = "(map [edge -> (list [[who] of end1] of edge [[who] of end2] of edge)] sort links)"
COMMON = ["effectiveness", "over-removal-rate", "net-effectiveness", "current-pollution-rate",
          "pollution-count", "initial-polluted-count", "over-removal-count", "deleted-count",
          "false-deleted", "removal-precision", STATE, EDGES]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def launcher_command(launcher: Path) -> list[str]:
    """Console is an executable, whereas the legacy launcher is a bash script."""
    if launcher.name.lower() in {"netlogo_console", "netlogo_console.exe"}:
        return [str(launcher), "--headless"]
    return ["bash", str(launcher)]


def launch_working_directory(launcher: Path, root: Path) -> Path:
    """Mac Console resolves its app/config relative to the installation folder."""
    if launcher.name.lower() in {"netlogo_console", "netlogo_console.exe"}:
        return launcher.parent
    return root


def read_table(path: Path) -> list[dict[str, str]]:
    """Find the actual table header; never assume a fixed preamble length."""
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.reader(stream)
        first = next(reader, [])
        if not first or first[0] != "BehaviorSpace results (NetLogo 6.4.0)":
            raise AssertionError(f"Expected NetLogo 6.4.0 output: {path}")
        for row in reader:
            if row and row[0] == "[run number]":
                fields = row
                break
        else:
            raise AssertionError(f"BehaviorSpace table header missing: {path}")
        data = []
        for row in reader:
            if not row or all(not cell for cell in row):
                continue
            if len(row) != len(fields):
                raise AssertionError(f"Ragged table row in {path}: {len(row)}/{len(fields)}")
            data.append(dict(zip(fields, row)))
    if not data:
        raise AssertionError(f"Empty BehaviorSpace output: {path}")
    return data


def n(row: dict, key: str) -> float:
    return float(row[key])


def close(a: float, b: float) -> bool:
    return math.isclose(a, b, abs_tol=1e-10, rel_tol=1e-12)


def rounded(value: float) -> int:
    # The diagnostics use nonnegative values: NetLogo round uses upward half ties.
    return math.floor(value + 0.5)


def make_cases(defaults: dict) -> list[dict]:
    result = []

    def add(name: str, **overrides) -> None:
        params = defaults | {"num-nodes": 100, "p0": 30} | overrides
        case_id = len(result) + 1
        result.append({"id": case_id, "name": name, "seed": 610000 + case_id, "params": params})

    add("legacy_BA_legal_targeted", **{"treatment": "legal"})
    add("legacy_BA_legal_random", **{"treatment": "legal", "targeting-mode": "random"})
    add("legacy_ER_platform_targeted", **{"network-type": "ER", "treatment": "platform"})
    add("legacy_ER_platform_random", **{"network-type": "ER", "treatment": "platform", "targeting-mode": "random"})
    add("legacy_WS_none", **{"network-type": "WS", "treatment": "none"})
    add("legacy_WS_legal_random", **{"network-type": "WS", "treatment": "legal", "targeting-mode": "random"})
    add("all_allowed_zero_inputs", **{"p0": 0, "beta0": 0, "amplification": 0,
        "super-ratio": 0, "lambda-weight": 0, "ws-rewire-prob": 0})
    add("legal_all_clean_TNR0", **{"treatment": "legal", "p0": 0, "beta0": 0,
        "legal-strength": 100, "legal-tnr": 0})
    add("legal_all_polluted_TPR0", **{"treatment": "legal", "p0": 100, "beta0": 0,
        "legal-strength": 100, "legal-tpr": 0})
    add("legal_perfect_clearance_continues", **{"treatment": "legal", "p0": 100, "beta0": 0,
        "legal-strength": 100, "legal-tpr": 100, "legal-tnr": 100})
    add("platform_all_clean_TNR0", **{"treatment": "platform", "p0": 0, "beta0": 0,
        "platform-speed": 100, "platform-tnr": 0})
    add("platform_all_polluted_TPR0", **{"treatment": "platform", "p0": 100, "beta0": 0,
        "platform-speed": 100, "platform-tpr": 0, "platform-tnr": 0})
    add("platform_perfect_clearance_continues", **{"treatment": "platform", "p0": 100, "beta0": 0,
        "platform-speed": 100, "platform-tpr": 100, "platform-tnr": 100})
    add("no_positive_decisions_precision_NA", **{"treatment": "platform", "beta0": 0,
        "platform-speed": 100, "platform-tpr": 0, "platform-tnr": 100})
    add("legal_zero_coverage_tau20", **{"treatment": "legal", "p0": 100, "beta0": 0,
        "super-ratio": 0, "legal-strength": 0, "legal-response-time": 20})
    add("platform_zero_coverage", **{"treatment": "platform", "p0": 10, "beta0": 0,
        "super-ratio": 0, "platform-speed": 0})
    for kappa in (1, 2, 5):
        add(f"state_responsive_kappa{kappa}", **{"treatment": "platform", "p0": 10, "beta0": 0,
            "platform-workload-mode": "state-responsive", "demand-kappa": kappa,
            "platform-tpr": 0, "platform-tnr": 100})
    add("state_responsive_zero_pollution", **{"treatment": "platform", "p0": 0, "beta0": 1,
        "amplification": 0, "super-ratio": 0, "platform-workload-mode": "state-responsive", "demand-kappa": 5})
    add("state_responsive_post_spread_count", **{"treatment": "platform", "p0": 10, "beta0": 1,
        "amplification": 0, "network-type": "WS", "ws-rewire-prob": 0,
        "platform-workload-mode": "state-responsive", "demand-kappa": 1,
        "platform-speed": 60, "platform-tpr": 0, "platform-tnr": 100})
    add("state_responsive_zero_kappa", **{"treatment": "platform", "p0": 10, "beta0": 0,
        "platform-workload-mode": "state-responsive", "demand-kappa": 0})
    add("all_super_spreaders", **{"network-type": "ER", "num-nodes": 80, "super-ratio": 100,
        "beta0": 0, "amplification": 0})
    add("WS_rewire1_low_coverage", **{"network-type": "WS", "num-nodes": 80, "ws-rewire-prob": 1,
        "treatment": "platform", "p0": 50, "beta0": 0, "platform-speed": 5,
        "platform-tpr": 100, "platform-tnr": 0})
    add("legal_low_coverage_every_step", **{"num-nodes": 80, "treatment": "legal", "targeting-mode": "random",
        "p0": 50, "beta0": 0, "legal-strength": 5, "legal-response-time": 1,
        "legal-tpr": 100, "legal-tnr": 0})
    result.append({**result[0], "id": 26, "name": "exact_seed_repeat"})
    return result


def write_experiment(path: Path, name: str, cases: list[dict], metrics: list[str], every=True, legacy=False) -> None:
    root = ET.Element("experiments")
    exp = ET.SubElement(root, "experiment", name=name, repetitions="1", runMetricsEveryStep=str(every).lower())
    ET.SubElement(exp, "setup").text = "random-seed validation-seed\nsetup" if legacy else "setup"
    ET.SubElement(exp, "go").text = "go"
    ET.SubElement(exp, "exitCondition").text = "ticks >= max-ticks"
    for metric in metrics:
        ET.SubElement(exp, "metric").text = metric
    for case in cases:
        sub = ET.SubElement(exp, "subExperiment")
        params = case["params"].copy()
        if legacy:
            params["legal-accuracy"] = params.pop("legal-tpr")
            params["platform-accuracy"] = params.pop("platform-tpr")
            for key in ("legal-tnr", "platform-tnr", "platform-workload-mode", "demand-kappa"):
                params.pop(key)
            params |= {"validation-case-id": case["id"], "validation-seed": case["seed"]}
        else:
            params |= {"condition-id": 0, "replicate-id": case["id"], "run-seed": case["seed"]}
        for key, value in params.items():
            values = ET.SubElement(sub, "enumeratedValueSet", variable=key)
            ET.SubElement(values, "value", value=json.dumps(value))
    ET.indent(root, space="  ")
    path.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE experiments SYSTEM "behaviorspace.dtd">\n' +
                    ET.tostring(root, encoding="unicode") + "\n", encoding="utf-8")


def write_invalid(path: Path) -> None:
    root = ET.Element("experiments")
    exp = ET.SubElement(root, "experiment", name="invalid_inputs", repetitions="1", runMetricsEveryStep="false")
    ET.SubElement(exp, "setup").text = '''let case-id replicate-id
set-defaults
set replicate-id case-id
set num-nodes 80
if case-id = 1 [set legal-response-time 0]
if case-id = 2 [set platform-speed 101]
if case-id = 3 [set targeting-mode "default"]
if case-id = 4 [set demand-kappa -1]
if case-id = 5 [set legal-tpr 101]
let rejected? false
carefully [setup] [set rejected? true set network-type error-message]
if not rejected? [error "Invalid input was unexpectedly accepted."]
reset-ticks'''
    ET.SubElement(exp, "go").text = "tick"
    ET.SubElement(exp, "timeLimit", steps="1")
    ET.SubElement(exp, "metric").text = "network-type"
    values = ET.SubElement(exp, "enumeratedValueSet", variable="replicate-id")
    for case_id in range(1, 6):
        ET.SubElement(values, "value", value=str(case_id))
    ET.indent(root, space="  ")
    path.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE experiments SYSTEM "behaviorspace.dtd">\n' +
                    ET.tostring(root, encoding="unicode") + "\n", encoding="utf-8")


def prepare(root: Path) -> tuple[list[dict], list[str], Path]:
    work = root / "validation/work"
    work.mkdir(parents=True, exist_ok=True)
    protocol = json.loads((root / "protocol/ABM_step1_protocol.json").read_text())
    cases = make_cases({p["name"]: p["default"] for p in protocol["model_parameters"]})
    spec = importlib.util.spec_from_file_location("abm_build_jobs", root / "scripts/build_jobs.py")
    jobs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(jobs)
    metrics = list(dict.fromkeys(jobs.METRICS + COMMON))
    write_experiment(work / "diagnostics.xml", "diagnostics", cases, metrics)
    write_experiment(work / "minimal_metrics.xml", "minimal_metrics", cases[:3], COMMON)
    write_experiment(work / "end_only.xml", "end_only", cases[:3], metrics, every=False)
    write_experiment(work / "legacy.xml", "legacy", cases[:6], COMMON, legacy=True)
    write_invalid(work / "invalid_inputs.xml")
    source = root / "validation/fixtures/legacy_v1.8.nls"
    template = (root / "model/ABM_revision_v2.0.nlogo").read_text()
    sections = template.split("@#$#@#$#@")
    # Original executable statements are preserved; only two diagnostic identity globals are added.
    sections[0] = source.read_text().replace("globals [", "globals [\n  validation-case-id validation-seed", 1) + "\n"
    sections[7] = "\n<experiments/>\n"
    (work / "legacy_wrapper.nlogo").write_text("@#$#@#$#@".join(sections), encoding="utf-8")
    (work / "diagnostic_cases.json").write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n")
    return cases, metrics, work


def grouped(rows: list[dict], identity="replicate-id") -> dict[int, list[dict]]:
    result = {}
    for row in rows:
        result.setdefault(int(float(row[identity])), []).append(row)
    for series in result.values():
        series.sort(key=lambda row: n(row, "[step]"))
    return result


def check_trajectory(case: dict, rows: list[dict]) -> dict:
    p, label = case["params"], case["name"]
    assert [n(row, "[step]") for row in rows] == list(range(51)), f"{label}: incomplete 0..50 steps"
    N = p["num-nodes"]
    initial = rounded(N * p["p0"] / 100)
    assert n(rows[0], "pollution-count") == initial, f"{label}: initial pollution"
    assert n(rows[0], "count-super-spreaders") == rounded(N * p["super-ratio"] / 100), f"{label}: superspreaders"
    assert n(rows[0], "observation-count") == 0
    assert rows[0]["mean-effectiveness"] == "NA"
    assert n(rows[0], "step-reviews") == 0
    assert n(rows[0], "cumulative-reviews") == 0
    for i, row in enumerate(rows):
        assert n(row, "network-node-count") == N
        assert row[EDGES] == rows[0][EDGES], f"{label}: changing network"
        assert close(n(row, "mean-degree"), 2 * n(row, "network-edge-count") / N)
        if p["network-type"] == "WS":
            assert n(row, "network-edge-count") == N * p["ba-m"]
        if p["network-type"] == "BA":
            # The NW generator starts with a clique of m+1 nodes.
            m = p["ba-m"]
            assert n(row, "network-edge-count") == m * N - m * (m + 1) / 2
        assert 0 <= n(row, "over-removal-rate") <= 100
        assert close(n(row, "effectiveness"), 100 - 100 * n(row, "pollution-count") / N)
        assert close(n(row, "over-removal-rate"), 100 * n(row, "count-wrongly-removed") / N)
        assert close(n(row, "net-effectiveness"), n(row, "effectiveness") - p["lambda-weight"] * n(row, "over-removal-rate"))
        assert n(row, "step-reviews") == sum(n(row, f"step-{outcome}") for outcome in ("tp", "fp", "tn", "fn"))
        assert n(row, "cumulative-reviews") == sum(n(row, f"cumulative-{outcome}") for outcome in ("tp", "fp", "tn", "fn"))
        assert n(row, "step-clean-reviews") == n(row, "step-fp") + n(row, "step-tn")
        assert n(row, "cumulative-clean-reviews") == n(row, "cumulative-fp") + n(row, "cumulative-tn")
        positive = n(row, "cumulative-tp") + n(row, "cumulative-fp")
        if positive == 0:
            assert row["removal-precision"] == "NA" and row["precision-defined?"] == "false"
        else:
            assert row["precision-defined?"] == "true"
            assert close(n(row, "removal-precision"), 100 * n(row, "cumulative-tp") / positive)
        if not i:
            continue
        prev = rows[i - 1]
        assert n(row, "observation-count") == i
        assert n(row, "count-wrongly-removed") >= n(prev, "count-wrongly-removed")
        for suffix in ("reviews", "tp", "fp", "tn", "fn"):
            assert n(row, f"cumulative-{suffix}") == n(prev, f"cumulative-{suffix}") + n(row, f"step-{suffix}")
        assert n(row, "pollution-count") == n(row, "polluted-pre-review") - n(row, "step-tp")
        assert n(row, "polluted-pre-review") >= n(prev, "pollution-count")
        if p["beta0"] == 0:
            assert n(row, "polluted-pre-review") == n(prev, "pollution-count")
        if p["treatment"] == "none":
            expected = 0
        elif p["treatment"] == "legal":
            expected = rounded(N * p["legal-strength"] / 100) if (i - 1) % p["legal-response-time"] == 0 else 0
        else:
            expected = rounded(N * p["platform-speed"] / 100)
            if p["platform-workload-mode"] == "state-responsive":
                expected = min(N, expected, rounded(p["demand-kappa"] * n(row, "polluted-pre-review")))
        assert n(row, "step-reviews") == expected, f"{label} step {i}: workload {row['step-reviews']}/{expected}"
        expected_opportunities = (i - 1) // p["legal-response-time"] + 1 if p["treatment"] == "legal" else 0
        assert n(row, "legal-action-opportunities") == expected_opportunities
        if p["treatment"] in ("legal", "platform"):
            prefix = p["treatment"]
            if p[f"{prefix}-tpr"] == 0:
                assert n(row, "step-tp") == 0
            if p[f"{prefix}-tpr"] == 100:
                assert n(row, "step-fn") == 0
            if p[f"{prefix}-tnr"] == 100:
                assert n(row, "step-fp") == 0
            if p[f"{prefix}-tnr"] == 0:
                assert n(row, "step-tn") == 0
        assert close(n(row, "mean-effectiveness"), sum(n(r, "effectiveness") for r in rows[1:i + 1]) / i)
        assert close(n(row, "mean-net-effectiveness"), sum(n(r, "net-effectiveness") for r in rows[1:i + 1]) / i)
    if "perfect_clearance" in label:
        assert all(n(row, "pollution-count") == 0 for row in rows[1:])
    if label == "state_responsive_post_spread_count":
        assert n(rows[1], "polluted-pre-review") > initial, "P3 fixture failed to witness diffusion before workload"
        assert n(rows[1], "step-reviews") > initial, "P3 used a stale pollution count"
    if label in ("legal_all_clean_TNR0", "platform_all_clean_TNR0"):
        assert n(rows[1], "over-removal-rate") == 100
    return {"case_id": case["id"], "name": label, "status": "passed", "steps": 50}


def compare_rows(a: list[dict], b: list[dict], columns: list[str], label: str, legacy=False) -> None:
    assert len(a) == len(b), f"{label}: row counts differ"
    for left, right in zip(a, b):
        assert left["[step]"] == right["[step]"], f"{label}: steps differ"
        for column in columns:
            if legacy and column == "removal-precision" and left[column] == "NA":
                assert float(right[column]) == 0
                continue
            assert left[column] == right[column], f"{label} step {left['[step]']}: {column} differs"


def inspect(root: Path, cases: list[dict], metrics: list[str], work: Path) -> dict:
    main = grouped(read_table(work / "diagnostics.csv"))
    assert set(main) == {case["id"] for case in cases}, "Missing or extra diagnostic run"
    checks = [check_trajectory(case, main[case["id"]]) for case in cases]
    compare_rows(main[1], main[26], metrics, "exact seed repeat")
    minimum = grouped(read_table(work / "minimal_metrics.csv"))
    final = grouped(read_table(work / "end_only.csv"))
    for case in cases[:3]:
        cid = case["id"]
        compare_rows(main[cid], minimum[cid], COMMON, f"extra diagnostics neutrality case {cid}")
        compare_rows(main[cid][-1:], final[cid], metrics, f"end-only neutrality case {cid}")
    legacy = grouped(read_table(work / "legacy.csv"), "validation-case-id")
    for case in cases[:6]:
        compare_rows(main[case["id"]], legacy[case["id"]], COMMON,
                     f"v1.8 stepwise compatibility case {case['id']}", legacy=True)
    invalid = read_table(work / "invalid_inputs.csv")
    assert len(invalid) == 5
    expected = {1: "legal-response-time", 2: "platform-speed", 3: "targeting-mode", 4: "demand-kappa", 5: "legal-tpr"}
    for row in invalid:
        cid = int(float(row["replicate-id"]))
        assert expected[cid] in row["network-type"], f"Invalid case {cid}: wrong error message"
    return {"status": "passed", "valid_diagnostic_runs": 38, "invalid_input_checks": 5,
            "full_trajectory_runs": 35, "end_only_runs": 3,
            "main_cases": checks, "same_seed_repeat": "passed",
            "additional_reporters_rng_neutrality": {"status": "passed", "runs": 3},
            "end_only_rng_neutrality": {"status": "passed", "runs": 3},
            "legacy_stepwise_compatibility": {"status": "passed", "runs": 6,
                "comparison": "51 states, full account states, network edges and shared outputs per run",
                "intentional_difference": "undefined precision is NA in v2.0 versus 0 in v1.8"},
            "formal_runs_executed": 0, "formal_results_claimed": False,
            "limitations": ["Small deterministic diagnostics are not substantive experimental findings.",
                            "Legacy comparisons use newly simulated seeds; historical seeds are not reconstructed.",
                            "No full 95,850-run experiment is started by this validation script."]}


def report(root: Path, result: dict) -> None:
    path = root / "validation/model_validation.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--netlogo", type=Path,
                        help="Path to NetLogo 6.4.0 NetLogo_Console or netlogo-headless.sh")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--inspect-existing", action="store_true")
    parser.add_argument("--timeout", type=int, default=300, help="Maximum seconds per small diagnostic batch")
    args = parser.parse_args()
    root = args.root.resolve()
    started = time.time()
    result = {"schema": "ABM-model-diagnostic-validation-v1", "status": "prepared_not_run",
              "model_sha256": sha256(root / "model/exp_code_v2.0.nls"),
              "model_wrapper_sha256": sha256(root / "model/ABM_revision_v2.0.nlogo"),
              "validation_script_sha256": sha256(Path(__file__)),
              "legacy_fixture_sha256": sha256(root / "validation/fixtures/legacy_v1.8.nls"),
              "formal_runs_executed": 0}
    try:
        cases, metrics, work = prepare(root)
        if args.prepare_only:
            report(root, result)
            print(json.dumps(result, indent=2))
            return 0
        stamps_path = work / "execution_provenance.json"
        stamp_keys = ("model_sha256", "model_wrapper_sha256", "legacy_fixture_sha256")
        if args.inspect_existing:
            if not stamps_path.exists():
                raise RuntimeError("Existing outputs have no execution provenance; run NetLogo again.")
            stamps = json.loads(stamps_path.read_text())
            if any(stamps.get(key) != result[key] for key in stamp_keys):
                raise RuntimeError("Existing outputs were generated from different model/fixture sources.")
            for name, stamp in stamps["batches"].items():
                if stamp["xml_sha256"] != sha256(work / f"{name}.xml") or stamp["csv_sha256"] != sha256(work / f"{name}.csv"):
                    raise RuntimeError(f"Existing {name} input/output hashes differ from execution provenance.")
        else:
            if args.netlogo is None:
                raise ValueError("Supply --netlogo /path/NetLogo_Console (or netlogo-headless.sh), or --prepare-only.")
            # Preserve the public launcher name when it is a symlink.
            launcher = args.netlogo.expanduser().absolute()
            if not launcher.is_file():
                raise ValueError(f"NetLogo launcher missing: {launcher}")
            result["runtime_launcher"] = str(launcher)
            result["runtime_launcher_sha256"] = sha256(launcher)
            launch_cwd = launch_working_directory(launcher, root)
            result["runtime_working_directory"] = str(launch_cwd)
            stamps = {key: result[key] for key in stamp_keys} | {"batches": {}}
            for name in ("diagnostics", "minimal_metrics", "end_only", "legacy", "invalid_inputs"):
                model = work / "legacy_wrapper.nlogo" if name == "legacy" else root / "model/ABM_revision_v2.0.nlogo"
                output = work / f"{name}.csv"
                if output.exists():
                    output.unlink()
                command = launcher_command(launcher) + ["--model", str(model), "--setup-file", str(work / f"{name}.xml"),
                           "--experiment", name, "--table", str(output), "--threads", "1"]
                print(f"Running isolated diagnostic batch: {name}", flush=True)
                with (work / f"{name}.log").open("w") as log:
                    completed = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                                               timeout=args.timeout, cwd=launch_cwd)
                if completed.returncode:
                    result["runtime_log_tail"] = (work / f"{name}.log").read_text(
                        encoding="utf-8", errors="replace")[-3000:]
                    raise RuntimeError(f"{name}: NetLogo exit {completed.returncode}; see validation/work/{name}.log")
                read_table(output)
                stamps["batches"][name] = {"xml_sha256": sha256(work / f"{name}.xml"), "csv_sha256": sha256(output)}
            stamps_path.write_text(json.dumps(stamps, indent=2) + "\n")
        result |= inspect(root, cases, metrics, work)
        if result["model_sha256"] != sha256(root / "model/exp_code_v2.0.nls"):
            raise RuntimeError("Model source changed during validation; rerun after source freeze.")
        if result["model_wrapper_sha256"] != sha256(root / "model/ABM_revision_v2.0.nlogo"):
            raise RuntimeError("Model wrapper changed during validation; rerun after source freeze.")
    except Exception as exc:
        result["status"] = "failed"
        result["error"] = f"{type(exc).__name__}: {exc}"
    result["elapsed_seconds"] = round(time.time() - started, 3)
    report(root, result)
    print(json.dumps({k: v for k, v in result.items() if k != "main_cases"}, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
