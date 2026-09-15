# Dynamic Evaluation of Governance Strategies for Mitigating Social Media Data Pollution: An Agent-Based Modeling Approach

This repository contains the simulation model, experimental data, analysis files, and figures associated with the study:

**Dynamic Evaluation of Governance Strategies for Mitigating Social Media Data Pollution: An Agent-Based Modeling Approach**

The study uses agent-based modeling (ABM) to simulate the diffusion of data pollution on social media networks and to evaluate different governance strategies, including legal intervention and platform self-regulation. The model is implemented in **NetLogo**, with batch experiments conducted using **BehaviorSpace**.

## 📌 Repository Structure

### Branches

The `main` branch contains the latest version of the simulation model, experimental data, analysis files, and manuscript figures.

The `Version-1` branch preserves an earlier version of the project, including the pre-revision model and associated experimental files, for reference.

### Main_Newest

- `data/` contains raw experimental outputs exported from NetLogo BehaviorSpace.
- `data_analysis/` contains processed datasets and analysis files used for result interpretation and figure preparation.
- `exp/` contains the NetLogo model and supporting experiment code.
- `fig/` contains the figures used in the current manuscript.

## ⚙️ How to Run the Simulation

1. Install **NetLogo 6.4.0** or a compatible later version.
2. Open the `.nlogo` model file in the `exp/` folder.
3. Use NetLogo's built-in **BehaviorSpace** tool to run the relevant batch experiments.
4. Export the simulation outputs as `.csv` files.
5. The corresponding raw and processed data can be found in the `data/` and `data_analysis/` folders.

Because the model includes stochastic processes, the reported results are based on repeated simulation runs and aggregated outcomes rather than individual trajectories.

## 💡 Experiment Organization
The repository includes three groups of experiments.
### Main experiments
`exp1–exp3` provide the baseline, legal-intervention, and platform self-regulation results used for the main analysis.
### Comparative and sensitivity experiments
`exp4` and `exp5` examine comparative governance performance and parameter sensitivity under different experimental conditions.
### Robustness experiments
`exp6` evaluates the model under alternative network topologies, while `exp7a` and `exp7b` examine the robustness of the results under different network scales.


## 📑 Research Scope

This project focuses on:

- the diffusion of data pollution in social media networks;
- agent-based modeling of governance interventions;
- comparative evaluation of legal intervention and platform self-regulation;
- sensitivity and robustness analysis under different governance and network conditions.

## 🖇️ Citation

If you use the model, data, or results from this repository in academic work, please cite the associated paper.

Full citation information will be added after publication.

## ✅ License

This repository is distributed under the MIT License. You are free to copy, modify, and distribute the content with proper attribution and inclusion of the license notice. See `LICENSE` for details.

## 🌻 Acknowledgments 

Special thanks to my advisor, colleagues, and friends for their guidance and support throughout the design, implementation, and analysis of this project. 

Thanks for your reading.




**Jingyu Lin**  
Last updated: September 2026
