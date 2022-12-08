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

from uci.engine import UciEngine, UciShell
from uci.rating import Rating


class MockEngine(object):
    def __init__(self):
        self.name = 'Mocked engine'
        self.options = {}

    def setoption(self, options: dict):
        self.options = options

    def get_elo(self):
        if 'UCI_Elo' in self.options:
            return self.options['UCI_Elo']
        else:
            return None


class TestEngine(unittest.TestCase):

    def test_engine_uses_elo(self):
        eng = UciEngine('some_test_engine', UciShell(), '')
        eng.engine = MockEngine()
        eng.startup({'UCI_Elo': '1400'})
        self.assertEqual('1400', eng.engine.get_elo())
        self.assertEqual(1400, eng.engine_rating)

    def test_engine_uses_rating(self):
        eng = UciEngine('some_engine', UciShell(), '')
        eng.engine = MockEngine()
        eng.startup({'UCI_Elo': 'aUtO'}, Rating(1345.5, 123.0))
        self.assertEqual('1350', eng.engine.get_elo())
        self.assertEqual(1350, eng.engine_rating)  # rounded to next 50

    def test_engine_adaptive_when_using_auto(self):
        eng = UciEngine('some_engine', UciShell(), '')
        eng.engine = MockEngine()
        eng.startup({'UCI_Elo': 'auto'}, Rating(1345.5, 123.0))
        self.assertTrue(eng.is_adaptive)
        self.assertEqual(1350, eng.engine_rating)  # rounded to next 50

    def test_engine_not_adaptive_when_using_auto_and_no_rating(self):
        eng = UciEngine('some_engine', UciShell(), '')
        eng.engine = MockEngine()
        eng.startup({'UCI_Elo': 'auto'}, None)
        self.assertFalse(eng.is_adaptive)
        self.assertEqual(-1, eng.engine_rating)
        self.assertEqual(None, eng.engine.get_elo())

    def test_engine_not_adaptive_when_not_using_auto(self):
        eng = UciEngine('some_engine', UciShell(), '')
        eng.engine = MockEngine()
        eng.startup({'UCI_Elo': '1234'}, Rating(1345.5, 123.0))
        self.assertFalse(eng.is_adaptive)
        self.assertEqual(1234, eng.engine_rating)
        self.assertEqual('1234', eng.engine.get_elo())

    def test_engine_has_rating_as_information_when_not_adaptive(self):
        eng = UciEngine('some_engine', UciShell(), '')
        eng.engine = MockEngine()
        eng.startup({'UCI_Elo': '1234'}, None)
        self.assertFalse(eng.is_adaptive)
        self.assertEqual(1234, eng.engine_rating)
        self.assertEqual('1234', eng.engine.get_elo())
