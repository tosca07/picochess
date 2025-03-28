# Copyright (C) 2013-2018 Jean-Francois Romang (jromang@posteo.de)
#                         Shivkumar Shivaji ()
#                         Jürgen Précour (LocutusOfPenguin@posteo.de)
#
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

import asyncio
import logging
from threading import Lock
from utilities import hms_time
from dgt.iface import DgtIface
from dgt.util import ClockIcons, ClockSide
from eboard.eboard import EBoard

from pgn import ModeInfo

logger = logging.getLogger(__name__)


class DgtHw(DgtIface):
    """Handle the DgtXL/3000 communication."""

    def __init__(self, dgtboard: EBoard, loop: asyncio.AbstractEventLoop):
        super(DgtHw, self).__init__(dgtboard, loop)

        self.lib_lock = Lock()

    def _display_on_dgt_xl(self, text: str, beep=False, left_icons=ClockIcons.NONE, right_icons=ClockIcons.NONE):
        text = text.ljust(6)
        if len(text) > 6:
            logger.warning("(ser) clock message too long [%s]", text)
        logger.debug("[%s]", text)
        with self.lib_lock:
            res = self.dgtboard.set_text_xl(text, 0x03 if beep else 0x00, left_icons, right_icons)
            if not res:
                logger.warning("SetText() returned error %i", res)
            return res

    def _display_on_dgt_3000(self, text: str, beep=False):
        text = text.ljust(8)
        if len(text) > 8:
            logger.warning("(ser) clock message too long [%s]", text)
        logger.debug("[%s]", text)
        with self.lib_lock:
            res = self.dgtboard.set_text_3k(bytes(text, "utf-8"), 0x03 if beep else 0x00)
            if not res:
                logger.warning("SetText() returned error %i", res)
            return res

    def _display_on_rev2_pi(self, text: str, beep=False):
        text = text.ljust(11)
        if len(text) > 11:
            logger.warning("(rev) clock message too long [%s]", text)
        logger.debug("[%s]", text)
        with self.lib_lock:
            res = self.dgtboard.set_text_rp(bytes(text, "utf-8"), 0x03 if beep else 0x00)
            if not res:
                logger.warning("SetText() returned error %i", res)
            return res

    def display_text_on_clock(self, message):
        """Display a text on the dgtxl/3k/rev2."""
        is_new_rev2 = self.dgtboard.is_revelation and self.dgtboard.enable_revelation_pi
        if is_new_rev2:
            text = message.large_text
        else:
            text = message.medium_text if self.enable_dgt3000 else message.small_text
        if self.get_name() not in message.devs:
            logger.debug("ignored %s - devs: %s", text, message.devs)
            return True

        if is_new_rev2:
            return self._display_on_rev2_pi(text, message.beep)
        else:
            if self.enable_dgt3000:
                return self._display_on_dgt_3000(text, message.beep)
            else:
                left_icons = message.ld if hasattr(message, "ld") else ClockIcons.NONE
                right_icons = message.rd if hasattr(message, "rd") else ClockIcons.NONE
                return self._display_on_dgt_xl(text, message.beep, left_icons, right_icons)

    def display_move_on_clock(self, message):
        """Display a move on the dgtxl/3k/rev2."""
        is_new_rev2 = self.dgtboard.is_revelation and self.dgtboard.enable_revelation_pi
        if self.enable_dgt3000 or is_new_rev2:
            bit_board, text = self.get_san(message)
            if is_new_rev2:
                points = "..." if message.side == ClockSide.RIGHT else "."
                if len(text) > 5:
                    points = "."
                text = "{:3d}{:s}{:s}".format(bit_board.fullmove_number, points, text)
        else:
            text = message.move.uci()
            if message.side == ClockSide.RIGHT:
                text = text[:2].rjust(3) + text[2:].rjust(3)
            else:
                text = text[:2].ljust(3) + text[2:].ljust(3)
        if self.get_name() not in message.devs:
            logger.debug("ignored %s - devs: %s", text, message.devs)
            return True
        if is_new_rev2:
            return self._display_on_rev2_pi(text, message.beep)
        else:
            if self.enable_dgt3000:
                return self._display_on_dgt_3000(text, message.beep)
            else:
                left_icons = message.ld if hasattr(message, "ld") else ClockIcons.NONE
                right_icons = message.rd if hasattr(message, "rd") else ClockIcons.NONE
                return self._display_on_dgt_xl(text, message.beep, left_icons, right_icons)

    def display_time_on_clock(self, message):
        """Display the time on the dgtxl/3k/rev2."""
        if self.get_name() not in message.devs:
            logger.debug("ignored endText - devs: %s", message.devs)
            return True
        if self.side_running != ClockSide.NONE or message.force:
            with self.lib_lock:
                if self.dgtboard.l_time >= 3600 * 10 or self.dgtboard.r_time >= 3600 * 10:
                    logger.debug("time values not set - abort function")
                    return False
                else:
                    if self.dgtboard.in_settime:
                        logger.debug("(ser) clock still in set mode - abort function")
                        return False
                    return self.dgtboard.end_text()
        else:
            logger.debug("(ser) clock isnt running - no need for endText")
            return True

    def flip_square(self, square):
        file_map = {"a": "h", "b": "g", "c": "f", "d": "e", "e": "d", "f": "c", "g": "b", "h": "a"}
        rank_map = {"1": "8", "2": "7", "3": "6", "4": "5", "5": "4", "6": "3", "7": "2", "8": "1"}
        # Reverse the file and rank of the source and destination squares
        flipped_square = file_map[square[0]] + rank_map[square[1]]
        return flipped_square

    def flip_move(self, move):
        # Extract source and destination squares from UCI move
        source = move[:2]
        dest = move[2:]
        # Reverse the file and rank of the source and destination squares
        flipped_source = self.flip_square(source)
        flipped_dest = self.flip_square(dest)
        # Combine the flipped source and destination squares to create the flipped UCI move
        flipped_move = flipped_source + flipped_dest
        return flipped_move

    def light_squares_on_revelation(self, uci_move: str):
        """Light the Rev2 leds."""

        if ModeInfo.get_flipped_board():
            print("flip the move!")
            new_move = self.flip_move(uci_move)
        else:
            new_move = uci_move

        self.dgtboard.light_squares_on_revelation(new_move)
        return True

    def light_square_on_revelation(self, square: str):
        """Light the Rev2 led."""

        if ModeInfo.get_flipped_board():
            new_square = self.flip_square(square)
        else:
            new_square = square
        self.dgtboard.light_square_on_revelation(new_square)
        return True

    def clear_light_on_revelation(self):
        """Clear the Rev2 leds."""
        self.dgtboard.clear_light_on_revelation()
        return True

    async def stop_clock(self, devs: set):
        """Stop the dgtxl/3k."""
        if self.get_name() not in devs:
            logger.debug("ignored stopClock - devs: %s", devs)
            return True
        logger.debug(
            "(%s) clock sending stop time to clock l:%s r:%s",
            ",".join(devs),
            hms_time(self.dgtboard.l_time),
            hms_time(self.dgtboard.r_time),
        )
        return self._resume_clock(ClockSide.NONE)

    def _resume_clock(self, side: ClockSide):
        if self.dgtboard.l_time >= 3600 * 10 or self.dgtboard.r_time >= 3600 * 10:
            logger.debug("time values not set - abort function")
            return False

        l_run = r_run = 0
        if ModeInfo.get_clock_side() == "left":
            if side == ClockSide.LEFT:
                l_run = 1
            if side == ClockSide.RIGHT:
                r_run = 1
        else:
            if side == ClockSide.LEFT:
                r_run = 1
            if side == ClockSide.RIGHT:
                l_run = 1
        with self.lib_lock:
            l_hms = hms_time(self.dgtboard.l_time)
            r_hms = hms_time(self.dgtboard.r_time)
            res = self.dgtboard.set_and_run(l_run, l_hms[0], l_hms[1], l_hms[2], r_run, r_hms[0], r_hms[1], r_hms[2])
            if not res:
                logger.warning("finally failed %i", res)
                return False
            else:
                self.side_running = side
            if not self.dgtboard.disable_end:
                res = self.dgtboard.end_text()  # this is needed for some(!) clocks
            self.dgtboard.in_settime = False  # @todo should be set on ACK (see: DgtBoard) not here
            return res

    async def start_clock(self, side: ClockSide, devs: set):
        """Start the dgtxl/3k."""
        if self.get_name() not in devs:
            logger.debug("ignored startClock - devs: %s", devs)
            return True
        logger.debug(
            "(%s) clock sending start time to clock l:%s r:%s",
            ",".join(devs),
            hms_time(self.dgtboard.l_time),
            hms_time(self.dgtboard.r_time),
        )
        return self._resume_clock(side)

    def set_clock(self, time_left: int, time_right: int, devs: set):
        """Start the dgtxl/3k."""
        if self.get_name() not in devs:
            logger.debug("ignored setClock - devs: %s", devs)
            return True
        logger.debug(
            "(%s) clock received last time from clock l:%s r:%s [ign]",
            ",".join(devs),
            hms_time(self.dgtboard.l_time),
            hms_time(self.dgtboard.r_time),
        )
        logger.debug(
            "(%s) clock sending set time to clock l:%s r:%s [use]",
            ",".join(devs),
            hms_time(time_left),
            hms_time(time_right),
        )
        self.dgtboard.in_settime = True  # it will return to false as soon SetAndRun ack received
        if ModeInfo.get_clock_side() == "left":
            self.dgtboard.l_time = time_left
            self.dgtboard.r_time = time_right
        else:
            self.dgtboard.r_time = time_left
            self.dgtboard.l_time = time_right
        return True

    def promotion_done(self, uci_move: str):
        self.dgtboard.promotion_done(uci_move)

    def get_name(self):
        """Get name."""
        return "ser"
