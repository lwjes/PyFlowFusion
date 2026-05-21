import os
import unittest


TESTCASE_MEMBER_NAMES = set(dir(unittest.TestCase))


class SeedFilteringMixin:
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

    def _default_fixme_blocklist_path(self):
        return getattr(self, 'fixme_blocklist_path', '')

    def _load_fixme_blocklist_rules(self):
        path = self._default_fixme_blocklist_path()
        if not path or not os.path.isfile(path):
            return []

        rules = []
        with open(path, 'r', encoding='utf-8', errors='ignore') as handle:
            for raw in handle:
                line = raw.strip()
                if not line or line.startswith('#'):
                    continue
                scope = 'any'
                pattern = line
                if ':' in line:
                    prefix, rest = line.split(':', 1)
                    normalized_prefix = prefix.strip().lower()
                    if normalized_prefix in {'any', 'description', 'code'}:
                        scope = normalized_prefix
                        pattern = rest.strip()
                if not pattern:
                    continue
                rules.append((scope, pattern.lower()))
        return rules

    def _record_matches_fixme_blocklist(self, record, rules):
        if not rules:
            return False

        description_text = (record.get('description') or '').lower()
        code_text = '\n'.join(
            [
                record.get('phpcode') or '',
                record.get('configuration') or '',
                record.get('helpers') or '',
                record.get('prelude') or '',
                record.get('skipif') or '',
            ]
        ).lower()
        any_text = f'{description_text}\n{code_text}'

        for scope, pattern in rules:
            if scope == 'description' and pattern in description_text:
                return True
            if scope == 'code' and pattern in code_text:
                return True
            if scope == 'any' and pattern in any_text:
                return True
        return False
