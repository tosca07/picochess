# Copyright (C) 2013-2014 Jean-Francois Romang (jromang@posteo.de)
#                         Shivkumar Shivaji ()
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

import logging
import queue

import threading
from utilities import *


class DGTInterface(Display, HardwareDisplay, threading.Thread):
    def __init__(self, device, enable_board_leds, enable_dgt_3000, disable_dgt_clock_beep):
        super(DGTInterface, self).__init__(device, enable_dgt_3000)

        self.enable_dgt_3000 = enable_dgt_3000
        self.enable_board_leds = enable_board_leds
        self.disable_dgt_clock_beep = disable_dgt_clock_beep
        self.displayed_text = None  # The current clock display or None if in ClockNRun mode or unknown text
        # self.dgt_queue = queue.Queue()

    def display_text_on_clock(self, text, dgt_xl_text=None, beep=BeepLevel.CONFIG, force=True):
        raise NotImplementedError()

    def display_move_on_clock(self, move, fen, beep=BeepLevel.CONFIG, force=True):
        raise NotImplementedError()

    def light_squares_revelation_board(self, squares):
        raise NotImplementedError()

    def clear_light_revelation_board(self):
        raise NotImplementedError()

    def stop_clock(self):
        raise NotImplementedError()

    def start_clock(self, time_left, time_right, side):
        raise NotImplementedError()

    def run(self):
        while True:
            # Check if we have something to display
            try:
                message = self.dgt_queue.get_nowait()
                # if type(message).__name__ == 'Dgt':
                logging.debug("Read dgt from queue: %s", message)
                for case in switch(message):
                    if case(Dgt.DISPLAY_MOVE):
                        self.display_move_on_clock(message.move, message.fen, message.beep)
                        break
                    if case(Dgt.DISPLAY_TEXT):
                        self.display_text_on_clock(message.text, message.xl, message.beep)
                        break
                    if case(Dgt.LIGHT_CLEAR):
                        self.clear_light_revelation_board()
                        break
                    if case(Dgt.LIGHT_SQUARES):
                        self.light_squares_revelation_board(message.squares)
                        break
                    if case(Dgt.CLOCK_STOP):
                        self.stop_clock()
                        break
                    if case(Dgt.CLOCK_START):
                        self.start_clock(message.time_left, message.time_right, message.side)
                        break
                    if case():  # Default
                        pass
            except queue.Empty:
                pass
