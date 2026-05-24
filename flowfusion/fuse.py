import ast
import copy
import os
import time
from random import choice

from .dataflow import PythonFastDataflow
from flowfusion.fusion.ast_rewriters import (
    _AttributeLoadRewriter,
    _NameLoadRewriter,
)
from flowfusion.fusion.class_assembly import ClassAssemblyMixin
from flowfusion.fusion.composer import ComposerMixin
from flowfusion.fusion.decorator_runtime import DecoratorRuntimeMixin
from flowfusion.fusion.prelude import PreludeProcessingMixin
from flowfusion.fusion.seed_preparation import SeedPreparationMixin
from flowfusion.fusion.seed_repository import load_seed_records
from flowfusion.fusion.seed_filters import SeedFilteringMixin
from flowfusion.fusion.source_analysis import SourceAnalysisMixin
from .mutator import Mutator


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


class Fusion(
    ComposerMixin,
    DecoratorRuntimeMixin,
    ClassAssemblyMixin,
    PreludeProcessingMixin,
    SeedPreparationMixin,
    SeedFilteringMixin,
    SourceAnalysisMixin,
):
    fuse_count = 0

    def __init__(self, config):
        self.config = config
        self.test_root = config.paths.project_root
        self.apifuzz = config.runtime.apifuzz
        self.ini = config.runtime.ini
        self.mutation = config.runtime.mutation
        self.mut = Mutator()
        self.runtime_dataflow = PythonFastDataflow()
        self.seeds = []
        self.temp_dir = config.paths.tmp_queue_dir
        self.pending_max_tmp = config.runtime.pending_max_tmp

    def _tmp_backlog(self):
        backlog = 0
        for filename in os.listdir(self.temp_dir):
            if filename.startswith('fused') and filename.endswith('.py'):
                backlog += 1
        return backlog

    def _safe_eval_list(self, maybe_list_str):
        if not maybe_list_str:
            return []
        try:
            value = ast.literal_eval(maybe_list_str)
        except Exception:
            return []
        return value if isinstance(value, list) else []

    def _runtime_dataflows(self, source):
        if not source:
            return []
        try:
            _, dataflows = self.runtime_dataflow.analyze(source)
        except Exception:
            return []
        return dataflows if isinstance(dataflows, list) else []

    def _strip_nul_bytes(self, text):
        if not isinstance(text, str) or '\x00' not in text:
            return text
        return text.replace('\x00', '')

    def _safe_parse_module(self, code):
        if isinstance(code, ast.Module):
            return copy.deepcopy(code)
        if isinstance(code, list):
            return ast.Module(body=copy.deepcopy(code), type_ignores=[])
        if not code or not code.strip():
            return ast.Module(body=[], type_ignores=[])
        return ast.parse(self._strip_nul_bytes(code))

    def _module_to_source(self, module):
        lines = []
        for stmt in module.body:
            rendered = ast.unparse(stmt).strip()
            if rendered:
                lines.append(rendered)
        return '\n'.join(lines)

    def _fuse_dataflow_interleave(self, test1, test2, dataflow1, dataflow2):
        if not dataflow1 or not dataflow2:
            return test1, test2

        source_candidates = self._collect_safe_source_flows(test1, dataflow1)
        target_candidates = self._collect_safe_target_flows(test2, dataflow2)
        if not source_candidates or not target_candidates:
            return test1, test2

        test1_flow = choice(source_candidates)
        test2_flow = choice(target_candidates)

        test1 += f'\n_fusion = {test1_flow}\n'
        test2 = self._bridge_python_dataflow(test2, test2_flow)

        return test1, test2

    def _rewrite_python_loads(self, source, old_name, new_name):
        try:
            module = ast.parse(self._strip_nul_bytes(source))
        except (SyntaxError, ValueError):
            return replace_random_occurrence(source, old_name, new_name)

        rewritten = _NameLoadRewriter(old_name, new_name).visit(module)
        ast.fix_missing_locations(rewritten)
        return self._module_to_source(rewritten)

    def _rewrite_python_attribute_loads(self, source, owner_name, attr_name, new_name):
        try:
            module = ast.parse(self._strip_nul_bytes(source))
        except (SyntaxError, ValueError):
            return replace_random_occurrence(source, f'{owner_name}.{attr_name}', new_name)

        rewritten = _AttributeLoadRewriter(owner_name, attr_name, new_name).visit(module)
        ast.fix_missing_locations(rewritten)
        return self._module_to_source(rewritten)

    def _bridge_python_dataflow(self, source, flow_name):
        if not flow_name:
            return source
        if '.' in flow_name:
            owner_name, _, attr_name = flow_name.partition('.')
            if owner_name not in {'self', 'cls'} or not attr_name:
                return source
            return self._rewrite_python_attribute_loads(source, owner_name, attr_name, '_fusion')
        if flow_name in self._collect_simple_assigned_names(source):
            return f'{flow_name} = _fusion\n{source}'
        return source

    def fuse(self):
        seed1 = choice(self.seeds)
        seed2 = choice(self.seeds)
        return self._compose_python_unittest(seed1, seed2)

    def write_file(self, filepath, content):
        parent = os.path.dirname(filepath)
        if parent and not os.path.exists(parent):
            os.makedirs(parent, exist_ok=True)
        with open(filepath, 'w', encoding='utf-8', errors='ignore') as handle:
            handle.write(content)

    def load_seeds(self):
        records = load_seed_records(self.test_root)

        if not records:
            raise RuntimeError('No Python seeds available')

        filtered_records = []
        dropped_unresolved_count = 0
        dropped_placeholder_count = 0
        for record in records:
            unresolved = self._seed_unresolved_self_dependencies(record)
            if unresolved:
                dropped_unresolved_count += 1
                continue
            if self._seed_has_non_runnable_placeholders(record):
                dropped_placeholder_count += 1
                continue
            filtered_records.append(record)

        dropped_abstractmethod_count = 0
        keep_records = []
        for record in filtered_records:
            if self._seed_uses_abstractmethod(record):
                dropped_abstractmethod_count += 1
                continue
            keep_records.append(record)
        filtered_records = keep_records

        if dropped_unresolved_count:
            print(
                '[FlowFusion] dropped '
                f'{dropped_unresolved_count} stale seeds with unresolved self/cls dependencies'
            )
        if dropped_placeholder_count:
            print(
                '[FlowFusion] dropped '
                f'{dropped_placeholder_count} non-runnable template seeds with placeholder contracts'
            )
        if dropped_abstractmethod_count:
            print(
                '[FlowFusion] dropped '
                f'{dropped_abstractmethod_count} seeds using abstractmethod'
            )

        if not filtered_records:
            raise RuntimeError('No Python seeds available after filtering')

        self.seeds = filtered_records

    def load_apis(self):
        return

    def main(self):
        self.load_seeds()
        self.load_apis()

        while True:
            if self.pending_max_tmp > 0:
                while self._tmp_backlog() >= self.pending_max_tmp:
                    time.sleep(0.2)
            try:
                fused_test = self.fuse()
            except (SyntaxError, ValueError):
                continue
            self.fuse_count += 1
            self.fuse_count %= 10000
            filepath = os.path.join(self.temp_dir, f'fused{self.fuse_count}.py')
            self.write_file(filepath, fused_test)
