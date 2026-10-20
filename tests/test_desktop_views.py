import unittest

from desktop_views import observation_age


class ObservationAgeTests(unittest.TestCase):
    def test_observation_ages_without_another_packet(self):
        self.assertEqual(observation_age(1000, 1000), 'Recent observation')
        self.assertEqual(observation_age(1000, 1899), 'Recent observation')
        self.assertEqual(observation_age(1000, 1900), 'Stale observation')
        self.assertEqual(observation_age(1000, 100000), 'Stale observation')

    def test_missing_invalid_or_future_receipt_time_is_unknown(self):
        for seen in (None, '', '1000', True, 0, -1, float('nan'), float('inf'), 2001):
            with self.subTest(seen=seen):
                self.assertEqual(observation_age(seen, 2000), 'Unknown')
