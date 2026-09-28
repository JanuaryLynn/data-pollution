#!/usr/bin/env python3
"""Summarize audited ABM v2 outputs using the frozen design-v1.0 rules.

Usage:
  python summarize_contrasts.py --project /path/to/ABM_revision_v2.0 \
      --data /path/to/processed --out /path/to/results_v2

Requires numpy, pandas, scipy. All CIs are unadjusted, pointwise 95% intervals.
Source data and the frozen design are never modified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import warnings

import numpy as np
import pandas as pd
import scipy
from scipy.stats import t, ttest_ind


RUN_OUTCOMES = [
    "E_mean", "O_final", "E_final", "PR_final", "net_E_mean", "net_E_final",
    "cumulative_reviews", "cumulative_tp", "cumulative_fp", "cumulative_tn",
    "cumulative_fn", "clean_review_exposure", "distinct_wronged",
    "final_pollution_count", "initial_polluted_count", "mean_degree", "max_degree",
    "degree_sd", "network_edges", "count_isolates", "mean_super_degree",
    "mean_ordinary_degree", "super_count", "legal_action_opportunities",
    "active_review_steps",
]
TRAJECTORY_OUTCOMES = [
    "E", "O", "net_E", "PR", "E_mean_to_step", "net_E_mean_to_step",
    "step_reviews", "step_tp", "step_fp", "step_tn", "step_fn",
    "cumulative_reviews", "cumulative_tp", "cumulative_fp", "cumulative_tn",
    "cumulative_fn", "cumulative_clean_reviews", "actual_review_coverage",
    "legal_action_opportunities", "active_review_steps", "pollution_count",
    "polluted_pre_review", "count_wrongly_removed",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_csv(data: pd.DataFrame, path: Path) -> None:
    temporary = path.with_name(path.name + ".tmp")
    data.to_csv(temporary, index=False, na_rep="NA", float_format="%.12g")
    temporary.replace(path)


def write_text(text: str, path: Path) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def summary(data: pd.DataFrame, keys: list[str], outcomes: list[str]) -> pd.DataFrame:
    """Summarize independent runs within each cell, never independent time steps."""
    missing = set(outcomes) - set(data.columns)
    if missing:
        raise ValueError(f"Missing required metrics: {sorted(missing)}")
    parts = []
    grouped = data.groupby(keys, sort=True, observed=True)
    n_total = grouped.size().rename("n_total")
    for outcome in outcomes:
        s = grouped[outcome].agg(n="count", mean="mean", sd="std").join(n_total)
        s["outcome"] = outcome
        s["n_missing"] = s["n_total"] - s["n"]
        s["se"] = s["sd"] / np.sqrt(s["n"])
        critical = t.ppf(0.975, s["n"] - 1)
        s["ci_low"] = s["mean"] - critical * s["se"]
        s["ci_high"] = s["mean"] + critical * s["se"]
        s["ci_status"] = np.select(
            [s["n"] == 0, s["n"] < 2, s["sd"] == 0],
            ["undefined_no_valid_runs", "undefined_fewer_than_two_runs", "zero_sample_variance"],
            default="estimated",
        )
        parts.append(s.reset_index())
    result = pd.concat(parts, ignore_index=True)
    return result[keys + ["outcome", "n", "n_total", "n_missing", "mean", "sd", "se", "ci_low", "ci_high", "ci_status"]]


def calculate_contrasts(conditions: pd.DataFrame, comparisons: pd.DataFrame) -> pd.DataFrame:
    cell = conditions.set_index(["condition_id", "outcome"])
    rows = []
    meta_cols = ["family", "actor", "p0", "expected_sign", "path", "primary_hypothesis", "contrast_unit", "interval_method", "paired_runs"]
    for (comparison_id, outcome), terms in comparisons.groupby(["comparison_id", "outcome"], sort=False):
        # Combining weights before squaring is essential when a cell is reused.
        weights = terms.groupby("condition_id")["weight"].sum()
        weights = weights[weights != 0]
        row = {"comparison_id": comparison_id, "outcome": outcome}
        row.update({k: terms.iloc[0][k] for k in meta_cols})
        stats = cell.loc[[(int(cid), outcome) for cid in weights.index]]
        n = stats["n"].to_numpy(dtype=float)
        means = stats["mean"].to_numpy(dtype=float)
        variances = stats["sd"].to_numpy(dtype=float) ** 2
        w = weights.to_numpy(dtype=float)
        row.update(unique_conditions=len(w), n_min=int(n.min()) if len(n) else 0,
                   combined_weights=json.dumps({str(int(cid)): float(weight) for cid, weight in weights.items()}, separators=(",", ":")))
        if len(w) == 0:
            row.update(estimate=0.0, se=0.0, df=np.inf, ci_low=0.0, ci_high=0.0, ci_status="algebraic_zero")
        elif np.any(n == 0):
            row.update(estimate=np.nan, se=np.nan, df=np.nan, ci_low=np.nan, ci_high=np.nan, ci_status="undefined_no_valid_runs_in_required_cell")
        elif np.any(n < 2):
            row.update(estimate=float(w @ means), se=np.nan, df=np.nan, ci_low=np.nan, ci_high=np.nan, ci_status="undefined_fewer_than_two_runs_in_required_cell")
        else:
            estimate = float(w @ means)
            component = w * w * variances / n
            var = float(component.sum())
            denominator = float(np.sum(component ** 2 / (n - 1)))
            df = var * var / denominator if denominator > 0 else np.inf
            se = np.sqrt(var)
            margin = float(t.ppf(0.975, df) * se)
            row.update(estimate=estimate, se=se, df=df, ci_low=estimate-margin,
                       ci_high=estimate+margin, ci_status="estimated" if var > 0 else "zero_sample_variance")
        if not np.isfinite(row["ci_low"]):
            row["interval_direction"] = "undefined"
        elif row["ci_low"] > 0:
            row["interval_direction"] = "positive"
        elif row["ci_high"] < 0:
            row["interval_direction"] = "negative"
        else:
            row["interval_direction"] = "includes_zero"
        rows.append(row)
    return pd.DataFrame(rows)


def joint_covariance(runs: pd.DataFrame, comparisons: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Retain E/O pairing within runs and shared controls across H3 contrasts.

    Cov(A,B) = sum_c w_A,c w_B,c S_c[outcome_A,outcome_B]/n_c.
    The resulting matrix describes estimator covariance, not simultaneous CIs.
    """
    ids = comparisons.loc[comparisons.family == "H3", "condition_id"].unique()
    cell_cov = {}
    cell_rows = []
    for cid, g in runs[runs.condition_id.isin(ids)].groupby("condition_id"):
        valid = g[["E_mean", "O_final"]].dropna()
        if len(valid) != len(g):
            raise ValueError("H3 outcomes must both be available for every run.")
        sample_cov = valid.cov()
        cell_cov[int(cid)] = sample_cov / len(valid)
        cell_rows.append(dict(condition_id=int(cid), n=len(valid),
                              sample_var_E_mean=float(sample_cov.loc["E_mean", "E_mean"]),
                              sample_var_O_final=float(sample_cov.loc["O_final", "O_final"]),
                              sample_cov_E_mean_O_final=float(sample_cov.loc["E_mean", "O_final"]),
                              mean_cov_E_mean_O_final=float(sample_cov.loc["E_mean", "O_final"] / len(valid))))
    terms = {}
    for key, g in comparisons[comparisons.family == "H3"].groupby(["comparison_id", "outcome"], sort=False):
        w = g.groupby("condition_id")["weight"].sum()
        terms[key] = {int(cid): float(value) for cid, value in w.items() if value != 0}
    rows = []
    for (id_a, out_a), wa in terms.items():
        for (id_b, out_b), wb in terms.items():
            shared = sorted(wa.keys() & wb.keys())
            value = sum(wa[cid] * wb[cid] * cell_cov[cid].loc[out_a, out_b] for cid in shared)
            rows.append(dict(comparison_id_a=id_a, outcome_a=out_a, comparison_id_b=id_b,
                             outcome_b=out_b, covariance=float(value), shared_conditions=";".join(map(str, shared))))
    return pd.DataFrame(cell_rows), pd.DataFrame(rows)


def scipy_crosscheck(runs: pd.DataFrame, contrasts: pd.DataFrame) -> int:
    """Independently check every estimable two-cell contrast against SciPy."""
    checked = 0
    by_condition = {int(cid): g for cid, g in runs.groupby("condition_id")}
    for _, row in contrasts.iterrows():
        weights = json.loads(row.combined_weights)
        if len(weights) != 2 or sorted(weights.values()) != [-1.0, 1.0] or row.ci_status != "estimated":
            continue
        positive = next(int(k) for k, v in weights.items() if v == 1)
        negative = next(int(k) for k, v in weights.items() if v == -1)
        a = by_condition[positive][row.outcome].dropna().to_numpy()
        b = by_condition[negative][row.outcome].dropna().to_numpy()
        with warnings.catch_warnings():
            # SciPy emits this warning for near-constant endpoints; the numeric
            # agreement is still checked rather than discarded.
            warnings.filterwarnings("ignore", message="Precision loss occurred", category=RuntimeWarning)
            result = ttest_ind(a, b, equal_var=False)
        interval = result.confidence_interval(0.95)
        np.testing.assert_allclose(
            [row.estimate, row.df, row.ci_low, row.ci_high],
            [a.mean() - b.mean(), result.df, interval.low, interval.high],
            rtol=1e-9, atol=1e-9,
        )
        checked += 1
    return checked


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True, help="Frozen experiment project containing design/ and protocol/.")
    parser.add_argument("--data", type=Path, required=True, help="Audited processed directory containing run_metrics.csv and grid_trajectories.csv.gz.")
    parser.add_argument("--out", type=Path, required=True, help="Analysis root; numerical outputs are written to processed/ and validation metadata to audit/.")
    args = parser.parse_args()
    project, data, out = args.project.resolve(), args.data.resolve(), args.out.resolve()
    processed, audit = out / "processed", out / "audit"
    processed.mkdir(parents=True, exist_ok=True)
    audit.mkdir(parents=True, exist_ok=True)
    protocol_path = project / "protocol/ABM_step1_protocol.json"
    protocol = json.loads(protocol_path.read_text())
    run_path = data / "run_metrics.csv"
    trajectory_path = data / "grid_trajectories.csv.gz"
    runs = pd.read_csv(run_path, na_values=["NA"], low_memory=False)
    design = pd.read_csv(project / "design/conditions.csv")
    comparisons = pd.read_csv(project / "design/comparisons.csv", keep_default_na=False)
    assert len(runs) == protocol["design"]["total_runs"]
    assert runs.run_id.is_unique and not runs.duplicated(["condition_id", "replicate_id"]).any()
    assert set(runs.condition_id) == set(design.condition_id)
    assert (runs.groupby("condition_id").size() == protocol["design"]["replicates"]).all()
    assert set(comparisons.outcome) <= set(RUN_OUTCOMES)
    cells = summary(runs, ["condition_id"], RUN_OUTCOMES)
    write_csv(cells, processed / "condition_summary.csv")
    print(f"Summarized {len(runs):,} runs into {len(cells):,} condition/outcome rows", flush=True)
    c = calculate_contrasts(cells, comparisons)
    assert len(c) == comparisons[["comparison_id", "outcome"]].drop_duplicates().shape[0] == 405
    write_csv(c, processed / "contrasts.csv")
    cell_cov, joint = joint_covariance(runs, comparisons)
    write_csv(cell_cov, processed / "h3_cell_covariance.csv")
    write_csv(joint, processed / "h3_joint_covariance.csv")
    trajectory_header = pd.read_csv(trajectory_path, nrows=0).columns
    need = ["condition_id", "replicate_id", "step"] + TRAJECTORY_OUTCOMES
    missing = set(need) - set(trajectory_header)
    if missing:
        raise ValueError(f"Trajectory columns missing: {sorted(missing)}")
    trajectories = pd.read_csv(trajectory_path, usecols=need, na_values=["NA"])
    assert len(trajectories) == protocol["design"]["grid_output_rows"]
    assert not trajectories.duplicated(["condition_id", "replicate_id", "step"]).any()
    ts = summary(trajectories, ["condition_id", "step"], TRAJECTORY_OUTCOMES)
    assert (ts.n_total == protocol["design"]["replicates"]).all()
    write_csv(ts, processed / "trajectory_summary.csv")
    # Concrete consistency checks: final trajectories equal run-level endpoints;
    # covariance matrix is symmetric PSD and diagonal equals marginal variances.
    endpoint_map = {"E": "E_final", "O": "O_final", "PR": "PR_final", "net_E": "net_E_final"}
    for traj_outcome, run_outcome in endpoint_map.items():
        a = ts[(ts.step == 50) & (ts.outcome == traj_outcome)].set_index("condition_id")["mean"].sort_index()
        b = cells[(cells.condition_id.isin(a.index)) & (cells.outcome == run_outcome)].set_index("condition_id")["mean"].sort_index()
        np.testing.assert_allclose(a.to_numpy(), b.to_numpy(), atol=1e-10, rtol=1e-10, equal_nan=True)
    labels = list(dict.fromkeys(zip(joint.comparison_id_a, joint.outcome_a)))
    matrix = joint.covariance.to_numpy().reshape(len(labels), len(labels))
    np.testing.assert_allclose(matrix, matrix.T, atol=1e-10, rtol=1e-10)
    if np.linalg.eigvalsh(matrix).min() < -1e-10:
        raise ValueError("H3 covariance matrix is not positive semidefinite")
    c_index = c.set_index(["comparison_id", "outcome"])
    np.testing.assert_allclose(np.diag(matrix), [c_index.loc[x, "se"] ** 2 for x in labels], atol=1e-10, rtol=1e-10)
    crosschecked = scipy_crosscheck(runs, c)
    provenance = {
        "schema": "ABM-statistical-summary-v1", "status": "passed", "n_runs": len(runs),
        "n_conditions": len(design), "n_condition_outcome_rows": len(cells),
        "n_trajectory_outcome_rows": len(ts), "n_frozen_outcome_contrasts": len(c),
        "undefined_contrasts": int(c.ci_status.str.startswith("undefined").sum()),
        "independent_scipy_Welch_crosscheck_count": crosschecked,
        "confidence_level": 0.95, "simultaneous_intervals": False, "paired_conditions": False,
        "checks": ["all_manifest_cells_have_30_runs", "run_identity_unique", "grid_trajectory_unique_and_complete",
                   "endpoint_summary_matches_run_metrics", "H3_covariance_symmetric_PSD_and_diagonal_matches_Welch_variance",
                   "independent_scipy_ttest_ind_nonzero_variance_two_cell_contrasts"],
        "software": {"python": sys.version, "numpy": np.__version__, "pandas": pd.__version__, "scipy": scipy.__version__},
        "source_sha256": {"run_metrics.csv": sha256(run_path), "grid_trajectories.csv.gz": sha256(trajectory_path),
                          "conditions.csv": sha256(project / "design/conditions.csv"), "comparisons.csv": sha256(project / "design/comparisons.csv"),
                          "protocol.json": sha256(protocol_path), "summarize_contrasts.py": sha256(Path(__file__))},
    }
    write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", audit / "statistics_validation.json")
    print(json.dumps({k: v for k, v in provenance.items() if k not in ["source_sha256", "software"]}, indent=2), flush=True)


if __name__ == "__main__":
    main()
