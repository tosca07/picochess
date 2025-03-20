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
#
# Some code copied from https://github.com/domschl/python-mchess/blob/master/mchess/chess_link.py

from typing import List

import json
import logging
import queue
import time
import threading
import typing

from eboard.move_debouncer import MoveDebouncer
from eboard.certabo import command
from eboard.certabo.parser import (
    CalibrationCallback,
    CertaboCalibrator,
    CertaboPiece,
    CertaboBoardMessageParser,
    ParserCallback,
)
from eboard.certabo.led_control import CertaboLedControl
from eboard.certabo.sentio import Sentio
from eboard.certabo.usb_transport import Transport


logger = logging.getLogger(__name__)


class Protocol(ParserCallback, CalibrationCallback):
    """
    This implements the 'Certabo' protocol for Certabo e-boards.

    Communication with the board is asynchronous. Replies from the board are written
    to the python queue (`appqueue`) that is provided during instantiation.

    Every message in `appqueue` is a short json string.
    """

    def __init__(self, appque, name):
        """
        :param appque: a Queue that receive chess board events
        :param name: identifies this protocol
        """
        super().__init__()
        self.piece_recognition = False
        self.name = name
        logger.debug("Certabo starting")
        self.error_condition = False
        self.appque = appque
        self.board_mutex = threading.Lock()
        self.trque = queue.Queue()
        self.trans = None
        self.led_control = None
        self.connected = False
        self.last_fen = None
        self.low_gain = True
        self.calibrator = CertaboCalibrator(self)
        self.calibrated = False
        self.initial_position_received = False  # initial position after calibration is complete
        self.brd_reversed = False
        self.device_in_config = False
        self.debouncer = MoveDebouncer(
            350, lambda fen: self.appque.put({"cmd": "raw_board_position", "fen": fen, "actor": self.name})
        )
        self.thread_active = True
        self.event_thread = threading.Thread(target=self._event_worker_thread)
        self.event_thread.setDaemon(True)
        self.event_thread.start()

        self.config = None
        try:
            self._read_config()
        except Exception as e:
            logger.debug(f"No valid default configuration, starting board-scan: {e}")

        self.parser = CertaboBoardMessageParser(self, self.low_gain)

        while True:
            if not self.device_in_config:
                self._search_board()

            if self.config is None or self.trans is None:
                logger.error("Cannot connect.")
                if self.config is None:
                    self.config = {"low_gain": self.low_gain}
                    self.write_configuration()
                self.error_condition = True
            else:
                self._connect()

            if not self.error_condition:
                break
            self.device_in_config = False
            time.sleep(3)

    def _read_config(self):
        with open("certabo_config.json", "r") as f:
            self.config = json.load(f)
            self.low_gain = self.config.get("low_gain", True)
            if "address" in self.config:
                logger.debug(f"Checking default configuration for board at {self.config['address']}")
                trans = self._open_transport()
                if trans is not None:
                    self.device_in_config = True
                    self.trans = trans

    def _search_board(self):
        tr = Transport(self.trque)
        logger.debug("created obj")
        if tr.is_init():
            logger.debug("Transport loaded.")
            address = tr.search_board()
            if address is not None:
                logger.debug(f"Found board at address {address}")
                self.config = {"address": address, "low_gain": self.low_gain}
                self.trans = tr
                self.write_configuration()
        else:
            logger.warning("Failed to initialize")

    def _connect(self):
        address = self.config["address"]
        logger.debug(f"Valid board available at {address}")
        logger.debug(f"Connecting to Certabo at {address}")
        self.connected = self.trans.open_mt(address)
        if self.connected:
            logger.info(f"Connected to Certabo at {address}")
            self.led_control = CertaboLedControl(self.trans)
            self.sentio = Sentio(self, self.led_control)
            self.error_condition = False
        else:
            self.trans.quit()
            logger.error(f"Connection to Certabo at {address} FAILED.")
            self.error_condition = True

    def quit(self):
        """
        Quit Certabo connection.
        Try to terminate transport threads gracefully.
        """
        if self.trans is not None:
            self.trans.quit()
        self.thread_active = False

    def position_initialized(self):
        """
        Check, if a board position has been received and the Certabo board is online.

        :return: True, if board position has been received
        """
        if self.connected:
            with self.board_mutex:
                fen = self.last_fen
            if fen is not None:
                return True
        return False

    def write_configuration(self):
        try:
            with open("certabo_config.json", "w") as f:
                json.dump(self.config, f, indent=4)
                return True
        except Exception as e:
            logger.error(f"Failed to save default configuration {self.config} to certabo_config.json: {e}")
        return False

    def _event_worker_thread(self):
        """
        The event worker thread is automatically started during __init__.
        """
        logger.debug("Certabo worker thread started.")
        while self.thread_active:
            if not self.trque.empty():
                msg = self.trque.get()
                token = "agent-state: "
                if msg[: len(token)] == token:
                    toks = msg[len(token) :]
                    i = toks.find(" ")
                    if i != -1:
                        state = toks[:i]
                        emsg = toks[i + 1 :]
                    else:
                        state = toks
                        emsg = ""
                    logger.info(f"Agent state of {self.name} changed to {state}, {emsg}")
                    if state == "offline":
                        self.error_condition = True
                    else:
                        self.error_condition = False
                    self.appque.put({"cmd": "agent_state", "state": state, "message": emsg})
                    continue

                if not self.calibrated and self.piece_recognition:
                    self.calibrator.calibrate(msg)
                else:
                    self.parser.parse(msg)
            else:
                time.sleep(0.01)

    def has_piece_recognition(self, piece_recognition: bool):
        self.piece_recognition = True
        if piece_recognition:
            self.calibrate()

    def occupied_squares(self, board: List[int]):
        if self.sentio is not None:
            self.sentio.occupied_squares(board)

    def board_update(self, short_fen: str):
        if not self.initial_position_received and short_fen == "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR":
            self.initial_position_received = True
        if self.initial_position_received:
            # only forward the fen if the initial position has been received at least once
            # to prevent additional queens on the board from changing settings
            self.debouncer.update(short_fen)
        with self.board_mutex:
            self.last_fen = short_fen

    def request_promotion_dialog(self, move: str):
        self.appque.put({"cmd": "request_promotion_dialog", "move": move, "actor": self.name})

    def reversed(self, value: bool):
        self.brd_reversed = value

    def set_led(self, pos):
        """
        Set LEDs according to `position`.

        :param pos: `position` array, field != 0 indicates a LED that should be on
        """
        if self.connected and self.led_control is not None:
            cmd = command.set_leds(pos, self.brd_reversed)
            self.led_control.write_led_command(cmd)

    def set_led_off(self):
        if self.connected and self.led_control is not None:
            self.led_control.write_led_command(command.set_leds_off())

    def uci_move(self, move: str):
        if self.connected:
            self.sentio.uci_move(move)

    def promotion_done(self, uci_move: str):
        if self.connected:
            self.sentio.promotion_done(uci_move)

    def calibrate(self):
        if self.connected:
            self.calibrated = False
            if self.led_control is not None:
                self.led_control.write_led_command(command.set_leds_calibrate())

    def calibration_complete(self, stones: typing.Dict[CertaboPiece, typing.Optional[str]]):
        logger.info("Certabo calibration complete")
        self.parser.update_stones(stones)
        self.calibrated = True
        self.set_led_off()

    def calibration_complete_square(self, square: int):
        # can be used to clear LED of square during calibration, not implemented
        pass

    def calibration_error(self):
        pass

    def _open_transport(self):
        tr = Transport(self.trque)
        if tr.is_init():
            return tr
        else:
            logger.warning("USB transport failed to initialize")
        return None
