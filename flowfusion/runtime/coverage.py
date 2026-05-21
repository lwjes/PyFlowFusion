import csv
import os
import shutil
import sys


def build_gcovr_command(xml_path, source_root, object_directory):
    gcovr_bin = shutil.which('gcovr')
    if gcovr_bin:
        runner = [gcovr_bin]
    else:
        runner = [sys.executable, '-m', 'gcovr']
    return runner + [
        '-sr',
        source_root,
        '--object-directory',
        object_directory,
        '-o',
        xml_path,
        '--xml',
        '--gcov-ignore-parse-errors',
    ]


def xml_path_for_seconds(output_dir, fuzz_seconds):
    return os.path.join(output_dir, f'gcovr-{int(fuzz_seconds)}.xml')


def read_line_rate(xml_path):
    with open(xml_path, 'r', encoding='utf-8', errors='ignore') as handle:
        content = handle.read()
    return float(content.split('line-rate="')[1].split('"')[0])


def read_latest_line_rate_from_csv(csv_path, preferred_phase=''):
    latest_rate = None
    preferred_rate = None

    with open(csv_path, 'r', encoding='utf-8', errors='ignore', newline='') as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            try:
                line_pct = float(row.get('line_pct', ''))
            except (TypeError, ValueError):
                continue
            rate = line_pct / 100.0
            latest_rate = rate
            if preferred_phase and row.get('phase') == preferred_phase:
                preferred_rate = rate

    if preferred_rate is not None:
        return preferred_rate
    if latest_rate is not None:
        return latest_rate
    raise ValueError(f'No readable coverage rows found in {csv_path}')
