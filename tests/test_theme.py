import datetime
import unittest
from unittest.mock import patch
from tests.mock_datetime import mock_datetime_now

import theme


@patch('utilities.get_location')
class TestTheme(unittest.TestCase):
    def test_calc_theme_for_known_astral_location(self, mocked_get_location):
        mocked_get_location.return_value = ('Berlin', '127.0.0.1', '127.0.0.1')
        with mock_datetime_now(datetime.datetime(2022, 12, 21, 22, 0, 0, 0), datetime):
            self.assertEqual('dark', theme.calc_theme('auto'))
        with mock_datetime_now(datetime.datetime(2022, 12, 21, 13, 0, 0, 0), datetime):
            self.assertEqual('light', theme.calc_theme('auto'))

    def test_calc_theme_for_unknown_astral_but_known_geolocation(self, mocked_get_location):
        mocked_get_location.return_value = ('Woerdern, Austria AT', '127.0.0.1', '127.0.0.1')
        with mock_datetime_now(datetime.datetime(2022, 12, 21, 22, 0, 0, 0), datetime):
            self.assertEqual('dark', theme.calc_theme('auto'))
        with mock_datetime_now(datetime.datetime(2022, 12, 21, 13, 0, 0, 0), datetime):
            self.assertEqual('light', theme.calc_theme('auto'))

    def test_calc_theme_according_to_current_time(self, mocked_get_location):
        mocked_get_location.return_value = ('?', None, None)
        with mock_datetime_now(datetime.datetime(2022, 12, 21, 16, 59, 0, 0), datetime):
            self.assertEqual('light', theme.calc_theme('auto'))
        with mock_datetime_now(datetime.datetime(2022, 12, 21, 17, 0, 0, 0), datetime):
            self.assertEqual('dark', theme.calc_theme('auto'))
        with mock_datetime_now(datetime.datetime(2022, 12, 21, 9, 0, 0, 0), datetime):
            self.assertEqual('dark', theme.calc_theme('auto'))
        with mock_datetime_now(datetime.datetime(2022, 12, 21, 9, 1, 0, 0), datetime):
            self.assertEqual('light', theme.calc_theme('auto'))

    def test_calc_theme_pass_through(self, _):
        self.assertEqual('light', theme.calc_theme('light'))
        self.assertEqual('dark', theme.calc_theme('dark'))
