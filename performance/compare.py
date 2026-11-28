"""Summarize a baseline and final Locust run without copying request fixtures."""

import argparse
import csv
import json
from pathlib import Path
from statistics import mean


def read(phase_path: Path):
    with (phase_path / 'requests_stats.csv').open() as report:
        rows = list(csv.DictReader(report))
    samples = json.loads((phase_path / 'resources.json').read_text())
    # Locust resets its request stats around 5 seconds after users start.
    samples = [row for row in samples if row['elapsed_s'] >= 6]
    return rows, samples


def result(row):
    failures = int(row['Failure Count'])
    total = int(row['Request Count'])
    return (
        f"{total} | {float(row['Requests/s']):.2f} | "
        f"{float(row['Average Response Time']):.1f} | "
        f"{row['50%']} | {row['95%']} | {row['99%']} | {100 * failures / total:.1f}%"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline', type=Path)
    parser.add_argument('final', type=Path)
    args = parser.parse_args()
    print('| Users | Run | Requests | Req/s | Mean ms | P50 ms | P95 ms | P99 ms | Error rate | '
          'Mean API CPU % | Peak API MiB | Peak DB sessions | Peak active DB | Lock waits sampled |')
    print('|' + ' --- |' * 14)
    for users in (10, 50, 100):
        for label, source in (('Baseline', args.baseline), ('Final', args.final)):
            rows, samples = read(source / str(users))
            aggregate = next(row for row in rows if row['Name'] == 'Aggregated')
            print(f"| {users} | {label} | {result(aggregate)} | "
                  f"{mean(row['api_cpu_percent'] for row in samples):.1f} | "
                  f"{max(row['api_rss_mib'] for row in samples):.1f} | "
                  f"{max(row['sessions'] for row in samples)} | "
                  f"{max(row['active'] for row in samples)} | "
                  f"{sum(row['waiting_locks'] for row in samples)} |")
    print('\n| Run | Operation at 100 users | Requests | Req/s | Mean ms | P50 ms | P95 ms | P99 ms | Error rate |')
    print('|' + ' --- |' * 9)
    for label, source in (('Baseline', args.baseline), ('Final', args.final)):
        rows, _ = read(source / '100')
        for row in rows:
            if row['Name'] != 'Aggregated':
                print(f"| {label} | `{row['Type']} {row['Name']}` | {result(row)} |")


if __name__ == '__main__':
    main()
