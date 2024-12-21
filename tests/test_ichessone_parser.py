#!/usr/bin/env python3

import unittest
from unittest.mock import call, patch
from eboard.ichessone.parser import Parser
from eboard.ichessone.parser import Battery


@patch('eboard.ichessone.parser.ParserCallback')
class TestParser(unittest.TestCase):

    def test_initial_position(self, MockedParserCallback):
        data = bytearray.fromhex('3d70a89bc98a77777777000000000000000000000000000000001111111142356324')
        Parser(MockedParserCallback).parse(data)
        MockedParserCallback.board_update.assert_called_once_with('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR')

    def test_initial_position_twice_calls_update_only_once(self, MockedParserCallback):
        data = bytearray.fromhex('3d70a89bc98a77777777000000000000000000000000000000001111111142356324' +
                                 '3d70a89bc98a77777777000000000000000000000000000000001111111142356324')
        Parser(MockedParserCallback).parse(data)
        MockedParserCallback.board_update.assert_called_once_with('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR')

    def test_two_different_positions_calls_update_twice(self, MockedParserCallback):
        data = bytearray.fromhex('3d70a89bc98a77777777000000000000000000000000000000001111111142356324' +
                                 '3d70a89bc98a77777777000000000000000000000000000000011111111042356324')
        Parser(MockedParserCallback).parse(data)
        calls = [call('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR'),
                 call('rnbqkbnr/pppppppp/8/8/8/7P/PPPPPPP1/RNBQKBNR')]
        MockedParserCallback.board_update.assert_has_calls(calls)

    def test_invalid_data(self, MockedParserCallback):
        data = bytearray.fromhex('3d70a89bc98a777777770000000000000000ff000000000000001111111142356324')
        Parser(MockedParserCallback).parse(data)
        MockedParserCallback.board_update.assert_not_called()

    def test_initial_position_black_and_white_reversed(self, MockedParserCallback):
        data = bytearray.fromhex('3d7042365324111111110000000000000000000000000000000077777777a89cb98a')
        Parser(MockedParserCallback).parse(data)
        MockedParserCallback.board_update.assert_called_once_with('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR')

    def test_reversed_board_calls_reversed_true(self, MockedParserCallback):
        data = bytearray.fromhex('3d7042365324111111110000000000000000000000000000000077777777a89cb98a')
        Parser(MockedParserCallback).parse(data)
        MockedParserCallback.reversed.assert_called_once_with(True)

    def test_junk_before_position_is_ignored(self, MockedParserCallback):
        data = bytearray.fromhex(
            '9876543210' + '3d70a89bc98a77777777000000000000000000000000000000001111111142356324')
        Parser(MockedParserCallback).parse(data)
        MockedParserCallback.board_update.assert_called_once_with('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR')

    def test_initial_position_split_with_junk_in_front(self, MockedParserCallback):
        data = bytearray.fromhex('9871233210' + '3d70a89bc98a7777777700000000000000000000000000000000')
        parser = Parser(MockedParserCallback)
        parser.parse(data)
        parser.parse(bytearray.fromhex('1111111142356324'))
        MockedParserCallback.board_update.assert_called_once_with('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR')

    def test_battery_charging(self, MockedParserCallback):
        data = bytearray.fromhex('3d620164')
        Parser(MockedParserCallback).parse(data)
        MockedParserCallback.battery.assert_called_once_with(100, Battery.CHARGING)

    def test_battery_discharging(self, MockedParserCallback):
        data = bytearray.fromhex('3d620058')
        Parser(MockedParserCallback).parse(data)
        MockedParserCallback.battery.assert_called_once_with(88, Battery.DISCHARGING)

    def test_battery_low(self, MockedParserCallback):
        data = bytearray.fromhex('3d620009')
        Parser(MockedParserCallback).parse(data)
        MockedParserCallback.battery.assert_called_once_with(9, Battery.LOW)

    def test_battery_exhausted(self, MockedParserCallback):
        data = bytearray.fromhex('3d620004')
        Parser(MockedParserCallback).parse(data)
        MockedParserCallback.battery.assert_called_once_with(4, Battery.EXHAUSTED)

    def test_junk_position_junk_battery(self, MockedParserCallback):
        parser = Parser(MockedParserCallback)
        parser.parse(bytearray.fromhex('9871233210'))  # invalid data
        parser.parse(
            bytearray.fromhex('3d70a89bc98a7777777700000000000000000000000000000000'))  # position, part1
        parser.parse(bytearray.fromhex('11111111'))  # position, part2
        parser.parse(bytearray.fromhex('42356324'))  # position, part3
        parser.parse(bytearray.fromhex('9871233210'))  # invalid data
        parser.parse(bytearray.fromhex('3d62'))  # battery, first half
        parser.parse(bytearray.fromhex('0004'))  # battery, second half
        MockedParserCallback.board_update.assert_called_once_with('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR')
        MockedParserCallback.battery.assert_called_once_with(4, Battery.EXHAUSTED)


if __name__ == '__main__':
    unittest.main()
