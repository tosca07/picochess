# Copyright (C) 2013-2018 Jean-Francois Romang (jromang@posteo.de)
#                         Shivkumar Shivaji ()
#                         Jürgen Précour (LocutusOfPenguin@posteo.de)
#                         Johan Sjöblom (messier109@gmail.com)
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
import time
import configparser
import re
import threading
from enum import Enum

import spur  # type: ignore
import paramiko

import chess.engine  # type: ignore
from chess.engine import Limit
from chess import Board  # type: ignore
from uci.rating import Rating, Result
from utilities import write_picochess_ini
from picotutor_constants import DEEP_DEPTH

# settings are for engine thinking limits
FLOAT_MAX_ENGINE_TIME = 2.0  # engine max thinking time
FLOAT_MIN_ENGINE_TIME = 0.1  # engine min thinking time
INT_EXPECTED_GAME_LENGTH = 100  # divide thinking time over expected game length

# how long the chess engine should analyse
# WATCHING
FLOAT_ANALYSIS_WAIT = 0.2  # save CPU by waiting between update calls to analysis()
# PLAYING
FLOAT_ANALYSE_LIMIT = 0.1  # asking for hint while not pondering
FLOAT_ANALYSE_PONDER_LIMIT = 0.05 # asking for a hint when pondering

UCI_ELO = "UCI_Elo"
UCI_ELO_NON_STANDARD = "UCI Elo"
UCI_ELO_NON_STANDARD2 = "UCI_Limit"

logger = logging.getLogger(__name__)

class EngineMode(Enum):
    """ represent modes of using chess engine """
    PLAYING = 1  # user plays engine
    WATCHING = 2  # engine is observing/analysing, user plays both sides



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


class ContinuousAnalysis:
    """ class for continous analysis from a chess engine """
    def __init__(self, delay: float):
        """
        A continuous analysis generator that runs in a background thread.

        :param delay: Time interval between each analysis iteration (in seconds).
        """
        self.engine = None
        self.game = None
        self.delay = delay
        self.first_limit = Limit or None  # set in start
        self.multipv = int or None # set in start
        self.first_multipv = int or None # set in start
        self.running = False
        self.thread = None
        self._analysis_data = None  # "best" InfoDict list
        self._first_data = None  # "low" InfoDict list
        self.lock = threading.Lock()  # Protects both self.game and self._analysis_data

    def _analyze_position(self):
        """Internal function for continuous analysis in the background thread."""
        while self.running:  # outer loop runs while analyser is running
            with self.lock:
                current_game = self.game.copy() if self.game else None
                self._analysis_data = self._first_data = None  # new position
            if not self._game_analysable(current_game):
                time.sleep(self.delay)
                continue
            first = True  # first analysis iteration
            limit = self.first_limit if self.first_limit else Limit(depth=DEEP_DEPTH)
            multipv = self.first_multipv if self.first_multipv else self.multipv
            while self.running and current_game.fen() == self.game.fen():
                try:  # inner loop runs while position stays same
                    with self.engine.analysis(current_game, limit=limit, multipv=multipv) as analysis:
                        with self.lock:
                            if current_game.fen() != self.game.fen():
                                self._analysis_data = self._first_data = None
                                break  # old position, break inner loop
                            self._update_analysis_data(first, analysis)
                        time.sleep(self.delay)  # Short pause
                        first = False  # after first settings
                        limit = Limit(depth=DEEP_DEPTH)  # more depth after first quick
                        multipv = self.multipv
                except chess.engine.AnalysisComplete:
                    time.sleep(self.delay)  # maybe it helps to wait some extra?
                    logger.debug("ContinousAnalyser ran out of information")


    def _update_analysis_data(self, first: bool,
                         analysis: chess.engine.SimpleAnalysisResult):
        """ internal function for updating in main loop
            _analyze_position - main loop manages the lock """
        if analysis.multipv:
            if first:
                self._first_data = analysis.multipv
            # always update even though its sometimes same as first
            self._analysis_data = analysis.multipv
        else:
            # first (low) stays - only mainloop resets both to None
            self._analysis_data = []


    def _game_analysable(self, game: chess.Board) -> bool:
        """ return True if game is analysable """
        if game is None:
            logger.warning("no game to analyse")
            return False
        elif game.is_game_over():
            logger.warning("nothing to analyse since game is over")
            return False
        # @ todo if current_game is starting position continue
        # then perhaps newgame() dont need to stop this thread
        # as it would stop analysing by itself
        # even better if we could detect if book is played
        return True


    def start(self, engine: chess.engine.SimpleEngine,
              game: chess.Board,
              first_limit: Limit | None = None,
              multipv: int | None = None,
              first_multipv: int | None = None):
        """
        Starts the analysis in a separate thread.

        :param engine: An instance of SimpleEngine managed externally.
        :param game: The current chess board (game) to analyze.
        :param first_limit optional to ask for first obvious moves analysis
        :param multipv: optional to ask for more than one root move
        """
        if not self.running:
            self.engine = engine
            self.game = game.copy()  # remember this game position
            self.first_limit = first_limit  # use this limit for first analysis call
            self.multipv = multipv
            self.first_multipv = first_multipv
            self.running = True
            self.thread = threading.Thread(target=self._analyze_position, daemon=True)
            self.thread.start()

    def stop(self):
        """Stops the continuous analysis."""
        self.running = False
        if self.thread:
            self.thread.join()


    def get_fen(self) -> str:
        """ return the fen the analysis is based on """
        with self.lock:
            return self.game.fen() if self.game else ""


    def get_analysis(self) -> dict:
        """ :return: first and latest lists of InfoDict
            key 'first': first low quick list of InfoDict (multipv)
            key 'last': contains a deep list of InfoDict (multipv)
        """
        with self.lock:
            result = { "low": self._first_data,
                       "best": self._analysis_data,
                       "fen": self.game.fen()
                     }
            return result

    def update_game(self, new_game: chess.Board):
        """ Updates the game for analysis in a thread-safe manner.
            Do not call if fen() is still the same """
        with self.lock:
            assert(self.game.fen() != new_game.fen())  # can be removed
            self.game = new_game.copy()  # remember this game position
            # dont reset self._analysis_data and self._first_data to None
            # let the main loop self._analyze_position manage it


    def is_running(self) -> bool:
        """
        Checks if the analysis is running.

        :return: True if analysis is running, otherwise False.
        """
        return self.running

    def get_current_game(self) -> Optional[chess.Board]:
        """
        Retrieves the current board being analyzed.

        :return: A copy of the current chess board or None if no board is set.
        """
        with self.lock:
            return self.game.copy() if self.game else None


class UciEngine(object):

    """Handle the uci engine communication."""

    # The rewrite for the new python chess module:
    # This UciEngine class can be in two modes:
    # WATCHING = user plays both sides
    # - an analysis generator to ask latest info is running
    #   in this mode you can send multipv larger than zero
    #   which is what the PicoTutor instance will do
    #   in PicoTutor the PicoTutor engine is not playing
    #   its just watching
    # PLAYING = user plays against computer
    # - self.idle is False only when engine is playing it's best move
    # - self.res will remember latest play result (maybe never needed)
    # - self.pondering indicates if engine is to ponder
    #   without pondering analysis will be "static" one-timer

    def __init__(self, file: str, uci_shell: UciShell, mame_par: str,
                 first_limit: Limit | None = None,
                 multipv: int | None = None,
                 first_multipv: int | None = None):
        """  first_limit restricts first low analysis 
             multipv sets number of root moves in analysis """
        super(UciEngine, self).__init__()
        logger.info("mame parameters=" + mame_par)
        self.mode = EngineMode.PLAYING  # picochess starts in NORMAL mode
        self.idle = True
        self.pondering = False  # normal mode no pondering
        self.analyser = ContinuousAnalysis(delay=FLOAT_ANALYSIS_WAIT)
        # previous existing attributes:
        self.is_adaptive = False
        self.is_mame = False
        self.engine_rating = -1
        self.uci_elo_eval_fn = None  # saved UCI_Elo eval function
        self.first_limit = first_limit  # if !None this is for first analysis
        self.multipv = multipv  # used by Analysis()
        self.first_multipv = first_multipv  # used for first low obvious moves
        try:
            logger.info("file " + file)
            if "/mame/" in file:
                self.is_mame = True
                mfile = [file, mame_par]
                logger.info(mfile)
            else:
                mfile = [file]
                logger.info(mfile)
            self.file = file

            logger.info("opening engine")
            self.engine = chess.engine.SimpleEngine.popen_uci(mfile, debug=True)

            logger.debug("in new chess module UciShell is used differently")
            self.shell = None  # check if uci files can be used any more
            self.engine_name = "NN"
            if self.engine:
                # handler = Informer()
                # self.engine.info_handlers.append(handler)
                if "name" in self.engine.id:
                    self.engine_name = self.engine.id["name"]
                    i = re.search(r"\W+", self.engine_name).start()
                    if i is not None:
                        self.engine_name = self.engine_name[:i]
            else:
                logger.error("engine executable [%s] not found", file)
            self.options: dict = {}

            self.res = None
            self.level_support = False
        except OSError:
            logger.exception("OS error in starting engine")
        except TypeError:
            logger.exception("engine executable not found")


    def loaded_ok(self) -> bool:
        """ check if engine was loaded ok """
        return self.engine is not None

    def get_name(self) -> str:
        """Get engine name. Use engine_loaded_ok if you 
           want to check if engine is loaded"""
        return self.engine_name

    def get_options(self):
        """Get engine options."""
        return self.options

    def get_pgn_options(self):
        """Get options."""
        return self.options

    def option(self, name : str, value):
        """Set OptionName with value."""
        self.options[name] = value

    def send(self):
        """Send options to engine."""
        try:
            self.engine.configure(self.options)
        except Exception as e:
            logger.warning(e)

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

    def quit(self):
        """Quit engine."""
        if self.analyser.is_running():
            self.analyser.stop()
        if self.engine.quit():  # Ask nicely
            if self.engine.terminate():  # If you won't go nicely....
                if self.is_mame:
                    os.system("sudo pkill -9 -f mess")
                else:
                    if self.engine.kill():  # Right that does it!
                        return False
        return True

    def stop(self):
        """ In PLAYMODE wait for engine to stop thinking
            always stops analyser """
        if self.mode == EngineMode.WATCHING:
            if self.analyser.is_running() is not None:
                logger.debug("stop analyser")
                self.analyser.stop()
            else:
                logger.debug("no analyser running in stop")
        elif self.mode == EngineMode.PLAYING:
            if not self.idle:
                logger.debug("waiting synchronized for engine to play to be ready")
            while not self.idle:
                time.sleep(FLOAT_MIN_ENGINE_TIME/2)  # wait until engine finishes play
            if self.analyser.is_running():
                logger.debug("analyser thread running in PLAYING mode - stopping it")
                self.analyser.stop()


    def pause_pgn_audio(self):
        """Stop engine."""
        logger.warning("pause audio old - unclear what to do here - doing nothing")


    def get_engine_limit(self, time_dict: dict, game: Board) -> float:
        """ a simple algorithm to get engine thinking time """
        try:
            if game.turn == chess.WHITE:
                t = time_dict["wtime"]
            else:
                t = time_dict["btime"]
            use_time = float(t)
            use_time = use_time / 1000.0  # convert to seconds
            # divide usable time over first N moves
            max_moves_left = INT_EXPECTED_GAME_LENGTH - game.fullmove_number
            if max_moves_left > 0:
                use_time = use_time / max_moves_left
            # apply upper and lower limits
            if use_time > FLOAT_MAX_ENGINE_TIME:
                use_time = FLOAT_MAX_ENGINE_TIME
            elif use_time < FLOAT_MIN_ENGINE_TIME:
                use_time = FLOAT_MIN_ENGINE_TIME
        except Exception as e:
            use_time = 0.2  # fallback so that play does not stop
            logger.warning(e)
        return use_time

    def go(self, time_dict: dict, game: Board) -> chess.engine.PlayResult:
        """Go engine."""
        logger.debug("molli: timedict: %s", str(time_dict))
        if self.analyser.is_running():
            logger.debug("analyser should not be running when PLAYING")
            self.analyser.stop()
        # Observable.fire(Event.START_SEARCH())
        use_time = self.get_engine_limit(time_dict, game)
        try:
            # @todo: how does the user affect the ponder value in this call
            self.idle = False  # engine is going to be busy now
            self.res = self.engine.play(game, chess.engine.Limit(time=use_time), ponder=self.pondering)
        except chess.engine.EngineTerminatedError:
            logger.error("Engine terminated")  # @todo find out, why this can happen!
            self.res = None
        finally:
            self.idle = True  # engine idle again
        # Observable.fire(Event.STOP_SEARCH())
        if self.res:
            logger.debug("res: %s", self.res)
            # not firing BEST_MOVE here because caller picochess fires it
        else:
            logger.error("engine terminated while trying to make a move")
        return self.res


    def start_analysis(self, game: chess.Board) -> bool:
        """ start analyser - returns True if already running 
            in current game position - means result can be expected """
        result = False
        if self.analyser.is_running():
            if game.fen() != self.analyser.get_fen():
                self.analyser.update_game(game)  # new position
            else:
                result = True  # was running - results to be expected
        else:
            if self.engine:
                self.analyser.start(self.engine, game,
                                    first_limit=self.first_limit,
                                    multipv=self.multipv,
                                    first_multipv=self.first_multipv)
            else:
                logger.warning("start analysis requested but no engine loaded")
        return result


    def is_analyser_running(self) -> bool:
        """ check if analyser is running """
        return self.analyser.is_running()

    def get_analysis(self, game: chess.Board) -> dict:
        """ key 'first': first low/quick list of InfoDict (multipv)
            key 'last': newest list of InfoDict (multipv) """
        # failed answer is empty lists
        result = {"low": [], "best": [], "fen": ""}
        if self.analyser.is_running():
            if self.analyser.get_fen() == game.fen():
                result = self.analyser.get_analysis()
            else:
                logger.debug("warning: analysis for old position %s", self.analyser.get_fen())
                logger.debug("current new position is %s", game.fen())
        else:
            if self.engine:
                # mode might have changed, recover by starting analyser
                self.analyser.start(self.engine, game,
                                    first_limit=self.first_limit,
                                    multipv=self.multipv)
        return result

    def playmode_analyse(self, game: Board) -> chess.engine.InfoDict | None:
        """ Get analysis update from pondering engine - BRAIN mode """
        if self.idle is False:
            # protect engine against calls if its not idle
            return None
        try:
            self.idle = False  # engine is going to be busy now
            if self.pondering:
                limit = FLOAT_ANALYSE_PONDER_LIMIT  # shorter
            else:
                limit = FLOAT_ANALYSE_LIMIT  # longer
            info = self.engine.analyse(game, chess.engine.Limit(time=limit))
        except chess.engine.EngineTerminatedError:
            logger.error("Engine terminated")  # @todo find out, why this can happen!
            info = None
        finally:
            self.idle = True  # engine idle again
        return info

    def is_thinking(self):
        """Engine thinking."""
        # @ todo check if self.pondering should be removed
        return not self.idle and not self.pondering

    def is_pondering(self):
        """Engine pondering."""
        # in the new chess module we are possibly idle
        # but have to inform picochess.py that we could
        # be pondering anyway
        return self.pondering

    def is_waiting(self):
        """Engine waiting."""
        return self.idle

    def is_ready(self):
        """Engine waiting."""
        return True  # should not be needed any more

    def newgame(self, game: Board):
        """Engine sometimes need this to setup internal values."""
        if self.analyser.is_running():
            # @todo we could send new board to analyser?
            # to avoid unnecessary stop and start?
            self.analyser.stop()

    def set_mode(self, mode: int, ponder: bool = True):
        """Set engine mode."""
        self.mode = mode
        if self.mode == EngineMode.PLAYING:
            # Modes: NORMAL, BRAIN
            if self.analyser.is_running() is not None:
                self.analyser.stop()  # stop analysing - let ponder do it
            self.pondering = ponder  # True in BRAIN mode = Ponder On menu
        elif self.mode == EngineMode.WATCHING:
            # Modes: ANALYSIS = Hint On, OBSERVING, etc...
            # self.analyser will be started in start_analysis
            # pondering has no meaning in ANALYSIS - leave unchanged
            pass

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
        elif UCI_ELO_NON_STANDARD2 in self.options:
            uci_elo_option_string = UCI_ELO_NON_STANDARD2
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
        elif UCI_ELO_NON_STANDARD2 in self.options:
            self.options[UCI_ELO_NON_STANDARD2] = str(int(self.engine_rating))

    def _save_rating(self, new_rating: Rating):
        write_picochess_ini("pgn-elo", max(500, int(new_rating.rating)))
        write_picochess_ini("rating-deviation", int(new_rating.rating_deviation))
