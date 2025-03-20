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

"""
ChessLink transport implementation for USB connections.
"""
import logging
import threading
import time

import eboard.chesslink.chess_link_protocol as clp

try:
    import serial  # type: ignore
    import serial.tools.list_ports  # type: ignore

    usb_support = True
except ImportError:
    usb_support = False

logger = logging.getLogger(__name__)


class Transport:
    """
    ChessLink transport implementation for USB connections.

    This class does automatic hardware detection of any ChessLink board connected
    via USB and support Linux, macOS and Windows.

    This transport uses an asynchronous background thread for hardware communcation.
    All replies are written to the python queue `que` given during initialization.
    """

    def __init__(self, que, protocol_dbg=False):
        """
        Initialize with python queue for event handling.
        Events are strings conforming to the ChessLink protocol as documented in
        `magic-link.md <https://github.com/domschl/python-mchess/blob/master/mchess/magic-board.md>`_.

        :param que: Python queue that will receive events from chess board.
        :param protocol_dbg: True: byte-level ChessLink protocol debug messages
        """
        if usb_support is False:
            logger.error("Cannot communicate: PySerial module not installed.")
            self.init = False
            return
        self.que = que  # asyncio.Queue()
        self.init = True
        logger.debug("USB init ok")
        self.protocol_debug = protocol_dbg
        self.last_agent_state = None
        self.error_state = False
        self.thread_active = False
        self.event_thread = None
        self.usb_dev = None
        self.uport = None

    def quit(self):
        """
        Initiate worker-thread stop
        """
        self.thread_active = False

    def search_board(self, iface=None):
        """
        Search for ChessLink connections on all USB ports.

        :param iface: not used for USB.
        :returns: Name of the port with a ChessLink board, None on failure.
        """
        logger.info("Searching for ChessLink boards...")
        logger.info("Note: search can be disabled in < chess_link_config.json >" ' by setting {"autodetect": false}')
        port = None
        ports = self.usb_port_search()
        if len(ports) > 0:
            if len(ports) > 1:
                logger.warning(f"Found {len(ports)} Millennium boards, using first found.")
            port = ports[0]
            logger.info(f"Autodetected Millennium board at USB port: {port}")
        return port

    def test_board(self, port):
        """
        Test an usb port for correct answer on get version command.

        :returns: Version string on ok, None on failure.
        """
        logger.debug(f"Testing port: {port}")
        try:
            self.usb_dev = serial.Serial(port, 38400, timeout=2, write_timeout=1)
            self.usb_dev.dtr = 0
            self.write_mt("V")
            version = self.usb_read_synchr(self.usb_dev, "v", 7)
            if len(version) != 7:
                self.usb_dev.close()
                logger.debug(f"Message length {len(version)} instead of 7")
                return None
            if version[0] != "v":
                logger.debug(f"Unexpected reply {version}")
                self.usb_dev.close()
                return None
            verstring = f"{version[1] + version[2]}.{version[3] + version[4]}"
            logger.debug(f"Millennium {verstring} at {port}")
            self.usb_dev.close()
            return verstring
        except (OSError, serial.SerialException) as e:
            logger.debug(f"Board detection on {port} resulted in error {e}")
        try:
            self.usb_dev.close()
        except Exception:
            pass
        return None

    def usb_port_check(self, port):
        """
        Check usb port for valid ChessLink connection

        :returns: True on success, False on failure.
        """
        logger.debug(f"Testing port: {port}")
        try:
            s = serial.Serial(port, 38400)
            s.close()
            return True
        except (OSError, serial.SerialException) as e:
            logger.debug(f"Can't open port {port}, {e}")
            return False

    def usb_port_search(self):
        """
        Get a list of all usb ports that have a connected ChessLink board.

        :returns: array of usb port names with valid ChessLink boards, an empty array
                  if none is found.
        """
        ports = list([port.device for port in serial.tools.list_ports.comports(True)])
        vports = []
        for port in ports:
            if self.usb_port_check(port):
                version = self.test_board(port)
                if version is not None:
                    logger.debug(f"Found board at: {port}")
                    vports.append(port)
                    break  # only one port necessary
        return vports

    def write_mt(self, msg):
        """
        Encode and write a message to ChessLink.

        :param msg: Message string. Parity will be added, and block CRC appended.
        """
        msg = clp.add_block_crc(msg)
        bts = []
        for c in msg:
            bo = clp.add_odd_par(c)
            bts.append(bo)
        try:
            if self.protocol_debug is True:
                logger.debug(f"Trying write <{bts}>")
            self.usb_dev.write(bts)
            self.usb_dev.flush()
        except Exception as e:
            logger.error(f"Failed to write {msg}: {e}")
            self.error_state = True
            return False
        if self.protocol_debug is True:
            logger.debug(f"Written '{msg}' as < {bts} > ok")
        return True

    def usb_read_synchr(self, usbdev, cmd, num):
        """
        Synchronous reads for initial hardware detection.
        """
        rep = []
        start = False
        while start is False:
            try:
                b = chr(ord(usbdev.read()) & 127)
            except Exception as e:
                logger.debug(f"USB read failed: {e}")
                return []
            if b == cmd:
                rep.append(b)
                start = True
        for _ in range(num - 1):
            try:
                b = chr(ord(usbdev.read()) & 127)
                rep.append(b)
            except Exception as e:
                logger.error(f"Read error {e}")
                break
        if clp.check_block_crc(rep) is False:
            return []
        return rep

    def agent_state(self, que, state, msg):
        if state != self.last_agent_state:
            self.last_agent_state = state
            que.put("agent-state: " + state + " " + msg)

    def open_mt(self, port):
        """
        Open an usb port to a connected ChessLink board.

        :returns: True on success.
        """
        self.uport = port
        try:
            self.usb_dev = serial.Serial(port, 38400, timeout=0.1)
            self.usb_dev.dtr = 0
        except Exception as e:
            emsg = f"USB cannot open port {port}, {e}"
            logger.error(emsg)
            self.agent_state(self.que, "offline", emsg)
            return False
        logger.debug(f"USB port {port} open")
        self.thread_active = True
        self.event_thread = threading.Thread(target=self.event_worker_thread, args=(self.que,))
        self.event_thread.setDaemon(True)
        self.event_thread.start()
        return True

    def event_worker_thread(self, que):
        """
        Background thread that sends data received via usb to the queue `que`.
        """
        logger.debug("USB worker thread started.")
        cmd_started = False
        cmd_size = 0
        cmd = ""
        self.agent_state(self.que, "online", f"Connected to {self.uport}")
        self.error_state = False
        posted = False
        while self.thread_active:
            while self.error_state is True:
                time.sleep(1.0)
                try:
                    self.usb_dev.close()
                except Exception as e:
                    logger.debug(f"Failed to close usb: {e}")
                try:
                    self.usb_dev = serial.Serial(self.uport, 38400, timeout=0.1)
                    self.usb_dev.dtr = 0
                    self.agent_state(self.que, "online", f"Reconnected to {self.uport}")
                    self.error_state = False
                    posted = False
                    break
                except Exception as e:
                    if posted is False:
                        emsg = f"Failed to reconnect to {self.uport}, {e}"
                        logger.warning(emsg)
                        self.agent_state(self.que, "offline", emsg)
                        posted = True

            b = ""
            try:
                if cmd_started is False:
                    self.usb_dev.timeout = None
                else:
                    self.usb_dev.timeout = 0.2
                by = self.usb_dev.read()
                if len(by) > 0:
                    b = chr(ord(by) & 127)
                else:
                    continue
            except Exception as e:
                if len(cmd) > 0:
                    logger.debug(f"USB command '{cmd[0]}' interrupted: {e}")
                time.sleep(0.1)
                cmd_started = False
                cmd_size = 0
                cmd = ""
                self.error_state = True
                continue
            if len(b) > 0:
                if cmd_started is False:
                    if b in clp.protocol_replies:
                        cmd_started = True
                        cmd_size = clp.protocol_replies[b]
                        cmd = b
                        cmd_size -= 1
                else:
                    cmd += b
                    cmd_size -= 1
                    if cmd_size == 0:
                        cmd_started = False
                        cmd_size = 0
                        if self.protocol_debug is True:
                            logger.debug(f"USB received cmd: {cmd}")
                        if clp.check_block_crc(cmd):
                            que.put(cmd)
                        cmd = ""

    def get_name(self):
        """
        Get name of this transport.

        :returns: 'chess_link_usb'
        """
        return "chesslink.chess_link_usb"

    def is_init(self):
        """
        Check, if hardware connection is up.

        :returns: True on success.
        """
        logger.debug("Ask for init")
        return self.init
