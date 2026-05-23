import os


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED_CPYTHON_ROOT = os.path.dirname(PROJECT_ROOT)
WORKSPACE_ROOT = os.path.join(PROJECT_ROOT, 'workspace')
LOCAL_COVERAGE_ROOT = os.path.join(WORKSPACE_ROOT, 'python-cov')


CONFIG = {
    'paths': {
        'project_root': PROJECT_ROOT,
        'tmp_queue_dir': os.path.join(WORKSPACE_ROOT, 'tmp_dir'),
        'py_seeds_dir': os.path.join(WORKSPACE_ROOT, 'py_seeds'),
        'py_deps_dir': os.path.join(WORKSPACE_ROOT, 'py_deps'),
        'py_fused_dir': os.path.join(WORKSPACE_ROOT, 'py_fused'),
        'bugs_dir': os.path.join(WORKSPACE_ROOT, 'bugs'),
        'fixme_dir': os.path.join(WORKSPACE_ROOT, 'fixme'),
        'knowledge_dir': os.path.join(PROJECT_ROOT, 'knowledges'),
    },
    'cpython': {
        'source_root': os.path.join(SHARED_CPYTHON_ROOT, 'cpython-src'),
        'fuzz_python_bin': os.path.join(LOCAL_COVERAGE_ROOT, 'python'),
        'cov_python_bin': os.path.join(LOCAL_COVERAGE_ROOT, 'python'),
        'cov_build_root': LOCAL_COVERAGE_ROOT,
    },
    'runtime': {
        'stop_after': -1,
        'mutation': True,
        'apifuzz': False,
        'ini': False,
        'case_timeout': 10,
        'pending_batch_size': 100,
        'pending_max_tmp': 200,
        'pending_timeout': 30,
    },
    'coverage': {
        'interval': 1800,
        'csv_path': os.path.join(WORKSPACE_ROOT, 'cov_record', 'coverage_24h.csv'),
        'phase': '',
        'gcovr_root': os.path.join(SHARED_CPYTHON_ROOT, 'cpython-src'),
    },
    'knowledge': {
        'fixme_blocklist': os.path.join(PROJECT_ROOT, 'knowledges', 'fixme_blocklist.txt'),
    },
}
