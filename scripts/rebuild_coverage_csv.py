#!/usr/bin/env python3
import argparse
import csv
import glob
import os
import sys
import xml.etree.ElementTree as ET


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_COV_RECORD_DIR = os.path.join(PROJECT_ROOT, 'workspace', 'cov_record')
DEFAULT_OUTPUT_PATH = os.path.join(DEFAULT_COV_RECORD_DIR, 'coverage_24h.csv')


def parse_args():
    parser = argparse.ArgumentParser(
        description='Rebuild coverage_24h.csv from gcovr-*.xml snapshots.',
    )
    parser.add_argument(
        '--cov-record-dir',
        default=DEFAULT_COV_RECORD_DIR,
        help='Directory containing gcovr-*.xml snapshots.',
    )
    parser.add_argument(
        '--output',
        default=DEFAULT_OUTPUT_PATH,
        help='CSV file to overwrite.',
    )
    return parser.parse_args()


def extract_elapsed_seconds(xml_path):
    filename = os.path.basename(xml_path)
    stem, ext = os.path.splitext(filename)
    if ext != '.xml' or not stem.startswith('gcovr-'):
        raise ValueError(f'Unexpected snapshot filename: {filename}')
    return int(stem.split('-', 1)[1])


def read_root_line_rate(xml_path):
    parser = ET.iterparse(xml_path, events=('start',))
    try:
        _, root = next(parser)
    except StopIteration as exc:
        raise ValueError(f'Empty XML file: {xml_path}') from exc
    line_rate = root.attrib.get('line-rate')
    if line_rate is None:
        raise ValueError(f'Missing root line-rate in {xml_path}')
    return float(line_rate)


def iter_snapshot_rows(cov_record_dir):
    pattern = os.path.join(cov_record_dir, 'gcovr-*.xml')
    for xml_path in sorted(glob.glob(pattern), key=extract_elapsed_seconds):
        elapsed_seconds = extract_elapsed_seconds(xml_path)
        line_rate = read_root_line_rate(xml_path)
        yield {
            'elapsed_seconds': elapsed_seconds,
            'elapsed_minutes': elapsed_seconds // 60,
            'line_rate': line_rate,
            'line_pct': line_rate * 100.0,
            'xml_path': xml_path,
        }


def main():
    args = parse_args()
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)

    rows = list(iter_snapshot_rows(args.cov_record_dir))
    with open(args.output, 'w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow([
            'elapsed_seconds',
            'elapsed_minutes',
            'line_rate',
            'line_pct',
            'xml_path',
        ])
        for row in rows:
            writer.writerow([
                row['elapsed_seconds'],
                row['elapsed_minutes'],
                f"{row['line_rate']:.16f}",
                f"{row['line_pct']:.4f}",
                row['xml_path'],
            ])

    print(f'Rebuilt {args.output} from {len(rows)} snapshot(s).')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'Error: {exc}', file=sys.stderr)
        raise SystemExit(1)
