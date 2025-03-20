from typing_extensions import Protocol
from abc import abstractmethod
from enum import Enum

from dgt.util import ClockIcons


class EBoard(Protocol):
    """Protocol for e-board implementations"""

    is_pi: bool = False
    is_revelation: bool = True
    enable_revelation_pi: bool = True
    l_time: int = 0
    r_time: int = 0
    disable_end: bool = True
    in_settime: bool = False  # this is true between set_clock and clock_start => use set values instead of clock
    low_time: bool = False  # This is set from picochess.py and used to limit the field timer

    @abstractmethod
    def light_squares_on_revelation(self, uci_move: str):
        """Light LEDs for the given uci_move."""
        raise NotImplementedError

    @abstractmethod
    def light_square_on_revelation(self, square: str):
        """Light LEDs on the given square."""
        raise NotImplementedError

    @abstractmethod
    def clear_light_on_revelation(self):
        """Clear the LEDs."""
        raise NotImplementedError

    @abstractmethod
    def run(self):
        raise NotImplementedError

    @abstractmethod
    def set_text_rp(self, text: bytes, beep: int):
        """Display a text on a Pi enabled Rev2."""
        raise NotImplementedError

    @abstractmethod
    def set_text_xl(self, text: str, beep: int, left_icons=ClockIcons.NONE, right_icons=ClockIcons.NONE):
        """Display a text on a XL clock."""
        raise NotImplementedError

    @abstractmethod
    def set_text_3k(self, text: bytes, beep: int):
        """Display a text on a 3000 Clock."""
        raise NotImplementedError

    @abstractmethod
    def set_and_run(self, lr: int, lh: int, lm: int, ls: int, rr: int, rh: int, rm: int, rs: int):
        """Set the clock with times and let it run."""
        raise NotImplementedError

    @abstractmethod
    def end_text(self):
        """Return the clock display to time display."""
        raise NotImplementedError

    @abstractmethod
    def promotion_done(self, uci_move: str):
        """Called when the user selected a piece for promotion."""
        raise NotImplementedError


class Battery(Enum):
    CHARGING = 0
    DISCHARGING = 1
    LOW = 2
    EXHAUSTED = 3


def to_battery(percent, status):
    battery = Battery.DISCHARGING
    if status == 1:
        battery = Battery.CHARGING
    value = max(0, min(100, percent))
    if value < 5:
        battery = Battery.EXHAUSTED
    elif value < 10:
        battery = Battery.LOW
    return value, battery


def to_short_fen(board) -> str:
    """
    Convert a board to a short FEN representation, e.g. 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR'
    :param board: the board to convert
    :return: a short fen representation
    """
    fen = ""
    for row_index, row in enumerate(range(7, -1, -1)):
        blanks = 0
        for col_index, col in enumerate(range(8)):
            if board[row * 8 + col] == " ":
                blanks += 1
                if col_index == 7 and blanks > 0:
                    fen += str(blanks)
            else:
                if blanks > 0:
                    fen += str(blanks)
                blanks = 0
                fen += board[row * 8 + col]
        if row_index != 7:
            fen += "/"
    return fen


def get_upper_4_bits(b):
    return (b & 0xF0) >> 4


def get_lower_4_bits(b):
    return b & 0x0F


def check_reversed(brd, is_reversed, callback):
    board = brd.copy()
    w_count_lower_half, b_count_lower_half = _piece_count(board, range(32))
    w_count_upper_half, b_count_upper_half = _piece_count(board, range(32, 64))
    if is_reversed and w_count_lower_half > 10 and b_count_upper_half > 10:
        is_reversed = False
        callback.reversed(is_reversed)
    elif not is_reversed and w_count_upper_half > 10 and b_count_lower_half > 10:
        is_reversed = True
        callback.reversed(is_reversed)
    if is_reversed:
        board.reverse()
    return board, is_reversed


def _piece_count(board, board_half):
    w_count = 0
    b_count = 0
    for i in board_half:
        if board[i] != " ":
            if board[i] < "Z":
                w_count += 1
            else:
                b_count += 1
    return w_count, b_count
