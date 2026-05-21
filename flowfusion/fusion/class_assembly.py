import unittest


TESTCASE_MEMBER_NAMES = set(dir(unittest.TestCase))


class ClassAssemblyMixin:
    def _build_runtime_attribute_alias_lines(self, prepared_seed, target_name):
        alias_lines = []
        helper_mapping = prepared_seed.get('helper_mapping', {})
        for name in sorted(prepared_seed.get('runtime_attribute_names', set())):
            mapped_name = helper_mapping.get(name)
            if not name or not mapped_name or name == mapped_name or name in TESTCASE_MEMBER_NAMES:
                continue
            alias_lines.append(
                f"if hasattr({target_name}, '{mapped_name}'):\n"
                f"    {target_name}.{name} = {target_name}.{mapped_name}"
            )
        return '\n'.join(alias_lines)

    def _build_source_class_aliases(self, prepared_seeds, prelude_source):
        existing_classes = self._collect_top_level_class_names(prelude_source)
        alias_lines = []
        seen = set()
        for prepared_seed in prepared_seeds:
            class_name = (prepared_seed.get('source_class_name') or '').strip()
            if (
                not class_name
                or class_name == 'FlowFusionTest'
                or not class_name.isidentifier()
                or class_name in seen
                or class_name in existing_classes
            ):
                continue
            alias_lines.append(f'{class_name} = FlowFusionTest')
            seen.add(class_name)
        return '\n'.join(alias_lines)

    def _build_helper_value_aliases(self, prepared_seeds):
        alias_lines = []
        seen = set()
        wrapper_names = {'setUp', 'tearDown', 'setUpClass', 'tearDownClass'}
        for prepared_seed in prepared_seeds:
            helper_mapping = prepared_seed.get('helper_mapping', {})
            for name in sorted(prepared_seed.get('helper_method_names', set())):
                if (
                    name in seen
                    or name not in helper_mapping
                    or not name
                    or name in wrapper_names
                    or name in TESTCASE_MEMBER_NAMES
                ):
                    continue
                alias_lines.append(f'{name} = {helper_mapping[name]}')
                seen.add(name)
            for name in sorted(prepared_seed.get('helper_value_names', set())):
                if name in seen or name not in helper_mapping:
                    continue
                if not name or name.startswith('__') or name in TESTCASE_MEMBER_NAMES:
                    continue
                alias_lines.append(f'{name} = {helper_mapping[name]}')
                seen.add(name)
        return '\n'.join(alias_lines)

    def _combine_helper_sources(self, prepared_seeds):
        helper_chunks = []
        for prepared_seed in prepared_seeds:
            helper_source = prepared_seed.get('helpers', '')
            helper_module = prepared_seed.get('helper_module')
            if helper_module is not None:
                helper_source = self._module_to_source(helper_module)
            stripped = (helper_source or '').strip()
            if stripped:
                helper_chunks.append(stripped)
        return '\n\n'.join(helper_chunks)

    def _build_setup_wrapper(self, prepared1, prepared2):
        setup_one = prepared1.get('configuration', '').strip()
        setup_two = prepared2.get('configuration', '').strip()
        return (
            'def _flowfusion_setup_one(self):\n'
            f'{self._indent_block(setup_one, level=1)}\n\n'
            'def _flowfusion_setup_two(self):\n'
            f'{self._indent_block(setup_two, level=1)}\n\n'
            'def setUp(self):\n'
            '    super().setUp()\n'
            '    self._flowfusion_setup_one()\n'
            '    self._flowfusion_setup_two()'
        )

    def _build_teardown_wrapper(self, prepared_seeds):
        teardown_calls = []
        for prepared_seed in prepared_seeds:
            helper_names = prepared_seed.get('helper_method_names', set())
            helper_mapping = prepared_seed.get('helper_mapping', {})
            if 'tearDown' in helper_names and 'tearDown' in helper_mapping:
                teardown_calls.append(f'self.{helper_mapping["tearDown"]}()')
        if not teardown_calls:
            return ''
        return (
            'def tearDown(self):\n'
            f'{self._indent_block(chr(10).join(teardown_calls), level=1)}'
        )

    def _build_class_setup_wrapper(self, prepared_seeds):
        class_setup_calls = []
        alias_lines = []
        for prepared_seed in prepared_seeds:
            helper_names = prepared_seed.get('helper_method_names', set())
            helper_mapping = prepared_seed.get('helper_mapping', {})
            if 'setUpClass' in helper_names and 'setUpClass' in helper_mapping:
                class_setup_calls.append(f'cls.{helper_mapping["setUpClass"]}()')
                runtime_aliases = self._build_runtime_attribute_alias_lines(prepared_seed, 'cls')
                if runtime_aliases:
                    alias_lines.append(runtime_aliases)
        if not class_setup_calls:
            return ''
        wrapper_body = '\n'.join(class_setup_calls + alias_lines)
        return (
            '@classmethod\n'
            'def setUpClass(cls):\n'
            '    super().setUpClass()\n'
            f'{self._indent_block(wrapper_body, level=1)}'
        )

    def _build_class_teardown_wrapper(self, prepared_seeds):
        class_teardown_calls = []
        for prepared_seed in prepared_seeds:
            helper_names = prepared_seed.get('helper_method_names', set())
            helper_mapping = prepared_seed.get('helper_mapping', {})
            if 'tearDownClass' in helper_names and 'tearDownClass' in helper_mapping:
                class_teardown_calls.append(f'cls.{helper_mapping["tearDownClass"]}()')
        if not class_teardown_calls:
            return ''
        return (
            '@classmethod\n'
            'def tearDownClass(cls):\n'
            f'{self._indent_block(chr(10).join(class_teardown_calls), level=1)}\n'
            '    super().tearDownClass()'
        )

    def _build_class_base_definition(self, prepared_seeds):
        class_bases = []
        for prepared_seed in prepared_seeds:
            for base in prepared_seed.get('base_names', self._safe_eval_list(prepared_seed.get('bases', ''))):
                if isinstance(base, str) and base and base not in class_bases:
                    class_bases.append(base)

        preserved_base_test_methods = set()
        for prepared_seed in prepared_seeds:
            for chunk in [
                prepared_seed.get('helpers', ''),
                prepared_seed.get('configuration', ''),
                prepared_seed.get('phpcode', ''),
            ]:
                preserved_base_test_methods.update(self._collect_super_test_method_names(chunk))

        sanitized_base_source, sanitized_bases = self._build_sanitized_base_aliases(
            class_bases,
            preserved_test_methods=preserved_base_test_methods,
        )
        class_base_list = ', '.join(sanitized_bases + ['unittest.TestCase'])
        return sanitized_base_source, class_base_list

    def _build_test_method_block(self, body_source, decorators, ignored):
        ignored_comment = ''
        if ignored:
            ignored_comment = '\n'.join(
                f'    # Ignored unsupported decorators during fusion: {item}'
                for item in ignored
            ) + '\n'

        decorator_block = ''
        if decorators:
            decorator_block = '\n'.join(f'    {item}' for item in decorators) + '\n'

        return (
            f'{ignored_comment}{decorator_block}'
            '    def test_fused(self):\n'
            f'{self._indent_block(body_source, level=2)}'
        )

    def _build_class_parts(self, prepared1, prepared2, body_source, decorators, ignored):
        prepared_seeds = [prepared1, prepared2]
        helpers_source = self._combine_helper_sources(prepared_seeds)
        helper_aliases = self._build_helper_value_aliases(prepared_seeds)
        class_setup_wrapper = self._build_class_setup_wrapper(prepared_seeds)
        class_teardown_wrapper = self._build_class_teardown_wrapper(prepared_seeds)
        setup_wrapper = self._build_setup_wrapper(prepared1, prepared2)
        teardown_wrapper = self._build_teardown_wrapper(prepared_seeds)
        test_method_block = self._build_test_method_block(body_source, decorators, ignored)

        class_parts = []
        if helpers_source:
            class_parts.append(self._indent_block(helpers_source, level=1))
        if helper_aliases:
            class_parts.append(self._indent_block(helper_aliases, level=1))
        if class_setup_wrapper:
            class_parts.append(self._indent_block(class_setup_wrapper, level=1))
        if class_teardown_wrapper:
            class_parts.append(self._indent_block(class_teardown_wrapper, level=1))
        class_parts.append(self._indent_block(setup_wrapper, level=1))
        if teardown_wrapper:
            class_parts.append(self._indent_block(teardown_wrapper, level=1))
        class_parts.append(test_method_block)
        return class_parts
