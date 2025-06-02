# Copyright (C) 2013-2018 Jean-Francois Romang (jromang@posteo.de)
#                         Shivkumar Shivaji ()
#                         Jürgen Précour (LocutusOfPenguin@posteo.de)
#
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

import asyncio
import logging
from threading import Timer, Lock
from typing import Dict, Set
from utilities import AsyncRepeatingTimer  # Ensure AsyncRepeatingTimer is imported from the correct module
from utilities import DisplayDgt, DispatchDgt, dispatch_queue
from dgt.api import Dgt, DgtApi
from dgt.menu import DgtMenu


logger = logging.getLogger(__name__)


class Dispatcher(DispatchDgt):
    """A dispatcher taking the dispatch_queue and fill dgt_queue with the commands in time."""

    def __init__(self, dgtmenu: DgtMenu, main_loop: asyncio.AbstractEventLoop):
        super(Dispatcher, self).__init__()

        self.dgtmenu = dgtmenu
        self.devices: Set[str] = set()
        self.maxtimer: Dict[str, Timer] = {}
        self.maxtimer_running: Dict[str, bool] = {}
        self.clock_connected: Dict[str, bool] = {}
        self.time_factor = 1  # This is for testing the duration - remove it lateron!
        self.tasks: Dict[str, list] = {}  # delayed task array

        self.display_hash: Dict[str, int] = {}  # Hash value of clock's display
        self.process_lock: Dict[str, Lock] = {}
        self.main_loop = main_loop

    def register(self, device: str):
        """Register new device to send DgtApi messsages."""
        logger.debug("device %s registered", device)
        self.devices.add(device)
        self.maxtimer_running[device] = False
        self.clock_connected[device] = False
        self.process_lock[device] = Lock()
        self.tasks[device] = []
        self.display_hash[device] = 0

    def is_prio_device(self, dev, connect):
        """Return the most prio registered device."""
        #  logger.debug("(%s) clock connected: %s", dev, connect)
        if not connect:
            return False
        if "i2c" in self.devices:
            return "i2c" == dev
        if "ser" in self.devices:
            return "ser" == dev
        return "web" == dev

    async def _stopped_maxtimer(self, dev: str):
        self.maxtimer_running[dev] = False
        self.dgtmenu.disable_picochess_displayed(dev)

        if dev not in self.devices:
            logger.debug("delete not registered (%s) tasks", dev)
            self.tasks[dev] = []
            return
        if self.tasks[dev]:
            logger.debug("processing delayed (%s) tasks: %s", dev, self.tasks[dev])
        else:
            logger.debug("(%s) max timer finished - returning to time display", dev)
            await DisplayDgt.show(Dgt.DISPLAY_TIME(force=False, wait=True, devs={dev}))
        while self.tasks[dev]:
            logger.debug("(%s) tasks has %i members", dev, len(self.tasks[dev]))
            try:
                message = self.tasks[dev].pop(0)
            except IndexError:
                break
            with self.process_lock[dev]:
                await self._process_message(message, dev)
            if self.maxtimer_running[dev]:  # run over the task list until a maxtime command was processed
                remaining = len(self.tasks[dev])
                if remaining:
                    logger.debug("(%s) tasks stopped on %i remaining members", dev, remaining)
                else:
                    logger.debug("(%s) tasks completed", dev)
                break

    async def _process_message(self, message, dev: str):
        do_handle = True
        if repr(message) in (DgtApi.CLOCK_START, DgtApi.CLOCK_STOP, DgtApi.DISPLAY_TIME):
            self.display_hash[dev] = 0  # Cant know the clock display if command changing the running status
        else:
            if repr(message) in (DgtApi.DISPLAY_MOVE, DgtApi.DISPLAY_TEXT):
                if self.display_hash[dev] == hash(message) and not message.beep:
                    do_handle = False
                else:
                    self.display_hash[dev] = hash(message)

        if do_handle:
            logger.debug("(%s) handle DgtApi: %s", dev, message)
            if repr(message) == DgtApi.CLOCK_VERSION:
                logger.debug("(%s) clock registered", dev)
                self.clock_connected[dev] = True

            clk = (
                DgtApi.DISPLAY_MOVE,
                DgtApi.DISPLAY_TEXT,
                DgtApi.DISPLAY_TIME,
                DgtApi.CLOCK_SET,
                DgtApi.CLOCK_START,
                DgtApi.CLOCK_STOP,
            )
            if repr(message) in clk and not self.clock_connected[dev]:
                logger.debug("(%s) clock still not registered => ignore %s", dev, message)
                return
            if hasattr(message, "maxtime"):
                if repr(message) == DgtApi.DISPLAY_TEXT:
                    if message.maxtime == 2.1:  # 2.1=picochess message
                        self.dgtmenu.enable_picochess_displayed(dev)
                    if self.dgtmenu.inside_updt_menu():
                        if message.maxtime == 0.1:  # 0.1=eBoard error
                            logger.debug("(%s) inside update menu => board errors not displayed", dev)
                            return
                        if message.maxtime == 1.1:  # 1.1=eBoard connect
                            logger.debug("(%s) inside update menu => board connect not displayed", dev)
                            return
                if message.maxtime > 0.1:  # filter out "all the time" show and "eBoard error" messages
                    self.maxtimer[dev] = AsyncRepeatingTimer(
                        message.maxtime * self.time_factor, self._stopped_maxtimer, self.main_loop, False, [dev]
                    )
                    self.maxtimer[dev].start()
                    logger.debug("(%s) showing %s for %.1f secs", dev, message, message.maxtime * self.time_factor)
                    self.maxtimer_running[dev] = True
            if repr(message) == DgtApi.CLOCK_START and self.dgtmenu.inside_updt_menu():
                logger.debug("(%s) inside update menu => clock not started", dev)
                return
            message.devs = {dev}  # on new system, we only have ONE device each message - force this!
            await DisplayDgt.show(message)
        else:
            logger.debug("(%s) hash ignore DgtApi: %s", dev, message)

    def stop_maxtimer(self, dev):
        """Stop the maxtimer."""
        if self.maxtimer_running[dev]:
            self.maxtimer[dev].stop()
            self.maxtimer_running[dev] = False
            self.dgtmenu.disable_picochess_displayed(dev)

    async def dispatch_consumer(self):
        """Consume the dispatch event queue"""
        logger.debug("dispatch_queue ready")
        try:
            while True:
                # Check if we have something to display
                msg = await dispatch_queue.get()
                logger.debug("received command from dispatch_queue: %s devs: %s", msg, ",".join(msg.devs))
                # issue #45 just process one message at a time - dont spawn task
                # asyncio.create_task(self.process_dispatch_message(msg))
                await self.process_dispatch_message(msg)
                dispatch_queue.task_done()
                await asyncio.sleep(0.05)  # balancing message queues
        except asyncio.CancelledError:
            logger.debug("dispatch_queue cancelled")

    async def process_dispatch_message(self, message):
        """Process the dispatch message"""
        for dev in message.devs & self.devices:
            if self.maxtimer_running[dev]:
                if hasattr(message, "wait"):
                    if message.wait:
                        self.tasks[dev].append(message)
                        logger.debug("(%s) tasks delayed: %s", dev, self.tasks[dev])
                        continue
                    else:
                        logger.debug("ignore former maxtime - dev: %s", dev)
                        self.stop_maxtimer(dev)
                        if self.tasks[dev]:
                            logger.debug("delete following (%s) tasks: %s", dev, self.tasks[dev])
                            while self.tasks[dev]:  # but do the last CLOCK_START()
                                command = self.tasks[dev].pop()
                                if repr(command) == DgtApi.CLOCK_START:  # clock might be in set mode
                                    logger.debug("processing (last) delayed clock start command")
                                    with self.process_lock[dev]:
                                        await self._process_message(command, dev)
                                    break
                            self.tasks[dev] = []
                else:
                    logger.debug("command doesnt change the clock display => (%s) max timer ignored", dev)
            else:
                logger.debug("(%s) max timer not running => processing command: %s", dev, message)

            with self.process_lock[dev]:
                await self._process_message(message, dev)
