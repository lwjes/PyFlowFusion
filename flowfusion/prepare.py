import os
import shutil
import subprocess
import sys

from flowfusion.config import load_config


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def copy_tree(src, dst):
    if not os.path.isdir(src):
        raise SystemExit(f'missing directory: {src}')
    if os.path.islink(dst) or os.path.isfile(dst):
        os.unlink(dst)
    elif os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def validate_cpython_runtime(config):
    lib_root = os.path.join(config.cpython.source_root, 'Lib')
    test_root = os.path.join(lib_root, 'test')

    if not os.path.isdir(test_root):
        raise SystemExit(f'CPython tests not found under {test_root}')
    if not os.path.exists(config.cpython.fuzz_python_bin):
        raise SystemExit(f'CPython interpreter not found at {config.cpython.fuzz_python_bin}')

    print(f'using CPython source: {config.cpython.source_root}')
    print(f'using CPython interpreter: {config.cpython.fuzz_python_bin}')


def collect_cpython_seeds(config):
    source_test_root = os.path.join(config.cpython.source_root, 'Lib', 'test')
    copied = 0

    ensure_dir(config.paths.py_seeds_dir)
    for current_root, _, files in os.walk(source_test_root):
        rel_root = os.path.relpath(current_root, source_test_root)
        target_root = (
            os.path.join(config.paths.py_seeds_dir, rel_root)
            if rel_root != '.'
            else config.paths.py_seeds_dir
        )
        ensure_dir(target_root)
        for filename in files:
            if not filename.startswith('test_') or not filename.endswith('.py'):
                continue
            shutil.copy2(
                os.path.join(current_root, filename),
                os.path.join(target_root, filename),
            )
            copied += 1

    print(f'copied {copied} CPython seed files into {config.paths.py_seeds_dir}')


def prepare_python_dependencies(config):
    copy_tree(
        os.path.join(config.cpython.source_root, 'Lib', 'test'),
        os.path.join(config.paths.py_deps_dir, 'test'),
    )
    copy_tree(
        os.path.join(config.cpython.source_root, 'Lib'),
        os.path.join(config.paths.py_deps_dir, 'support_lib'),
    )
    print(f'prepared Python dependency trees under {config.paths.py_deps_dir}')


def run_knowledge_builder(config):
    script_path = os.path.join(config.paths.knowledge_dir, 'build.py')
    env = os.environ.copy()
    env['FLOWFUSION_CONFIG'] = config.config_path
    result = subprocess.run(
        [sys.executable, script_path],
        cwd=config.paths.knowledge_dir,
        env=env,
    )
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main():
    config = load_config()
    print('Preparing FlowFusion for CPython fuzzing...')

    for path in (
        config.paths.py_seeds_dir,
        config.paths.py_deps_dir,
        config.paths.py_fused_dir,
        config.paths.tmp_queue_dir,
        config.paths.bugs_dir,
        config.paths.fixme_dir,
        os.path.dirname(config.coverage.csv_path) if config.coverage.csv_path else '',
        os.path.join(config.paths.project_root, 'workspace', 'san_record'),
    ):
        if path:
            ensure_dir(path)

    validate_cpython_runtime(config)
    collect_cpython_seeds(config)
    prepare_python_dependencies(config)
    run_knowledge_builder(config)

    print('CPython preparation finished.')


if __name__ == '__main__':
    main()
