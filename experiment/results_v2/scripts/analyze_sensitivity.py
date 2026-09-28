#!/usr/bin/env python3
"""Frozen P4 sensitivity analysis; reads audited real runs, never starts NetLogo.

Usage: python scripts/analyze_sensitivity.py --project ../implementation \
    --data processed/run_metrics.csv --out .
Inputs: 500 authoritative LHS rows/actor, 30 independent simulations/row/stratum.
Row bootstrap is approximate LHS-design stability; within-point bootstrap measures
simulation Monte Carlo noise. Their intervals are deliberately kept separate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy
from scipy.stats import rankdata, ks_2samp

OUTCOMES = ["E_mean", "O_final"]
BINS = [5, 10, 20]
AGGS = ["median", "mean", "maximum"]
ACTOR_INPUTS = {"legal": ["legal-strength", "legal-response-time", "alpha_legal"],
                "platform": ["platform-speed", "alpha_platform"]}
LABELS = {"legal-strength": "Legal coverage L (%)", "legal-response-time": "Legal interval tau (ticks)",
          "alpha_legal": "Legal accuracy alpha (%)", "platform-speed": "Platform coverage np (%)",
          "alpha_platform": "Platform accuracy alpha (%)"}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def make_bins(x, names):
    """Fixed original full-design empirical quantiles; integer tau is never split."""
    masks, groups, records = [], [], []
    start = 0
    for ib, nb in enumerate(BINS):
        for j, name in enumerate(names):
            if name == "legal-response-time":
                edges = np.arange(1, 22, 20 // nb, dtype=float)
                b = ((x[:, j].astype(int) - 1) // (20 // nb)).astype(int)
            else:
                edges = np.quantile(x[:, j], np.linspace(0, 1, nb + 1), method="linear")
                b = np.searchsorted(edges[1:-1], x[:, j], side="right")
            counts = np.bincount(b, minlength=nb)
            if len(counts) != nb or np.any(counts == 0):
                raise ValueError(f"Empty original bin: {name}, {nb}")
            masks.append(np.equal(b[:, None], np.arange(nb)[None, :]))
            groups.append((ib, j, slice(start, start + nb)))
            start += nb
            records.append({"input": name, "bins": nb, "edges": edges.tolist(),
                            "counts": counts.tolist(), "closure": "left closed; final includes maximum"})
    return np.concatenate(masks, axis=1), groups, records


def pawn_batch(y, masks, groups, ninputs, weights=None):
    """Exact empirical KS, vectorized over fixed bins and bootstrap replicates.

    y: (bootstrap, rows). We evaluate CDFs only at the END of tied response
    values. This avoids an inflated KS when ties are present (including repeated
    bootstrap rows). weights are multinomial row counts, or all ones for MC.
    """
    y = np.asarray(y)
    if y.ndim == 1:
        y = y[None, :]
    nbatch, n = y.shape
    if weights is None:
        weights = np.ones((nbatch, n), dtype=float)
    order = np.argsort(y, axis=1, kind="stable")
    ys = np.take_along_axis(y, order, axis=1)
    ws = np.take_along_axis(weights, order, axis=1)
    mm = masks[order, :]
    conditional_counts = mm * ws[:, :, None]
    totals = conditional_counts.sum(axis=1)
    cdfs = np.cumsum(conditional_counts, axis=1, dtype=float)
    np.divide(cdfs, totals[:, None, :], out=cdfs, where=totals[:, None, :] > 0)
    unconditional = np.cumsum(ws, axis=1) / ws.sum(axis=1, keepdims=True)
    delta = np.abs(cdfs - unconditional[:, :, None])
    endpoints = np.concatenate((ys[:, 1:] != ys[:, :-1], np.ones((nbatch, 1), dtype=bool)), axis=1)
    delta *= endpoints[:, :, None]
    ks = delta.max(axis=1)
    ks[totals == 0] = np.nan
    res = np.full((nbatch, len(BINS), len(AGGS), ninputs), np.nan)
    for ib, j, sl in groups:
        # No nanmedian: an empty conditional bin invalidates the entire index.
        vals = ks[:, sl]
        res[:, ib, 0, j] = np.median(vals, axis=1)
        res[:, ib, 1, j] = np.mean(vals, axis=1)
        res[:, ib, 2, j] = np.max(vals, axis=1)
    active_min = np.min(np.where(weights > 0, y, np.inf), axis=1)
    active_max = np.max(np.where(weights > 0, y, -np.inf), axis=1)
    constant = active_max == active_min
    res[constant] = np.nan
    return res


def prcc_batch(x, y):
    """Rank residual correlations, average ties, full intercept adjustment."""
    if x.ndim == 2:
        x = x[None, :, :]
    if y.ndim == 2:
        y = y[None, :, :]
    xr = rankdata(x, axis=1, method="average")
    yr = rankdata(y, axis=1, method="average")
    batch, n, p = xr.shape
    result = np.full((batch, yr.shape[2], p), np.nan)
    for j in range(p):
        other = np.delete(xr, j, axis=2)
        z = np.concatenate((np.ones((batch, n, 1)), other), axis=2)
        zz_inv = np.linalg.pinv(z)
        rx = xr[:, :, j] - (z @ (zz_inv @ xr[:, :, j, None]))[:, :, 0]
        ry = yr - z @ (zz_inv @ yr)
        numerator = np.einsum("bn,bno->bo", rx, ry)
        denom = np.sqrt(np.einsum("bn,bn->b", rx, rx)[:, None] * np.einsum("bno,bno->bo", ry, ry))
        # A constant response or a residual at floating-point noise scale is NA.
        valid = (np.ptp(yr, axis=1) > 0) & (denom > 1e-8)
        np.divide(numerator, denom, out=result[:, :, j], where=valid)
    return np.clip(result, -1, 1)


def interval(samples):
    a = np.asarray(samples)
    a = a[np.isfinite(a)]
    if len(a) < 2:
        return np.nan, np.nan, len(a)
    lo, hi = np.quantile(a, [0.025, 0.975])
    return float(lo), float(hi), len(a)


def ci_fields(row, draw, mc):
    for label, values in [("row", draw), ("mc", mc)]:
        lo, hi, n = interval(values)
        row.update({f"{label}_ci95_low": lo, f"{label}_ci95_high": hi, f"{label}_valid_resamples": n})
    return row


def validate_ks(masks, groups, y, got):
    """One meaningful reference check: ties-aware implementation vs scipy KS."""
    largest = 0.
    for ib, j, sl in groups:
        vals = [ks_2samp(y, y[masks[:, k]], method="asymp").statistic for k in range(sl.start, sl.stop)]
        want = [np.median(vals), np.mean(vals), np.max(vals)]
        largest = max(largest, float(np.max(np.abs(np.array(want) - got[ib, :, j]))))
    if largest > 1e-12:
        raise ValueError(f"KS reference mismatch {largest}")
    return largest


def response_figures(responses, out):
    """Descriptive scatter/conditional-mean plots used to inspect monotonicity."""
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "pdf.fonttype": 42, "ps.fonttype": 42})
    for actor, names in ACTOR_INPUTS.items():
        for outcome in OUTCOMES:
            fig, axes = plt.subplots(3, len(names), figsize=(4.0 * len(names), 7.5), squeeze=False)
            for row, p0 in enumerate([10, 30, 50]):
                data = responses[(responses.actor == actor) & (responses.p0 == p0)]
                for col, name in enumerate(names):
                    ax = axes[row, col]
                    xx, yy = data[name].to_numpy(), data[outcome].to_numpy()
                    ax.scatter(xx, yy, s=7, alpha=0.27, color="#3875a2", linewidth=0, rasterized=True)
                    if name == "legal-response-time":
                        bins = ((xx.astype(int) - 1) // 2).astype(int)
                    else:
                        e = np.quantile(xx, np.linspace(0, 1, 11))
                        bins = np.searchsorted(e[1:-1], xx, side="right")
                    ax.plot([np.mean(xx[bins == i]) for i in range(10)],
                            [np.mean(yy[bins == i]) for i in range(10)], "o-", ms=3, lw=1.3, color="#b84b29")
                    ax.set_xlabel(LABELS[name])
                    if col == 0:
                        ax.set_ylabel(f"p0 = {p0}%\n{outcome} (%)")
                    ax.grid(axis="y", alpha=.15)
            fig.suptitle(f"{actor.capitalize()} LHS response diagnostics: {outcome}\n"
                         "Each dot: mean of 30 runs; line: mean within 10 fixed input bins", fontsize=11)
            fig.tight_layout(rect=(0, 0, 1, .945))
            for ext in ["pdf", "png"]:
                fig.savefig(out / "figures" / f"sensitivity_response_{actor}_{outcome}.{ext}", dpi=160, bbox_inches="tight")
            plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", type=Path, required=True)
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    start = time.time()
    args.out = args.out.resolve()
    for d in ["processed", "figures"]:
        (args.out / d).mkdir(parents=True, exist_ok=True)
    protocol_path = args.project / "protocol" / "ABM_step1_protocol.json"
    spec = json.loads(protocol_path.read_text())
    cfg = spec["statistics"]["sensitivity"]
    nboot = cfg["row_bootstrap"]["resamples"]
    if nboot != cfg["within_point_bootstrap"]["resamples"] or nboot != 1000:
        raise ValueError("Analysis requires the frozen 1,000 + 1,000 resamples")
    runs = pd.read_csv(args.data)
    comparisons = pd.read_csv(args.project / "design" / "sensitivity_comparisons.csv")
    conditions = pd.read_csv(args.project / "design" / "conditions.csv")
    primary, diagnostics, differences, responses, bin_responses = [], [], [], [], []
    archive, checks, maximum_ks_error = {}, [], 0.
    source_hashes = {str(protocol_path): sha256(protocol_path), str(args.data): sha256(args.data),
                     str(args.project / "design" / "conditions.csv"):
                         sha256(args.project / "design" / "conditions.csv"),
                     str(args.project / "design" / "sensitivity_comparisons.csv"):
                         sha256(args.project / "design" / "sensitivity_comparisons.csv")}
    for iactor, (actor, names) in enumerate(ACTOR_INPUTS.items()):
        lhs_path = args.project / "design" / f"lhs_{actor}.csv"
        source_hashes[str(lhs_path)] = sha256(lhs_path)
        lhs = pd.read_csv(lhs_path).sort_values("lhs_point_id")
        if lhs.lhs_point_id.tolist() != list(range(1, 501)):
            raise ValueError("Expected exactly 500 frozen LHS rows")
        x = lhs[names].to_numpy(float)
        masks, groups, bin_records = make_bins(x, names)
        p = len(names)
        for ip0, p0 in enumerate([10, 30, 50]):
            stratum = f"{actor}_p{p0:03d}"
            print(f"Analyzing {stratum}: 500 LHS rows x 30 runs", flush=True)
            ids = conditions[(conditions.sensitivity_actor == actor) & (conditions.p0 == p0)]
            subset = runs[runs.condition_id.isin(ids.condition_id)].sort_values(["lhs_point_id", "replicate_id"])
            if len(ids) != 500 or len(subset) != 15000:
                raise ValueError(f"Incomplete stratum: {stratum}")
            if subset.groupby("lhs_point_id").replicate_id.apply(list).tolist() != [list(range(1, 31))] * 500:
                raise ValueError(f"Invalid replicate identities: {stratum}")
            first = subset.drop_duplicates("lhs_point_id")
            for name in names:
                source_name = f"{actor}-tpr" if name.startswith("alpha_") else name
                if not np.allclose(first[source_name].to_numpy(), x[:, names.index(name)], rtol=0, atol=1e-12):
                    raise ValueError(f"LHS binding mismatch: {stratum}, {name}")
                if name.startswith("alpha_") and not np.array_equal(first[f"{actor}-tpr"], first[f"{actor}-tnr"]):
                    raise ValueError("Frozen P4 requires symmetric accuracy")
            yrep = subset[OUTCOMES].to_numpy(float).reshape(500, 30, 2)
            if not np.isfinite(yrep).all():
                raise ValueError("Non-finite primary response")
            y = yrep.mean(axis=1)
            y20 = yrep[:, :20].mean(axis=1)
            point = np.stack([pawn_batch(y[:, o], masks, groups, p)[0] for o in range(2)])
            point20 = np.stack([pawn_batch(y20[:, o], masks, groups, p)[0] for o in range(2)])
            prcc = prcc_batch(x, y)[0]
            prcc20 = prcc_batch(x, y20)[0]
            for o in range(2):
                if np.ptp(y[:, o]) > 0:
                    maximum_ks_error = max(maximum_ks_error, validate_ks(masks, groups, y[:, o], point[o]))
            row_pawn = np.empty((nboot, 2, len(BINS), len(AGGS), p))
            mc_pawn = np.empty_like(row_pawn)
            row_prcc = np.empty((nboot, 2, p))
            mc_prcc = np.empty_like(row_prcc)
            row_seed = cfg["row_bootstrap"]["seeds"][iactor * 3 + ip0]
            mc_seed = cfg["within_point_bootstrap"]["seeds"][iactor * 3 + ip0]
            row_rng, mc_rng = np.random.default_rng(row_seed), np.random.default_rng(mc_seed)
            # Bound memory by batch. RNG draws and index pairing are invariant to
            # batch size: the bootstrap-major flattening order is fixed.
            batch_size = 25
            for begin in range(0, nboot, batch_size):
                end = min(nboot, begin + batch_size)
                b = end - begin
                sampled = row_rng.integers(0, 500, size=(b, 500))
                weights = np.zeros((b, 500), dtype=float)
                np.add.at(weights, (np.arange(b)[:, None], sampled), 1)
                for o in range(2):
                    row_pawn[begin:end, o] = pawn_batch(np.broadcast_to(y[:, o], (b, 500)), masks, groups, p, weights)
                row_prcc[begin:end] = prcc_batch(x[sampled], y[sampled])
                # Within each design row, resample the PAIRED E/O run vectors.
                take = mc_rng.integers(0, 30, size=(b, 500, 30))
                mc_y = yrep[np.arange(500)[None, :, None], take, :].mean(axis=2)
                for o in range(2):
                    mc_pawn[begin:end, o] = pawn_batch(mc_y[:, :, o], masks, groups, p)
                mc_prcc[begin:end] = prcc_batch(np.broadcast_to(x, (b, *x.shape)), mc_y)
            archive.update({f"{stratum}_row_pawn": row_pawn, f"{stratum}_mc_pawn": mc_pawn,
                            f"{stratum}_row_prcc": row_prcc, f"{stratum}_mc_prcc": mc_prcc})
            for o, outcome in enumerate(OUTCOMES):
                for ib, nb in enumerate(BINS):
                    for ag, agg in enumerate(AGGS):
                        estimates = point[o, ib, ag]
                        estimates20 = point20[o, ib, ag]
                        ranks30 = rankdata(-estimates, method="min")
                        ranks20 = rankdata(-estimates20, method="min")
                        for j, name in enumerate(names):
                            rec = {"actor": actor, "p0": p0, "stratum": stratum, "outcome": outcome,
                                   "method": "PAWN", "bins": nb, "aggregation": agg, "input": name,
                                   "estimate": estimates[j], "n_lhs": 500, "repeats": 30,
                                   "estimate_20": estimates20[j], "rank_30": ranks30[j], "rank_20": ranks20[j],
                                   "estimable": bool(np.isfinite(estimates[j]))}
                            ci_fields(rec, row_pawn[:, o, ib, ag, j], mc_pawn[:, o, ib, ag, j])
                            diagnostics.append(rec)
                            if nb == 10 and agg == "median":
                                primary.append(rec.copy())
                for j, name in enumerate(names):
                    rec = {"actor": actor, "p0": p0, "stratum": stratum, "outcome": outcome,
                           "method": "PRCC", "bins": np.nan, "aggregation": "rank_residual_correlation",
                           "input": name, "estimate": prcc[o, j], "n_lhs": 500, "repeats": 30,
                           "estimate_20": prcc20[o, j], "rank_30": np.nan, "rank_20": np.nan,
                           "estimable": bool(np.isfinite(prcc[o, j]))}
                    ci_fields(rec, row_prcc[:, o, j], mc_prcc[:, o, j])
                    primary.append(rec)
            for _, comp in comparisons[comparisons.stratum == stratum].iterrows():
                jp, jn = names.index(comp.positive_input), names.index(comp.negative_input)
                for o, outcome in enumerate(OUTCOMES):
                    est = point[o, 1, 0, jp] - point[o, 1, 0, jn]
                    rec = {"comparison_id": comp.comparison_id if outcome == "E_mean" else comp.comparison_id.replace("H2_", "O_companion_"),
                           "family": "H2" if outcome == "E_mean" else "O_companion", "actor": actor,
                           "p0": p0, "stratum": stratum, "outcome": outcome,
                           "method": "PAWN_median_10_bins", "positive_input": comp.positive_input,
                           "negative_input": comp.negative_input, "estimate": est,
                           "expected_sign": "positive" if outcome == "E_mean" else "not_hypothesized",
                           "estimate_20": point20[o, 1, 0, jp] - point20[o, 1, 0, jn]}
                    rowdiff = row_pawn[:, o, 1, 0, jp] - row_pawn[:, o, 1, 0, jn]
                    mcdiff = mc_pawn[:, o, 1, 0, jp] - mc_pawn[:, o, 1, 0, jn]
                    ci_fields(rec, rowdiff, mcdiff)
                    if not np.isfinite(rec["row_ci95_low"]):
                        rec["row_interval_direction"] = "not_estimable"
                    elif rec["row_ci95_low"] > 0:
                        rec["row_interval_direction"] = "positive"
                    elif rec["row_ci95_high"] < 0:
                        rec["row_interval_direction"] = "negative"
                    else:
                        rec["row_interval_direction"] = "unresolved"
                    differences.append(rec)
            response = first[["condition_id", "lhs_point_id"]].copy()
            response["actor"], response["p0"], response["stratum"] = actor, p0, stratum
            for j, name in enumerate(names):
                response[name] = x[:, j]
            for o, outcome in enumerate(OUTCOMES):
                response[outcome], response[outcome + "_20"] = y[:, o], y20[:, o]
                response[outcome + "_mc_se"] = yrep[:, :, o].std(axis=1, ddof=1) / np.sqrt(30)
            responses.append(response)
            for ib, j, sl in groups:
                if BINS[ib] != 10:
                    continue
                for k in range(10):
                    select = masks[:, sl.start + k]
                    for o, outcome in enumerate(OUTCOMES):
                        bin_responses.append({"actor": actor, "p0": p0, "stratum": stratum,
                                              "input": names[j], "outcome": outcome, "bin": k + 1,
                                              "n_lhs": int(select.sum()), "x_mean": x[select, j].mean(),
                                              "response_mean": y[select, o].mean(),
                                              "response_min": y[select, o].min(),
                                              "response_max": y[select, o].max()})
            checks.append({"stratum": stratum, "condition_count": len(ids), "run_count": len(subset),
                           "input_names": names, "input_correlation": np.corrcoef(x.T).tolist(),
                           "row_seed": row_seed, "mc_seed": mc_seed, "bins": bin_records,
                           "responses": {outcome: {"min": float(y[:, o].min()), "max": float(y[:, o].max()),
                               "sd_across_design_rows": float(y[:, o].std(ddof=1)),
                               "mean_within_point_mc_se": float((yrep[:, :, o].std(axis=1, ddof=1) / np.sqrt(30)).mean()),
                               "constant_response": bool(np.ptp(y[:, o]) == 0),
                               "valid_row_primary_draws": int(np.isfinite(row_pawn[:, o, 1, 0]).all(axis=1).sum()),
                               "valid_mc_primary_draws": int(np.isfinite(mc_pawn[:, o, 1, 0]).all(axis=1).sum())}
                                         for o, outcome in enumerate(OUTCOMES)}})
            print(f"Completed {stratum}; elapsed {time.time() - start:.1f}s", flush=True)
    dfs = {"sensitivity_indices": pd.DataFrame(primary), "sensitivity_differences": pd.DataFrame(differences),
           "sensitivity_diagnostics": pd.DataFrame(diagnostics),
           "sensitivity_design_responses": pd.concat(responses, ignore_index=True),
           "sensitivity_response_bins": pd.DataFrame(bin_responses)}
    for name, df in dfs.items():
        df.to_csv(args.out / "processed" / f"{name}.csv", index=False, na_rep="NA", float_format="%.12g")
    np.savez_compressed(args.out / "processed" / "sensitivity_bootstrap_draws.npz", **archive)
    response_figures(dfs["sensitivity_design_responses"], args.out)
    metadata = {"schema": "ABM-P4-frozen-sensitivity-analysis-v1", "status": "completed",
                "source_hashes": source_hashes, "script_sha256": sha256(Path(__file__)),
                "versions": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__, "scipy": scipy.__version__},
                "bootstrap_resamples_each_kind": nboot, "bin_counts": BINS, "aggregations": AGGS,
                "outcomes": OUTCOMES, "archive_pawn_axes": ["bootstrap", "outcome", "bin_setting", "aggregation", "input"],
                "archive_prcc_axes": ["bootstrap", "outcome", "input"],
                "bootstrap_percentiles": [2.5, 97.5], "ks_reference_max_abs_error": maximum_ks_error,
                "ordinary_bootstrap_preserves_lhs_stratification": False,
                "mc_intervals_added_to_row_intervals": False,
                "first_20_repeats_used_for_stability": True,
                "strata": checks, "elapsed_seconds": time.time() - start}
    (args.out / "processed" / "sensitivity_analysis_checks.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"status": "completed", "strata": 6, "primary_index_rows": len(primary),
                      "diagnostic_rows": len(diagnostics), "difference_rows": len(differences),
                      "elapsed_seconds": time.time() - start}, indent=2), flush=True)


if __name__ == "__main__":
    main()
