#!/usr/bin/env python3

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
Certabo transport implementation for USB connections.
"""
import logging
import threading
import queue
import time

try:
    import serial  # type: ignore
    import serial.tools.list_ports  # type: ignore

    usb_support = True
except ImportError:
    serial = None
    usb_support = False


logger = logging.getLogger(__name__)


class Transport(object):
    """
    Certabo transport implementation for USB connections.

    This transport uses an asynchronous background thread for hardware communication.
    All replies are written to the python queue `que` given during initialization.
    """

    def __init__(self, que: queue.Queue):
        """
        :param que: Queue that will receive events from chess board
        """
        if usb_support is False:
            logger.error("Cannot communicate: PySerial module not installed.")
            self.init = False
            return
        self.que = que
        self.init = True
        logger.debug("USB init ok")
        self.last_agent_state = None
        self.error_state = False
        self.thread_active = False
        self.event_thread = None
        self.usb_dev = None
        self.uport = None

    def quit(self):
        self.thread_active = False

    def search_board(self):
        """
        Search for Certabo connections on all USB ports.

        :returns: Name of the port with a Certabo board, None on failure
        """
        logger.info("Searching for Certabo board...")
        port = None
        ports = self.usb_port_search()
        if len(ports) > 0:
            if len(ports) > 1:
                logger.warning(f"Found {len(ports)} Certabo boards, using first found.")
            port = ports[0]
            logger.info(f"Autodetected Certabo board at USB port: {port}")
        return port

    def test_board(self, port):
        logger.debug(f"Testing port: {port}")
        try:
            self.usb_dev = serial.Serial(port, 38400, timeout=2, write_timeout=1)
            self.usb_dev.dtr = 0
            msg = self.usb_read().decode(encoding="UTF-8", errors="ignore")
            if ":" in msg and "\r\n" in msg:
                logger.debug(f"Message found: {msg}")
                self.usb_dev.close()
                return True
            else:
                self.usb_dev.close()
                return False
        except (OSError, serial.SerialException) as e:
            logger.error(f"Board detection on {port} resulted in error {e}")
        try:
            self.usb_dev.close()
        except (OSError, serial.SerialException):
            pass
        return False

    def is_init(self):
        """
        Check, if hardware connection is up.

        :returns: True on success
        """
        return self.init

    def usb_port_check(self, port):
        """
        Check usb port for valid Certabo connection

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
        Get a list of all usb ports that have a connected Certabo board.

        :returns: array of usb port names with valid Certabo boards, an empty array
                  if none is found.
        """
        ports = list([port.device for port in serial.tools.list_ports.comports(True)])
        vports = []
        for port in ports:
            if self.usb_port_check(port):
                if self.test_board(port):
                    logger.debug(f"Found board at: {port}")
                    vports.append(port)
                    break  # only one port necessary
        return vports

    def write_mt(self, msg):
        """
        Write a message to Certabo.

        :param msg: Message string
        """
        try:
            self.usb_dev.write(msg)
            self.usb_dev.flush()
        except Exception as e:
            logger.error(f"Failed to write {msg}: {e}")
            self.error_state = True

    def usb_read(self):
        """
        Read for initial hardware detection.
        """
        try:
            return self.usb_dev.read(1024)
        except (OSError, serial.SerialException) as e:
            logger.error(f"Error reading from serial port, {e}")
        return bytes()

    def agent_state(self, que, state, msg):
        if state != self.last_agent_state:
            self.last_agent_state = state
            que.put("agent-state: " + state + " " + msg)

    def open_mt(self, port):
        """
        Open an usb port to a connected Certabo board.

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

            self._usb_read(que)

    def _usb_read(self, que):
        try:
            by = self.usb_dev.read(1024)
            if len(by) > 0:
                que.put(by)
        except (OSError, serial.SerialException, TypeError) as e:
            logger.error(f"Error reading from serial port, {e}")
            time.sleep(0.1)
            self.error_state = True
