import os
import shutil
import time


def tmp_backlog(tmp_dir):
    backlog = 0
    for filename in os.listdir(tmp_dir):
        if filename.startswith('fused') and filename.endswith('.py'):
            backlog += 1
    return backlog


def pending_tests(tmp_dir, pending_batch_size=0):
    tests = []
    for filename in os.listdir(tmp_dir):
        if not filename.startswith('fused') or not filename.endswith('.py'):
            continue
        tests.append(os.path.join(tmp_dir, filename))
    tests = sorted(tests)
    tmp_backlog_count = len(tests)
    if pending_batch_size > 0:
        tests = tests[:pending_batch_size]
    return tests, tmp_backlog_count


def move_test(src_path, fused_dir, now_fn=None):
    if not os.path.exists(src_path):
        return None

    now_fn = now_fn or time.time
    dst_path = os.path.join(fused_dir, os.path.basename(src_path))
    if os.path.exists(dst_path):
        root, ext = os.path.splitext(dst_path)
        dst_path = f'{root}_{int(now_fn() * 1000)}{ext}'
    try:
        shutil.move(src_path, dst_path)
    except FileNotFoundError:
        return None
    return dst_path


def archive_case(testcase_path, output_path, folder):
    case_id = len(os.listdir(folder)) + 1
    case_dir = os.path.join(folder, str(case_id))
    os.makedirs(case_dir, exist_ok=True)
    try:
        if os.path.exists(testcase_path):
            shutil.copy2(testcase_path, os.path.join(case_dir, 'case.py'))
        if os.path.exists(output_path):
            shutil.copy2(output_path, os.path.join(case_dir, 'test.out'))
    except FileNotFoundError:
        return
