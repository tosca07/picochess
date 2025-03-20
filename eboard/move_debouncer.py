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

from typing import Callable, List, Optional
from threading import Timer

import chess  # type: ignore


class MoveDebouncer(object):
    """
    MoveDebouncer debounces FENs received from an e-board if a move is detected and the move is extendable.
    A move is extendable if the piece of the current move could move further to another square.
    For example, the move pawn to e3 in the starting position is extendable because the pawn could move to e4 instead.
    The pawn move to e4 cannot be extended since the pawn could not move on in one move.
    Since this class has no game information, king moves are potentially always extendable, even if the king has already
    castled.

    TODO: Consider direction. The current implementation does not check the direction of the moving piece,
          that is, even if there are no more squares available in the direction in which a piece is being moved,
          if there are other moves available for this piece in other directions, the move is currently determined to be
          extendable.
    """

    def __init__(self, debounce_time_millis: int, callback: Callable[[str], None]):
        """
        :param debounce_time_millis: wait time in milliseconds until the callback is called
        :param callback: callback to be called after the debounce time passes or if the move is not extendable
        """
        self.debounce_time_millis = debounce_time_millis
        self.callback = callback
        self.previous_fen = None
        self.timer: Optional[Timer] = None
        self.previous_fens: List[str] = []

    def update(self, short_fen: str):
        """
        Update the debouncer with a new short fen.

        :param short_fen: short fen to forward to the callback
        """
        if self.debounce_time_millis <= 0:
            self.callback(short_fen)
            return
        if self.timer is not None:
            self.timer.cancel()
        if self._shall_start_timer(short_fen):
            self.timer = Timer(self.debounce_time_millis / 1000, self.callback, [short_fen])
            self.timer.start()
        else:
            self.callback(short_fen)
        self.previous_fens.append(short_fen)

    def stop(self):
        if self.timer is not None:
            self.timer.cancel()

    def _shall_start_timer(self, short_fen: str):
        self.previous_fens = self.previous_fens[len(self.previous_fens) - 2 :]  # keep two entries max
        for previous in self.previous_fens:
            if self._is_move_extendable(previous, short_fen):
                self.previous_fens = []
                return True
        return False

    def _is_move_extendable(self, previous_fen: str, fen: str):
        board = self._board_from_fen(previous_fen, "b")
        legal_moves = board.legal_moves
        legal_fens = self._legal_fens(board, legal_moves)
        result = False
        if fen in legal_fens:
            result = self._is_extendable(board, legal_moves, legal_fens.index(fen))
        else:
            board = self._board_from_fen(previous_fen, "w")
            legal_moves = board.legal_moves
            legal_fens = self._legal_fens(board, legal_moves)
            if fen in legal_fens:
                result = self._is_extendable(board, legal_moves, legal_fens.index(fen))
        return result

    def _is_extendable(self, board: chess.Board, legal_moves: list, index: int):
        move = list(legal_moves)[index]
        if board.piece_type_at(move.from_square) == chess.KNIGHT:
            return False
        for m in legal_moves:
            if m.from_square == move.from_square and m.to_square != move.to_square:
                return True
        return False

    def _board_from_fen(self, board_fen: str, color: str):
        return chess.Board(board_fen + " " + color + " - - 0 1")

    def _legal_fens(self, b: chess.Board, legal_moves: list):
        board = b.copy()
        fens = []
        for move in legal_moves:
            board.push(move)
            fens.append(board.board_fen())
            board.pop()
        return fens
