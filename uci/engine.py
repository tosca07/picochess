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

import os
from typing import Optional
import logging
import configparser
import spur  # type: ignore
import paramiko

from subprocess import DEVNULL
from dgt.api import Event
from utilities import Observable
import chess.uci  # type: ignore
from chess import Board  # type: ignore
from uci.informer import Informer
from uci.rating import Rating, Result
from utilities import write_picochess_ini

UCI_ELO = "UCI_Elo"
UCI_ELO_NON_STANDARD = "UCI Elo"

logger = logging.getLogger(__name__)


class WindowsShellType:
    """Shell type supporting Windows for spur."""

    supports_which = True

    def generate_run_command(self, command_args, store_pid, cwd=None, update_env={}, new_process_group=False):
        if new_process_group:
            raise spur.ssh.UnsupportedArgumentError("'new_process_group' is not supported when using a windows shell")

        commands = []
        if command_args[0] == "kill":
            command_args = self.generate_kill_command(command_args[-1]).split()

        if store_pid:
            commands.append("powershell (Get-WmiObject Win32_Process -Filter ProcessId=$PID).ParentProcessId")

        if cwd is not None:
            commands.append(
                "cd {0} 2>&1 || ( echo. & echo spur-cd: %errorlevel% & exit 1 )".format(self.win_escape_sh(cwd))
            )
            commands.append("echo. & echo spur-cd: 0")

        update_env_commands = ["SET {0}={1}".format(key, value) for key, value in update_env.items()]
        commands += update_env_commands
        commands.append(
            "( (powershell Get-Command {0} > nul 2>&1) && echo 0) || (echo %errorlevel% & exit 1)".format(
                self.win_escape_sh(command_args[0])
            )
        )

        commands.append(" ".join(command_args))
        return " & ".join(commands)

    def generate_kill_command(self, pid):
        return "taskkill /F /PID {0}".format(pid)

    @staticmethod
    def win_escape_sh(value):
        return '"' + value + '"'


class UciShell(object):
    """Handle the uci engine shell."""

    def __init__(self, hostname=None, username=None, key_file=None, password=None, windows=False):
        super(UciShell, self).__init__()
        if hostname:
            logger.info("connecting to [%s]", hostname)
            shell_params = {
                "hostname": hostname,
                "username": username,
                "missing_host_key": paramiko.AutoAddPolicy(),
            }
            if key_file:
                shell_params["private_key_file"] = key_file
            else:
                shell_params["password"] = password
            if windows:
                shell_params["shell_type"] = WindowsShellType()

            self._shell = spur.SshShell(**shell_params)
        else:
            self._shell = None

    def __getattr__(self, attr):
        """Dispatch unknown attributes to SshShell."""
        return getattr(self._shell, attr)

    def get(self):
        return self if self._shell is not None else None


class UciEngine(object):

    """Handle the uci engine communication."""

    def __init__(self, file: str, uci_shell: UciShell, mame_par: str):
        super(UciEngine, self).__init__()
        logger.info("mame parameters=" + mame_par)
        try:
            self.is_adaptive = False
            self.is_mame = False
            self.engine_rating = -1
            self.uci_elo_eval_fn = None  # saved UCI_Elo eval function
            self.shell = uci_shell.get()
            logger.info("file " + file)
            if "/mame/" in file:
                self.is_mame = True
                mfile = [file, mame_par]
                logger.info(mfile)
            else:
                mfile = [file]
                logger.info(mfile)
            if self.shell:
                self.engine = chess.uci.spur_spawn_engine(self.shell, mfile)
            else:
                self.engine = chess.uci.popen_engine(mfile, stderr=DEVNULL)

            self.file = file
            if self.engine:
                handler = Informer()
                self.engine.info_handlers.append(handler)
                self.engine.uci()
            else:
                logger.error("engine executable [%s] not found", file)
            self.options: dict = {}
            self.future = None
            self.show_best = True

            self.res = None
            self.level_support = False
        except OSError:
            logger.exception("OS error in starting engine")
        except TypeError:
            logger.exception("engine executable not found")

    def get_name(self):
        """Get engine name."""
        return self.engine.name

    def get_options(self):
        """Get engine options."""
        return self.engine.options

    def get_pgn_options(self):
        """Get options."""
        return self.options

    def option(self, name, value):
        """Set OptionName with value."""
        self.options[name] = value

    def send(self):
        """Send options to engine."""
        self.engine.setoption(self.options)

    def has_levels(self):
        """Return engine level support."""
        has_lv = self.has_skill_level() or self.has_handicap_level() or self.has_limit_strength() or self.has_strength()
        return self.level_support or has_lv

    def has_skill_level(self):
        """Return engine skill level support."""
        return "Skill Level" in self.engine.options

    def has_handicap_level(self):
        """Return engine handicap level support."""
        return "Handicap Level" in self.engine.options

    def has_limit_strength(self):
        """Return engine limit strength support."""
        return "UCI_LimitStrength" in self.engine.options

    def has_strength(self):
        """Return engine strength support."""
        return "Strength" in self.engine.options

    def has_chess960(self):
        """Return chess960 support."""
        return "UCI_Chess960" in self.engine.options

    def has_ponder(self):
        """Return ponder support."""
        return "Ponder" in self.engine.options

    def get_file(self):
        """Get File."""
        return self.file

    def position(self, game: Board):
        """Set position."""
        self.engine.position(game)

    def quit(self):
        """Quit engine."""
        if self.engine.quit():  # Ask nicely
            if self.engine.terminate():  # If you won't go nicely....
                if self.is_mame:
                    os.system("sudo pkill -9 -f mess")
                else:
                    if self.engine.kill():  # Right that does it!
                        return False
        return True

    def uci(self):
        """Send start uci command."""
        self.engine.uci()

    def stop(self, show_best=False):
        """Stop engine."""
        logger.info("show_best old: %s new: %s", self.show_best, show_best)
        self.show_best = show_best
        if self.is_waiting():
            logger.info("engine already stopped")
            return self.res
        try:
            self.engine.stop()
        except chess.uci.EngineTerminatedException:
            logger.error("Engine terminated")  # @todo find out, why this can happen!
        return self.future.result()

    def pause_pgn_audio(self):
        """Stop engine."""
        logger.info("pause audio old")
        try:
            self.engine.uci()
        except chess.uci.EngineTerminatedException:
            logger.error("Engine terminated")  # @todo find out, why this can happen!

    def go(self, time_dict: dict):
        """Go engine."""
        self.show_best = True
        time_dict["async_callback"] = self.callback
        logger.debug("molli: timedict: %s", str(time_dict))
        # Observable.fire(Event.START_SEARCH())
        self.future = self.engine.go(**time_dict)
        return self.future

    def go_emu(self):
        """Go engine."""
        logger.debug("molli: go_emu")
        self.future = self.engine.go(async_callback=self.callback)

    def ponder(self):
        """Ponder engine."""
        self.show_best = False

        # Observable.fire(Event.START_SEARCH())
        self.future = self.engine.go(ponder=True, infinite=True, async_callback=self.callback)
        return self.future

    def brain(self, time_dict: dict):
        """Permanent brain."""
        self.show_best = True
        time_dict["ponder"] = True
        time_dict["async_callback"] = self.callback3

        # Observable.fire(Event.START_SEARCH())
        self.future = self.engine.go(**time_dict)
        return self.future

    def hit(self):
        """Send a ponder hit."""
        logger.info("show_best: %s", self.show_best)
        self.engine.ponderhit()
        self.show_best = True

    def callback(self, command):
        """Callback function."""
        try:
            self.res = command.result()
        except chess.uci.EngineTerminatedException:
            logger.error("Engine terminated")  # @todo find out, why this can happen!
            self.show_best = False
        logger.info("res: %s", self.res)
        # Observable.fire(Event.STOP_SEARCH())
        if self.show_best and self.res:
            Observable.fire(Event.BEST_MOVE(move=self.res.bestmove, ponder=self.res.ponder, inbook=False))
        else:
            logger.info("event best_move not fired")

    def callback3(self, command):
        """Callback function."""
        try:
            self.res = command.result()
        except chess.uci.EngineTerminatedException:
            logger.error("Engine terminated")  # @todo find out, why this can happen!
            self.show_best = False
        logger.info("res: %s", self.res)
        # Observable.fire(Event.STOP_SEARCH())
        if self.show_best and self.res:
            Observable.fire(Event.BEST_MOVE(move=self.res.bestmove, ponder=self.res.ponder, inbook=False))
        else:
            logger.info("event best_move not fired")

    def is_thinking(self):
        """Engine thinking."""
        return not self.engine.idle and not self.engine.pondering

    def is_pondering(self):
        """Engine pondering."""
        return not self.engine.idle and self.engine.pondering

    def is_waiting(self):
        """Engine waiting."""
        return self.engine.idle

    def is_ready(self):
        """Engine waiting."""
        return self.engine.isready()

    def newgame(self, game: Board):
        """Engine sometimes need this to setup internal values."""
        self.engine.ucinewgame()
        self.engine.position(game)

    def mode(self, ponder: bool, analyse: bool):
        """Set engine mode."""
        self.engine.setoption({"Ponder": ponder, "UCI_AnalyseMode": analyse})

    def startup(self, options: dict, rating: Optional[Rating] = None):
        """Startup engine."""
        parser = configparser.ConfigParser()

        if not options:
            if self.shell is None:
                success = bool(parser.read(self.get_file() + ".uci"))
            else:
                try:
                    with self.shell.open(self.get_file() + ".uci", "r") as file:
                        parser.read_file(file)
                    success = True
                except FileNotFoundError:
                    success = False
            if success:
                options = dict(parser[parser.sections().pop()])

        self.level_support = bool(options)

        self.options = options.copy()
        self._engine_rating(rating)
        logger.debug("setting engine with options %s", self.options)
        self.send()

        logger.debug("Loaded engine [%s]", self.get_name())
        logger.debug("Supported options [%s]", self.get_options())

    def _engine_rating(self, rating: Optional[Rating] = None):
        """
        Set engine_rating; replace UCI_Elo 'auto' value with rating.
        Delete UCI_Elo from the options if no rating is given.
        """
        uci_elo_option_string = None
        if UCI_ELO in self.options:
            uci_elo_option_string = UCI_ELO
        elif UCI_ELO_NON_STANDARD in self.options:
            uci_elo_option_string = UCI_ELO_NON_STANDARD
        if uci_elo_option_string is not None:
            uci_elo_option = self.options[uci_elo_option_string].strip()
            if uci_elo_option.lower() == "auto" and rating is not None:
                self._set_rating(self._round_engine_rating(int(rating.rating)))
            elif uci_elo_option.isnumeric():
                self.engine_rating = int(uci_elo_option)
            elif "auto" in uci_elo_option and rating is not None:
                uci_elo_with_rating = uci_elo_option.replace("auto", str(int(rating.rating)))
                try:
                    evaluated = eval(uci_elo_with_rating)
                    if str(evaluated).isnumeric():
                        self._set_rating(int(evaluated))
                        self.uci_elo_eval_fn = uci_elo_option  # save evaluation function for updating engine ELO later
                    else:
                        del self.options[uci_elo_option_string]
                except Exception as e:  # noqa - catch all exceptions for eval()
                    logger.error(f"invalid option set for {uci_elo_option_string}={uci_elo_with_rating}, exception={e}")
                    del self.options[uci_elo_option_string]
            else:
                del self.options[uci_elo_option_string]

    def _set_rating(self, value: int):
        self.engine_rating = value
        self._set_uci_elo_to_engine_rating()
        self.is_adaptive = True

    def _round_engine_rating(self, value: int) -> int:
        """Round the value up to the next 50, minimum=500"""
        return max(500, int(value / 50 + 1) * 50)

    def update_rating(self, rating: Rating, result: Result) -> Rating:
        """Send the new ELO value to the engine and save the ELO and rating deviation"""
        if not self.is_adaptive or result is None or self.engine_rating < 0:
            return rating
        new_rating = rating.rate(Rating(self.engine_rating, 0), result)
        if self.uci_elo_eval_fn is not None:
            # evaluation function instead of auto?
            self.engine_rating = eval(self.uci_elo_eval_fn.replace("auto", str(int(new_rating.rating))))
        else:
            self.engine_rating = self._round_engine_rating(int(new_rating.rating))
        self._save_rating(new_rating)
        self._set_uci_elo_to_engine_rating()
        self.send()
        return new_rating

    def _set_uci_elo_to_engine_rating(self):
        if UCI_ELO in self.options:
            self.options[UCI_ELO] = str(int(self.engine_rating))
        elif UCI_ELO_NON_STANDARD in self.options:
            self.options[UCI_ELO_NON_STANDARD] = str(int(self.engine_rating))

    def _save_rating(self, new_rating: Rating):
        write_picochess_ini("pgn-elo", max(500, int(new_rating.rating)))
        write_picochess_ini("rating-deviation", int(new_rating.rating_deviation))
