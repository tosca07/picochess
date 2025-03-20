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
ChessLink transport implementation for Bluetooth LE connections using `bluepy`.
"""
import logging
import threading
import queue
import time
import os

import eboard.chesslink.chess_link_protocol as clp

try:
    import bluepy  # type: ignore
    from bluepy.btle import Scanner, DefaultDelegate, Peripheral  # type: ignore

    bluepy_ble_support = True
except ImportError:
    bluepy_ble_support = False


logger = logging.getLogger(__name__)


class Transport:
    """
    ChessLink transport implementation for Bluetooth LE connections using `bluepy`.

    This class does automatic hardware detection of any ChessLink board using bluetooth LE
    and supports Linux and Raspberry Pi.

    This transport uses an asynchronous background thread for hardware communcation.
    All replies are written to the python queue `que` given during initialization.

    For the details of the Chess Link protocol, please refer to:
    `magic-link.md <https://github.com/domschl/python-mchess/blob/master/mchess/magic-board.md>`_.
    """

    def __init__(self, que, protocol_dbg=False):
        """
        Initialize with python queue for event handling.
        Events are strings conforming to the ChessLink protocol as documented in
        `magic-link.md <https://github.com/domschl/python-mchess/blob/master/mchess/magic-board.md>`_.

        :param que: Python queue that will eceive events from chess board.
        :param protocol_dbg: True: byte-level ChessLink protocol debug messages
        """
        if bluepy_ble_support is False:
            self.init = False
            return
        self.wrque = queue.Queue()
        self.que = que
        self.init = True
        logger.debug("bluepy_ble init ok")
        self.protocol_debug = protocol_dbg
        self.scan_timeout = 10
        self.worker_thread_active = False
        self.worker_threader = None
        self.conn_state = None

        self.bp_path = os.path.dirname(os.path.abspath(bluepy.__file__))
        self.bp_helper = os.path.join(self.bp_path, "bluepy-helper")
        if not os.path.exists(self.bp_helper):
            logger.warning(f"Unexpected: {self.bp_helper} does not exist!")
        self.fix_cmd = "sudo setcap 'cap_net_raw,cap_net_admin+eip' " + self.bp_helper

    def quit(self):
        """
        Initiate worker-thread stop
        """
        self.worker_thread_active = False

    def search_board(self, iface=0):
        """
        Search for ChessLink connections using Bluetooth LE.

        :param iface: interface number of bluetooth adapter, default 1.
        :returns: Bluetooth address of ChessLink board, or None on failure.
        """
        logger.debug("bluepy_ble: searching for boards")

        class ScanDelegate(DefaultDelegate):
            """scanner class"""

            def __init__(self):
                DefaultDelegate.__init__(self)

            def handleDiscovery(self, scanEntry, isNewDev, isNewData):
                if isNewDev:
                    logger.debug(f"Discovered device {scanEntry.addr}")
                elif isNewData:
                    logger.debug(f"Received new data from {scanEntry.addr}")

        scanner = Scanner(iface=iface).withDelegate(ScanDelegate())

        try:
            devices = scanner.scan(self.scan_timeout)
        except Exception as e:
            logger.error(f"BLE scanning failed. {e}")
            logger.error(f"excecute: {self.fix_cmd}")
            return None

        devs = sorted(devices, key=lambda x: x.rssi, reverse=True)
        for b in devs:
            logger.debug(f"sorted by rssi {b.addr} {b.rssi}")

        for bledev in devs:
            logger.debug(f"Device {bledev.addr} ({bledev.addrType}), RSSI={bledev.rssi} dB")
            for adtype, desc, value in bledev.getScanData():
                logger.debug(f"  {desc} ({adtype}) = {value}")
                if desc == "Complete Local Name":
                    if "MILLENNIUM CHESS" in value:
                        logger.info(
                            "Autodetected Millennium Chess Link board at "
                            f"Bluetooth LE address: {bledev.addr}, "
                            f"signal strength (rssi): {bledev.rssi}"
                        )
                        return bledev.addr
        return None

    def test_board(self, address):
        """
        Test dummy.

        :returns: Version string "1.0" always.
        """
        logger.debug(f"test_board address {address} not implemented.")
        # self.open_mt(address)
        return "1.0"

    def open_mt(self, address):
        """
        Open a bluetooth LE connection to ChessLink board.

        :param address: bluetooth address
        :returns: True on success.
        """
        logger.debug("Starting worker-thread for bluepy ble")
        self.worker_thread_active = True
        self.worker_threader = threading.Thread(target=self.worker_thread, args=(address, self.wrque, self.que))
        self.worker_threader.setDaemon(True)
        self.worker_threader.start()
        timer = time.time()
        self.conn_state = None
        while self.conn_state is None and time.time() - timer < 5.0:
            time.sleep(0.1)
        if self.conn_state is None:
            return False
        return self.conn_state

    def write_mt(self, msg):
        """
        Encode and asynchronously write a message to ChessLink.

        :param msg: Message string. Parity will be added, and block CRC appended.
        """
        if self.protocol_debug is True:
            logger.debug(f"write-que-entry {msg}")
        self.wrque.put(msg)

    def get_name(self):
        """
        Get name of this transport.

        :returns: 'eboard.chesslink.chess_link_bluepy'
        """
        return "eboard.chesslink.chess_link_bluepy"

    def is_init(self):
        """
        Check, if hardware connection is up.

        :returns: True on success.
        """
        return self.init

    def agent_state(self, que, state, msg):
        que.put("agent-state: " + state + " " + msg)

    def mil_open(self, address, mil, que):

        class PeriDelegate(DefaultDelegate):
            """peripheral delegate class"""

            def __init__(self, que):
                self.que = que
                logger.debug("Init delegate for peri")
                self.chunks = ""
                DefaultDelegate.__init__(self)

            def handleNotification(self, cHandle, data):
                logger.debug(f"BLE: Handle: {cHandle}, data: {data}")
                rcv = ""
                for b in data:
                    rcv += chr(b & 127)
                logger.debug("BLE received [{}]".format(rcv))
                self.chunks += rcv
                if self.chunks[0] not in clp.protocol_replies:
                    logger.warning(f"Illegal reply start '{self.chunks[0]}' received, discarding")
                    while len(self.chunks) > 0 and self.chunks[0] not in clp.protocol_replies:
                        self.chunks = self.chunks[1:]
                if len(self.chunks) > 0:
                    mlen = clp.protocol_replies[self.chunks[0]]
                    if len(self.chunks) >= mlen:
                        valmsg = self.chunks[:mlen]
                        logger.debug("bluepy_ble received complete msg: {}".format(valmsg))
                        if clp.check_block_crc(valmsg):
                            que.put(valmsg)
                        self.chunks = self.chunks[mlen:]

        rx = None
        tx = None
        logger.debug("Peripheral generated {}".format(address))
        try:
            services = mil.getServices()
        except Exception as e:
            emsg = "Failed to enumerate services for {}, {}".format(address, e)
            logger.error(emsg)
            self.agent_state(que, "offline", emsg)
            return None, None
        # time.sleep(0.1)
        logger.debug(f"services: {len(services)}")
        for ser in services:
            logger.debug("Service: {}".format(ser))
            chrs = ser.getCharacteristics()
            for chri in chrs:
                if chri.uuid == "49535343-1e4d-4bd9-ba61-23c647249616":  # TX char, rx for us
                    rx = chri
                    rxh = chri.getHandle()
                    # Enable notification magic:
                    logger.debug("Enabling notifications")
                    mil.writeCharacteristic(rxh + 1, (1).to_bytes(2, byteorder="little"))
                if chri.uuid == "49535343-8841-43f4-a8d4-ecbe34729bb3":  # RX char, tx for us
                    tx = chri
                    # txh = chri.getHandle()
                if chri.supportsRead():
                    logger.debug(f"  {chri} UUID={chri.uuid} {chri.propertiesToString()} -> " "{chri.read()}")
                else:
                    logger.debug(f"  {chri} UUID={chri.uuid} {chri.propertiesToString()}")

        try:
            logger.debug("Installing peripheral delegate")
            delegate = PeriDelegate(que)
            mil.withDelegate(delegate)
        except Exception as e:
            emsg = f"Bluetooth LE: Failed to install peripheral delegate! {e}"
            logger.error(emsg)
            self.agent_state(que, "offline", emsg)
            return None, None
        self.agent_state(que, "online", "Connected to ChessLink board via BLE")
        return (rx, tx)

    def worker_thread(self, address, wrque, que):
        """
        Background thread that handles bluetooth sending and forwards data received via
        bluetooth to the queue `que`.
        """
        message_delta_time = 0.1  # least 0.1 sec between outgoing btle messages

        logger.debug(f"bluepy_ble open_mt {address}")
        try:
            logger.debug("per1")
            mil = Peripheral(address)
            logger.debug("per2")
        except Exception as e:
            logger.debug("per3")
            emsg = f"Failed to create BLE peripheral at {address}, {e}"
            logger.error(emsg)
            self.agent_state(que, "offline", "{}".format(e))
            self.conn_state = False
            return

        rx, tx = self.mil_open(address, mil, que)

        time_last_out = time.time() + 0.2

        if rx is None or tx is None:
            bt_error = True
            self.conn_state = False
        else:
            bt_error = False
            self.conn_state = True
        while self.worker_thread_active is True:
            rep_err = False
            while bt_error is True:
                time.sleep(1)
                bt_error = False
                self.init = False
                try:
                    mil.connect(address)
                except Exception as e:
                    if rep_err is False:
                        logger.warning(f"Reconnect failed: {e} [Local bluetooth problem?]")
                        rep_err = True
                    bt_error = True
                if bt_error is False:
                    logger.info(f"Bluetooth reconnected to {address}")
                    rx, tx = self.mil_open(address, mil, que)
                    time_last_out = time.time() + 0.2
                    self.init = True

            if wrque.empty() is False and time.time() - time_last_out > message_delta_time:
                msg = wrque.get()
                gpar = 0
                for b in msg:
                    gpar = gpar ^ ord(b)
                msg = msg + clp.hex2(gpar)
                if self.protocol_debug is True:
                    logger.debug(f"blue_ble write: <{msg}>")
                bts = ""
                for c in msg:
                    bo = chr(clp.add_odd_par(c))
                    bts += bo
                    btsx = bts.encode("latin1")
                if self.protocol_debug is True:
                    logger.debug(f"Sending: <{btsx}>")
                try:
                    tx.write(btsx, withResponse=True)
                    time_last_out = time.time()
                except Exception as e:
                    logger.error(f"bluepy_ble: failed to write {msg}: {e}")
                    bt_error = True
                    self.agent_state(que, "offline", f"Connection to Bluetooth peripheral lost: {e}")
                wrque.task_done()

            try:
                rx.read()
                mil.waitForNotifications(0.05)
                # time.sleep(0.1)
            except Exception as e:
                logger.warning(f"Bluetooth read error {e}")
                bt_error = True
                self.agent_state(que, "offline", f"Connection to Bluetooth peripheral lost: {e}")
                continue
            time.sleep(0.01)
        mil.disconnect()
