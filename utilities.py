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

import logging
import os
import platform
import urllib.request
import socket
import json
import copy
import configparser
import subprocess
import asyncio
import time
from ctypes import cdll, c_int

from subprocess import Popen, PIPE

from dgt.translate import DgtTranslate
from dgt.api import Dgt

from configobj import ConfigObj, ConfigObjError, DuplicateError  # type: ignore

from typing import Optional

from pathlib import Path

# picochess version
version = "4.1.9"

logger = logging.getLogger(__name__)

evt_queue: asyncio.Queue = asyncio.Queue()
dispatch_queue: asyncio.Queue = asyncio.Queue()

msgdisplay_devices = []
dgtdisplay_devices = []


class Observable(object):
    """Input devices are observable."""

    def __init__(self):
        super(Observable, self).__init__()

    @staticmethod
    async def fire(event):
        """Put an event on the Queue."""
        event_copy = copy.deepcopy(event) if event is not None else None
        await Observable._add_to_queue(event_copy)

    @staticmethod
    async def _add_to_queue(event):
        """Put an event on the Queue."""
        await evt_queue.put(event)
        #  logger.debug("added event to queue %s", event)


class DispatchDgt(object):
    """Input devices are observable."""

    def __init__(self):
        super(DispatchDgt, self).__init__()

    @staticmethod
    async def fire(dgt):
        """Put an event on the Queue."""
        await DispatchDgt._add_to_queue(copy.deepcopy(dgt))

    @staticmethod
    async def _add_to_queue(dgt):
        """Put an event on the Queue."""
        await dispatch_queue.put(dgt)
        logger.debug("added dgt to queue %s", dgt)


class DisplayMsg(object):
    """Display devices (DGT XL clock, Piface LCD, pgn file...)."""

    def __init__(self, loop: asyncio.AbstractEventLoop):
        super(DisplayMsg, self).__init__()
        self.msg_queue = asyncio.Queue()
        self.loop = loop  # everyone to use main loop
        msgdisplay_devices.append(self)

    async def add_to_queue(self, message):
        """Put an event on the Queue."""
        await self.msg_queue.put(message)

    @staticmethod
    async def show(message):
        """Send a message on each display device."""
        for display in msgdisplay_devices:
            await display.add_to_queue(copy.deepcopy(message))
        # logger.debug("added message to %d queues %s", len(msgdisplay_devices), message)


class DisplayDgt(object):
    """Display devices (DGT XL clock, Piface LCD, pgn file...)."""

    def __init__(self, loop: asyncio.AbstractEventLoop):
        super(DisplayDgt, self).__init__()
        self.dgt_queue = asyncio.Queue()
        self.loop = loop  # everyone to use main loop
        dgtdisplay_devices.append(self)

    async def add_to_queue(self, message):
        """Put an event on the Queue."""
        await self.dgt_queue.put(message)
        # logger.debug("added message to dgt queue %s", message)

    @staticmethod
    async def show(message):
        """Send a message on each display device."""
        for display in dgtdisplay_devices:
            await display.add_to_queue(copy.deepcopy(message))


class AsyncRepeatingTimer:
    """Call function on a given interval - Async version to replace RepeatedTimer"""

    def __init__(self, interval, callback, loop: asyncio.AbstractEventLoop, repeating=True, args=None, kwargs=None):
        self.interval = interval  # Interval between each execution
        self.callback = callback  # Function to be repeatedly called
        self._task = None  # Reference to the asynchronous task
        self._running = False  # Keeps track of whether the timer is running
        self.loop = loop  # run callback in callers eventloop
        self.repeating = repeating  # repeat is default, set false to run only once
        self.args = args if args is not None else []
        self.kwargs = kwargs if kwargs is not None else {}

    def is_running(self):
        """Return the running status."""
        return self._running

    async def _run(self):
        while self._running:  # Continue running until the timer is stopped
            try:
                await asyncio.sleep(self.interval)
            except asyncio.CancelledError:
                # Timer cancelled during shutdown; exit quietly.
                break
            if asyncio.iscoroutinefunction(self.callback):
                await self.callback(*self.args, **self.kwargs)
            else:
                self.callback(*self.args, **self.kwargs)  # sync callback
            if not self.repeating:
                self._running = False

    def start(self):
        """Start the RepeatingTimer."""
        if not self._running:
            self._running = True
            self._task = self.loop.create_task(self._run())
        else:
            logging.info("repeated timer already running - strange!")

    def stop(self):
        """Stop the RepeatingTimer."""
        if self._running:
            self._running = False
            if self._task is not None:
                self._task.cancel()
                self._task = None
        else:
            logging.debug("repeated timer already stopped - strange!")


def get_opening_books():
    """Build an opening book lib."""
    config = configparser.ConfigParser()
    config.optionxform = str
    program_path = os.path.dirname(os.path.realpath(__file__)) + os.sep
    book_path = program_path + "books"
    config.read(book_path + os.sep + "books.ini")

    library = []
    for section in config.sections():
        text = Dgt.DISPLAY_TEXT(
            web_text=config[section]["large"],
            large_text=config[section]["large"],
            medium_text=config[section]["medium"],
            small_text=config[section]["small"],
            wait=True,
            beep=False,
            maxtime=0,
            devs={"ser", "i2c", "web"},
        )
        library.append({"file": "books" + os.sep + section, "text": text})
    return library


def hms_time(seconds: int):
    """Transfer a seconds integer to hours,mins,secs."""
    if seconds < 0:
        logging.warning("negative time %i", seconds)
        return 0, 0, 0
    mins, secs = divmod(seconds, 60)
    hours, mins = divmod(mins, 60)
    return hours, mins, secs


def do_popen(command, log=True, force_en_env=False):
    """Connect via Popen and log the result."""
    if force_en_env:  # force an english environment
        force_en_env = os.environ.copy()
        force_en_env["LC_ALL"] = "C"
        stdout, stderr = Popen(command, stdout=PIPE, stderr=PIPE, env=force_en_env).communicate()
    else:
        stdout, stderr = Popen(command, stdout=PIPE, stderr=PIPE).communicate()
    if log:
        logging.debug([output.decode(encoding="UTF-8") for output in [stdout, stderr]])
    return stdout.decode(encoding="UTF-8")


def git_name():
    """Get the git execute name."""
    return "git.exe" if platform.system() == "Windows" else "git"


def get_tags():
    """Get the last 3 tags from git."""
    git = git_name()
    tags = [(tags, tags[1] + tags[-2:]) for tags in do_popen([git, "tag"], log=False).split("\n")[-4:-1]]
    return tags  # returns something like [('v0.9j', 09j'), ('v0.9k', '09k'), ('v0.9l', '09l')]


def checkout_tag(tag):
    """Update picochess by tag from git."""
    git = git_name()
    do_popen([git, "checkout", tag])
    do_popen(["pip3", "install", "-r", "requirements.txt"])


def update_pico_engines():
    """Update picochess engines from github resource (asset) files"""
    script_path = "/opt/picochess/move-engines-to-backup.sh"

    try:
        result = subprocess.run(["/bin/sh", script_path], check=True, capture_output=True, text=True)
        logger.debug("Engines successfully moved to backup. Proceeding to update pico")
        logger.debug("Script output: %s", result.stdout)
        # the purpose of above is just to empty the engines folder, now get new engines
        update_pico_v4(reason="engines")  # triggers update which runs install-engines to get new engines

    except subprocess.CalledProcessError as e:
        logger.debug("Error while running move-engines-to-backup.sh")
        logger.debug("Return code: %s", e.returncode)


def update_pico_v4(reason: Optional[str] = None):
    """use the picochess-update.service and update on next boot"""
    # Path to the update trigger flag
    flag_path = Path.home() / "run_picochess_update.flag"
    flag_reason = reason if reason else "pico"

    # Create the flag file if it doesn't exist
    try:
        flag_path.write_text(flag_reason, encoding="utf-8")
        logger.info("Update flag '%s' created. Will run on next boot.", flag_reason)
    except Exception:
        logger.info("Failed to create update flag. Cannot update picochess on next boot.")


async def update_picochess(dgtpi: bool, auto_reboot: bool, dgttranslate: DgtTranslate):
    """Update picochess from git."""
    git = git_name()

    branch = do_popen([git, "rev-parse", "--abbrev-ref", "HEAD"], log=False).rstrip()
    if branch == "master":
        # Fetch remote repo
        do_popen([git, "remote", "update"])
        # Check if update is needed - need to make sure, we get english answers
        output = do_popen([git, "status", "-uno"], force_en_env=True)
        if "up-to-date" not in output and "Your branch is ahead of" not in output:
            DispatchDgt.fire(dgttranslate.text("Y25_update"))
            # Update
            logging.debug("updating picochess")
            do_popen([git, "pull", "origin", branch])
            do_popen(["pip3", "install", "-r", "requirements.txt"])
            if auto_reboot:
                reboot(dgtpi, dev="web")
        else:
            logging.debug("no update available")
    else:
        logging.warning("wrong branch %s", branch)


def shutdown(dgtpi: bool, dev: str):
    """Shutdown picochess."""
    logging.debug("shutting down system requested by (%s)", dev)

    if platform.system() == "Windows":
        os.system("shutdown /s")
    elif dgtpi:
        shutdown_dgtpi()
        os.system("sudo shutdown -h now")
    else:
        os.system("sudo shutdown -h now")


def shutdown_dgtpi():
    """Shutdown and close communication to DGTPI, clearing the clock screen."""
    logging.debug("shutting down dgtpi system")
    try:
        dgt_functions = cdll.LoadLibrary("etc/dgtpicom.so")

        # Set function prototypes
        dgt_functions.dgtpicom_init.restype = c_int
        dgt_functions.dgtpicom_configure.restype = c_int
        dgt_functions.dgtpicom_off.argtypes = [c_int]
        dgt_functions.dgtpicom_off.restype = c_int
        dgt_functions.dgtpicom_stop.restype = None

        # Init and configure
        if dgt_functions.dgtpicom_init() < 0:
            logging.debug("dgtpicom_init failed in shutdown")
        if dgt_functions.dgtpicom_configure() < 0:
            logging.debug("dgtpicom_configure may have failed in shutdown")

        time.sleep(0.2)  # allow clock to settle
        max_retries = 3
        for attempt in range(max_retries):
            result = dgt_functions.dgtpicom_off(1)
            if result == 0:
                logging.debug("dgtpicom succesfully closed on attempt %d", attempt + 1)
                break
            else:
                logging.debug("dgtpicom_off attempt %d failed with return code %s", attempt + 1, result)
            time.sleep(0.2)
        dgt_functions.dgtpicom_stop()
        time.sleep(0.2)
    except Exception as e:
        logging.error("Exception during shutdown_dgtpi: %s", e)


def exit_pico(dgtpi: bool, dev: str):
    """exit picochess."""
    logging.debug("exit picochess requested by (%s)", dev)

    if platform.system() == "Windows":
        os.system("sudo pkill -f chromium")
        os.system("sudo systemctl stop picochess")
    elif dgtpi:
        shutdown_dgtpi()
        os.system("sudo pkill -f chromium")
        os.system("sudo systemctl stop dgtpi")
    elif platform.machine() != "x86_64":
        # on Debian Linux laptops we dont want to stop chromium
        # on Pi systems we have kiosk mode, so we kill chromium
        # @todo should perhaps have a check for kiosk mode here
        os.system("sudo pkill -f chromium")
    # no need to stop picochess, all async will be stopped by MainLoop


def reboot(dgtpi: bool, dev: str):
    """Reboot picochess."""
    logging.debug("rebooting system requested by (%s)", dev)

    if platform.system() == "Windows":
        os.system("shutdown /r")
    elif dgtpi:
        os.system("sudo reboot")
    else:
        os.system("sudo reboot")


def _get_internal_ip() -> Optional[str]:
    try:
        iproute = subprocess.run(["ip", "-j", "route", "get", "8.8.8.8"], capture_output=True)
        routes = json.loads(iproute.stdout)
        if routes:
            gateway = routes[0]["gateway"]
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.connect((gateway, 80))
            int_ip = sock.getsockname()[0]
            sock.close()
            return int_ip
    except Exception:
        return None
    return None


def get_location():
    """Return the location of the user and the external and internal ip adr."""
    if int_ip := _get_internal_ip():
        try:
            response = urllib.request.urlopen("https://get.geojs.io/v1/ip/geo.json")
            j = json.loads(response.read().decode())

            country_name = j.get("country", "")
            country_code = j.get("country_code", "")
            city = j.get("city", "")
            ext_ip = j.get("IPv4", None)

            return f"{city}, {country_name} {country_code}", ext_ip, int_ip
        except Exception:
            pass
    return "?", None, None


def write_picochess_ini(key: str, value):
    """Update picochess.ini config file with key/value."""
    try:
        config = ConfigObj("picochess.ini", default_encoding="utf8")
        config[key] = value
        config.write()
    except (ConfigObjError, DuplicateError) as conf_exc:
        logging.exception(conf_exc)


def is_wayland_session() -> bool:
    return os.environ.get("XDG_SESSION_TYPE") == "wayland" or bool(os.environ.get("WAYLAND_DISPLAY"))


_WINDOW_COMMANDS = {
    "toggle_fullscreen": "xdotool keydown alt key F11; sleep 0.2; xdotool keyup alt",
    "switch_window": "xdotool keydown alt key Tab; sleep 0.2; xdotool keyup alt",
    "switch_window_toggle_fullscreen": (
        "xdotool keydown alt key Tab; sleep 0.2; xdotool keyup alt; "
        "sleep 0.2; xdotool keydown alt key F11; sleep 0.2; xdotool keyup alt"
    ),
}


def get_window_command(action: str) -> Optional[str]:
    if is_wayland_session():
        logger.info("Wayland session detected; skipping window action '%s'", action)
        return None
    cmd = _WINDOW_COMMANDS.get(action)
    if cmd is None:
        logger.warning("Unknown window action '%s'", action)
    return cmd


def get_engine_mame_par(engine_rspeed: float, engine_rsound=False, engine_rwindow: Optional[bool] = None) -> str:
    if engine_rspeed < 0.01:
        engine_mame_par = "-nothrottle"
    else:
        engine_mame_par = "-speed " + str(engine_rspeed)
    if not engine_rsound:
        engine_mame_par = engine_mame_par + " -sound none"
    if engine_rwindow is True:
        engine_mame_par = engine_mame_par + " -window"
    elif engine_rwindow is False:
        engine_mame_par = engine_mame_par + " -nowindow"
    return engine_mame_par


# Game pgn header keys we want to keep and ensure
important_header_keys = {"Event", "Site", "Date", "Round", "White", "Black", "WhiteElo", "BlackElo", "Result"}


def keep_essential_headers(headers: dict) -> dict:
    """Return a cleaned dict with only the standard PGN headers to keep."""
    return {k: v for k, v in headers.items() if k in important_header_keys}


def ensure_important_headers(headers: dict) -> None:
    """Ensure standard PGN headers exist, filling headers dict with '?' if missing"""
    for key in important_header_keys:
        if key not in headers:
            headers[key] = "?"
