import ast
import builtins
from random import choice


BUILTIN_NAMES = set(dir(builtins))


def replace_random_occurrence(text, old, new):
    positions = []
    start = 0
    while True:
        start = text.find(old, start)
        if start == -1:
            break
        positions.append(start)
        start += len(old)

    if not positions:
        return text

    random_pos = choice(positions)
    return text[:random_pos] + new + text[random_pos + len(old):]


class _AttributeMethodRenamer(ast.NodeTransformer):
    def __init__(self, mapping, rename_top_level_names=False, helper_methods=None, rewrite_helper_loads=False):
        self.mapping = mapping
        self.rename_top_level_names = rename_top_level_names
        self.helper_methods = helper_methods or set()
        self.rewrite_helper_loads = rewrite_helper_loads
        self.scope_depth = 0
        self.class_depth = 0
        self.attribute_value_depth = 0
        self.local_rename_stack = []

    def _collect_direct_local_renames(self, body):
        local_renames = set()
        for stmt in body:
            if (
                isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef))
                and stmt.name in self.mapping
            ):
                local_renames.add(stmt.name)
        return local_renames

    def _visit_function_like(self, node):
        node.decorator_list = [self.visit(item) for item in node.decorator_list]
        node.args = self.visit(node.args)
        if node.returns is not None:
            node.returns = self.visit(node.returns)
        self.local_rename_stack.append(self._collect_direct_local_renames(node.body))
        self.scope_depth += 1
        node.body = [self.visit(item) for item in node.body]
        self.scope_depth -= 1
        self.local_rename_stack.pop()
        return node

    def visit_FunctionDef(self, node):
        if node.name in self.mapping:
            node.name = self.mapping[node.name]
        return self._visit_function_like(node)

    def visit_AsyncFunctionDef(self, node):
        if node.name in self.mapping:
            node.name = self.mapping[node.name]
        return self._visit_function_like(node)

    def visit_ClassDef(self, node):
        node.decorator_list = [self.visit(item) for item in node.decorator_list]
        node.bases = [self.visit(item) for item in node.bases]
        node.keywords = [self.visit(item) for item in node.keywords]
        self.class_depth += 1
        node.body = [self.visit(item) for item in node.body]
        self.class_depth -= 1
        return node

    def visit_Attribute(self, node):
        self.attribute_value_depth += 1
        node.value = self.visit(node.value)
        self.attribute_value_depth -= 1
        if (
            self.class_depth == 0
            and isinstance(node.value, ast.Name)
            and node.value.id in {'self', 'cls'}
        ):
            node.attr = self.mapping.get(node.attr, node.attr)
        return node

    def visit_Name(self, node):
        if (
            isinstance(node.ctx, ast.Load)
            and node.id in self.mapping
            and any(node.id in names for names in self.local_rename_stack)
        ):
            return ast.copy_location(ast.Name(id=self.mapping[node.id], ctx=node.ctx), node)
        if (
            self.rewrite_helper_loads
            and self.class_depth == 0
            and self.attribute_value_depth == 0
            and isinstance(node.ctx, ast.Load)
            and node.id in self.helper_methods
            and node.id in self.mapping
        ):
            return ast.copy_location(
                ast.Attribute(
                    value=ast.Name(id='self', ctx=ast.Load()),
                    attr=self.mapping[node.id],
                    ctx=node.ctx,
                ),
                node,
            )
        if self.rename_top_level_names and self.scope_depth == 0 and node.id in self.mapping:
            if (
                isinstance(node.ctx, ast.Load)
                and node.id in self.helper_methods
                and node.id in BUILTIN_NAMES
            ):
                return node
            return ast.copy_location(ast.Name(id=self.mapping[node.id], ctx=node.ctx), node)
        return node


class _NameLoadRewriter(ast.NodeTransformer):
    def __init__(self, old_name, new_name):
        self.old_name = old_name
        self.new_name = new_name

    def visit_Name(self, node):
        if node.id == self.old_name and isinstance(node.ctx, ast.Load):
            return ast.copy_location(ast.Name(id=self.new_name, ctx=node.ctx), node)
        return node


class _AttributeLoadRewriter(ast.NodeTransformer):
    def __init__(self, owner_name, attr_name, new_name):
        self.owner_name = owner_name
        self.attr_name = attr_name
        self.new_name = new_name

    def visit_Attribute(self, node):
        self.generic_visit(node)
        if (
            isinstance(node.ctx, ast.Load)
            and isinstance(node.value, ast.Name)
            and node.value.id == self.owner_name
            and node.attr == self.attr_name
        ):
            return ast.copy_location(ast.Name(id=self.new_name, ctx=ast.Load()), node)
        return node


class _StringLiteralRewriter(ast.NodeTransformer):
    def __init__(self, replacements):
        self.replacements = [(old, new) for (old, new) in replacements if old and old != new]

    def visit_Constant(self, node):
        if not isinstance(node.value, str) or not self.replacements:
            return node

        value = node.value
        for old, new in self.replacements:
            value = value.replace(old, new)

        if value == node.value:
            return node
        return ast.copy_location(ast.Constant(value=value), node)


class _SelfReferentialClassAliasRepair(ast.NodeTransformer):
    def __init__(self, inverse_mapping):
        self.inverse_mapping = inverse_mapping

    def _repair_value(self, target_name, value):
        original_name = self.inverse_mapping.get(target_name)
        if not original_name:
            return value

        if isinstance(value, ast.Name) and value.id == target_name:
            return ast.copy_location(ast.Name(id=original_name, ctx=ast.Load()), value)

        if (
            isinstance(value, ast.Attribute)
            and isinstance(value.value, ast.Name)
            and value.value.id == target_name
        ):
            return ast.copy_location(
                ast.Attribute(
                    value=ast.Name(id=original_name, ctx=ast.Load()),
                    attr=value.attr,
                    ctx=value.ctx,
                ),
                value,
            )

        return value

    def visit_Assign(self, node):
        self.generic_visit(node)
        if len(node.targets) != 1:
            return node

        target = node.targets[0]
        if isinstance(target, ast.Name):
            node.value = self._repair_value(target.id, node.value)
        return node

    def visit_AnnAssign(self, node):
        self.generic_visit(node)
        if isinstance(node.target, ast.Name) and node.value is not None:
            node.value = self._repair_value(node.target.id, node.value)
        return node


class _RequiredClassTestMethodStripper(ast.NodeTransformer):
    def __init__(self, stripped_class_names, preserved_test_methods=None):
        self.stripped_class_names = set(stripped_class_names)
        self.preserved_test_methods = {
            name: set(methods)
            for (name, methods) in (preserved_test_methods or {}).items()
        }

    def visit_ClassDef(self, node):
        node.decorator_list = [self.visit(item) for item in node.decorator_list]
        node.bases = [self.visit(item) for item in node.bases]
        node.keywords = [self.visit(item) for item in node.keywords]
        node.body = [self.visit(item) for item in node.body]
        node.body = [item for item in node.body if item is not None]

        if node.name in self.stripped_class_names:
            keep_methods = self.preserved_test_methods.get(node.name, set())
            node.body = [
                item
                for item in node.body
                if not (
                    isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and item.name.startswith('test')
                    and item.name not in keep_methods
                )
            ]

        if not node.body:
            node.body = [ast.Pass()]
        return node
