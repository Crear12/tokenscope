import unittest
from collections import defaultdict
from build_demo import synthetic_data


class SyntheticDemo(unittest.TestCase):
    def test_deterministic_complete_and_fictional(self):
        data = synthetic_data()
        self.assertEqual(data, synthetic_data())
        self.assertEqual(len(data['rows']), 270)
        self.assertEqual(len({r['date'] for r in data['rows']}), 90)
        self.assertEqual({r['model'] for r in data['rows']}, {'Atlas Code', 'Cedar Think', 'Orbit Local'})
        self.assertTrue(all(r['tokens'] > 0 and float(r['cost_usd']) >= 0 for r in data['rows']))
        by_day_model = defaultdict(lambda: [0, 0.0])
        for row in data['hourly_rows']:
            key = row['date'], row['host'], row['model']
            by_day_model[key][0] += row['tokens']
            by_day_model[key][1] += float(row['cost_usd'])
            self.assertIn(row['hour'], {'09', '14'})
        for row in data['rows']:
            tokens, cost = by_day_model[row['date'], row['host'], row['model']]
            self.assertEqual(tokens, row['tokens'])
            self.assertAlmostEqual(cost, float(row['cost_usd']))

    def test_monthly_leaders_change(self):
        data = synthetic_data()
        for month, expected in enumerate(('Atlas Code', 'Cedar Think', 'Orbit Local'), 1):
            totals = {}
            for row in data['rows']:
                if int(row['date'][5:7]) == month:
                    totals[row['model']] = totals.get(row['model'], 0) + row['tokens']
            self.assertEqual(max(totals, key=totals.get), expected)

    def test_session_titles_and_components_are_synthetic(self):
        data = synthetic_data()
        titles = {f'{name} · iteration {i+1}' for i in range(9)
                  for name in ('Build a sample dashboard', 'Review a fictional API', 'Explore a demo dataset')}
        for row in data['session_rows']:
            self.assertIn(row['session_title'], titles)
            self.assertIn(row['host'], {'workstation', 'lab'})
            self.assertEqual(row['tokens'], sum(row[k] for k in
                             ('fresh_input_tokens', 'cache_read_tokens', 'cache_creation_tokens', 'output_tokens')))
