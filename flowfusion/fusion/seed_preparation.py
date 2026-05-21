import ast

from flowfusion.fusion.ast_rewriters import (
    _AttributeMethodRenamer,
    _SelfReferentialClassAliasRepair,
)
from flowfusion.fusion.seed_ir import (
    seed_ir_base_names,
    seed_ir_decorator_nodes,
    seed_ir_section_module,
)


class SeedPreparationMixin:
    def _seed_section_module(self, seed, section_name):
        module = seed_ir_section_module(seed.get('seed_ir'), section_name)
        if module is not None:
            return module
        field_name = {
            'prelude': 'prelude',
            'helpers': 'helpers',
            'configuration': 'configuration',
            'body': 'phpcode',
        }[section_name]
        return self._safe_parse_module(seed.get(field_name, ''))

    def _seed_decorator_lines(self, seed):
        decorator_nodes = seed_ir_decorator_nodes(seed.get('seed_ir'))
        if decorator_nodes is not None:
            return [ast.unparse(node).strip() for node in decorator_nodes if ast.unparse(node).strip()]
        return [line.strip() for line in (seed.get('skipif') or '').splitlines() if line.strip()]

    def _seed_base_names(self, seed):
        base_names = seed_ir_base_names(seed.get('seed_ir'))
        if base_names is not None:
            return [name for name in base_names if isinstance(name, str) and name]
        return self._safe_eval_list(seed.get('bases', ''))

    def _build_seed_mapping(self, seed, prefix):
        names = set()
        helper_module = self._seed_section_module(seed, 'helpers')
        configuration_module = self._seed_section_module(seed, 'configuration')
        body_module = self._seed_section_module(seed, 'body')
        names.update(self._collect_helper_member_names(helper_module))
        for chunk in [helper_module, configuration_module, body_module]:
            names.update(self._collect_self_cls_attribute_names(chunk))
        return {name: f'{prefix}_{name}' for name in sorted(names)}

    def _rewrite_with_mapping(
        self,
        source,
        mapping,
        rename_top_level_names=False,
        helper_methods=None,
        rewrite_helper_loads=False,
    ):
        if not source or not mapping:
            return source
        module = self._safe_parse_module(source)
        rewritten = _AttributeMethodRenamer(
            mapping,
            rename_top_level_names=rename_top_level_names,
            helper_methods=helper_methods,
            rewrite_helper_loads=rewrite_helper_loads,
        ).visit(module)
        ast.fix_missing_locations(rewritten)
        return self._module_to_source(rewritten)

    def _repair_self_referential_class_aliases(self, source, mapping):
        if not source or not mapping:
            return source

        inverse_mapping = {new: old for (old, new) in mapping.items() if old and new}
        if not inverse_mapping:
            return source

        module = self._safe_parse_module(source)
        repaired = _SelfReferentialClassAliasRepair(inverse_mapping).visit(module)
        ast.fix_missing_locations(repaired)
        return self._module_to_source(repaired)

    def _remap_dataflow_value(self, value, mapping):
        if isinstance(value, list):
            return [self._remap_dataflow_value(item, mapping) for item in value]
        if isinstance(value, tuple):
            return tuple(self._remap_dataflow_value(item, mapping) for item in value)
        if not isinstance(value, str):
            return value
        if value in mapping:
            return f'self.{mapping[value]}'
        if value.startswith('self.'):
            attr = value.split('.', 1)[1]
            if attr in mapping:
                return f'self.{mapping[attr]}'
        if value.startswith('cls.'):
            attr = value.split('.', 1)[1]
            if attr in mapping:
                return f'cls.{mapping[attr]}'
        return value

    def _remap_dataflow(self, raw_dataflow, mapping):
        if not raw_dataflow or not mapping:
            return raw_dataflow
        remapped = self._remap_dataflow_value(self._safe_eval_list(raw_dataflow), mapping)
        return str(remapped)

    def _inject_missing_common_defaults(self, setup_source, seed):
        if not setup_source:
            return setup_source

        load_names = self._collect_name_loads(setup_source)
        assigned_names = self._collect_assigned_names(setup_source)
        injected_lines = []

        if (
            'encoding' in load_names
            and 'encoding' not in assigned_names
            and (
                'DEFAULT_ENCODING' in (seed.get('prelude', '') or '')
                or 'DEFAULT_ENCODING' in (seed.get('helpers', '') or '')
                or 'DEFAULT_ENCODING' in setup_source
            )
        ):
            injected_lines.append('encoding = DEFAULT_ENCODING')

        if not injected_lines:
            return setup_source
        return '\n'.join(injected_lines + [setup_source])

    def _prepare_python_seed(self, seed, prefix):
        source_class_name = self._extract_class_name(seed.get('description', ''))
        seed_mapping = self._build_seed_mapping(seed, prefix)
        helper_module = self._seed_section_module(seed, 'helpers')
        configuration_module = self._seed_section_module(seed, 'configuration')
        body_module = self._seed_section_module(seed, 'body')
        prelude_module = self._seed_section_module(seed, 'prelude')
        helper_methods = self._collect_helper_method_names(helper_module)
        helper_value_names = self._collect_helper_value_names(helper_module)
        runtime_attribute_names = set()
        for chunk in [helper_module, configuration_module, body_module]:
            runtime_attribute_names.update(self._collect_self_cls_attribute_names(chunk))
        helper_runtime_names = set(helper_methods).union(helper_value_names)
        helper_source = self._rewrite_with_mapping(
            helper_module,
            seed_mapping,
            rename_top_level_names=True,
            helper_methods=helper_methods,
        )
        helper_source = self._repair_self_referential_class_aliases(helper_source, seed_mapping)
        setup_source = self._rewrite_with_mapping(
            configuration_module,
            seed_mapping,
            helper_methods=helper_runtime_names,
            rewrite_helper_loads=True,
        )
        setup_source = self._inject_missing_common_defaults(setup_source, seed)
        body_source = self._rewrite_with_mapping(
            body_module,
            seed_mapping,
            helper_methods=helper_runtime_names,
            rewrite_helper_loads=True,
        )
        if source_class_name and source_class_name != 'FlowFusionTest':
            helper_source = self._rewrite_python_loads(helper_source, source_class_name, 'FlowFusionTest')
            setup_source = self._rewrite_python_loads(setup_source, source_class_name, 'FlowFusionTest')
            body_source = self._rewrite_python_loads(body_source, source_class_name, 'FlowFusionTest')
        dataflow_source = self._remap_dataflow(seed.get('dataflow', ''), seed_mapping)
        return {
            **seed,
            'helpers': helper_source,
            'configuration': setup_source,
            'phpcode': body_source,
            'dataflow': dataflow_source,
            'helper_module': self._safe_parse_module(helper_source),
            'configuration_module': self._safe_parse_module(setup_source),
            'body_module': self._safe_parse_module(body_source),
            'prelude_module': prelude_module,
            'skipif_lines': self._seed_decorator_lines(seed),
            'base_names': self._seed_base_names(seed),
            'helper_method_names': helper_methods,
            'helper_value_names': helper_value_names,
            'runtime_attribute_names': runtime_attribute_names,
            'helper_mapping': seed_mapping,
            'source_class_name': source_class_name,
        }
