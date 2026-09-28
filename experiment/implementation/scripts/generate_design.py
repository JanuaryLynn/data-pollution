#!/usr/bin/env python3
"""Generate the frozen ABM design and planned-run manifest without running NetLogo.

First generation: python scripts/generate_design.py --new-design
Reproduction:     python scripts/generate_design.py

Archived LHS CSVs are authoritative. Existing archives are validated and reused;
they are never silently resampled. A manifest with any non-planned status is never
overwritten. To start a genuinely new design, use --new-design --output NEW_DIR.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
import platform
import tempfile
from collections import Counter
from pathlib import Path

import numpy as np
import scipy
from scipy.stats import qmc

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_VERSION = "v2.0-design-v1.0"
GENERATOR_VERSION = "1.0.0"
COUNTER_METRICS = {"cumulative_reviews", "clean_review_exposure"}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(config):
    values = {k: (int(v) if isinstance(v, float) and v.is_integer() else v)
              for k, v in config.items()}
    return json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def config_hash(config):
    return hashlib.sha256(canonical(config).encode()).hexdigest()


def dump_json(path, obj):
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
            temp_path = Path(stream.name)
            stream.write(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
        temp_path.replace(path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def write_csv(path, fields, rows):
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=path.parent,
                                         prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
            temp_path = Path(stream.name)
            writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n", extrasaction="raise")
            writer.writeheader()
            writer.writerows(rows)
        temp_path.replace(path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def validate_config(config, spec):
    assert set(config) == {p["name"] for p in spec["model_parameters"]}
    for param in spec["model_parameters"]:
        value = config[param["name"]]
        if param["type"] == "enum":
            assert value in param["values"], (param["name"], value)
        else:
            assert isinstance(value, (int, float)) and not isinstance(value, bool)
            assert math.isfinite(value)
            if param["type"] == "integer":
                assert value == int(value)
            assert value >= param.get("minimum", -math.inf)
            assert value <= param.get("maximum", math.inf)
    assert 2 * config["ba-m"] < config["num-nodes"]
    assert config["beta0"] * (1 + config["amplification"]) <= 1
    if config["platform-workload-mode"] == "fixed":
        assert config["demand-kappa"] == 1


def prepare_lhs(output, spec, protocol_hash, new_design):
    """Read archival matrices or explicitly create both using pinned RNG semantics."""
    p4 = spec["design"]["P4"]
    paths = [output / "lhs_legal.csv", output / "lhs_platform.csv", output / "lhs_metadata.json"]
    present = [p.exists() for p in paths]
    if any(present) and not all(present):
        raise RuntimeError("Incomplete LHS archive: restore all three archive files; do not silently resample.")
    if not all(present):
        if not new_design:
            raise RuntimeError("No archived LHS matrices. Use --new-design for the first explicit generation.")
        meta = {"protocol_sha256": protocol_hash, "generator_version": GENERATOR_VERSION,
                "python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__,
                "sampler": "scipy.stats.qmc.LatinHypercube", "scramble": True, "strength": 1,
                "optimization": None, "rng_argument": "rng=numpy.random.default_rng(seed)",
                "matrix_status": "archived_authoritative_input", "actors": {}}
        for actor in ("legal", "platform"):
            actor_spec = p4[actor]
            names = actor_spec["column_order"]
            sample = qmc.LatinHypercube(d=len(names), scramble=True, strength=1,
                                       optimization=None, rng=np.random.default_rng(actor_spec["seed"]))
            unit = sample.random(p4["points_per_actor"])
            rows = []
            for i, u in enumerate(unit, 1):
                row = {"lhs_point_id": i}
                row.update({"unit_" + name.replace("-", "_"): float(x) for name, x in zip(names, u)})
                for name, bounds, x in zip(names, actor_spec["bounds"], u):
                    row[name] = (1 + math.floor(20 * float(x)) if name == "legal-response-time"
                                 else bounds[0] + (bounds[1] - bounds[0]) * float(x))
                coverage_name = "legal-strength" if actor == "legal" else "platform-speed"
                # NetLogo round on nonnegative counts is half up, unlike Python round.
                row["review_capacity_at_N1000"] = math.floor(1000 * row[coverage_name] / 100 + 0.5)
                rows.append(row)
            path = output / f"lhs_{actor}.csv"
            write_csv(path, list(rows[0]), rows)
            meta["actors"][actor] = {"seed": actor_spec["seed"], "columns": names,
                                      "points": len(rows), "sha256": sha256(path)}
        dump_json(paths[2], meta)
    meta = json.loads(paths[2].read_text(encoding="utf-8"))
    assert meta["protocol_sha256"] == protocol_hash, "Protocol changed: use a separately versioned design directory."
    result = {}
    checks = {}
    for actor in ("legal", "platform"):
        actor_spec = p4[actor]
        path = output / f"lhs_{actor}.csv"
        assert sha256(path) == meta["actors"][actor]["sha256"], "Archived LHS file hash changed."
        raw = read_csv(path)
        n = p4["points_per_actor"]
        assert len(raw) == n
        assert [int(row["lhs_point_id"]) for row in raw] == list(range(1, n + 1))
        for name in actor_spec["column_order"]:
            unit_name = "unit_" + name.replace("-", "_")
            u = [float(row[unit_name]) for row in raw]
            assert all(0 <= v < 1 for v in u)
            assert sorted(math.floor(n * v) for v in u) == list(range(n)), (actor, name, "not LHS")
        typed = []
        for row in raw:
            values = {"lhs_point_id": int(row["lhs_point_id"])}
            for name, bounds in zip(actor_spec["column_order"], actor_spec["bounds"]):
                u = float(row["unit_" + name.replace("-", "_")])
                expected = 1 + math.floor(20 * u) if name == "legal-response-time" else bounds[0] + (bounds[1] - bounds[0]) * u
                actual = int(row[name]) if name == "legal-response-time" else float(row[name])
                assert actual == expected, (actor, name, actual, expected)
                values[name] = actual
            cov = values["legal-strength" if actor == "legal" else "platform-speed"]
            assert int(row["review_capacity_at_N1000"]) == math.floor(1000 * cov / 100 + 0.5)
            typed.append(values)
        assert len({canonical({key: value for key, value in row.items() if key != "lhs_point_id"})
                    for row in typed}) == n
        checks[actor] = {"points": n, "every_unit_column_has_one_point_per_stratum": True,
                         "actual_values_match_unit_mapping": True, "archive_hash_verified": True}
        if actor == "legal":
            tau_counts = Counter(row["legal-response-time"] for row in typed)
            assert tau_counts == {i: 25 for i in range(1, 21)}
            checks[actor]["tau_counts"] = dict(sorted(tau_counts.items()))
        result[actor] = typed
    return result, meta, checks


class Design:
    def __init__(self, spec):
        self.spec = spec
        self.params = [p["name"] for p in spec["model_parameters"]]
        self.defaults = {p["name"]: p["default"] for p in spec["model_parameters"]}
        self.conditions = []
        self.by_hash = {}
        self.groups = []
        self.module_counts = []
        self.comparisons = []

    def cell(self, actor, p0, overrides=None):
        return {**self.defaults, "treatment": actor, "p0": p0, **(overrides or {})}

    def add(self, config, module, role="experimental", actor="", point=""):
        validate_config(config, self.spec)
        digest = config_hash(config)
        is_new = digest not in self.by_hash
        if is_new:
            row = {"condition_id": len(self.conditions) + 1, "configuration_hash": digest,
                   "design_family": "P4" if module.startswith("P4_") else "grid",
                   "primary_module": module, "sensitivity_actor": actor, "lhs_point_id": point,
                   "output_mode": "final" if module.startswith("P4_") else "trajectory",
                   "expected_rows_per_run": 1 if module.startswith("P4_") else config["max-ticks"] + 1,
                   **config}
            self.conditions.append(row)
            self.by_hash[digest] = row
        row = self.by_hash[digest]
        self.groups.append({"module": module, "condition_id": row["condition_id"], "role": role,
                            "new_in_module": str(is_new).lower(), "sensitivity_actor": actor,
                            "lhs_point_id": point})
        return row["condition_id"]

    def resolve(self, actor, p0, overrides=None):
        digest = config_hash(self.cell(actor, p0, overrides))
        assert digest in self.by_hash, (actor, p0, overrides, "condition absent")
        return self.by_hash[digest]["condition_id"]

    def expand_grid(self):
        actors = {"none_legal_platform": ("none", "legal", "platform"),
                  "legal_and_platform": ("legal", "platform")}
        for block in self.spec["design"]["grid_blocks"]:
            before = len(self.conditions)
            module = block["module"]
            block_actors = actors.get(block["treatment"], (block["treatment"],))
            axes = list(block["axes"].items())
            symmetric_axes = list(block["symmetric_accuracy_axes"].items())
            for p0 in self.spec["design"]["common_p0"]:
                for actor in block_actors:
                    all_axes = [values for _, values in axes + symmetric_axes]
                    for combination in itertools.product(*all_axes):
                        config = self.cell(actor, p0, block["fixed_overrides"])
                        for (name, _), value in zip(axes, combination[:len(axes)]):
                            key = ("legal-strength" if actor == "legal" else "platform-speed") if name == "active_actor_coverage" else name
                            config[key] = value
                        for (symmetric_actor, _), value in zip(symmetric_axes, combination[len(axes):]):
                            config[symmetric_actor + "-tpr"] = value
                            config[symmetric_actor + "-tnr"] = value
                        role = "experimental"
                        if module == "P1_topology" and config["network-type"] == "BA":
                            role = "BA_reference"
                        if module == "scale" and config["num-nodes"] == 1000:
                            role = "N1000_reference"
                        if module.startswith("P6_") and config[actor + "-tpr"] == config[actor + "-tnr"]:
                            role = "symmetric_accuracy_reference"
                        self.add(config, module, role)
            new = len(self.conditions) - before
            assert new == block["new_conditions_after_prior_deduplication"], (module, new)
            self.module_counts.append({"module": module, "new_conditions": new,
                                       "members": sum(g["module"] == module for g in self.groups)})
        assert len(self.conditions) == self.spec["design"]["grid_conditions"]
        # Explicit shared controls: one set of runs per complete configuration.
        for p0 in self.spec["design"]["common_p0"]:
            self.add(self.cell("platform", p0), "P3", "fixed_workload_control")
            for actor in ("legal", "platform"):
                for target in ("targeted", "random"):
                    self.add(self.cell(actor, p0, {"targeting-mode": target}), "P5", "high_coverage_reference")
        assert len(self.conditions) == self.spec["design"]["grid_conditions"]

    def expand_lhs(self, lhs):
        for actor in ("legal", "platform"):
            before = len(self.conditions)
            for p0 in self.spec["design"]["common_p0"]:
                for values in lhs[actor]:
                    overrides = {key: value for key, value in values.items()
                                 if key not in {"lhs_point_id", "alpha_legal", "alpha_platform"}}
                    accuracy = values["alpha_" + actor]
                    overrides.update({actor + "-tpr": accuracy, actor + "-tnr": accuracy})
                    self.add(self.cell(actor, p0, overrides), "P4_" + actor,
                             "sensitivity_design_point", actor, values["lhs_point_id"])
            new = len(self.conditions) - before
            assert new == 1500
            self.module_counts.append({"module": "P4_" + actor, "new_conditions": new, "members": new})

    def contrast(self, cid, family, actor, p0, outcomes, terms, expected="unspecified", path="", primary=False):
        resolved = [(weight, self.resolve(actor, p0, overrides)) for weight, overrides in terms]
        assert sum(weight for weight, _ in resolved) == 0
        assert len({condition for _, condition in resolved}) == len(resolved)
        for metric in outcomes:
            for term, (weight, condition) in enumerate(resolved, 1):
                self.comparisons.append({"comparison_id": cid, "family": family, "actor": actor, "p0": p0,
                    "outcome": metric, "term_index": term, "condition_id": condition, "weight": weight,
                    "expected_sign": expected, "path": path, "primary_hypothesis": str(primary).lower(),
                    "contrast_unit": "reviews" if metric in COUNTER_METRICS else "percentage_points",
                    "interval_method": "independent_condition_weighted_Welch", "paired_runs": "false"})

    def expand_comparisons(self):
        spec = self.spec["comparisons"]
        for family in ("H1", "H3"):
            outcomes = [spec[family]["outcome"]] if family == "H1" else spec[family]["outcomes"]
            for p0 in spec["repeat_each_template_for_p0"]:
                for template in spec[family]["templates"]:
                    self.contrast(template["id"] + f"_p{p0:02}", family, template["actor"], p0, outcomes,
                                  [(cell["weight"], cell["overrides"]) for cell in template["cells"]],
                                  template.get("expected_sign", "unspecified"), template.get("path", ""), True)
        for p0 in spec["repeat_each_template_for_p0"]:
            for kappa in (1, 2, 5):
                self.contrast(f"P3_kappa{kappa}_minus_fixed_p{p0:02}", "P3", "platform", p0,
                              ["E_mean", "O_final", "PR_final", "cumulative_reviews", "clean_review_exposure"],
                              [(1, {"platform-workload-mode": "state-responsive", "demand-kappa": kappa}), (-1, {})])
            for actor in ("legal", "platform"):
                coverage_name = "legal-strength" if actor == "legal" else "platform-speed"
                high = self.defaults[coverage_name]
                for coverage in (5, 10, 20, high):
                    family = "P5" if coverage != high else "P5_high_coverage_reference"
                    self.contrast(f"{family}_{actor}_coverage{coverage}_targeted_minus_random_p{p0:02}",
                                  family, actor, p0, ["E_mean", "O_final"],
                                  [(1, {coverage_name: coverage, "targeting-mode": "targeted"}),
                                   (-1, {coverage_name: coverage, "targeting-mode": "random"})])
                levels = (90, 95, 100) if actor == "legal" else (70, 80, 90)
                coverages = (70,) if actor == "legal" else (50, 75)
                for coverage in coverages:
                    for varying, fixed in (("tpr", "tnr"), ("tnr", "tpr")):
                        for fixed_level in levels:
                            overrides = {coverage_name: coverage, actor + "-" + fixed: fixed_level}
                            self.contrast(f"P6_{actor}_coverage{coverage}_{varying}_high_minus_low_at_{fixed}{fixed_level}_p{p0:02}",
                                          "P6_" + actor, actor, p0, ["E_mean", "O_final", "PR_final"],
                                          [(1, {**overrides, actor + "-" + varying: levels[-1]}),
                                           (-1, {**overrides, actor + "-" + varying: levels[0]})])
            for actor in ("none", "legal", "platform"):
                for network in ("ER", "WS"):
                    self.contrast(f"topology_{actor}_{network}_minus_BA_p{p0:02}", "topology", actor, p0,
                                  ["E_mean", "O_final", "E_final", "PR_final"],
                                  [(1, {"network-type": network}), (-1, {})])
                self.contrast(f"scale_{actor}_N5000_minus_N1000_p{p0:02}", "scale", actor, p0,
                              ["E_mean", "O_final", "E_final", "PR_final"], [(1, {"num-nodes": 5000}), (-1, {})])


def protect_output(output, new_design):
    execution_dir = output.parent / "outputs"
    if (execution_dir / "execution_binding.json").exists():
        raise RuntimeError("Execution binding exists: the planned manifest is frozen after execution starts; use a separately versioned project.")
    if (execution_dir / "run_status.csv").exists():
        with (execution_dir / "run_status.csv").open(encoding="utf-8", newline="") as stream:
            if next(csv.DictReader(stream), None) is not None:
                raise RuntimeError("Execution status records exist: refusing to rewrite the planned manifest.")
    manifest = output / "run_manifest.csv"
    if manifest.exists():
        with manifest.open(encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream):
                if row.get("status") != "planned":
                    raise RuntimeError("Manifest contains non-planned work; refusing to overwrite any run identity or status.")
    if new_design and any((output / filename).exists() for filename in ("conditions.csv", "lhs_legal.csv", "lhs_platform.csv")):
        raise RuntimeError("--new-design requires a fresh directory. Archived designs cannot be resampled in place.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=ROOT / "protocol" / "ABM_step1_protocol.json")
    parser.add_argument("--output", type=Path, default=ROOT / "design")
    parser.add_argument("--new-design", action="store_true")
    parser.add_argument("--model-version", default=DEFAULT_MODEL_VERSION)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    protect_output(output, args.new_design)
    spec = json.loads(args.protocol.read_text(encoding="utf-8"))
    protocol_hash = sha256(args.protocol)
    lhs, sampling_meta, lhs_checks = prepare_lhs(output, spec, protocol_hash, args.new_design)
    design = Design(spec)
    design.expand_grid()
    design.expand_lhs(lhs)
    design.expand_comparisons()
    assert len(design.conditions) == spec["design"]["total_conditions"]
    assert len(design.params) == 21
    # Prevent a changed generator from silently renumbering existing conditions.
    conditions_path = output / "conditions.csv"
    if conditions_path.exists():
        old = read_csv(conditions_path)
        for row in old:
            stored_config = {p["name"]: (row[p["name"]] if p["type"] == "enum" else float(row[p["name"]]))
                             for p in spec["model_parameters"]}
            assert config_hash(stored_config) == row["configuration_hash"], "Stored condition parameter values no longer match their hash."
        old_identity = [(int(r["condition_id"]), r["configuration_hash"]) for r in old]
        new_identity = [(r["condition_id"], r["configuration_hash"]) for r in design.conditions]
        assert old_identity == new_identity, "Existing condition IDs or configurations changed: create a new version."
    manifest_path = output / "run_manifest.csv"
    if manifest_path.exists():
        previous_identities = set()
        by_id = {r["condition_id"]: r for r in design.conditions}
        with manifest_path.open(encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream):
                cid, rid = int(row["condition_id"]), int(row["replicate_id"])
                assert cid in by_id and 1 <= rid <= spec["design"]["replicates"]
                assert (cid, rid) not in previous_identities, "Existing manifest contains duplicate identities."
                previous_identities.add((cid, rid))
                assert row["run_id"] == f"c{cid:04}_r{rid:02}"
                assert int(row["seed"]) == 20260922 + 1000 * cid + rid, "Existing run seed changed."
                assert row["configuration_hash"] == by_id[cid]["configuration_hash"]
        assert len(previous_identities) == spec["design"]["total_runs"], "Existing manifest is incomplete; restore it before regeneration."
    write_csv(conditions_path, list(design.conditions[0]), design.conditions)
    write_csv(output / "condition_groups.csv", list(design.groups[0]), design.groups)
    write_csv(output / "comparisons.csv", list(design.comparisons[0]), design.comparisons)

    sensitivity_comparisons = []
    for p0 in spec["design"]["common_p0"]:
        for actor, lhs_input, rhs_input in spec["comparisons"]["H2"]["index_differences"]:
            sensitivity_comparisons.append({"comparison_id": f"H2_{actor}_{lhs_input.replace('-', '_')}_minus_{rhs_input}_p{p0:02}",
                "family": "H2", "actor": actor, "p0": p0, "outcome": "E_mean",
                "stratum": f"{actor}_p0{p0:02}", "index": "PAWN_median_10_bins",
                "positive_input": lhs_input, "negative_input": rhs_input, "expected_sign": "positive",
                "interval_method": "joint_design_row_bootstrap_fixed_bins", "paired_runs": "false"})
    write_csv(output / "sensitivity_comparisons.csv", list(sensitivity_comparisons[0]), sensitivity_comparisons)

    model_path = ROOT / "model" / "exp_code_v2.0.nls"
    model_digest = sha256(model_path) if model_path.exists() else ""
    conditions_digest = sha256(conditions_path)
    run_fields = ["run_id", "condition_id", "replicate_id", "seed", "status", "output_mode",
                  "expected_rows", "expected_final_step", "model_version", "model_source_sha256",
                  "protocol_version", "protocol_sha256", "configuration_hash", "conditions_file_sha256",
                  "raw_output_path", "attempt_count", "completed_at_utc", "error_message"]
    seeds = set()
    row_counts = Counter()

    def runs():
        for condition in design.conditions:
            cid = condition["condition_id"]
            for rid in range(1, spec["design"]["replicates"] + 1):
                seed = 20260922 + 1000 * cid + rid
                assert seed not in seeds
                seeds.add(seed)
                row_counts[condition["output_mode"]] += condition["expected_rows_per_run"]
                run_id = f"c{cid:04}_r{rid:02}"
                yield {"run_id": run_id, "condition_id": cid, "replicate_id": rid, "seed": seed,
                       "status": "planned", "output_mode": condition["output_mode"],
                       "expected_rows": condition["expected_rows_per_run"], "expected_final_step": condition["max-ticks"],
                       "model_version": args.model_version, "model_source_sha256": model_digest,
                       "protocol_version": spec["version"], "protocol_sha256": protocol_hash,
                       "configuration_hash": condition["configuration_hash"], "conditions_file_sha256": conditions_digest,
                       "raw_output_path": "", "attempt_count": 0,
                       "completed_at_utc": "", "error_message": ""}

    write_csv(output / "run_manifest.csv", run_fields, runs())
    assert len(seeds) == spec["design"]["total_runs"]
    assert max(seeds) == spec["running"]["max_seed"]
    assert row_counts == {"trajectory": 298350, "final": 90000}
    group_keys = [(g["module"], g["condition_id"], g["role"]) for g in design.groups]
    assert len(group_keys) == len(set(group_keys))
    comparison_counts = {family: len({row["comparison_id"] for row in design.comparisons if row["family"] == family})
                         for family in sorted({r["family"] for r in design.comparisons})}
    assert comparison_counts["H1"] == 12
    assert comparison_counts["H3"] == 15
    assert len(sensitivity_comparisons) == 9
    comparison_groups = {}
    for row in design.comparisons:
        comparison_groups.setdefault((row["comparison_id"], row["outcome"]), []).append(row)
    for key, rows in comparison_groups.items():
        assert sum(row["weight"] for row in rows) == 0
        assert all(1 <= row["condition_id"] <= 195 for row in rows)
    metadata = {
        "schema": "ABM-executable-design-manifest", "generator_version": GENERATOR_VERSION,
        "protocol_version": spec["version"], "protocol_sha256": protocol_hash,
        "model_version": args.model_version, "model_source_sha256": model_digest,
        "model_hash_status": "resolved" if model_digest else "model_file_not_yet_present",
        "simulation_status": "no_runs_executed_by_generator", "condition_count": len(design.conditions),
        "run_count": len(seeds), "replicates_per_condition": spec["design"]["replicates"],
        "parameter_count": len(design.params), "parameter_columns": design.params,
        "group_membership_count": len(design.groups), "module_counts_before_extra_control_memberships": design.module_counts,
        "comparison_counts": comparison_counts, "linear_comparison_outcomes": len(comparison_groups),
        "linear_comparison_term_rows": len(design.comparisons), "H2_index_difference_count": len(sensitivity_comparisons),
        "output_rows": dict(row_counts), "seed_min": min(seeds), "seed_max": max(seeds),
        "seed_formula": spec["running"]["seed_formula"],
        "condition_order": "grid block order; p0 outermost, actor next, axes in JSON insertion order; then legal P4 and platform P4, p0 outermost and lhs_point_id increasing",
        "manifest_binding": "Join run_manifest.condition_id to conditions.condition_id and verify configuration_hash; 21 parameters are bound as one row, never expanded as a Cartesian product",
        "manifest_raw_output_path": "Initially empty: no simulation output exists. The immutable planned manifest is not a live status log; outputs/run_status.csv stores actual source_csv and behavior_run. Resolve batch membership through jobs/job_index.csv. No per-run output file is promised.",
        "comparisons_format": "long format: sum(weight * condition mean) grouped by comparison_id and outcome; H3 shares comparison_id across E/O; same replicate_id is not a paired network",
        "PR_null_policy": "If cumulative TP+FP is zero, PR_final is missing; exclude invalid ratios and report n_valid; comparison CI NA for insufficient valid runs",
        "H2_separate_file_reason": "Differences of sensitivity indices are not linear contrasts of condition means",
        "P5_reference_note": "High-coverage targeted-minus-random comparisons are descriptive references; low-coverage comparisons remain the P5 test",
        "sampling_environment": {key: sampling_meta[key] for key in ("python", "numpy", "scipy", "rng_argument")},
        "generation_environment": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__},
        "source_files": {"scripts/generate_design.py": sha256(Path(__file__))},
        "files": {filename: sha256(output / filename) for filename in
                  ("conditions.csv", "condition_groups.csv", "run_manifest.csv", "comparisons.csv",
                   "sensitivity_comparisons.csv", "lhs_legal.csv", "lhs_platform.csv", "lhs_metadata.json")}}
    dump_json(output / "design_metadata.json", metadata)
    checks = {"status": "passed", "scope": "configuration and scheduling validation; no simulation results",
              "all_21_parameter_rows_valid": True, "deduplication_uses_complete_parameters": True,
              "condition_ids_contiguous_and_stable": True, "module_new_counts_match_protocol": True,
              "grid_conditions": 195, "P4_conditions": 3000, "total_conditions": 3195,
              "grid_runs": 5850, "P4_runs": 90000, "total_runs": len(seeds),
              "all_runs_planned": True, "all_seeds_unique": True, "seed_min": min(seeds), "seed_max": max(seeds),
              "all_comparison_conditions_resolve": True, "contrast_weights_sum_to_zero": True,
              "same_replicate_id_not_treated_as_paired": True,
              "H1_contrasts": 12, "H3_joint_comparisons": 15, "H2_index_differences": 9,
              "group_memberships_unique": True, "lhs_checks": lhs_checks,
              "expected_output_rows": dict(row_counts),
              "model_source_hash_present": bool(model_digest)}
    dump_json(output / "design_validation.json", checks)
    print(json.dumps({"status": "passed", "conditions": len(design.conditions), "runs": len(seeds),
                      "grid_conditions": 195, "P4_conditions": 3000, "comparisons": comparison_counts,
                      "output": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
