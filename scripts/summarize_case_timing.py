#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path


BUCKET_ORDER = ('<1s', '1-3s', '3-5s', '5-7s', '7-9s', '9-10s', 'timeout')


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def latest_run_dir(run_root: Path) -> Path:
    candidates = sorted(
        (
            path for path in run_root.iterdir()
            if path.is_dir() and (path / 'case_timing.csv').is_file()
        ),
        key=lambda path: path.name,
    )
    if not candidates:
        raise FileNotFoundError(f'no timing run found under {run_root}')
    return candidates[-1]


def percentile_ms(values: list[int], ratio: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, math.ceil(ratio * len(ordered)) - 1)
    return ordered[index]


def load_rows(csv_path: Path) -> list[dict]:
    with csv_path.open('r', encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def ratio(count: int, total: int) -> float:
    if total == 0:
        return 0.0
    return count / total


def build_summary(rows: list[dict], run_dir: Path) -> dict:
    durations = []
    bucket_counts = {name: 0 for name in BUCKET_ORDER}
    result_counts = {}
    retried_cases = 0

    for row in rows:
        duration_ms = int(row['duration_ms'])
        durations.append(duration_ms)
        bucket = row['bucket']
        if bucket not in bucket_counts:
            bucket_counts[bucket] = 0
        bucket_counts[bucket] += 1

        result = row['result']
        result_counts[result] = result_counts.get(result, 0) + 1

        if int(row.get('attempts', '1')) > 1:
            retried_cases += 1

    total_cases = len(rows)
    summary = {
        'run_dir': str(run_dir),
        'csv_path': str(run_dir / 'case_timing.csv'),
        'total_cases': total_cases,
        'retried_cases': retried_cases,
        'bucket_counts': bucket_counts,
        'bucket_ratios': {
            bucket: ratio(count, total_cases)
            for bucket, count in bucket_counts.items()
        },
        'result_counts': result_counts,
        'result_ratios': {
            result: ratio(count, total_cases)
            for result, count in result_counts.items()
        },
        'duration_ms': {
            'min': min(durations) if durations else 0,
            'avg': round(sum(durations) / total_cases, 2) if total_cases else 0.0,
            'p50': percentile_ms(durations, 0.50),
            'p90': percentile_ms(durations, 0.90),
            'p99': percentile_ms(durations, 0.99),
            'max': max(durations) if durations else 0,
        },
    }
    return summary


def write_json(summary: dict, output_path: Path) -> None:
    output_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )


def write_markdown(summary: dict, output_path: Path) -> None:
    lines = [
        '# Case Timing Summary',
        '',
        f"- run_dir: `{summary['run_dir']}`",
        f"- total_cases: `{summary['total_cases']}`",
        f"- retried_cases: `{summary['retried_cases']}`",
        '',
        '## Bucket Distribution',
        '',
        '| Bucket | Count | Ratio |',
        '| --- | ---: | ---: |',
    ]

    for bucket in BUCKET_ORDER:
        count = summary['bucket_counts'].get(bucket, 0)
        pct = summary['bucket_ratios'].get(bucket, 0.0) * 100
        lines.append(f'| {bucket} | {count} | {pct:.2f}% |')

    lines.extend(
        [
            '',
            '## Result Distribution',
            '',
            '| Result | Count | Ratio |',
            '| --- | ---: | ---: |',
        ]
    )

    for result, count in sorted(summary['result_counts'].items()):
        pct = summary['result_ratios'].get(result, 0.0) * 100
        lines.append(f'| {result} | {count} | {pct:.2f}% |')

    duration = summary['duration_ms']
    lines.extend(
        [
            '',
            '## Duration Percentiles',
            '',
            '| Metric | Value (ms) |',
            '| --- | ---: |',
            f"| min | {duration['min']} |",
            f"| avg | {duration['avg']} |",
            f"| p50 | {duration['p50']} |",
            f"| p90 | {duration['p90']} |",
            f"| p99 | {duration['p99']} |",
            f"| max | {duration['max']} |",
            '',
        ]
    )

    output_path.write_text('\n'.join(lines), encoding='utf-8')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Summarize PyFlowFusion3 case timing results.')
    parser.add_argument(
        '--run-dir',
        type=Path,
        help='Timing run directory. Defaults to the latest directory under workspace/timing_record.',
    )
    parser.add_argument(
        '--json-out',
        type=Path,
        help='Path to write summary JSON. Defaults to <run-dir>/summary.json.',
    )
    parser.add_argument(
        '--md-out',
        type=Path,
        help='Path to write summary Markdown. Defaults to <run-dir>/summary.md.',
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_root = project_root() / 'workspace' / 'timing_record'
    run_dir = args.run_dir.resolve() if args.run_dir else latest_run_dir(run_root)
    csv_path = run_dir / 'case_timing.csv'

    if not csv_path.is_file():
        raise SystemExit(f'case timing csv not found: {csv_path}')

    rows = load_rows(csv_path)
    if not rows:
        raise SystemExit(f'case timing csv is empty: {csv_path}')

    summary = build_summary(rows, run_dir)
    json_out = args.json_out.resolve() if args.json_out else run_dir / 'summary.json'
    md_out = args.md_out.resolve() if args.md_out else run_dir / 'summary.md'

    write_json(summary, json_out)
    write_markdown(summary, md_out)
    print(f'[summarize_case_timing] wrote {json_out}')
    print(f'[summarize_case_timing] wrote {md_out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
