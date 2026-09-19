import unittest
from build_demo import synthetic_data


class SyntheticDemo(unittest.TestCase):
    def test_deterministic_complete_and_fictional(self):
        data = synthetic_data()
        self.assertEqual(data, synthetic_data())
        self.assertEqual(len(data['rows']), 270)
        self.assertEqual(len({r['date'] for r in data['rows']}), 90)
        self.assertEqual({r['model'] for r in data['rows']}, {'Atlas Code', 'Cedar Think', 'Orbit Local'})
        self.assertTrue(all(r['tokens'] > 0 and float(r['cost_usd']) >= 0 for r in data['rows']))

    def test_monthly_leaders_change(self):
        data = synthetic_data()
        for month, expected in enumerate(('Atlas Code', 'Cedar Think', 'Orbit Local'), 1):
            totals = {}
            for row in data['rows']:
                if int(row['date'][5:7]) == month:
                    totals[row['model']] = totals.get(row['model'], 0) + row['tokens']
            self.assertEqual(max(totals, key=totals.get), expected)
