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
from unittest.mock import call, patch
from chessnut.parser import Parser
from chessnut.parser import Battery


@patch("chessnut.parser.ParserCallback")
class TestParser(unittest.TestCase):

    def test_initial_position(self, MockedParserCallback):
        data = bytearray.fromhex("012458233185444444440000000000000000000000000000000077777777A6C99B6AFFFFFFFF")
        Parser(MockedParserCallback).parse(data)
        MockedParserCallback.board_update.assert_called_once_with("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR")

    def test_initial_position_twice_calls_update_only_once(self, MockedParserCallback):
        data = bytearray.fromhex(
            "012458233185444444440000000000000000000000000000000077777777A6C99B6AFFFFFFFF"
            + "012458233185444444440000000000000000000000000000000077777777A6C99B6AFFFFFFFF"
        )
        Parser(MockedParserCallback).parse(data)
        MockedParserCallback.board_update.assert_called_once_with("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR")

    def test_two_different_positions_calls_update_twice(self, MockedParserCallback):
        data = bytearray.fromhex(
            "012458233185444444440000000000000000000000000000000077777777A6C99B6AFFFFFFFF"
            + "012458233185444400440000000000000000000000000000000077700777A6C99B6AFFFFFFFF"
        )
        Parser(MockedParserCallback).parse(data)
        calls = [
            call("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"),
            call("rnbqkbnr/pp2pppp/8/8/8/8/PP1PP1PP/RNBQKBNR"),
        ]
        MockedParserCallback.board_update.assert_has_calls(calls)

    def test_invalid_data(self, MockedParserCallback):
        data = bytearray.fromhex("012458233185444444440000000000000FFFF00000000000000077777777A6C99B6AFFFFFFFF")
        Parser(MockedParserCallback).parse(data)
        MockedParserCallback.board_update.assert_not_called()

    def test_initial_position_black_and_white_reversed(self, MockedParserCallback):
        data = bytearray.fromhex("0124A6B99C6A77777777000000000000000000000000000000004444444458133285FFFFFFFF")
        Parser(MockedParserCallback).parse(data)
        MockedParserCallback.board_update.assert_called_once_with("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR")

    def test_reversed_board_calls_reversed_true(self, MockedParserCallback):
        data = bytearray.fromhex("0124A6B99C6A77777777000000000000000000000000000000004444444458133285FFFFFFFF")
        Parser(MockedParserCallback).parse(data)
        MockedParserCallback.reversed.assert_called_once_with(True)

    def test_junk_before_position_is_ignored(self, MockedParserCallback):
        data = bytearray.fromhex(
            "9876543210" + "012458233185444444440000000000000000000000000000000077777777A6C99B6AFFFFFFFF"
        )
        Parser(MockedParserCallback).parse(data)
        MockedParserCallback.board_update.assert_called_once_with("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR")

    def test_initial_position_split_with_junk_in_front(self, MockedParserCallback):
        data = bytearray.fromhex("9871233210" + "012458233185444444440000000000000000000000000000000077777777")
        parser = Parser(MockedParserCallback)
        parser.parse(data)
        parser.parse(bytearray.fromhex("A6C99B6AFFFFFFFF"))
        MockedParserCallback.board_update.assert_called_once_with("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR")

    def test_battery_charging(self, MockedParserCallback):
        data = bytearray.fromhex("2a026401")
        Parser(MockedParserCallback).parse(data)
        MockedParserCallback.battery.assert_called_once_with(100, Battery.CHARGING)

    def test_battery_discharging(self, MockedParserCallback):
        data = bytearray.fromhex("2a025800")
        Parser(MockedParserCallback).parse(data)
        MockedParserCallback.battery.assert_called_once_with(88, Battery.DISCHARGING)

    def test_battery_low(self, MockedParserCallback):
        data = bytearray.fromhex("2a020900")
        Parser(MockedParserCallback).parse(data)
        MockedParserCallback.battery.assert_called_once_with(9, Battery.LOW)

    def test_battery_exhausted(self, MockedParserCallback):
        data = bytearray.fromhex("2a020400")
        Parser(MockedParserCallback).parse(data)
        MockedParserCallback.battery.assert_called_once_with(4, Battery.EXHAUSTED)

    def test_junk_position_junk_battery(self, MockedParserCallback):
        parser = Parser(MockedParserCallback)
        parser.parse(bytearray.fromhex("9871233210"))  # invalid data
        parser.parse(
            bytearray.fromhex("012458233185444444440000000000000000000000000000000077777777")
        )  # position, part1
        parser.parse(bytearray.fromhex("A6C99B6A"))  # position, part2
        parser.parse(bytearray.fromhex("FFFFFFFF"))  # position, part3
        parser.parse(bytearray.fromhex("9871233210"))  # invalid data
        parser.parse(bytearray.fromhex("2a02"))  # battery, first half
        parser.parse(bytearray.fromhex("0400"))  # battery, second half
        MockedParserCallback.board_update.assert_called_once_with("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR")
        MockedParserCallback.battery.assert_called_once_with(4, Battery.EXHAUSTED)


if __name__ == "__main__":
    unittest.main()
