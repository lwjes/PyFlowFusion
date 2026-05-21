# PyFlowFusion3

这是为 PyFlowFusion 模糊测试项目整理出来的工作区。
原始的 `PyFlowFusion/` 目录保持不变。

## 目录结构

```text
PyFlowFusion3/
  flowfusion/        核心融合、运行时、配置和入口代码
  configs/           运行配置与路径配置
  knowledges/        知识库构建脚本与黑名单规则
  scripts/           构建与长跑脚本
  benchmarks/        libFuzzer 和 unittest 对照实验
  data/image/        架构图和结果图
  docs/              当前整理方案说明
  workspace/         运行时生成数据
```

## 调整说明

- `flowfusion/` 现在同时包含核心库和入口编排模块。
- `workspace/` 用来集中种子、融合样例、bug、fixme 和覆盖率记录等运行产物。
- `scripts/` 用来集中构建脚本和长时间运行脚本。
- `benchmarks/` 用来集中 libFuzzer 基线和 unittest 对照实验文件。

## 运行方式

```bash
python -m flowfusion.prepare
python -m flowfusion
```

默认配置仍然依赖父级工作区里的 `cpython/` 目录。
