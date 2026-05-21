import ast
import textwrap

from flowfusion.fusion.ast_rewriters import _StringLiteralRewriter


class ComposerMixin:
    def _indent_block(self, source, level=1):
        if not source.strip():
            source = 'pass'
        return textwrap.indent(source.strip(), ' ' * (level * 4))

    def _extract_future_imports(self, source):
        if not source or not source.strip():
            return [], source

        module = self._safe_parse_module(source)
        future_lines = []
        seen = set()
        kept_body = []
        for stmt in module.body:
            if (
                isinstance(stmt, ast.ImportFrom)
                and stmt.module == '__future__'
                and stmt.level == 0
            ):
                rendered = ast.unparse(stmt).strip()
                if rendered and rendered not in seen:
                    seen.add(rendered)
                    future_lines.append(rendered)
                continue
            kept_body.append(stmt)
        kept_module = ast.Module(body=kept_body, type_ignores=[])
        return future_lines, self._module_to_source(kept_module)

    def _extract_test_name(self, description):
        if not description or '::' not in description:
            return ''
        return description.rsplit('::', 1)[-1].strip()

    def _extract_class_name(self, description):
        if not description or '::' not in description:
            return ''
        parts = [part.strip() for part in description.split('::') if part.strip()]
        if len(parts) < 2:
            return ''
        return parts[-2]

    def _rewrite_string_literals(self, source, replacements):
        if not source or not replacements:
            return source

        try:
            module = ast.parse(self._strip_nul_bytes(source))
        except (SyntaxError, ValueError):
            rewritten = source
            for old, new in replacements:
                if old and old != new:
                    rewritten = rewritten.replace(old, new)
            return rewritten

        rewritten = _StringLiteralRewriter(replacements).visit(module)
        ast.fix_missing_locations(rewritten)
        return self._module_to_source(rewritten)

    def _normalize_fused_test_name_expectations(self, source, description):
        test_name = self._extract_test_name(description)
        if not test_name or test_name == 'test_fused':
            return source
        return self._rewrite_string_literals(source, [(test_name, 'test_fused')])

    def _build_fused_body_source(
        self,
        prepared1,
        prepared2,
        ignored_prelude,
        runtime_code1,
        runtime_code2,
    ):
        body_lines = [
            f'# fused from {prepared1["description"]}',
            '\n'.join(ignored_prelude).strip(),
            runtime_code1.strip(),
            f'# fused from {prepared2["description"]}',
            runtime_code2.strip(),
        ]
        return '\n'.join(line for line in body_lines if line)

    def _render_fused_module(
        self,
        future_imports,
        prelude,
        sanitized_base_source,
        class_base_list,
        class_parts,
        source_class_aliases,
    ):
        fused_sections = []
        if future_imports:
            fused_sections.append('\n'.join(future_imports))
        fused_sections.append('import unittest')
        if prelude:
            fused_sections.append(prelude)
        if sanitized_base_source:
            fused_sections.append(sanitized_base_source)
        fused_sections.append(f'class FlowFusionTest({class_base_list}):\n' + '\n\n'.join(class_parts))
        if source_class_aliases:
            fused_sections.append(source_class_aliases)
        fused_sections.append("if __name__ == '__main__':\n    unittest.main()")
        return '\n\n'.join(section for section in fused_sections if section.strip()) + '\n'

    def _compose_python_unittest(self, seed1, seed2):
        prepared1 = self._prepare_python_seed(seed1, 'flowfusion_seed1')
        prepared2 = self._prepare_python_seed(seed2, 'flowfusion_seed2')

        code1 = prepared1['phpcode']
        code2 = prepared2['phpcode']
        if self.mutation:
            code1 = self.mut.mutate(code1)
            code2 = self.mut.mutate(code2)

        dataflow1 = self._runtime_dataflows(code1) or self._safe_eval_list(prepared1['dataflow'])
        dataflow2 = self._runtime_dataflows(code2) or self._safe_eval_list(prepared2['dataflow'])
        new_code1, new_code2 = self._fuse_dataflow_interleave(code1, code2, dataflow1, dataflow2)

        prepared_seeds = [prepared1, prepared2]
        decorators, ignored, ignored_prelude = self._collect_decorator_context(prepared_seeds)

        prelude = self._combine_preludes(prepared1, prepared2)
        future_imports, prelude = self._extract_future_imports(prelude)
        source_class_aliases = self._build_source_class_aliases(prepared_seeds, prelude)

        runtime_code1 = self._prepare_runtime_code(prepared1, new_code1)
        runtime_code2 = self._prepare_runtime_code(prepared2, new_code2)
        body_source = self._build_fused_body_source(
            prepared1,
            prepared2,
            ignored_prelude,
            runtime_code1,
            runtime_code2,
        )

        sanitized_base_source, class_base_list = self._build_class_base_definition(prepared_seeds)
        class_parts = self._build_class_parts(prepared1, prepared2, body_source, decorators, ignored)
        fused = self._render_fused_module(
            future_imports,
            prelude,
            sanitized_base_source,
            class_base_list,
            class_parts,
            source_class_aliases,
        )

        ast.parse(self._strip_nul_bytes(fused))
        return fused
