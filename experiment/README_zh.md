# 实验数据与分析代码

本目录对应模型 `v2.0-design-v1.0`、3,195 个配置，每个配置 30 次独立运行，共 95,850 次正式运行。其中网格实验为 195 个配置、5,850 次运行，全局敏感性实验为 3,000 个配置、90,000 次运行。

## 文件位置

以下路径相对于本 `experiment/` 目录。

| 路径 | 内容 |
|---|---|
| `implementation/model/` | NetLogo 模型入口及其加载的模型源码 |
| `implementation/design/` | 参数配置、运行种子、LHS 矩阵、预设比较及设计元数据 |
| `implementation/jobs/` | 实验批次及 BehaviorSpace XML |
| `implementation/scripts/` | 设计生成及实验执行程序 |
| `implementation/validation/` | 模型与执行器的独立小批验证记录 |
| `results_v2/source/outputs/` | 正式实验原始输出、实际运行状态和来源记录 |
| `results_v2/processed/` | 运行指标、条件及轨迹汇总、比较、敏感性分析及 bootstrap draws |
| `results_v2/scripts/` | 数据审计、分析、原版绘图、制表及打包程序 |
| `results_v2/audit/` | 核验记录、数据字典及来源校验值 |
| `results_v2/validation/` | 原分析图的历史检查记录 |
| `results_v2/requirements-analysis.txt` | 分析依赖版本 |
| `SHA256SUMS.txt` | 当前发布包的文件校验清单 |

本精简包不预先包含原分析版的 `figures/`、`plot_data/` 和 `tables/`；这些目录由程序重新生成。分析程序输出数值数据、图表和 JSON/CSV 验证记录，不自动生成中文结果报告或论文修改建议。旧合并图册及其专用脚本不再包含。

论文最终排版图表及 Supplementary Information 放在仓库中与 `experiment/` 并列的 `publication/` 目录。该目录单独上传，不包含在本实验压缩包内。分析程序生成的原版图表与论文最终排版可能不同。

## 数据口径

1. 相同条件跨模块复用同一组 30 次结果。不同配置具有相同 `replicate_id` 不代表配对实验。
2. `E_mean` 是每次运行 step 1–50 的平均效果，排除 step 0。`O_final` 是截至第 50 步至少遭受一次误伤的独立账号比例，不是累计 FP 事件数。
3. `PR_final` 先在每次运行计算，再对有定义的运行求均值；分母为零记为缺失值，汇总同时报告有效样本量。
4. 条件均值采用运行间 Student-t 区间。预设线性比较先合并相同配置的权重，再使用独立条件方差和 Welch–Satterthwaite 自由度。区间未经裁剪，均为逐项区间，不作多重性调整；跨零不表示等效。
5. P4 对每种治理及每个初始污染水平使用 500 个 LHS 点，每点响应为 30 次运行的均值。主分析为 PAWN、10 个固定分箱及 KS 中位数；PRCC 为补充分析。行 bootstrap 稳定性区间与点内 Monte Carlo 区间分别报告，不合并。
6. E、O、PR 使用百分数尺度，其差值为百分点；敏感性指数无量纲；累计工作量的单位为审核次数。

## 复现分析

从仓库根目录执行；如果已经进入 `experiment/`，第一行改为 `cd results_v2`：

```bash
cd experiment/results_v2
python3 -m pip install -r requirements-analysis.txt
python3 scripts/run_pipeline.py
```

该命令审计和分析保存的原始输出，不调用 NetLogo。敏感性分析为两种 bootstrap 各 1,000 次重抽，可能耗时较长。生成结果写入 `results_v2/` 下相应目录，原始输出保持不变。

使用现有处理结果重新生成原版图表：

```bash
python3 scripts/run_pipeline.py --figures-only
```

该选项读取 `processed/` 中的现有统计结果和 `implementation/design/` 中的设计信息，自动创建图表输出目录，不重新计算完整敏感性分析。Matplotlib 直接生成图形 PDF；如需编译分析表册，安装所需 LaTeX 环境后加上 `--compile-tables`。

重新执行模拟的方法见 `implementation/README_zh.md`，使用 NetLogo 6.4.0 及 NW 扩展。模型入口为 `implementation/model/ABM_revision_v2.0.nlogo`，须保持其与 `.nls` 源码的相对位置。

## 历史记录与文件校验

`implementation/` 中的设计和小批验证文档记录正式实验之前的状态，因此部分文档仍写有“待运行”或“尚未启动”；`design/run_manifest.csv` 也保留原始 `planned` 状态。正式运行的实际完成情况见 `results_v2/source/outputs/run_status.csv` 和 `results_v2/audit/data_audit.json`。历史审计或图形检查中提到的旧图册、旧输出文件不表示本精简包仍包含这些衍生文件。

2026-09-27 整理检查确认：324 个正式原始输出文件、14 个处理结果文件，以及模型、任务和设计文件，均与此前核查的版本逐字节一致。本发布包补回了四份已有设计元数据，并整理了目录、说明、打包程序和校验清单。移除文字报告输出后，重新执行常规统计汇总进行验证，五份 CSV 与已有结果逐字节一致；敏感性脚本通过代码结构比对确认计算逻辑保留，未重新执行 NetLogo 或全量敏感性 bootstrap。

本发布版移除了四处自动中文报告输出，并保留相应的统计计算、检查条件和机器可读记录：数据审计信息写入 `results_v2/audit/data_audit.json`，统计汇总验证信息写入 `results_v2/audit/statistics_validation.json`，敏感性验证信息写入 `results_v2/processed/sensitivity_analysis_checks.json`，模型小批验证信息写入 `implementation/validation/model_validation.json`。图注和表注仍保留，作为图表的正常说明。

已保存的历史 JSON 中的脚本哈希继续对应当时生成这些结果的脚本，没有改写为清理后的哈希。移除文字输出会改变脚本文件哈希，但统计函数、抽样顺序和随机种子逻辑保持不变；重新执行时生成的验证 JSON 会记录清理后的脚本版本。

分析依赖清单保持原样；其中 pypdf、reportlab 是历史图册依赖，当前分析入口不使用。既有审计和小批验证文档、`audit/atlas_inventory.json` 作为历史记录保留。

在 `experiment/` 目录核验发布文件：Linux 使用 `sha256sum -c SHA256SUMS.txt`，macOS 使用 `shasum -a 256 -c SHA256SUMS.txt`。

在 `results_v2/` 内运行 `python3 scripts/package_results.py` 可重新打包。默认输出为 `experiment/deliverables/experiment_complete.zip`，包含当前实验文件及新的根目录校验清单，不包含并列的 `publication/`。若先重新绘图再打包，新生成的衍生文件也会包含在内。

## 模型解释边界

误伤只计入代价，不删除节点、不改变边，也不反馈传播状态。P3 使用审核前真实污染量调整工作量，未建模现实举报、预筛选或外生污染。P4 敏感性排序限定于所设参数范围和分布，不直接表示现实中等成本投入的优先级。
