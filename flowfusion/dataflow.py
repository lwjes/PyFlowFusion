import ast


class PythonFastDataflow:
    """
    Lightweight AST-based dataflow extraction for Python source.
    """

    def __init__(self):
        self.variables = []
        self.dataflows = []
        self._builtin_names = set(dir(__builtins__))

    def _name_from_node(self, node):
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            base = self._name_from_node(node.value)
            return f'{base}.{node.attr}' if base else node.attr
        if isinstance(node, ast.Subscript):
            return self._name_from_node(node.value)
        return None

    def _target_names(self, node):
        names = set()
        if node is None:
            return names
        if isinstance(node, (ast.Tuple, ast.List)):
            for elt in node.elts:
                names |= self._target_names(elt)
            return names
        direct = self._name_from_node(node)
        if direct:
            names.add(direct)
        return names

    def _collect_names(self, node):
        names = set()
        if node is None:
            return names

        direct = self._name_from_node(node)
        if direct:
            names.add(direct)

        for child in ast.walk(node):
            child_name = self._name_from_node(child)
            if child_name:
                names.add(child_name)

        return names

    def _filter_names(self, names):
        filtered = set()
        for name in names:
            if not name or name == 'self':
                continue
            if name in self._builtin_names:
                continue
            filtered.add(name)
        return filtered

    def _find(self, item, parent):
        if item not in parent:
            parent[item] = item
        if parent[item] != item:
            parent[item] = self._find(parent[item], parent)
        return parent[item]

    def _union(self, left, right, parent):
        left_root = self._find(left, parent)
        right_root = self._find(right, parent)
        if left_root != right_root:
            parent[right_root] = left_root

    def analyze(self, pycode):
        try:
            tree = ast.parse(pycode)
        except SyntaxError:
            self.variables = []
            self.dataflows = []
            return self.variables, self.dataflows

        parent = {}
        all_vars = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                lhs = set()
                for target in node.targets:
                    lhs |= self._target_names(target)
                rhs = self._collect_names(node.value)
            elif isinstance(node, ast.AnnAssign):
                lhs = self._target_names(node.target)
                rhs = self._collect_names(node.value)
            elif isinstance(node, ast.AugAssign):
                lhs = self._target_names(node.target)
                rhs = self._collect_names(node.value)
            elif isinstance(node, ast.NamedExpr):
                lhs = self._target_names(node.target)
                rhs = self._collect_names(node.value)
            elif isinstance(node, ast.For):
                lhs = self._target_names(node.target)
                rhs = self._collect_names(node.iter)
            elif isinstance(node, ast.comprehension):
                lhs = self._target_names(node.target)
                rhs = self._collect_names(node.iter)
            elif isinstance(node, ast.With):
                lhs = set()
                rhs = set()
                for item in node.items:
                    lhs |= self._target_names(item.optional_vars)
                    rhs |= self._collect_names(item.context_expr)
            elif isinstance(node, ast.ExceptHandler):
                lhs = {node.name} if node.name else set()
                rhs = self._collect_names(node.type)
            elif isinstance(node, ast.Call):
                lhs = self._collect_names(node.func)
                rhs = set()
                for arg in node.args:
                    rhs |= self._collect_names(arg)
                for kw in node.keywords:
                    rhs |= self._collect_names(kw.value)
            else:
                continue

            all_vars |= lhs | rhs
            for left in lhs:
                for right in rhs:
                    self._union(left, right, parent)

        all_vars = self._filter_names(all_vars)
        groups = {}
        for var in all_vars:
            root = self._find(var, parent)
            groups.setdefault(root, []).append(var)

        self.variables = sorted(all_vars)
        self.dataflows = [sorted(set(group)) for group in groups.values()]
        return self.variables, self.dataflows
