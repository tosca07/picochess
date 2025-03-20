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

"""The Chess Link Protocol

```
<V56>
2018-08-31 11:07:31,141 DEBUG ChessLinkBluePy Sending: <b'\xd6\xb5\xb6'>
2018-08-31 11:07:31,212 DEBUG ChessLinkBluePy BLE: Handle: 55, data: b'v\xb01\xb0\xb374'
2018-08-31 11:07:31,212 DEBUG ChessLinkBluePy BLE received [v010374]
2018-08-31 11:07:31,212 DEBUG ChessLinkBluePy bluepy_ble received complete msg: v010374
```s
"""
import time
import logging
import sys
import threading
import queue
import json
import importlib
import copy

import eboard.chesslink.chess_link_protocol as clp
import eboard.chesslink.chess_link_bluepy as tri


# See document:
# `magic-board.md <https://github.com/domschl/python-mchess/blob/master/mchess/magic-board.md>_
# for details on the Chess Link protocol.

logger = logging.getLogger(__name__)


class ChessLink:
    """
    This implements the 'Chess Link' protocol for Millennium Chess Genius Exclusive and
    future boards compatible with that protocol.

    For the details of the Chess Link protocol, please refer to:
    `magic-link.md <https://github.com/domschl/python-mchess/blob/master/mchess/magic-board.md>`_.

    `position` array

    This class refers to chess boards using the `position` 8x8 array. Field values: 1: white pawn,
    2: w-knight, 3: w-bishop, 4: w-rook, 5: w-queen, 6: w-king, 0: empty square, -1; black pawn,
    -2: b-knight, -3: b-bishop, -4: b-rook, -5: b-queen, -6: b-king.

    Communcation with the Chess Link board is asynchronous. Replies from the board are written
    to the python queue (`appqueue`) that is provided during instantiation.

    Every message in `appqueue` is a short json string. Currently implemented are:

    Version::

        {'version': '01.04', 'actor': '<actor-name>'}

    New game detected (board has been set to start position)::

        {'new game', '', 'actor': '<actor-name>', 'orientation': True}

    Transport error::

        {'error': '<error message>', 'actor': '<actor-name>'}

    Board position has changed::

        {'fen': fen, 'actor': '<actor-name>'}

    See remarks on `position2fen()`: move counts, castling are not valid, only the position
    part should be used.

    Valid move on board detected::

        {'move': {'uci': '<uci-format move, e.g. e2e4>', 'fen': '<resulting fen position>',
         'actor': '<actor-name>'}}

    See remarks on `position_to_fen()`: move counts, castling are not valid, only the position
    part should be used.

    In order for the board to detect valid move, a list of possible valid moves has to given
    to the board using `move_from()`. Typically, this list is generated using the python
    module `python_chess`. See chess_link_agent.py for an example.
    """

    def __init__(self, appque, name):
        """
        Constructor, searches, configures and connectors to Chess Link compatible
        Millennium Chess Genius Exclusive or similar boards.

        :param appque: a Queue that receive chess board events
        :param name: identifies this protocol
        """
        self.version = "0.3.0"
        self.board_version = "---"
        self.name = name
        self.figrep = {"int": [1, 2, 3, 4, 5, 6, 0, -1, -2, -3, -4, -5, -6], "ascii": "PNBRQK.pnbrqk"}
        logger.debug("Chess Link starting")
        self.WHITE = 0
        self.BLACK = 1
        self.error_condition = False
        self.turn = self.WHITE
        if sys.version_info[0] < 3:
            logger.critical("FATAL: You need Python 3.x to run this module.")
            exit(-1)

        self.appque = appque
        self.board_mutex = threading.Lock()
        self.is_new_game = False
        self.trans = None
        self.trque = queue.Queue()  # asyncio.Queue()
        self.mill_config = None
        self.connected = False
        self.position = None
        self.reference_position = None
        self.orientation = True
        self.legal_moves = None
        self.found_board = False

        self.thread_active = True
        self.event_thread = threading.Thread(target=self._event_worker_thread, args=(self.trque, self.board_mutex))
        self.event_thread.setDaemon(True)
        self.event_thread.start()

        self.mill_config = None
        try:
            self._read_config()
        except Exception as e:
            logger.debug(f"No valid default configuration, starting board-scan: {e}")
        # These repetitions are caused by monolithic arch of bluepy single-threads.
        reps = 0
        # Should be replaced by async refactor at some point.
        while True:
            if reps > 0:
                logger.warning("Retrying scan and connect after error.")
            if not self.found_board:
                self._search_board()

            if self.mill_config is None or self.trans is None:
                logger.error("No transport available, cannot connect.")
                if self.mill_config is None:
                    self.mill_config = {}
                    self.write_configuration()
                self.error_condition = True
            else:
                self._connect()

            if self.error_condition is False:
                break
            reps += 1
            self.found_board = False
            time.sleep(3)

    def _read_config(self):
        with open("chess_link_config.json", "r") as f:
            self.mill_config = json.load(f)
            if "orientation" not in self.mill_config:
                self.mill_config["orientation"] = True
                self.write_configuration()
            if "protocol_debug" not in self.mill_config:
                self.mill_config["protocol_debug"] = False
                self.write_configuration()
            if "btle_iface" not in self.mill_config:
                self.mill_config["btle_iface"] = 0
                self.write_configuration()
            if "transport" in self.mill_config and "address" in self.mill_config:
                logger.debug(
                    f"Checking default configuration for board via "
                    f"{self.mill_config['transport']} "
                    f"at {self.mill_config['address']}"
                )
                self.orientation = self.mill_config["orientation"]
                trans = self._open_transport(self.mill_config["transport"], self.mill_config["protocol_debug"])
                if trans is not None:
                    if trans.test_board(self.mill_config["address"]) is not None:
                        logger.debug("Default board config used.")
                        self.found_board = True
                        self.trans = trans
                    else:
                        if self.mill_config["autodetect"] is False:
                            logger.warning("Default board not available, autodetect=False.")
                        else:
                            logger.warning("Default board not available, start scan.")

    def _search_board(self):
        if self.mill_config is None or "autodetect" not in self.mill_config or self.mill_config["autodetect"] is True:
            tr = tri.Transport(self.trque)
            logger.debug("created obj")
            if tr.is_init() is True:
                logger.debug(f"Transport {tr.get_name()} loaded.")
                if self.mill_config is not None:
                    btle = self.mill_config["btle_iface"]
                else:
                    btle = 0
                address = tr.search_board(btle)
                if address is not None:
                    logger.debug(f"Found board on transport {tr.get_name()} at address {address}")
                    self.mill_config = {"transport": tr.get_name(), "address": address}
                    self.trans = tr
                    self.write_configuration()
            else:
                logger.warning(f"Transport {tr.get_name()} failed to initialize")

    def _connect(self):
        address = self.mill_config["address"]
        transport = self.mill_config["transport"]
        logger.debug(f"Valid board available on {transport} at {address}")
        logger.debug(f"Connecting to Chess Link via {transport} at {address}")
        self.connected = self.trans.open_mt(address)
        if self.connected:
            logger.info(f"Connected to Chess Link via {transport} at {address}")
        else:
            self.trans.quit()
            logger.error(f"Connection to Chess Link via {transport} at {address} FAILED.")
            self.error_condition = True

    def quit(self):
        """
        Quit ChessLink

        Try to terminate transport threads gracefully.
        """
        if self.trans is not None:
            self.trans.quit()
        self.thread_active = False

    def position_initialized(self):
        """
        Check, if a board position has been received and chess link board is online.

        :return: True, if board position has been received.
        """
        if self.connected is True:
            pos = None
            with self.board_mutex:
                pos = self.position
            if pos is not None:
                return True
        return False

    def write_configuration(self):
        """
        Write the configuration for hardware connection (USB/Bluetooth LE)
        and board orientation to 'chess_link_config.json'

        :return: True on success, False on error
        """
        if "transport" in self.mill_config:
            self.mill_config["orientation"] = self.orientation
        if "btle_iface" not in self.mill_config:
            self.mill_config["btle_iface"] = 0
        if "autodetect" not in self.mill_config:
            self.mill_config["autodetect"] = True
        try:
            with open("chess_link_config.json", "w") as f:
                json.dump(self.mill_config, f, indent=4)
                return True
        except Exception as e:
            logger.error(f"Failed to save default configuration {self.mill_config} " f"to chess_link_config.json: {e}")
        return False

    def _event_worker_thread(self, que, mutex):
        """
        This background thread is started on creation of a ChessLink object.
        It decodes chess link encoded messages and sends json messages to the application.

        The event worker thread is automatically started during __init__.
        """
        logger.debug("Chess Link worker thread started.")
        while self.thread_active:
            if self.trque.empty() is False:
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
                    self.appque.put(
                        {
                            "cmd": "agent_state",
                            "state": state,
                            "message": emsg,
                            "version": f"{self.version} ChessLink: {self.board_version}",
                            "class": "board",
                            "actor": self.name,
                        }
                    )
                    continue

                if len(msg) > 0:
                    if msg[0] == "s":
                        if len(msg) == 67:
                            rp = msg[1:65]
                            val_pos = True
                            position = [[0 for x in range(8)] for y in range(8)]
                            if len(rp) == 64:
                                for y in range(8):
                                    for x in range(8):
                                        c = rp[7 - x + y * 8]
                                        i = self.figrep["ascii"].find(c)
                                        if i == -1:
                                            logger.warning(f"Invalid char in raw position: {c}")
                                            val_pos = False
                                            continue
                                        else:
                                            f = self.figrep["int"][i]
                                            if self.orientation is True:
                                                position[y][x] = f
                                            else:
                                                position[7 - y][7 - x] = f
                            else:
                                val_pos = False
                                logger.warning(f"Error in board position, received {len(rp)}")
                                continue
                        else:
                            val_pos = False
                            logger.error(f"Incomplete board position, {msg}")
                        if val_pos is True:
                            fen = self.position_to_fen(position)
                            sfen = self.short_fen(fen)
                            if sfen == "RNBKQBNR/PPPPPPPP/8/8/8/8/pppppppp/rnbkqbnr":
                                if self.orientation is True:
                                    logger.debug("Cable-left board detected.")
                                    self.orientation = False
                                    self.write_configuration()
                                    position_inv = copy.deepcopy(position)
                                    for x in range(8):
                                        for y in range(8):
                                            position[x][y] = position_inv[7 - x][7 - y]
                                else:
                                    logger.debug("Cable-right board detected.")
                                    self.orientation = True
                                    self.write_configuration()
                                    position_inv = copy.deepcopy(position)
                                    for x in range(8):
                                        for y in range(8):
                                            position[x][y] = position_inv[7 - x][7 - y]
                            fen = self.position_to_fen(position)
                            sfen = self.short_fen(fen)

                            if sfen == "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR":
                                if self.is_new_game is False:
                                    self.is_new_game = True  # XXX changed on cleanup
                                    cmd = {
                                        "cmd": "new_game",
                                        "actor": self.name,
                                        "orientation": self.orientation,
                                    }  # XXX: orientation?!
                                    self.new_game(position)
                                    self.appque.put(cmd)
                            else:
                                self.is_new_game = False

                            with mutex:
                                self.position = copy.deepcopy(position)
                                if self.reference_position is None:
                                    self.reference_position = copy.deepcopy(position)
                            self.appque.put({"cmd": "raw_board_position", "fen": fen, "actor": self.name})
                            self._check_move(position)
                    if msg[0] == "v":
                        logger.debug("got version reply")
                        if len(msg) == 7:
                            version = "{}.{}".format(msg[1] + msg[2], msg[3] + msg[4])
                            self.board_version = version
                        else:
                            logger.warning(f"Bad length of version-reply: {len(version)}")

                    if msg[0] == "l":
                        logger.debug("got led-set reply")
                    if msg[0] == "x":
                        logger.debug("got led-off reply")
                    if msg[0] == "w":
                        logger.debug("got write-register reply")
                        if len(msg) == 7:
                            reg_cont = "{}->{}".format(msg[1] + msg[2], msg[3] + msg[4])
                            logger.debug(f"Register written: {reg_cont}")
                        else:
                            logger.warning(f"Invalid length {len(msg)} for write-register reply")
                    if msg[0] == "r":
                        logger.debug("got read-register reply")
                        if len(msg) == 7:
                            reg_cont = "{}->{}".format(msg[1] + msg[2], msg[3] + msg[4])
                            logger.debug(f"Register content: {reg_cont}")
                        else:
                            logger.warning(f"Invalid length {len(msg)} for read-register reply")

            else:
                time.sleep(0.01)

    def new_game(self, pos):
        """
        Initiate a new game

        :param pos: `position` array of the current position. If the hardware board has
                    currently a different position, all differences are indicated by
                    blinking leds.
        """
        self.reference_position = pos
        self.set_led_off()
        self.legal_moves = None

    def _check_move(self, pos):
        """
        Check, if current change on board is a legal move. If yes, put move into queue
        `appqueue`. This function is called by the background thread. In order for
        it to be called, `move_from` needs to have been called before.
        """
        fen = self.short_fen(self.position_to_fen(pos))
        if self.legal_moves is not None and fen in self.legal_moves:
            self.appque.put({"cmd": "move", "uci": self.legal_moves[fen], "actor": self.name})
            self.legal_moves = None
            self.reference_position = pos
            self.set_led_off()
            return True
        return False

    def move_from(self, fen, legal_moves, color, eval_only=False):
        """
        Register all legal moves possible in current position. Once the legal moves are
        registered, the background thread checks for board changes, and signals a legal
        move using the python queue `appqueue` given during initialization.

        Non-legal changes or incomplete moves will cause the affected fields to blink continously.

        :param fen: current position
        :param legal_moves: dictionary of key:fen value: uci_move (e.g. e2e4). python_chess
                            is the recommended module to calculate all legal moves.
        :param color: color to move (ChessLink.WHITE or ChessLink.BLACK)
        :param eval_only: True: indicate ponder evals
        """
        if self.connected is True:
            if eval_only is False:
                self.legal_moves = legal_moves
                self.turn = color
                self.reference_position = self.fen_to_position(fen)
                with self.board_mutex:
                    self.show_delta(self.reference_position, self.position)
            else:
                eval_position = self.fen_to_position(fen)
                with self.board_mutex:
                    self.show_delta(self.position, eval_position, freq=0x15, ontime1=0x02, ontime2=0x01)
        else:
            logger.warning("Not connected to Chess Link.")

    def show_deltas(self, positions, freq):
        """
        Signal leds to show difference between current position on board, and intended position.
        This is used to signal moves by other agents, or discrepancies with the current position.

        Up to four half-moves can be indicated at sequence of up to 5 positions.

        :param positions: array of `position` arrays. Max length is 5 (4 half-moves incl. start
                          position)
        :param freq: Blink frequency
        """
        if self.connected is True:
            if len(positions) > 5:
                npos = 5
            else:
                npos = len(positions)
            dpos = [[0 for x in range(8)] for y in range(8)]
            for ply in range(npos - 1):
                frame = ply * 2
                for y in range(8):
                    for x in range(8):
                        if positions[ply + 1][y][x] != positions[ply][y][x]:
                            if positions[ply][y][x] != 0:
                                dpos[y][x] |= 1 << (7 - frame)
                            else:
                                dpos[y][x] |= 1 << (7 - (frame + 1))
            self._set_mv_led(dpos, freq)
            time.sleep(0.05)
        else:
            logger.warning("Not connected to Chess Link.")

    def _set_mv_led(self, pos, freq):
        """
        Set the leds on board according to pos array, used by `show_deltas`.
        """
        if self.connected is True:
            leds = [[0 for x in range(9)] for y in range(9)]
            cmd = "L" + clp.hex2(freq)
            for y in range(8):
                for x in range(8):
                    if pos[y][x] != 0:
                        if self.orientation is True:
                            leds[7 - x][y] |= pos[y][x]
                            leds[7 - x + 1][y] |= pos[y][x]
                            leds[7 - x][y + 1] |= pos[y][x]
                            leds[7 - x + 1][y + 1] |= pos[y][x]
                        else:
                            leds[x][7 - y] |= pos[y][x]
                            leds[x + 1][7 - y] |= pos[y][x]
                            leds[x][7 - y + 1] |= pos[y][x]
                            leds[x + 1][7 - y + 1] |= pos[y][x]

            for y in range(9):
                for x in range(9):
                    cmd = cmd + clp.hex2(leds[y][x])
            self.trans.write_mt(cmd)
        else:
            logger.warning("Not connected to Chess Link.")

    def show_delta(self, pos1, pos2, freq=0x20, ontime1=0x0F, ontime2=0xF0):
        """
        Indicate difference between two `position` arrays using the board's leds.

        :param pos1: `position` array of the start position
        :param pos2: `position` array of the target position
        :param freq: blink frequency, see
        `magic-link.md <https://github.com/domschl/python-mchess/blob/master/mchess/magic-board.md>`_.
        :param ontime1: 8-bit value, bits indicate cycles led is on.
        :param ontime2: 8-bit value, bits indicate cycles led is off.
        """
        if self.connected is True:
            dpos = [[0 for x in range(8)] for y in range(8)]
            for y in range(8):
                for x in range(8):
                    if pos2[y][x] != pos1[y][x]:
                        if pos1[y][x] != 0:
                            dpos[y][x] = 1
                        else:
                            dpos[y][x] = 2
            self.set_led(dpos, freq, ontime1, ontime2)
        else:
            logger.warning("Not connected to Chess Link.")

    def set_led(self, pos, freq, ontime1, ontime2):
        """
        Static blinking leds according to `position`.

        :param pos: `position` array, field != 0 indicates a led that should blink.
        :param freq: blink frequency, see
        `magic-link.md <https://github.com/domschl/python-mchess/blob/master/mchess/magic-board.md>`_.
        :param ontime1: 8-bit value, bits indicate cycles led is on.
        :param ontime2: 8-bit value, bits indicate cycles led is off.
        """
        if self.connected is True:
            leds = [[0 for x in range(9)] for y in range(9)]
            cmd = "L" + clp.hex2(freq)
            for y in range(8):
                for x in range(8):
                    if pos[y][x] != 0:
                        if self.orientation is True:
                            leds[7 - x][y] = pos[y][x]
                            leds[7 - x + 1][y] = pos[y][x]
                            leds[7 - x][y + 1] = pos[y][x]
                            leds[7 - x + 1][y + 1] = pos[y][x]
                        else:
                            leds[x][7 - y] = pos[y][x]
                            leds[x + 1][7 - y] = pos[y][x]
                            leds[x][7 - y + 1] = pos[y][x]
                            leds[x + 1][7 - y + 1] = pos[y][x]

            for y in range(9):
                for x in range(9):
                    if leds[y][x] == 0:
                        cmd = cmd + "00"
                    elif leds[y][x] == 1:
                        cmd = cmd + clp.hex2(ontime1)
                    else:
                        cmd = cmd + clp.hex2(ontime2)

            self.trans.write_mt(cmd)
        else:
            logger.warning("Not connected to Chess Link.")

    def set_led_off(self):
        """
        Switch off all leds.
        """
        if self.connected is True:
            self.trans.write_mt("X")
        else:
            logger.warning("Not connected to Chess Link.")

    def get_debounce(self):
        """
        Asynchronuosly request the current debounce setting. The answer will be
        written to the queue `appqueue` given during initialization.

        See `magic-link.md <https://github.com/domschl/python-mchess/blob/master/mchess/magic-board.md>`_.
        """
        if self.connected is True:
            cmd = "R" + clp.hex2(2)
            self.trans.write_mt(cmd)
        else:
            logger.warning("Not connected to Chess Link.")

    def set_debounce(self, count):
        """
        Set the debounce-value. Debouncing helps to prevent random fluke events. Should be tested
        together with different `set_scan_time_ms()` values.

        :param count: 0-4, 0: no debounce, 1-4: 1-4 scan times debounce.
        """
        if self.connected is True:
            cmd = "W02"
            if count < 0 or count > 4:
                logger.error(
                    f'Invalid debounce count {count}, "\
                               "should be 0: no debounce, 1 .. 4: 1-4  scan times debounce'
                )
            else:
                # 3: no debounce, 4: 2 scans debounce, -> 7: 4 scans
                cmd += clp.hex2(count + 3)
                self.trans.write_mt(cmd)
                logger.debug(f"Setting board scan debounce to {count}")
        else:
            logger.warning("Not connected to Chess Link.")

    def get_led_brightness_percent(self):
        """
        Asynchronuosly request the current led brightness setting. The answer will be
        written to the queue `appqueue` given during initialization.

        See `magic-link.md <https://github.com/domschl/python-mchess/blob/master/mchess/magic-board.md>`_.
        """
        if self.connected is True:
            cmd = "R" + clp.hex2(4)
            self.trans.write_mt(cmd)
        else:
            logger.warning("Not connected to Chess Link.")

    def set_led_brightness(self, level=1.0):
        """
        Set the led brighness.

        :param level: 0.0 - 1.0: 0(darkest) up to 1.0(brightest).
        """
        if self.connected is True:
            cmd = "W04"
            if level < 0.0 or level > 1.0:
                logger.error(
                    f'Invalid brightness level {level}, "\
                               "should be between 0(darkest)..1.0(brightest)'
                )
            else:
                ilevel = int(level * 15)
                cmd += clp.hex2(ilevel)
                self.trans.write_mt(cmd)
                logger.debug(f"Setting led brightness to {ilevel} (bri={level})")
        else:
            logger.warning("Not connected to Chess Link.")

    def get_scan_time_ms(self):
        """
        Asynchronuosly request the current scan time setting. The answer will be
        written to the queue `appqueue` given during initialization.

        See `magic-link.md <https://github.com/domschl/python-mchess/blob/master/mchess/magic-board.md>`_.
        """
        if self.connected is True:
            cmd = "R" + clp.hex2(1)
            if self.connected is True:
                self.trans.write_mt(cmd)
            else:
                logger.warning("Not connected to Chess Link.")
        else:
            logger.warning("Not connected to Chess Link.")

    # default is scan every 40.96 ms, 24.4 scans per second.
    def set_scan_time_ms(self, scan_ms=41):
        """
        Set the scan time value. Lower scan times make the board less susceptible to random
        unexpected events and can be used together with `set_debounce()` to prevent random
        fluke events.

        :param scan_ms: 30.72(fastest)-522.24(slowest), scan time in ms. A value around 100ms is
                        recommended, board default is 41ms.
        """
        if self.connected is True:
            cmd = "W01"
            if scan_ms < 2.048 * 15.0 or scan_ms > 255.0 * 2.048:
                logger.error(
                    f"Invalid scan_ms {scan_ms}, shouldbe between 30.72(fastest, "
                    "might not work)..522.24(slowest, about 2 scans per sec))"
                )
            else:
                iscans = int(scan_ms / 2.048)
                if iscans < 15:
                    iscans = 15
                if iscans > 255:
                    iscans = 255
                cmd += clp.hex2(iscans)
                self.trans.write_mt(cmd)
                logger.debug(
                    f"Setting scan_ms intervall to {iscans} -> " "{scan_ms}ms ({1000.0/scan_ms} scans per sec)"
                )
        else:
            logger.warning("Not connected to Chess Link.")

    def short_fen(self, fen):
        """
        Utility-function to cut off all information after the actual position, since the board
        does not know about move counts or castling.

        E.g. `rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1` is transformed to
        `rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR`

        :returns: position-only part of the fen string.
        """
        i = fen.find(" ")
        if i == -1:
            logger.error(f"Invalid fen position <{fen}> in short_fen")
            return None
        else:
            return fen[:i]

    def position_to_fen(self, position):
        """
        Convert a 8x8 `position` array to a fen position. Typically, an 8x8 `position` is generated
        by the Chess Link board, which has no information about the current move, side to move, or
        castling status.

        The returned FEN has always ending `w KQkq - 0 1` after the actual position (only
        rudimentary checks for castling are done)

        :returns: FEN string derived from postion-array
        """
        fen = ""
        blanks = 0
        for y in range(8):
            for x in range(8):
                f = position[7 - y][x]
                c = "?"
                for i in range(len(self.figrep["int"])):
                    if self.figrep["int"][i] == f:
                        c = self.figrep["ascii"][i]
                        break
                if c == "?":
                    logger.error(f"Internal FEN error, could not translation {c} at {y}{x}")
                    return ""
                if c == ".":
                    blanks = blanks + 1
                else:
                    if blanks > 0:
                        fen += str(blanks)
                        blanks = 0
                    fen += c
            if blanks > 0:
                fen += str(blanks)
                blanks = 0
            if y < 7:
                fen += "/"
        fen += " w "
        castle = ""
        if position[0][4] == 6 and position[0][7] == 4:
            castle += "K"
        if position[0][4] == 6 and position[0][0] == 4:
            castle += "Q"
        if position[7][4] == -6 and position[7][7] == -4:
            castle += "k"
        if position[7][4] == -6 and position[7][0] == -4:
            castle += "q"
        if castle == "":
            castle = "-"
        fen += castle + " - 0 1"
        return fen

    def fen_to_position(self, fen):
        """
        Convert a FEN position into an 8x8 `position` array.

        Note that the current implementation of `position` arrays does not maintain move-counts,
        castling stati or any history data.

        :returns: 8x8 `position` array.
        """
        position = [[0 for x in range(8)] for y in range(8)]
        fenp = self.short_fen(fen)
        fi = 0
        for y in range(8):
            x = 0
            while x < 8:
                c = fenp[fi]
                fi += 1
                if c >= "1" and c <= "8":
                    x += int(c)
                    continue
                ci = -99
                for i in range(len(self.figrep["ascii"])):
                    if self.figrep["ascii"][i] == c:
                        ci = self.figrep["int"][i]
                        break
                if ci == -99:
                    logger.error(f"Internal FEN2 error decoding {c} at {y}{x}")
                    return []
                position[7 - y][x] = ci
                x += 1
            if y < 7 and fenp[fi] != "/":
                logger.error(f"Illegal fen: missing '/' {y}{x}: {fenp[fi]}[{fi}]")
                return []
            fi += 1
        return position

    def _open_transport(self, transport, protocol_debug):
        """
        Internal function to load transport modules (USB or bluetooth)
        """
        try:
            tri = importlib.import_module(transport)
            tr = tri.Transport(self.trque, protocol_debug)
            if tr.is_init() is True:
                logger.debug(f"Transport {tr.get_name()} loaded.")
                return tr
            else:
                logger.warning(f"Transport {tr.get_name()} failed to initialize")
        except Exception as e:
            logger.warning(f"Internal error {e}, import of {transport} failed, " "transport not available.")
        return None

    def reset(self):
        """
        Reset Chess Link module.
        """
        if self.connected is True:
            self.trans.write_mt("T")
            logger.warning("Chess Link reset initiated, will take 3 secs.")
        else:
            logger.warning("Not connected to Chess Link, can't reset.")
        return "?"

    def get_version(self):
        """
        Asynchronuosly request the Chess Link version number. The answer will be
        written to the queue `appqueue` given during initialization.
        """
        if self.connected is True:
            self.trans.write_mt("V")
        else:
            logger.warning("Not connected to Chess Link, can't get version.")
        return "?"

    def get_position(self):
        """
        Asynchronuosly request the Chess Link board position. The answer will be
        written to the queue `appqueue` given during initialization.

        By default, the Chess Link board sends a position to `appqueue` on all changes
        to the board position, so explicit calls to `get_position()` should not be required
        most of the times.
        """
        if self.connected is True:
            self.trans.write_mt("S")
        else:
            logger.warning("Not connected to Chess Link, can't get position.")
        return "?"

    def set_orientation(self, orientation):
        """
        Set the Chess Link board orientation.

        Setting the orientation is only necessary, when autodecection cannot work,
        because the board has never been set to a start position.

        :param orientation: True: cable right, False: cable left.
        """
        if orientation != self.orientation:
            self.orientation = orientation
            logger.info("Swapping board position")
            with self.board_mutex:
                pos = copy.deepcopy(self.position)
                for y in range(8):
                    for x in range(8):
                        pos[y][x] = self.position[7 - y][7 - x]
                self.position = pos
        self.write_configuration()

    def get_orientation(self):
        """
        ChessLink tries to autodetect the orientation of the board by looking for
        initial start positions.

        If the board has never been set to the initial start position, the orientation
        must be set using `set_orientation()`.
        """
        return self.orientation
