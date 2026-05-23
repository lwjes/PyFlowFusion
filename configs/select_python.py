import os


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED_CPYTHON_ROOT = os.path.dirname(PROJECT_ROOT)
WORKSPACE_ROOT = os.path.join(PROJECT_ROOT, 'workspace')
LOCAL_COVERAGE_ROOT = os.path.join(WORKSPACE_ROOT, 'python-cov')


CONFIG = {
    'cpython': {
        'fuzz_python_bin': os.path.abspath(
            os.getenv(
                'FLOWFUSION_PYTHON_BIN',
                os.path.join(LOCAL_COVERAGE_ROOT, 'python'),
            )
        ),
        'cov_python_bin': os.path.join(LOCAL_COVERAGE_ROOT, 'python'),
        'cov_build_root': LOCAL_COVERAGE_ROOT,
    },
}
