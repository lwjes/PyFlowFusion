import ast
import subprocess


CRASH_MARKERS = (
    'Fatal Python error',
    'AddressSanitizer',
    'Segmentation fault',
    'Aborted',
    'Assertion `',
)
SYNTAX_MARKERS = ('SyntaxError', 'IndentationError', 'TabError')
TIMEOUT_MARKERS = ('TimeoutExpired',)
SKIP_MARKERS = (
    'unittest.case.SkipTest:',
    'SkipTest:',
    'Standard library module ',
)


def classify_failure(returncode, output):
    if any(marker in output for marker in SYNTAX_MARKERS):
        return 'syntax'
    if any(marker in output for marker in TIMEOUT_MARKERS):
        return 'failure'
    if any(marker in output for marker in SKIP_MARKERS):
        return 'skip'
    if returncode < 0 or any(marker in output for marker in CRASH_MARKERS):
        return 'crash'
    if returncode != 0:
        return 'failure'
    return 'ok'


def run_testcase_once(
    python_bin,
    testcase_path,
    *,
    cwd,
    env,
    timeout_seconds,
    subprocess_module=subprocess,
):
    process_env = env
    if env and env.get('FLOWFUSION_REAL_PYTHON_BIN'):
        process_env = env.copy()
        child_pythonpath = process_env.pop('PYTHONPATH', '')
        if child_pythonpath:
            process_env['FLOWFUSION_CHILD_PYTHONPATH'] = child_pythonpath

    proc = subprocess_module.run(
        [python_bin, testcase_path],
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        cwd=cwd,
        env=process_env,
    )
    output = (proc.stdout or '') + (proc.stderr or '')
    return output, proc.returncode


def validate_syntax(testcase_path):
    with open(testcase_path, 'r', encoding='utf-8', errors='ignore') as handle:
        source = handle.read()
    ast.parse(source)
