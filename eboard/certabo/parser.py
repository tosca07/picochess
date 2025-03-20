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

from typing import Dict, List, Optional
import binascii
import re
from collections import Counter

from eboard.eboard import to_short_fen, check_reversed


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
        return f"CertaboPiece(piece_id={self.piece_id})"


class BoardTranslator:

    def translate(self, board: List[CertaboPiece]):
        pass

    def translate_occupied_squares(self, board: List[int]):
        pass

    def has_piece_recognition(self, value: bool):
        pass


class CalibrationCallback:

    def calibration_complete(self, stones: Dict[CertaboPiece, Optional[str]]):
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

    def has_piece_recognition(self, piece_recognition: bool):
        pass

    def occupied_squares(self, board: List[int]):
        pass

    def request_promotion_dialog(self, move: str):
        pass


NO_PIECE = CertaboPiece(bytearray(5))
BLACK_EXTRA_QUEEN_SQUARE = 19
WHITE_EXTRA_QUEEN_SQUARE = 43
NO_STONE = " "


def to_square(i: int):
    row = 7 - (i // 8)
    col = i % 8
    return row * 8 + col


class Parser(object):

    def __init__(self, callback: BoardTranslator):
        self.callback = callback
        self.buffer = bytearray()
        self.last_board: List = []
        self.reversed = False
        self.piece_recognition = False

    def parse(self, msg: bytearray):
        # copy any previous buffer to the front
        data = self.buffer + msg
        self.buffer = bytearray()

        if len(data) > 15:
            input_str = data.decode(encoding="UTF-8", errors="ignore")
            if "\r\n" not in input_str:
                self._add_to_buffer(data)
            else:
                split_data = input_str.split(":")
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
        split_input = re.sub("[\r\nL*]", "", part).split()
        if not self.piece_recognition and len(split_input) > 8:
            self.piece_recognition = True
            self.callback.has_piece_recognition(True)
        if self.piece_recognition:
            return self._parse_with_piece_info(split_input)
        else:
            return self._parse_without_piece_info(split_input)

    def _parse_with_piece_info(self, split_input):
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

    def _parse_without_piece_info(self, split_input):
        if len(split_input) >= 8:
            board = []
            for row in range(8):
                try:
                    b = int(split_input[row])
                    for col in range(7, -1, -1):
                        if (b & (1 << col)) != 0:
                            board.append(1)  # UNKNOWN
                        else:
                            board.append(0)
                except ValueError:
                    return False
            self.callback.translate_occupied_squares(board)
            self.buffer = bytearray()
            return True
        else:
            return False


class CertaboBoardMessageParser(BoardTranslator):

    def __init__(self, callback: ParserCallback, low_gain):
        self.callback = callback
        self.last_board: List = []
        self.board_history: List = []
        self.low_gain_chips = low_gain
        self.reversed = False
        self.stones: Dict = {}
        self.parser = Parser(self)

    def update_stones(self, stones: Dict[CertaboPiece, Optional[str]]):
        self.stones = stones

    def parse(self, msg: bytearray):
        self.parser.parse(msg)

    def translate(self, board: List[CertaboPiece]):
        new_board: List = [None] * 64
        i = 0
        for piece in board:
            square = to_square(i)
            if piece in self.stones:
                new_board[square] = self.stones[piece]
            else:
                new_board[square] = NO_STONE
            i += 1
        if self.low_gain_chips:
            # average over the last three IDs for each square for low gain chips
            self.board_history = self.board_history[-2:]
            self.board_history.append(new_board)
            counter: Dict = Counter()
            for board in self.board_history:
                d = {index: value for index, value in enumerate(board)}
                counter.update(d)
            avg_board = []
            for i in range(64):
                stone: str = Counter(counter[i]).most_common(1)[0][0]
                avg_board.append(stone)
            self._process_new_board(avg_board)
        else:
            self._process_new_board(new_board)

    def _process_new_board(self, new_board):
        if self.last_board != new_board:
            self.last_board = new_board
            board, self.reversed = check_reversed(new_board, self.reversed, self.callback)
            self.callback.board_update(to_short_fen(board))

    def translate_occupied_squares(self, board: List[int]):
        self.callback.occupied_squares(board)

    def has_piece_recognition(self, value: bool):
        self.callback.has_piece_recognition(value)


class CalibrationSquare(object):

    def __init__(self, square: int):
        self.square = square
        self.pieceId: Optional[CertaboPiece] = None

    def calibrate_piece(self, callback: CalibrationCallback, received_boards: List[List[CertaboPiece]]):
        calib_piece_count: Dict[CertaboPiece, int] = {}
        for board in received_boards:
            piece = board[self.square]
            if piece in calib_piece_count.keys():
                calib_piece_count[piece] = calib_piece_count[piece] + 1
            else:
                calib_piece_count[piece] = 1
        for p_id, count in calib_piece_count.items():
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
            return "p"
        if 47 < self.square < 56:
            return "P"
        square_to_stone = {
            0: "r",
            7: "r",
            1: "n",
            6: "n",
            2: "b",
            5: "b",
            3: "q",
            BLACK_EXTRA_QUEEN_SQUARE: "q",
            4: "k",
            56: "R",
            63: "R",
            57: "N",
            62: "N",
            58: "B",
            61: "B",
            59: "Q",
            WHITE_EXTRA_QUEEN_SQUARE: "Q",
            60: "K",
        }
        if self.square in square_to_stone:
            return self._no_stone_or(square_to_stone[self.square])
        else:
            return None

    def _no_stone_or(self, stone: str):
        if self.pieceId == NO_PIECE:
            return " "
        else:
            return stone


class CertaboCalibrator(BoardTranslator):

    def __init__(self, callback: CalibrationCallback):
        super().__init__()
        self.callback = callback
        self.calibrationSquares = []
        self.receivedBoards: List = []
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

    def calibrate(self, calib_input: bytearray):
        self.parser.parse(calib_input)

    def translate(self, board: List[CertaboPiece]):
        self.receivedBoards.append(board)
        if len(self.receivedBoards) >= 7 and not self.calibrationComplete:
            if self.check_pieces():
                stones: Dict[CertaboPiece, Optional[str]] = {}
                for square in self.calibrationSquares:
                    stone = square.get_stone()
                    if stone is not None and square.pieceId is not None:
                        stones[square.pieceId] = stone
                self.calibrationComplete = True
                self.callback.calibration_complete(stones)
            elif len(self.receivedBoards) > 15:
                self.receivedBoards = self.receivedBoards[-10:]
                self.callback.calibration_error()

    def check_pieces(self) -> bool:
        all_calibrated = True
        for square in self.calibrationSquares:
            if not square.is_calibrated():
                square.calibrate_piece(self.callback, self.receivedBoards)
                if not square.is_calibrated():
                    all_calibrated = False
        return all_calibrated
