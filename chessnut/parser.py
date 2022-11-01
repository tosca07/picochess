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

from enum import Enum


class Battery(Enum):
    CHARGING = 0
    DISCHARGING = 1
    LOW = 2
    EXHAUSTED = 3


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
        self.last_board = []
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
                                board = self._check_reversed(board)
                                self.callback.board_update(self._to_short_fen(board))
                            i = new_pos
                    elif (i + 3) < len(data) and data[i] == 0x2a and data[i + 1] == 0x02:  # battery
                        self.callback.battery(*self._to_battery(data[i + 2], data[i + 3]))
                        i += 3
                i += 1
        else:
            self._add_to_buffer(msg)

    def _parse_position(self, data, index):
        data_length = 36
        if len(data) >= (index + data_length + 2):
            data = data[index + 2:]
            index += data_length + 1
            return index, data
        else:
            self._add_to_buffer(data)
        return index, bytearray()

    def _add_to_buffer(self, arr):
        self.buffer += arr

    def _to_battery(self, percent, status):
        battery = Battery.DISCHARGING
        if status == 1:
            battery = Battery.CHARGING
        value = max(0, min(100, percent))
        if value < 5:
            battery = Battery.EXHAUSTED
        elif value < 10:
            battery = Battery.LOW
        return value, battery

    def _to_board(self, data):
        if len(data) >= 32:
            board = [None] * 64
            i = 0
            for row in range(7, -1, -1):
                for col in range(3, -1, -1):
                    board[i] = self._to_stone(self._get_upper_4_bits(data[row * 4 + col]))
                    board[i + 1] = self._to_stone(self._get_lower_4_bits(data[row * 4 + col]))
                    i += 2
            i += 1
            return board
        else:
            return []

    def _to_stone(self, value):
        translation = {0: ' ',
                       0x07: 'P', 0x06: 'R', 0x0a: 'N', 0x09: 'B', 0x0b: 'Q', 0x0c: 'K',
                       0x04: 'p', 0x08: 'r', 0x05: 'n', 0x03: 'b', 0x01: 'q', 0x02: 'k'}
        if value in translation:
            return translation[value]
        else:
            return None

    def _to_short_fen(self, board):
        fen = ''
        for row_index, row in enumerate(range(7, -1, -1)):
            blanks = 0
            for col_index, col in enumerate(range(8)):
                if board[row * 8 + col] == ' ':
                    blanks += 1
                    if col_index == 7 and blanks > 0:
                        fen += str(blanks)
                else:
                    if blanks > 0:
                        fen += str(blanks)
                    blanks = 0
                    fen += board[row * 8 + col]
            if row_index != 7:
                fen += '/'
        return fen

    def _check_reversed(self, brd):
        board = brd.copy()
        w_count_lower_half, b_count_lower_half = self._piece_count(board, range(32))
        w_count_upper_half, b_count_upper_half = self._piece_count(board, range(32, 64))
        if self.reversed and w_count_lower_half > 10 and b_count_upper_half > 10:
            self.reversed = False
            self.callback.reversed(self.reversed)
        elif not self.reversed and w_count_upper_half > 10 and b_count_lower_half > 10:
            self.reversed = True
            self.callback.reversed(self.reversed)
        if self.reversed:
            board.reverse()
        return board

    def _piece_count(self, board, board_half):
        w_count = 0
        b_count = 0
        for i in board_half:
            if board[i] != ' ':
                if board[i] < 'Z':
                    w_count += 1
                else:
                    b_count += 1
        return w_count, b_count

    @staticmethod
    def _get_upper_4_bits(b):
        return (b & 0xf0) >> 4

    @staticmethod
    def _get_lower_4_bits(b):
        return b & 0x0f
