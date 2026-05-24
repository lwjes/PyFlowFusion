import ast
import unittest


TESTCASE_MEMBER_NAMES = set(dir(unittest.TestCase))


class SeedFilteringMixin:
    def _seed_source_chunks(self, seed):
        return [
            seed.get('prelude', ''),
            seed.get('helpers', ''),
            seed.get('configuration', ''),
            seed.get('phpcode', ''),
        ]

    def _collect_abstractmethod_aliases(self, seed):
        abstractmethod_aliases = {'abstractmethod'}
        abc_module_aliases = {'abc'}

        for chunk in self._seed_source_chunks(seed):
            if not chunk:
                continue
            try:
                module = self._safe_parse_module(chunk)
            except (SyntaxError, ValueError, TypeError, AttributeError):
                continue
            for stmt in module.body:
                if isinstance(stmt, ast.ImportFrom) and stmt.module == 'abc':
                    for alias in stmt.names:
                        if alias.name == 'abstractmethod':
                            abstractmethod_aliases.add(alias.asname or alias.name)
                elif isinstance(stmt, ast.Import):
                    for alias in stmt.names:
                        if alias.name == 'abc':
                            abc_module_aliases.add(alias.asname or alias.name)

        return abstractmethod_aliases, abc_module_aliases

    def _decorator_uses_abstractmethod(self, decorator, abstractmethod_aliases, abc_module_aliases):
        if isinstance(decorator, ast.Name):
            return decorator.id in abstractmethod_aliases
        if (
            isinstance(decorator, ast.Attribute)
            and isinstance(decorator.value, ast.Name)
            and decorator.value.id in abc_module_aliases
            and decorator.attr == 'abstractmethod'
        ):
            return True
        return False

    def _seed_uses_abstractmethod(self, seed):
        chunks = self._seed_source_chunks(seed)
        if not any('abstractmethod' in (chunk or '').lower() for chunk in chunks):
            return False

        abstractmethod_aliases, abc_module_aliases = self._collect_abstractmethod_aliases(seed)
        for chunk in chunks:
            if not chunk:
                continue
            try:
                module = self._safe_parse_module(chunk)
            except (SyntaxError, ValueError, TypeError, AttributeError):
                continue
            for node in ast.walk(module):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    continue
                if any(
                    self._decorator_uses_abstractmethod(
                        decorator,
                        abstractmethod_aliases,
                        abc_module_aliases,
                    )
                    for decorator in node.decorator_list
                ):
                    return True
        return False

    def _seed_unresolved_self_dependencies(self, seed):
        loaded = set()
        for chunk in [seed.get('helpers', ''), seed.get('configuration', ''), seed.get('phpcode', '')]:
            loaded.update(self._collect_self_cls_loaded_attribute_names(chunk))

        defined = set(self._collect_helper_member_names(seed.get('helpers', '')))
        for chunk in [seed.get('helpers', ''), seed.get('configuration', ''), seed.get('phpcode', '')]:
            defined.update(self._collect_self_cls_attribute_names(chunk))

        return {
            name
            for name in loaded
            if name not in defined and name not in TESTCASE_MEMBER_NAMES
        }

    def _seed_has_non_runnable_placeholders(self, seed):
        helper_source = seed.get('helpers', '')
        if not helper_source:
            return False

        called_members = set()
        loaded_members = set()
        assigned_members = set()
        for chunk in [helper_source, seed.get('configuration', ''), seed.get('phpcode', '')]:
            called_members.update(self._collect_called_self_cls_members(chunk))
            loaded_members.update(self._collect_self_cls_loaded_attribute_names(chunk))
            assigned_members.update(self._collect_self_cls_attribute_names(chunk))

        none_placeholders = self._extract_direct_none_placeholders(helper_source)
        unresolved_none_members = {
            name
            for name in none_placeholders
            if name in called_members and name not in assigned_members
        }

        notimplemented_methods = self._extract_notimplemented_placeholder_methods(helper_source)
        unresolved_notimplemented_methods = {
            name
            for name in notimplemented_methods
            if name in called_members
        }

        notimplemented_properties = self._extract_notimplemented_placeholder_properties(helper_source)
        unresolved_notimplemented_properties = {
            name
            for name in notimplemented_properties
            if name in loaded_members and name not in assigned_members
        }

        return bool(
            unresolved_none_members
            or unresolved_notimplemented_methods
            or unresolved_notimplemented_properties
        )
