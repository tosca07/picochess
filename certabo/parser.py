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

import binascii
import re
import typing


class CertaboPiece(object):

    def __init__(self, piece_id: bytearray):
        self.piece_id = piece_id

    def __eq__(self, obj):
        return isinstance(obj, CertaboPiece) and obj.piece_id == self.piece_id

    def __hash__(self):
        return hash(binascii.hexlify(self.piece_id))

    def __str__(self):
        return self.piece_id

    def __repr__(self):
        return f'CertaboPiece(piece_id={self.piece_id})'


class BoardTranslator:

    def translate(self, board: typing.List[CertaboPiece]):
        pass


class CalibrationCallback:

    def calibration_complete(self, stones: typing.Dict[CertaboPiece, int]):
        pass

    def calibration_complete_square(self, square: int):
        pass

    def calibration_error(self):
        pass


class ParserCallback(object):

    def board_update(self, short_fen: str):
        pass

    def reversed(self, value: bool):
        pass


NO_PIECE = CertaboPiece(bytearray(5))
BLACK_EXTRA_QUEEN_SQUARE = 19
WHITE_EXTRA_QUEEN_SQUARE = 43
NO_STONE = ' '


def to_square(i: int):
    row = 7 - (i // 8)
    col = i % 8
    return row * 8 + col


class Parser(object):

    def __init__(self, callback: BoardTranslator):
        self.callback = callback
        self.buffer = bytearray()
        self.last_board = []
        self.reversed = False

    def parse(self, msg: bytearray):
        # copy any previous buffer to the front
        data = self.buffer + msg
        self.buffer = bytearray()

        if len(data) > 64 * 5 * 2:
            input_str = data.decode(encoding='UTF-8', errors='ignore')
            if '\r\n' not in input_str:
                self._add_to_buffer(data)
            else:
                split_data = input_str.split(':')
                for index, part in enumerate(split_data):
                    if len(part) > 0 and not self._parse(part) and index == len(split_data) - 1:
                        position = len(data) - len(part) - 1
                        if position >= 0:
                            self._add_to_buffer(data[position:])
                        break
        else:
            self.buffer = data

    def _add_to_buffer(self, arr):
        self.buffer += arr

    def _parse(self, part: str):
        split_input = re.sub('[\r\nL*]', '', part).split()
        if len(split_input) >= 320:
            board = []
            for square in range(64):
                piece_id = bytearray(5)
                for i in range(5):
                    try:
                        piece_id[i] = int(split_input[square * 5 + i])
                    except ValueError:
                        return False
                piece = CertaboPiece(piece_id)
                board.append(piece)
            self.callback.translate(board)
            self.buffer = bytearray()
            return True
        else:
            return False


class CertaboBoardMessageParser(BoardTranslator):

    def __init__(self, callback: ParserCallback):
        self.callback = callback
        self.last_board = []
        self.reversed = False
        self.stones = {}
        self.parser = Parser(self)

    def update_stones(self, stones: typing.Dict[CertaboPiece, int]):
        self.stones = stones

    def parse(self, msg: bytearray):
        self.parser.parse(msg)

    def translate(self, board: typing.List[CertaboPiece]):
        newBoard = [None] * 64
        i = 0
        for piece in board:
            square = to_square(i)
            if piece in self.stones:
                newBoard[square] = self.stones[piece]
            else:
                newBoard[square] = NO_STONE
            i += 1
        if self.last_board != newBoard:
            self.last_board = newBoard
            newBoard = self._check_reversed(newBoard)
            self.callback.board_update(self._to_short_fen(newBoard))

    # TODO duplicates _to_short_fen from chessnut/parser.py
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

    # TODO duplicates _piece_count from chessnut/parser.py
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


class CalibrationSquare(object):

    def __init__(self, square: int):
        self.square = square
        self.pieceId = None

    def calibrate_piece(self, callback: CalibrationCallback, received_boards: typing.List[typing.List[CertaboPiece]]):
        piece_count: typing.Dict[CertaboPiece, int] = {}
        for board in received_boards:
            piece = board[self.square]
            if piece in piece_count.keys():
                piece_count[piece] = piece_count[piece] + 1
            else:
                piece_count[piece] = 1
        for p_id, count in piece_count.items():
            if count > len(received_boards) // 2 and self._piece_or_extra_queen_square(p_id):
                self.pieceId = p_id
                if p_id != NO_PIECE:
                    callback.calibration_complete_square(to_square(self.square))
                break

    def _piece_or_extra_queen_square(self, piece: CertaboPiece) -> bool:
        return piece != NO_PIECE or self._is_extra_queen_square()

    def _is_extra_queen_square(self) -> bool:
        return self.square == BLACK_EXTRA_QUEEN_SQUARE or self.square == WHITE_EXTRA_QUEEN_SQUARE

    def is_calibrated(self):
        return self.pieceId is not None

    def get_stone(self):
        if 7 < self.square < 16:
            return 'p'
        if 47 < self.square < 56:
            return 'P'
        if self.square == 0 or self.square == 7:
            return self._no_stone_or('r')
        if self.square == 1 or self.square == 6:
            return self._no_stone_or('n')
        if self.square == 2 or self.square == 5:
            return self._no_stone_or('b')
        if self.square == 3 or self.square == BLACK_EXTRA_QUEEN_SQUARE:
            return self._no_stone_or('q')
        if self.square == 4:
            return self._no_stone_or('k')
        if self.square == 56 or self.square == 63:
            return self._no_stone_or('R')
        if self.square == 57 or self.square == 62:
            return self._no_stone_or('N')
        if self.square == 58 or self.square == 61:
            return self._no_stone_or('B')
        if self.square == 59 or self.square == WHITE_EXTRA_QUEEN_SQUARE:
            return self._no_stone_or('Q')
        if self.square == 60:
            return self._no_stone_or('K')
        return None

    def _no_stone_or(self, stone: str):
        if self.pieceId == NO_PIECE:
            return ' '
        else:
            return stone


class CertaboCalibrator(BoardTranslator):

    def __init__(self, callback: CalibrationCallback):
        super().__init__()
        self.callback = callback
        self.calibrationSquares = []
        self.receivedBoards = []
        self.calibrationComplete = False
        self.parser = Parser(self)
        for i in range(16):
            # black squares
            self.calibrationSquares.append(CalibrationSquare(i))
        for i in range(48, 64):
            # white squares
            self.calibrationSquares.append(CalibrationSquare(i))
        self.calibrationSquares.append(CalibrationSquare(BLACK_EXTRA_QUEEN_SQUARE))
        self.calibrationSquares.append(CalibrationSquare(WHITE_EXTRA_QUEEN_SQUARE))

    def calibrate(self, input: bytearray):
        self.parser.parse(input)

    def translate(self, board: typing.List[CertaboPiece]):
        self.receivedBoards.append(board)
        if len(self.receivedBoards) >= 7 and not self.calibrationComplete:
            if self.check_pieces():
                stones = {}
                for square in self.calibrationSquares:
                    stone = square.get_stone()
                    if stone is not None:
                        stones[square.pieceId] = stone
                self.calibrationComplete = True
                self.callback.calibration_complete(stones)
            elif len(self.receivedBoards) > 15:
                self.receivedBoards = self.receivedBoards[-10:]
                self.callback.calibration_error()

    def check_pieces(self) -> bool:
        allCalibrated = True
        for square in self.calibrationSquares:
            if not square.is_calibrated():
                square.calibrate_piece(self.callback, self.receivedBoards)
                if not square.is_calibrated():
                    allCalibrated = False
        return allCalibrated
