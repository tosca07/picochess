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
import time
import logging
import copy
from math import ceil
import chess  # type: ignore
from utilities import Observable, hms_time, AsyncRepeatingTimer
from dgt.board import Rev2Info
from dgt.api import Event
from dgt.util import TimeMode


logger = logging.getLogger(__name__)


class TimeControl(object):
    """Control the picochess internal clock."""

    def __init__(
        self,
        mode=TimeMode.FIXED,
        fixed=0,
        blitz=0,
        fischer=0,
        moves_to_go=0,
        blitz2=0,
        depth=0,
        node=0,
        internal_time=None,
    ):
        super(TimeControl, self).__init__()
        self.mode = mode
        self.move_time = fixed
        self.game_time = blitz
        self.fisch_inc = fischer
        self.moves_to_go = moves_to_go
        self.moves_to_go_orig = moves_to_go
        self.game_time2 = blitz2
        self.depth = depth
        self.node = node
        self.internal_time = internal_time

        if depth > 0:
            self.mode = TimeMode.FIXED
            self.move_time = 671
            self.depth = depth
            self.node = 0
            self.game_time = 0
            self.fisch_inc = 0
            self.moves_to_go_orig = 0
            self.moves_to_go = 0

        if node > 0:
            self.mode = TimeMode.FIXED
            self.move_time = 671
            self.depth = 0
            self.node = node
            self.game_time = 0
            self.fisch_inc = 0
            self.moves_to_go_orig = 0
            self.moves_to_go = 0

        self.clock_time = {chess.WHITE: 0, chess.BLACK: 0}  # saves the sended clock time for white/black
        self.timer = None
        self.run_color = None
        self.active_color = None
        self.start_time = None

        if internal_time:  # preset the clock (received) time already
            self.clock_time[chess.WHITE] = int(internal_time[chess.WHITE])
            self.clock_time[chess.BLACK] = int(internal_time[chess.BLACK])
        else:
            self.reset()

    def __eq__(self, other):
        chk_mode = self.mode == other.mode
        chk_secs = self.move_time == other.move_time
        chk_mins = self.game_time == other.game_time
        chk_finc = self.fisch_inc == other.fisch_inc
        return chk_mode and chk_secs and chk_mins and chk_finc

    def __hash__(self):
        value = (
            str(self.mode)
            + str(self.move_time)
            + str(self.game_time)
            + str(self.fisch_inc)
            + str(self.moves_to_go_orig)
            + str(self.game_time2)
            + str(self.depth)
            + str(self.node)
        )
        return hash(value)

    def get_parameters(self):
        """Return the state of this class for generating a new instance."""
        return {
            "mode": self.mode,
            "fixed": self.move_time,
            "blitz": self.game_time,
            "fischer": self.fisch_inc,
            "moves_to_go": self.moves_to_go_orig,
            "blitz2": self.game_time2,
            "depth": self.depth,
            "node": self.node,
            "internal_time": self.internal_time,
        }

    def get_list_text(self):
        """Get the clock list text for the current time setting."""
        if self.moves_to_go_orig > 0:
            if self.fisch_inc > 0:
                return "{:2d} {:3d} {:2d} {:2d}".format(
                    self.moves_to_go_orig, self.game_time, self.fisch_inc, self.game_time2
                )
            else:
                return "{:2d} {:3d} {:2d}".format(self.moves_to_go_orig, self.game_time, self.game_time2)
        if self.depth > 0:
            return "{:3d}".format(self.depth)
        if self.node > 0:
            return "{:3d}".format(self.node)
        if self.mode == TimeMode.FIXED:
            return "{:3d}".format(self.move_time)
        if self.mode == TimeMode.BLITZ:
            return "{:3d}".format(self.game_time)
        if self.mode == TimeMode.FISCHER:
            return "{:3d} {:2d}".format(self.game_time, self.fisch_inc)

        return "errtm"

    def reset(self):
        """Reset the clock's times for both players."""
        if self.mode == TimeMode.BLITZ:
            self.clock_time[chess.WHITE] = self.clock_time[chess.BLACK] = self.game_time * 60

        elif self.mode == TimeMode.FISCHER:
            self.clock_time[chess.WHITE] = self.clock_time[chess.BLACK] = self.game_time * 60 + self.fisch_inc

        elif self.mode == TimeMode.FIXED:
            self.clock_time[chess.WHITE] = self.clock_time[chess.BLACK] = self.move_time

        self.internal_time = {
            chess.WHITE: float(self.clock_time[chess.WHITE]),
            chess.BLACK: float(self.clock_time[chess.BLACK]),
        }

        self.active_color = None

        self.moves_to_go = self.moves_to_go_orig

    def _log_time(self):
        time_w, time_b = self.get_internal_time(flip_board=False)
        return hms_time(time_w), hms_time(time_b)

    def get_internal_time(self, flip_board=False):
        """Return the startup time for setting the clock at beginning."""
        i_time = copy.copy(self.internal_time)
        if flip_board:
            i_time[chess.WHITE], i_time[chess.BLACK] = i_time[chess.BLACK], i_time[chess.WHITE]
        return int(i_time[chess.WHITE]), int(i_time[chess.BLACK])

    def set_clock_times(self, white_time: int, black_time: int, moves_to_go: int = 0):
        """Set the times send from the clock."""
        # logger.debug("set clock times w:%s b:%s", hms_time(white_time), hms_time(black_time))
        self.clock_time[chess.WHITE] = white_time
        self.clock_time[chess.BLACK] = black_time
        self.moves_to_go = moves_to_go

    def reset_start_time(self):
        """Set the start time to the current time."""
        self.start_time = time.time()

    async def _out_of_time(self):
        """Fire an OUT_OF_TIME event."""
        self.run_color = None
        if self.mode == TimeMode.FIXED:
            logger.debug('timeout - but in "MoveTime" mode, dont fire event')
        elif self.mode == TimeMode.FISCHER and self.game_time == 0:
            pass  # molli: simulated median move time => no out of time / game end event
        elif self.active_color is not None:
            display_color = "WHITE" if self.active_color == chess.WHITE else "BLACK"
            txt = "current clock time (before subtracting) is %f and color is %s"
            logger.debug(txt, self.internal_time[self.active_color], display_color)
            await Observable.fire(Event.OUT_OF_TIME(color=self.active_color))

    def add_time(self, color):
        """Add the increment value to the color given."""
        assert self.internal_running() is False, "internal clock still running for: %s" % self.run_color
        if self.mode == TimeMode.FISCHER:
            # log times - issue #184
            w_hms, b_hms = self._log_time()
            logger.debug("before internal time w:%s - b:%s", w_hms, b_hms)

            self.internal_time[color] += self.fisch_inc
            self.clock_time[color] += self.fisch_inc

            # log times - issue #184
            w_hms, b_hms = self._log_time()
            logger.debug("after internal time w:%s - b:%s", w_hms, b_hms)

        if self.mode == TimeMode.FIXED:
            self.reset()

    def sub_online_time(self, color, i_dec):
        """Add the increment value to the color given."""
        assert self.internal_running() is False, "internal clock still running for: %s" % self.run_color

        # log times - issue #184
        w_hms, b_hms = self._log_time()
        logger.debug("before internal time w:%s - b:%s", w_hms, b_hms)
        if self.internal_time[color] > i_dec and i_dec > 0:
            self.internal_time[color] -= i_dec
            self.clock_time[color] -= i_dec

        # log times - issue #184
        w_hms, b_hms = self._log_time()
        logger.debug("after internal time w:%s - b:%s", w_hms, b_hms)

    def add_game2(self, color):
        """Add the tournamment game 2 value to the color given."""
        assert self.internal_running() is False, "internal clock still running for: %s" % self.run_color
        if self.moves_to_go_orig > 0:
            # log times - issue #184
            w_hms, b_hms = self._log_time()
            logger.debug("molli: game2 before internal time w:%s - b:%s", w_hms, b_hms)

            self.internal_time[color] += self.game_time2 * 60
            self.clock_time[color] += self.game_time2 * 60

            # log times - issue #184
            w_hms, b_hms = self._log_time()
            logger.debug("molli: game2 after internal time w:%s - b:%s", w_hms, b_hms)

    def start_internal(self, color: chess.Color, loop: asyncio.AbstractEventLoop, log: bool = True):
        """Start the internal clock."""
        if not self.internal_running():
            if self.mode in (TimeMode.BLITZ, TimeMode.FISCHER):
                self.active_color = color
                self.reset_start_time()

            if log:
                w_hms, b_hms = self._log_time()
                logger.debug("start internal time w:%s - b:%s [ign]", w_hms, b_hms)
                logger.debug(
                    "received clock time w:%s - b:%s [use]",
                    hms_time(self.clock_time[chess.WHITE]),
                    hms_time(self.clock_time[chess.BLACK]),
                )
            if not Rev2Info.get_web_only():
                # hack to make picochess work WITH DGT board but WITHOUT a clock attached to it
                # delta should be zero for non-attached / not running clock (with correction for fischer increment)
                deltaBW = self.clock_time[chess.WHITE] - self.clock_time[chess.BLACK]
                if self.active_color == chess.BLACK:
                    deltaBW -= self.fisch_inc
                logger.debug("delta: %s", deltaBW)

                if (
                    self.clock_time[chess.WHITE] >= self.internal_time[chess.WHITE]
                    and self.clock_time[chess.BLACK] >= self.internal_time[chess.BLACK]
                    and deltaBW == 0
                ):
                    logger.info("looks like external clock is not present...not taking over its time now")
                else:
                    w_dir, b_dir = self.get_internal_time(flip_board=False)
                    # molli Avoid strange reset bug to 0
                    if w_dir != self.clock_time[chess.WHITE] and (
                        self.clock_time[chess.WHITE] == 0
                        or (self.clock_time[chess.WHITE] == self.fisch_inc and self.mode == TimeMode.FISCHER)
                        or (self.clock_time[chess.WHITE] == self.game_time and self.mode == TimeMode.BLITZ)
                    ):
                        logger.debug("molli: Difference in white clock time!")
                        self.clock_time[chess.WHITE] = w_dir
                    else:
                        self.internal_time[chess.WHITE] = self.clock_time[chess.WHITE]
                    # molli Avoid strange reset bug to 0
                    if b_dir != self.clock_time[chess.BLACK] and (
                        self.clock_time[chess.BLACK] == 0
                        or (self.clock_time[chess.BLACK] == self.fisch_inc and self.mode == TimeMode.FISCHER)
                        or (self.clock_time[chess.BLACK] == self.game_time and self.mode == TimeMode.BLITZ)
                    ):
                        logger.debug("molli: Difference in black clock time!")
                        self.clock_time[chess.BLACK] = b_dir
                    else:
                        self.internal_time[chess.BLACK] = self.clock_time[chess.BLACK]

            # Only start thread if not already started for same color, and the player has not already lost on time
            if self.internal_time[color] > 0 and self.active_color is not None and self.run_color != self.active_color:
                self.timer = AsyncRepeatingTimer(
                    self.internal_time[color],
                    self._out_of_time,
                    loop=loop,
                    repeating=False,
                )
                self.timer.start()
                logger.debug(
                    "internal timer started - color: %s run: %s active: %s", color, self.run_color, self.active_color
                )
                self.run_color = self.active_color

    def stop_internal(self, log=True):
        """Stop the internal clock."""
        if self.internal_running() and self.mode in (TimeMode.BLITZ, TimeMode.FISCHER):
            if log:
                w_hms, b_hms = self._log_time()
                logger.debug("old internal time w:%s b:%s", w_hms, b_hms)

            if self.timer:
                self.timer.stop()
            else:
                logger.warning("time=%s", self.internal_time)
            used_time = ceil((time.time() - self.start_time) * 10) / 10
            if log:
                logger.debug("used time: %s secs", used_time)
            self.internal_time[self.active_color] -= used_time
            if self.internal_time[self.active_color] < 0:
                self.internal_time[self.active_color] = 0
            if log:
                w_hms, b_hms = self._log_time()
                logger.debug("new internal time w:%s b:%s", w_hms, b_hms)
            self.run_color = self.active_color = None

    def internal_running(self):
        """Return if the internal clock is running."""
        return self.active_color is not None

    def uci(self):
        """Return remaining time for both players in an UCI dict."""
        uci_dict = {}
        if self.depth > 0:
            uci_dict["depth"] = str(self.depth)
        elif self.node > 0:
            uci_dict["nodes"] = str(self.node)
        elif self.mode in (TimeMode.BLITZ, TimeMode.FISCHER):
            uci_dict["wtime"] = str(int(self.internal_time[chess.WHITE] * 1000))
            uci_dict["btime"] = str(int(self.internal_time[chess.BLACK] * 1000))

            if self.mode == TimeMode.FISCHER:
                uci_dict["winc"] = str(self.fisch_inc * 1000)
                uci_dict["binc"] = str(self.fisch_inc * 1000)

            if self.moves_to_go_orig > 0 and self.moves_to_go > 0:
                uci_dict["movestogo"] = self.moves_to_go

        elif self.mode == TimeMode.FIXED:
            uci_dict["movetime"] = str(self.move_time * 1000)

        return uci_dict
