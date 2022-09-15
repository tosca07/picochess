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
    import bluepy
    from bluepy.btle import Scanner, DefaultDelegate, Peripheral

    bluepy_ble_support = True
except ImportError:
    bluepy_ble_support = False


class Transport():

    def __init__(self, que: queue.Queue):
        """
        :param que: Queue that will receive events from chess board
        """
        if not bluepy_ble_support:
            self.init = False
            return
        self.wrque = queue.Queue()
        self.log = logging.getLogger('Chessnut')
        self.que = que
        self.init = True
        self.log.debug('bluepy_ble init ok')
        self.scan_timeout = 10
        self.worker_thread_active = False
        self.worker_threader = None
        self.conn_state = None

        self.bp_path = os.path.dirname(os.path.abspath(bluepy.__file__))
        self.bp_helper = os.path.join(self.bp_path, 'bluepy-helper')
        if not os.path.exists(self.bp_helper):
            self.log.warning(f'Unexpected: {self.bp_helper} does not exist!')
        self.fix_cmd = "sudo setcap 'cap_net_raw,cap_net_admin+eip' " + self.bp_helper

    def quit(self):
        self.worker_thread_active = False

    def search_board(self, iface=0):
        """
        Search for Chessnut connections using Bluetooth LE.

        :param iface: interface number of bluetooth adapter
        :returns: Bluetooth address of Chessnut board, or None on failure
        """
        self.log.debug('bluepy_ble: searching for boards')

        class ScanDelegate(DefaultDelegate):

            def __init__(self, log):
                self.log = log
                DefaultDelegate.__init__(self)

            def handleDiscovery(self, scanEntry, isNewDev, isNewData):
                if isNewDev:
                    self.log.debug(f'Discovered device {scanEntry.addr}')
                elif isNewData:
                    self.log.debug(f'Received new data from {scanEntry.addr}')

        scanner = Scanner(iface=iface).withDelegate(ScanDelegate(self.log))

        try:
            devices = scanner.scan(self.scan_timeout)
        except Exception as e:
            self.log.error(f'BLE scanning failed. {e}')
            self.log.error(f'excecute: {self.fix_cmd}')
            return None

        devs = sorted(devices, key=lambda x: x.rssi, reverse=True)
        for b in devs:
            self.log.debug(f'sorted by rssi {b.addr} {b.rssi}')

        for bledev in devs:
            self.log.debug(
                f'Device {bledev.addr} ({bledev.addrType}), RSSI={bledev.rssi} dB')
            for (adtype, desc, value) in bledev.getScanData():
                self.log.debug(f'  {desc} ({adtype}) = {value}')
                if desc == 'Complete Local Name':
                    if 'Chessnut' in value:
                        self.log.info(
                            f'Autodetected Chessnut board at Bluetooth LE address: '
                            f'{bledev.addr}, signal strength (rssi): {bledev.rssi}')
                        return bledev.addr
        return None

    def open_mt(self, address):
        """
        Open a Bluetooth LE connection to Chessnut board.

        :param address: bluetooth address
        :returns: True on success.
        """
        self.log.debug('Starting worker-thread for bluepy ble')
        self.worker_thread_active = True
        self.worker_threader = threading.Thread(
            target=self.worker_thread, args=(self.log, address, self.wrque, self.que))
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
        Asynchronously write a message to Chessnut.

        :param msg: Message string
        """
        self.wrque.put(msg)

    def is_init(self):
        """
        Check, if hardware connection is up.

        :returns: True on success
        """
        return self.init

    def agent_state(self, que, state, msg):
        que.put('agent-state: ' + state + ' ' + msg)

    def device_open(self, address, device, que, log):

        class PeriDelegate(DefaultDelegate):

            def __init__(self, log, que):
                self.log = log
                self.que = que
                self.log.debug('Init delegate for peri')
                DefaultDelegate.__init__(self)

            def handleNotification(self, cHandle, data):
                self.log.debug(f'BLE: Handle: {cHandle}, data: {data}')
                self.log.debug(f'BLE received [{data}]')
                que.put(data)

        rx = None
        tx = None
        log.debug(f'Peripheral generated {address}')
        try:
            services = device.getServices()
        except Exception as e:
            emsg = f'Failed to enumerate services for {address}, {e}'
            log.error(emsg)
            self.agent_state(que, 'offline', emsg)
            return None, None
        log.debug(f'services: {len(services)}')
        for ser in services:
            log.debug(f'Service: {ser}')
            chrs = ser.getCharacteristics()
            for chri in chrs:
                if chri.uuid == '1b7e8262-2877-41c3-b46e-cf057c562023':
                    rx = chri
                    rxh = chri.getHandle()
                    log.debug('Enabling notifications')
                    device.writeCharacteristic(handle=rxh + 1, val=(1).to_bytes(2, byteorder='little'),
                                               withResponse=False)
                elif chri.uuid == '1b7e8272-2877-41c3-b46e-cf057c562023':
                    tx = chri
                if chri.supportsRead():
                    log.debug(f'  {chri} UUID={chri.uuid} {chri.propertiesToString()} -> {chri.read()}')
                else:
                    log.debug(f'  {chri} UUID={chri.uuid} {chri.propertiesToString()}')

        try:
            log.debug('Installing peripheral delegate')
            delegate = PeriDelegate(log, que)
            device.withDelegate(delegate)
        except Exception as e:
            emsg = f'Bluetooth LE: Failed to install peripheral delegate! {e}'
            log.error(emsg)
            self.agent_state(que, 'offline', emsg)
            return None, None
        self.agent_state(que, 'online', 'Connected to Chessnut board via BLE')
        return (rx, tx)

    def worker_thread(self, log, address, wrque, que):
        """
        Background thread that handles bluetooth sending and forwards data received via
        bluetooth to the queue `que`.
        """
        message_delta_time = 0.1  # least 0.1 sec between outgoing btle messages

        log.debug(f'bluepy_ble open_mt {address}')
        try:
            device = Peripheral(address)
            device.setMTU(40)
        except Exception as e:
            emsg = f'Failed to create BLE peripheral at {address}, {e}'
            log.error(emsg)
            self.agent_state(que, 'offline', '{}'.format(e))
            self.conn_state = False
            return

        rx, tx = self.device_open(address, device, que, log)

        time_last_out = time.time() + 0.2

        if rx is None or tx is None:
            bt_error = True
            self.conn_state = False
        else:
            bt_error = False
            self.conn_state = True
        while self.worker_thread_active:
            rep_err = False
            while bt_error:
                time.sleep(1)
                bt_error = False
                self.init = False
                try:
                    device.connect(address)
                    time.sleep(1)  # try to prevent race condition - see https://github.com/IanHarvey/bluepy/issues/325
                    device.setMTU(40)
                except Exception as e:
                    if not rep_err:
                        self.log.warning(f'Reconnect failed: {e} [Local bluetooth problem?]')
                        rep_err = True
                    bt_error = True
                if not bt_error:
                    self.log.info(f'Bluetooth reconnected to {address}')
                    rx, tx = self.device_open(address, device, que, log)
                    time_last_out = time.time() + 0.2
                    self.init = True

            if not wrque.empty() and time.time() - time_last_out > message_delta_time:
                msg = wrque.get()
                try:
                    tx.write(msg, withResponse=True)
                    time_last_out = time.time()
                except Exception as e:
                    log.error(f'bluepy_ble: failed to write {msg}: {e}')
                    bt_error = True
                    self.agent_state(que, 'offline', 'Connection to Bluetooth peripheral lost')
                wrque.task_done()

            try:
                if rx.supportsRead():
                    rx.read()
                device.waitForNotifications(0.05)
            except Exception as e:
                self.log.warning(f'Bluetooth read error {e}')
                bt_error = True
                self.agent_state(que, 'offline', 'Connection to Bluetooth peripheral lost')
                continue
            time.sleep(0.01)
        device.disconnect()
