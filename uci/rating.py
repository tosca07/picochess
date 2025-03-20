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

from typing import Optional
from enum import Enum
import math

from dgt.util import GameResult, PlayMode


class Result(Enum):
    DRAW = 0.5
    WIN = 1
    LOSS = 0


class Rating(object):
    THRESHOLD = 0.00001
    Q = math.log(10) / 400

    def __init__(self, rating: float, rating_deviation: float):
        self.rating = rating
        self.rating_deviation = rating_deviation

    def rate(self, other: "Rating", result: Result) -> "Rating":
        """
        Rate with Glicko rating (see http://www.glicko.net/glicko/glicko.pdf)
        """
        expected_outcome = self._expected_outcome(other)
        g = self._g(other.rating_deviation)
        d_squared = math.pow((math.pow(Rating.Q, 2)) * (math.pow(g, 2)) * expected_outcome * (1 - expected_outcome), -1)
        denominator = math.pow(max(self.rating_deviation, 0.000001), -2) + 1 / d_squared
        new_rating = self.rating + Rating.Q / denominator * g * (result.value - expected_outcome)
        return Rating(new_rating, math.sqrt(1.0 / denominator))

    def _expected_outcome(self, other: "Rating"):
        return 1.0 / (1 + math.pow(10, -self._g(other.rating_deviation) * (self.rating - other.rating) / 400.0))

    def _g(self, deviation: float) -> float:
        return 1.0 / math.sqrt(1 + (3 * (math.pow(Rating.Q, 2)) * math.pow(deviation, 2) / math.pow(math.pi, 2)))

    def is_similar_to(self, other: "Rating") -> bool:
        return (
            math.fabs(self.rating - other.rating) < Rating.THRESHOLD
            and math.fabs(self.rating_deviation - other.rating_deviation) < Rating.THRESHOLD
        )


def determine_result(result, play_mode, is_whites_turn) -> Optional[Result]:
    res = None
    if (
        result == GameResult.DRAW
        or result == GameResult.STALEMATE
        or result == GameResult.SEVENTYFIVE_MOVES
        or result == GameResult.FIVEFOLD_REPETITION
        or result == GameResult.INSUFFICIENT_MATERIAL
    ):
        res = Result.DRAW
    else:
        if (
            result == GameResult.WIN_BLACK
            and play_mode == PlayMode.USER_BLACK
            or result == GameResult.WIN_WHITE
            and play_mode == PlayMode.USER_WHITE
        ):
            res = Result.WIN
        elif (
            result == GameResult.WIN_WHITE
            and play_mode == PlayMode.USER_BLACK
            or result == GameResult.WIN_BLACK
            and play_mode == PlayMode.USER_WHITE
        ):
            res = Result.LOSS
        elif result == GameResult.OUT_OF_TIME:
            if (
                play_mode == PlayMode.USER_WHITE
                and not is_whites_turn
                or play_mode == PlayMode.USER_BLACK
                and is_whites_turn
            ):
                res = Result.WIN
            else:
                res = Result.LOSS
        elif result == GameResult.MATE:
            if (
                play_mode == PlayMode.USER_BLACK
                and is_whites_turn
                or play_mode == PlayMode.USER_WHITE
                and not is_whites_turn
            ):
                res = Result.WIN
            else:
                res = Result.LOSS
    return res
