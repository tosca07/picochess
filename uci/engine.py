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

import asyncio
import os
from typing import Optional
import logging
import configparser
import re
from enum import Enum
import copy

import spur  # type: ignore
import paramiko

import chess.engine  # type: ignore
from chess.engine import Limit
from chess import Board  # type: ignore
from uci.rating import Rating, Result
from utilities import write_picochess_ini

# settings are for engine thinking limits
FLOAT_MAX_ENGINE_TIME = 2.0  # engine max thinking time
FLOAT_MIN_ENGINE_TIME = 0.1  # engine min thinking time
INT_EXPECTED_GAME_LENGTH = 100  # divide thinking time over expected game length

FLOAT_ANALYSIS_WAIT = 0.1  # save CPU in ContinuousAnalysis

UCI_ELO = "UCI_Elo"
UCI_ELO_NON_STANDARD = "UCI Elo"
UCI_ELO_NON_STANDARD2 = "UCI_Limit"

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


class ContinuousAnalysis:
    """ class for continous analysis from a chess engine """
    def __init__(self,
                 engine: chess.engine.SimpleEngine,
                 delay: float,
                 loop: asyncio.AbstractEventLoop,
                 engine_debug_name: str
                 ):
        """
        A continuous analysis generator that runs as a background async task.

        :param delay: Time interval to do CPU saving sleep between analysis.
        """
        self.engine = None
        self.game = None  # latest position requested to be analysed
        self.limit_reached = False  # True when limit reached for position
        self.current_game = None  # latest position being analysed
        self.delay = delay
        self._running = False
        self._task = None
        self._analysis_data = None  # "best" InfoDict list
        self._first_data = None  # "low" InfoDict list
        self.loop = loop  # main loop everywhere
        self.whoami = engine_debug_name  # picotutor or engine
        self._first_low_kwargs: dict | None = None  # set in start
        self._normal_deep_kwargs: dict | None = None  # set in start
        self.lock = asyncio.Lock()
        self.pause_event = asyncio.Event()
        self.pause_event.set()  # Start unpaused
        self.engine = engine
        if not self.engine:
            logger.error("%s ContinuousAnalysis initialised without engine", self.whoami)


    async def play_move(self,
                        game: Board,
                        limit: Limit,
                        pondering: bool
                        ) -> chess.engine.PlayResult:
        """Plays the best move and updates the board."""
        result = None
        self.pause_event.clear()  # Pause analysis
        try:
            async with self.lock:
                result = await self.engine.play(copy.deepcopy(game), limit=limit, ponder=pondering)
            # @todo we could update the current game here
            # so that analysis on user turn would start immediately
        except chess.engine.EngineTerminatedError:
            logger.error("Engine terminated")
        finally:
            self.pause_event.set()  # Resume analysis
        return result


    async def _watching_analyse(self):
        """Internal function for continuous analysis in the background."""
        debug_once_limit = True
        debug_once_game = True
        self.limit_reached = False  # True when depth limit reached for position
        while self._running:
            try:
                if self.limit_reached:
                    if debug_once_limit:
                        logger.debug("%s ContinuousAnalyser analysis limited", self.whoami)
                        debug_once_limit = False  # dont flood log
                    await asyncio.sleep(self.delay)
                    continue
                if not self._game_analysable(self.game):
                    if debug_once_game:
                        logger.debug("%s ContinuousAnalyser no game to analyse", self.whoami)
                        debug_once_game = False  # dont flood log
                    await asyncio.sleep(self.delay)
                    continue
                # new position - start with new current_game and empty data
                async with self.lock:
                    self.current_game = self.game.copy()
                    self._analysis_data = self._first_data = None
                self.limit_reached = await self._analyse_position()
            except asyncio.CancelledError:
                logger.debug("%s ContinuousAnalyser cancelled", self.whoami)
                # same situation as in stop
                self._task = None
                self._running = False

    
    async def _analyse_position(self)->bool:
        """ analyse while position stays same or limit reached
            returns True if limit was reached for this position """
        first = True
        while self._running and self.current_game.fen() == self.game.fen():
            if first and self._first_low_kwargs:
                kwargs = self._first_low_kwargs
            else: # normal deep analysis
                kwargs = self._normal_deep_kwargs
                first = False  # deep has only one call to forever
            try:
                await self._analyse_forever(first, kwargs)
                if not first:
                    return True  # limit reached, done with this position
            except chess.engine.AnalysisComplete:
                logger.debug("ContinuousAnalyser ran out of information")
                asyncio.sleep(self.delay)  # maybe it helps to wait some extra?
            finally:
                first = False  # no longer first _analyse_forever call
        return False  # limit not reached, position changed



    async def _analyse_forever(self, first: bool=False, kwargs: dict | None = None):
        """ analyse forever if no kwargs Limit sent
            if first is True store an extra first low result """
        if kwargs:
            limit: chess.engine.Limit = kwargs["limit"] if "limit" in kwargs else None
            multipv: int = kwargs["multipv"] if "multipv" in kwargs else None
        else:
            limit = None
            multipv = None
        with await self.engine.analysis(self.current_game, limit=limit, multipv=multipv) as analysis:
            async for info in analysis:
                await self.pause_event.wait()  # Wait if analysis is paused
                async with self.lock:
                    # after waiting, check if position has changed
                    if self.current_game.fen() != self.game.fen():
                        self._analysis_data = self._first_data = None
                        return  # old position, quit analysis
                    updated = self._update_analysis_data(first, analysis)  # update to latest
                    if updated:
                        #  self.debug_analyser()  # normally commented out
                        if limit:
                            # @todo change 0 to -1 to get all multipv finished
                            if first:
                                info_limit: chess.engine.InfoDict = self._first_data[0]
                            else:
                                info_limit: chess.engine.InfoDict = self._analysis_data[0]
                            if "depth" in info_limit and limit.depth:
                                if info_limit.get("depth") >= limit.depth:
                                    return  # limit reached
                await asyncio.sleep(self.delay)  # save cpu
                # else just wait for info so that we get updated True


    def debug_analyser(self):
        """ use this debug call to see how low and deep depth evolves """
        # lock is on when we come here
        if self._first_data:
            i: chess.engine.InfoDict = self._first_data[0]
            if "depth" in i:
                logger.debug("%s ContinuousAnalyser low depth: %d",
                            self.whoami, i.get("depth")
                            )
        if self._analysis_data:
            j: chess.engine.InfoDict = self._analysis_data[0]
            if "depth" in j:
                logger.debug("%s ContinuousAnalyser deep depth: %d",
                            self.whoami, j.get("depth")
                            )

    def _update_analysis_data(self,
                              first: bool,
                              analysis: chess.engine.AnalysisResult)->bool:
        """ internal function for updating while analysing 
            returns True if data was updated """
        # lock is on when we come here
        result = False
        if analysis.multipv:
            if first:
                self._first_data = analysis.multipv
            # always update even though its sometimes same as first
            self._analysis_data = analysis.multipv
            result = True
        return result


    def _game_analysable(self, game: chess.Board) -> bool:
        """ return True if game is analysable """
        if game is None:
            return False
        if game.is_game_over():
            return False
        if game.fen() == chess.Board.starting_fen:
            return False
        # @todo skip while in book? or is that main loops logic?
        return True


    def start(self,
              game: chess.Board,
              normal_deep_kwargs: dict | None = None,
              first_low_kwargs: dict | None = None
              ):
        """
        Starts the analysis. You may ask for two rounds by giving
        an extra first_low_kwargs, typically with low limit like limit=5
        Normal one will be deep and is run after optional first low

        :param engine: An instance of SimpleEngine managed externally.
        :param game: The current chess board (game) to analyze.
        :param normal_deep_kwargs: limit the analysis, None means forever
        :param first_low_kwargs: optional limit to get a first low analysis
        """
        if not self._running:
            if not self.engine:
                logger.error("%s ContinuousAnalysis cannot start without engine", self.whoami)
            else:
                self.game = game.copy()  # remember this game position
                self.limit_reached = False  # True when limit reached for position
                self._first_low_kwargs = first_low_kwargs
                self._normal_deep_kwargs = normal_deep_kwargs
                self._running = True
                self._task = self.loop.create_task(self._watching_analyse())
                logging.debug("%s ContinuousAnalysis started", self.whoami)
        else:
            logging.info("%s ContinuousAnalysis already running - strange!", self.whoami)

    def stop(self):
        """Stops the continuous analysis."""
        if self._running:
            if self._task is not None:
                self._task.cancel()
                self._task = None
                self._running = False
                logging.debug("%s ContinuousAnalysis stopped", self.whoami)


    def get_fen(self) -> str:
        """ return the fen the analysis is based on """
        return self.current_game.fen() if self.current_game else ""


    async def get_analysis(self) -> dict:
        """ :return: deepcopied first low and latest best lists of InfoDict
            key 'low': first low limited shallow list of InfoDict (multipv)
            key 'best': a deep list of InfoDict (multipv)
        """
        # due to the nature of the async analysis update it
        # continues to update it all the time, deepcopy needed
        async with self.lock:
            result = { "low": copy.deepcopy(self._first_data),
                        "best": copy.deepcopy(self._analysis_data),
                        "fen": copy.deepcopy(self.current_game.fen())
                        }
            return result

    async def update_game(self, new_game: chess.Board):
        """ Updates the game for analysis in a thread-safe manner.
            Do not call if fen() is still the same """
        async with self.lock:
            self.game = new_game.copy()  # remember this game position
            self.limit_reached = False  # True when limit reached for position
            # dont reset self._analysis_data and self._first_data to None
            # let the main loop self._analyze_position manage it


    def is_running(self) -> bool:
        """
        Checks if the analysis is running.

        :return: True if analysis is running, otherwise False.
        """
        return self._running


    def get_current_game(self) -> Optional[chess.Board]:
        """
        Retrieves the current board being analyzed.

        :return: A copy of the current chess board or None if no board is set.
        """
        return self.current_game.copy() if self.current_game else None


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

    def __init__(self,
                file: str, uci_shell: UciShell,
                mame_par: str,
                loop: asyncio.AbstractEventLoop,
                engine_debug_name: str = "engine"
                 ):
        """ initialise engine with file and mame_par info """
        super(UciEngine, self).__init__()
        logger.info("mame parameters=%s", mame_par)
        self.idle = True
        self.pondering = False  # normal mode no pondering
        self.loop = loop  # main loop everywhere
        self.analyser: ContinuousAnalysis | None = None
        # previous existing attributes:
        self.is_adaptive = False
        self.engine_rating = -1
        self.uci_elo_eval_fn = None  # saved UCI_Elo eval function
        self.file = file
        self.mame_par = mame_par
        self.is_mame = "/mame/" in self.file
        self.transport: chess.engine.Protocol | None = None  # find out correct type
        self.engine: chess.engine.UciProtocol | None = None
        self.engine_name = "NN"
        self.options: dict = {}
        self.res: chess.engine.PlayResult = None
        self.level_support = False
        self.shell = None  # check if uci files can be used any more
        self.engine_debug_name = engine_debug_name
        self.engine_lock = asyncio.Lock()

    async def open_engine(self):
        """ Open engine. Call after __init__ """
        try:
            logger.info("file %s", self.file)
            if self.is_mame:
                mfile = [self.file, self.mame_par]
            else:
                mfile = [self.file]
            logger.info("mfile %s", mfile)
            logger.info("opening engine")
            self.transport, self.engine = await chess.engine.popen_uci(mfile)
            self.analyser = ContinuousAnalysis(
                engine=self.engine,
                delay=FLOAT_ANALYSIS_WAIT,
                loop=self.loop,
                engine_debug_name=self.engine_debug_name
                )
            if self.engine:
                if "name" in self.engine.id:
                    self.engine_name = self.engine.id["name"]
                    i = re.search(r"\W+", self.engine_name).start()
                    if i is not None:
                        self.engine_name = self.engine_name[:i]
            else:
                logger.error("engine executable %s not found", self.file)
        except OSError:
            logger.exception("OS error in starting engine %s", self.file)
        except TypeError:
            logger.exception("engine executable not found %s", self.file)
        except chess.engine.EngineTerminatedError:
            logger.exception("engine terminated - could not execute file %s", self.file)


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

    async def send(self):
        """Send options to engine."""
        try:
            await self.engine.configure(self.options)
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

    async def quit(self):
        """Quit engine."""
        if self.analyser.is_running():
            self.analyser.stop()
        await self.engine.quit() # Ask nicely
        # @todo not sure how to know if we can call terminate and kill?
        if self.is_mame:
            os.system("sudo pkill -9 -f mess")


    def stop(self):
        """ Stop background ContinuousAnalyser """
        if self.analyser.is_running() is not None:
            self.analyser.stop()


    def pause_pgn_audio(self):
        """Stop engine."""
        logger.warning("pause audio old - unclear what to do here - doing nothing")


    def get_engine_limit(self, time_dict: dict, game: Board) -> float:
        """ a simple algorithm to get engine thinking time 
            parameter game will not change """
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

    async def go(self, time_dict: dict, game: Board) -> chess.engine.PlayResult:
        """Go engine.
           parameter game will not change, it is deep copied """
        logger.debug("molli: timedict: %s", str(time_dict))
        use_time = self.get_engine_limit(time_dict, game)
        try:
            async with self.engine_lock:
                self.idle = False  # engine is going to be busy now
                limit: Limit = Limit(time=use_time)
                self.res = await self.analyser.play_move(game, limit, self.pondering)
        except chess.engine.EngineTerminatedError:
            logger.error("Engine terminated")  # @todo find out, why this can happen!
            self.res = None
        finally:
            self.idle = True  # engine idle again
        if self.res:
            logger.debug("res: %s", self.res)
            # not firing BEST_MOVE here because caller picochess fires it
        else:
            logger.error("engine terminated while trying to make a move")
        return self.res


    async def start_analysis(self, game: chess.Board,
                        normal_deep_kwargs: dict | None = None,
                        first_low_kwargs: dict | None = None
                        ) -> bool:
        """ start analyser - returns True if if it was already running
            in current game position, which means result can be expected

            parameters:
            normal_deep_kwargs: normal deep limit - use None for forever
               - a dict with limit and multipv
            first_low_kwargs: extra limited first low analysis
               - a dict with limit and multipv """
        result = False
        if self.analyser.is_running():
            if game.fen() != self.analyser.get_fen():
                await self.analyser.update_game(game)  # new position
            else:
                result = True  # was running - results to be expected
        else:
            if self.engine:
                async with self.engine_lock:
                    self.analyser.start(game,
                                        normal_deep_kwargs,
                                        first_low_kwargs
                                        )
            else:
                logger.warning("start analysis requested but no engine loaded")
        return result


    def is_analyser_running(self) -> bool:
        """ check if analyser is running """
        return self.analyser.is_running()

    async def get_analysis(self, game: chess.Board) -> dict:
        """ key 'first': first low/quick list of InfoDict (multipv)
            key 'last': newest list of InfoDict (multipv) """
        # failed answer is empty lists
        result = {"low": [], "best": [], "fen": ""}
        if self.analyser.is_running():
            if self.analyser.get_fen() == game.fen():
                result = await self.analyser.get_analysis()
            else:
                logger.debug("warning: analysis for old position")
                logger.debug("current new position is %s", game.fen())
        else:
            logger.debug("caller has forgot to start analysis")
        return result

    async def playmode_analyse(self, game: Board,
                               limit: chess.engine.Limit,
                               ) -> chess.engine.InfoDict | None:
        """ Get analysis update from playing engine
            parameter game will not change, it is deep copied """
        if self.idle is False:
            # protect engine against calls if its not idle
            return None
        try:
            async with self.engine_lock:
                self.idle = False  # engine is going to be busy now
                info = await self.engine.analyse(copy.deepcopy(game), limit)
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
        """Engine sometimes need this to setup internal values.
           parameter game will not change """
        # game param is kept here for backward and possible
        # future compatibility
        # example: if analyser is going to run forever the board
        # needs to be sent to it
        if self.analyser.is_running():
            # @todo we could send new board to analyser?
            # to avoid unnecessary stop and start?
            self.analyser.stop()


    def set_mode(self, ponder: bool = True):
        """ Set engine ponder mode for a playing engine """
        self.pondering = ponder  # True in BRAIN mode = Ponder On menu

    async def startup(self, options: dict, rating: Optional[Rating] = None):
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
        await self.send()

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

    async def update_rating(self, rating: Rating, result: Result) -> Rating:
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
        await self.send()
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
