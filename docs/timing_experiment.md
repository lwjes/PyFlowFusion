# PyFlowFusion3 用例耗时统计方案

## 1. 目标

本方案用于在 `PyFlowFusion3/` 中统计单个用例的执行耗时，并满足下面三个约束：

- 每个用例最多执行 10 秒。
- 总共执行 10000 个用例。
- 输出每个用例的耗时明细，并在运行结束后汇总到固定时间桶。

为了降低对现有主流程的影响，本方案不修改 `flowfusion/` 核心逻辑，只在 `configs/`、`scripts/` 和 `docs/` 下新增文件。

## 2. 方案总览

核心思路是把 `config.cpython.fuzz_python_bin` 从真实 CPython 解释器替换为一个计时代理：

```text
flowfusion.main
  -> case_timer.py
     -> real CPython
```

`case_timer.py` 负责三件事：

1. 接收 `main.py` 传入的原始用例路径。
2. 转发给真实 CPython 执行。
3. 用单调时钟记录开始时间、结束时间和总耗时，并把结果追加写入 `case_timing.csv`。

## 3. 新增文件

### 3.1 `configs/timing_10000.py`

作用：

- 把 `fuzz_python_bin` 指向计时代理 `scripts/case_timer.py`。
- 把 `runtime.stop_after` 固定为 `10000`。
- 把 `runtime.case_timeout` 固定为 `10`。
- 把 `runtime.pending_timeout` 设为 `0`，避免批次超时提前截断实验。
- 关闭覆盖率采样，避免统计实验期间引入额外干扰。

### 3.2 `scripts/case_timer.py`

作用：

- 作为真正被 `main.py` 调起的执行入口。
- 内部再去启动真实 CPython。
- 在正常结束、崩溃、失败、语法错误、跳过和超时时都写一条 CSV 记录。

关键设计点：

- 使用 `time.monotonic_ns()` 统计耗时，避免系统时间跳变影响结果。
- 代理内部设置一个略小于 10 秒的超时阈值，默认比外层少 `150ms`。
  - 这样即便用例超时，代理也有机会先写完 CSV，再把结果返回给 `main.py`。
- 对“同一个用例的多次解释器调用”做会话合并。
  - `main.py` 在缺资源时会补齐依赖并重试同一个用例。
  - 代理用 `workspace/timing_record/<run>/inflight/*.json` 保存中间状态。
  - 只有当该用例真正结束时，才向 `case_timing.csv` 追加一条最终记录。

### 3.3 `scripts/run_10000_timing.sh`

作用：

- 为本次实验创建独立的运行目录。
- 清理 `tmp_dir`、`py_fused`、`bugs`、`fixme`，保证结果干净。
- 导出代理需要的环境变量。
- 启动 `python3 -m flowfusion`。
- 在主流程结束后自动调用 `summarize_case_timing.py` 生成汇总结果。

### 3.4 `scripts/summarize_case_timing.py`

作用：

- 读取 `case_timing.csv`。
- 统计各耗时桶的数量和占比。
- 统计 `ok / failure / crash / syntax / skip / timeout` 分布。
- 计算 `min / avg / p50 / p90 / p99 / max`。
- 输出 `summary.json` 和 `summary.md`。

## 4. 运行时目录结构

本方案不要求预先在仓库中手工维护这些目录，脚本会在运行时自动创建：

```text
workspace/
  timing_record/
    20260522_153000/
      case_timing.csv
      summary.json
      summary.md
      run.log
      meta.env
      inflight/
        <case_key>.json
```

说明：

- `case_timing.csv`：每个用例一行明细。
- `summary.json`：适合后续图表或论文脚本读取。
- `summary.md`：适合人工阅读。
- `run.log`：本轮 `python3 -m flowfusion` 的标准日志。
- `meta.env`：记录本轮实验实际使用的配置和解释器路径。
- `inflight/`：用于同一用例多次重试时保存临时会话状态。

## 5. 时间桶定义

为了避免边界歧义，桶定义明确为：

- `<1s`：`t < 1.0`
- `1-3s`：`1.0 <= t < 3.0`
- `3-5s`：`3.0 <= t < 5.0`
- `5-7s`：`5.0 <= t < 7.0`
- `7-9s`：`7.0 <= t < 9.0`
- `9-10s`：`9.0 <= t < 10.0`
- `timeout`：代理或主流程判定该用例超时

这里把 `timeout` 单独统计，而不是强行塞进 `9-10s`，因为“正常在 10 秒内完成”和“被超时机制强制终止”是两种不同结果。

## 6. `case_timing.csv` 字段

每一行包含下面这些字段：

- `case_key`：用例路径的 SHA1 哈希，用于唯一标识当前用例。
- `testcase_path`：本轮实际执行的用例路径。
- `start_iso`：第一次尝试该用例时的开始时间。
- `end_iso`：最终完成该用例时的结束时间。
- `duration_ms`：从第一次执行到最终完成的总耗时，单位毫秒。
- `bucket`：按总耗时映射后的时间桶。
- `result`：最终结果类型，可能为 `ok`、`failure`、`crash`、`syntax`、`skip`、`timeout`。
- `returncode`：代理返回给 `main.py` 的退出码。
- `attempts`：该用例在代理层实际调用真实解释器的次数。
- `timed_out`：是否命中代理内部超时，`1` 表示是，`0` 表示否。

## 7. 与现有流程的关系

本方案不改动 `flowfusion/main.py`，而是利用它现有的配置入口：

- `fuzz_python_bin`：替换成计时代理。
- `stop_after`：直接控制执行上限。
- `case_timeout`：继续保留 10 秒主约束。

因此它对当前主循环、归档逻辑、异常分类逻辑和覆盖率逻辑的侵入性都很低。

## 8. 使用方法

### 8.1 默认运行

在 `PyFlowFusion3/` 根目录执行：

```bash
bash scripts/run_10000_timing.sh
```

### 8.2 指定真实解释器

默认真实解释器是 `workspace/python-cov/python`。如果要切到 sanitizer 构建，可以这样执行：

```bash
FLOWFUSION_REAL_PYTHON_BIN="$PWD/workspace/python-san/python" \
bash scripts/run_10000_timing.sh
```

### 8.3 只做汇总

如果 `case_timing.csv` 已经存在，也可以单独重跑汇总：

```bash
python3 scripts/summarize_case_timing.py --run-dir workspace/timing_record/<run_id>
```

## 9. 已知折中

为了保证代理能在外层 10 秒超时之前把 CSV 写完，代理内部默认会提前 `150ms` 终止真实解释器。

这意味着：

- 极少数本来会在 `9.85s ~ 10.0s` 完成的用例，可能被保守地计为 `timeout`。
- 这个偏差只影响最靠近 10 秒边界的一小段区间。

如果后续要进一步压缩这部分误差，可以把 `FLOWFUSION_TIMER_MARGIN_MS` 再调小，但要同时承担“外层先杀代理、导致漏记”的风险。
