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
# Most of the code copied from https://github.com/domschl/python-mchess/blob/master/mchess/chess_link_bluepy.py

import logging
import threading
import queue
import time
import os

try:
    import bluepy  # type: ignore
    from bluepy.btle import Scanner, DefaultDelegate, Peripheral  # type: ignore

    bluepy_ble_support = True
except ImportError:
    bluepy_ble_support = False

logger = logging.getLogger(__name__)


class Transport(object):

    def __init__(self, que: queue.Queue, read_characteristic: str, write_characteristic: str):
        """
        :param que: Queue that will receive events from chess board
        """
        if not bluepy_ble_support:
            self.init = False
            return
        self.wrque: queue.Queue = queue.Queue()
        self.que = que
        self._read_characteristic = read_characteristic
        self._write_characteristic = write_characteristic
        self.init = True
        logger.debug("bluepy_ble init ok")
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
        self.worker_thread_active = False

    def search_board(self, board_identifier: str, iface=0):
        """
        Search for e-board connections using Bluetooth LE.

        :param iface: interface number of bluetooth adapter
        :returns: Bluetooth address of e-board, or None on failure
        """
        logger.debug("bluepy_ble: searching for boards")

        scanner = self._create_scanner(iface)

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
                    if board_identifier in value:
                        logger.info(
                            f"Autodetected {board_identifier} board at Bluetooth LE address: "
                            f"{bledev.addr}, signal strength (rssi): {bledev.rssi}"
                        )
                        return bledev.addr
        return None

    def _create_scanner(self, iface):
        class ScanDelegate(DefaultDelegate):

            def __init__(self):
                DefaultDelegate.__init__(self)

            def handleDiscovery(self, scanEntry, isNewDev, isNewData):
                if isNewDev:
                    logger.debug(f"Discovered device {scanEntry.addr}")
                elif isNewData:
                    logger.debug(f"Received new data from {scanEntry.addr}")

        scanner = Scanner(iface=iface).withDelegate(ScanDelegate())
        return scanner

    def open_mt(self, address):
        """
        Open a Bluetooth LE connection to e-board.

        :param address: bluetooth address
        :returns: True on success.
        """
        logger.debug("Starting worker-thread for bluepy ble")
        self.worker_thread_active = True
        self.worker_threader = threading.Thread(target=self._worker_thread, args=(address, self.wrque, self.que))
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
        Asynchronously write a message to e-board.

        :param msg: Message string
        """
        self.wrque.put(msg)

    def is_init(self):
        """
        Check, if hardware connection is up.

        :returns: True on success
        """
        return self.init

    def _agent_state(self, que, state, msg):
        que.put("agent-state: " + state + " " + msg)

    def _device_open(self, address, device, que):

        class PeriDelegate(DefaultDelegate):

            def __init__(self, que):
                self.que = que
                logger.debug("Init delegate for peri")
                DefaultDelegate.__init__(self)

            def handleNotification(self, cHandle, data):
                logger.debug(f"BLE: Handle: {cHandle}, data: {data}")
                logger.debug(f"BLE received [{data}]")
                que.put(data)

        logger.debug(f"Peripheral generated {address}")
        try:
            services = device.getServices()
        except Exception as e:
            emsg = f"Failed to enumerate services for {address}, {e}"
            logger.error(emsg)
            self._agent_state(que, "offline", emsg)
            return None, None
        rx, tx = self._init_characteristics(device, services)

        try:
            logger.debug("Installing peripheral delegate")
            delegate = PeriDelegate(que)
            device.withDelegate(delegate)
        except Exception as e:
            emsg = f"Bluetooth LE: Failed to install peripheral delegate! {e}"
            logger.error(emsg)
            self._agent_state(que, "offline", emsg)
            return None, None
        self._agent_state(que, "online", "Connected to e-board via BLE")
        return rx, tx

    def _init_characteristics(self, device, services):
        rx = None
        tx = None
        logger.debug(f"services: {len(services)}")
        for ser in services:
            logger.debug(f"Service: {ser}")
            chrs = ser.getCharacteristics()
            for chri in chrs:
                if chri.uuid == self._read_characteristic:
                    rx = chri
                    rxh = chri.getHandle()
                    logger.debug("Enabling notifications")
                    device.writeCharacteristic(
                        handle=rxh + 1, val=(1).to_bytes(2, byteorder="little"), withResponse=True
                    )
                elif chri.uuid == self._write_characteristic:
                    tx = chri
                if chri.supportsRead():
                    logger.debug(f"  {chri} UUID={chri.uuid} {chri.propertiesToString()} -> {chri.read()}")
                else:
                    logger.debug(f"  {chri} UUID={chri.uuid} {chri.propertiesToString()}")
        return rx, tx

    def _worker_thread(self, address, wrque, que):
        """
        Background thread that handles bluetooth sending and forwards data received via
        bluetooth to the queue `que`.
        """
        device = self._create_device(address, que)
        if device is None:
            return

        rx, tx = self._device_open(address, device, que)

        time_last_out = time.time() + 0.2

        if rx is None or tx is None:
            bt_error = True
            self.conn_state = False
        else:
            bt_error = False
            self.conn_state = True

        self._handle_device_data(device, address, rx, tx, que, wrque, bt_error, time_last_out)

    def _handle_device_data(self, device, address, rx, tx, que, wrque, bt_error, time_last_out):
        message_delta_time = 0.1  # least 0.1 sec between outgoing btle messages
        while self.worker_thread_active:
            rep_err = False
            while bt_error:
                bt_error, rx, tx, time_last_out = self._try_connect(
                    device, address, rx, tx, que, rep_err, time_last_out
                )

            if not wrque.empty() and time.time() - time_last_out > message_delta_time:
                msg = wrque.get()
                try:
                    tx.write(msg, withResponse=True)
                    time_last_out = time.time()
                except Exception as e:
                    logger.error(f"bluepy_ble: failed to write {msg}: {e}")
                    bt_error = True
                    self._agent_state(que, "offline", "BLE connection lost")
                wrque.task_done()

            try:
                self._read(device, rx)
            except Exception as e:
                logger.warning(f"Bluetooth read error {e}")
                bt_error = True
                self._agent_state(que, "offline", "BLE connection lost")
                continue
            time.sleep(0.01)
        device.disconnect()

    def _try_connect(self, device, address, rx, tx, que, rep_err, time_last_out):
        time.sleep(1)
        bt_error = False
        self.init = False
        try:
            self._connect_device(device, address)
        except Exception as e:
            if not rep_err:
                logger.warning(f"Reconnect failed: {e} [Local bluetooth problem?]")
                rep_err = True
            bt_error = True
        if not bt_error:
            rx, tx, time_last_out = self._on_connect(device, address, rx, tx, que, time_last_out)
        return bt_error, rx, tx, time_last_out

    def _on_connect(self, device, address, rx, tx, que, time_last_out):
        logger.info(f"Bluetooth reconnected to {address}")
        rx, tx = self._device_open(address, device, que)
        time_last_out = time.time() + 0.2
        self.init = True
        return rx, tx, time_last_out

    def _create_device(self, address, que):
        logger.debug(f"bluepy_ble open_mt {address}")
        try:
            device = Peripheral(address)
            device.setMTU(40)
        except Exception as e:
            emsg = f"Failed to create BLE peripheral at {address}, {e}"
            logger.error(emsg)
            self._agent_state(que, "offline", "{}".format(e))
            self.conn_state = False
            return None
        return device

    def _connect_device(self, device, address):
        device.connect(address)
        time.sleep(1)  # try to prevent race condition - see https://github.com/IanHarvey/bluepy/issues/325
        device.setMTU(40)

    def _read(self, device, rx):
        if rx.supportsRead():
            rx.read()
        device.waitForNotifications(0.05)
