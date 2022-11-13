import typing
from abc import abstractmethod

from dgt.util import ClockIcons


class EBoard(typing.Protocol):
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
        raise NotImplementedError

    @abstractmethod
    def light_square_on_revelation(self, square: str):
        raise NotImplementedError

    @abstractmethod
    def clear_light_on_revelation(self):
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
        raise NotImplementedError

    @abstractmethod
    def set_text_3k(self, text: bytes, beep: int):
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
    def set_reverse(self, flag):
        raise NotImplementedError
