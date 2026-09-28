# 补充图 S1–S4 数据与绘图映射核查

结果：**PASS**。33 份绘图 CSV、222 条图示结果记录（216 个唯一 condition_id/outcome、90 个唯一条件），共 4 个 TeX 文件。

逐字段比对正式 condition_summary.csv；条件参数独立取自正式 run_metrics.csv。核对原始数值、缩放后均值及区间端点、误差长度、参数坐标、面板顺序、162 个热图硬编码数值标签与 12 个 nPR 标签。

容差：绝对 1e-10 + 相对 1e-12×来源绝对值。最大绝对偏差：{'summary_fields': 0.0, 'metadata_fields': 0.0, 'plot_transform_fields': 3.552713678800501e-15, 'hardcoded_labels': 0.0}

## 单位与语义

- O_final / O(50) 是截至第50步曾被误伤的不同账户占比（%），不是误伤审查事件次数。
- cumulative_reviews 与 clean_review_exposure 是第1–50步累计审查事件数，包含对同一账户的重复审查；plot_scale=1000 表示以千次为单位。
- PR_final 是有定义的运行级精确率均值；S1的12个精确率显示值均为 n=30、n_total=30、n_missing=0。
- S1固定模式虽记录 demand-kappa=1，但该参数在固定模式中不生效；横轴标为 Fixed 是正确的。
- S2–S4热图显示均值，格内数值保留一位小数；完整精度均值及CI端点仍保留于CSV中。
- 附件内未包含 figure_style.tex；这些独立TeX图需使用项目现有公共样式文件编译。

## 问题

未发现数据、缩放、坐标或硬编码标签错误。

运行级独立重算另见 condition_runlevel_recheck.{json,md}；未重新运行模拟。

## 运行级独立复算

从现有 run_metrics.csv 提取90个条件，每条件30次，共2,700条条件运行，run_id及seed均全局唯一；216个图示条件—指标组合对应6,480个 outcome 样本，并非6,480次独立仿真。另对未在图中显示PR的78个组合补查，共复算294个条件—指标组合。

均值、样本SD、SE及未截断的95% Student-t区间均通过。容差为绝对1e-9 + 相对1e-11×来源绝对值，以容纳正式汇总CSV保留12位有效数字的序列化舍入；最大均值偏差3.33348e-8，最大CI端点偏差4.65880e-8（原始事件计数尺度）。90个条件的PR有效n均为30。

逐运行验证 O(50)=100×distinct_wronged/N、累计审查次数=TP+FP+TN+FN、对清洁账户的审查次数=FP+TN、精确率=100×TP/(TP+FP)，全部通过。未重新运行模拟，也未从逐步原始轨迹重新构建run_metrics。
