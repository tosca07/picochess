import unittest
from freezegun import freeze_time
from unittest.mock import patch

import theme


@patch("utilities.get_location")
class TestTheme(unittest.TestCase):
    def test_calc_theme_for_known_astral_location(self, mocked_get_location):
        with freeze_time("2022-12-21 22:00:00"):
            self.assertEqual("dark", theme.calc_theme("auto", "auto"))
        with freeze_time("2022-12-21 13:00:00"):
            self.assertEqual("light", theme.calc_theme("auto", "auto"))

    def test_calc_theme_for_known_astral_location_from_settings(self, _):
        with freeze_time("2022-12-21 22:00:00"):
            self.assertEqual("dark", theme.calc_theme("auto", "Vienna"))
        with freeze_time("2022-12-21 13:00:00"):
            self.assertEqual("light", theme.calc_theme("auto", "Vienna"))

    def test_calc_theme_for_unknown_astral_but_known_geolocation(self, mocked_get_location):
        mocked_get_location.return_value = ("Woerdern, Austria AT", "127.0.0.1", "127.0.0.1")
        with freeze_time("2022-12-21 22:00:00"):
            self.assertEqual("dark", theme.calc_theme("auto", "auto"))
        with freeze_time("2022-12-21 13:00:00"):
            self.assertEqual("light", theme.calc_theme("auto", "auto"))

    def test_calc_theme_according_to_current_time(self, mocked_get_location):
        mocked_get_location.return_value = ("?", None, None)
        with freeze_time("2022-12-21 16:59:00"):
            self.assertEqual("light", theme.calc_theme("auto", "auto"))
        with freeze_time("2022-12-21 17:00:00"):
            self.assertEqual("dark", theme.calc_theme("auto", "auto"))
        with freeze_time("2022-12-21 09:00:00"):
            self.assertEqual("dark", theme.calc_theme("auto", "auto"))
        with freeze_time("2022-12-21 09:01:00"):
            self.assertEqual("light", theme.calc_theme("auto", "auto"))

    def test_calc_theme_pass_through(self, _):
        self.assertEqual("light", theme.calc_theme("light", "auto"))
        self.assertEqual("dark", theme.calc_theme("dark", "auto"))
