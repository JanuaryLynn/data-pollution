# Dynamic Evaluation of Governance Strategies for Mitigating Social Media Data Pollution: An Agent-Based Modeling Approach

This repository provides the NetLogo simulation model, experimental design, archived simulation outputs, statistical analysis code, and publication materials for the study named above.

The study uses agent-based modeling (ABM) to examine the diffusion of data pollution on social media networks and to compare legal intervention with platform moderation. Batch simulations are conducted with NetLogo BehaviorSpace. Statistical analyses include parameter comparisons, global sensitivity analysis, and robustness checks across network topologies and sizes.

## 🌳 Project versions

| Branch | Contents |
|---|---|
| `main` | Version 3: the current project, organized into `experiment/` and `publication/`. |
| `Version-1` | Archived Version 1 of the model and associated experimental materials. |
| `Version-2` | Archived Version 2 of the project. |

Use Version 3 for the current study. Earlier branches are retained for reference; their simulation outputs are not pooled with the current results.

The repository version and the model identifier are separate: the current repository is Version 3, while the archived simulation model retains the identifier `v2.0-design-v1.0` and its original filenames for traceability.

## 📋 Repository structure

Paths below are relative to the repository root.

| Path | Contents |
|---|---|
| `experiment/implementation/` | NetLogo model, parameter configurations, random-seed manifest, BehaviorSpace jobs, execution scripts, and experiment protocol. |
| `experiment/results_v2/source/` | Archived simulation outputs and execution records used in the analysis. |
| `experiment/results_v2/processed/` | Extracted run-level metrics, condition summaries, statistical contrasts, and sensitivity-analysis results. |
| `experiment/results_v2/scripts/` | Python scripts for auditing outputs, extracting metrics, computing statistics, and generating analysis figures and tables. |
| `experiment/results_v2/audit/` | Data-integrity checks, provenance records, and audit results. |
| `experiment/results_v2/validation/` | Analysis validation records. Model validation files are also retained within `implementation/`. |
| `experiment/results_v2/requirements-analysis.txt` | Python dependency versions for the analysis environment. |
| `experiment/README_zh.md` | Additional Chinese-language documentation for the experiment and analysis materials. |
| `publication/fig/` | Figure materials prepared for the manuscript, including LaTeX sources and their supporting files. |
| `publication/tab/` | Manuscript and appendix table materials, including LaTeX sources. |
| `publication/supplementary_information/` | The combined Supplementary Information project and its supporting figure and table materials. |

The paths and explicit commands in this README describe the Version 3 layout. Earlier documentation and archived execution logs may refer to the original package directory names.

## 💡 Key data and design files

| File | Purpose |
|---|---|
| `experiment/implementation/design/conditions.csv` | Complete parameter settings and condition identifiers. |
| `experiment/implementation/design/run_manifest.csv` | Run identifiers, condition assignments, and recorded random seeds. |
| `experiment/implementation/design/comparisons.csv` | Prespecified condition comparisons and contrast weights. |
| `experiment/implementation/design/sensitivity_comparisons.csv` | Prespecified H2 sensitivity-index comparisons. |
| `experiment/results_v2/processed/run_metrics.csv` | One record per simulation run, with outcomes and provenance fields. |
| `experiment/results_v2/processed/condition_summary.csv` | Condition-level summaries, confidence intervals, and valid sample sizes. |
| `experiment/results_v2/processed/contrasts.csv` | Statistical comparisons between experimental conditions. |
| `experiment/results_v2/processed/sensitivity_indices.csv` | PAWN and PRCC estimates with separate uncertainty summaries. |
| `experiment/results_v2/processed/sensitivity_differences.csv` | Prespecified differences between sensitivity indices. |
| `experiment/results_v2/processed/sensitivity_diagnostics.csv` | Alternative sensitivity-analysis specifications. |

Grid experiments retain observations from steps 0–50. The sensitivity experiments retain terminal records that include outcomes accumulated within each run; complete step-by-step trajectories are not archived for those runs.

## 🕹️ Reproducing the analysis

The archived results can be inspected without rerunning NetLogo. To execute the analysis scripts, use Python 3.12 and install the dependencies from the repository root:

```bash
python3 -m pip install -r experiment/results_v2/requirements-analysis.txt
```

Run all commands below from the repository root. They use explicit paths for the current directory layout and write regenerated outputs to `experiment/reproduced/`. This keeps the archived files in `experiment/results_v2/processed/` available for comparison.

### 1. Locate and audit the raw outputs

The raw-output archive is located at `experiment/results_v2/source/outputs/`. The directory passed to `--outputs` must directly contain `execution_binding.json`, `run_status.csv`, and `attempts/`:

```bash
ABM_RAW_OUTPUTS="experiment/results_v2/source/outputs"

python3 experiment/results_v2/scripts/audit_extract.py \
    --project experiment/implementation \
    --outputs "$ABM_RAW_OUTPUTS" \
    --out experiment/reproduced
```

### 2. Recompute summaries, contrasts, and sensitivity results

```bash
python3 experiment/results_v2/scripts/summarize_contrasts.py \
    --project experiment/implementation \
    --data experiment/reproduced/processed \
    --out experiment/reproduced

python3 experiment/results_v2/scripts/analyze_sensitivity.py \
    --project experiment/implementation \
    --data experiment/reproduced/processed/run_metrics.csv \
    --out experiment/reproduced
```

Sensitivity analysis repeats the archived bootstrap procedures and can take substantially longer than ordinary condition summaries. These commands analyze existing simulation outputs; they do not launch NetLogo.

### 3. Generate analysis figures and tables

```bash
python3 experiment/results_v2/scripts/make_figures.py \
    --project experiment/implementation \
    --data experiment/reproduced/processed \
    --out experiment/reproduced/figures

python3 experiment/results_v2/scripts/make_sensitivity_figures.py \
    --data experiment/reproduced/processed \
    --out experiment/reproduced

python3 experiment/results_v2/scripts/make_tables.py \
    --project experiment/implementation \
    --data experiment/reproduced/processed \
    --out experiment/reproduced/tables
```

To regenerate these figures and tables from the supplied summaries, replace `experiment/reproduced/processed` with `experiment/results_v2/processed` in the three commands above. Input–response figures are generated separately by `analyze_sensitivity.py`.

The convenience wrapper `experiment/results_v2/scripts/run_pipeline.py` also supports the current layout. It writes regenerated outputs into `experiment/results_v2/`, including its `processed/` directory; the explicit commands above keep those supplied summaries available for comparison by writing to `experiment/reproduced/`.

The packaging script `experiment/results_v2/scripts/package_results.py` creates an archive containing `implementation/`, `results_v2/`, and the experiment README. Its default destination is `experiment/deliverables/experiment_complete.zip`; it does not include `experiment/reproduced/` or `publication/`.

## ⚙️ Running the NetLogo model

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

Replace `--dry-run` with `--execute` to run the grid jobs. Use `--phase p4` for the sensitivity-design jobs. New simulations should use a fresh output directory such as `experiment/rerun_outputs/`, preserving the archived outputs in `experiment/results_v2/source/outputs/`.

## 📑 Building the publication materials

The Python scripts generate analysis figures and tables. The materials in `publication/` contain the LaTeX layouts prepared for the manuscript, appendix, and Supplementary Information.

- Compile figure sources from their project directories, preserving the relative paths to their CSV data and style files.
- Compile `publication/tab/tables.tex` from its directory with the accompanying `sn-jnl.cls` and required LaTeX packages.
- Compile `publication/supplementary_information/supplementary_information.tex` from its directory, retaining its table sources, figure PDFs, styles, and metadata files.

Use pdfLaTeX for the supplied projects and rerun compilation as needed to resolve cross-references and contents lists. In Overleaf, select the appropriate main document for each project. Supplementary figure and table numbers are assigned by the compiled document and may differ from the legacy source filenames.

## 🔭 Research scope

The model evaluates governance mechanisms under specified network structures, parameter ranges, and input distributions. It is not calibrated to predict outcomes for a particular social media platform or jurisdiction.

Wrongful interventions contribute to exposure and workload measures but do not delete accounts or links or otherwise feed back into diffusion. State-responsive auditing uses the true pollution count before review, which is an idealized information assumption. Sensitivity rankings describe the specified experimental design and should not be interpreted as returns to equal-cost policy changes.

## 📍 Citation

If you use the model, data, or results in academic work, please cite the associated paper. 

- Full publication details and a DOI will be added after publication. Please also identify the repository version or commit used in your work.

## ✅ License

This project is distributed under the MIT License. See `LICENSE` for the license text and applicable terms.

## 🌻 Acknowledgments

Special thanks to my advisor, colleagues, and friends for their guidance and support throughout the design, implementation, and analysis of this project.

**Jingyu Lin**  
Last updated: September 28, 2026
