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
import time

from chessnut.protocol import Protocol


class ChessnutAgent:

    def __init__(self, appque):
        self.name = 'ChessnutAgent'
        self.appque = appque
        self.log = logging.getLogger(self.name)
        self.brd = Protocol(self.appque, self.name)
        self.init_position = False

        if self.brd.connected:
            self.realtime_mode()
        else:
            self.log.warning('Connection to Chessnut failed.')
            return

        self.log.debug('waiting for board position')
        start = time.time()
        warned = False
        while not self.init_position:
            if self.brd.error_condition:
                self.log.info('Chessnut board not available.')
                return
            if time.time() - start > 2 and not warned:
                warned = True
                self.log.info('Searching for Chessnut board...')
            self.init_position = self.brd.position_initialized()
            time.sleep(0.1)

        if self.init_position:
            self.log.debug('board position received, init ok.')
        else:
            self.log.error('no board position received')

    def quit(self):
        self.brd.quit()

    def set_led_off(self):
        self.brd.set_led_off()

    def set_led(self, pos):
        self.brd.set_led(pos)

    def request_battery_status(self):
        self.brd.request_battery_status()

    def realtime_mode(self):
        self.brd.realtime_mode()
