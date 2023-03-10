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

from dgt.util import GameResult, PlayMode
from uci.rating import Rating, Result
from uci.rating import determine_result


class TestRating(unittest.TestCase):

    def test_rate_a(self):
        rating = Rating(1500, 200)
        rating = rating.rate(Rating(1400, 30), Result.WIN)
        rating = rating.rate(Rating(1550, 100), Result.LOSS)
        rating = rating.rate(Rating(1700, 300), Result.LOSS)
        self.assertTrue(rating.is_similar_to(Rating(1464.219038, 151.253743)))

    def test_rate_b(self):
        rating = Rating(1400, 80)
        rating = rating.rate(Rating(1500, 150), Result.WIN)
        self.assertTrue(rating.is_similar_to(Rating(1420.049159, 78.430213)))

    def test_rate_1700_rated(self):
        rating = Rating(1200, 350)
        rating = rating.rate(Rating(1200, 0), Result.WIN)
        rating = rating.rate(Rating(1374, 0), Result.WIN)
        rating = rating.rate(Rating(1491, 0), Result.WIN)
        rating = rating.rate(Rating(1578, 0), Result.WIN)
        rating = rating.rate(Rating(1647, 0), Result.WIN)
        self.assertTrue(rating.is_similar_to(Rating(1705.760868, 142.013046)))

    def test_rate_1300_rated(self):
        rating = Rating(1200, 350)
        rating = rating.rate(Rating(1200, 0), Result.WIN)
        rating = rating.rate(Rating(1374, 0), Result.LOSS)
        rating = rating.rate(Rating(1258, 0), Result.WIN)
        rating = rating.rate(Rating(1345, 0), Result.LOSS)
        self.assertTrue(rating.is_similar_to(Rating(1275.6206362, 155.605427)))

    def test_rate_1000_rated(self):
        rating = Rating(1200, 350)
        rating = rating.rate(Rating(1200, 0), Result.LOSS)
        rating = rating.rate(Rating(1025, 0), Result.LOSS)
        rating = rating.rate(Rating(908, 0), Result.WIN)
        rating = rating.rate(Rating(995, 0), Result.WIN)
        self.assertTrue(rating.is_similar_to(Rating(1065.206549, 155.6053732)))

    def test_rate_with_zero_rating_deviation(self):
        rating = Rating(1200, 0)
        rating = rating.rate(Rating(1200, 0), Result.LOSS)
        print(rating.rating_deviation)
        self.assertTrue(rating.is_similar_to(Rating(1200.0, 0.0)))


class TestDetermineResult(unittest.TestCase):

    def test_no_result_for_ABORT(self):
        self.assertIsNone(determine_result(GameResult.ABORT, PlayMode.USER_WHITE, True))

    def test_win(self):
        self.assertEqual(Result.WIN, determine_result(GameResult.WIN_WHITE, PlayMode.USER_WHITE, True))
        self.assertEqual(Result.WIN, determine_result(GameResult.WIN_WHITE, PlayMode.USER_WHITE, False))
        self.assertEqual(Result.WIN, determine_result(GameResult.WIN_BLACK, PlayMode.USER_BLACK, True))
        self.assertEqual(Result.WIN, determine_result(GameResult.WIN_BLACK, PlayMode.USER_BLACK, False))

    def test_loss(self):
        self.assertEqual(Result.LOSS, determine_result(GameResult.WIN_WHITE, PlayMode.USER_BLACK, True))
        self.assertEqual(Result.LOSS, determine_result(GameResult.WIN_WHITE, PlayMode.USER_BLACK, False))
        self.assertEqual(Result.LOSS, determine_result(GameResult.WIN_BLACK, PlayMode.USER_WHITE, True))
        self.assertEqual(Result.LOSS, determine_result(GameResult.WIN_BLACK, PlayMode.USER_WHITE, False))

    def test_draw(self):
        self.assertEqual(Result.DRAW, determine_result(GameResult.DRAW, PlayMode.USER_WHITE, True))
        self.assertEqual(Result.DRAW, determine_result(GameResult.INSUFFICIENT_MATERIAL, PlayMode.USER_WHITE, True))
        self.assertEqual(Result.DRAW, determine_result(GameResult.FIVEFOLD_REPETITION, PlayMode.USER_WHITE, True))
        self.assertEqual(Result.DRAW, determine_result(GameResult.SEVENTYFIVE_MOVES, PlayMode.USER_WHITE, True))
        self.assertEqual(Result.DRAW, determine_result(GameResult.STALEMATE, PlayMode.USER_WHITE, True))

    def test_mate(self):
        self.assertEqual(Result.WIN, determine_result(GameResult.MATE, PlayMode.USER_WHITE, False))
        self.assertEqual(Result.WIN, determine_result(GameResult.MATE, PlayMode.USER_BLACK, True))
        self.assertEqual(Result.LOSS, determine_result(GameResult.MATE, PlayMode.USER_WHITE, True))
        self.assertEqual(Result.LOSS, determine_result(GameResult.MATE, PlayMode.USER_BLACK, False))
