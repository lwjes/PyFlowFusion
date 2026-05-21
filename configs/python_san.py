import os


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACE_ROOT = os.path.join(PROJECT_ROOT, 'workspace')


CONFIG = {
    'cpython': {
        'fuzz_python_bin': os.path.join(WORKSPACE_ROOT, 'python-san', 'python'),
    },
    'coverage': {
        'interval': 0,
    },
}
