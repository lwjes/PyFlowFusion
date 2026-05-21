import ast
import copy


class _BoundNameRewriter(ast.NodeTransformer):
    def __init__(self, bindings):
        self.bindings = bindings

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Load) and node.id in self.bindings:
            return ast.copy_location(copy.deepcopy(self.bindings[node.id]), node)
        return node


class DecoratorRuntimeMixin:
    def _non_docstring_body(self, function_node):
        body = list(function_node.body)
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            return body[1:]
        return body

    def _iter_decorator_helper_functions(self, prepared_seed):
        for module_name in ('helper_module', 'prelude_module'):
            module = prepared_seed.get(module_name)
            if module is None:
                continue
            for stmt in module.body:
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    yield stmt

    def _find_decorator_helper_function(self, prepared_seed, function_name):
        for function_node in self._iter_decorator_helper_functions(prepared_seed):
            if function_node.name == function_name:
                return function_node
        return None

    def _filter_python_decorators(self, decorator_text):
        supported = []
        ignored = []

        for raw in decorator_text.splitlines():
            line = raw.strip()
            if not line:
                continue
            normalized = line if line.startswith('@') else '@' + line
            plain = normalized.lstrip('@')
            plain_lower = plain.lower()
            if (
                'skip' in plain_lower
                or 'expectedfailure' in plain_lower
                or 'requires_' in plain_lower
                or plain_lower.startswith('create_and_remove_directory(')
            ):
                supported.append(normalized)
            else:
                ignored.append(normalized)

        return supported, ignored

    def _extract_ignored_decorator_prelude(self, decorator_text):
        prelude_lines = []
        for raw in decorator_text.splitlines():
            line = raw.strip().lstrip('@')
            if not line:
                continue
            if not (line.startswith('support.bigmemtest(') or line.startswith('bigmemtest(')):
                continue
            try:
                expr = ast.parse(line, mode='eval').body
            except SyntaxError:
                continue
            if not isinstance(expr, ast.Call):
                continue

            func = expr.func
            is_bigmemtest = (
                isinstance(func, ast.Name)
                and func.id == 'bigmemtest'
            ) or (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == 'support'
                and func.attr == 'bigmemtest'
            )
            if not is_bigmemtest:
                continue

            size_node = None
            for keyword in expr.keywords:
                if keyword.arg == 'size':
                    size_node = keyword.value
                    break
            if size_node is None and expr.args:
                size_node = expr.args[0]
            if size_node is None:
                continue

            size_expr = ast.unparse(size_node).strip()
            prelude_lines.append(f'size = {size_expr}')
        return prelude_lines

    def _select_mock_patch_target_name(self, source):
        assigned_names = self._collect_assigned_names(source)
        mock_names = sorted(
            name
            for name in self._collect_name_loads(source)
            if name.startswith('mock') and name not in assigned_names
        )
        return mock_names[0] if len(mock_names) == 1 else ''

    def _is_subtests_decorator_call(self, expr):
        if not isinstance(expr, ast.Call):
            return False

        func = expr.func
        if isinstance(func, ast.Name) and func.id == 'subTests':
            return True
        return (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == 'support'
            and func.attr == 'subTests'
        )

    def _extract_subtests_spec_from_call(self, expr):
        if not self._is_subtests_decorator_call(expr) or len(expr.args) < 2:
            return None

        try:
            arg_names = ast.literal_eval(expr.args[0])
        except Exception:
            return None
        if not isinstance(arg_names, str) or not arg_names.strip():
            return None
        return arg_names, expr.args[1]

    def _extract_subtests_spec_from_helper(self, function_node):
        body = self._non_docstring_body(function_node)
        if len(body) != 1 or not isinstance(body[0], ast.Return) or body[0].value is None:
            return None
        return self._extract_subtests_spec_from_call(body[0].value)

    def _bind_decorator_helper_args(self, function_node, decorator_expr):
        if not isinstance(decorator_expr, ast.Call):
            return None
        if any(keyword.arg is None for keyword in decorator_expr.keywords):
            return None

        bindings = {}
        call_args = list(decorator_expr.args)
        call_keywords = {keyword.arg: keyword.value for keyword in decorator_expr.keywords}

        positional_params = list(function_node.args.posonlyargs) + list(function_node.args.args)
        defaults = list(function_node.args.defaults)
        defaults_start = len(positional_params) - len(defaults)

        for index, param in enumerate(positional_params):
            if index < len(call_args):
                bindings[param.arg] = copy.deepcopy(call_args[index])
                continue
            if param.arg in call_keywords:
                bindings[param.arg] = copy.deepcopy(call_keywords.pop(param.arg))
                continue
            if index >= defaults_start:
                bindings[param.arg] = copy.deepcopy(defaults[index - defaults_start])
                continue
            return None

        remaining_args = call_args[len(positional_params):]
        if function_node.args.vararg is not None:
            bindings[function_node.args.vararg.arg] = ast.Tuple(
                elts=[copy.deepcopy(arg) for arg in remaining_args],
                ctx=ast.Load(),
            )
        elif remaining_args:
            return None

        for param, default in zip(function_node.args.kwonlyargs, function_node.args.kw_defaults):
            if param.arg in call_keywords:
                bindings[param.arg] = copy.deepcopy(call_keywords.pop(param.arg))
                continue
            if default is None:
                return None
            bindings[param.arg] = copy.deepcopy(default)

        if function_node.args.kwarg is not None:
            bindings[function_node.args.kwarg.arg] = ast.Dict(
                keys=[ast.Constant(value=key) for key in call_keywords],
                values=[copy.deepcopy(call_keywords[key]) for key in call_keywords],
            )
            call_keywords = {}

        if call_keywords:
            return None
        return bindings

    def _resolve_subtests_spec(self, expr, prepared_seed):
        direct_spec = self._extract_subtests_spec_from_call(expr)
        if direct_spec is not None:
            (arg_names, values_node) = direct_spec
            return arg_names, ast.unparse(values_node).strip()

        if not isinstance(expr, ast.Call) or not isinstance(expr.func, ast.Name):
            return None

        function_node = self._find_decorator_helper_function(prepared_seed, expr.func.id)
        if function_node is None:
            return None

        helper_spec = self._extract_subtests_spec_from_helper(function_node)
        if helper_spec is None:
            return None

        bindings = self._bind_decorator_helper_args(function_node, expr)
        if bindings is None:
            return None

        (arg_names, values_node) = helper_spec
        rewritten_values = _BoundNameRewriter(bindings).visit(copy.deepcopy(values_node))
        ast.fix_missing_locations(rewritten_values)
        values_expr = ast.unparse(rewritten_values).strip()
        if not values_expr:
            return None
        return arg_names, values_expr

    def _apply_ignored_decorator_runtime(self, decorator_text, code, prepared_seed):
        wrapped = code.strip()
        if not wrapped:
            return wrapped

        patch_decorators = []
        for raw in decorator_text.splitlines():
            line = raw.strip().lstrip('@')
            if not line:
                continue
            if (
                line.startswith('unittest.mock.patch(')
                or line.startswith('unittest.mock.patch.object(')
                or line.startswith('mock.patch(')
                or line.startswith('mock.patch.object(')
                or line.startswith('patch(')
                or line.startswith('patch.object(')
            ):
                patch_decorators.append(line)

        if len(patch_decorators) == 1:
            patch_arg_name = self._select_mock_patch_target_name(wrapped)
            if patch_arg_name:
                wrapped = (
                    f'with {patch_decorators[0]} as {patch_arg_name}:\n'
                    f'{self._indent_block(wrapped, level=1)}'
                )

        for raw in decorator_text.splitlines():
            line = raw.strip().lstrip('@')
            try:
                expr = ast.parse(line, mode='eval').body
            except SyntaxError:
                continue
            resolved = self._resolve_subtests_spec(expr, prepared_seed)
            if resolved is None:
                continue
            (arg_names, arg_values_expr) = resolved
            if not arg_values_expr:
                continue

            names = [name.strip() for name in arg_names.split(',') if name.strip()]
            if not names:
                continue

            target = ', '.join(names)
            label_items = ', '.join(f'{name}={name}' for name in names)
            wrapped = (
                f'for ({target}) in {arg_values_expr}:\n'
                f'    with self.subTest({label_items}):\n'
                f'{self._indent_block(wrapped, level=2)}'
            )

        return wrapped

    def _collect_decorator_context(self, prepared_seeds):
        decorators = []
        ignored = []
        ignored_prelude = []
        for prepared_seed in prepared_seeds:
            decorator_text = '\n'.join(prepared_seed.get('skipif_lines', []))
            supported, unsupported = self._filter_python_decorators(decorator_text)
            decorators.extend(supported)
            ignored.extend(unsupported)
            ignored_prelude.extend(self._extract_ignored_decorator_prelude(decorator_text))
        return decorators, ignored, ignored_prelude

    def _prepare_runtime_code(self, prepared_seed, code):
        decorator_text = '\n'.join(prepared_seed.get('skipif_lines', []))
        runtime_code = self._apply_ignored_decorator_runtime(decorator_text, code, prepared_seed)
        return self._normalize_fused_test_name_expectations(runtime_code, prepared_seed['description'])
