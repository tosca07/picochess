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

from typing import List, Optional

import chess  # type: ignore

from eboard.certabo.led_control import CertaboLedControl
from eboard.certabo.parser import to_square
from eboard.certabo.parser import ParserCallback
import eboard.certabo.command


class Sentio(object):
    """Sentio handles board states from e-boards, that do not feature piece recognition"""

    def __init__(self, callback: ParserCallback, led_control: CertaboLedControl):
        self.last_occupied_squares: Optional[List[int]] = None
        self.last_engine_move: Optional[chess.Move] = None
        self.capture_piece: Optional[CapturePiece] = None
        self.board = chess.Board()  # board with initial position
        self.callback = callback
        self.led_control = led_control

    def uci_move(self, move: str):
        """Called from the protocol when an engine made a move"""
        try:
            chess_move = chess.Move.from_uci(move)
            if self.board.is_legal(chess_move):
                self.last_engine_move = chess_move
        except ValueError:
            pass

    def promotion_done(self, move: str):
        """Called from the protocol when the user selected a piece for promotion"""
        try:
            chess_move = chess.Move.from_uci(move)
            self._make_move(chess_move)
        except ValueError:
            pass

    def occupied_squares(self, occupied: List[int]):
        """Called when the board receives board data, consisting of the squares that are occupied marked with a 1"""
        if self.last_occupied_squares == occupied:
            return
        self.last_occupied_squares = occupied.copy()
        expected_squares = self._fen_to_squares(self.board.fen())
        occupied_squares = self._occupied_to_squares(occupied)
        if expected_squares == occupied_squares:
            self.callback.board_update(self.board.board_fen())
            self._write_led_command(eboard.certabo.command.set_leds_off())
        elif occupied_squares == self._fen_to_squares(chess.STARTING_FEN):
            self.board = chess.Board()
            self._call_board_update(self.board.board_fen())
            self._write_led_command(eboard.certabo.command.set_leds_off())
        elif not self._take_back_move(occupied_squares):
            self._leds_for_difference(expected_squares, occupied_squares)
            self._check_valid_move(expected_squares, occupied_squares)

    def _leds_for_difference(self, expected_squares, occupied_squares):
        difference = list(expected_squares.symmetric_difference(occupied_squares))
        self._write_led_command(eboard.certabo.command.set_led_squares(difference))

    def _fen_to_squares(self, fen: str):
        return chess.SquareSet(chess.Board(fen).occupied)

    def _occupied_to_squares(self, occupied: List[int]):
        squares = chess.SquareSet()
        for index, is_occupied in enumerate(occupied):
            if is_occupied:
                squares.add(to_square(index))
        return squares

    def _check_valid_move(self, expected_squares, occupied_squares):
        missing = list(expected_squares.difference(occupied_squares))
        extra = list(occupied_squares.difference(expected_squares))
        if not self._non_capture_move(missing, extra):
            self._capture_move(missing, extra)

    def _non_capture_move(self, missing, extra) -> bool:
        if len(missing) == 1 and len(extra) == 1:
            move = chess.Move(missing[0], extra[0])
            if self._make_move(move):
                return True
            else:
                # try promotion move
                move = chess.Move(missing[0], extra[0], promotion=chess.QUEEN)
                if self.board.is_legal(move):
                    self.callback.request_promotion_dialog(move.uci())
                return True
        return False

    def _capture_move(self, missing, extra):
        if len(missing) == 2 and len(extra) == 0:
            if self.board.piece_at(missing[0]).color != self.board.piece_at(missing[1]).color:
                if self.board.piece_at(missing[0]).color == self.board.turn:
                    self.capture_piece = CapturePiece(self.board.piece_at(missing[0]), missing[0], missing[1])
                else:
                    self.capture_piece = CapturePiece(self.board.piece_at(missing[1]), missing[1], missing[0])
            else:
                self.capture_piece = None
        elif self.capture_piece is not None and self._is_possibly_capture(missing, extra):
            move = chess.Move(self.capture_piece.from_square, self.capture_piece.to_square)
            if not self._make_move(move):
                # try promotion move
                move = chess.Move(self.capture_piece.from_square, self.capture_piece.to_square, promotion=chess.QUEEN)
                if self.board.is_legal(move):
                    self.callback.request_promotion_dialog(move.uci())
            self.capture_piece = None
        elif self.capture_piece is not None and self._is_possibly_ep_capture(missing, extra):
            move = chess.Move(self.capture_piece.from_square, extra[0])
            self.capture_piece = None
            self._make_move(move)

    def _is_possibly_capture(self, missing, extra):
        return len(missing) == 1 and len(extra) == 0

    def _is_possibly_ep_capture(self, missing, extra):
        return len(missing) == 2 and len(extra) == 1 and self.capture_piece.piece.piece_type == chess.PAWN

    def _make_move(self, move: chess.Move) -> bool:
        if self.board.is_legal(move):
            self._do_board_move(move)
            return True
        else:
            # sliding piece?
            try:
                prev_move = self.board.pop()
                new_move = chess.Move(prev_move.from_square, move.to_square)
                if self.board.is_legal(new_move):
                    self._do_board_move(new_move)
                    return True
                else:
                    self.board.push(prev_move)
            except IndexError:
                pass
        return False

    def _do_board_move(self, move):
        if self.board.is_castling(move):
            brd = chess.Board(self.board.fen())
            king = brd.remove_piece_at(move.from_square)
            brd.set_piece_at(move.to_square, king)
            self._call_board_update(brd.board_fen())
            self.board.push(move)
        else:
            self.board.push(move)
            self._call_board_update(self.board.board_fen())

    def _take_back_move(self, occupied_squares) -> bool:
        try:
            prev_move = self.board.pop()
            if occupied_squares == self.board.occupied:
                self._call_board_update(self.board.board_fen())
                return True
            else:
                self.board.push(prev_move)
        except IndexError:
            pass
        return False

    def _call_board_update(self, board_fen):
        self.last_engine_move = None
        self.callback.board_update(board_fen)

    def _write_led_command(self, cmd: bytearray):
        if self.last_engine_move is not None:
            cmd = eboard.certabo.command.add_led_squares(
                cmd, [self.last_engine_move.from_square, self.last_engine_move.to_square]
            )
        self.led_control.write_led_command(cmd)


class CapturePiece(object):

    def __init__(self, piece: chess.Piece, from_square: int, to_square: int):
        self.piece = piece
        self.from_square = from_square
        self.to_square = to_square
