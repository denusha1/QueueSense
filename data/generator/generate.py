"""Reproducible, fictional FIFO clinic operations. Standard library only."""
import argparse
import csv
import hashlib
import json
import random
import statistics
import uuid
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

NAMESPACE = uuid.UUID('4b1797bb-82e6-4a66-a1b0-dae6e3d199af')
TZ = timezone(timedelta(hours=5, minutes=30))
DEPARTMENTS = [('GEN', 'General medicine', 11, 78), ('DEN', 'Dental care', 19, 48), ('EYE', 'Eye clinic', 9, 68)]
TABLES = ['departments', 'staff', 'staff_schedules', 'queue_sessions', 'queue_tokens', 'service_events', 'staff_availability']


def uid(key):
    return str(uuid.uuid5(NAMESPACE, key))


def iso(value):
    return value.isoformat() if value is not None else None


def generate(days=90, seed=42, start=date(2026, 6, 1)):
    if days < 1 or days > 366:
        raise ValueError('days must be between 1 and 366')
    rng = random.Random(seed)
    tables = {name: [] for name in TABLES}
    for code, name, mean_service, base_arrivals in DEPARTMENTS:
        department_id = uid(code)
        tables['departments'].append(dict(id=department_id, code=code, name=name, location='Demo clinic · Floor 1', timezone='Asia/Colombo', queue_threshold=15, is_active=True))
        staff_ids = [uid(code + '-staff-' + str(i)) for i in range(3)]
        for i, staff_id in enumerate(staff_ids):
            tables['staff'].append(dict(id=staff_id, user_id=None, department_id=department_id, display_name=code + ' · Demo clinician ' + str(i + 1), staff_type='doctor', is_active=True))
        for offset in range(days):
            day = start + timedelta(days=offset)
            # Closed Sundays; Saturday has lower demand and only two staff.
            if day.weekday() == 6:
                continue
            opening = datetime.combine(day, time(8), TZ)
            lunch = opening + timedelta(hours=4)
            restart = lunch + timedelta(hours=1)
            shift_end = opening + timedelta(hours=10)
            active = 2 if day.weekday() == 5 or rng.random() < .3 else 3
            free_at = [opening] * active
            last_called = opening
            session_id = uid(code + '-' + day.isoformat())
            session = dict(id=session_id, department_id=department_id, service_date=day.isoformat(), opened_at=iso(opening), closed_at=None)
            tables['queue_sessions'].append(session)
            day_factor = [1.2, 1.05, 1, 1, 1.1, .7][day.weekday()]
            total = max(12, round(base_arrivals * day_factor * rng.uniform(.85, 1.15)))
            arrivals = []
            for _ in range(total):
                hour = rng.choices(range(8), weights=[13, 20, 19, 11, 4, 13, 12, 8])[0]
                arrivals.append(opening + timedelta(hours=hour, seconds=rng.randrange(3600)))
            arrivals.sort()
            last_end = shift_end
            for number, arrival in enumerate(arrivals, 1):
                token_id = uid(session_id + '-token-' + str(number))
                token = dict(id=token_id, session_id=session_id, department_id=department_id, staff_id=None, token_no=number, synthetic_patient_id='SYN-' + code + '-' + day.strftime('%Y%m%d') + '-' + str(number).zfill(3), priority_class='standard', status='waiting', check_in_at=iso(arrival), called_at=None, service_start_at=None, completed_at=None, ended_at=None)
                outcome = rng.random()
                event_times = [('check_in', arrival)]
                if outcome < .04:
                    ended = arrival + timedelta(minutes=rng.randint(2, 18))
                    token.update(status='cancelled', ended_at=iso(ended))
                    event_times.append(('cancelled', ended))
                else:
                    worker = min(range(active), key=lambda i: free_at[i])
                    called = max(arrival, free_at[worker], last_called)
                    no_show = outcome < .08
                    duration = 3 if no_show else min(55, max(3, rng.lognormvariate(0, .3) * mean_service))
                    if not no_show and rng.random() < .025:
                        duration += 12  # occasional operational delay
                    # Calls and consultations fit wholly outside the planned lunch break.
                    if called < restart and called + timedelta(minutes=duration + 1) > lunch:
                        called = restart
                    last_called = called
                    ended = called + timedelta(minutes=duration + (0 if no_show else 1))
                    token.update(staff_id=staff_ids[worker], called_at=iso(called), ended_at=iso(ended))
                    event_times.append(('called', called))
                    if no_show:
                        token['status'] = 'no_show'
                        event_times.append(('no_show', ended))
                    else:
                        began = called + timedelta(minutes=1)
                        token.update(status='completed', service_start_at=iso(began), completed_at=iso(ended))
                        event_times.extend([('service_start', began), ('completed', ended)])
                    free_at[worker] = ended
                last_end = max(last_end, ended)
                tables['queue_tokens'].append(token)
                for event_type, timestamp in event_times:
                    tables['service_events'].append(dict(id=uid(token_id + '-' + event_type), token_id=token_id, department_id=department_id, staff_id=None if event_type == 'check_in' else token['staff_id'], event_type=event_type, event_time=iso(timestamp)))
            session['closed_at'] = iso(last_end)
            for i in range(active):
                staff_id = staff_ids[i]
                actual_end = max(shift_end, free_at[i])
                for index, (begin, end) in enumerate([(opening, lunch), (restart, actual_end)]):
                    tables['staff_schedules'].append(dict(id=uid(session_id + staff_id + '-schedule-' + str(index)), staff_id=staff_id, service_date=day.isoformat(), start_at=iso(begin), end_at=iso(end), status='scheduled'))
                for state, timestamp in [('available', opening), ('break', lunch), ('available', restart), ('offline', actual_end)]:
                    tables['staff_availability'].append(dict(id=uid(staff_id + iso(timestamp)), staff_id=staff_id, status=state, changed_at=iso(timestamp)))
    return tables


def summary(tables, days, seed, start):
    tokens = tables['queue_tokens']
    departments = []
    for department in tables['departments']:
        subset = [t for t in tokens if t['department_id'] == department['id']]
        waits = [(datetime.fromisoformat(t['service_start_at']) - datetime.fromisoformat(t['check_in_at'])).total_seconds() / 60 for t in subset if t['service_start_at']]
        departments.append(dict(id=department['id'], code=department['code'], name=department['name'], arrivals=len(subset), completed=sum(t['status'] == 'completed' for t in subset), cancelled=sum(t['status'] == 'cancelled' for t in subset), noShows=sum(t['status'] == 'no_show' for t in subset), averageWait=round(statistics.mean(waits), 1)))
    latest = max(s['service_date'] for s in tables['queue_sessions'])
    latest_sessions = {s['id'] for s in tables['queue_sessions'] if s['service_date'] == latest}
    samples = []
    for department in departments:
        subset = [t for t in tokens if t['session_id'] in latest_sessions and t['department_id'] == department['id']][:20]
        for t in subset:
            samples.append(dict(token=department['code'] + '-' + str(t['token_no']).zfill(3), patient=t['synthetic_patient_id'], department=department['code'], status=t['status'], arrival=t['check_in_at'], start=t['service_start_at'], completed=t['completed_at']))
    digest = hashlib.sha256(json.dumps(tables, sort_keys=True).encode()).hexdigest()
    return dict(synthetic=True, generatorVersion='1.0.0', seed=seed, start=start.isoformat(), end=(start + timedelta(days=days - 1)).isoformat(), latestServiceDate=latest, calendarDays=days, counts={k: len(v) for k, v in tables.items()}, fingerprint=digest, departments=departments, samples=samples)


def sql_literal(value):
    if value is None:
        return 'NULL'
    if isinstance(value, bool):
        return 'TRUE' if value else 'FALSE'
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def write_dataset(tables, output):
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'seed.sql').open('w') as sql:
        sql.write('-- Fictional synthetic records. Apply transactionally to an empty demo database.\n')
        for table, rows in tables.items():
            if not rows:
                continue
            columns = list(rows[0])
            with (output / (table + '.csv')).open('w', newline='') as file:
                writer = csv.DictWriter(file, fieldnames=columns)
                writer.writeheader()
                writer.writerows(rows)
            for offset in range(0, len(rows), 250):
                sql.write('INSERT INTO ' + table + ' (' + ','.join(columns) + ') VALUES\n')
                sql.write(',\n'.join('(' + ','.join(sql_literal(row[c]) for c in columns) + ')' for row in rows[offset:offset + 250]) + ';\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--days', type=int, default=90)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--start', type=date.fromisoformat, default=date(2026, 6, 1))
    parser.add_argument('--output', type=Path, default=Path('data/generated'))
    parser.add_argument('--preview', type=Path, default=Path('data/sample/summary.json'))
    args = parser.parse_args()
    if args.start.weekday() == 6 and args.days == 1:
        parser.error('Selected interval is a closed Sunday; include a clinic day.')
    tables = generate(args.days, args.seed, args.start)
    write_dataset(tables, args.output)
    report = summary(tables, args.days, args.seed, args.start)
    args.preview.parent.mkdir(parents=True, exist_ok=True)
    args.preview.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ['counts', 'fingerprint']}, indent=2))


if __name__ == '__main__':
    main()
