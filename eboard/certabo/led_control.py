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

from collections import deque
import logging
import threading
import time
import traceback


logger = logging.getLogger(__name__)


class CertaboLedControl(object):
    LEDS_OFF_COMMAND = bytearray(8)

    def __init__(self, transport):
        self.transport = transport
        self.pending = deque([])
        self.stopped = False
        self.last_time = time.time()
        self.last_cmd = None
        threading.Thread(target=self.main_loop).start()

    def main_loop(self):
        while not self.stopped:
            time.sleep(0.1)
            try:
                self.process_commands()
            except Exception:
                traceback.print_exc()
                logger.exception("Problem while processing LED commands")
                return

    def process_commands(self):
        lock = threading.Lock()
        with lock:
            while len(self.pending) > 2:
                self.pending.popleft()
            if len(self.pending) == 2 and self.pending[-1] != CertaboLedControl.LEDS_OFF_COMMAND:
                self.pending.popleft()
            current_time = time.time()
            if (self.last_time + 0.6) <= current_time and len(self.pending) > 0:
                cmd = self.pending.popleft()
                if cmd != self.last_cmd:
                    self.transport.write_mt(cmd)
                    self.last_cmd = cmd
                    self.last_time = current_time

    def write_led_command(self, cmd: bytearray):
        lock = threading.Lock()
        with lock:
            logger.debug(f"adding LED command {cmd}")
            self.pending.append(cmd)

    def stop(self):
        self.stopped = True
