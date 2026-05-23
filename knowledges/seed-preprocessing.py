import ast
import os
import sqlite3
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from flowfusion.dataflow import PythonFastDataflow
from flowfusion.fusion.seed_ir import build_seed_ir, dumps_seed_ir


TESTCASE_MEMBER_NAMES = set(dir(unittest.TestCase))


def ensure_schema(cursor):
    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS seeds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phpcode TEXT,
            variable TEXT,
            dataflow TEXT,
            description TEXT,
            configuration TEXT,
            skipif TEXT,
            extension TEXT,
            secondary BOOL,
            language TEXT DEFAULT 'python'
        )
        '''
    )

    cursor.execute("PRAGMA table_info(seeds)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    if 'language' not in existing_columns:
        cursor.execute("ALTER TABLE seeds ADD COLUMN language TEXT DEFAULT 'python'")
    if 'prelude' not in existing_columns:
        cursor.execute("ALTER TABLE seeds ADD COLUMN prelude TEXT DEFAULT ''")
    if 'helpers' not in existing_columns:
        cursor.execute("ALTER TABLE seeds ADD COLUMN helpers TEXT DEFAULT ''")
    if 'bases' not in existing_columns:
        cursor.execute("ALTER TABLE seeds ADD COLUMN bases TEXT DEFAULT '[]'")
    if 'seed_ir' not in existing_columns:
        cursor.execute("ALTER TABLE seeds ADD COLUMN seed_ir TEXT DEFAULT ''")


def _stmt_list_to_source(statements):
    lines = []
    for stmt in statements:
        rendered = ast.unparse(stmt).strip()
        if rendered:
            lines.append(rendered)
    return '\n'.join(lines)


def _iter_target_names(target):
    if isinstance(target, ast.Name):
        yield target.id
        return
    if isinstance(target, (ast.Tuple, ast.List)):
        for item in target.elts:
            yield from _iter_target_names(item)


def _is_main_guard(node):
    if not isinstance(node, ast.If):
        return False

    test = node.test
    if not isinstance(test, ast.Compare):
        return False
    if len(test.ops) != 1 or not isinstance(test.ops[0], ast.Eq):
        return False
    if len(test.comparators) != 1:
        return False

    left = test.left
    right = test.comparators[0]
    return (
        isinstance(left, ast.Name)
        and left.id == '__name__'
        and isinstance(right, ast.Constant)
        and right.value == '__main__'
    ) or (
        isinstance(right, ast.Name)
        and right.id == '__name__'
        and isinstance(left, ast.Constant)
        and left.value == '__main__'
    )


def _main_guard_orelse(node):
    if _is_main_guard(node):
        return list(node.orelse)
    return None


def _class_base_names(node):
    return {ast.unparse(base) for base in node.bases}


def _simple_name(dotted_name):
    if not isinstance(dotted_name, str):
        return ''
    return dotted_name.rsplit('.', 1)[-1]


def _is_plain_testcase_base(base_name):
    return base_name in {'unittest.TestCase', 'TestCase'}


def _non_plain_testcase_bases(node):
    return [base for base in _class_base_names(node) if not _is_plain_testcase_base(base)]


def _is_unittest_class(node):
    return _has_test_methods(node) or any('TestCase' in base for base in _class_base_names(node))


def _has_test_methods(node):
    return any(
        isinstance(stmt, ast.FunctionDef) and stmt.name.startswith('test')
        for stmt in node.body
    )


def _referenced_top_level_classes(node, top_level_classes):
    referenced = set()
    for base in node.bases:
        for child in ast.walk(base):
            if isinstance(child, ast.Name) and child.id in top_level_classes and child.id != node.name:
                referenced.add(child.id)
    return referenced


def _referenced_top_level_names(node, top_level_classes, excluded_names=None):
    referenced = set()
    excluded_names = set(excluded_names or set())
    for child in ast.walk(node):
        if (
            isinstance(child, ast.Name)
            and isinstance(child.ctx, ast.Load)
            and child.id in top_level_classes
            and child.id not in excluded_names
        ):
            referenced.add(child.id)
    return referenced


def _ordered_referenced_top_level_classes(node, top_level_classes):
    referenced = []
    seen = set()
    for base in node.bases:
        for child in ast.walk(base):
            if (
                isinstance(child, ast.Name)
                and child.id in top_level_classes
                and child.id != node.name
                and child.id not in seen
            ):
                referenced.append(child.id)
                seen.add(child.id)
    return referenced


def _collect_class_closure(node, top_level_classes):
    closure = []
    visited = set()

    def append_class(class_name):
        if class_name in visited:
            return
        class_node = top_level_classes.get(class_name)
        if class_node is None:
            return
        for dependency in _ordered_referenced_top_level_classes(class_node, top_level_classes):
            append_class(dependency)
        closure.append(class_node)
        visited.add(class_name)

    append_class(node.name)
    return closure


def _collect_external_non_plain_bases(class_nodes, top_level_classes):
    bases = []
    seen = set()
    for class_node in class_nodes:
        for base_name in _class_base_names(class_node):
            if _is_plain_testcase_base(base_name):
                continue
            if _simple_name(base_name) in top_level_classes:
                continue
            if base_name in seen:
                continue
            bases.append(base_name)
            seen.add(base_name)
    return bases


def _find_first_lifecycle_method(class_nodes, method_name):
    for class_node in reversed(class_nodes):
        for stmt in class_node.body:
            if isinstance(stmt, ast.FunctionDef) and stmt.name == method_name:
                return stmt
    return None


def _collect_helper_members(class_nodes):
    members = []
    for class_node in class_nodes:
        for stmt in class_node.body:
            if isinstance(stmt, ast.FunctionDef) and stmt.name.startswith('test'):
                continue
            if isinstance(stmt, ast.FunctionDef) and stmt.name == 'setUp':
                continue
            members.append(stmt)
    return members


def _collect_self_cls_loaded_attrs_from_nodes(nodes):
    names = set()
    module = ast.Module(body=list(nodes), type_ignores=[])
    for node in ast.walk(module):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in {'self', 'cls'}
            and isinstance(node.ctx, ast.Load)
        ):
            names.add(node.attr)
    return names


def _collect_defined_member_names(class_nodes):
    names = set()
    for class_node in class_nodes:
        for stmt in class_node.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names.add(stmt.name)
            elif isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    names.update(_iter_target_names(target))
            elif isinstance(stmt, ast.AnnAssign):
                names.update(_iter_target_names(stmt.target))
    module = ast.Module(body=list(class_nodes), type_ignores=[])
    for node in ast.walk(module):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in {'self', 'cls'}
            and isinstance(node.ctx, ast.Store)
        ):
            names.add(node.attr)
    return names


def _has_unresolved_self_dependencies(class_nodes, test_method):
    loaded = _collect_self_cls_loaded_attrs_from_nodes(list(class_nodes) + [test_method])
    defined = _collect_defined_member_names(class_nodes)
    unresolved = {
        name
        for name in loaded
        if name not in defined and name not in TESTCASE_MEMBER_NAMES
    }
    return bool(unresolved)


def _contains_relative_imports(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level > 0:
            return True
    return False


def _collect_top_level_test_factory_templates(tree, top_level_classes):
    templates = set()
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            call = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.value, ast.Call):
            call = node.value
        else:
            continue

        if isinstance(call.func, ast.Name):
            func_name = call.func.id
        elif isinstance(call.func, ast.Attribute):
            func_name = call.func.attr
        else:
            func_name = ''

        if func_name != 'test_both':
            continue

        for arg in call.args:
            if isinstance(arg, ast.Name) and arg.id in top_level_classes:
                templates.add(arg.id)
    return templates


def parse_python_unittest_file(filepath, source):
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    if _contains_relative_imports(tree):
        return []

    module_name = os.path.basename(filepath)
    parsed_tests = []
    top_level_classes = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    }
    factory_template_classes = _collect_top_level_test_factory_templates(tree, top_level_classes)

    module_prelude_nodes = []
    appended_classes = set()

    def append_class_with_dependencies(class_name):
        if class_name in appended_classes:
            return

        class_node = top_level_classes.get(class_name)
        if class_node is None:
            return

        for dependency in _referenced_top_level_classes(class_node, top_level_classes):
            append_class_with_dependencies(dependency)

        module_prelude_nodes.append(class_node)
        appended_classes.add(class_name)

    for node in tree.body:
        guard_orelse = _main_guard_orelse(node)
        if guard_orelse is not None:
            module_prelude_nodes.extend(guard_orelse)
            for stmt in guard_orelse:
                for referenced in _referenced_top_level_names(stmt, top_level_classes):
                    append_class_with_dependencies(referenced)
            continue
        if not isinstance(node, ast.ClassDef):
            module_prelude_nodes.append(node)
            for referenced in _referenced_top_level_names(node, top_level_classes):
                append_class_with_dependencies(referenced)
            continue
        if not _has_test_methods(node):
            append_class_with_dependencies(node.name)
            continue
        for dependency in _non_plain_testcase_bases(node):
            append_class_with_dependencies(dependency)
        for referenced in _referenced_top_level_names(node, top_level_classes, excluded_names={node.name}):
            append_class_with_dependencies(referenced)

    module_prelude = _stmt_list_to_source(module_prelude_nodes)

    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue

        if not _has_test_methods(node):
            continue
        if node.name in factory_template_classes:
            continue

        test_methods = []
        for stmt in node.body:
            if isinstance(stmt, ast.FunctionDef) and stmt.name.startswith('test'):
                test_methods.append(stmt)

        if not test_methods:
            continue

        class_closure = _collect_class_closure(node, top_level_classes)
        class_decorators = [ast.unparse(d) for d in node.decorator_list]
        mixin_bases = _collect_external_non_plain_bases(class_closure, top_level_classes)
        setup_method = _find_first_lifecycle_method(class_closure, 'setUp')
        setup_lines = []
        if setup_method is not None:
            setup_lines = [ast.unparse(s) for s in setup_method.body]

        helper_members = _collect_helper_members(class_closure)
        helper_source = _stmt_list_to_source(helper_members)

        for test_method in test_methods:
            if _has_unresolved_self_dependencies(class_closure, test_method):
                continue
            method_decorators = [ast.unparse(d) for d in test_method.decorator_list]
            skip_markers = class_decorators + method_decorators
            body_lines = [ast.unparse(s) for s in test_method.body]

            parsed_tests.append(
                {
                    'description': f"{module_name}::{node.name}::{test_method.name}",
                    'configuration': '\n'.join(setup_lines),
                    'skipif': '\n'.join(skip_markers),
                    'code': '\n'.join(body_lines),
                    'prelude': module_prelude,
                    'helpers': helper_source,
                    'bases': str(mixin_bases),
                    'seed_ir': build_seed_ir(
                        prelude_nodes=module_prelude_nodes,
                        helper_nodes=helper_members,
                        configuration_nodes=setup_method.body if setup_method is not None else [],
                        body_nodes=test_method.body,
                        decorator_nodes=list(node.decorator_list) + list(test_method.decorator_list),
                        base_names=mixin_bases,
                    ),
                    'secondary': False,
                    'language': 'python',
                }
            )

    return parsed_tests
def collect_python_seeds(seed_dir, cursor):
    if not os.path.exists(seed_dir):
        return

    py_dataflow = PythonFastDataflow()

    for current_root, _, files in os.walk(seed_dir):
        for seed in files:
            if not seed.endswith('.py'):
                continue

            full_path = os.path.join(current_root, seed)
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                source = f.read()

            tests = parse_python_unittest_file(full_path, source)
            for test in tests:
                code = test['code']
                variables, dataflows = py_dataflow.analyze(code)

                cursor.execute(
                    '''
                    INSERT INTO seeds (phpcode, variable, dataflow, description, configuration, skipif, extension, secondary, language, prelude, helpers, bases, seed_ir)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (
                        code,
                        str(variables),
                        str(dataflows),
                        test['description'],
                        test['configuration'],
                        test['skipif'],
                        '',
                        test['secondary'],
                        test['language'],
                        test['prelude'],
                        test['helpers'],
                        test['bases'],
                        dumps_seed_ir(test['seed_ir']),
                    ),
                )


def main():
    conn = sqlite3.connect('seeds.db')
    cursor = conn.cursor()

    ensure_schema(cursor)

    cursor.execute('DELETE FROM seeds')

    print('dataflow pre-processing')
    collect_python_seeds(os.path.join(PROJECT_ROOT, 'workspace', 'py_seeds'), cursor)

    conn.commit()
    conn.close()


if __name__ == '__main__':
    main()
