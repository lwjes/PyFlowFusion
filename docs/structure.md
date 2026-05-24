# 项目目录总说明

这份文档说明 `PyFlowFusion3` 在运行前、运行中、运行后可能出现的目录和文件，并标明它们的作用、生成时机和生成者。

说明约定：

- “手工维护”表示由开发者直接编辑，不是脚本自动生成。
- “自动生成”表示由脚本、运行模块或 Python 解释器在特定阶段创建。
- 当前 `flowfusion_app/` 已合并进 `flowfusion/`，因此文档只描述单一核心包结构。

## 1. 顶层结构

| 路径 | 作用 | 何时出现 | 由谁生成 |
|---|---|---|---|
| `flowfusion/` | 核心包，包含配置、融合、运行时、入口代码 | 仓库存在即有 | 手工维护 |
| `configs/` | 运行配置文件 | 仓库存在即有 | 手工维护 |
| `knowledges/` | 知识库构建脚本、黑名单和数据库 | 仓库存在即有；数据库为后续生成 | 手工维护 + `knowledges/build.py` |
| `scripts/` | 构建、准备、长跑和统计脚本 | 仓库存在即有 | 手工维护 |
| `benchmarks/` | 对照实验目录 | 仓库存在即有；子目录内容运行后产生 | 手工维护 + 基线脚本 |
| `data/image/` | 图表、架构图和论文插图 | 仓库存在即有 | 手工维护或手工导出 |
| `docs/` | 项目说明文档 | 仓库存在即有 | 手工维护 |
| `workspace/` | 运行时工作区，存放种子、临时队列、构建产物和结果 | 运行 `prepare`、`main`、构建或长跑脚本后创建 | `flowfusion.prepare`、`flowfusion.main`、`scripts/*` |
| `outputs/` | 预留的最终结果出口 | 当前为空；以后可手工放报告和汇总 | 暂无自动生成者 |
| `.gitignore` | 忽略规则 | 仓库存在即有 | 手工维护 |
| `README.md` | 顶层总览 | 仓库存在即有 | 手工维护 |

## 2. 核心包 `flowfusion/`

这个目录现在同时承担“核心库”和“入口编排”两类职责。

| 路径 | 作用 | 何时出现 | 由谁生成 |
|---|---|---|---|
| `flowfusion/__init__.py` | 包标记 | 仓库存在即有 | 手工维护 |
| `flowfusion/__main__.py` | `python -m flowfusion` 入口 | 仓库存在即有 | 手工维护 |
| `flowfusion/config.py` | 读取配置、解析环境变量、构造路径对象 | 仓库存在即有 | 手工维护 |
| `flowfusion/main.py` | 主 fuzz 循环、执行、归档、统计 | 仓库存在即有 | 手工维护 |
| `flowfusion/prepare.py` | 准备种子、依赖和知识库 | 仓库存在即有 | 手工维护 |
| `flowfusion/fuse.py` | 融合两个种子生成新用例 | 仓库存在即有 | 手工维护 |
| `flowfusion/mutator.py` | Python 代码变异规则 | 仓库存在即有 | 手工维护 |
| `flowfusion/dataflow.py` | AST 数据流分析 | 仓库存在即有 | 手工维护 |
| `flowfusion/fusion/__init__.py` | 融合子包标记 | 仓库存在即有 | 手工维护 |
| `flowfusion/fusion/ast_rewriters.py` | AST 重写辅助器 | 仓库存在即有 | 手工维护 |
| `flowfusion/fusion/class_assembly.py` | 类级种子组装 | 仓库存在即有 | 手工维护 |
| `flowfusion/fusion/composer.py` | 测试组合逻辑 | 仓库存在即有 | 手工维护 |
| `flowfusion/fusion/decorator_runtime.py` | 装饰器和运行时处理 | 仓库存在即有 | 手工维护 |
| `flowfusion/fusion/prelude.py` | 前导代码处理 | 仓库存在即有 | 手工维护 |
| `flowfusion/fusion/seed_filters.py` | 种子过滤、黑名单、健康检查 | 仓库存在即有 | 手工维护 |
| `flowfusion/fusion/seed_ir.py` | 种子 IR 结构与序列化 | 仓库存在即有 | 手工维护 |
| `flowfusion/fusion/seed_preparation.py` | 种子预处理和字段抽取 | 仓库存在即有 | 手工维护 |
| `flowfusion/fusion/seed_repository.py` | 种子数据库读取 | 仓库存在即有 | 手工维护 |
| `flowfusion/fusion/source_analysis.py` | 源码分析和依赖关系抽取 | 仓库存在即有 | 手工维护 |
| `flowfusion/runtime/__init__.py` | 运行时子包标记 | 仓库存在即有 | 手工维护 |
| `flowfusion/runtime/coverage.py` | 覆盖率采样、XML/CSV 解析 | 仓库存在即有 | 手工维护 |
| `flowfusion/runtime/executor.py` | 单用例执行、超时和结果分类 | 仓库存在即有 | 手工维护 |
| `flowfusion/runtime/queue_store.py` | 队列移动、归档和临时队列统计 | 仓库存在即有 | 手工维护 |
| `flowfusion/runtime/resources.py` | 缺失资源补齐和路径回填 | 仓库存在即有 | 手工维护 |

## 3. 配置目录 `configs/`

| 文件 | 作用 | 何时出现 | 由谁生成 |
|---|---|---|---|
| `configs/default.py` | 默认配置，定义项目根目录、工作区和 CPython 路径 | 仓库存在即有 | 手工维护 |
| `configs/python_san.py` | Sanitizer 运行配置 | 仓库存在即有 | 手工维护 |
| `configs/select_python.py` | 可选择解释器的配置 | 仓库存在即有 | 手工维护 |
| `configs/__pycache__/` | Python 编译缓存 | 第一次导入配置模块后 | Python 解释器自动生成 |

## 4. 知识库目录 `knowledges/`

这个目录既有源码，也有 SQLite 数据库。数据库是运行时结果，源码是手工维护文件。

| 文件或目录 | 作用 | 何时出现 | 由谁生成 |
|---|---|---|---|
| `knowledges/build.py` | 统一构建知识库：依次调用函数库、类库和种子预处理脚本 | 仓库存在即有 | 手工维护 |
| `knowledges/function.py` | 构建 `apis.db` | 仓库存在即有；执行 `build.py` 时被调用 | `knowledges/build.py` |
| `knowledges/class.py` | 构建 `class.db` | 仓库存在即有；执行 `build.py` 时被调用 | `knowledges/build.py` |
| `knowledges/seed-preprocessing.py` | 种子预处理脚本，独立运行时可生成种子清单和摘要 | 仓库存在即有 | 手工运行或 `build.py` 间接调用 |
| `knowledges/README.md` | 知识库说明 | 仓库存在即有 | 手工维护 |
| `knowledges/apis.db` | 函数与参数知识库 | 运行 `flowfusion.prepare` 或 `knowledges/build.py` 后 | `function.py` |
| `knowledges/class.db` | 类、方法和属性知识库 | 运行 `flowfusion.prepare` 或 `knowledges/build.py` 后 | `class.py` |
| `knowledges/seeds.db` | Python 种子知识库 | 运行 `flowfusion.prepare` 或 `knowledges/build.py` 后 | `seed-preprocessing.py` |
| `knowledges/*.db-journal` | SQLite 临时日志文件 | 数据库写入期间可能出现 | SQLite 自动生成 |
| `knowledges/*.sqlite` / `*.sqlite3` | 兼容性或临时数据库文件 | 手工改名或外部工具导出时可能出现 | 手工或外部工具 |

`seed-preprocessing.py` 独立运行时，常见还会生成这些文件：

- `seeds/`：生成的种子目录
- `meta/seed_manifest.csv`：种子清单
- `meta/skipped_files.json`：跳过文件列表
- `meta/summary.json`：预处理摘要

这些目录和文件出现的时机是手工执行该脚本，并指定输出目录时。

## 5. 脚本目录 `scripts/`

| 文件 | 作用 | 何时出现 | 由谁生成 |
|---|---|---|---|
| `scripts/build.sh` | 构建 coverage 版 CPython | 仓库存在即有；执行时创建 `workspace/python-cov/` | 手工运行 |
| `scripts/build_san.sh` | 构建 sanitizer 版 CPython | 仓库存在即有；执行时创建 `workspace/python-san/` | 手工运行 |
| `scripts/prepare.sh` | 准备种子、依赖和知识库 | 仓库存在即有；执行时创建多个工作区目录 | 手工运行 |
| `scripts/run_cov_24h.sh` | 24 小时覆盖率长跑 | 仓库存在即有；执行时创建覆盖率记录 | 手工运行 |
| `scripts/run_san_24h.sh` | 24 小时 sanitizer 长跑 | 仓库存在即有；执行时创建 sanitizer 记录 | 手工运行 |
| `scripts/rebuild_coverage_csv.py` | 由 `gcovr-*.xml` 重建 `coverage_24h.csv` | 仓库存在即有 | 手工运行 |
| `scripts/__pycache__/` | Python 缓存 | 执行 `rebuild_coverage_csv.py` 后 | Python 解释器自动生成 |

`scripts` 执行后常见的结果如下：

- `workspace/python-cov/`：coverage 版 CPython 构建目录
- `workspace/python-san/`：sanitizer 版 CPython 构建目录
- `workspace/py_seeds/`、`workspace/py_deps/`、`workspace/py_fused/`、`workspace/bugs/`、`workspace/fixme/`：准备和运行结果
- `workspace/cov_record/`、`workspace/san_record/`：长跑统计结果

## 6. 基线实验目录 `benchmarks/`

### 6.1 `benchmarks/libfuzzer_cov/`

| 文件或目录 | 作用 | 何时出现 | 由谁生成 |
|---|---|---|---|
| `benchmarks/libfuzzer_cov/build.sh` | 构建 `fuzz_pycompile` 所需的 coverage 版 CPython | 仓库存在即有 | 手工运行 |
| `benchmarks/libfuzzer_cov/prepare_pycompile_corpus.py` | 从 `Lib/test` 生成 libFuzzer 语料 | 仓库存在即有 | 手工运行 |
| `benchmarks/libfuzzer_cov/run_pycompile_24h.sh` | 24 小时 libFuzzer 基线长跑 | 仓库存在即有 | 手工运行 |
| `benchmarks/libfuzzer_cov/python-cov/` | coverage 版 CPython 构建目录 | 执行 `build.sh` 后 | `build.sh` |
| `benchmarks/libfuzzer_cov/bin/` | libFuzzer 可执行文件目录 | 执行 `run_pycompile_24h.sh` 后 | `run_pycompile_24h.sh` |
| `benchmarks/libfuzzer_cov/corpus/` | 活动语料目录 | 执行 `run_pycompile_24h.sh` 后 | `run_pycompile_24h.sh` |
| `benchmarks/libfuzzer_cov/corpus_seed_from_libtest/` | 从 `Lib/test` 生成的初始种子 | 执行 `run_pycompile_24h.sh` 后 | `prepare_pycompile_corpus.py` |
| `benchmarks/libfuzzer_cov/logs/` | 每轮 fuzz 日志 | 执行 `run_pycompile_24h.sh` 后 | `run_pycompile_24h.sh` |
| `benchmarks/libfuzzer_cov/meta/` | 语料和运行元数据 | 执行 `run_pycompile_24h.sh` 后 | `run_pycompile_24h.sh` |
| `benchmarks/libfuzzer_cov/artifacts/` | libFuzzer 崩溃/异常产物 | 执行 `run_pycompile_24h.sh` 后 | libFuzzer |
| `benchmarks/libfuzzer_cov/stats.csv` | 每轮统计摘要 | 执行 `run_pycompile_24h.sh` 后 | `run_pycompile_24h.sh` |
| `benchmarks/libfuzzer_cov/status.txt` | 当前运行状态 | 执行 `run_pycompile_24h.sh` 后 | `run_pycompile_24h.sh` |
| `benchmarks/libfuzzer_cov/summary.txt` | 最终结果摘要 | 每次运行结束后 | `run_pycompile_24h.sh` |
| `benchmarks/libfuzzer_cov/logs.zip` | 历史日志压缩包 | 手工压缩或旧运行残留 | 手工或外部脚本 |
| `benchmarks/libfuzzer_cov/__pycache__/` | Python 缓存 | 执行 Python 脚本后 | Python 解释器自动生成 |

### 6.2 `benchmarks/libfuzzer_test/`

| 文件或目录 | 作用 | 何时出现 | 由谁生成 |
|---|---|---|---|
| `benchmarks/libfuzzer_test/build.sh` | 构建 replay 测量用的 coverage 版 CPython | 仓库存在即有 | 手工运行 |
| `benchmarks/libfuzzer_test/measure_pycompile_gcov.sh` | 回放语料并生成 GCOV 覆盖率报告 | 仓库存在即有 | 手工运行 |
| `benchmarks/libfuzzer_test/replay_fuzz_pycompile.c` | 语料回放驱动程序 | 仓库存在即有 | 手工维护 |
| `benchmarks/libfuzzer_test/python_cov/` | coverage 构建目录 | 执行 `build.sh` 后 | `build.sh` |
| `benchmarks/libfuzzer_test/bin/` | 回放二进制目录 | 执行 `measure_pycompile_gcov.sh` 后 | `measure_pycompile_gcov.sh` |
| `benchmarks/libfuzzer_test/results/` | GCOV 结果目录 | 执行 `measure_pycompile_gcov.sh` 后 | `measure_pycompile_gcov.sh` |
| `benchmarks/libfuzzer_test/results/libfuzzer_pycompile_gcov.xml` | GCOV XML 报告 | 每次测量结束后 | `measure_pycompile_gcov.sh` |
| `benchmarks/libfuzzer_test/results/libfuzzer_pycompile_gcov_summary.txt` | GCOV 摘要 | 每次测量结束后 | `measure_pycompile_gcov.sh` |

## 7. 运行工作区 `workspace/`

这是项目运行后最主要的生成目录。它的内容一般可以删掉重建。

| 路径 | 作用 | 何时出现 | 由谁生成 |
|---|---|---|---|
| `workspace/py_seeds/` | 从 CPython `Lib/test` 复制来的 Python 种子 | 执行 `flowfusion.prepare` 后 | `flowfusion.prepare` |
| `workspace/py_deps/test/` | `Lib/test` 的副本 | 执行 `flowfusion.prepare` 后 | `flowfusion.prepare` |
| `workspace/py_deps/support_lib/` | CPython `Lib` 的副本，用于运行时补依赖 | 执行 `flowfusion.prepare` 后 | `flowfusion.prepare` |
| `workspace/py_fused/` | 已移动出的融合样例，供回放或归档 | 执行 `flowfusion.main` 时持续出现 | `flowfusion.main` |
| `workspace/tmp_dir/` | 临时队列，存放等待执行的融合样例和短期中间文件 | 执行 `flowfusion.prepare` 初始化；执行 `flowfusion.main` 时持续使用 | `flowfusion.prepare`、`flowfusion.main` |
| `workspace/bugs/` | 崩溃样例目录 | 发现 crash 后自动归档 | `flowfusion.main` |
| `workspace/bugs/<n>/case.py` | 崩溃样例本体 | 发现 crash 后生成 | `flowfusion.main` |
| `workspace/bugs/<n>/test.out` | 崩溃时输出 | 发现 crash 后生成 | `flowfusion.main` |
| `workspace/fixme/` | 语法错误或普通失败样例目录 | 发现 syntax error / failure 后自动归档 | `flowfusion.main` |
| `workspace/fixme/<n>/case.py` | 失败样例本体 | 发现失败后生成 | `flowfusion.main` |
| `workspace/fixme/<n>/test.out` | 失败输出 | 发现失败后生成 | `flowfusion.main` |
| `workspace/cov_record/` | 覆盖率记录根目录 | 执行 `flowfusion.prepare` 初始化；执行 `scripts/run_cov_24h.sh` 时创建时间戳子目录 | `flowfusion.prepare`、`scripts/run_cov_24h.sh` |
| `workspace/cov_record/<run_id>/` | 单次覆盖率长跑结果目录 | 执行 `scripts/run_cov_24h.sh` 后 | `scripts/run_cov_24h.sh` |
| `workspace/cov_record/<run_id>/gcovr_snapshots/gcovr-*.xml` | 覆盖率快照 | 覆盖率长跑过程中按时间间隔生成 | `flowfusion.main` |
| `workspace/cov_record/<run_id>/coverage_24h.csv` | 覆盖率 CSV 汇总 | 长跑结束或手工重建 CSV 时 | `scripts/run_cov_24h.sh`、`scripts/rebuild_coverage_csv.py` |
| `workspace/cov_record/<run_id>/run_24h.log` | 覆盖率长跑日志 | 执行 `scripts/run_cov_24h.sh` 后 | `scripts/run_cov_24h.sh` |
| `workspace/san_record/` | sanitizer 记录目录 | 执行 `scripts/run_san_24h.sh` 后 | `scripts/run_san_24h.sh` |
| `workspace/san_record/run_24h.log` | sanitizer 长跑日志 | 执行 `scripts/run_san_24h.sh` 后 | `scripts/run_san_24h.sh` |
| `workspace/san_record/status.txt` | sanitizer 运行状态 | 运行开始和结束时更新 | `scripts/run_san_24h.sh` |
| `workspace/san_record/summary.txt` | sanitizer 最终摘要 | 运行结束后 | `scripts/run_san_24h.sh` |
| `workspace/python-cov/` | coverage 版 CPython 构建树 | 执行 `scripts/build.sh` 后 | `scripts/build.sh` |
| `workspace/python-san/` | sanitizer 版 CPython 构建树 | 执行 `scripts/build_san.sh` 后 | `scripts/build_san.sh` |

`workspace/python-cov/` 和 `workspace/python-san/` 里通常会出现这些构建产物：

- `python` 可执行文件
- `libpython*.a` 静态库
- `*.o`、`*.gcda`、`*.gcno`、`*.gcov`
- 构建系统生成的中间目录和缓存文件

## 8. 通用自动文件

下面这些文件可能会散落在多个目录里，属于自动生成，不建议手工维护：

| 文件模式 | 作用 | 何时出现 | 由谁生成 |
|---|---|---|---|
| `__pycache__/` | Python 字节码缓存目录 | 第一次导入模块后 | Python 解释器 |
| `*.pyc` | Python 字节码文件 | 第一次导入模块后 | Python 解释器 |
| `*.log` | 长跑日志 | 运行脚本时 | 各类 shell 脚本 |
| `*.out` | 用例输出 | 测试执行后 | `flowfusion.main` |
| `gcovr-*.xml` | 覆盖率快照 | 覆盖率长跑过程中 | `flowfusion.main` |
| `*.db-journal` | SQLite 写入日志 | 数据库写入期间 | SQLite |
| `*.gcda` / `*.gcno` | 覆盖率数据文件 | 编译和执行后 | 编译器和运行时 |

## 9. `outputs/` 的定位

当前 `outputs/` 目录没有自动写入动作。它只是预留的最终结果出口，适合以后手工放：

- 最终图表
- 汇总表格
- 论文附件
- 导出的对比结果

如果后续希望让某个脚本自动写入 `outputs/`，需要再单独接一条明确的输出链路。
