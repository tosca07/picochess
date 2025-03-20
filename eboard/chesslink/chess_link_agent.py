# Original copyright:
#
# MIT License
#
# Copyright (c) 2018 Dominik Schlösser
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""Agent for Millennium chess board Chess Genius Exclusive"""
import logging
import time

import eboard.chesslink.chess_link as cl


logger = logging.getLogger(__name__)


class ChessLinkAgent:
    """Hardware board agent implementation"""

    def __init__(self, appque):
        self.name = "ChessLinkAgent"
        self.appque = appque
        self.cl_brd = cl.ChessLink(self.appque, self.name)
        self.init_position = False

        if self.cl_brd.connected is True:
            self.cl_brd.get_version()
            self.cl_brd.set_debounce(4)
            self.cl_brd.get_scan_time_ms()
            self.cl_brd.set_scan_time_ms(100.0)
            self.cl_brd.get_scan_time_ms()
            self.cl_brd.get_position()
        else:
            logger.warning("Connection to ChessLink failed.")
            return

        logger.debug("waiting for board position")
        start = time.time()
        warned = False
        while self.init_position is False:
            if self.cl_brd.error_condition is True:
                logger.info("ChessLink board not available.")
                return
            if time.time() - start > 2 and warned is False:
                warned = True
                logger.info("Searching for ChessLink board...")
            self.init_position = self.cl_brd.position_initialized()
            time.sleep(0.1)

        if self.init_position is True:
            logger.debug("board position received, init ok.")
        else:
            logger.error("no board position received")

    def quit(self):
        self.cl_brd.quit()

    def get_fen(self):
        return self.cl_brd.position_to_fen(self.cl_brd.position)

    def set_led_off(self):
        return self.cl_brd.set_led_off()

    def set_led(self, pos, freq=0x20, ontime1=0x0F, ontime2=0xF0):
        return self.cl_brd.set_led(pos, freq, ontime1, ontime2)
