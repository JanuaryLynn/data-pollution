# 实验配置与运行清单

这是一份待运行的设计归档，不包含新的模拟结果。总计 3,195 个完整条件，每个条件 30 次独立运行，共 95,850 次。

| 文件 | 用途 |
|---|---|
| `conditions.csv` | 每行一个完整条件；含 21 个模型参数、条件编号和配置哈希 |
| `condition_groups.csv` | 条件与实验模块之间的多对多对应关系，保留共享对照 |
| `run_manifest.csv` | 每行一次预定运行；含种子、状态、输出方式、预期记录数和来源哈希 |
| `lhs_legal.csv`、`lhs_platform.csv` | 每类治理各 500 个实际 LHS 向量及单位区间抽样坐标 |
| `lhs_metadata.json` | LHS 生成环境、随机数调用方式、种子和归档矩阵哈希 |
| `comparisons.csv` | 预定比较的长表，每行是一个条件均值对应的权重项 |
| `sensitivity_comparisons.csv` | H2 的 9 个 PAWN 敏感性指数差值；单独存储，不与条件均值对比混用 |
| `design_metadata.json` | 数量、版本、文件哈希、字段和分析约定 |
| `design_validation.json` | 生成时对配置、种子、比较和 LHS 分层的检验结果 |

## 运行时如何读取

以 `run_manifest.csv` 为任务列表，通过 `condition_id` 连接到 `conditions.csv`，并确认两边 `configuration_hash` 一致。一次性设置该行的全部 21 个模型参数，再设置身份变量：

| CSV 列 | NetLogo 全局变量 |
|---|---|
| `condition_id` | `condition-id` |
| `replicate_id` | `replicate-id` |
| `seed` | `run-seed` |

21 个参数列使用模型中的连字符名称。运行身份、输出方式及版本信息不属于这 21 个科学参数。不得把不同行的 LHS 参数或对角线 TPR/TNR 分别展开成笛卡尔积。BehaviorSpace 在显式安排 30 个重复编号时使用 `repetitions="1"`。

`condition_id` 为 1—3,195；`replicate_id` 为 1—30。种子固定为 `20260922 + 1000 * condition_id + replicate_id`。不同条件即使重复编号相同，也不属于同网络的配对模拟。失败任务应按原身份与种子重试。

`status` 初始全部为 `planned`；运行后该预定清单仍保持不变，实时状态另存于 `outputs/run_status.csv`。`raw_output_path` 初始为空，因为此时尚无模拟输出。执行器保存每个批次各次尝试的 CSV，实际路径与批次内运行号见状态表中的 `source_csv`、`behavior_run`；通过 `jobs/job_index.csv` 中的条件成员关系找到批次，再用条件编号和重复编号识别具体运行。本清单不承诺为每次运行单独生成 CSV。仅存在运行清单或 XML 文件不表示模拟完成。

## 输出方式

前 195 个条件属于网格实验，使用 `trajectory`，记录第 0—50 步，合计 298,350 行。其余 3,000 个条件属于 P4，使用 `final`，每次运行记录一行最终结果及 1—50 步的内部累计均值，合计 90,000 行。总预期记录数为 388,350，不包括 CSV 表头或 BehaviorSpace 元数据。

`E_mean`、`net_E_mean` 排除第 0 步。E、O、PR 使用 0—100 的尺度。PR 的分母 `cumulative_TP + cumulative_FP` 为零时，分析值为缺失；汇总报告有效次数，不能将缺失当作 0。

## 条件与分组

条件按冻结协议模块顺序首次出现时编号。每模块以 p0 为外层循环，治理主体其次，各轴按照协议 JSON 的列出顺序展开。最后依次加入法律 P4、平台 P4，各自同样以 p0 为外层、`lhs_point_id` 为内层。同一完整参数行只运行一次，复用其 30 次结果。

`condition_groups.csv` 因此有 3,264 行成员关系，大于 3,195 个条件。P3 的 `fixed_workload_control` 复用平台基准；P5 的 `high_coverage_reference` 复用法律覆盖 70% 和平台覆盖 75% 的 targeted/random 条件；P6 对角线使用 `symmetric_accuracy_reference`。`new_in_module` 仅表示该行参数是否在首次处理该成员关系时新建条件。

P4 保留连续覆盖率的完整精度；`review_capacity_at_N1000` 记录换算为人数后的半向上取整结果。法律 τ 根据 `1 + floor(20 * u)` 转换，各整数值恰有 25 个 LHS 点。每组 500 个向量在 p0 为 10、30、50 时复用，但三组的模拟种子不同。

## 比较清单

按 `comparison_id` 和 `outcome` 对 `comparisons.csv` 分组，计算 `sum(weight × condition_mean)`。H1 共 12 个四项交互对比；H3 共 15 组同时报告 E/O 的两项对比。H3 的两个结局共用一个比较编号。P3、P5、P6、拓扑和规模比较亦已绑定到确切的条件编号。P5 额外保留 6 个高覆盖参考比较，供描述性对照使用。

同一条件在多个比较中重复出现时应保留协方差；联合 bootstrap 时每个条件只重抽一次，且每次运行的 E/O 保持一起。`primary_hypothesis=true` 只标记 H1/H3 的预定直接比较，H2 另见敏感性指数清单。未预定方向的项目使用 `expected_sign=unspecified`；它不意味着预期零差异。

`cumulative_reviews` 与 `clean_review_exposure` 的差值单位为审核次数；其他比较列的单位为百分点。`clean_review_exposure = cumulative_TN + cumulative_FP`。无治理组的 PR 通常不可估计，相关比较应保留为缺失并说明原因。

## 可复现生成与保护

在项目根目录运行 `python scripts/generate_design.py`，默认读取并校验当前归档 LHS，不重新抽样。首次生成新目录须显式使用 `--new-design --output NEW_DIR`。不能在既有设计上使用 `--new-design`。生成器拒绝覆盖含有任何非 `planned` 状态的运行清单；已有条件编号、参数值、配置哈希或种子发生变化时亦拒绝覆盖。一旦默认 `outputs/` 中存在执行绑定或运行状态记录，同样拒绝重生。自定义输出目录的后续执行还由执行器核对设计哈希，防止继续执行与既有记录不相容的设计。

首次归档采用 NumPy 2.3.5、SciPy 1.17.0，调用 `LatinHypercube(..., rng=numpy.random.default_rng(seed))`。实际矩阵及其哈希是复现依据，不能仅凭相同整数种子与不同版本或 `seed=` 调用方式假定得到相同矩阵。

模型源码定稿后重新生成仍全为 `planned` 的清单，可以补齐或更新模型源码哈希；此操作保持条件、抽样矩阵和运行种子不变。开始运行后应通过执行器维护状态，不再覆盖清单。修改实验设计须另建版本并记录原因。
