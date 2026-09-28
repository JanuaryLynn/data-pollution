# 合并版 Supplementary Information

本工程合并 Supplementary Tables S1–S17 与 Supplementary Figures S1–S11。当前编译结果为32页，包含一份统一目录及两个分区阅读说明。

## 使用

主文件：`supplementary_information.tex`。

Overleaf：上传本目录的全部文件，选择该文件为主文件，使用 pdfLaTeX 编译。目录和页码需要多轮编译；Overleaf通常会自动处理。

本地：安装 TeX Live/MiKTeX（含 `geometry`、`caption`、`longtable`、`microtype`、`hyperref`、`pdflscape`、`eso-pic`），然后运行：

```bash
python3 build_supplement.py
```

该脚本运行三轮 pdfLaTeX，并生成 `supplementary_information.pdf`。已提供全部独立图 PDF，合并文档无需重新绘图。

## 结构

1. `Contents`：按表格、图片两部分列出全部28项，含页码、点击跳转及PDF书签。
2. `Supplementary tables` / `Reading the tables`：简要说明条件汇总、预设比较、样本量、区间与单位。
3. Tables S1–S17：保留横向A4页面、15 mm边距和longtable续表；横页页码正常横排于底部。
4. `Supplementary figures` / `Reading the figures`：说明指标定义、敏感性设计、两类bootstrap区间及分箱响应线。
5. Figures S1–S11：保留纵向A4页面、20 mm边距。

全册连续页码，表与图各自独立从S1编号。原有表和图的引用标签均保留。

## 常用修改位置

- 文章标题、期刊、作者与通讯作者信息：`metadata.tex`。
- 两段阅读说明、总体页面设置和目录样式：`supplementary_information.tex`。
- 表格顺序和目录标题：`table_pages.tex`。
- 图的caption、顺序和简短目录标题：`figure_pages.tex`。
- 单个表的数据与排版：`tables/`。
- 单个图的绘图源码：根目录相应`.tex`；PDF在`figures/`。

本合并工程随附 `table_style.tex`：其中已移除原先独立加载的横版 `geometry`，由总文件统一管理横竖版切换。


## 内容保留与验证

17个原始表格源码和11张独立图PDF完整保留。图文件的长caption内容不变，只增加简短目录条目。`data/`含两套工程的数据；此前核查记录在`validation/tables/`和`validation/figures/`。本次合并核查另存于`validation/merge_check.json`。
