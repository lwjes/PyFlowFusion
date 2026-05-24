# 项目目的与实验设计

本文档说明 `PyFlowFusion3` 的研究目标、实验组织方式，以及它和当前目录结构之间的对应关系。

`structure.md` 负责解释“有哪些目录和文件”，本文档负责解释“为什么要这样分层，以及各层如何配合实验”。

## 1. 项目目的

PyFlowFusion3 研究的是一套面向 CPython 测试场景的自动化模糊测试流程。当前目录结构已经收敛为：

- 一个核心包：`flowfusion/`
- 一个配置层：`configs/`
- 一个知识库层：`knowledges/`
- 一个运行工作区：`workspace/`
- 两条对照实验线：`benchmarks/`
- 一组静态图表资源：`data/image/`

这个项目要回答的核心问题是：

1. 只依赖 `Lib/test` 的已有测试，能否持续生长出新的有效测试？
2. 通过代码分析和种子融合生成的用例，是否比纯随机变异更有结构性和可执行性？
3. 在 coverage 构建和 sanitizer 构建下，生成流程是否都能稳定运行？
4. 与 `libFuzzer + fuzz_pycompile` 基线相比，当前流程在覆盖率、异常发现和可复现性上表现如何？

## 2. 整体设计

整个实验围绕 `flowfusion/` 展开，分成四个阶段：

1. 种子准备
2. 知识库构建
3. 融合与执行
4. 结果记录与对照

### 2.1 种子准备

种子来源于 CPython 源码树中的 `Lib/test`。

- `flowfusion.prepare` 复制 `test_*.py` 到 `workspace/py_seeds/`
- 同时准备 `workspace/py_deps/` 作为运行时依赖副本
- 这一步是整个流程的输入预处理层

它的作用不是生成最终结果，而是把原始测试样例整理成稳定、可复用的实验输入。

### 2.2 知识库构建

知识库由 `knowledges/` 层负责构建和维护。

- `apis.db` 记录函数、参数和调用模式
- `class.db` 记录类、方法和属性关系
- `seeds.db` 记录种子的结构化字段和 IR

这一步的作用是给后续融合和过滤提供“结构信息”，让流程不只是拼接字符串，而是尽量基于代码语义来生成新样例。

### 2.3 融合与执行

核心逻辑现在都在 `flowfusion/` 里：

- `flowfusion.main` 负责主循环、执行、分类和归档
- `flowfusion.fuse` 负责种子融合
- `flowfusion.mutator` 负责低概率变异
- `flowfusion.runtime.*` 负责执行、覆盖率、队列和资源补齐

运行时的主要工作区是 `workspace/`：

- `workspace/tmp_dir/` 放待执行队列
- `workspace/py_fused/` 放已移动出的融合样例
- `workspace/bugs/` 放 crash 样例
- `workspace/fixme/` 放 syntax error 或 failure 样例

执行过程的关键设计是：

- 先做语法检查，再执行
- 运行时发现缺失资源时尝试自动补齐
- crash、syntax error、普通 failure 分别归档

### 2.4 结果采集与对照

实验保留两条主线：

- 主流程：`flowfusion/`
- 基线流程：`benchmarks/`

对照关注的不是单次速度，而是更长期的结果质量：

- 覆盖率变化
- 有效样例数量
- 崩溃样例数量
- 失败样例数量
- 长时间运行的稳定性

## 3. 各层和目录的对应关系

### 3.1 `flowfusion/`

这是项目的唯一核心代码包，包含配置、融合、入口和运行时。

它对应的实验动作是：

- `python -m flowfusion.prepare`
- `python -m flowfusion`

### 3.2 `configs/`

这个目录控制运行方式，不参与算法本身。

- `default.py` 决定 `workspace/` 的具体子目录
- `python_san.py` 决定 sanitizer 运行方式
- `select_python.py` 用于选择解释器

### 3.3 `knowledges/`

这个目录提供实验所需的结构知识和黑名单。

- 数据库是运行后生成的
- 脚本是手工维护的
- 黑名单用于过滤不适合作为种子的样例

### 3.4 `workspace/`

这是运行时结果和中间态的统一出口。

- 这里的内容可重建
- 这里的内容通常不应该手工编辑
- 这里适合放种子、队列、结果、日志和构建树

### 3.5 `benchmarks/`

这里放对照实验，不和主流程混在一起。

- `libfuzzer_cov/` 对应 `fuzz_pycompile` 覆盖率基线
- `libfuzzer_test/` 对应回放和 GCOV 测量

### 3.6 `data/image/`

这里放静态图表资源，通常用于论文、汇报或结果展示。

### 3.7 `outputs/`

这个目录是预留出口，目前没有自动写入动作。

如果后续要放最终汇总表、论文附件或导出的图表，可以优先放这里，而不是塞回 `workspace/`。

## 4. 主要实验场景

### 4.1 覆盖率实验

目的：观察 `flowfusion` 是否能持续推动 CPython 覆盖率提升。

对应目录：

- 输入：`workspace/py_seeds/`
- 运行：`workspace/tmp_dir/`
- 采样：`workspace/cov_record/<run_id>/gcovr_snapshots/`
- 构建：`workspace/python-cov/`

对应脚本：

- `scripts/build.sh`
- `scripts/run_cov_24h.sh`

输出文件：

- `workspace/cov_record/<run_id>/gcovr_snapshots/gcovr-*.xml`
- `workspace/cov_record/<run_id>/coverage_24h.csv`
- `workspace/cov_record/<run_id>/run_24h.log`

### 4.2 Sanitizer 实验

目的：观察流程在地址/未定义行为检测下是否稳定。

对应目录：

- 运行队列：`workspace/tmp_dir/`
- 融合结果：`workspace/py_fused/`
- 崩溃输出：`workspace/bugs/`
- 失败输出：`workspace/fixme/`
- 记录：`workspace/san_record/`
- 构建：`workspace/python-san/`

对应脚本：

- `scripts/build_san.sh`
- `scripts/run_san_24h.sh`

### 4.3 libFuzzer 基线

目的：和传统基线做横向比较。

对应目录：

- `benchmarks/libfuzzer_cov/`

对应脚本：

- `benchmarks/libfuzzer_cov/build.sh`
- `benchmarks/libfuzzer_cov/prepare_pycompile_corpus.py`
- `benchmarks/libfuzzer_cov/run_pycompile_24h.sh`

### 4.4 unittest 回放

目的：在 GCOV 下测量基线语料的覆盖情况。

对应目录：

- `benchmarks/libfuzzer_test/`

对应脚本：

- `benchmarks/libfuzzer_test/build.sh`
- `benchmarks/libfuzzer_test/measure_pycompile_gcov.sh`

## 5. 结果指标

主要看这些指标：

- 覆盖率是否增长
- crash 是否真实可复现
- `fixme` 是否过多
- 每秒执行用例数
- 长跑是否稳定

如果覆盖率有增长，但大多数样例都落入 `fixme/`，说明融合或过滤还不够好。
如果 crash 很多但不可复现，说明结果稳定性还不足。
如果覆盖率、稳定性和异常发现都表现良好，才说明这套设计有效。

## 6. 推荐执行顺序

1. 构建 CPython
2. 执行 `flowfusion.prepare`
3. 构建知识库
4. 跑一次短流程验证
5. 跑覆盖率实验
6. 跑 sanitizer 实验
7. 跑 libFuzzer 基线
8. 跑 unittest 回放
9. 汇总图表和论文材料

## 7. 产物组织原则

项目现在已经按用途分层：

- `flowfusion/`：稳定源码
- `configs/`：运行配置
- `knowledges/`：知识库代码和数据库
- `workspace/`：可丢弃运行产物
- `benchmarks/`：对照实验
- `data/image/`：展示图表
- `outputs/`：最终汇总出口

这种结构的好处是，代码、实验、结果和临时文件可以彼此分开，复现时不容易互相污染。
