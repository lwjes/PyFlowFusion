# 基线实验

这个目录用于放置非核心的对照实验流程。

- `libfuzzer_cov/`：`fuzz_pycompile` 覆盖率基线
- `libfuzzer_test/`：unittest 回放和 GCOV 测量流程

每个基线都把自己的辅助脚本和运行产物放在同一个子目录下，避免和主流程源码混在一起。
