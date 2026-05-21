import os


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


CONFIG = {
    'cpython': {
        'fuzz_python_bin': os.path.abspath(
            os.getenv(
                'FLOWFUSION_TIMING_PROXY_BIN',
                os.path.join(PROJECT_ROOT, 'scripts', 'case_timer.py'),
            )
        ),
    },
    'runtime': {
        'stop_after': 10000,
        'case_timeout': 10,
        'pending_timeout': 0,
    },
    'coverage': {
        'interval': 0,
        'csv_path': '',
    },
}
