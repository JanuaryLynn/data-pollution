#!/usr/bin/env python3
"""Build row-bound NetLogo 6.4 BehaviorSpace jobs from the frozen manifest.

Only Python's standard library is needed.  Each subExperiment is one complete
condition; replicate-id is its sole varying input.  This prevents accidental
Cartesian expansion of Latin-hypercube columns or symmetric TPR/TNR inputs.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
MODEL_VERSION = "v2.0-design-v1.0"
METRICS = [
    "run-seed", "model-version", "effectiveness", "over-removal-rate",
    "net-effectiveness", "removal-precision", "precision-defined?",
    "mean-effectiveness", "mean-net-effectiveness", "observation-count",
    "current-pollution-rate", "count-wrongly-removed", "initial-polluted-count", "pollution-count",
    "polluted-pre-review", "step-reviews", "step-tp", "step-fp", "step-tn",
    "step-fn", "cumulative-reviews", "cumulative-tp", "cumulative-fp",
    "cumulative-tn", "cumulative-fn", "step-clean-reviews", "cumulative-clean-reviews",
    "actual-review-coverage", "legal-action-opportunities", "active-review-steps",
    "network-node-count", "network-edge-count", "mean-degree", "max-degree",
    "degree-sd", "count-isolates", "mean-super-degree", "mean-ordinary-degree",
    "count-super-spreaders", "legal-load", "audit-load",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def read_design(root: Path):
    protocol = json.loads((root / "protocol/ABM_step1_protocol.json").read_text())
    parameters = protocol["model_parameters"]
    conditions = read_csv(root / "design/conditions.csv")
    manifest = read_csv(root / "design/run_manifest.csv")
    by_condition = {int(row["condition_id"]): row for row in conditions}
    if len(by_condition) != len(conditions):
        raise ValueError("Duplicate condition_id in conditions.csv")
    seen = set()
    grouped = {}
    for row in manifest:
        cid, rep = int(row["condition_id"]), int(row["replicate_id"])
        if (cid, rep) in seen:
            raise ValueError(f"Duplicate manifest identity: {cid}/{rep}")
        seen.add((cid, rep))
        if cid not in by_condition:
            raise ValueError(f"Manifest references unknown condition {cid}")
        seed = int(row.get("seed", row.get("run_seed", "")))
        if seed != 20260922 + 1000 * cid + rep:
            raise ValueError(f"Seed mismatch: {cid}/{rep}")
        grouped.setdefault(cid, []).append(row)
    if set(grouped) != set(by_condition):
        raise ValueError("Not every condition has manifest runs")
    for cid, rows in grouped.items():
        if sorted(int(r["replicate_id"]) for r in rows) != list(range(1, 31)):
            raise ValueError(f"Condition {cid} does not have replicates 1..30")
    return protocol, parameters, by_condition, manifest, grouped


def phase_of(row: dict[str, str]) -> str:
    explicit = row.get("phase", "").lower()
    if explicit in ("grid", "p4"):
        return explicit
    mode = row.get("output_mode", "").lower()
    if mode in ("trajectory", "full", "full-trajectory", "full_trajectory"):
        return "grid"
    if mode in ("end-only", "end_only", "endonly", "summary", "final"):
        return "p4"
    raise ValueError(f"Unknown phase/output mode: {row}")


def literal(value: str, parameter: dict) -> str:
    if parameter["type"] == "enum":
        return json.dumps(value, ensure_ascii=True)
    # CSVs preserve full-precision decimal strings; do not round LHS inputs.
    return value


def make_experiment(name: str, phase: str, condition_rows: list[dict[str, str]],
                    runs_by_condition: dict[int, list[dict[str, str]]],
                    parameters: list[dict]) -> ET.Element:
    experiment = ET.Element("experiment", {
        "name": name, "repetitions": "1",
        "runMetricsEveryStep": "true" if phase == "grid" else "false",
    })
    ET.SubElement(experiment, "setup").text = (
        "set run-seed (20260922 + 1000 * condition-id + replicate-id)\nsetup"
    )
    ET.SubElement(experiment, "go").text = "go"
    ET.SubElement(experiment, "exitCondition").text = "ticks >= max-ticks"
    for metric in METRICS:
        ET.SubElement(experiment, "metric").text = metric
    for row in condition_rows:
        cid = int(row["condition_id"])
        sub = ET.SubElement(experiment, "subExperiment")
        for parameter in parameters:
            item = ET.SubElement(sub, "enumeratedValueSet", {"variable": parameter["name"]})
            ET.SubElement(item, "value", {"value": literal(row[parameter["name"]], parameter)})
        item = ET.SubElement(sub, "enumeratedValueSet", {"variable": "condition-id"})
        ET.SubElement(item, "value", {"value": str(cid)})
        item = ET.SubElement(sub, "enumeratedValueSet", {"variable": "replicate-id"})
        for run in sorted(runs_by_condition[cid], key=lambda r: int(r["replicate_id"])):
            ET.SubElement(item, "value", {"value": run["replicate_id"]})
    return experiment


def write_xml(path: Path, experiment: ET.Element) -> None:
    root = ET.Element("experiments")
    root.append(experiment)
    ET.indent(root, space="  ")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE experiments SYSTEM "behaviorspace.dtd">\n'
    text += ET.tostring(root, encoding="unicode") + "\n"
    path.write_text(text, encoding="utf-8")


def build(root: Path, batch_size: int = 50) -> dict:
    if not 1 <= batch_size <= 50:
        raise ValueError("batch_size must be 1..50 conditions")
    if (root / "outputs/execution_binding.json").exists():
        raise ValueError("Execution has begun in this package; preserve the frozen jobs. "
                         "Use a separate versioned package for changed jobs.")
    protocol, parameters, conditions, manifest, grouped = read_design(root)
    if len(parameters) != 21 or len(conditions) != 3195 or len(manifest) != 95850:
        raise ValueError("Counts disagree with frozen design: expected 21/3195/95850")
    jobs_dir = root / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    existing = list(jobs_dir.glob("*.xml"))
    index = []
    assigned = set()
    for phase in ("grid", "p4"):
        ids = sorted(cid for cid in conditions if phase_of(grouped[cid][0]) == phase)
        for offset in range(0, len(ids), batch_size):
            chunk = ids[offset:offset + batch_size]
            job_id = f"{phase}_{offset // batch_size + 1:03d}"
            rows = [conditions[cid] for cid in chunk]
            for cid in chunk:
                if any(phase_of(r) != phase for r in grouped[cid]):
                    raise ValueError(f"Mixed output modes for condition {cid}")
                assigned.add(cid)
            path = jobs_dir / f"{job_id}.xml"
            write_xml(path, make_experiment(job_id, phase, rows, grouped, parameters))
            n_runs = sum(len(grouped[cid]) for cid in chunk)
            index.append({
                "job_id": job_id, "phase": phase,
                "output_mode": "trajectory" if phase == "grid" else "final",
                "xml_path": f"jobs/{job_id}.xml", "experiment_name": job_id,
                "condition_ids": ";".join(map(str, chunk)),
                "condition_count": len(chunk), "run_count": n_runs,
                "expected_data_rows": n_runs * (51 if phase == "grid" else 1),
                "xml_sha256": sha256(path),
            })
    if assigned != set(conditions):
        raise ValueError("Job coverage incomplete")
    expected_paths = {root / row["xml_path"] for row in index}
    stale = [p for p in existing if p not in expected_paths]
    if stale:
        raise ValueError(f"Unexpected stale job XMLs; move them before rebuilding: {stale}")
    with (jobs_dir / "job_index.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(index[0]))
        writer.writeheader()
        writer.writerows(index)
    summary = {
        "schema": "ABM-row-bound-jobs-v1", "model_version": MODEL_VERSION,
        "design_version": protocol["version"], "conditions": len(conditions),
        "runs": len(manifest), "jobs": len(index), "maximum_conditions_per_job": batch_size,
        "grid_jobs": sum(r["phase"] == "grid" for r in index),
        "p4_jobs": sum(r["phase"] == "p4" for r in index),
        "expected_data_rows": sum(r["expected_data_rows"] for r in index),
        "conditions_sha256": sha256(root / "design/conditions.csv"),
        "run_manifest_sha256": sha256(root / "design/run_manifest.csv"),
        "job_index_sha256": sha256(jobs_dir / "job_index.csv"),
        "metrics": METRICS,
    }
    (jobs_dir / "jobs_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--batch-size", type=int, default=50)
    args = parser.parse_args()
    print(json.dumps(build(args.root.resolve(), args.batch_size), indent=2))


if __name__ == "__main__":
    main()
