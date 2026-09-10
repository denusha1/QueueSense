import unittest
from datetime import date, datetime
from generate import generate, summary


class GeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = generate(days=14)

    def test_reproducible_and_seed_sensitive(self):
        self.assertEqual(self.data, generate(days=14))
        self.assertNotEqual(self.data['queue_tokens'], generate(days=14, seed=43)['queue_tokens'])

    def test_status_timestamps_and_event_integrity(self):
        events = {}
        for event in self.data['service_events']:
            events.setdefault(event['token_id'], {})[event['event_type']] = event['event_time']
        for token in self.data['queue_tokens']:
            timeline = [token[key] for key in ['check_in_at','called_at','service_start_at','completed_at','ended_at'] if token[key]]
            self.assertEqual(timeline, sorted(timeline))
            self.assertEqual(events[token['id']]['check_in'], token['check_in_at'])
            self.assertEqual(events[token['id']][token['status']], token['ended_at'])
            self.assertTrue(token['synthetic_patient_id'].startswith('SYN-'))
            if token['status'] == 'completed':
                self.assertIsNotNone(token['service_start_at'])
            else:
                self.assertIsNone(token['service_start_at'])

    def test_staff_never_double_booked_and_work_fits_schedule(self):
        by_staff = {}
        schedules = {}
        for row in self.data['staff_schedules']:
            schedules.setdefault(row['staff_id'], []).append((row['start_at'], row['end_at']))
        for token in self.data['queue_tokens']:
            if token['staff_id']:
                by_staff.setdefault(token['staff_id'], []).append((token['called_at'], token['ended_at']))
        for staff, intervals in by_staff.items():
            intervals.sort()
            for previous, current in zip(intervals, intervals[1:]):
                self.assertLessEqual(previous[1], current[0])
            for begin, end in intervals:
                self.assertTrue(any(a <= begin <= end <= b for a, b in schedules[staff]))

    def test_references_and_unique_tokens(self):
        departments = {d['id'] for d in self.data['departments']}
        sessions = {s['id']: s for s in self.data['queue_sessions']}
        staff = {s['id']: s for s in self.data['staff']}
        unique = set()
        for token in self.data['queue_tokens']:
            session = sessions[token['session_id']]
            self.assertIn(token['department_id'], departments)
            self.assertEqual(session['department_id'], token['department_id'])
            self.assertEqual(datetime.fromisoformat(token['check_in_at']).date().isoformat(), session['service_date'])
            if token['staff_id']:
                self.assertEqual(staff[token['staff_id']]['department_id'], token['department_id'])
            key = (token['session_id'], token['token_no'])
            self.assertNotIn(key, unique)
            unique.add(key)

    def test_fifo_even_across_lunch(self):
        calls = {}
        for token in self.data['queue_tokens']:
            if token['called_at']:
                calls.setdefault(token['session_id'], []).append((token['token_no'], token['called_at']))
        for entries in calls.values():
            ordered = [called for _, called in sorted(entries)]
            self.assertEqual(ordered, sorted(ordered))

    def test_summary_reconciles(self):
        report = summary(self.data, 14, 42, date(2026, 6, 1))
        self.assertEqual(sum(d['arrivals'] for d in report['departments']), len(self.data['queue_tokens']))
        for department in report['departments']:
            self.assertEqual(department['arrivals'], department['completed'] + department['cancelled'] + department['noShows'])
            self.assertGreaterEqual(department['averageWait'], 1)
        self.assertEqual(len(report['samples']), 60)

    def test_bounds(self):
        for days in [0, -1, 367]:
            with self.assertRaises(ValueError):
                generate(days=days)


if __name__ == '__main__':
    unittest.main()
