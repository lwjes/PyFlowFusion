import ast


class SourceAnalysisMixin:
    def _safe_parse_analysis_module(self, source):
        try:
            return self._safe_parse_module(source)
        except (SyntaxError, ValueError, TypeError, AttributeError):
            return None

    def _iter_target_names(self, target):
        if isinstance(target, ast.Name):
            yield target.id
            return
        if isinstance(target, (ast.Tuple, ast.List)):
            for item in target.elts:
                yield from self._iter_target_names(item)

    def _collect_helper_member_names(self, source):
        module = self._safe_parse_analysis_module(source)
        if module is None:
            return set()
        helper_names = set()
        for stmt in module.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                helper_names.add(stmt.name)
            elif isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    helper_names.update(self._iter_target_names(target))
            elif isinstance(stmt, ast.AnnAssign):
                helper_names.update(self._iter_target_names(stmt.target))
        return helper_names

    def _collect_helper_method_names(self, source):
        module = self._safe_parse_analysis_module(source)
        if module is None:
            return set()
        method_names = set()
        for stmt in module.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method_names.add(stmt.name)
        return method_names

    def _collect_super_test_method_names(self, source):
        names = set()
        module = self._safe_parse_analysis_module(source)
        if module is None:
            return names
        for node in ast.walk(module):
            if not isinstance(node, ast.Attribute):
                continue
            if not node.attr.startswith('test'):
                continue
            if (
                isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)
                and node.value.func.id == 'super'
            ):
                names.add(node.attr)
        return names

    def _collect_helper_value_names(self, source):
        module = self._safe_parse_analysis_module(source)
        if module is None:
            return set()
        value_names = set()
        for stmt in module.body:
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    value_names.update(self._iter_target_names(target))
            elif isinstance(stmt, ast.AnnAssign):
                value_names.update(self._iter_target_names(stmt.target))
        return value_names

    def _collect_self_cls_attribute_names(self, source):
        names = set()
        module = self._safe_parse_analysis_module(source)
        if module is None:
            return names
        for node in ast.walk(module):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id in {'self', 'cls'}
                and isinstance(node.ctx, ast.Store)
            ):
                names.add(node.attr)
        return names

    def _collect_self_cls_loaded_attribute_names(self, source):
        names = set()
        module = self._safe_parse_analysis_module(source)
        if module is None:
            return names
        for node in ast.walk(module):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id in {'self', 'cls'}
                and isinstance(node.ctx, ast.Load)
            ):
                names.add(node.attr)
        return names

    def _collect_class_attribute_loads(self, source):
        loads = {}
        if not source:
            return loads

        module = self._safe_parse_analysis_module(source)
        if module is None:
            return loads
        for node in ast.walk(module):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.ctx, ast.Load)
                and isinstance(node.value, ast.Name)
                and node.value.id
            ):
                loads.setdefault(node.value.id, set()).add(node.attr)
        return loads

    def _collect_name_loads(self, source):
        loads = set()
        try:
            module = self._safe_parse_module(source)
        except (SyntaxError, ValueError, TypeError, AttributeError):
            return loads

        for node in ast.walk(module):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                loads.add(node.id)
        return loads

    def _has_risky_name_usage(self, source, target_name):
        try:
            module = self._safe_parse_module(source)
        except (SyntaxError, ValueError, TypeError, AttributeError):
            return True

        for node in ast.walk(module):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == target_name:
                return True
            if isinstance(node, (ast.With, ast.AsyncWith)):
                for item in node.items:
                    if isinstance(item.context_expr, ast.Name) and item.context_expr.id == target_name:
                        return True
            if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Name) and node.exc.id == target_name:
                return True
            if isinstance(node, ast.ExceptHandler) and isinstance(node.type, ast.Name) and node.type.id == target_name:
                return True
        return False

    def _collect_assigned_names(self, source):
        names = set()
        try:
            module = self._safe_parse_module(source)
        except (SyntaxError, ValueError, TypeError, AttributeError):
            return names

        for node in ast.walk(module):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                names.add(node.id)
        return names

    def _is_simple_bridge_value(self, node):
        return isinstance(
            node,
            (
                ast.Constant,
                ast.Name,
                ast.Tuple,
                ast.List,
                ast.Set,
                ast.Dict,
                ast.UnaryOp,
                ast.BinOp,
                ast.JoinedStr,
            ),
        )

    def _collect_simple_assigned_names(self, source):
        names = set()
        try:
            module = self._safe_parse_module(source)
        except (SyntaxError, ValueError, TypeError, AttributeError):
            return names

        for stmt in module.body:
            value = None
            targets = []
            if isinstance(stmt, ast.Assign):
                value = stmt.value
                targets = stmt.targets
            elif isinstance(stmt, ast.AnnAssign):
                value = stmt.value
                targets = [stmt.target]

            if value is None or not self._is_simple_bridge_value(value):
                continue

            for target in targets:
                for name in self._iter_target_names(target):
                    names.add(name)
        return names

    def _collect_safe_source_flows(self, source, dataflows):
        assigned_names = self._collect_simple_assigned_names(source)
        candidates = []
        seen = set()
        for group in dataflows:
            for flow_name in group:
                if not isinstance(flow_name, str) or not flow_name or '.' in flow_name:
                    continue
                if flow_name not in assigned_names or flow_name in seen or flow_name.startswith('__'):
                    continue
                seen.add(flow_name)
                candidates.append(flow_name)
        return candidates

    def _collect_safe_target_flows(self, source, dataflows):
        simple_assigned_names = self._collect_simple_assigned_names(source)
        candidates = []
        seen = set()
        for group in dataflows:
            for flow_name in group:
                if (
                    not isinstance(flow_name, str)
                    or not flow_name
                    or '.' in flow_name
                ):
                    continue
                if flow_name not in simple_assigned_names or flow_name.startswith('__'):
                    continue
                if self._has_risky_name_usage(source, flow_name):
                    continue
                if flow_name in seen:
                    continue
                seen.add(flow_name)
                candidates.append(flow_name)
        return candidates

    def _collect_top_level_class_names(self, source):
        if not source:
            return set()
        module = self._safe_parse_analysis_module(source)
        if module is None:
            return set()
        return {
            stmt.name
            for stmt in module.body
            if isinstance(stmt, ast.ClassDef)
        }

    def _extract_direct_none_placeholders(self, source):
        placeholders = set()
        if not source:
            return placeholders

        module = self._safe_parse_analysis_module(source)
        if module is None:
            return placeholders
        for stmt in module.body:
            if (
                isinstance(stmt, ast.Assign)
                and isinstance(stmt.value, ast.Constant)
                and stmt.value.value is None
            ):
                for target in stmt.targets:
                    placeholders.update(self._iter_target_names(target))
            elif (
                isinstance(stmt, ast.AnnAssign)
                and stmt.value is not None
                and isinstance(stmt.value, ast.Constant)
                and stmt.value.value is None
            ):
                placeholders.update(self._iter_target_names(stmt.target))
        return placeholders

    def _is_notimplemented_placeholder_function(self, node):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return False

        body = list(node.body)
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body = body[1:]

        if len(body) != 1 or not isinstance(body[0], ast.Raise):
            return False

        exc = body[0].exc
        if isinstance(exc, ast.Name):
            return exc.id == 'NotImplementedError'
        if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name):
            return exc.func.id == 'NotImplementedError'
        return False

    def _has_property_decorator(self, node):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return False
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Name) and decorator.id == 'property':
                return True
        return False

    def _extract_notimplemented_placeholder_methods(self, source):
        placeholders = set()
        if not source:
            return placeholders

        module = self._safe_parse_analysis_module(source)
        if module is None:
            return placeholders
        for stmt in module.body:
            if self._is_notimplemented_placeholder_function(stmt):
                placeholders.add(stmt.name)
        return placeholders

    def _extract_notimplemented_placeholder_properties(self, source):
        placeholders = set()
        if not source:
            return placeholders

        module = self._safe_parse_analysis_module(source)
        if module is None:
            return placeholders
        for stmt in module.body:
            if (
                self._is_notimplemented_placeholder_function(stmt)
                and self._has_property_decorator(stmt)
            ):
                placeholders.add(stmt.name)
        return placeholders

    def _collect_called_self_cls_members(self, source):
        names = set()
        if not source:
            return names

        module = self._safe_parse_analysis_module(source)
        if module is None:
            return names
        for node in ast.walk(module):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in {'self', 'cls'}
            ):
                names.add(node.func.attr)
        return names
