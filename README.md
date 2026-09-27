# Dynamic Evaluation of Governance Strategies for Mitigating Social Media Data Pollution: An Agent-Based Modeling Approach

This repository provides the NetLogo simulation model, experimental design, archived simulation outputs, statistical analysis code, and publication materials for the study named above.

The study uses agent-based modeling (ABM) to examine the diffusion of data pollution on social media networks and to compare legal intervention with platform moderation. Batch simulations are conducted with NetLogo BehaviorSpace. Statistical analyses include parameter comparisons, global sensitivity analysis, and robustness checks across network topologies and sizes.

## Project versions

| Branch | Contents |
|---|---|
| `main` | Version 3: the current project, organized into `experiment/` and `publication/`. |
| `Version-1` | Archived Version 1 of the model and associated experimental materials. |
| `Version-2` | Archived Version 2 of the project. |

Use Version 3 for the current study. Earlier branches are retained for reference; their simulation outputs are not pooled with the current results.

The repository version and the model identifier are separate: the current repository is Version 3, while the archived simulation model retains the identifier `v2.0-design-v1.0` and its original filenames for traceability.

## Repository structure

Paths below are relative to the repository root.

| Path | Contents |
|---|---|
| `experiment/implementation/` | NetLogo model, parameter configurations, random-seed manifest, BehaviorSpace jobs, execution scripts, and experiment protocol. |
| `experiment/source_update/` | Archived simulation outputs and execution records used in the analysis. |
| `experiment/processed/` | Extracted run-level metrics, condition summaries, statistical contrasts, and sensitivity-analysis results. |
| `experiment/scripts_update/` | Python scripts for auditing outputs, extracting metrics, computing statistics, and generating analysis figures and tables. |
| `experiment/audit/` | Data-integrity checks, provenance records, and audit results. |
| `experiment/validation/` | Analysis validation records. Model validation files are also retained within `implementation/`. |
| `experiment/requirements-analysis.txt` | Python dependency versions for the analysis environment. |
| `experiment/README_zh.md` | Additional Chinese-language documentation for the experiment and analysis materials. |
| `publication/fig/` | Figure materials prepared for the manuscript, including LaTeX sources and their supporting files. |
| `publication/tab/` | Manuscript and appendix table materials, including LaTeX sources. |
| `publication/supplementary_information/` | The combined Supplementary Information project and its supporting figure and table materials. |

The paths and explicit commands in this README describe the Version 3 layout. Earlier documentation and archived execution logs may refer to the original package directory names.

## Experimental design

The current dataset contains **3,195 unique parameter configurations**, each evaluated using **30 independent simulation runs**, for a total of **95,850 runs**.

| Component | Unique configurations | Runs |
|---|---:|---:|
| Grid experiments and robustness checks | 195 | 5,850 |
| Global sensitivity design: legal governance | 1,500 | 45,000 |
| Global sensitivity design: platform governance | 1,500 | 45,000 |
| **Total** | **3,195** | **95,850** |

The experiments cover:

- Benchmark outcomes under no governance, legal intervention, and platform moderation.
- Legal coverage and response-interval sweeps, and platform coverage and accuracy sweeps.
- Random versus degree-targeted selection, including low-coverage conditions.
- Fixed versus state-responsive platform auditing.
- Separate variation of true-positive and true-negative rates (TPR and TNR).
- Alternative network topologies (BA, ER, and WS) and network sizes.
- Global sensitivity analysis using PAWN indices and supplementary partial rank correlation coefficients (PRCC).

Sensitivity analysis uses 500 Latin hypercube sampling (LHS) points for each governance regime and initial pollution level, with initial pollution set to 10%, 30%, or 50%. Each point's response is averaged over 30 runs.

Identical configurations share the same archived set of 30 runs across tables, figures, and diagnostic analyses. Reusing these results does not create additional independent runs. Matching replicate numbers across different configurations do not indicate paired simulations or shared network realizations.

## Key data and design files

| File | Purpose |
|---|---|
| `experiment/implementation/design/conditions.csv` | Complete parameter settings and condition identifiers. |
| `experiment/implementation/design/run_manifest.csv` | Run identifiers, condition assignments, and recorded random seeds. |
| `experiment/implementation/design/comparisons.csv` | Prespecified condition comparisons and contrast weights. |
| `experiment/implementation/design/sensitivity_comparisons.csv` | Prespecified H2 sensitivity-index comparisons. |
| `experiment/processed/run_metrics.csv` | One record per simulation run, with outcomes and provenance fields. |
| `experiment/processed/condition_summary.csv` | Condition-level summaries, confidence intervals, and valid sample sizes. |
| `experiment/processed/contrasts.csv` | Statistical comparisons between experimental conditions. |
| `experiment/processed/sensitivity_indices.csv` | PAWN and PRCC estimates with separate uncertainty summaries. |
| `experiment/processed/sensitivity_differences.csv` | Prespecified differences between sensitivity indices. |
| `experiment/processed/sensitivity_diagnostics.csv` | Alternative sensitivity-analysis specifications. |

Grid experiments retain observations from steps 0–50. The sensitivity experiments retain terminal records that include outcomes accumulated within each run; complete step-by-step trajectories are not archived for those runs.

## Outcome definitions and statistical conventions

- **Mean effectiveness** (`E_mean`, or $\bar E$) averages effectiveness over steps 1–50 within each run; step 0 is excluded.
- **Final effectiveness** (`E_final`, or $E(50)$) is effectiveness at step 50.
- **Wrongful exposure** (`O_final`, or $O(50)$) is the percentage of distinct accounts ever wronged by step 50. Each account is counted at most once in this measure.
- **Removal precision** (`PR_final`, or $P_R(50)$) is calculated within each run and then averaged over runs with a defined ratio. Undefined precision is retained as missing, rather than replaced with zero.
- **Review totals** count review events, including repeated reviews of the same account. Clean-account review totals are therefore distinct from the number of unique accounts exposed to wrongful intervention.

Effectiveness, wrongful exposure, and precision are reported as percentages; differences in these outcomes are expressed in percentage points. Sensitivity indices are dimensionless, and workload differences count review events.

Condition means use Student-t confidence intervals. Prespecified condition contrasts use Welch–Satterthwaite intervals. Reported 95% intervals are marginal, without multiplicity adjustment, and are not clipped to the outcome bounds. An interval containing zero does not establish equivalence.

The primary PAWN specification uses the median Kolmogorov–Smirnov distance across 10 fixed input bins. Row-bootstrap stability intervals and within-point Monte Carlo intervals are calculated separately, with 1,000 resamples for each procedure. They are not combined into a single interval. PRCC provides supplementary information about conditional rank association.

## Reproducing the analysis

The archived results can be inspected without rerunning NetLogo. To execute the analysis scripts, use Python 3.12 and install the dependencies from the repository root:

```bash
python3 -m pip install -r experiment/requirements-analysis.txt
```

The commands below use explicit paths for the current directory layout and write regenerated outputs to `experiment/reproduced/`. This keeps the archived files in `experiment/processed/` available for comparison.

### 1. Locate and audit the raw outputs

The raw-output directory passed to `--outputs` must directly contain `execution_binding.json`, `run_status.csv`, and `attempts/`. The following shell commands accommodate an archive stored either directly in `source_update/` or in its `outputs/` subdirectory:

```bash
ABM_RAW_OUTPUTS="experiment/source_update"
if [ -d "$ABM_RAW_OUTPUTS/outputs" ]; then
    ABM_RAW_OUTPUTS="$ABM_RAW_OUTPUTS/outputs"
fi

python3 experiment/scripts_update/audit_extract.py \
    --project experiment/implementation \
    --outputs "$ABM_RAW_OUTPUTS" \
    --out experiment/reproduced
```

If the archive has an additional enclosing directory, set `ABM_RAW_OUTPUTS` to the directory containing those metadata files before running the audit.

### 2. Recompute summaries, contrasts, and sensitivity results

```bash
python3 experiment/scripts_update/summarize_contrasts.py \
    --project experiment/implementation \
    --data experiment/reproduced/processed \
    --out experiment/reproduced

python3 experiment/scripts_update/analyze_sensitivity.py \
    --project experiment/implementation \
    --data experiment/reproduced/processed/run_metrics.csv \
    --out experiment/reproduced
```

Sensitivity analysis repeats the archived bootstrap procedures and can take substantially longer than ordinary condition summaries. These commands analyze existing simulation outputs; they do not launch NetLogo.

### 3. Generate analysis figures and tables

```bash
python3 experiment/scripts_update/make_figures.py \
    --project experiment/implementation \
    --data experiment/reproduced/processed \
    --out experiment/reproduced/figures

python3 experiment/scripts_update/make_sensitivity_figures.py \
    --data experiment/reproduced/processed \
    --out experiment/reproduced

python3 experiment/scripts_update/make_tables.py \
    --project experiment/implementation \
    --data experiment/reproduced/processed \
    --out experiment/reproduced/tables
```

To regenerate these figures and tables from the supplied summaries, replace `experiment/reproduced/processed` with `experiment/processed` in the three commands above. Input–response figures are generated separately by `analyze_sensitivity.py`.

The retained `run_pipeline.py` and `package_results.py` convenience wrappers contain paths from the earlier package layout. Use the explicit commands above with the current `scripts_update/` and `source_update/` directory names. The optional combined figure-atlas generator has been removed.

## Running the NetLogo model

Use **NetLogo 6.4.0 with the NW extension**. Open:

```text
experiment/implementation/model/ABM_revision_v2.0.nlogo
```

Keep `exp_code_v2.0.nls` in the same directory as the `.nlogo` file. For a basic interactive check, run the following commands in NetLogo's Command Center:

```netlogo
set-defaults
set treatment "legal"
setup
repeat 50 [ go ]
```

This produces one example trajectory. To reproduce the experimental design, use the archived configurations, seeds, and BehaviorSpace jobs in `experiment/implementation/`, rather than the interactive defaults.

The batch runner exposes its options through:

```bash
python3 experiment/implementation/scripts/run_experiments.py --help
```

For example, on macOS, adjust the NetLogo installation path below and preview the grid jobs:

```bash
ABM_NETLOGO="/Applications/NetLogo 6.4.0/NetLogo_Console"

python3 experiment/implementation/scripts/run_experiments.py \
    --root experiment/implementation \
    --netlogo-headless "$ABM_NETLOGO" \
    --outputs experiment/rerun_outputs \
    --phase grid --dry-run
```

Replace `--dry-run` with `--execute` to run the grid jobs. Use `--phase p4` for the sensitivity-design jobs. New simulations should use a fresh output directory such as `experiment/rerun_outputs/`, preserving the archived outputs in `source_update/`.

## Building the publication materials

The Python scripts generate analysis figures and tables. The materials in `publication/` contain the LaTeX layouts prepared for the manuscript, appendix, and Supplementary Information.

- Compile figure sources from their project directories, preserving the relative paths to their CSV data and style files.
- Compile the standalone table document with the accompanying journal class and required LaTeX packages.
- Compile the combined Supplementary Information from its main document in `publication/supplementary_information/`, retaining its table sources, figure PDFs, styles, and metadata files.

Use pdfLaTeX for the supplied projects and rerun compilation as needed to resolve cross-references and contents lists. In Overleaf, select the appropriate main document for each project. Supplementary figure and table numbers are assigned by the compiled document and may differ from the legacy source filenames.

## Research scope

The model evaluates governance mechanisms under specified network structures, parameter ranges, and input distributions. It is not calibrated to predict outcomes for a particular social media platform or jurisdiction.

Wrongful interventions contribute to exposure and workload measures but do not delete accounts or links or otherwise feed back into diffusion. State-responsive auditing uses the true pollution count before review, which is an idealized information assumption. Sensitivity rankings describe the specified experimental design and should not be interpreted as returns to equal-cost policy changes.

## Citation

If you use the model, data, or results in academic work, please cite the associated paper. 

- Full publication details and a DOI will be added after publication. Please also identify the repository version or commit used in your work.

## License

This project is distributed under the MIT License. See `LICENSE` for the license text and applicable terms.

## Acknowledgments

Special thanks to my advisor, colleagues, and friends for their guidance and support throughout the design, implementation, and analysis of this project.

**Jingyu Lin**  
Last updated: September 27, 2026
