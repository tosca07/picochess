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

from move_debouncer import MoveDebouncer


@patch("move_debouncer.Timer.cancel")
@patch("move_debouncer.Timer.start")
class TestMoveDebouncer(unittest.TestCase):

    def test_timer_is_started_for_extendable_move(self, MockedTimer_start, MockedTimer_cancel):
        d = MoveDebouncer(1000, lambda fen: None)
        d.update("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR")  # start position
        d.update("rnbqkbnr/pppppppp/8/8/8/8/PPPP1PPP/RNBQKBNR")  # pawn on e2 picked up
        d.update("rnbqkbnr/pppppppp/8/8/8/4P3/PPPP1PPP/RNBQKBNR")  # pawn put down on e3
        MockedTimer_start.assert_called_once()
        MockedTimer_cancel.assert_not_called()

    def test_timer_is_canceled_for_non_extendable_move(self, MockedTimer_start, MockedTimer_cancel):
        d = MoveDebouncer(1000, lambda fen: None)
        d.update("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR")  # start position
        d.update("rnbqkbnr/pppppppp/8/8/8/8/PPPP1PPP/RNBQKBNR")  # pawn on e2 picked up
        d.update("rnbqkbnr/pppppppp/8/8/8/4P3/PPPP1PPP/RNBQKBNR")  # pawn put down on e3
        MockedTimer_start.reset_mock()
        d.update("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR")  # pawn put down on e4
        MockedTimer_cancel.assert_called_once()
        MockedTimer_start.assert_not_called()

    def test_rook_move_is_extendable(self, MockedTimer_start, MockedTimer_cancel):
        d = MoveDebouncer(1000, lambda fen: None)
        d.update("rn1qk2r/pp2ppbp/2p2np1/3p1b1P/3P4/4PN2/PPP1BPP1/RNBQK2R")
        d.update("rn1qk2r/pp2ppbp/2p2np1/3p1b1P/3P4/4PN2/PPP1BPP1/RNBQK3")  # remove rook from h1
        d.update("rn1qk2r/pp2ppbp/2p2np1/3p1b1P/3P4/4PN2/PPP1BPPR/RNBQK3")  # place rook on h2
        d.update("rn1qk2r/pp2ppbp/2p2np1/3p1b1P/3P4/4PN1R/PPP1BPP1/RNBQK3")  # place rook on h3
        self.assertEqual(2, MockedTimer_start.call_count)

    def test_ignore_knight_move(self, MockedTimer_start, MockedTimer_cancel):
        d = MoveDebouncer(1000, lambda fen: None)
        d.update("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR")  # start position
        d.update("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKB1R")  # Knight on g1 picked up
        d.update("rnbqkbnr/pppppppp/8/8/8/5N2/PPPPPPPP/RNBQKB1R")  # Knight put down on f3
        MockedTimer_start.assert_not_called()


if __name__ == "__main__":
    unittest.main()
