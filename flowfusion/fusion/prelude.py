import ast

from flowfusion.fusion.ast_rewriters import _RequiredClassTestMethodStripper


class PreludeProcessingMixin:
    def _is_main_guard(self, node):
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

    def _expand_main_guard(self, stmt):
        if self._is_main_guard(stmt):
            return list(stmt.orelse)
        return [stmt]

    def _strip_main_guards_from_source(self, source):
        module = self._safe_parse_module(source)
        filtered = ast.Module(
            body=[expanded for stmt in module.body for expanded in self._expand_main_guard(stmt)],
            type_ignores=[],
        )
        return self._module_to_source(filtered)

    def _strip_top_level_functions(self, source, blocked_names):
        if not source or not blocked_names:
            return source

        module = self._safe_parse_module(source)
        filtered = ast.Module(
            body=[
                stmt
                for stmt in module.body
                if not (
                    isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and stmt.name in blocked_names
                )
            ],
            type_ignores=[],
        )
        return self._module_to_source(filtered)

    def _reorder_top_level_class_dependencies(self, source):
        if not source:
            return source

        module = self._safe_parse_module(source)
        top_level_classes = {
            stmt.name: stmt
            for stmt in module.body
            if isinstance(stmt, ast.ClassDef)
        }
        if not top_level_classes:
            return source

        ordered = []
        emitted = set()

        def emit(stmt):
            stmt_id = id(stmt)
            if stmt_id in emitted:
                return
            for dependency in self._referenced_top_level_classes(stmt, top_level_classes):
                dep_stmt = top_level_classes.get(dependency)
                if dep_stmt is not None:
                    emit(dep_stmt)
            emitted.add(stmt_id)
            ordered.append(stmt)

        for stmt in module.body:
            emit(stmt)

        reordered = ast.Module(body=ordered, type_ignores=[])
        return self._module_to_source(reordered)

    def _simple_name(self, dotted_name):
        if not isinstance(dotted_name, str):
            return ''
        return dotted_name.rsplit('.', 1)[-1]

    def _class_base_names(self, node):
        return [ast.unparse(base) for base in node.bases]

    def _has_test_methods(self, node):
        return any(
            isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and stmt.name.startswith('test')
            for stmt in node.body
        )

    def _referenced_top_level_classes(self, node, top_level_classes):
        referenced = set()
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and child.id in top_level_classes:
                if isinstance(node, ast.ClassDef) and child.id == node.name:
                    continue
                referenced.add(child.id)
        return referenced

    def _collect_required_prelude_classes(self, top_level_classes, required_bases):
        required = set()
        pending = []
        for base_name in required_bases:
            if not isinstance(base_name, str):
                continue
            for candidate in {base_name, self._simple_name(base_name)}:
                if candidate in top_level_classes and candidate not in required:
                    pending.append(candidate)

        while pending:
            class_name = pending.pop()
            if class_name in required:
                continue
            required.add(class_name)
            class_node = top_level_classes.get(class_name)
            if class_node is None:
                continue
            for dependency in self._referenced_top_level_classes(class_node, top_level_classes):
                if dependency not in required:
                    pending.append(dependency)
        return required

    def _collect_required_test_methods_for_module(
        self,
        module,
        top_level_classes,
        external_required_attrs,
        explicit_required_methods=None,
    ):
        required_attrs = {}
        for class_name, attrs in (external_required_attrs or {}).items():
            if class_name in top_level_classes:
                required_attrs.setdefault(class_name, set()).update(attrs)
            simple_name = self._simple_name(class_name)
            if simple_name in top_level_classes:
                required_attrs.setdefault(simple_name, set()).update(attrs)

        for class_name, methods in (explicit_required_methods or {}).items():
            if class_name in top_level_classes:
                required_attrs.setdefault(class_name, set()).update(methods)
            simple_name = self._simple_name(class_name)
            if simple_name in top_level_classes:
                required_attrs.setdefault(simple_name, set()).update(methods)

        for node in ast.walk(module):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.ctx, ast.Load)
                and isinstance(node.value, ast.Name)
                and node.value.id in top_level_classes
            ):
                required_attrs.setdefault(node.value.id, set()).add(node.attr)

        required_methods = {}
        for class_name, attrs in required_attrs.items():
            class_node = top_level_classes.get(class_name)
            if class_node is None:
                continue
            existing_test_methods = {
                stmt.name
                for stmt in class_node.body
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and stmt.name.startswith('test')
            }
            keep = existing_test_methods.intersection(attrs)
            if keep:
                required_methods[class_name] = keep
        return required_methods

    def _collect_retained_prelude_classes(
        self,
        module_body,
        top_level_classes,
        required_bases,
        required_class_names=None,
    ):
        retained = {
            name
            for name, node in top_level_classes.items()
            if not self._is_prelude_test_class(node)
        }
        required_roots = list(required_bases or [])
        for class_name in (required_class_names or set()):
            if class_name:
                required_roots.append(class_name)
        retained.update(self._collect_required_prelude_classes(top_level_classes, required_roots))
        for stmt in module_body:
            if isinstance(stmt, ast.ClassDef):
                continue
            retained.update(self._referenced_top_level_classes(stmt, top_level_classes))

        pending = list(retained)
        while pending:
            class_name = pending.pop()
            class_node = top_level_classes.get(class_name)
            if class_node is None:
                continue
            for dependency in self._referenced_top_level_classes(class_node, top_level_classes):
                if dependency in retained:
                    continue
                retained.add(dependency)
                pending.append(dependency)

        return retained

    def _is_prelude_test_class(self, node):
        if self._has_test_methods(node):
            return True

        for base_name in self._class_base_names(node):
            simple_name = self._simple_name(base_name)
            if simple_name.endswith('TestCase'):
                return True
            if simple_name.endswith('Test') or simple_name.endswith('Tests'):
                return True
        return False

    def _strip_irrelevant_test_classes_from_source(
        self,
        source,
        required_bases,
        required_class_attrs=None,
        required_class_names=None,
        required_test_methods=None,
    ):
        if not source:
            return source

        module = self._safe_parse_module(source)
        top_level_classes = {
            stmt.name: stmt
            for stmt in module.body
            if isinstance(stmt, ast.ClassDef)
        }
        module_attr_loads = self._collect_class_attribute_loads(source)
        required_class_names = (
            set(required_class_names or set())
            .union((required_class_attrs or {}).keys())
            .union(module_attr_loads.keys())
        )
        retained_classes = self._collect_retained_prelude_classes(
            module.body,
            top_level_classes,
            required_bases,
            required_class_names=required_class_names,
        )
        stripped_classes = {
            name
            for name, node in top_level_classes.items()
            if name in retained_classes and self._is_prelude_test_class(node)
        }
        preserved_methods = self._collect_required_test_methods_for_module(
            module,
            top_level_classes,
            required_class_attrs,
            explicit_required_methods=required_test_methods,
        )
        filtered = _RequiredClassTestMethodStripper(stripped_classes, preserved_methods).visit(module)
        ast.fix_missing_locations(filtered)
        filtered = ast.Module(
            body=[
                stmt
                for stmt in filtered.body
                if not (
                    isinstance(stmt, ast.ClassDef)
                    and stmt.name not in retained_classes
                    and self._is_prelude_test_class(stmt)
                )
            ],
            type_ignores=[],
        )
        return self._module_to_source(filtered)

    def _build_sanitized_base_aliases(self, class_bases, preserved_test_methods=None):
        if not class_bases:
            return '', []

        preserved_test_methods = sorted(set(preserved_test_methods or []))
        helper_lines = [
            'def _flowfusion_sanitize_base(base, keep_tests=()):',
            "    sanitized = type(f'_FlowFusionSanitized_{base.__name__}', (base,), {})",
            '    keep_tests = set(keep_tests)',
            '    for name in dir(sanitized):',
            "        if name.startswith('test') and name not in keep_tests and callable(getattr(sanitized, name, None)):",
            '            setattr(sanitized, name, None)',
            '    return sanitized',
        ]
        alias_names = []
        for index, base in enumerate(class_bases, start=1):
            alias_name = f'_flowfusion_base_{index}'
            helper_lines.append(
                f'{alias_name} = _flowfusion_sanitize_base({base}, {preserved_test_methods!r})'
            )
            alias_names.append(alias_name)
        return '\n'.join(helper_lines), alias_names

    def _combine_preludes(self, seed1, seed2):
        prelude_chunks = []
        required_bases = self._seed_base_names(seed1) + self._seed_base_names(seed2)
        required_class_attrs = {}
        required_class_names = set()
        required_base_test_methods = {}
        for seed in [seed1, seed2]:
            super_test_methods = set()
            for chunk in [seed.get('helpers', ''), seed.get('configuration', ''), seed.get('phpcode', '')]:
                attr_loads = self._collect_class_attribute_loads(chunk)
                for class_name, attrs in attr_loads.items():
                    required_class_attrs.setdefault(class_name, set()).update(attrs)
                required_class_names.update(self._collect_name_loads(chunk))
                super_test_methods.update(self._collect_super_test_method_names(chunk))
            if super_test_methods:
                for base_name in self._seed_base_names(seed):
                    if not isinstance(base_name, str) or not base_name:
                        continue
                    required_base_test_methods.setdefault(base_name, set()).update(super_test_methods)
                    simple_name = self._simple_name(base_name)
                    if simple_name:
                        required_base_test_methods.setdefault(simple_name, set()).update(super_test_methods)
        for chunk in [
            seed1.get('prelude_module', seed1.get('prelude', '')),
            seed2.get('prelude_module', seed2.get('prelude', '')),
        ]:
            normalized = self._strip_main_guards_from_source(chunk)
            normalized = self._strip_top_level_functions(normalized, {'load_tests'}).strip()
            normalized = self._strip_irrelevant_test_classes_from_source(
                normalized,
                required_bases,
                required_class_attrs=required_class_attrs,
                required_class_names=required_class_names,
                required_test_methods=required_base_test_methods,
            ).strip()
            normalized = self._reorder_top_level_class_dependencies(normalized).strip()
            if normalized and normalized not in prelude_chunks:
                prelude_chunks.append(normalized)
        return '\n\n'.join(prelude_chunks)
