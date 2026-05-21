import os
import re
import shutil


def extract_missing_file_path(output):
    output_text = output or ''
    patterns = [
        r"FileNotFoundError:\s*\[Errno 2\].*?:\s*'([^']+)'",
        r"\[Errno 2\]\s+No such file or directory:\s*'([^']+)'",
        r"[Cc]an't read certificate file\s+'([^']+)'",
    ]
    for pattern in patterns:
        matches = list(re.finditer(pattern, output_text))
        if matches:
            return matches[-1].group(1)
    return ''


def relative_path_under_fused_dir(maybe_path, fused_dir):
    if not maybe_path:
        return ''
    try:
        rel_path = os.path.relpath(os.path.normpath(maybe_path), os.path.normpath(fused_dir))
    except ValueError:
        return ''
    if rel_path in {'.', ''} or rel_path.startswith('..') or os.path.isabs(rel_path):
        return ''
    return rel_path


def resource_source_roots(py_deps_dir, py_seeds_dir, cpython_root):
    return [
        os.path.join(py_deps_dir, 'test'),
        os.path.join(py_deps_dir, 'support_lib', 'test'),
        py_deps_dir,
        py_seeds_dir,
        os.path.join(cpython_root, 'Lib', 'test'),
    ]


def hydrate_missing_resource(
    missing_path,
    fused_dir,
    py_deps_dir,
    py_seeds_dir,
    cpython_root,
    print_fn=print,
):
    rel_path = relative_path_under_fused_dir(missing_path, fused_dir)
    if not rel_path:
        return False

    target_path = os.path.normpath(missing_path)
    if os.path.exists(target_path):
        return False

    for root in resource_source_roots(py_deps_dir, py_seeds_dir, cpython_root):
        source_path = os.path.normpath(os.path.join(root, rel_path))
        if not os.path.isfile(source_path):
            continue
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        shutil.copy2(source_path, target_path)
        print_fn(f'[FlowFusion] hydrated missing resource: {rel_path}')
        return True

    return False
