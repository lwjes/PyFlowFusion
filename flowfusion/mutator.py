import ast
import builtins
import keyword
from random import randint, choice, shuffle, random
import re
import subprocess
import os
import sys
import math


class Mutator:
    """
    Mutator adapted for Python source. Introduces low-probability mutations
    to exercise edge cases (integers, strings, operators, variable names).
    """

    def __init__(self):
        pass

    def _replace_match(self, code, match, replacement):
        return code[:match.start()] + replacement + code[match.end():]

    def _replace_random_regex_match(self, code, pattern, replacement, flags=0):
        matches = list(re.finditer(pattern, code, flags))
        if not matches:
            return code
        selected = choice(matches)
        return self._replace_match(code, selected, replacement)

    def extract_sec(self, test, section):
        """
        Legacy helper kept for compatibility with older callers.
        Args:
            test: The full serialized text.
            section: The section label.

        Returns:
            The content of the specified section or an empty string if not found.
        """
        if section not in test:
            return ""
        start_idx = test.find(section) + len(section)
        x = re.search("--([_A-Z]+)--", test[start_idx:])
        end_idx = x.start() if x != None else len(test) - 1
        ret = test[start_idx:start_idx + end_idx].strip("\n")
        return ret

    """
    `mr` means `mutation rule`
    Below are various mutation rules applied to Python code.
    """

    def _mr_arith_operators(self, code):
        """
        Randomly mutate arithmetic operators such as +, -, *, /, %, **.
        99.9% of the time, this function will return the original code without changes.
        """
        if random() > 0.001:
            return code

        target_regex = r'\*\*|[-+*/%]'
        replacements = ['+', '-', '*', '/', '%', '**']
        matches = list(re.finditer(target_regex, code))
        if not matches:
            return code
        return self._replace_match(code, choice(matches), choice(replacements))

    def _mr_assign_operators(self, code):
        """
        Randomly mutate assignment operators such as +=, -=, *=, /=, %=.
        99.9% of the time, this function will return the original code without changes.
        """
        if random() > 0.001:
            return code

        target_regex = r'\+=|-=|\*=|/=|%='
        replacements = ['+=', '-=', '*=', '/=', '%=']
        matches = list(re.finditer(target_regex, code))
        if not matches:
            return code
        victim = choice(matches).group(0)
        replace = choice([op for op in replacements if op != victim])
        return self._replace_random_regex_match(code, re.escape(victim), replace)

    def _mr_logical_operators(self, code):
        """
        Randomly mutate logical operators such as 'and', 'or', 'xor', '&&', '||'.
        99.9% of the time, this function will return the original code without changes.
        """
        if random() > 0.001:
            return code

        target_regex = r'\band\b|\bor\b|\bnot\b|\bxor\b'
        replacements = ['and', 'or', 'not', 'xor']
        matches = list(re.finditer(target_regex, code))
        if not matches:
            return code
        victim = choice(matches).group(0)
        replace = choice([op for op in replacements if op != victim])
        return self._replace_random_regex_match(code, re.escape(victim), replace)

    def _mr_integer(self, code):
        """
        Randomly mutate integer expressions to special boundary values like -1 and sys.maxsize.
        99.9% of the time, this function will return the original code without changes.
        """
        if random() > 0.001:
            return code

        target_regex = r'(?<![A-Za-z0-9_])(?:0x[0-9a-fA-F]+|[1-9][0-9]*|0)(?![A-Za-z0-9_])'
        # Avoid replacing numeric literals with None: this tends to create
        # low-value type crashes (e.g. eval(None), range(None)) that do not
        # help fuzzing signal quality.
        replacements = ['-1', '0', str(-sys.maxsize-1), str(sys.maxsize), 'float("nan")', 'float("inf")']
        matches = list(re.finditer(target_regex, code))
        if not matches:
            return code
        return self._replace_match(code, choice(matches), choice(replacements))

    def _mr_string(self, code):
        """
        Randomly mutate string literals with special values like random bytes or special encoding.
        99% of the time, this function will return the original code without changes.
        """
        if random() > 0.01:
            return code

        # naive string literal matcher (single/double/triple)
        target_regex = r"('''.*?'''|\"\"\".*?\"\"\"|'([^'\\]|\\.)*'|\"([^\"\\]|\\.)*\")"
        matches = list(re.finditer(target_regex, code, flags=re.DOTALL))
        if not matches:
            return code
        # Keep the null-byte mutation as an escaped sequence in source text,
        # not a literal NUL character, so AST parsing can still proceed.
        # Keep string mutations string-typed to reduce trivial TypeError drift.
        replacements = [f'"{chr(randint(32,126))}"', '""', '"\\x00"']
        return self._replace_match(code, choice(matches), choice(replacements))

    def _mr_variable(self, code):
        """
        Randomly mutate variables by replacing them with other variables.
        99.5% of the time, this function will return the original code without changes.
        """
        if random() > 0.002:
            return code

        variables = self._collect_mutable_variables(code)
        if len(variables) < 2:
            return code
        victim = choice(variables)
        replace = choice([v for v in variables if v!=victim])
        return self._replace_random_regex_match(code, r'(?<!\.)\b' + re.escape(victim) + r'\b', replace)

    def _collect_mutable_variables(self, code):
        """
        Collect mutation candidates that are likely local value slots:
        - must be assigned and later loaded in the snippet
        - assignment value must be simple/literal-like
        - must not be imported module names / function names / class names
        - must not be private/dunder/internal flowfusion helper names
        """
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return []

        stored = set()
        loaded = set()
        imported = set()
        declared = set()
        simple_assigned = set()

        def is_simple_value(node):
            return isinstance(
                node,
                (
                    ast.Constant,
                    ast.Tuple,
                    ast.List,
                    ast.Set,
                    ast.Dict,
                    ast.UnaryOp,
                    ast.BinOp,
                    ast.JoinedStr,
                ),
            )

        def add_simple_targets(target):
            if isinstance(target, ast.Name):
                simple_assigned.add(target.id)
                return
            if isinstance(target, (ast.Tuple, ast.List)):
                for elt in target.elts:
                    add_simple_targets(elt)

        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                if isinstance(node.ctx, ast.Store):
                    stored.add(node.id)
                elif isinstance(node.ctx, ast.Load):
                    loaded.add(node.id)
            elif isinstance(node, ast.Assign):
                if is_simple_value(node.value):
                    for target in node.targets:
                        add_simple_targets(target)
            elif isinstance(node, ast.AnnAssign):
                if node.value is not None and is_simple_value(node.value):
                    add_simple_targets(node.target)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.asname or alias.name.split('.')[0])
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name == '*':
                        continue
                    imported.add(alias.asname or alias.name)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                declared.add(node.name)

        blocked = set(keyword.kwlist)
        blocked.update(dir(builtins))
        blocked.update({'self', 'cls', 'super'})
        blocked.update(imported)
        blocked.update(declared)

        candidates = []
        for name in sorted(stored.intersection(loaded).intersection(simple_assigned)):
            if (
                not name
                or name in blocked
                or name.startswith('_')
                or name.startswith('flowfusion_')
                or name.isupper()
            ):
                continue
            candidates.append(name)
        return candidates

    def mutate(self, code):
        code = self._mr_arith_operators(code)
        code = self._mr_assign_operators(code)
        code = self._mr_logical_operators(code)
        code = self._mr_integer(code)
        code = self._mr_string(code)
        code = self._mr_variable(code)
        return code
