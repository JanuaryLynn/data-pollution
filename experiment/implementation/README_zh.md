# ABM 返修：统一模型与完整实验任务

模型版本：`v2.0-design-v1.0`。研究设计：`design-v1.0`。启动脚本修订：`console-launcher-v2`（2026-09-22）。

本包完成统一模型代码、完整参数配置、对照复用关系和运行清单，供本轮重新实验使用。正式研究任务共 **3,195 个配置，每配置 30 次，共 95,850 次**。`run_manifest.csv` 是冻结的任务定义，所有正式任务初始状态为 `planned`。小批诊断与正式研究数据分开保存。

## 先看哪些文件

| 文件 | 用途 |
|---|---|
| `model/exp_code_v2.0.nls` | 唯一模型代码源，包含全部 21 个参数和过程 |
| `model/ABM_revision_v2.0.nlogo` | NetLogo 入口，通过相对路径加载同目录 `.nls` |
| `design/conditions.csv` | 3,195 行完整配置；每行绑定 21 个参数 |
| `design/condition_groups.csv` | 每个配置属于哪些实验模块及对照组 |
| `design/run_manifest.csv` | 95,850 个运行身份、种子、输出模式和版本校验信息 |
| `design/lhs_legal.csv`、`lhs_platform.csv` | 已归档的两个 500 行 LHS 设计，包含采样值和整数容量 |
| `design/comparisons.csv` | H1/H3 及补充比较的条件编号、权重和指标 |
| `design/sensitivity_comparisons.csv` | H2 的 9 个敏感性指数差定义 |
| `jobs/` | 按完整配置绑定的 BehaviorSpace XML 与批次索引 |
| `scripts/` | 设计生成、任务生成和执行/续跑程序 |
| `validation/` | 验证程序、诊断结果和最终验收说明 |
| `protocol/ABM_step1_protocol.json` | 第一阶段的冻结设计记录 |

更详细的 CSV 字段和计数见 `design/README.md`。本包尚不包含正式实验结果、统计分析程序或新版论文图表。

## 打开模型

使用 **NetLogo 6.4.0 及其 NW 扩展**。解压后保留目录结构，打开 `model/ABM_revision_v2.0.nlogo`，不要将它和 `.nls` 分开。

任务 XML 使用 6.4 新增的子实验语法逐行绑定配置。执行方式可对照 [NetLogo 6.4.0 官方 BehaviorSpace 手册](https://ccl.northwestern.edu/netlogo/6.4.0/docs/behaviorspace.html)。

在 Command Center 中可以逐行执行一个交互检查：

```netlogo
set-defaults
set treatment "legal"
setup
repeat 50 [ go ]
```

`set-defaults` 是交互初始化入口；`setup-fresh` 等于重设默认值后 setup，默认无治理。正式 XML 使用完整显式参数，不调用这两个默认值入口。若把 `.nls` 全部粘贴到其他模型的 Code Tab，应删除该模型原有的重复代码和旧实验参数定义；推荐直接使用本包 `.nlogo`。

## 任务安排

| 部分 | 配置数 | 运行数 | 保存方式 |
|---|---:|---:|---|
| 原实验 P1/P2 | 96 | 2,880 | step 0–50 轨迹 |
| P3 | 9 | 270 | step 0–50 轨迹 |
| P5 | 36 | 1,080 | step 0–50 轨迹 |
| P6 新增非对角条件 | 54 | 1,620 | step 0–50 轨迹 |
| **网格合计** | **195** | **5,850** | **298,350 行** |
| P4 法律 | 1,500 | 45,000 | 每次最终记录，含运行内均值 |
| P4 平台 | 1,500 | 45,000 | 每次最终记录，含运行内均值 |
| **总计** | **3,195** | **95,850** | **388,350 行正式观测** |

相同完整配置只运行一组 30 次，由模块映射供多张图表复用。P6 对角线已经包含在原扫描中。旧 v1.8 的 10 次结果不合并到新版正式数据。

每次模拟种子为 `20260922 + 1000 * condition_id + replicate_id`，最大为 23,455,952。相同重复编号不表示跨配置配对或共用同一张网络。

## 执行与续跑

以下命令都在解压后的本包根目录执行。Mac 优先使用安装目录中的 `NetLogo_Console`，它通过 NetLogo 自带的 Java 启动，不依赖系统单独安装的 Java，也不需要寻找 `bin/java`。这是 [NetLogo 6.4 官方推荐的个人电脑启动方式](https://ccl.northwestern.edu/netlogo/6.4.0/docs/behaviorspace.html#how-to-use-it)。保留路径两端的引号。

```bash
ABM_NETLOGO="/Applications/NetLogo 6.4.0/NetLogo_Console"
python3 validation/validate_model.py --netlogo "$ABM_NETLOGO"
```

等待校验完成，确认输出 `"status": "passed"` 后再执行下文。若报错，查看 `error` 指定的 `validation/work/*.log`。命令中心中的交互检查成功，不等于命令行校验已通过。

`console-launcher-v2` 同时更新了 `validation/validate_model.py` 和 `scripts/run_experiments.py`；两个脚本都会自动给 `NetLogo_Console` 加上 `--headless`，并从 NetLogo 安装目录启动子进程，以便 Mac 控制台找到 `.app` 内的配置。模型、实验 XML、CSV 和日志都使用绝对路径，仍保存在实验包下。不要把 `--headless` 拼入启动器路径。原来的 `netlogo-headless.sh` 方式仍支持，但需要可用的命令行 Java。`--netlogo-headless` 参数名保留兼容，它也接受 `NetLogo_Console`。新开终端时重新设置 `ABM_NETLOGO` 并进入实验文件夹即可。若校验时 NetLogo 退出失败，结果会附带 `runtime_log_tail` 显示本次日志末尾的具体错误。

执行现成任务只需要 Python 标准库和 NetLogo；只有重新生成 LHS 设计时才需要所附版本的 NumPy/SciPy。模型、设计、种子和实验 XML 均未因本次启动修复而改变。若已经开始正式任务，更新执行器会触发原有的版本绑定保护；不要删除该保护记录。

先预览网格任务，不启动模拟：

```bash
python3 scripts/run_experiments.py --netlogo-headless "$ABM_NETLOGO" --phase grid --dry-run
```

正式执行时加入 `--execute`。可先限制一个批次，以确认本机环境、输出和耗时：

```bash
python3 scripts/run_experiments.py --netlogo-headless "$ABM_NETLOGO" --phase grid --threads 2 --limit-batches 1 --execute
```

完成网格后，再运行 P4：

```bash
python3 scripts/run_experiments.py --netlogo-headless "$ABM_NETLOGO" --phase grid --threads 2 --execute
python3 scripts/run_experiments.py --netlogo-headless "$ABM_NETLOGO" --phase p4 --threads 2 --execute
```

执行器将运行状态另存于输出目录。重复执行同一命令时检查已有有效数据，再为缺失任务生成同身份、同种子的续跑任务；每次尝试使用独立原始 CSV 和日志。进程退出不等于实验成功，仍需核对运行身份、步数和计数等。不要手动把冻结清单中的 `planned` 全部改成 `completed`。

改变模型代码或配置后，不在原结果目录中继续混跑；执行器会核查版本与文件校验值。重新生成任务不代表完成任何模拟。发现合法但极端的结果也不能擅自删除或换种子。

## 输出的解释

E、O、PR 均采用 0–100 尺度；差值用百分点。`mean-effectiveness` 和 `mean-net-effectiveness` 只统计完成后的 step 1–50，step 0 的运行均值是 `NA`。`audit-load` 是平台容量上限；P3 实际工作量看 `step-reviews`，不能用容量上限替代。

法律输出的干预时点为 step 1、1+τ、…，不是首次等待 τ 步后才干预。`legal-action-opportunities` 包括覆盖为 0 的到期时点；`active-review-steps` 只计算实际审核人数大于 0 的步骤。

`over-removal-count` 是曾经至少一次受误伤的独立账号数；`cumulative-fp` 是误伤事件数，两者不能互换。`PR_final` 后续由每次运行累计 TP/FP 得到，再对有效运行求均值，同时报告有效次数。

## 再生成及版本记录

本包已经提供完整配置与任务，通常无需重新生成。需要核验时先查看：

```bash
python3 scripts/generate_design.py --help
python3 scripts/build_jobs.py --help
python3 validation/validate_model.py --help
```

设计生成器默认使用归档 LHS，保护既有配置身份；新设计应写入新的设计目录。随机种子不能替代保存实际采样矩阵和依赖版本。冻结协议中的 `implementation_status` 记录第一阶段当时的状态，不代表本包现状；本包实际验证结论以 `validation/VALIDATION_REPORT.md` 为准。

本次实际采样明确使用 SciPy 1.17.0 的 `LatinHypercube(rng=numpy.random.default_rng(seed))`。此前方案中的抽样预览仅用于检查数量与映射；本次归档的 `lhs_*.csv` 才是后续运行的固定参数向量，不以预览的最小值、最大值作为运行输入。

小批诊断均为程序验证，不能作为正式 30 次重复的替代或与正式原始输出混用。
