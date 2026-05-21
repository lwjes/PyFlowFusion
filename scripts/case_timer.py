#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


CRASH_MARKERS = (
    'Fatal Python error',
    'AddressSanitizer',
    'Segmentation fault',
    'Aborted',
    'Assertion `',
)
SYNTAX_MARKERS = ('SyntaxError', 'IndentationError', 'TabError')
SKIP_MARKERS = (
    'unittest.case.SkipTest:',
    'SkipTest:',
    'Standard library module ',
)
MISSING_PATH_PATTERNS = (
    r"FileNotFoundError:\s*\[Errno 2\].*?:\s*'([^']+)'",
    r"\[Errno 2\]\s+No such file or directory:\s*'([^']+)'",
    r"[Cc]an't read certificate file\s+'([^']+)'",
)
DEFAULT_MAX_HYDRATION_ATTEMPTS = 8
DEFAULT_TIMEOUT_MARGIN_MS = 150
CSV_FIELDS = (
    'case_key',
    'testcase_path',
    'start_iso',
    'end_iso',
    'duration_ms',
    'bucket',
    'result',
    'returncode',
    'attempts',
    'timed_out',
)


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def env_path(name: str, default: Path) -> Path:
    value = os.getenv(name)
    if value:
        return Path(value).expanduser().resolve()
    return default.expanduser().resolve()


def env_command(name: str, default: Path) -> str:
    value = os.getenv(name)
    if not value:
        return str(default.expanduser().resolve())
    if os.path.isabs(value) or os.sep in value or (os.altsep and os.altsep in value):
        return str(Path(value).expanduser().resolve())
    return value


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec='seconds')


def case_key_for(testcase_path: Path) -> str:
    return hashlib.sha1(str(testcase_path).encode('utf-8')).hexdigest()


def state_path_for(state_dir: Path, case_key: str) -> Path:
    return state_dir / f'{case_key}.json'


def load_state(state_path: Path) -> dict:
    if not state_path.is_file():
        return {}
    try:
        return json.loads(state_path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state_path: Path, state: dict) -> None:
    tmp_path = state_path.with_suffix('.tmp')
    tmp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp_path, state_path)


def remove_state(state_path: Path) -> None:
    try:
        state_path.unlink()
    except FileNotFoundError:
        return


def extract_missing_file_path(output: str) -> str:
    for pattern in MISSING_PATH_PATTERNS:
        matches = list(re.finditer(pattern, output or ''))
        if matches:
            return matches[-1].group(1)
    return ''


def relative_path_under_fused_dir(maybe_path: str, fused_dir: Path) -> str:
    if not maybe_path:
        return ''
    try:
        rel_path = os.path.relpath(
            os.path.normpath(maybe_path),
            os.path.normpath(str(fused_dir)),
        )
    except ValueError:
        return ''
    if rel_path in {'.', ''} or rel_path.startswith('..') or os.path.isabs(rel_path):
        return ''
    return rel_path


def resource_source_roots(py_deps_dir: Path, py_seeds_dir: Path, cpython_root: Path) -> list[Path]:
    return [
        py_deps_dir / 'test',
        py_deps_dir / 'support_lib' / 'test',
        py_deps_dir,
        py_seeds_dir,
        cpython_root / 'Lib' / 'test',
    ]


def is_retryable_missing_resource(
    output: str,
    *,
    fused_dir: Path,
    py_deps_dir: Path,
    py_seeds_dir: Path,
    cpython_root: Path,
) -> bool:
    missing_path = extract_missing_file_path(output)
    rel_path = relative_path_under_fused_dir(missing_path, fused_dir)
    if not rel_path:
        return False
    for root in resource_source_roots(py_deps_dir, py_seeds_dir, cpython_root):
        if (root / rel_path).is_file():
            return True
    return False


def classify_result(returncode: int, output: str, timed_out: bool) -> str:
    if timed_out or 'TimeoutExpired' in output:
        return 'timeout'
    if any(marker in output for marker in SYNTAX_MARKERS):
        return 'syntax'
    if any(marker in output for marker in SKIP_MARKERS):
        return 'skip'
    if returncode < 0 or any(marker in output for marker in CRASH_MARKERS):
        return 'crash'
    if returncode != 0:
        return 'failure'
    return 'ok'


def bucket_for(duration_ms: int, timed_out: bool, timeout_seconds: int) -> str:
    if timed_out or duration_ms >= timeout_seconds * 1000:
        return 'timeout'
    seconds = duration_ms / 1000.0
    if seconds < 1.0:
        return '<1s'
    if seconds < 3.0:
        return '1-3s'
    if seconds < 5.0:
        return '3-5s'
    if seconds < 7.0:
        return '5-7s'
    if seconds < 9.0:
        return '7-9s'
    return '9-10s'


def append_csv_row(csv_path: Path, row: dict) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not csv_path.exists() or csv_path.stat().st_size == 0
    with csv_path.open('a', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def flush_child_output(stdout: str, stderr: str) -> None:
    if stdout:
        sys.stdout.write(stdout)
    if stderr:
        sys.stderr.write(stderr)
    sys.stdout.flush()
    sys.stderr.flush()


def main() -> int:
    if len(sys.argv) < 2:
        print('usage: case_timer.py <testcase.py> [extra args...]', file=sys.stderr)
        return 2

    root = project_root()
    workspace_root = root / 'workspace'
    record_dir = env_path(
        'FLOWFUSION_TIMING_RECORD_DIR',
        workspace_root / 'timing_record' / 'latest',
    )
    csv_path = env_path(
        'FLOWFUSION_TIMING_CSV',
        record_dir / 'case_timing.csv',
    )
    state_dir = record_dir / 'inflight'
    state_dir.mkdir(parents=True, exist_ok=True)

    real_python = env_command(
        'FLOWFUSION_REAL_PYTHON_BIN',
        workspace_root / 'python-cov' / 'python',
    )
    fused_dir = env_path('FLOWFUSION_FUSED_DIR', workspace_root / 'py_fused')
    py_deps_dir = env_path('FLOWFUSION_PY_DEPS_DIR', workspace_root / 'py_deps')
    py_seeds_dir = env_path('FLOWFUSION_PY_SEEDS_DIR', workspace_root / 'py_seeds')
    cpython_root = env_path('FLOWFUSION_CPYTHON_ROOT', root.parent / 'cpython' / 'cpython-src')
    timeout_seconds = env_int('FLOWFUSION_CASE_TIMEOUT', 10)
    timeout_margin_ms = env_int('FLOWFUSION_TIMER_MARGIN_MS', DEFAULT_TIMEOUT_MARGIN_MS)
    max_hydration_attempts = env_int(
        'FLOWFUSION_MAX_HYDRATION_ATTEMPTS',
        DEFAULT_MAX_HYDRATION_ATTEMPTS,
    )
    max_interpreter_calls = max_hydration_attempts + 1

    testcase_path = Path(sys.argv[1]).expanduser().resolve()
    extra_args = sys.argv[2:]
    case_key = case_key_for(testcase_path)
    state_path = state_path_for(state_dir, case_key)
    state = load_state(state_path)

    start_ns = int(state.get('start_ns', time.monotonic_ns()))
    start_iso = state.get('start_iso', now_iso())
    attempts = int(state.get('attempts', 0)) + 1

    inner_timeout = max(0.1, timeout_seconds - (timeout_margin_ms / 1000.0))
    proc = subprocess.Popen(
        [str(real_python), str(testcase_path), *extra_args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding='utf-8',
        errors='ignore',
    )

    timed_out = False
    try:
        stdout, stderr = proc.communicate(timeout=inner_timeout)
        returncode = proc.returncode if proc.returncode is not None else 1
    except subprocess.TimeoutExpired:
        timed_out = True
        proc.kill()
        stdout, stderr = proc.communicate()
        stdout = stdout or ''
        stderr = (stderr or '') + '\nTimeoutExpired\n'
        returncode = proc.returncode if proc.returncode is not None else -9

    flush_child_output(stdout or '', stderr or '')
    combined_output = (stdout or '') + (stderr or '')

    retryable_missing_resource = (
        not timed_out
        and is_retryable_missing_resource(
            combined_output,
            fused_dir=fused_dir,
            py_deps_dir=py_deps_dir,
            py_seeds_dir=py_seeds_dir,
            cpython_root=cpython_root,
        )
    )

    if retryable_missing_resource and attempts < max_interpreter_calls:
        save_state(
            state_path,
            {
                'case_key': case_key,
                'testcase_path': str(testcase_path),
                'start_ns': start_ns,
                'start_iso': start_iso,
                'attempts': attempts,
            },
        )
        return returncode

    end_ns = time.monotonic_ns()
    duration_ms = max(0, round((end_ns - start_ns) / 1_000_000))
    result = classify_result(returncode, combined_output, timed_out)
    bucket = bucket_for(duration_ms, timed_out, timeout_seconds)

    row = {
        'case_key': case_key,
        'testcase_path': str(testcase_path),
        'start_iso': start_iso,
        'end_iso': now_iso(),
        'duration_ms': duration_ms,
        'bucket': bucket,
        'result': result,
        'returncode': returncode,
        'attempts': attempts,
        'timed_out': int(timed_out),
    }

    try:
        append_csv_row(csv_path, row)
        remove_state(state_path)
    except OSError as exc:
        print(f'[case_timer] failed to write timing row: {exc}', file=sys.stderr)

    return returncode


if __name__ == '__main__':
    raise SystemExit(main())
