这个目录保存的是用于 CPython 模糊测试的 Python 知识库。

生成文件：

- `apis.db`：由 `function.py` 根据配置好的 CPython 解释器自动构建
- `class.db`：由 `class.py` 根据配置好的 CPython 解释器自动构建
- `seeds.db`：由 `seed-preprocessing.py` 构建

快速重建：

```bash
python build.py
```

种子来源：

- `seed-preprocessing.py` 会递归读取 `workspace/py_seeds/`
- 每个 `unittest.TestCase.test_*` 方法都会生成一个种子

存储字段：

- `prelude`：模块级导入、常量和辅助函数
- `helpers`：源测试类中的非测试成员
- `configuration`：`setUp()` 语句
- `skipif`：类/方法装饰器
- `phpcode`：历史列名，出于兼容性保留，现在存放 Python 测试体语句
- `seed_ir`：结构化 JSON 种子 IR，包含基于 AST 的 prelude/helpers/configuration/body/decorators

说明：

- 变量提取和数据流分组都基于 AST
- 融合时优先使用 `seed_ir`，没有时再回退到旧的字符串列
- 由于复制过来的 CPython 测试可能保留子目录，递归扫描种子很重要
