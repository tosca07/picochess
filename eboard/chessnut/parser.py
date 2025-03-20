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

from typing import List

from eboard.eboard import to_short_fen, to_battery, get_upper_4_bits, get_lower_4_bits, check_reversed
from eboard.eboard import Battery


class ParserCallback(object):

    def board_update(self, short_fen: str):
        pass

    def battery(self, percent: int, status: Battery):
        pass

    def reversed(self, value: bool):
        pass


class Parser(object):

    def __init__(self, callback: ParserCallback):
        self.callback = callback
        self.buffer = bytearray()
        self.last_board: List = []
        self.reversed = False

    def parse(self, msg: bytearray):
        # copy any previous buffer to the front
        data = self.buffer + msg
        self.buffer = bytearray()
        if len(data) >= 3:
            i = 0
            while i < len(data):
                if (i + 2) < len(data):
                    if data[i] == 0x01 and data[i + 1] == 0x24:  # position
                        new_pos, position_data = self._parse_position(data, i)
                        board = self._to_board(position_data)
                        if len(board) > 0 and None not in board:
                            if self.last_board != board:
                                self.last_board = board
                                board, self.reversed = check_reversed(board, self.reversed, self.callback)
                                self.callback.board_update(to_short_fen(board))
                            i = new_pos
                    elif (i + 3) < len(data) and data[i] == 0x2A and data[i + 1] == 0x02:  # battery
                        self.callback.battery(*to_battery(data[i + 2], data[i + 3]))
                        i += 3
                i += 1
        else:
            self._add_to_buffer(msg)

    def _parse_position(self, data, index):
        data_length = 36
        if len(data) >= (index + data_length + 2):
            data = data[index + 2 :]
            index += data_length + 1
            return index, data
        else:
            self._add_to_buffer(data)
        return index, bytearray()

    def _add_to_buffer(self, arr):
        self.buffer += arr

    def _to_board(self, data):
        if len(data) >= 32:
            board = [None] * 64
            i = 0
            for row in range(7, -1, -1):
                for col in range(3, -1, -1):
                    board[i] = self._to_stone(get_upper_4_bits(data[row * 4 + col]))
                    board[i + 1] = self._to_stone(get_lower_4_bits(data[row * 4 + col]))
                    i += 2
            i += 1
            return board
        else:
            return []

    @staticmethod
    def _to_stone(value):
        translation = {
            0: " ",
            0x07: "P",
            0x06: "R",
            0x0A: "N",
            0x09: "B",
            0x0B: "Q",
            0x0C: "K",
            0x04: "p",
            0x08: "r",
            0x05: "n",
            0x03: "b",
            0x01: "q",
            0x02: "k",
        }
        if value in translation:
            return translation[value]
        else:
            return None
