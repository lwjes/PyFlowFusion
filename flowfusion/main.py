import os
import subprocess
import threading
import time

from flowfusion.config import load_config
from .fuse import Fusion
from flowfusion.runtime.coverage import (
    build_gcovr_command,
    read_latest_line_rate_from_csv,
    read_line_rate,
    xml_path_for_seconds,
)
from flowfusion.runtime.executor import (
    classify_failure,
    run_testcase_once,
    validate_syntax,
)
from flowfusion.runtime.queue_store import (
    archive_case,
    move_test,
    pending_tests,
    tmp_backlog,
)
from flowfusion.runtime.resources import (
    extract_missing_file_path,
    hydrate_missing_resource,
    relative_path_under_fused_dir,
    resource_source_roots,
)


class BaseFuzz:
    def __init__(self, config):
        self.config = config
        self.test_root = config.paths.project_root
        self.tmp_dir = config.paths.tmp_queue_dir
        self.bug_folder = config.paths.bugs_dir
        self.fixme_folder = config.paths.fixme_dir
        self.total_count = 0
        self.syntax_error_count = 0
        self.stopping_test_num = config.runtime.stop_after
        self.mutation = config.runtime.mutation
        self.apifuzz = config.runtime.apifuzz
        self.ini = config.runtime.ini
        self.fusion = True
        self.coverage = 0.0
        self.cov_interval = config.coverage.interval
        self.case_timeout = config.runtime.case_timeout
        self.pending_batch_size = config.runtime.pending_batch_size
        self.pending_max_tmp = config.runtime.pending_max_tmp
        self.pending_timeout = config.runtime.pending_timeout
        self.coverage_csv_path = config.coverage.csv_path
        self.coverage_phase = config.coverage.phase
        self.coverage_root = config.coverage.gcovr_root
        self.coverage_build_root = config.cpython.cov_build_root
        self._last_cov_at = 0.0

        os.makedirs(self.bug_folder, exist_ok=True)
        os.makedirs(self.fixme_folder, exist_ok=True)

    def _stop_requested(self):
        return self.stopping_test_num > 0 and self.total_count >= self.stopping_test_num

    def _refresh_external_coverage(self):
        if getattr(self, 'cov_interval', 0) > 0:
            return

        csv_path = getattr(self, 'coverage_csv_path', '')
        if not csv_path:
            return

        try:
            self.coverage = read_latest_line_rate_from_csv(
                csv_path,
                preferred_phase=getattr(self, 'coverage_phase', ''),
            )
        except (OSError, ValueError):
            return

    def runtime_log(self, seconds, pending_size=None, tmp_backlog=None, batch_no=None):
        self._refresh_external_coverage()
        bugs_found = len(os.listdir(self.bug_folder))
        syntax_correct_rate = 1.0
        if self.total_count:
            syntax_correct_rate = float((self.total_count - self.syntax_error_count) / self.total_count)
        throughput = self.total_count / seconds if seconds else 0
        extra_parts = []
        if batch_no is not None:
            extra_parts.append(f'batch no: {batch_no}')
        if pending_size is not None:
            extra_parts.append(f'pending size: {pending_size}')
        if tmp_backlog is not None:
            extra_parts.append(f'tmp backlog: {tmp_backlog}')
        extra_log = f" | {' | '.join(extra_parts)}" if extra_parts else ''
        print(
            f'time: {int(seconds)} seconds | bugs found: {bugs_found} | '
            f'tests executed: {self.total_count} | syntax correct rate: {syntax_correct_rate:.2%} | '
            f'throughput: {throughput:.2f} tests per second{extra_log}'
        )
        if self.coverage:
            print(f'Coverage: {self.coverage:.2%}')
        if self._stop_requested():
            raise SystemExit(0)


class PythonFuzz(BaseFuzz):
    def __init__(self, config):
        super().__init__(config)
        self.cpython_root = config.cpython.source_root
        self.python_bin = config.cpython.fuzz_python_bin
        self.fused_dir = config.paths.py_fused_dir
        self.py_deps_dir = config.paths.py_deps_dir
        self.py_seeds_dir = config.paths.py_seeds_dir
        self.coverage_snapshot_dir = (
            os.path.dirname(self.coverage_csv_path)
            if self.coverage_csv_path
            else self.tmp_dir
        )
        self.batch_no = 0
        self._fusion_throttled = False
        os.makedirs(self.fused_dir, exist_ok=True)
        os.makedirs(self.coverage_snapshot_dir, exist_ok=True)

    def _build_runtime_env(self):
        env = os.environ.copy()
        python_path_parts = []

        support_lib = os.path.join(self.py_deps_dir, 'support_lib')
        if os.path.exists(support_lib):
            python_path_parts.append(support_lib)

        if os.path.exists(self.py_deps_dir):
            python_path_parts.append(self.py_deps_dir)

        existing = env.get('PYTHONPATH')
        if existing:
            python_path_parts.append(existing)

        env['PYTHONPATH'] = os.pathsep.join(python_path_parts)
        env.setdefault('ASAN_OPTIONS', 'detect_leaks=0:abort_on_error=1')
        env.setdefault('UBSAN_OPTIONS', 'print_stacktrace=1:halt_on_error=1')
        return env

    def _tmp_backlog(self):
        return tmp_backlog(self.tmp_dir)

    def _pending_tests(self):
        return pending_tests(self.tmp_dir, pending_batch_size=self.pending_batch_size)

    def _move_test(self, src_path):
        return move_test(src_path, self.fused_dir, now_fn=time.time)

    def _archive_case(self, testcase_path, output_path, folder):
        return archive_case(testcase_path, output_path, folder)

    def _classify_failure(self, returncode, output):
        result = classify_failure(returncode, output)
        if result == 'syntax':
            self.syntax_error_count += 1
        return result

    def _extract_missing_file_path(self, output):
        return extract_missing_file_path(output)

    def _relative_path_under_fused_dir(self, maybe_path):
        return relative_path_under_fused_dir(maybe_path, self.fused_dir)

    def _resource_source_roots(self):
        return resource_source_roots(self.py_deps_dir, self.py_seeds_dir, self.cpython_root)

    def _hydrate_missing_resource(self, missing_path):
        return hydrate_missing_resource(
            missing_path,
            self.fused_dir,
            self.py_deps_dir,
            self.py_seeds_dir,
            self.cpython_root,
            print_fn=print,
        )

    def _run_testcase_once(self, testcase_path):
        timeout_seconds = max(1, int(getattr(self, 'case_timeout', 120)))
        return run_testcase_once(
            self.python_bin,
            testcase_path,
            cwd=self.cpython_root,
            env=self._build_runtime_env(),
            timeout_seconds=timeout_seconds,
            subprocess_module=subprocess,
        )

    def _validate_syntax(self, testcase_path):
        return validate_syntax(testcase_path)

    def execute_testcase(self, testcase_path):
        output_path = testcase_path + '.out'
        if not os.path.exists(self.python_bin):
            raise SystemExit(f'CPython interpreter not found at {self.python_bin}. Run ./prepare.sh first.')

        try:
            self._validate_syntax(testcase_path)
            output, returncode = self._run_testcase_once(testcase_path)
            hydration_attempts = 0
            max_hydration_attempts = 8
            hydrated_paths = set()
            while returncode != 0 and hydration_attempts < max_hydration_attempts:
                missing_path = self._extract_missing_file_path(output)
                if not missing_path or missing_path in hydrated_paths:
                    break
                if not self._hydrate_missing_resource(missing_path):
                    break
                hydrated_paths.add(missing_path)
                hydration_attempts += 1
                output, returncode = self._run_testcase_once(testcase_path)
        except SyntaxError as exc:
            output = f'{type(exc).__name__}: {exc}\n'
            returncode = 1
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout.decode('utf-8', 'ignore') if isinstance(exc.stdout, bytes) else (exc.stdout or '')
            stderr = exc.stderr.decode('utf-8', 'ignore') if isinstance(exc.stderr, bytes) else (exc.stderr or '')
            output = stdout + stderr + '\nTimeoutExpired\n'
            returncode = -9

        with open(output_path, 'w', encoding='utf-8', errors='ignore') as handle:
            handle.write(output)

        result = self._classify_failure(returncode, output)
        self.total_count += 1

        if result == 'crash':
            self._archive_case(testcase_path, output_path, self.bug_folder)
        elif result in {'syntax', 'failure'}:
            self._archive_case(testcase_path, output_path, self.fixme_folder)

    def collect_cov(self, fuzz_seconds):
        def run_coverage_collection():
            xml_path = xml_path_for_seconds(self.coverage_snapshot_dir, fuzz_seconds)
            try:
                subprocess.run(
                    build_gcovr_command(
                        xml_path,
                        self.coverage_root,
                        self.coverage_build_root,
                    ),
                    cwd=self.coverage_build_root,
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except (FileNotFoundError, subprocess.CalledProcessError) as exc:
                print(f'[Coverage] collection failed for {xml_path}: {exc}')
                return

            try:
                self.coverage = read_line_rate(xml_path)
                print(f'Coverage: {self.coverage:.2%}')
            except (OSError, IndexError, ValueError) as exc:
                print(f'[Coverage] unable to read {xml_path}: {exc}')
                return

        threading.Thread(target=run_coverage_collection, daemon=True).start()

    def main(self):
        fusion_thread = None
        start = time.time()
        self._last_cov_at = start
        print('Start FlowFusion for Python...')

        while True:
            now = time.time()
            if self.cov_interval > 0 and now - self._last_cov_at >= self.cov_interval:
                self._last_cov_at = now
                self.collect_cov(now - start)

            pending, tmp_backlog = self._pending_tests()
            can_start_fusion = (
                self.pending_max_tmp <= 0
                or tmp_backlog < self.pending_max_tmp
            )

            if self.fusion and (fusion_thread is None or not fusion_thread.is_alive()):
                if can_start_fusion:
                    fusion = Fusion(self.config)
                    fusion_thread = threading.Thread(target=fusion.main, daemon=True)
                    fusion_thread.start()
                    if self._fusion_throttled:
                        print('[FlowFusion] fusion resumed')
                    self._fusion_throttled = False
                elif not self._fusion_throttled:
                    print(
                        '[FlowFusion] fusion throttled by backlog: '
                        f'{tmp_backlog} (limit {self.pending_max_tmp})'
                    )
                    self._fusion_throttled = True

            if not pending:
                time.sleep(0.5)
                continue

            self.batch_no += 1
            current_batch = self.batch_no
            current_pending_size = len(pending)
            batch_start = time.time()
            for pending_case in pending:
                if self.pending_timeout > 0 and time.time() - batch_start >= self.pending_timeout:
                    print(
                        '[FlowFusion] batch timeout reached: '
                        f'{self.pending_timeout}s (batch no: {current_batch})'
                    )
                    break
                testcase_path = self._move_test(pending_case)
                if not testcase_path:
                    continue
                self.execute_testcase(testcase_path)
                if self._stop_requested():
                    self.runtime_log(
                        time.time() - start,
                        pending_size=current_pending_size,
                        tmp_backlog=self._tmp_backlog(),
                        batch_no=current_batch,
                    )

            self.runtime_log(
                time.time() - start,
                pending_size=current_pending_size,
                tmp_backlog=self._tmp_backlog(),
                batch_no=current_batch,
            )


def main():
    PythonFuzz(load_config()).main()


if __name__ == '__main__':
    main()
