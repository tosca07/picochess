#!/usr/bin/env python3

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

import unittest
from unittest.mock import patch

from uci.engine import UciEngine, UciShell
from uci.rating import Rating, Result

UCI_ELO = "UCI_Elo"
UCI_ELO_NON_STANDARD = "UCI Elo"


class MockEngine(object):
    def __init__(self, *args, **kwargs):
        self.name = "Mocked engine"
        self.options = {}
        self.info_handlers = list()

    def setoption(self, options: dict):
        self.options = options

    def get_elo(self):
        if UCI_ELO in self.options:
            return self.options[UCI_ELO]
        elif UCI_ELO_NON_STANDARD in self.options:
            return self.options[UCI_ELO_NON_STANDARD]
        else:
            return None

    def uci(self):
        pass


@patch("chess.engine.SimpleEngine.popen_uci", new=MockEngine)
class TestEngine(unittest.TestCase):
    def test_engine_uses_elo(self):
        eng = UciEngine("some_test_engine", UciShell(), "")
        eng.engine = MockEngine()
        eng.startup({UCI_ELO: "1400"})
        self.assertEqual("1400", eng.engine.get_elo())
        self.assertEqual(1400, eng.engine_rating)

    def test_engine_uses_elo_non_standard_option(self):
        eng = UciEngine("some_test_engine", UciShell(), "")
        eng.engine = MockEngine()
        eng.startup({UCI_ELO_NON_STANDARD: "1400"})
        self.assertEqual("1400", eng.engine.get_elo())
        self.assertEqual(1400, eng.engine_rating)

    def test_engine_uses_rating(self):
        eng = UciEngine("some_engine", UciShell(), "")
        eng.engine = MockEngine()
        eng.startup({UCI_ELO: "aUtO"}, Rating(1345.5, 123.0))
        self.assertEqual("1350", eng.engine.get_elo())
        self.assertEqual(1350, eng.engine_rating)  # rounded to next 50

    def test_engine_uses_rating_non_standard_option(self):
        eng = UciEngine("some_engine", UciShell(), "")
        eng.engine = MockEngine()
        eng.startup({UCI_ELO_NON_STANDARD: "aUtO"}, Rating(1345.5, 123.0))
        self.assertEqual("1350", eng.engine.get_elo())
        self.assertEqual(1350, eng.engine_rating)  # rounded to next 50

    def test_engine_adaptive_when_using_auto(self):
        eng = UciEngine("some_engine", UciShell(), "")
        eng.engine = MockEngine()
        eng.startup({UCI_ELO: "auto"}, Rating(1345.5, 123.0))
        self.assertTrue(eng.is_adaptive)
        self.assertEqual(1350, eng.engine_rating)  # rounded to next 50

    def test_engine_adaptive_when_using_auto_non_standard_option(self):
        eng = UciEngine("some_engine", UciShell(), "")
        eng.engine = MockEngine()
        eng.startup({UCI_ELO_NON_STANDARD: "auto"}, Rating(1345.5, 123.0))
        self.assertTrue(eng.is_adaptive)
        self.assertEqual(1350, eng.engine_rating)  # rounded to next 50

    def test_engine_not_adaptive_when_using_auto_and_no_rating(self):
        eng = UciEngine("some_engine", UciShell(), "")
        eng.engine = MockEngine()
        eng.startup({UCI_ELO: "auto"}, None)
        self.assertFalse(eng.is_adaptive)
        self.assertEqual(-1, eng.engine_rating)
        self.assertEqual(None, eng.engine.get_elo())

    def test_engine_not_adaptive_when_not_using_auto(self):
        eng = UciEngine("some_engine", UciShell(), "")
        eng.engine = MockEngine()
        eng.startup({UCI_ELO: "1234"}, Rating(1345.5, 123.0))
        self.assertFalse(eng.is_adaptive)
        self.assertEqual(1234, eng.engine_rating)
        self.assertEqual("1234", eng.engine.get_elo())

    def test_engine_has_rating_as_information_when_not_adaptive(self):
        eng = UciEngine("some_engine", UciShell(), "")
        eng.engine = MockEngine()
        eng.startup({UCI_ELO: "1234"}, None)
        self.assertFalse(eng.is_adaptive)
        self.assertEqual(1234, eng.engine_rating)
        self.assertEqual("1234", eng.engine.get_elo())

    def test_engine_has_rating_as_information_when_not_adaptive_non_standard_option(self):
        eng = UciEngine("some_engine", UciShell(), "")
        eng.engine = MockEngine()
        eng.startup({UCI_ELO_NON_STANDARD: "1234"}, None)
        self.assertFalse(eng.is_adaptive)
        self.assertEqual(1234, eng.engine_rating)
        self.assertEqual("1234", eng.engine.get_elo())

    def test_invalid_value_for_uci_elo(self):
        eng = UciEngine("some_engine", UciShell(), "")
        eng.engine = MockEngine()
        eng.startup({UCI_ELO: "XXX"}, Rating(450.5, 123.0))
        self.assertEqual(None, eng.engine.get_elo())
        self.assertEqual(-1, eng.engine_rating)

    def test_engine_does_not_eval_for_no_rating(self):
        eng = UciEngine("some_engine", UciShell(), "")
        eng.engine = MockEngine()
        eng.startup({UCI_ELO: "max(auto, 800)"}, None)
        self.assertEqual(None, eng.engine.get_elo())
        self.assertEqual(-1, eng.engine_rating)

    def test_engine_uses_eval_for_rating(self):
        eng = UciEngine("some_engine", UciShell(), "")
        eng.engine = MockEngine()
        eng.startup({UCI_ELO: "max(auto, 800)"}, Rating(450.5, 123.0))
        self.assertEqual("800", eng.engine.get_elo())
        self.assertEqual(800, eng.engine_rating)

    def test_engine_uses_eval_for_rating_non_standard_option(self):
        eng = UciEngine("some_engine", UciShell(), "")
        eng.engine = MockEngine()
        eng.startup({UCI_ELO_NON_STANDARD: "max(auto, 800)"}, Rating(450.5, 123.0))
        self.assertEqual("800", eng.engine.get_elo())
        self.assertEqual(800, eng.engine_rating)

    def test_simple_eval(self):
        eng = UciEngine("some_engine", UciShell(), "")
        eng.engine = MockEngine()
        eng.startup({UCI_ELO: "auto + 100"}, Rating(850.5, 123.0))
        self.assertEqual("950", eng.engine.get_elo())
        self.assertEqual(950, eng.engine_rating)

    def test_fancy_eval(self):
        eng = UciEngine("some_engine", UciShell(), "")
        eng.engine = MockEngine()
        eng.startup(
            {UCI_ELO: 'exec("import random; random.seed();") or max(800, (auto + random.randint(10,80)))'},
            Rating(850.5, 123.0),
        )
        self.assertGreater(eng.engine_rating, 859)
        self.assertLess(eng.engine_rating, 931)

    def test_eval_syntax_error(self):
        eng = UciEngine("some_engine", UciShell(), "")
        eng.engine = MockEngine()
        eng.startup({UCI_ELO: "max(auto,"}, Rating(450.5, 123.0))
        self.assertEqual(None, eng.engine.get_elo())
        self.assertEqual(-1, eng.engine_rating)

    def test_eval_error(self):
        eng = UciEngine("some_engine", UciShell(), "")
        eng.engine = MockEngine()
        eng.startup({UCI_ELO: 'max(auto, "abc")'}, Rating(450.5, 123.0))
        self.assertEqual(None, eng.engine.get_elo())
        self.assertEqual(-1, eng.engine_rating)

    @patch("uci.engine.write_picochess_ini")
    def test_update_rating(self, _):
        eng = UciEngine("some_engine", UciShell(), "")
        eng.engine = MockEngine()
        eng.startup({UCI_ELO: "auto"}, Rating(849.5, 123.0))
        self.assertEqual("850", eng.engine.get_elo())
        self.assertEqual(850, eng.engine_rating)
        eng.update_rating(Rating(850.5, 123.0), Result.WIN)
        self.assertEqual("900", eng.engine.get_elo())
        self.assertEqual(900, eng.engine_rating)

    @patch("uci.engine.write_picochess_ini")
    def test_update_rating_with_eval(self, _):
        eng = UciEngine("some_engine", UciShell(), "")
        eng.engine = MockEngine()
        eng.startup({UCI_ELO: "auto + 11"}, Rating(850.5, 123.0))
        self.assertEqual("861", eng.engine.get_elo())
        self.assertEqual(861, eng.engine_rating)
        new_rating = eng.update_rating(Rating(850.5, 123.0), Result.WIN)
        self.assertEqual(890, int(new_rating.rating))
        self.assertEqual("901", eng.engine.get_elo())
        self.assertEqual(901, eng.engine_rating)
