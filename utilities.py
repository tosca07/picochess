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
import queue
import os
import platform
import urllib.request
import socket
import json
import time
import copy
import configparser
import subprocess

from threading import Timer
from subprocess import Popen, PIPE

from dgt.translate import DgtTranslate
from dgt.api import Dgt
from ctypes import cdll, c_int

from configobj import ConfigObj, ConfigObjError, DuplicateError  # type: ignore

from typing import Optional

# picochess version
version = '3.3'

evt_queue: queue.Queue = queue.Queue()
dispatch_queue: queue.Queue = queue.Queue()

msgdisplay_devices = []
dgtdisplay_devices = []


class Observable(object):

    """Input devices are observable."""

    def __init__(self):
        super(Observable, self).__init__()

    @staticmethod
    def fire(event):
        """Put an event on the Queue."""
        evt_queue.put(copy.deepcopy(event))


class DispatchDgt(object):

    """Input devices are observable."""

    def __init__(self):
        super(DispatchDgt, self).__init__()

    @staticmethod
    def fire(dgt):
        """Put an event on the Queue."""
        dispatch_queue.put(copy.deepcopy(dgt))


class DisplayMsg(object):

    """Display devices (DGT XL clock, Piface LCD, pgn file...)."""

    def __init__(self):
        super(DisplayMsg, self).__init__()
        self.msg_queue = queue.Queue()
        msgdisplay_devices.append(self)

    @staticmethod
    def show(message):
        """Send a message on each display device."""
        for display in msgdisplay_devices:
            display.msg_queue.put(copy.deepcopy(message))


class DisplayDgt(object):

    """Display devices (DGT XL clock, Piface LCD, pgn file...)."""

    def __init__(self):
        super(DisplayDgt, self).__init__()
        self.dgt_queue = queue.Queue()
        dgtdisplay_devices.append(self)

    @staticmethod
    def show(message):
        """Send a message on each display device."""
        for display in dgtdisplay_devices:
            display.dgt_queue.put(copy.deepcopy(message))


class RepeatedTimer(object):

    """Call function on a given interval."""

    def __init__(self, interval, function, *args, **kwargs):
        self._timer = None
        self.interval = interval
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.timer_running = False

    def _run(self):
        self.timer_running = False
        self.start()
        self.function(*self.args, **self.kwargs)

    def is_running(self):
        """Return the running status."""
        return self.timer_running

    def start(self):
        """Start the RepeatedTimer."""
        if not self.timer_running:
            self._timer = Timer(self.interval, self._run)
            self._timer.start()
            self.timer_running = True
        else:
            logging.info('repeated timer already running - strange!')

    def stop(self):
        """Stop the RepeatedTimer."""
        if self.timer_running:
            self._timer.cancel()
            self.timer_running = False
        else:
            logging.info('repeated timer already stopped - strange!')


def get_opening_books():
    """Build an opening book lib."""
    config = configparser.ConfigParser()
    config.optionxform = str
    program_path = os.path.dirname(os.path.realpath(__file__)) + os.sep
    book_path = program_path + 'books'
    config.read(book_path + os.sep + 'books.ini')

    library = []
    for section in config.sections():
        text = Dgt.DISPLAY_TEXT(web_text=config[section]['large'], large_text=config[section]['large'], medium_text=config[section]['medium'], small_text=config[section]['small'],
                                wait=True, beep=False, maxtime=0, devs={'ser', 'i2c', 'web'})
        library.append(
            {
                'file': 'books' + os.sep + section,
                'text': text
            }
        )
    return library


def hms_time(seconds: int):
    """Transfer a seconds integer to hours,mins,secs."""
    if seconds < 0:
        logging.warning('negative time %i', seconds)
        return 0, 0, 0
    mins, secs = divmod(seconds, 60)
    hours, mins = divmod(mins, 60)
    return hours, mins, secs


def do_popen(command, log=True, force_en_env=False):
    """Connect via Popen and log the result."""
    if force_en_env:  # force an english environment
        force_en_env = os.environ.copy()
        force_en_env['LC_ALL'] = 'C'
        stdout, stderr = Popen(command, stdout=PIPE, stderr=PIPE, env=force_en_env).communicate()
    else:
        stdout, stderr = Popen(command, stdout=PIPE, stderr=PIPE).communicate()
    if log:
        logging.debug([output.decode(encoding='UTF-8') for output in [stdout, stderr]])
    return stdout.decode(encoding='UTF-8')


def git_name():
    """Get the git execute name."""
    return 'git.exe' if platform.system() == 'Windows' else 'git'


def get_tags():
    """Get the last 3 tags from git."""
    git = git_name()
    tags = [(tags, tags[1] + tags[-2:]) for tags in do_popen([git, 'tag'], log=False).split('\n')[-4:-1]]
    return tags  # returns something like [('v0.9j', 09j'), ('v0.9k', '09k'), ('v0.9l', '09l')]


def checkout_tag(tag):
    """Update picochess by tag from git."""
    git = git_name()
    do_popen([git, 'checkout', tag])
    do_popen(['pip3', 'install', '-r', 'requirements.txt'])


def update_picochess(dgtpi: bool, auto_reboot: bool, dgttranslate: DgtTranslate):
    """Update picochess from git."""
    git = git_name()

    branch = do_popen([git, 'rev-parse', '--abbrev-ref', 'HEAD'], log=False).rstrip()
    if branch == 'master':
        # Fetch remote repo
        do_popen([git, 'remote', 'update'])
        # Check if update is needed - need to make sure, we get english answers
        output = do_popen([git, 'status', '-uno'], force_en_env=True)
        if 'up-to-date' not in output and 'Your branch is ahead of' not in output:
            DispatchDgt.fire(dgttranslate.text('Y25_update'))
            # Update
            logging.debug('updating picochess')
            do_popen([git, 'pull', 'origin', branch])
            do_popen(['pip3', 'install', '-r', 'requirements.txt'])
            if auto_reboot:
                reboot(dgtpi, dev='web')
            else:
                time.sleep(2)  # give time to display the "update" message
        else:
            logging.debug('no update available')
    else:
        logging.warning('wrong branch %s', branch)


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

def exit(dgtpi: bool, dev: str):
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
        os.system("sudo systemctl stop picochess")
    else:
        os.system("sudo pkill -f chromium")


def reboot(dgtpi: bool, dev: str):
    """Reboot picochess."""
    logging.debug('rebooting system requested by (%s)', dev)
    
    time.sleep(5)  # give some time to send out the pgn file or speak the event
    if platform.system() == 'Windows':
        os.system('shutdown /r')
    elif dgtpi:
        os.system('sudo reboot')
    else:
        os.system('sudo reboot')


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
            response = urllib.request.urlopen('https://get.geojs.io/v1/ip/geo.json')
            j = json.loads(response.read().decode())

            country_name = j.get('country', '')
            country_code = j.get('country_code', '')
            city = j.get('city', '')
            ext_ip = j.get('IPv4', None)

            return f"{city}, {country_name} {country_code}", ext_ip, int_ip
        except Exception:
            pass
    return '?', None, None


def write_picochess_ini(key: str, value):
    """Update picochess.ini config file with key/value."""
    try:
        config = ConfigObj('picochess.ini', default_encoding='utf8')
        config[key] = value
        config.write()
    except (ConfigObjError, DuplicateError) as conf_exc:
        logging.exception(conf_exc)


def get_engine_mame_par(engine_rspeed: float, engine_rsound=False) -> str:
    if engine_rspeed < 0.01:
        engine_mame_par = '-nothrottle'
    else:
        engine_mame_par = '-speed ' + str(engine_rspeed)
    if not engine_rsound:
        engine_mame_par = engine_mame_par + ' -sound none'
    return engine_mame_par
