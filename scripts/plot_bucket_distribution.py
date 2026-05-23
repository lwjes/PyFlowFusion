#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt


DEFAULT_BUCKET_ORDER = (
    '<1s',
    '1-3s',
    '3-5s',
    '5-7s',
    '7-9s',
    '9-10s',
    'timeout',
)


def parse_args():
    parser = argparse.ArgumentParser(
        description='Plot the timing bucket distribution from summary.json.'
    )
    parser.add_argument(
        'summary_json',
        type=Path,
        help='Path to a timing_record summary.json file.',
    )
    parser.add_argument(
        '--output',
        type=Path,
        help='Output image path. Defaults to bucket_distribution.png next to summary.json.',
    )
    parser.add_argument(
        '--title',
        default='Bucket Distribution',
        help='Chart title.',
    )
    return parser.parse_args()


def load_summary(path):
    with path.open('r', encoding='utf-8') as handle:
        summary = json.load(handle)
    bucket_counts = summary.get('bucket_counts')
    if not isinstance(bucket_counts, dict):
        raise SystemExit(f'missing bucket_counts in {path}')
    bucket_ratios = summary.get('bucket_ratios') or {}
    if not isinstance(bucket_ratios, dict):
        bucket_ratios = {}
    return summary, bucket_counts, bucket_ratios


def ordered_buckets(bucket_counts):
    known = [bucket for bucket in DEFAULT_BUCKET_ORDER if bucket in bucket_counts]
    extra = sorted(bucket for bucket in bucket_counts if bucket not in DEFAULT_BUCKET_ORDER)
    return known + extra


def plot_bucket_distribution(summary, bucket_counts, bucket_ratios, output_path, title):
    buckets = ordered_buckets(bucket_counts)
    counts = [int(bucket_counts.get(bucket, 0)) for bucket in buckets]
    ratios = [float(bucket_ratios.get(bucket, 0.0)) for bucket in buckets]

    fig_width = max(8, len(buckets) * 1.1)
    fig, ax = plt.subplots(figsize=(fig_width, 5.2))
    bars = ax.bar(buckets, counts, color='#2f6f9f', edgecolor='#1f2933', linewidth=0.8)

    total_cases = summary.get('total_cases')
    subtitle = f'total cases: {total_cases}' if total_cases is not None else ''
    ax.set_title(f'{title}\n{subtitle}' if subtitle else title, pad=12)
    ax.set_xlabel('Bucket')
    ax.set_ylabel('Case Count')
    ax.grid(axis='y', linestyle='--', linewidth=0.7, alpha=0.35)
    ax.set_axisbelow(True)

    max_count = max(counts) if counts else 0
    y_offset = max(1, max_count * 0.025)
    for bar, count, ratio in zip(bars, counts, ratios):
        label = f'{count}\n{ratio:.1%}'
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + y_offset,
            label,
            ha='center',
            va='bottom',
            fontsize=9,
        )

    ax.set_ylim(0, max_count + max(5, max_count * 0.18))
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


def main():
    args = parse_args()
    summary_path = args.summary_json.resolve()
    output_path = (
        args.output.resolve()
        if args.output
        else summary_path.with_name('bucket_distribution.png')
    )
    summary, bucket_counts, bucket_ratios = load_summary(summary_path)
    plot_bucket_distribution(
        summary,
        bucket_counts,
        bucket_ratios,
        output_path,
        args.title,
    )
    print(f'wrote {output_path}')


if __name__ == '__main__':
    main()
