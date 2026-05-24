#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from pathlib import Path


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


def cap_label(cap_seconds: float) -> str:
    text = f'{cap_seconds:g}'
    return text.replace('.', '_')


def load_durations_ms(csv_path: Path) -> list[int]:
    durations = []
    with csv_path.open('r', encoding='utf-8', newline='') as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            durations.append(int(row['duration_ms']))
    return durations


def write_markdown(
    output_path: Path,
    *,
    run_dir: Path,
    csv_path: Path,
    cap_seconds: float,
    cap_ms: int,
    durations: list[int],
) -> None:
    capped_durations = [min(duration, cap_ms) for duration in durations]
    capped_count = sum(1 for duration in durations if duration > cap_ms)
    average_ms = sum(capped_durations) / len(capped_durations)

    lines = [
        '# Capped Average Duration',
        '',
        f'- run_dir: `{run_dir}`',
        f'- csv_path: `{csv_path}`',
        f'- cap_seconds: `{cap_seconds:g}`',
        f'- cap_ms: `{cap_ms}`',
        f'- total_cases: `{len(durations)}`',
        f'- capped_cases: `{capped_count}`',
        f'- capped_average_ms: `{average_ms:.2f}`',
        f'- capped_average_seconds: `{average_ms / 1000:.4f}`',
        '',
    ]
    output_path.write_text('\n'.join(lines), encoding='utf-8')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Compute capped average duration from a timing case_timing.csv.'
    )
    parser.add_argument(
        '--run-dir',
        type=Path,
        help='Timing run directory. Defaults to the latest directory under workspace/timing_record.',
    )
    parser.add_argument(
        '--cap-seconds',
        type=float,
        required=True,
        help='Upper bound in seconds. Durations above this value are counted as this value.',
    )
    parser.add_argument(
        '--output',
        type=Path,
        help='Output Markdown path. Defaults to <run-dir>/capped_average_<cap>s.md.',
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.cap_seconds <= 0:
        raise SystemExit('--cap-seconds must be greater than 0')

    run_root = project_root() / 'workspace' / 'timing_record'
    run_dir = args.run_dir.resolve() if args.run_dir else latest_run_dir(run_root)
    csv_path = run_dir / 'case_timing.csv'
    if not csv_path.is_file():
        raise SystemExit(f'case timing csv not found: {csv_path}')

    durations = load_durations_ms(csv_path)
    if not durations:
        raise SystemExit(f'case timing csv is empty: {csv_path}')

    cap_ms = int(args.cap_seconds * 1000)
    output_path = (
        args.output.resolve()
        if args.output
        else run_dir / f'capped_average_{cap_label(args.cap_seconds)}s.md'
    )
    write_markdown(
        output_path,
        run_dir=run_dir,
        csv_path=csv_path,
        cap_seconds=args.cap_seconds,
        cap_ms=cap_ms,
        durations=durations,
    )
    print(f'[capped_average_duration] wrote {output_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
