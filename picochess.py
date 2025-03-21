#!/usr/bin/env python3

# Copyright (C) 2013-2018 Jean-Francois Romang (jromang@posteo.de)
#                         Shivkumar Shivaji ()
#                         Jürgen Précour (LocutusOfPenguin@posteo.de)
#                         Wilhelm
#                         Dirk ("Molli")
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


import sys
import os
import subprocess
import copy
import gc
import logging
from logging.handlers import RotatingFileHandler
import time
import math
from typing import Any, List, Optional, Set, Tuple
import asyncio
from pathlib import Path
import platform

import paramiko
import chess.pgn
import chess.polyglot
from tornado.platform.asyncio import AsyncIOMainLoop
from chess.engine import InfoDict, Limit
import dgt.util

from configuration import Configuration
from uci.engine import UciShell, UciEngine
from uci.engine_provider import EngineProvider
from uci.rating import Rating, determine_result

from timecontrol import TimeControl
from theme import calc_theme
from utilities import (
    get_location,
    update_picochess,
    get_opening_books,
    shutdown,
    reboot,
    exit,
    checkout_tag,
)
from utilities import (
    Observable,
    DisplayMsg,
    version,
    evt_queue,
    write_picochess_ini,
    hms_time,
    get_engine_mame_par,
)
from utilities import AsyncRepeatingTimer, DispatchDgt
from pgn import Emailer, PgnDisplay, ModeInfo
from server import WebDisplay, WebServer, WebVr
from picotalker import PicoTalkerDisplay
from dispatcher import Dispatcher

from dgt.api import Message, Event
from dgt.util import GameResult, TimeMode, Mode, PlayMode, PicoComment, PicoCoach
from dgt.hw import DgtHw
from dgt.pi import DgtPi
from dgt.display import DgtDisplay
from dgt.board import DgtBoard, Rev2Info
from dgt.translate import DgtTranslate
from dgt.menu import DgtMenu
from eboard.eboard import EBoard
from eboard.chesslink.board import ChessLinkBoard
from eboard.chessnut.board import ChessnutBoard
from eboard.ichessone.board import IChessOneBoard
from eboard.certabo.board import CertaboBoard
from picotutor import PicoTutor

FLOAT_MIN_BACKGROUND_TIME = 1.5  # dont update analysis more often than this
# Limit analysis of engine
# ENGINE WATCHING
FLOAT_MAX_ANALYSIS_DEPTH = 27  # same famous limit as in deep blue 1997?
# ENGINE PLAYING
# Dont make the following large as it will block engine play go
FLOAT_MAX_ANALYSE_TIME = 0.1  # asking for hint while not pondering

ONLINE_PREFIX = "Online"

logger = logging.getLogger(__name__)


class AlternativeMover:
    """Keep track of alternative moves."""

    def __init__(self):
        self._excludedmoves = set()

    def all(self, game: chess.Board) -> Set[chess.Move]:
        """Get all remaining legal moves from game position."""
        searchmoves = set(game.legal_moves) - self._excludedmoves
        if not searchmoves:
            self.reset()
            return set(game.legal_moves)
        return searchmoves

    def book(self, bookreader: chess.polyglot.MemoryMappedReader, game_copy: chess.Board):
        """Get a BookMove or None from game position."""
        try:
            choice = bookreader.weighted_choice(game_copy, exclude_moves=self._excludedmoves)
        except IndexError:
            return None

        book_move = choice.move
        self.exclude(book_move)
        game_copy.push(book_move)
        try:
            choice = bookreader.weighted_choice(game_copy)
            book_ponder = choice.move
        except IndexError:
            book_ponder = None
        return chess.engine.BestMove(book_move, book_ponder)

    def check_book(self, bookreader, game_copy: chess.Board) -> bool:
        """Checks if a BookMove exists in current game position."""
        try:
            choice = bookreader.weighted_choice(game_copy)
        except IndexError:
            return False

        book_move = choice.move

        if book_move:
            return True
        else:
            return False

    def exclude(self, move) -> None:
        """Add move to the excluded move list."""
        self._excludedmoves.add(move)

    def reset(self) -> None:
        """Reset the exclude move list."""
        self._excludedmoves.clear()


class PicochessState:
    """Class to keep track of state in Picochess."""

    def __init__(self):
        self.automatic_takeback = False
        self.best_move_displayed = None
        self.best_move_posted = False
        self.book_in_use = ""
        self.comment_file = ""
        self.dgtmenu = None
        self.dgttranslate = None
        self.done_computer_fen = None
        self.done_move = chess.Move.null()
        self.engine_file = ""
        self.engine_text = None
        self.engine_level = ""
        self.new_engine_level = ""
        self.newgame_happened = False
        self.old_engine_level = ""
        self.error_fen = None
        self.fen_error_occured = False
        self.fen_timer: AsyncRepeatingTimer | None = None
        self.fen_timer_running = False
        self.flag_flexible_ponder = False
        self.flag_last_engine_emu = False
        self.flag_last_engine_online = False
        self.flag_last_engine_pgn = False
        self.flag_picotutor = True
        self.flag_pgn_game_over = False
        self.flag_premove = False
        self.flag_startup = False
        self.game = None or chess.Board()
        self.game_declared = False  # User declared resignation or draw
        self.interaction_mode = Mode.NORMAL
        self.last_legal_fens: List[Any] = []
        self.last_move = None
        self.legal_fens: List[Any] = []
        self.legal_fens_after_cmove: List[Any] = []
        self.max_guess = 0
        self.max_guess_black = 0
        self.max_guess_white = 0
        self.no_guess_black = 1
        self.no_guess_white = 1
        self.online_decrement = 0
        self.pb_move = chess.Move.null()  # Best ponder move
        self.pgn_book_test = False
        self.picotutor: PicoTutor | None = None
        self.play_mode = PlayMode.USER_WHITE
        self.position_mode = False
        self.reset_auto = False
        self.searchmoves = AlternativeMover()
        self.seeking_flag = False
        self.set_location = ""
        self.start_time_cmove_done = 0.0
        self.take_back_locked = False
        self.takeback_active = False
        self.tc_init_last = None
        self.think_time = 0
        self.time_control: TimeControl = None
        self.rating: Rating = None
        self.coach_triggered = False
        self.last_error_fen = ""
        self.artwork_in_use = False
        self.delay_fen_error = 4

    def start_clock(self) -> None:
        """Start the clock."""
        if self.interaction_mode in (
            Mode.NORMAL,
            Mode.BRAIN,
            Mode.OBSERVE,
            Mode.REMOTE,
            Mode.TRAINING,
        ):
            self.time_control.start_internal(self.game.turn)
            tc_init = self.time_control.get_parameters()
            if self.interaction_mode == Mode.TRAINING:
                pass
            else:
                DisplayMsg.show(Message.CLOCK_START(turn=self.game.turn, tc_init=tc_init, devs={"ser", "i2c", "web"}))
                # removed sync sleep
                # @todo give some time to clock to really do it. Check this solution!
        else:
            logger.warning("wrong function call [start]! mode: %s", self.interaction_mode)

    def stop_clock(self) -> None:
        """Stop the clock."""
        if self.interaction_mode in (
            Mode.NORMAL,
            Mode.BRAIN,
            Mode.OBSERVE,
            Mode.REMOTE,
            Mode.TRAINING,
        ):
            self.time_control.stop_internal()
            if self.interaction_mode == Mode.TRAINING:
                pass
            else:
                DisplayMsg.show(Message.CLOCK_STOP(devs={"ser", "i2c", "web"}))
                # removed sync sleep
                # @todo give some time to clock to really do it. Check this solution!
        else:
            logger.warning("wrong function call [stop]! mode: %s", self.interaction_mode)

    def stop_fen_timer(self) -> None:
        """Stop the fen timer cause another fen string been send."""
        if self.fen_timer_running:
            self.fen_timer.stop()
            self.fen_timer_running = False

    def get_user_color(self):
        if self.play_mode == PlayMode.USER_BLACK:
            return chess.BLACK
        else:
            return chess.WHITE

    def is_user_turn(self) -> bool:
        """Return True if is users turn to move"""
        return (self.game.turn == chess.WHITE and self.play_mode == PlayMode.USER_WHITE) or (
            self.game.turn == chess.BLACK and self.play_mode == PlayMode.USER_BLACK
        )

    def is_not_user_turn(self) -> bool:
        """Return True if it is NOT users turn (only valid in normal, brain or remote mode)."""
        assert self.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.REMOTE, Mode.TRAINING), (
            "wrong mode: %s" % self.interaction_mode
        )
        condition1 = self.play_mode == PlayMode.USER_WHITE and self.game.turn == chess.BLACK
        condition2 = self.play_mode == PlayMode.USER_BLACK and self.game.turn == chess.WHITE
        return condition1 or condition2

    async def set_online_tctrl(self, game_time, fischer_inc, main_loop: asyncio.AbstractEventLoop) -> None:
        l_game_time = 0
        l_fischer_inc = 0

        logger.debug("molli online set_online_tctrl input %s %s", game_time, fischer_inc)
        l_game_time = int(game_time)
        l_fischer_inc = int(fischer_inc)
        self.stop_clock()
        self.time_control.stop_internal(log=False)

        self.time_control = TimeControl()
        tc_init = self.time_control.get_parameters()

        if l_fischer_inc == 0:
            tc_init["mode"] = TimeMode.BLITZ
            tc_init["blitz"] = l_game_time
            tc_init["fischer"] = 0
        else:
            tc_init["mode"] = TimeMode.FISCHER
            tc_init["blitz"] = l_game_time
            tc_init["fischer"] = l_fischer_inc

        tc_init["blitz2"] = 0
        tc_init["moves_to_go"] = 0
        tc_init["loop"] = main_loop  # needed by timer in TimeControl

        lt_white = l_game_time * 60 + l_fischer_inc
        lt_black = l_game_time * 60 + l_fischer_inc
        tc_init["internal_time"] = {chess.WHITE: lt_white, chess.BLACK: lt_black}

        self.time_control = TimeControl(**tc_init)
        text = self.dgttranslate.text("N00_oktime")
        msg = Message.TIME_CONTROL(time_text=text, show_ok=True, tc_init=tc_init)
        DisplayMsg.show(msg)
        self.stop_fen_timer()

    def check_game_state(self):
        """
        Check if the game has ended or not ; it also sends Message to Displays if the game has ended.

        :param game:
        :param play_mode:
        :return: False is the game continues, Game_Ends() Message if it has ended
        """
        if self.game.is_stalemate():
            result = GameResult.STALEMATE
        elif self.game.is_insufficient_material():
            result = GameResult.INSUFFICIENT_MATERIAL
        elif self.game.is_seventyfive_moves():
            result = GameResult.SEVENTYFIVE_MOVES
        elif self.game.is_fivefold_repetition():
            result = GameResult.FIVEFOLD_REPETITION
        elif self.game.is_checkmate():
            result = GameResult.MATE
        else:
            return False

        return Message.GAME_ENDS(
            tc_init=self.time_control.get_parameters(),
            result=result,
            play_mode=self.play_mode,
            game=self.game.copy(),
        )

    @staticmethod
    def _num(time_str) -> int:
        try:
            value = int(time_str)
            if value > 999:
                value = 999
            return value
        except ValueError:
            return 1

    async def transfer_time(self, time_list: list, depth=0, node=0):
        """Transfer the time list to a TimeControl Object and a Text Object."""
        i_depth = self._num(depth)
        i_node = self._num(node)

        if i_depth > 0:
            fixed = 671
            timec = TimeControl(TimeMode.FIXED, fixed=fixed, depth=i_depth)
            textc = self.dgttranslate.text("B00_tc_depth", timec.get_list_text())
        elif i_node > 0:
            fixed = 671
            timec = TimeControl(TimeMode.FIXED, fixed=fixed, node=i_node)
            textc = self.dgttranslate.text("B00_tc_node", timec.get_list_text())
        elif len(time_list) == 1:
            fixed = self._num(time_list[0])
            timec = TimeControl(TimeMode.FIXED, fixed=fixed)
            textc = self.dgttranslate.text("B00_tc_fixed", timec.get_list_text())
        elif len(time_list) == 2:
            blitz = self._num(time_list[0])
            fisch = self._num(time_list[1])
            if fisch == 0:
                timec = TimeControl(TimeMode.BLITZ, blitz=blitz)
                textc = self.dgttranslate.text("B00_tc_blitz", timec.get_list_text())
            else:
                timec = TimeControl(TimeMode.FISCHER, blitz=blitz, fischer=fisch)
                textc = self.dgttranslate.text("B00_tc_fisch", timec.get_list_text())
        elif len(time_list) == 3:
            moves_to_go = self._num(time_list[0])
            blitz = self._num(time_list[1])
            blitz2 = self._num(time_list[2])
            if blitz2 == 0:
                timec = TimeControl(TimeMode.BLITZ, blitz=blitz, moves_to_go=moves_to_go, blitz2=blitz2)
                textc = self.dgttranslate.text("B00_tc_tourn", timec.get_list_text())
            else:
                fisch = blitz2
                blitz2 = 0
                timec = TimeControl(
                    TimeMode.FISCHER,
                    blitz=blitz,
                    fischer=fisch,
                    moves_to_go=moves_to_go,
                    blitz2=blitz2,
                )
                textc = self.dgttranslate.text("B00_tc_tourn", timec.get_list_text())
        elif len(time_list) == 4:
            moves_to_go = self._num(time_list[0])
            blitz = self._num(time_list[1])
            fisch = self._num(time_list[2])
            blitz2 = self._num(time_list[3])
            if fisch == 0:
                timec = TimeControl(TimeMode.BLITZ, blitz=blitz, moves_to_go=moves_to_go, blitz2=blitz2)
                textc = self.dgttranslate.text("B00_tc_tourn", timec.get_list_text())
            else:
                timec = TimeControl(
                    TimeMode.FISCHER,
                    blitz=blitz,
                    fischer=fisch,
                    moves_to_go=moves_to_go,
                    blitz2=blitz2,
                )
                textc = self.dgttranslate.text("B00_tc_tourn", timec.get_list_text())
        else:
            timec = TimeControl(TimeMode.BLITZ, blitz=5)
            textc = self.dgttranslate.text("B00_tc_blitz", timec.get_list_text())
        return timec, textc


async def check_ssh(host, username, password) -> bool:
    try:
        s = paramiko.SSHClient()
        s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        s.connect(host, username=username, password=password, timeout=7)
        s.close()
    except Exception:
        return False
    return True


async def log_pgn(state: PicochessState):
    logger.debug("molli pgn: pgn_book_test: %s", str(state.pgn_book_test))
    logger.debug("molli pgn: game turn: %s", state.game.turn)
    logger.debug("molli pgn: max_guess_white: %s", state.max_guess)
    logger.debug("molli pgn: max_guess_white: %s", state.max_guess_white)
    logger.debug("molli pgn: max_guess_black: %s", state.max_guess_black)
    logger.debug("molli pgn: no_guess_white: %s", state.no_guess_white)
    logger.debug("molli pgn: no_guess_black: %s", state.no_guess_black)


async def read_pgn_info():
    info = {}
    arch = platform.machine()
    pgn_info_path = "/opt/picochess/engines/" + arch + "/extra/pgn_game_info.txt"
    try:
        with open(pgn_info_path) as info_file:
            for line in info_file:
                name, value = line.partition("=")[::2]
                info[name.strip()] = value.strip()
        return (
            info["PGN_GAME"],
            info["PGN_PROBLEM"],
            info["PGN_FEN"],
            info["PGN_RESULT"],
            info["PGN_White"],
            info["PGN_Black"],
        )
    except (OSError, KeyError):
        logger.error("Could not read pgn_game_info file")
        return "Game Error", "", "", "*", "", ""


async def read_online_result():
    result_line = ""
    winner = ""

    try:
        log_u = open("online_game.txt", "r")
    except Exception:
        log_u = ""
        logger.error("Could not read online game file")
        return

    if log_u:
        i = 0
        lines = log_u.readlines()
        for line in lines:
            i += 1
            if i == 9:
                result_line = line[12:].strip()
            elif i == 10:
                winner = line[7:].strip()
    else:
        result_line = ""

    log_u.close()
    return (str(result_line), str(winner))


async def read_online_user_info() -> Tuple[str, str, str, str, int, int]:
    own_user = "unknown"
    opp_user = "unknown"
    login = "failed"
    own_color = ""
    game_time = 0
    fischer_inc = 0

    try:
        log_u = open("online_game.txt", "r")
        lines = log_u.readlines()
        for line in lines:
            key, value = line.split("=")
            if key == "LOGIN":
                login = value.strip()
            elif key == "COLOR":
                own_color = value.strip()
            elif key == "OWN_USER":
                own_user = value.strip()
            elif key == "OPPONENT_USER":
                opp_user = value.strip()
            elif key == "GAME_TIME":
                game_time = int(value.strip())
            elif key == "FISCHER_INC":
                fischer_inc = int(value.strip())
    except Exception:
        logger.error("Could not read online game file")
        return login, own_color, own_user, opp_user, 0, 0

    log_u.close()
    logger.debug("online game_time %s fischer_inc: %s", game_time, fischer_inc)

    return login, own_color, own_user, opp_user, game_time, fischer_inc


async def compare_fen(fen_board_external="", fen_board_internal="") -> str:
    # <Piece Placement> ::= <rank8>'/'<rank7>'/'<rank6>'/'<rank5>'/'<rank4>'/'<rank3>'/'<rank2>'/'<rank1>
    # <ranki>       ::= [<digit17>]<piece> {[<digit17>]<piece>} [<digit17>] | '8'
    # <piece>       ::= <white Piece> | <black Piece>
    # <digit17>     ::= '1' | '2' | '3' | '4' | '5' | '6' | '7'
    # <white Piece> ::= 'P' | 'N' | 'B' | 'R' | 'Q' | 'K'
    # <black Piece> ::= 'p' | 'n' | 'b' | 'r' | 'q' | 'k'
    # eg. starting position 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR'
    #                       'a8 b8 c8 d8... / a7 b7... / a1 b1 c1 ... h1'

    if fen_board_external == fen_board_internal or fen_board_external == "" or fen_board_internal == "":
        return ""

    internal_board = chess.Board()
    internal_board.set_board_fen(fen_board_internal)

    external_board = chess.Board()
    external_board.set_board_fen(fen_board_external)

    # now compare each square and return first difference
    # and return first all fields to be cleared and then
    # all fields where to put new/different pieces on
    # start first with all squares to be cleared
    put_field = ""
    for square_no in range(0, 64):
        if internal_board.piece_at(square_no) != external_board.piece_at(square_no):
            if internal_board.piece_at(square_no) is None:
                return str("clear " + chess.square_name(square_no))
            else:
                put_field = str("put " + str(internal_board.piece_at(square_no)) + " " + chess.square_name(square_no))
    return put_field


async def compute_legal_fens(game_copy: chess.Board):
    """
    Compute a list of legal FENs for the given game.

    :param game_copy: The game
    :return: A list of legal FENs
    """
    fens = []
    for move in game_copy.legal_moves:
        game_copy.push(move)
        fens.append(game_copy.board_fen())
        game_copy.pop()
    return fens


async def main() -> None:
    """Main function."""
    # Use asyncio's event loop as the Tornado IOLoop
    AsyncIOMainLoop().install()
    main_loop = asyncio.get_event_loop()
    # the following calls could be done with one but in the future
    # main loop is hopefully not global in utilities.py
    # use main loop everywhere...
    DispatchDgt.set_main_loop(main_loop)
    Observable.set_main_loop(main_loop)
    state = PicochessState()
    own_user = ""
    opp_user = ""
    game_time = 0
    fischer_inc = 0
    login = ""

    async def display_ip_info(state: PicochessState):
        """Fire an IP_INFO message with the IP adr."""
        location, ext_ip, int_ip = get_location()

        if state.set_location == "auto":
            pass
        else:
            location = state.set_location

        info = {"location": location, "ext_ip": ext_ip, "int_ip": int_ip, "version": version}
        DisplayMsg.show(Message.IP_INFO(info=info))

    config = Configuration()
    args, unknown = config._args, config.unknown

    # Enable logging
    if args.log_file:
        handler = RotatingFileHandler("logs" + os.sep + args.log_file, maxBytes=1 * 1024 * 1024, backupCount=5)
        logging.basicConfig(
            level=getattr(logging, args.log_level.upper()),
            format="%(asctime)s.%(msecs)03d %(levelname)7s %(module)10s - %(funcName)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            handlers=[handler],
        )
    logging.getLogger("chess.engine").setLevel(logging.INFO)  # don't want to get so many python-chess uci messages

    logger.debug("#" * 20 + " PicoChess v%s " + "#" * 20, version)
    # log the startup parameters but hide the password fields
    a_copy = copy.copy(vars(args))
    a_copy["mailgun_key"] = a_copy["smtp_pass"] = a_copy["engine_remote_key"] = a_copy["engine_remote_pass"] = "*****"
    logger.debug("startup parameters: %s", a_copy)
    if unknown:
        logger.warning("invalid parameter given %s", unknown)

    EngineProvider.init()

    Rev2Info.set_dgtpi(args.dgtpi)
    state.flag_flexible_ponder = args.flexible_analysis
    state.flag_premove = args.premove
    state.set_location = args.location
    state.online_decrement = args.online_decrement

    try:
        board_type = dgt.util.EBoard[args.board_type.upper()]
    except KeyError:
        board_type = dgt.util.EBoard.DGT
    ModeInfo.set_eboard_type(board_type)

    # wire some dgt classes
    if board_type == dgt.util.EBoard.CHESSLINK:
        dgtboard: EBoard = ChessLinkBoard()
    elif board_type == dgt.util.EBoard.CHESSNUT:
        dgtboard = ChessnutBoard()
    elif board_type == dgt.util.EBoard.ICHESSONE:
        dgtboard = IChessOneBoard()
    elif board_type == dgt.util.EBoard.CERTABO:
        dgtboard = CertaboBoard()
    else:
        dgtboard = DgtBoard(
            args.dgt_port, args.disable_revelation_leds, args.dgtpi, args.disable_et, main_loop, args.slow_slide
        )
    state.dgttranslate = DgtTranslate(args.beep_config, args.beep_some_level, args.language, version)
    state.dgtmenu = DgtMenu(
        args.clockside,
        args.disable_confirm_message,
        args.ponder_interval,
        args.user_voice,
        args.computer_voice,
        args.speed_voice,
        args.enable_capital_letters,
        args.disable_short_notation,
        args.log_file,
        args.engine_remote_server,
        args.rolling_display_normal,
        max(0, min(20, args.volume_voice)),
        board_type,
        args.theme,
        round(float(args.rspeed), 2),
        args.rsound,
        args.rdisplay,
        args.rwindow,
        args.rolling_display_ponder,
        args.show_engine,
        PicoCoach.from_str(args.tutor_coach),
        args.tutor_watcher,
        args.tutor_explorer,
        PicoComment.from_str(args.tutor_comment),
        args.comment_factor,
        args.continue_game,
        args.alt_move,
        state.dgttranslate,
    )

    dgtdispatcher = Dispatcher(state.dgtmenu)

    logger.debug("node %s", args.node)

    state.time_control, time_text = await state.transfer_time(args.time.split(), depth=args.depth, node=args.node)
    state.tc_init_last = state.time_control.get_parameters()
    time_text.beep = False

    # The class dgtDisplay fires Event (Observable) & DispatchDgt (Dispatcher)
    my_dgt_display = DgtDisplay(state.dgttranslate, state.dgtmenu, state.time_control, main_loop)
    asyncio.create_task(my_dgt_display.message_consumer())
    my_dgt_display.start_once_per_second_timer()
    # @todo optimise to start this timer only when playmode is needing it?

    ModeInfo.set_clock_side(args.clockside)

    sample_beeper = False
    sample_beeper_level = 0

    if args.beep_some_level > 1:
        # samples: confirmation and button press sounds
        sample_beeper_level = 2
    elif args.beep_some_level == 1:
        # samples: only confirmation sounds
        sample_beeper_level = 1
    else:
        sample_beeper_level = 0

    if args.beep_config == "sample":
        # sample sounds according to beeper_level
        sample_beeper = True
    else:
        # samples: no sounds
        sample_beeper = False

    pico_talker = PicoTalkerDisplay(
        args.user_voice,
        args.computer_voice,
        args.speed_voice,
        args.enable_setpieces_voice,
        args.comment_factor,
        sample_beeper,
        sample_beeper_level,
        board_type,
        main_loop,
    )

    asyncio.create_task(pico_talker.message_consumer())

    # Launch web server
    if args.web_server_port:
        my_web_server = WebServer()
        shared: dict = {}
        # moved starting WebDisplayt and WebVr here so that they are in same main loop
        logger.info("initializing message queues")
        my_web_display = WebDisplay(shared, main_loop)
        asyncio.create_task(my_web_display.message_consumer())
        my_web_vr = WebVr(shared, dgtboard, main_loop)
        asyncio.create_task(my_web_vr.dgt_consumer())
        logger.info("message queues ready - starting web server")
        dgtdispatcher.register("web")
        theme: str = calc_theme(args.theme, state.set_location)
        web_app = my_web_server.make_app(theme, shared)
        try:
            web_app.listen(args.web_server_port)
        except PermissionError:
            logger.error("Could not start web server - port %d not allowed by operating system", args.web_server_port)
            logger.error("try: sudo setcap 'cap_net_bind_service=+ep' $(readlink -f $(which python3))")
            sys.exit(1)  # fatal, cannot continue without web server
        except OSError:
            logger.error("Could not start web server - port %d not available", args.web_server_port)
            logger.error("is another Picochess, or other web application already running?")
            sys.exit(1)  # fatal, cannot continue without web server

    if board_type == dgt.util.EBoard.NOEBOARD:
        logger.debug("starting PicoChess in no eboard mode")
    else:
        # Connect to DGT board
        logger.debug("starting PicoChess in board mode")
        if args.dgtpi:
            my_dgtpi = DgtPi(dgtboard, main_loop)
            dgtdispatcher.register("i2c")
            asyncio.create_task(my_dgtpi.dgt_consumer())
            asyncio.create_task(my_dgtpi.process_incoming_clock_forever())
        else:
            logger.debug("(ser) starting the board connection")
            dgtboard.run()  # a clock can only be online together with the board, so we must start it infront
        my_dgthw = DgtHw(dgtboard, main_loop)
        dgtdispatcher.register("ser")
        asyncio.create_task(my_dgthw.dgt_consumer())

    # The class Dispatcher sends DgtApi messages at the correct (delayed) time out
    asyncio.create_task(dgtdispatcher.dispatch_consumer())

    # Save to PGN
    emailer = Emailer(email=args.email, mailgun_key=args.mailgun_key)
    emailer.set_smtp(
        sserver=args.smtp_server,
        suser=args.smtp_user,
        spass=args.smtp_pass,
        sencryption=args.smtp_encryption,
        sstarttls=args.smtp_starttls,
        sport=args.smtp_port,
        sfrom=args.smtp_from,
    )

    my_pgn_display = PgnDisplay("games" + os.sep + args.pgn_file, emailer, main_loop)
    asyncio.create_task(my_pgn_display.message_consumer())

    # Update
    if args.enable_update:
        update_picochess(args.dgtpi, args.enable_update_reboot, state.dgttranslate)

    #################################################

    class MainLoop:
        """main turned into a class"""

        def __init__(
            self,
            own_user,
            opp_user,
            game_time,
            fischer_inc,
            login,
            state: PicochessState,
            pico_talker: PicoTalkerDisplay,
            dgtdispatcher: Dispatcher,
            dgtboard: DgtBoard,
            board_type,
            loop: asyncio.AbstractEventLoop,
            args,
        ):
            self.loop = loop
            self._task = None  # placeholder for message consumer task
            self.own_user = own_user
            self.opp_user = opp_user
            self.game_time = game_time
            self.fischer_inc = fischer_inc
            self.login = login
            self.state = state
            self.engine = None  # placeholder for UciEngine
            self.state.fen_timer = None  # this and next line could be removed?
            self.state.fen_timer_running = False  # already set in picostate init
            self.args = args
            self.pico_talker = pico_talker
            self.dgtdispatcher = dgtdispatcher
            self.dgtboard = dgtboard
            self.board_type = board_type
            # @todo start background analyser only when new game starts
            self.background_analyse_timer = AsyncRepeatingTimer(
                FLOAT_MIN_BACKGROUND_TIME, self._pv_score_depth_analyser, loop=self.loop
            )
            ###########################################

            # try the given engine first and if that fails the first from "engines.ini" then exit
            self.state.engine_file = self.args.engine

            self.engine_remote_home = self.args.engine_remote_home.rstrip(os.sep)

            self.uci_remote_shell = None

            self.uci_local_shell = UciShell(hostname="", username="", key_file="", password="")

            if self.state.engine_file is None:
                self.state.engine_file = EngineProvider.installed_engines[0]["file"]

            self.is_out_of_time_already = False  # molli: out of time message only once
            self.all_books = get_opening_books()
            try:
                self.book_index = [book["file"] for book in self.all_books].index(args.book)
            except ValueError:
                logger.warning("selected book not present, defaulting to %s", self.all_books[7]["file"])
                self.book_index = 7
            self.state.book_in_use = self.args.book
            self.bookreader = chess.polyglot.open_reader(self.all_books[self.book_index]["file"])
            self.state.searchmoves = AlternativeMover()
            self.state.artwork_in_use = False

        async def initialise(self, time_text):
            """Due to use of async some initialisation is moved here"""
            engine_file_to_load = self.state.engine_file  # assume not mame
            if "/mame/" in self.state.engine_file and self.state.dgtmenu.get_engine_rdisplay():
                engine_file_art = self.state.engine_file + "_art"
                my_file = Path(engine_file_art)
                if my_file.is_file():
                    self.state.artwork_in_use = True
                    engine_file_to_load = engine_file_art  # load mame

            self.engine = UciEngine(
                file=engine_file_to_load,
                uci_shell=self.uci_local_shell,
                mame_par=self.calc_engine_mame_par(),
                loop=self.loop,
            )
            await self.engine.open_engine()
            if engine_file_to_load != self.state.engine_file:
                await asyncio.sleep(1)  # mame artwork wait

            await display_ip_info(state)
            await asyncio.sleep(1.0)

            if not self.engine.loaded_ok():
                logger.error("engine %s not started", self.state.engine_file)
                await asyncio.sleep(3)
                DisplayMsg.show(Message.ENGINE_FAIL())
                await asyncio.sleep(2)
                sys.exit(-1)

            # Startup - internal
            self.state.game = chess.Board()  # Create the current game
            self.state.legal_fens = await compute_legal_fens(self.state.game.copy())  # Compute the legal FENs
            self.state.flag_startup = True

            if self.args.pgn_elo and self.args.pgn_elo.isnumeric() and self.args.rating_deviation:
                self.state.rating = Rating(float(args.pgn_elo), float(args.rating_deviation))
            self.args.engine_level = None if self.args.engine_level == "None" else self.args.engine_level
            if self.args.engine_level == '""':
                self.args.engine_level = None
            engine_opt, level_index = await self.get_engine_level_dict(args.engine_level)
            await self.engine.startup(engine_opt, self.state.rating)

            if (
                self.emulation_mode()
                and self.state.dgtmenu.get_engine_rdisplay()
                and self.state.artwork_in_use
                and not self.state.dgtmenu.get_engine_rwindow()
            ):
                # switch to fullscreen
                cmd = "xdotool keydown alt key F11; sleep 0.2; xdotool keyup alt"
                subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                    shell=True,
                )

            # Startup - external
            self.state.engine_level = self.args.engine_level
            self.state.old_engine_level = self.state.engine_level
            self.state.new_engine_level = self.state.engine_level

            if self.state.engine_level:
                level_text = self.state.dgttranslate.text("B00_level", self.state.engine_level)
                level_text.beep = False
            else:
                level_text = None
                self.state.engine_level = ""

            if self.args.pgn_user:
                user_name = self.args.pgn_user
            else:
                if self.args.email:
                    user_name = self.args.email.split("@")[0]
                else:
                    user_name = "Player"
            sys_info = {
                "version": version,
                "engine_name": self.engine.get_name(),
                "user_name": user_name,
                "user_elo": self.args.pgn_elo,
                "rspeed": round(float(args.rspeed), 2),
            }

            DisplayMsg.show(Message.SYSTEM_INFO(info=sys_info))
            DisplayMsg.show(
                Message.STARTUP_INFO(
                    info={
                        "interaction_mode": self.state.interaction_mode,
                        "play_mode": self.state.play_mode,
                        "books": self.all_books,
                        "book_index": self.book_index,
                        "level_text": level_text,
                        "level_name": self.state.engine_level,
                        "tc_init": self.state.time_control.get_parameters(),
                        "time_text": time_text,
                    }
                )
            )

            # engines setup
            DisplayMsg.show(
                Message.ENGINE_STARTUP(
                    installed_engines=EngineProvider.installed_engines,
                    file=self.state.engine_file,
                    level_index=level_index,
                    has_960=self.engine.has_chess960(),
                    has_ponder=self.engine.has_ponder(),
                )
            )
            DisplayMsg.show(Message.ENGINE_SETUP())
            self.update_elo_display()

            # set timecontrol restore data set for normal engines after leaving emulation mode
            pico_time = self.args.def_timectrl

            if self.emulation_mode():
                self.state.flag_last_engine_emu = True
                time_control_l, time_text_l = await self.state.transfer_time(pico_time.split(), depth=0, node=0)
                self.state.tc_init_last = time_control_l.get_parameters()

            if self.pgn_mode():
                ModeInfo.set_pgn_mode(mode=True)
                self.state.flag_last_engine_pgn = True
                await self.det_pgn_guess_tctrl()
            else:
                ModeInfo.set_pgn_mode(mode=False)

            if self.online_mode():
                ModeInfo.set_online_mode(mode=True)
                await self.set_wait_state(Message.START_NEW_GAME(game=self.state.game.copy(), newgame=True))
            else:
                ModeInfo.set_online_mode(mode=False)
                self.engine.newgame(self.state.game.copy())

            DisplayMsg.show(Message.PICOCOMMENT(picocomment="ok"))

            self.state.comment_file = self.get_comment_file()
            tutor_engine = self.args.tutor_engine
            if self.remote_engine_mode() and self.uci_remote_shell:
                uci_shell = self.uci_remote_shell
            else:
                uci_shell = self.uci_local_shell
            depth = FLOAT_MAX_ANALYSIS_DEPTH if bool(self.args.coach_analyser) else None
            self.state.picotutor = PicoTutor(
                i_ucishell=uci_shell,
                i_engine_path=tutor_engine,
                i_comment_file=self.state.comment_file,
                i_lang=self.args.language,
                i_coach_analyser=bool(self.args.coach_analyser),
                loop=self.loop,
                i_depth=depth,
            )
            self.state.picotutor.set_status(
                self.state.dgtmenu.get_picowatcher(),
                self.state.dgtmenu.get_picocoach(),
                self.state.dgtmenu.get_picoexplorer(),
                self.state.dgtmenu.get_picocomment(),
            )
            await self.state.picotutor.open_engine()

            ModeInfo.set_game_ending(result="*")

            text = self.state.dgtmenu.get_current_engine_name()
            self.state.engine_text = text
            self.state.dgtmenu.enter_top_menu()

            if self.state.dgtmenu.get_enginename():
                msg = Message.ENGINE_NAME(engine_name=self.state.engine_text)
                DisplayMsg.show(msg)

        async def think(
            self,
            msg: Message,
            searchlist=False,
        ):
            """
            Start a new search on the current game.

            If a move is found in the opening book, fire an event in a few seconds.
            """
            DisplayMsg.show(msg)
            if not self.online_mode() or self.state.game.fullmove_number > 1:
                self.state.start_clock()
            book_res = self.state.searchmoves.book(self.bookreader, self.state.game.copy())
            if (book_res and not self.emulation_mode() and not self.online_mode() and not self.pgn_mode()) or (
                book_res and (self.pgn_mode() and self.state.pgn_book_test)
            ):
                await Observable.fire(Event.BEST_MOVE(move=book_res.move, ponder=book_res.ponder, inbook=True))
            else:
                while not self.engine.is_waiting():
                    await asyncio.sleep(0.05)
                    logger.warning("engine is still not waiting")
                uci_dict = state.time_control.uci()
                if searchlist:
                    # molli: otherwise might lead to problems with internal books
                    uci_dict["searchmoves"] = self.state.searchmoves.all(self.state.game)
                try:
                    engine_res = await self.engine.go(uci_dict, self.state.game)
                    if engine_res:
                        logger.debug("engine moved %s", engine_res.move.uci)
                        await Observable.fire(
                            Event.BEST_MOVE(move=engine_res.move, ponder=engine_res.ponder, inbook=False)
                        )
                        # webplay: Event.BEST_MOVE pushes the move on display
                        # dgt board: BEST_MOVE 1) informs 2) user moves, 3) dgt event to process_fen() push
                    else:
                        logger.error("fatal no move received from engine")
                        #  this code is most likely never reached, exception below is more likely
                        await Observable.fire(Event.BEST_MOVE(move=None, ponder=None, inbook=False))
                except Exception as e:
                    if self.pgn_mode():
                        logger.debug("pgn_mode no valid move received from engine %s", e)
                    else:
                        logger.error("fatal - engine failed to make a move %s", e)
                    #  @todo do we need to check for pgn_mode or other?
                    await Observable.fire(Event.BEST_MOVE(move=None, ponder=None, inbook=False))
            self.state.automatic_takeback = False

        async def stop_search(self):
            """Stop current search."""
            self.engine.stop()
            if not self.emulation_mode():
                while not self.engine.is_waiting():
                    await asyncio.sleep(0.05)
                    logger.debug("engine is still not waiting")

        async def stop_search_and_clock(self, ponder_hit=False):
            """Depending on the interaction mode stop search and clock."""
            if self.state.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.TRAINING):
                self.state.stop_clock()
                if self.engine.is_waiting():
                    logger.debug("engine already waiting")
                else:
                    if ponder_hit:
                        pass  # we send the self.engine.hit() lateron!
                    else:
                        await self.stop_search()
            elif self.state.interaction_mode in (Mode.REMOTE, Mode.OBSERVE):
                self.state.stop_clock()
                await self.stop_search()
            elif self.state.interaction_mode in (Mode.ANALYSIS, Mode.KIBITZ, Mode.PONDER):
                await self.stop_search()

        def get_comment_file(self) -> str:
            comment_path = self.state.engine_file + "_comments_" + self.args.language + ".txt"
            logger.debug("molli comment file: %s", comment_path)
            comment_file = Path(comment_path)
            if comment_file.is_file():
                logger.debug("molli comment file exists")
                return comment_path
            else:
                logger.debug("molli comment file does not exist")
                return ""

        async def call_pico_coach(self):
            if self.state.coach_triggered:
                self.state.position_mode = True
            if (
                (self.state.game.turn == chess.WHITE and self.state.play_mode == PlayMode.USER_WHITE)
                or (self.state.game.turn == chess.BLACK and self.state.play_mode == PlayMode.USER_BLACK)
            ) and not (self.state.game.is_checkmate() or self.state.game.is_stalemate()):
                self.state.stop_clock()
                await asyncio.sleep(0.5)
                self.state.stop_fen_timer()
                await asyncio.sleep(0.5)
                eval_str = "ANALYSIS"
                msg = Message.PICOTUTOR_MSG(eval_str=eval_str)
                DisplayMsg.show(msg)
                await asyncio.sleep(2)

                (
                    t_best_move,
                    t_best_score,
                    t_best_mate,
                    t_pv_best_move,
                    t_alt_best_moves,
                ) = self.state.picotutor.get_pos_analysis()

                tutor_str = "POS" + str(t_best_score)
                msg = Message.PICOTUTOR_MSG(eval_str=tutor_str, score=t_best_score)
                DisplayMsg.show(msg)
                await asyncio.sleep(5)

                if t_best_mate:
                    l_mate = int(t_best_mate)
                    if t_best_move != chess.Move.null():
                        game_tutor = self.state.game.copy()
                        san_move = game_tutor.san(t_best_move)
                        game_tutor.push(t_best_move)  # for picotalker (last move spoken)
                        tutor_str = "BEST" + san_move
                        msg = Message.PICOTUTOR_MSG(eval_str=tutor_str, game=game_tutor.copy())
                        DisplayMsg.show(msg)
                        await asyncio.sleep(5)
                else:
                    l_mate = 0
                if l_mate > 0:
                    eval_str = "PICMATE_" + str(abs(l_mate))
                    msg = Message.PICOTUTOR_MSG(eval_str=eval_str)
                    DisplayMsg.show(msg)
                    await asyncio.sleep(5)
                elif l_mate < 0:
                    eval_str = "USRMATE_" + str(abs(l_mate))
                    msg = Message.PICOTUTOR_MSG(eval_str=eval_str)
                    DisplayMsg.show(msg)
                    await asyncio.sleep(5)
                else:
                    l_max = 0
                    for alt_move in t_alt_best_moves:
                        l_max = l_max + 1
                        if l_max <= 3:
                            game_tutor = self.state.game.copy()
                            san_move = game_tutor.san(alt_move)
                            game_tutor.push(alt_move)  # for picotalker (last move spoken)

                            tutor_str = "BEST" + san_move
                            msg = Message.PICOTUTOR_MSG(eval_str=tutor_str, game=game_tutor.copy())
                            DisplayMsg.show(msg)
                            await asyncio.sleep(5)
                        else:
                            break
                self.state.start_clock()

        def calc_engine_mame_par(self):
            return get_engine_mame_par(self.state.dgtmenu.get_engine_rspeed(), self.state.dgtmenu.get_engine_rsound())

        def pgn_mode(self):
            if "pgn_" in self.state.engine_file:
                return True
            else:
                return False

        def remote_windows(self):
            windows = False
            if "\\" in self.engine_remote_home:
                windows = True
            else:
                windows = False
            return windows

        async def get_engine_level_dict(self, engine_level):
            """Transfer an engine level to its level_dict plus an index."""
            for eng in EngineProvider.installed_engines:
                if eng["file"] == self.state.engine_file:
                    level_list = sorted(eng["level_dict"])
                    try:
                        level_index = level_list.index(engine_level)
                        return eng["level_dict"][level_list[level_index]], level_index
                    except ValueError:
                        break
            return {}, None

        async def set_fen_from_pgn(self, pgn_fen):
            bit_board = chess.Board(pgn_fen)
            bit_board.set_fen(bit_board.fen())
            logger.debug("molli PGN Fen: %s", bit_board.fen())
            if bit_board.is_valid():
                logger.debug("molli PGN fen is valid!")
                self.state.game = chess.Board(bit_board.fen())
                self.state.done_computer_fen = None
                self.state.done_move = self.state.pb_move = chess.Move.null()
                self.state.searchmoves.reset()
                self.state.game_declared = False
                self.state.legal_fens = compute_legal_fens(self.state.game.copy())
                self.state.legal_fens_after_cmove = []
                self.state.last_legal_fens = []
                if self.picotutor_mode():
                    self.state.picotutor.reset()
                    await self.state.picotutor.set_position(self.state.game.fen(), i_turn=self.state.game.turn)
                    if self.state.play_mode == PlayMode.USER_BLACK:
                        await self.state.picotutor.set_user_color(chess.BLACK)
                    else:
                        await self.state.picotutor.set_user_color(chess.WHITE)
            else:
                logger.debug("molli PGN fen is invalid!")

        def picotutor_mode(self):
            enabled = False

            if (
                self.state.flag_picotutor
                and self.state.interaction_mode in (Mode.NORMAL, Mode.TRAINING, Mode.BRAIN)
                and not self.online_mode()
                and not self.pgn_mode()
                and (
                    self.state.dgtmenu.get_picowatcher()
                    or (self.state.dgtmenu.get_picocoach() != PicoCoach.COACH_OFF)
                    or self.state.dgtmenu.get_picoexplorer()
                )
                and self.state.picotutor is not None
            ):
                enabled = True
            else:
                enabled = False

            return enabled

        def online_mode(self):
            online = False
            if len(self.engine.get_name()) >= 6:
                if self.engine.get_name()[0:6] == ONLINE_PREFIX:
                    online = True
                else:
                    online = False
            return online

        async def set_wait_state(self, msg: Message, start_search=True):
            """Enter engine waiting (normal mode) and maybe (by parameter) start pondering."""
            if not self.state.done_computer_fen:
                self.state.legal_fens = await compute_legal_fens(self.state.game.copy())
                self.state.last_legal_fens = []
            if self.state.interaction_mode in (Mode.NORMAL, Mode.BRAIN):  # @todo handle Mode.REMOTE too and TRAINING?
                if self.state.done_computer_fen:
                    logger.debug("best move displayed, dont search and also keep play mode: %s", self.state.play_mode)
                    start_search = False
                else:
                    old_mode = self.state.play_mode
                    self.state.play_mode = (
                        PlayMode.USER_WHITE if self.state.game.turn == chess.WHITE else PlayMode.USER_BLACK
                    )
                    if old_mode != self.state.play_mode:
                        logger.debug("new play mode: %s", self.state.play_mode)
                        text = self.state.play_mode.value  # type: str
                        if self.picotutor_mode():
                            await self.state.picotutor.set_user_color(self.state.get_user_color())
                        DisplayMsg.show(
                            Message.PLAY_MODE(
                                play_mode=self.state.play_mode, play_mode_text=self.state.dgttranslate.text(text)
                            )
                        )
            if start_search:
                if not self.engine.is_waiting():
                    logger.warning("engine not waiting")
                # Go back to analysing or observing - all modes except REMOTE?
                if self.state.interaction_mode in (
                    Mode.BRAIN,
                    Mode.ANALYSIS,
                    Mode.KIBITZ,
                    Mode.PONDER,
                    Mode.TRAINING,
                    Mode.OBSERVE,
                    Mode.REMOTE,
                ):
                    DisplayMsg.show(msg)
                    await self.analyse()
                    return
            if not self.state.reset_auto:
                if self.state.automatic_takeback:
                    await self.stop_search_and_clock()
                    self.state.reset_auto = True
                DisplayMsg.show(msg)
            else:
                DisplayMsg.show(msg)  # molli: fix for web display refresh
                if self.state.automatic_takeback and self.state.takeback_active:
                    if self.state.play_mode == PlayMode.USER_WHITE:
                        text_pl = "K20_playmode_white_user"
                    else:
                        text_pl = "K20_playmode_black_user"
                    DisplayMsg.show(Message.SHOW_TEXT(text_string=text_pl))
                self.state.automatic_takeback = False
                self.state.takeback_active = False
                self.state.reset_auto = False

            self.state.stop_fen_timer()

        async def takeback(self):
            await self.stop_search_and_clock()
            l_error = False
            try:
                self.state.game.pop()
                l_error = False
            except Exception:
                l_error = True
                logger.debug("takeback not possible!")
            if not l_error:
                if self.picotutor_mode():
                    if self.state.best_move_posted:
                        await self.state.picotutor.pop_last_move()
                        self.state.best_move_posted = False
                    await self.state.picotutor.pop_last_move()
                self.state.done_computer_fen = None
                self.state.done_move = self.state.pb_move = chess.Move.null()
                self.state.searchmoves.reset()
                self.state.takeback_active = True
                await self.set_wait_state(Message.TAKE_BACK(game=self.state.game.copy()))

                if self.pgn_mode():  # molli pgn
                    await log_pgn(self.state)
                    if self.state.max_guess_white > 0:
                        if self.state.game.turn == chess.WHITE:
                            if self.state.no_guess_white > self.state.max_guess_white:
                                await self.get_next_pgn_move()
                    elif self.state.max_guess_black > 0:
                        if self.state.game.turn == chess.BLACK:
                            if self.state.no_guess_black > self.state.max_guess_black:
                                await self.get_next_pgn_move()

                if self.state.game.board_fen() == chess.STARTING_BOARD_FEN:
                    pos960 = 518
                    await Observable.fire(Event.NEW_GAME(pos960=pos960))

        async def get_next_pgn_move(self):
            await log_pgn(self.state)
            await asyncio.sleep(0.5)

            if self.state.max_guess_black > 0:
                self.state.no_guess_black = 1
            elif self.state.max_guess_white > 0:
                self.state.no_guess_white = 1

            if not self.engine.is_waiting():
                await self.stop_search_and_clock()

            self.state.last_legal_fens = []
            self.state.legal_fens_after_cmove = []
            self.state.best_move_displayed = self.state.done_computer_fen
            if self.state.best_move_displayed:
                self.state.done_computer_fen = None
                self.state.done_move = self.state.pb_move = chess.Move.null()

            msg = Message.SET_PLAYMODE(play_mode=self.state.play_mode)
            DisplayMsg.show(msg)
            msg = Message.COMPUTER_MOVE_DONE()

            if self.state.time_control.mode == TimeMode.FIXED:
                self.state.time_control.reset()

            self.state.legal_fens = []

            cond1 = self.state.game.turn == chess.WHITE and self.state.play_mode == PlayMode.USER_BLACK
            cond2 = self.state.game.turn == chess.BLACK and self.state.play_mode == PlayMode.USER_WHITE
            if cond1 or cond2:
                self.state.time_control.reset_start_time()
                await self.think(msg)
            else:
                DisplayMsg.show(msg)
                self.state.start_clock()
                self.state.legal_fens = await compute_legal_fens(self.state.game.copy())

        async def switch_online(self):
            color = ""
            if self.online_mode():
                login, own_color, own_user, opp_user, game_time, fischer_inc = await read_online_user_info()
                logger.debug("molli own_color in switch_online [%s]", own_color)
                logger.debug("molli self.own_user in switch_online [%s]", own_user)
                logger.debug("molli self.opp_user in switch_online [%s]", opp_user)
                logger.debug("molli game_time in switch_online [%s]", game_time)
                logger.debug("molli fischer_inc in switch_online [%s]", fischer_inc)

                ModeInfo.set_online_mode(mode=True)
                ModeInfo.set_online_self.own_user(name=own_user)
                ModeInfo.set_online_opponent(name=opp_user)

                if len(own_color) > 1:
                    color = own_color[2]
                else:
                    color = own_color

                logger.debug("molli switch_online start timecontrol")
                self.state.set_online_tctrl(game_time, fischer_inc, self.loop)
                self.state.time_control.reset_start_time()

                logger.debug("molli switch_online new_color: %s", color)
                if (
                    (color == "b" or color == "B")
                    and self.state.game.turn == chess.WHITE
                    and self.state.play_mode == PlayMode.USER_WHITE
                    and self.state.done_move == chess.Move.null()
                ):
                    # switch to black color for user and send a 'go' to the engine
                    self.state.play_mode = PlayMode.USER_BLACK
                    text = self.state.play_mode.value  # type: str
                    msg = Message.PLAY_MODE(
                        play_mode=self.state.play_mode, play_mode_text=self.state.dgttranslate.text(text)
                    )

                    await self.stop_search_and_clock()

                    self.state.last_legal_fens = []
                    self.state.legal_fens_after_cmove = []
                    self.state.legal_fens = []

                    await self.think(msg)

            else:
                ModeInfo.set_online_mode(mode=False)

            if self.pgn_mode():
                ModeInfo.set_pgn_mode(mode=True)
            else:
                ModeInfo.set_pgn_mode(mode=False)

        async def process_fen(self, fen: str, state: PicochessState):
            """Process given fen like doMove, undoMove, takebackPosition, handleSliding."""
            handled_fen = True
            self.state.error_fen = None
            legal_fens_pico = await compute_legal_fens(self.state.game.copy())

            # Check for same position
            if fen == self.state.game.board_fen():
                logger.debug("Already in this fen: %s", fen)
                self.state.flag_startup = False
                # molli: Chess tutor
                if (
                    self.picotutor_mode()
                    and self.state.dgtmenu.get_picocoach() == PicoCoach.COACH_LIFT
                    and fen != chess.STARTING_BOARD_FEN
                    and not self.state.take_back_locked
                    and self.state.coach_triggered
                    and not self.state.position_mode
                    and not self.state.automatic_takeback
                ):
                    self.call_pico_coach()
                    self.state.coach_triggered = False
                elif self.state.position_mode:
                    self.state.position_mode = False
                    if self.state.delay_fen_error == 1:
                        # position finally alright!
                        tutor_str = "POSOK"
                        msg = Message.PICOTUTOR_MSG(eval_str=tutor_str, game=self.state.game.copy())
                        DisplayMsg.show(msg)
                        self.state.delay_fen_error = 4
                        await asyncio.sleep(1)
                        if not self.state.done_computer_fen:
                            self.state.start_clock()
                    DisplayMsg.show(Message.EXIT_MENU())
                elif self.emulation_mode() and self.state.dgtmenu.get_engine_rdisplay() and self.state.artwork_in_use:
                    # switch windows/tasks
                    cmd = "xdotool keydown alt key Tab; sleep 0.2; xdotool keyup alt"
                    subprocess.run(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        universal_newlines=True,
                        shell=True,
                    )
            # Check if we have to undo a previous move (sliding)
            elif fen in self.state.last_legal_fens:
                logger.info("sliding move detected")
                if self.state.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.TRAINING):
                    if self.state.is_not_user_turn():
                        await self.stop_search()
                        self.state.game.pop()
                        if self.picotutor_mode():
                            if self.state.best_move_posted:
                                await self.state.picotutor.pop_last_move()  # bestmove already sent to tutor
                                self.state.best_move_posted = False
                            await self.state.picotutor.pop_last_move()  # no switch of sides
                        logger.info("user move in computer turn, reverting to: %s", self.state.game.fen())
                    elif self.state.done_computer_fen:
                        self.state.done_computer_fen = None
                        self.state.done_move = chess.Move.null()
                        self.state.game.pop()
                        if self.picotutor_mode():
                            if self.state.best_move_posted:
                                await self.state.picotutor.pop_last_move()  # bestmove already sent to tutor
                                self.state.best_move_posted = False
                            await self.state.picotutor.pop_last_move()  # no switch of sides
                        logger.info(
                            "user move while computer move is displayed, reverting to: %s",
                            self.state.game.fen(),
                        )
                    else:
                        handled_fen = False
                        logger.error("last_legal_fens not cleared: %s", self.state.game.fen())
                elif self.state.interaction_mode == Mode.REMOTE:
                    if self.state.is_not_user_turn():
                        self.state.game.pop()
                        if self.picotutor_mode():
                            if self.state.best_move_posted:
                                await self.state.picotutor.pop_last_move()  # bestmove already sent to tutor
                                self.state.best_move_posted = False
                            await self.state.picotutor.pop_last_move()
                        logger.info("user move in remote turn, reverting to: %s", self.state.game.fen())
                    elif self.state.done_computer_fen:
                        self.state.done_computer_fen = None
                        self.state.done_move = chess.Move.null()
                        self.state.game.pop()
                        if self.picotutor_mode():
                            if self.state.best_move_posted:
                                await self.state.picotutor.pop_last_move()  # bestmove already sent to tutor
                                self.state.best_move_posted = False
                            await self.state.picotutor.pop_last_move()
                        logger.info(
                            "user move while remote move is displayed, reverting to: %s",
                            self.state.game.fen(),
                        )
                    else:
                        handled_fen = False
                        logger.error("last_legal_fens not cleared: %s", self.state.game.fen())
                else:
                    self.state.game.pop()
                    if self.picotutor_mode():
                        if self.state.best_move_posted:
                            await self.state.picotutor.pop_last_move()  # bestmove already sent to tutor
                            self.state.best_move_posted = False
                        await self.state.picotutor.pop_last_move()
                        # just to be sure set fen pos.
                        game_copy = copy.deepcopy(self.state.game)
                        await self.state.picotutor.set_position(game_copy.fen(), i_turn=game_copy.turn)
                        if self.state.play_mode == PlayMode.USER_BLACK:
                            await self.state.picotutor.set_user_color(chess.BLACK)
                        else:
                            await self.state.picotutor.set_user_color(chess.WHITE)
                    logger.info("wrong color move -> sliding, reverting to: %s", self.state.game.fen())
                legal_moves = list(self.state.game.legal_moves)
                move = legal_moves[state.last_legal_fens.index(fen)]
                await self.user_move(move, sliding=True)
                if self.state.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.REMOTE, Mode.TRAINING):
                    self.state.legal_fens = []
                else:
                    self.state.legal_fens = await compute_legal_fens(self.state.game.copy())

            # allow playing/correcting moves for pico's side in TRAINING mode:
            elif fen in legal_fens_pico and self.state.interaction_mode == Mode.TRAINING:
                legal_moves = list(self.state.game.legal_moves)
                move = legal_moves[legal_fens_pico.index(fen)]

                if self.state.done_computer_fen:
                    if fen == self.state.done_computer_fen:
                        pass
                    else:
                        DisplayMsg.show(Message.WRONG_FEN())  # display set pieces/pico's move
                        await asyncio.sleep(3)  # display set pieces again and accept new players move as pico's move
                        DisplayMsg.show(
                            Message.ALTERNATIVE_MOVE(game=self.state.game.copy(), play_mode=self.state.play_mode)
                        )
                        await asyncio.sleep(2)
                        DisplayMsg.show(
                            Message.COMPUTER_MOVE(move=move, ponder=False, game=self.state.game.copy(), wait=False)
                        )
                        await asyncio.sleep(2)
                logger.debug("user move did a move for pico")

                await self.user_move(move, sliding=False)
                self.state.last_legal_fens = self.state.legal_fens
                if self.state.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.REMOTE, Mode.TRAINING):
                    self.state.legal_fens = []
                else:
                    self.state.legal_fens = await compute_legal_fens(self.state.game.copy())

            # standard legal move
            elif fen in self.state.legal_fens:
                logger.debug("standard move detected")
                self.state.newgame_happened = False
                legal_moves = list(self.state.game.legal_moves)
                move = legal_moves[state.legal_fens.index(fen)]
                await self.user_move(move, sliding=False)
                self.state.last_legal_fens = self.state.legal_fens
                if self.state.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.REMOTE):
                    self.state.legal_fens = []
                else:
                    self.state.legal_fens = await compute_legal_fens(self.state.game.copy())

            # molli: allow direct play of an alternative move for pico
            elif (
                fen in legal_fens_pico
                and fen not in self.state.legal_fens
                and fen != self.state.done_computer_fen
                and self.state.done_computer_fen
                and self.state.interaction_mode in (Mode.NORMAL, Mode.BRAIN)
                and not self.online_mode()
                and not self.emulation_mode()
                and not self.pgn_mode()
                and self.state.dgtmenu.get_game_altmove()
                and not self.state.takeback_active
            ):
                legal_moves = list(self.state.game.legal_moves)
                computer_move = self.state.done_move
                self.state.done_move = legal_moves[legal_fens_pico.index(fen)]
                self.state.best_move_posted = False
                self.state.best_move_displayed = None
                if computer_move:
                    DisplayMsg.show(
                        Message.COMPUTER_MOVE(move=computer_move, ponder=False, game=self.state.game.copy(), wait=False)
                    )
                    await asyncio.sleep(3)
                DisplayMsg.show(Message.ALTERNATIVE_MOVE(game=self.state.game.copy(), play_mode=self.state.play_mode))
                await asyncio.sleep(3)
                if self.state.done_move:
                    DisplayMsg.show(
                        Message.COMPUTER_MOVE(
                            move=self.state.done_move, ponder=False, game=self.state.game.copy(), wait=False
                        )
                    )
                    await asyncio.sleep(1.5)

                DisplayMsg.show(Message.COMPUTER_MOVE_DONE())
                logger.info("user did a move for pico")
                self.state.game.push(self.state.done_move)
                self.state.done_computer_fen = None
                self.state.done_move = chess.Move.null()
                game_end = self.state.check_game_state()
                valid = True
                if self.picotutor_mode():
                    # @todo why do we pop a picotutor move here?
                    await self.state.picotutor.pop_last_move()
                    valid = await self.state.picotutor.push_move(self.state.done_move)
                    if not valid:
                        self.state.picotutor.reset()
                        await self.state.picotutor.set_position(self.state.game.fen(), i_turn=self.state.game.turn)

                if game_end:
                    self.state.legal_fens = []
                    self.state.legal_fens_after_cmove = []
                    if self.online_mode():
                        await self.stop_search_and_clock()
                        self.state.stop_fen_timer()
                    await self.stop_search_and_clock()
                    DisplayMsg.show(game_end)
                else:
                    self.state.searchmoves.reset()
                    self.state.time_control.add_time(not self.state.game.turn)

                    # molli new tournament time control
                    if (
                        self.state.time_control.moves_to_go_orig > 0
                        and (self.state.game.fullmove_number - 1) == self.state.time_control.moves_to_go_orig
                    ):
                        self.state.time_control.add_game2(not self.state.game.turn)
                        t_player = False
                        msg = Message.TIMECONTROL_CHECK(
                            player=t_player,
                            movestogo=self.state.time_control.moves_to_go_orig,
                            time1=self.state.time_control.game_time,
                            time2=self.state.time_control.game_time2,
                        )
                        DisplayMsg.show(msg)

                    self.state.start_clock()

                self.state.legal_fens = await compute_legal_fens(
                    self.state.game.copy()
                )  # calc. new legal moves based on alt. move
                self.state.last_legal_fens = []

            # Player has done the computer or remote move on the board
            elif fen == self.state.done_computer_fen:
                logger.info("done move detected")
                assert self.state.interaction_mode in (
                    Mode.NORMAL,
                    Mode.BRAIN,
                    Mode.REMOTE,
                    Mode.TRAINING,
                ), (
                    "wrong mode: %s" % self.state.interaction_mode
                )
                DisplayMsg.show(Message.COMPUTER_MOVE_DONE())

                self.state.best_move_posted = False
                self.state.game.push(self.state.done_move)
                self.state.done_computer_fen = None
                self.state.done_move = chess.Move.null()

                if self.online_mode() or self.emulation_mode():
                    # for online or emulation engine the user time alraedy runs with move announcement
                    # => subtract time between announcement and execution
                    end_time_cmove_done = time.time()
                    cmove_time = math.floor(end_time_cmove_done - self.state.start_time_cmove_done)
                    if cmove_time > 0:
                        self.state.time_control.sub_online_time(self.state.game.turn, cmove_time)
                    cmove_time = 0
                    self.state.start_time_cmove_done = 0

                game_end = self.state.check_game_state()
                if game_end:
                    await self.update_elo(game_end.result)
                    self.state.legal_fens = []
                    self.state.legal_fens_after_cmove = []
                    if self.online_mode():
                        await self.stop_search_and_clock()
                        self.state.stop_fen_timer()
                    await self.stop_search_and_clock()
                    if not self.pgn_mode():
                        DisplayMsg.show(game_end)
                else:
                    self.state.searchmoves.reset()

                    self.state.time_control.add_time(not self.state.game.turn)

                    # molli new tournament time control
                    if (
                        self.state.time_control.moves_to_go_orig > 0
                        and (self.state.game.fullmove_number - 1) == self.state.time_control.moves_to_go_orig
                    ):
                        self.state.time_control.add_game2(not self.state.game.turn)
                        t_player = False
                        msg = Message.TIMECONTROL_CHECK(
                            player=t_player,
                            movestogo=self.state.time_control.moves_to_go_orig,
                            time1=self.state.time_control.game_time,
                            time2=self.state.time_control.game_time2,
                        )
                        DisplayMsg.show(msg)

                    if not self.online_mode() or self.state.game.fullmove_number > 1:
                        self.state.start_clock()
                    else:
                        DisplayMsg.show(Message.EXIT_MENU())  # show clock
                        end_time_cmove_done = 0

                    self.state.legal_fens = await compute_legal_fens(self.state.game.copy())

                    if self.pgn_mode():
                        await log_pgn(self.state)
                        if self.state.game.turn == chess.WHITE:
                            if self.state.max_guess_white > 0:
                                if self.state.no_guess_white > self.state.max_guess_white:
                                    self.state.last_legal_fens = []
                                    await self.get_next_pgn_move()
                            else:
                                self.state.last_legal_fens = []
                                await self.get_next_pgn_move()
                        elif self.state.game.turn == chess.BLACK:
                            if self.state.max_guess_black > 0:
                                if self.state.no_guess_black > self.state.max_guess_black:
                                    self.state.last_legal_fens = []
                                    await self.get_next_pgn_move()
                            else:
                                self.state.last_legal_fens = []
                                await self.get_next_pgn_move()

                self.state.last_legal_fens = []
                self.state.newgame_happened = False

                if self.state.game.fullmove_number < 1:
                    ModeInfo.reset_opening()
                if self.picotutor_mode() and self.state.dgtmenu.get_picoexplorer():
                    op_eco, op_name, op_moves, op_in_book = self.state.picotutor.get_opening()
                    if op_in_book and op_name:
                        ModeInfo.set_opening(self.state.book_in_use, str(op_name), op_eco)
                        DisplayMsg.show(Message.SHOW_TEXT(text_string=op_name))

            # molli: Premove/fast move: Player has done the computer move and his own move in rapid sequence
            elif (
                fen in self.state.legal_fens_after_cmove
                and self.state.flag_premove
                and self.state.done_move != chess.Move.null()
            ):  # and self.state.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.TRAINING):
                logger.info("standard move after computer move detected")
                # molli: execute computer move first
                self.state.game.push(self.state.done_move)
                self.state.done_computer_fen = None
                self.state.done_move = chess.Move.null()
                self.state.best_move_posted = False
                self.state.searchmoves.reset()

                self.state.time_control.add_time(not self.state.game.turn)
                # molli new tournament time control
                if (
                    self.state.time_control.moves_to_go_orig > 0
                    and (self.state.game.fullmove_number - 1) == self.state.time_control.moves_to_go_orig
                ):
                    self.state.time_control.add_game2(not self.state.game.turn)
                    t_player = False
                    msg = Message.TIMECONTROL_CHECK(
                        player=t_player,
                        movestogo=self.state.time_control.moves_to_go_orig,
                        time1=self.state.time_control.game_time,
                        time2=self.state.time_control.game_time2,
                    )
                    DisplayMsg.show(msg)

                self.state.last_legal_fens = []
                self.state.legal_fens_after_cmove = []
                self.state.legal_fens = await compute_legal_fens(
                    self.state.game.copy()
                )  # molli new legal fance based on cmove

                # standard user move handling
                legal_moves = list(self.state.game.legal_moves)
                move = legal_moves[state.legal_fens.index(fen)]
                await self.user_move(move, sliding=False)
                self.state.last_legal_fens = self.state.legal_fens
                self.state.newgame_happened = False
                if self.state.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.REMOTE, Mode.TRAINING):
                    self.state.legal_fens = []
                else:
                    self.state.legal_fens = await compute_legal_fens(self.state.game.copy())

            # Check if this is a previous legal position and allow user to restart from this position
            else:
                if (
                    self.state.take_back_locked
                    or self.online_mode()
                    or (self.emulation_mode() and not self.state.automatic_takeback)
                ):
                    handled_fen = False
                else:
                    handled_fen = False
                    game_copy = copy.deepcopy(self.state.game)
                    while game_copy.move_stack:
                        game_copy.pop()
                        if game_copy.board_fen() == fen:
                            handled_fen = True
                            logger.info("current game fen      : %s", self.state.game.fen())
                            logger.info("undoing game until fen: %s", fen)
                            await self.stop_search_and_clock()
                            while len(game_copy.move_stack) < len(self.state.game.move_stack):
                                self.state.game.pop()

                                if self.picotutor_mode():
                                    if self.state.best_move_posted:  # molli computer move already sent to tutor!
                                        await self.state.picotutor.pop_last_move()
                                        self.state.best_move_posted = False
                                    await self.state.picotutor.pop_last_move()

                            # its a complete new pos, delete saved values
                            self.state.done_computer_fen = None
                            self.state.done_move = self.state.pb_move = chess.Move.null()
                            self.state.searchmoves.reset()
                            self.state.takeback_active = True
                            await self.set_wait_state(
                                Message.TAKE_BACK(game=self.state.game.copy())
                            )  # new: force stop no matter if picochess turn

                            break

                    if self.pgn_mode():  # molli pgn
                        await log_pgn(self.state)
                        if self.state.max_guess_white > 0:
                            if self.state.game.turn == chess.WHITE:
                                if self.state.no_guess_white > self.state.max_guess_white:
                                    await self.get_next_pgn_move()
                        elif self.state.max_guess_black > 0:
                            if self.state.game.turn == chess.BLACK:
                                if self.state.no_guess_black > self.state.max_guess_black:
                                    await self.get_next_pgn_move()

            logger.debug("fen: %s result: %s", fen, handled_fen)
            self.state.stop_fen_timer()
            if handled_fen:
                self.state.flag_startup = False
                self.state.error_fen = None
                self.state.fen_error_occured = False
                if self.state.position_mode and self.state.delay_fen_error == 1:
                    tutor_str = "POSOK"
                    msg = Message.PICOTUTOR_MSG(eval_str=tutor_str, game=self.state.game.copy())
                    DisplayMsg.show(msg)
                    await asyncio.sleep(1)
                    if not self.state.done_computer_fen:
                        self.state.start_clock()
                    DisplayMsg.show(Message.EXIT_MENU())
                self.state.position_mode = False
            else:
                if fen == chess.STARTING_BOARD_FEN:
                    pos960 = 518
                    self.state.error_fen = None
                    if self.state.position_mode and self.state.delay_fen_error == 1:
                        tutor_str = "POSOK"
                        msg = Message.PICOTUTOR_MSG(eval_str=tutor_str, game=self.state.game.copy())
                        DisplayMsg.show(msg)
                        if not self.state.done_computer_fen:
                            self.state.start_clock()
                    self.state.position_mode = False
                    await Observable.fire(Event.NEW_GAME(pos960=pos960))
                else:
                    self.state.error_fen = fen
                    self.start_fen_timer()

        async def user_move(self, move: chess.Move, sliding: bool):
            """Handle an user move."""

            eval_str = ""

            self.state.take_back_locked = False

            logger.info("user move [%s] sliding: %s", move, sliding)
            if move not in self.state.game.legal_moves:
                logger.warning("illegal move [%s]", move)
            else:
                if self.state.interaction_mode == Mode.BRAIN:
                    ponder_hit = move == self.state.pb_move
                    logger.info(
                        "pondering move: [%s] res: Ponder%s",
                        self.state.pb_move,
                        "Hit" if ponder_hit else "Miss",
                    )
                else:
                    ponder_hit = False
                if sliding and ponder_hit:
                    logger.warning("sliding detected, turn ponderhit off")
                    ponder_hit = False

                await self.stop_search_and_clock(ponder_hit=ponder_hit)
                if (
                    self.state.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.OBSERVE, Mode.REMOTE, Mode.TRAINING)
                    and not sliding
                ):
                    self.state.time_control.add_time(self.state.game.turn)
                    # molli new tournament time control
                    if (
                        self.state.time_control.moves_to_go_orig > 0
                        and self.state.game.fullmove_number == self.state.time_control.moves_to_go_orig
                    ):
                        self.state.time_control.add_game2(self.state.game.turn)
                        t_player = True
                        msg = Message.TIMECONTROL_CHECK(
                            player=t_player,
                            movestogo=self.state.time_control.moves_to_go_orig,
                            time1=self.state.time_control.game_time,
                            time2=self.state.time_control.game_time2,
                        )
                        DisplayMsg.show(msg)
                    if self.online_mode():
                        # molli for online pseudo time sync
                        if self.state.online_decrement > 0:
                            self.state.time_control.sub_online_time(self.state.game.turn, self.state.online_decrement)

                game_before = self.state.game.copy()

                self.state.done_computer_fen = None
                self.state.done_move = chess.Move.null()
                fen = self.state.game.fen()
                turn = self.state.game.turn
                logger.debug("user did a move for user")
                self.state.game.push(move)  # this is where user move is made
                eval_str = ""

                if self.picotutor_mode() and not self.state.position_mode and not self.state.takeback_active:
                    l_mate = ""
                    t_hint_move = chess.Move.null()
                    valid = await self.state.picotutor.push_move(move)
                    # get evalutaion result and give user feedback
                    if self.state.dgtmenu.get_picowatcher():
                        if valid:
                            eval_str, l_mate = self.state.picotutor.get_user_move_eval()
                        else:
                            # invalid move from tutor side!? Something went wrong
                            eval_str = "ER"
                            await self.state.picotutor.set_position(self.state.game.fen(), i_turn=self.state.game.turn)
                            if self.state.play_mode == PlayMode.USER_BLACK:
                                await self.state.picotutor.set_user_color(chess.BLACK)
                            else:
                                await self.state.picotutor.set_user_color(chess.WHITE)
                                l_mate = ""
                            eval_str = ""  # no error message
                        if eval_str != "" and self.state.last_move != move:  # molli takeback_mame
                            msg = Message.PICOTUTOR_MSG(eval_str=eval_str)
                            DisplayMsg.show(msg)
                            if "??" in eval_str:
                                await asyncio.sleep(3)
                            else:
                                await asyncio.sleep(1)
                        if l_mate:
                            n_mate = int(l_mate)
                        else:
                            n_mate = 0
                        if n_mate < 0:
                            msg_str = "USRMATE_" + str(abs(n_mate))
                            msg = Message.PICOTUTOR_MSG(eval_str=msg_str)
                            DisplayMsg.show(msg)
                            await asyncio.sleep(1.5)
                        elif n_mate > 1:
                            n_mate = n_mate - 1
                            msg_str = "PICMATE_" + str(abs(n_mate))
                            msg = Message.PICOTUTOR_MSG(eval_str=msg_str)
                            DisplayMsg.show(msg)
                            await asyncio.sleep(1.5)
                        # get additional info in case of blunder
                        if eval_str == "??" and self.state.last_move != move:
                            t_hint_move = chess.Move.null()
                            threat_move = chess.Move.null()
                            (
                                t_hint_move,
                                t_pv_user_move,
                            ) = self.state.picotutor.get_user_move_info()

                            try:
                                # move 0 was bad because of threat 1 response
                                threat_move = t_pv_user_move[1]
                            except IndexError:
                                threat_move = chess.Move.null()

                            if threat_move != chess.Move.null():
                                game_tutor = game_before.copy()
                                game_tutor.push(move)
                                san_move = game_tutor.san(threat_move)
                                game_tutor.push(t_pv_user_move[1])  # 1st counter move

                                tutor_str = "THREAT" + san_move
                                msg = Message.PICOTUTOR_MSG(eval_str=tutor_str, game=game_tutor.copy())
                                DisplayMsg.show(msg)
                                await asyncio.sleep(5)

                            if t_hint_move != chess.Move.null():
                                game_tutor = game_before.copy()
                                san_move = game_tutor.san(t_hint_move)
                                game_tutor.push(t_hint_move)
                                tutor_str = "HINT" + san_move
                                msg = Message.PICOTUTOR_MSG(eval_str=tutor_str, game=game_tutor.copy())
                                DisplayMsg.show(msg)
                                await asyncio.sleep(5)

                    if self.state.game.fullmove_number < 1:
                        ModeInfo.reset_opening()

                self.state.searchmoves.reset()
                if self.state.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.TRAINING):
                    msg = Message.USER_MOVE_DONE(move=move, fen=fen, turn=turn, game=self.state.game.copy())
                    game_end = self.state.check_game_state()
                    if game_end:
                        await self.update_elo(game_end.result)
                        # molli: for online/emulation mode we have to publish this move as well to the engine
                        if self.online_mode():
                            logger.info("starting think()")
                            await self.think(msg)
                        elif self.emulation_mode():
                            logger.info("molli: starting mame_endgame()")
                            self.mame_endgame()
                            DisplayMsg.show(msg)
                            DisplayMsg.show(game_end)
                            self.state.legal_fens_after_cmove = []  # molli
                        else:
                            DisplayMsg.show(msg)
                            DisplayMsg.show(game_end)
                            self.state.legal_fens_after_cmove = []  # molli
                    else:
                        if self.state.interaction_mode in (Mode.NORMAL, Mode.TRAINING):
                            if not self.state.check_game_state():
                                # molli: automatic takeback of blunder moves for mame engines
                                if self.emulation_mode() and eval_str == "??" and self.state.last_move != move:
                                    # molli: do not send move to engine
                                    # wait for take back or lever button in case of no takeback
                                    if self.board_type == dgt.util.EBoard.NOEBOARD:
                                        await Observable.fire(Event.TAKE_BACK(take_back="PGN_TAKEBACK"))
                                    else:
                                        self.state.takeback_active = True
                                        self.state.automatic_takeback = True  # to be reset in think!
                                        await self.set_wait_state(Message.TAKE_BACK(game=self.state.game.copy()))
                                else:
                                    # send move to engine
                                    logger.debug("starting think()")
                                    await self.think(msg)
                        else:
                            assert self.state.interaction_mode == Mode.BRAIN
                            logger.debug("new implementation of ponderhit - starting think")
                            await self.think(msg)

                    self.state.last_move = move
                elif self.state.interaction_mode == Mode.REMOTE:
                    msg = Message.USER_MOVE_DONE(move=move, fen=fen, turn=turn, game=self.state.game.copy())
                    game_end = self.state.check_game_state()
                    DisplayMsg.show(msg)
                    if game_end:
                        DisplayMsg.show(game_end)
                    else:
                        await self.observe()
                elif self.state.interaction_mode == Mode.OBSERVE:
                    msg = Message.REVIEW_MOVE_DONE(move=move, fen=fen, turn=turn, game=self.state.game.copy())
                    game_end = self.state.check_game_state()
                    if game_end:
                        DisplayMsg.show(msg)
                        DisplayMsg.show(game_end)
                    else:
                        DisplayMsg.show(msg)
                        await self.observe()
                else:  # self.state.interaction_mode in (Mode.ANALYSIS, Mode.KIBITZ, Mode.PONDER):
                    msg = Message.REVIEW_MOVE_DONE(move=move, fen=fen, turn=turn, game=self.state.game.copy())
                    game_end = self.state.check_game_state()
                    if game_end:
                        DisplayMsg.show(msg)
                        DisplayMsg.show(game_end)
                    else:
                        DisplayMsg.show(msg)
                        await self.analyse()

                if (
                    self.picotutor_mode()
                    and not self.state.position_mode
                    and not self.state.takeback_active
                    and not self.state.automatic_takeback
                ):
                    if self.state.dgtmenu.get_picoexplorer():
                        opening_name = ""
                        opening_in_book = False
                        opening_eco, opening_name, _, opening_in_book = self.state.picotutor.get_opening()
                        if opening_in_book and opening_name:
                            ModeInfo.set_opening(self.state.book_in_use, str(opening_name), opening_eco)
                            DisplayMsg.show(Message.SHOW_TEXT(text_string=opening_name))
                            await asyncio.sleep(0.7)

                    if self.state.dgtmenu.get_picocomment() != PicoComment.COM_OFF and not game_end:
                        game_comment = ""
                        game_comment = self.state.picotutor.get_game_comment(
                            pico_comment=self.state.dgtmenu.get_picocomment(),
                            com_factor=self.state.dgtmenu.get_comment_factor(),
                        )
                        if game_comment:
                            DisplayMsg.show(Message.SHOW_TEXT(text_string=game_comment))
                            await asyncio.sleep(0.7)
                self.state.takeback_active = False

        async def observe(self) -> chess.engine.InfoDict | None:
            """Start a new ponder search on the current game."""
            info = await self.analyse()
            self.state.start_clock()
            return info

        async def update_elo(self, result):
            if self.engine.is_adaptive:
                self.state.rating = await self.engine.update_rating(
                    self.state.rating,
                    determine_result(result, self.state.play_mode, self.state.game.turn == chess.WHITE),
                )

        def update_elo_display(self):
            DisplayMsg.show(Message.SYSTEM_INFO(info={"rspeed": self.state.dgtmenu.get_engine_rspeed()}))
            if self.engine.is_adaptive:
                DisplayMsg.show(
                    Message.SYSTEM_INFO(
                        info={"user_elo": int(self.state.rating.rating), "engine_elo": self.engine.engine_rating}
                    )
                )
            elif self.engine.engine_rating > 0:
                user_elo = self.args.pgn_elo
                if self.state.rating is not None:
                    user_elo = str(int(self.state.rating.rating))
                DisplayMsg.show(
                    Message.SYSTEM_INFO(info={"user_elo": user_elo, "engine_elo": self.engine.engine_rating})
                )

        def start_fen_timer(self):
            """Start the fen timer in case an unhandled fen string been received from board."""
            delay = 0
            if self.state.position_mode:
                delay = self.state.delay_fen_error  # if a fen error already occured don't wait too long for next check
            else:
                delay = 4
                self.state.delay_fen_error = 4
            self.state.fen_timer = AsyncRepeatingTimer(delay, self.expired_fen_timer, self.loop, repeating=False)
            self.state.fen_timer.start()
            self.state.fen_timer_running = True

        async def mame_endgame(self):
            """
            Start a new search on the current game.

            If a move is found in the opening book, fire an event in a few seconds.
            """

            while not self.engine.is_waiting():
                await asyncio.sleep(0.05)
                logger.warning("engine is still not waiting")
            # self.engine.position(copy.deepcopy(game))

        def is_engine_playing_moves(self) -> bool:
            """return true if engine is playing moves based on self.state.Mode
            otherwise engine is watching and user plays both sides"""
            return bool(self.state.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.TRAINING))

        def debug_pv_info(self, info: chess.engine.InfoDict):
            if info:
                logger.debug(
                    "engine pv move: %s - depth %d - score %s",
                    info.get("pv")[0].uci(),
                    info.get("depth"),
                    str(info["score"]),
                )
            else:
                logger.debug("empty InfoDict")

        async def analyse(self) -> chess.engine.InfoDict | None:
            """analyse, observe etc depening on mode - create analysis info"""
            # it will work to get a short hint move also when not pondering
            info: InfoDict | None = None
            engine_playing_moves = self.is_engine_playing_moves()
            user_turn = self.state.is_user_turn()
            if self.state.picotutor.is_coach_analyser():
                # we ask picotutor engine for best move info
                if user_turn:
                    result = await self.state.picotutor.get_analysis()
                    if result.get("fen") == self.state.game.fen():
                        # analysis was for our current board position
                        info_list: list[chess.engine.InfoDict] = result.get("best")
                        if info_list:
                            info = info_list[0]  # pv first
                            logger.debug("we got picotutor best move!")
                            self.debug_pv_info(info)
            else:
                # get info from playing engine
                if not engine_playing_moves or user_turn:
                    deep_kwargs = {"limit": Limit(depth=FLOAT_MAX_ANALYSIS_DEPTH)}
                    was_running = await self.engine.start_analysis(self.state.game, deep_kwargs)
                    if was_running:
                        # optimisation, ask only if analysis was already running
                        result = await self.engine.get_analysis(self.state.game)
                        info_list: list[InfoDict] = result.get("best")
                        if info_list:
                            for info in info_list:
                                self.debug_pv_info(info)
                            info: InfoDict = info_list[0]  # pv first
            if info:
                await self.send_analyse(info, engine_playing_moves)
            return info

        async def send_analyse(self, info: chess.engine.InfoDict, engine_playing_moves: bool):
            """send info - if engine_playing_moves use user color
            otherwise its in analysing state and score is for turn"""
            # info is first multipv root move; send to displays
            if "pv" in info:
                # @todo check if we really have a move list here
                move = info.get("pv")[0]  # first move
                if move:
                    self.state.pb_move = move  # backward compatibility
                    await Observable.fire(Event.NEW_PV(pv=[move]))
            # send depth before score as score is assembling depth in receiver end
            if "depth" in info:
                d = info.get("depth")
                if d:
                    await Observable.fire(Event.NEW_DEPTH(depth=d))
            if "score" in info:
                s = info["score"]
                if engine_playing_moves:
                    p = s.pov(self.state.get_user_color()).score()
                else:
                    p = s.pov(self.state.game.turn).score()
                if p:
                    await Observable.fire(Event.NEW_SCORE(score=p, mate=s.is_mate()))

        async def expired_fen_timer(self):
            """Handle times up for an unhandled fen string send from board."""
            game_fen = ""
            self.state.fen_timer_running = False
            external_fen = ""
            internal_fen = ""

            if self.state.error_fen:
                logger.debug("fen_timer expired %s", self.state.error_fen)
                game_fen = self.state.game.board_fen()
                if (
                    self.state.interaction_mode in (Mode.NORMAL, Mode.TRAINING, Mode.BRAIN)
                    and self.state.error_fen != chess.STARTING_BOARD_FEN
                    and game_fen == chess.STARTING_BOARD_FEN
                    and self.state.flag_startup
                    and self.state.dgtmenu.get_game_contlast()
                    and not self.online_mode()
                    and not self.pgn_mode()
                    and not self.emulation_mode()
                ):
                    # molli: read the pgn of last game and restore correct game status and times
                    self.state.flag_startup = False
                    DisplayMsg.show(Message.RESTORE_GAME())
                    await asyncio.sleep(2)

                    l_pgn_file_name = "last_game.pgn"
                    await self.read_pgn_file(l_pgn_file_name)

                elif self.state.interaction_mode == Mode.PONDER and self.state.flag_flexible_ponder:
                    if (not self.state.newgame_happened) or self.state.flag_startup:
                        # molli: no error in analysis(ponder) mode => start new game with current fen
                        # and try to keep same player to play (white or black) but check
                        # if it is a legal position (otherwise switch sides or return error)
                        fen1 = self.state.error_fen
                        fen2 = self.state.error_fen
                        if self.state.game.turn == chess.WHITE:
                            fen1 += " w KQkq - 0 1"
                            fen2 += " b KQkq - 0 1"
                        else:
                            fen1 += " b KQkq - 0 1"
                            fen2 += " w KQkq - 0 1"
                        # ask python-chess to correct the castling string
                        bit_board = chess.Board(fen1)
                        bit_board.set_fen(bit_board.fen())
                        if bit_board.is_valid():
                            self.state.game = chess.Board(bit_board.fen())
                            await self.stop_search_and_clock()
                            self.engine.newgame(self.state.game.copy())
                            self.state.done_computer_fen = None
                            self.state.done_move = self.state.pb_move = chess.Move.null()
                            self.state.searchmoves.reset()
                            self.state.game_declared = False
                            self.state.legal_fens = await compute_legal_fens(self.state.game.copy())
                            self.state.legal_fens_after_cmove = []
                            self.state.last_legal_fens = []
                            DisplayMsg.show(Message.SHOW_TEXT(text_string="NEW_POSITION"))
                            await self.set_wait_state(
                                Message.START_NEW_GAME(game=self.state.game.copy(), newgame=False)
                            )
                            await self.stop_search_and_clock()
                            await self.analyse()
                        else:
                            # ask python-chess to correct the castling string
                            bit_board = chess.Board(fen2)
                            bit_board.set_fen(bit_board.fen())
                            if bit_board.is_valid():
                                self.state.game = chess.Board(bit_board.fen())
                                await self.stop_search_and_clock()
                                self.engine.newgame(self.state.game.copy())
                                self.state.done_computer_fen = None
                                self.state.done_move = self.state.pb_move = chess.Move.null()
                                self.state.searchmoves.reset()
                                self.state.game_declared = False
                                self.state.legal_fens = await compute_legal_fens(self.state.game.copy())
                                self.state.legal_fens_after_cmove = []
                                self.state.last_legal_fens = []
                                DisplayMsg.show(Message.SHOW_TEXT(text_string="NEW_POSITION"))
                                await self.set_wait_state(
                                    Message.START_NEW_GAME(game=self.state.game.copy(), newgame=False)
                                )
                                await self.stop_search_and_clock()
                                await self.analyse()
                            else:
                                logger.info("wrong fen %s for 4 secs", self.state.error_fen)
                                DisplayMsg.show(Message.WRONG_FEN())
                else:
                    logger.info("wrong fen %s for 4 secs", self.state.error_fen)
                    if self.online_mode():
                        # show computer opponents move again
                        if self.state.seeking_flag:
                            DisplayMsg.show(Message.SEEKING())
                        elif self.state.best_move_displayed:
                            DisplayMsg.show(
                                Message.COMPUTER_MOVE(
                                    move=self.state.done_move,
                                    ponder=False,
                                    game=self.state.game.copy(),
                                    wait=False,
                                )
                            )
                    fen_res = ""
                    internal_fen = self.state.game.board_fen()
                    external_fen = self.state.error_fen
                    fen_res = await compare_fen(external_fen, internal_fen)

                    if external_fen == self.state.last_error_fen:
                        if (
                            self.emulation_mode()
                            and self.state.dgtmenu.get_engine_rdisplay()
                            and self.state.artwork_in_use
                        ):
                            # switch windows/tasks
                            cmd = "xdotool keydown alt key Tab; sleep 0.2; xdotool keyup alt"
                            subprocess.run(
                                cmd,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                universal_newlines=True,
                                shell=True,
                            )
                    if (not self.state.position_mode) and fen_res:
                        if fen_res[4] == "K" or fen_res[4] == "k":
                            self.state.coach_triggered = True
                            if not self.picotutor_mode():
                                self.state.position_mode = True
                        else:
                            self.state.position_mode = True
                            self.state.coach_triggered = False
                        if external_fen != chess.STARTING_BOARD_FEN:
                            DisplayMsg.show(Message.WRONG_FEN())
                            await asyncio.sleep(2)
                        self.state.delay_fen_error = 4
                        # molli: Picochess correction messages
                        # show incorrect square(s) and piece to put or be removed
                    elif self.state.position_mode and fen_res:
                        self.state.delay_fen_error = 1
                        if not self.online_mode():
                            self.state.stop_clock()
                        msg = Message.POSITION_FAIL(fen_result=fen_res)
                        DisplayMsg.show(msg)
                        await asyncio.sleep(1)
                    else:
                        DisplayMsg.show(Message.EXIT_MENU())
                        self.state.delay_fen_error = 4

                    if (
                        self.state.interaction_mode in (Mode.NORMAL, Mode.TRAINING, Mode.BRAIN)
                        and game_fen != chess.STARTING_BOARD_FEN
                        and self.state.flag_startup
                    ):
                        if self.state.dgtmenu.get_enginename():
                            msg = Message.ENGINE_NAME(engine_name=self.state.engine_text)
                            DisplayMsg.show(msg)

                        if self.pgn_mode():
                            pgn_white = ""
                            pgn_black = ""
                            (
                                pgn_game_name,
                                pgn_problem,
                                pgn_fen,
                                pgn_result,
                                pgn_white,
                                pgn_black,
                            ) = await read_pgn_info()

                            if pgn_white:
                                DisplayMsg.show(Message.SHOW_TEXT(text_string=pgn_white))
                            if pgn_black:
                                DisplayMsg.show(Message.SHOW_TEXT(text_string=pgn_black))

                            if pgn_result:
                                DisplayMsg.show(Message.SHOW_TEXT(text_string=pgn_result))

                            if "mate in" in pgn_problem or "Mate in" in pgn_problem:
                                await self.set_fen_from_pgn(pgn_fen)
                                DisplayMsg.show(Message.SHOW_TEXT(text_string=pgn_problem))
                            else:
                                DisplayMsg.show(Message.SHOW_TEXT(text_string=pgn_game_name))

                    else:
                        if self.state.done_computer_fen and not self.state.position_mode:
                            DisplayMsg.show(Message.EXIT_MENU())
                    self.state.fen_error_occured = True  # to be reset in fen_handling
            self.state.flag_startup = False
            self.state.newgame_happened = False
            self.state.last_error_fen = external_fen

        async def read_pgn_file(self, file_name: str):
            """Read game from PGN file"""
            logger.debug("molli: read game from pgn file")

            l_filename = "games" + os.sep + file_name
            try:
                l_file_pgn = open(l_filename)
                if not l_file_pgn:
                    return
            except OSError:
                return

            l_game_pgn = chess.pgn.read_game(l_file_pgn)
            l_file_pgn.close()

            logger.debug("molli: read game filename %s", l_filename)

            await self.stop_search_and_clock()

            if self.picotutor_mode():
                self.state.picotutor.reset()

            self.state.game = chess.Board()
            l_move = chess.Move.null()

            if l_game_pgn.headers["Event"]:
                DisplayMsg.show(Message.SHOW_TEXT(text_string=str(l_game_pgn.headers["Event"])))

            if l_game_pgn.headers["White"]:
                DisplayMsg.show(Message.SHOW_TEXT(text_string=str(l_game_pgn.headers["White"])))

            DisplayMsg.show(Message.SHOW_TEXT(text_string="versus"))

            if l_game_pgn.headers["Black"]:
                DisplayMsg.show(Message.SHOW_TEXT(text_string=str(l_game_pgn.headers["Black"])))

            if l_game_pgn.headers["Result"]:
                DisplayMsg.show(Message.SHOW_TEXT(text_string=str(l_game_pgn.headers["Result"])))

            await asyncio.sleep(2)
            DisplayMsg.show(Message.READ_GAME)
            await asyncio.sleep(2)

            for l_move in l_game_pgn.main_line():
                self.state.game.push(l_move)

            # take back last move in order to send it with user_move for web publishing
            if l_move:
                self.state.game.pop()

            self.engine.newgame(self.state.game.copy())

            # switch temporarly picotutor off
            self.state.flag_picotutor = False

            if l_move:
                # publish current position to webserver
                await self.user_move(l_move, sliding=True)

            self.state.flag_picotutor = True

            await self.stop_search_and_clock()
            turn = self.state.game.turn
            self.state.done_computer_fen = None
            self.state.done_move = self.state.pb_move = chess.Move.null()
            self.state.play_mode = PlayMode.USER_WHITE if turn == chess.WHITE else PlayMode.USER_BLACK

            l_pico_depth = 0
            try:
                if "PicoDepth" in l_game_pgn.headers and l_game_pgn.headers["PicoDepth"]:
                    l_pico_depth = int(l_game_pgn.headers["PicoDepth"])
            except ValueError:
                pass

            l_pico_node = 0
            try:
                if "PicoNode" in l_game_pgn.headers and l_game_pgn.headers["PicoNode"]:
                    l_pico_node = int(l_game_pgn.headers["PicoNode"])
            except ValueError:
                pass

            if "PicoTimeControl" in l_game_pgn.headers and l_game_pgn.headers["PicoTimeControl"]:
                l_pico_tc = str(l_game_pgn.headers["PicoTimeControl"])
                self.state.time_control, time_text = await self.state.transfer_time(
                    l_pico_tc.split(), depth=l_pico_depth, node=l_pico_node
                )

            try:
                if "PicoRemTimeW" in l_game_pgn.headers and l_game_pgn.headers["PicoRemTimeW"]:
                    lt_white = int(l_game_pgn.headers["PicoRemTimeW"])
            except ValueError:
                lt_white = 0

            try:
                if "PicoRemTimeB" in l_game_pgn.headers and l_game_pgn.headers["PicoRemTimeB"]:
                    lt_black = int(l_game_pgn.headers["PicoRemTimeB"])
            except ValueError:
                lt_black = 0

            tc_init = self.state.time_control.get_parameters()
            self.state.tc_init_last = self.state.time_control.get_parameters()

            tc_init["internal_time"] = {chess.WHITE: lt_white, chess.BLACK: lt_black}
            text = self.state.dgttranslate.text("N00_oktime")
            self.state.time_control.reset()

            await Observable.fire(Event.SET_TIME_CONTROL(tc_init=tc_init, time_text=text, show_ok=False))
            self.state.stop_clock()
            DisplayMsg.show(Message.EXIT_MENU())

            self.state.searchmoves.reset()
            self.state.game_declared = False

            self.state.legal_fens = await compute_legal_fens(self.state.game.copy())
            self.state.legal_fens_after_cmove = []
            self.state.last_legal_fens = []
            await self.stop_search_and_clock()
            # self.engine.position(copy.deepcopy(self.state.game))

            game_end = self.state.check_game_state()
            if game_end:
                self.state.play_mode = PlayMode.USER_WHITE if turn == chess.WHITE else PlayMode.USER_BLACK
                self.state.legal_fens = []
                self.state.legal_fens_after_cmove = []
                DisplayMsg.show(game_end)
            else:
                self.state.play_mode = PlayMode.USER_WHITE if turn == chess.WHITE else PlayMode.USER_BLACK
                text = self.state.play_mode.value
                msg = Message.PLAY_MODE(
                    play_mode=self.state.play_mode,
                    play_mode_text=self.state.dgttranslate.text(text),
                )
                DisplayMsg.show(msg)
                await asyncio.sleep(1)

            self.state.take_back_locked = True  # important otherwise problems for setting up the position

        def emulation_mode(self):
            emulation = False
            if "(mame" in self.engine.get_name() or "(mess" in self.engine.get_name() or self.engine.is_mame:
                emulation = True
            ModeInfo.set_emulation_mode(emulation)
            return emulation

        async def set_emulation_tctrl(self):
            logger.debug("molli: set_emulation_tctrl")
            if self.emulation_mode():
                pico_depth = 0
                pico_node = 0
                pico_tctrl_str = ""

                self.state.stop_clock()
                self.state.time_control.stop_internal(log=False)

                uci_options = self.engine.get_pgn_options()
                pico_tctrl_str = ""

                try:
                    if "PicoTimeControl" in uci_options:
                        pico_tctrl_str = str(uci_options["PicoTimeControl"])
                except IndexError:
                    pico_tctrl_str = ""

                try:
                    if "PicoDepth" in uci_options:
                        pico_depth = int(uci_options["PicoDepth"])
                except IndexError:
                    pico_depth = 0

                try:
                    if "PicoNode" in uci_options:
                        pico_node = int(uci_options["PicoNode"])
                except IndexError:
                    pico_node = 0

                if pico_tctrl_str:
                    logger.debug("molli: set_emulation_tctrl input %s", pico_tctrl_str)
                    self.state.time_control, time_text = await self.state.transfer_time(
                        pico_tctrl_str.split(), depth=pico_depth, node=pico_node
                    )
                    tc_init = self.state.time_control.get_parameters()
                    text = self.state.dgttranslate.text("N00_oktime")
                    await Observable.fire(Event.SET_TIME_CONTROL(tc_init=tc_init, time_text=text, show_ok=True))
                    self.state.stop_fen_timer()

        async def det_pgn_guess_tctrl(self):
            self.state.max_guess_white = 0
            self.state.max_guess_black = 0

            logger.debug("molli pgn: determine pgn guess")

            uci_options = self.engine.get_pgn_options()

            logger.debug("molli pgn: uci_options %s", str(uci_options))

            if "max_guess" in uci_options:
                self.state.max_guess = int(uci_options["max_guess"])
            else:
                self.state.max_guess = 0

            if "think_time" in uci_options:
                self.state.think_time = int(uci_options["think_time"])
            else:
                self.state.think_time = 0

            if "pgn_game_file" in uci_options:
                logger.debug("molli pgn: pgn_game_file; %s", str(uci_options["pgn_game_file"]))
                if "book_test" in str(uci_options["pgn_game_file"]):
                    self.state.pgn_book_test = True
                    logger.debug("molli pgn: pgn_book_test set to True")
                else:
                    self.state.pgn_book_test = False
                    logger.debug("molli pgn: pgn_book_test set to False")
            else:
                logger.debug("molli pgn: pgn_book_test not found => False")
                self.state.pgn_book_test = False

            self.state.max_guess_white = self.state.max_guess
            self.state.max_guess_black = 0

            tc_init = self.state.time_control.get_parameters()
            tc_init["mode"] = TimeMode.FIXED
            tc_init["fixed"] = self.state.think_time
            tc_init["blitz"] = 0
            tc_init["fischer"] = 0

            tc_init["blitz2"] = 0
            tc_init["moves_to_go"] = 0
            tc_init["depth"] = 0
            tc_init["node"] = 0

            self.state.stop_clock()
            text = self.state.dgttranslate.text("N00_oktime")
            self.state.time_control.reset()
            await Observable.fire(Event.SET_TIME_CONTROL(tc_init=tc_init, time_text=text, show_ok=True))
            self.state.stop_clock()
            DisplayMsg.show(Message.EXIT_MENU())

        def engine_mode(self):
            """call when engine mode is changed"""
            if self.state.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.TRAINING):
                # optimisation, dont ask for ponder unless needed
                ponder_mode = True if self.state.interaction_mode == Mode.BRAIN else False
                self.engine.set_mode(ponder=ponder_mode)
                if self.state.interaction_mode in (Mode.BRAIN, Mode.TRAINING):
                    self.background_analyse_timer.start()
                else:
                    self.background_analyse_timer.stop()  # Normal mode no analysis
                # mode might have changed back to playing, activate tutor
                self.state.picotutor.set_status(
                    self.state.dgtmenu.get_picowatcher(),
                    self.state.dgtmenu.get_picocoach(),
                    self.state.dgtmenu.get_picoexplorer(),
                    self.state.dgtmenu.get_picocomment(),
                )
                self.state.picotutor.reset()
            elif self.state.interaction_mode in (Mode.ANALYSIS, Mode.KIBITZ, Mode.OBSERVE, Mode.PONDER):
                self.engine.set_mode()
                self.background_analyse_timer.start()  # permanent brain in analysis mode
                # tutor cannot run if playing engine is only watching?
                self.state.picotutor.set_status(
                    watcher=False,
                    coach=PicoCoach.COACH_OFF,
                    explorer=self.state.dgtmenu.get_picoexplorer(),
                    comments=False,
                )

        def remote_engine_mode(self):
            if "remote" in self.state.engine_file:
                return True
            else:
                return False

        async def _pv_score_depth_analyser(self):
            """Analyse PV score depth in the background"""
            if self.state.game:
                if self.state.game.fullmove_number > 1 and not self.state.game.is_game_over():
                    # @todo find a way to skip background analysis
                    # while we are doing inbook
                    await self.analyse()

        async def event_consumer(self):
            """Event consumer for main"""
            logger.info("evt_queue ready")
            while True:
                event = await evt_queue.get()
                logger.debug("evt_queue incoming message")
                await self.process_main_events(event)

        async def process_main_events(self, event):
            """Consume event from evt_queue"""
            logger.debug("received event from evt_queue: %s", event)
            if isinstance(event, Event.FEN):
                await self.process_fen(event.fen, self.state)

            elif isinstance(event, Event.KEYBOARD_MOVE):
                move = event.move
                logger.debug("keyboard move [%s]", move)
                if move not in self.state.game.legal_moves:
                    logger.warning("illegal move. fen: [%s]", self.state.game.fen())
                else:
                    game_copy = self.state.game.copy()
                    game_copy.push(move)
                    fen = game_copy.board_fen()
                    DisplayMsg.show(Message.DGT_FEN(fen=fen, raw=False))

            elif isinstance(event, Event.LEVEL):
                if event.options:
                    await self.engine.startup(event.options, self.state.rating)
                self.state.new_engine_level = event.level_name
                DisplayMsg.show(
                    Message.LEVEL(
                        level_text=event.level_text,
                        level_name=event.level_name,
                        do_speak=bool(event.options),
                    )
                )

            elif isinstance(event, Event.NEW_ENGINE):
                old_file = self.state.engine_file
                old_options = {}
                old_options = self.engine.get_pgn_options()
                engine_fallback = False
                # Stop the old engine cleanly
                if not self.emulation_mode():
                    await self.stop_search()
                # Closeout the engine process and threads

                self.state.engine_file = event.eng["file"]
                self.state.artwork_in_use = False
                engine_file_to_load = self.state.engine_file  # assume not mame
                if "/mame/" in self.state.engine_file and self.state.dgtmenu.get_engine_rdisplay():
                    engine_file_art = self.state.engine_file + "_art"
                    my_file = Path(engine_file_art)
                    if my_file.is_file():
                        self.state.artwork_in_use = True
                        engine_file_to_load = engine_file_art  # load mame
                    else:
                        DisplayMsg.show(Message.SHOW_TEXT(text_string="NO_ARTWORK"))

                help_str = engine_file_to_load.rsplit(os.sep, 1)[1]
                remote_file = self.engine_remote_home + os.sep + help_str

                flag_eng = False
                flag_eng = await check_ssh(
                    self.args.engine_remote_server, self.args.engine_remote_user, self.args.engine_remote_pass
                )

                logger.debug("molli check_ssh:%s", flag_eng)
                DisplayMsg.show(Message.ENGINE_SETUP())

                if self.remote_engine_mode():
                    if flag_eng:
                        if not self.uci_remote_shell:
                            if self.remote_windows():
                                logger.info("molli: Remote Windows Connection")
                                self.uci_remote_shell = UciShell(
                                    hostname=self.args.engine_remote_server,
                                    username=self.args.engine_remote_user,
                                    key_file=self.args.engine_remote_key,
                                    password=self.args.engine_remote_pass,
                                    windows=True,
                                )
                            else:
                                logger.info("molli: Remote Mac/UNIX Connection")
                                self.uci_remote_shell = UciShell(
                                    hostname=self.args.engine_remote_server,
                                    username=self.args.engine_remote_user,
                                    key_file=self.args.engine_remote_key,
                                    password=self.args.engine_remote_pass,
                                )
                    else:
                        engine_fallback = True
                        DisplayMsg.show(Message.ONLINE_FAILED())
                        await asyncio.sleep(2)
                        DisplayMsg.show(Message.REMOTE_FAIL())
                        await asyncio.sleep(2)

                await self.engine.quit()
                # Load the new one and send self.args.
                if self.remote_engine_mode() and flag_eng and self.uci_remote_shell:
                    self.engine = UciEngine(
                        file=remote_file,
                        uci_shell=self.uci_remote_shell,
                        mame_par=self.calc_engine_mame_par(),
                        loop=self.loop,
                    )
                    await self.engine.open_engine()
                else:
                    self.engine = UciEngine(
                        file=engine_file_to_load,
                        uci_shell=self.uci_local_shell,
                        mame_par=self.calc_engine_mame_par(),
                        loop=self.loop,
                    )
                    await self.engine.open_engine()
                    if engine_file_to_load != self.state.engine_file:
                        await asyncio.sleep(1)  # mame artwork wait
                if not self.engine.loaded_ok():
                    # New engine failed to start, restart old engine
                    logger.error("new engine failed to start, reverting to %s", old_file)
                    engine_fallback = True
                    event.options = old_options
                    self.state.engine_file = old_file
                    help_str = old_file.rsplit(os.sep, 1)[1]
                    remote_file = self.engine_remote_home + os.sep + help_str

                    if self.remote_engine_mode() and flag_eng and self.uci_remote_shell:
                        self.engine = UciEngine(
                            file=remote_file,
                            uci_shell=self.uci_remote_shell,
                            mame_par=self.calc_engine_mame_par(),
                            loop=self.loop,
                        )
                        await self.engine.open_engine()
                    else:
                        # restart old mame engine?
                        self.state.artwork_in_use = False
                        if "/mame/" in old_file and self.state.dgtmenu.get_engine_rdisplay():
                            old_file_art = old_file + "_art"
                            my_file = Path(old_file_art)
                            if my_file.is_file():
                                self.state.artwork_in_use = True
                                old_file = old_file_art

                        self.engine = UciEngine(
                            file=old_file,
                            uci_shell=self.uci_local_shell,
                            mame_par=self.calc_engine_mame_par(),
                            loop=self.loop,
                        )
                        await self.engine.open_engine()
                    if not self.engine.loaded_ok():
                        # Help - old engine failed to restart. There is no engine
                        logger.error("no engines started")
                        DisplayMsg.show(Message.ENGINE_FAIL())
                        await asyncio.sleep(3)
                        sys.exit(-1)
                # All done - rock'n'roll
                # @todo remove check for BRAIN mode and has_ponder
                if self.state.interaction_mode == Mode.BRAIN and not self.engine.has_ponder():
                    logger.debug("new engine doesnt support brain mode, reverting to %s", old_file)
                    engine_fallback = True
                    await self.engine.quit()
                    if self.remote_engine_mode() and flag_eng and self.uci_remote_shell:
                        self.engine = UciEngine(
                            file=remote_file,
                            uci_shell=self.uci_remote_shell,
                            mame_par=self.calc_engine_mame_par(),
                            loop=self.loop,
                        )
                        await self.engine.open_engine()
                    else:
                        self.engine = UciEngine(
                            file=old_file,
                            uci_shell=self.uci_local_shell,
                            mame_par=self.calc_engine_mame_par(),
                            loop=self.loop,
                        )
                        await self.engine.open_engine()
                    await self.engine.startup(old_options, self.state.rating)
                    self.engine.newgame(self.state.game.copy())
                    if not self.engine.loaded_ok():
                        logger.error("no engines started")
                        DisplayMsg.show(Message.ENGINE_FAIL())
                        await asyncio.sleep(3)
                        sys.exit(-1)

                if (
                    self.emulation_mode()
                    and self.state.dgtmenu.get_engine_rdisplay()
                    and self.state.artwork_in_use
                    and not self.state.dgtmenu.get_engine_rwindow()
                ):
                    # switch to fullscreen
                    cmd = "xdotool keydown alt key F11; sleep 0.2 xdotool keyup alt"
                    subprocess.run(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        universal_newlines=True,
                        shell=True,
                    )

                await self.engine.startup(event.options, self.state.rating)

                if self.online_mode():
                    self.state.stop_clock()
                    DisplayMsg.show(Message.ONLINE_LOGIN())
                    # check if login successful (correct server & correct user)
                    (
                        self.login,
                        own_color,
                        self.self.own_user,
                        self.self.opp_user,
                        self.game_time,
                        self.fischer_inc,
                    ) = await read_online_user_info()
                    logger.debug("molli online login: %s", self.login)

                    if "ok" not in self.login:
                        # server connection failed: check settings!
                        DisplayMsg.show(Message.ONLINE_FAILED())
                        await asyncio.sleep(3)
                        engine_fallback = True
                        event.options = dict()
                        old_file = "engines/aarch64/a-stockf"
                        help_str = old_file.rsplit(os.sep, 1)[1]
                        remote_file = self.engine_remote_home + os.sep + help_str

                        if self.remote_engine_mode() and flag_eng and self.uci_remote_shell:
                            self.engine = UciEngine(
                                file=remote_file,
                                uci_shell=self.uci_remote_shell,
                                mame_par=self.calc_engine_mame_par(),
                                loop=self.loop,
                            )
                            await self.engine.open_engine()
                        else:
                            self.engine = UciEngine(
                                file=old_file,
                                uci_shell=self.uci_local_shell,
                                mame_par=self.calc_engine_mame_par(),
                                loop=self.loop,
                            )
                            await self.engine.open_engine()
                        if not self.engine.loaded_ok():
                            # Help - old engine failed to restart. There is no engine
                            logger.error("no engines started")
                            DisplayMsg.show(Message.ENGINE_FAIL())
                            await asyncio.sleep(3)
                            sys.exit(-1)
                        await self.engine.startup(event.options, self.state.rating)
                    else:
                        await asyncio.sleep(2)
                elif self.emulation_mode() or self.pgn_mode():
                    # molli for emulation engines we have to reset to starting position
                    await self.stop_search_and_clock()
                    game_fen = self.state.game.board_fen()
                    self.state.game = chess.Board()
                    self.state.game.turn = chess.WHITE
                    self.state.play_mode = PlayMode.USER_WHITE
                    self.engine.newgame(self.state.game.copy())
                    self.state.done_computer_fen = None
                    self.state.done_move = self.state.pb_move = chess.Move.null()
                    self.state.searchmoves.reset()
                    self.state.game_declared = False
                    self.state.legal_fens = await compute_legal_fens(self.state.game.copy())
                    self.state.last_legal_fens = []
                    self.state.legal_fens_after_cmove = []
                    self.is_out_of_time_already = False
                    real_new_game = game_fen != chess.STARTING_BOARD_FEN
                    msg = Message.START_NEW_GAME(game=self.state.game.copy(), newgame=real_new_game)
                    DisplayMsg.show(msg)
                else:
                    self.engine.newgame(self.state.game.copy())

                self.engine_mode()

                if engine_fallback:
                    msg = Message.ENGINE_FAIL()
                    # molli: in case of engine fail, set correct old engine display settings
                    for index in range(0, len(EngineProvider.installed_engines)):
                        if EngineProvider.installed_engines[index]["file"] == old_file:
                            logger.debug("molli index:%s", str(index))
                            self.state.dgtmenu.set_engine_index(index)
                    # in case engine fails, reset level as well
                    if self.state.old_engine_level:
                        level_text = self.state.dgttranslate.text("B00_level", self.state.old_engine_level)
                        level_text.beep = False
                    else:
                        level_text = None
                    DisplayMsg.show(
                        Message.LEVEL(
                            level_text=level_text,
                            level_name=self.state.old_engine_level,
                            do_speak=False,
                        )
                    )
                    self.state.new_engine_level = self.state.old_engine_level
                else:
                    self.state.searchmoves.reset()
                    msg = Message.ENGINE_READY(
                        eng=event.eng,
                        eng_text=event.eng_text,
                        engine_name=self.engine.get_name(),
                        has_levels=self.engine.has_levels(),
                        has_960=self.engine.has_chess960(),
                        has_ponder=self.engine.has_ponder(),
                        show_ok=event.show_ok,
                    )
                # Schedule cleanup of old objects
                gc.collect()

                await self.set_wait_state(msg, not engine_fallback)
                if self.state.interaction_mode in (
                    Mode.NORMAL,
                    Mode.BRAIN,
                    Mode.TRAINING,
                ):  # engine isnt started/searching => stop the clock
                    self.state.stop_clock()
                self.state.engine_text = state.dgtmenu.get_current_engine_name()
                self.state.dgtmenu.exit_menu()

                self.state.old_engine_level = self.state.new_engine_level
                self.state.engine_level = self.state.new_engine_level
                self.state.dgtmenu.set_state_current_engine(self.state.engine_file)
                self.state.dgtmenu.exit_menu()
                # here dont care if engine supports pondering, cause Mode.NORMAL from startup
                if (
                    not self.remote_engine_mode()
                    and not self.online_mode()
                    and not self.pgn_mode()
                    and not engine_fallback
                ):
                    # dont write engine(_level) if remote/online engine or engine failure
                    write_picochess_ini("engine", event.eng["file"])
                    write_picochess_ini("engine-level", self.state.engine_level)

                if self.pgn_mode():
                    if not self.state.flag_last_engine_pgn:
                        self.state.tc_init_last = self.state.time_control.get_parameters()

                    await self.det_pgn_guess_tctrl()

                    self.state.flag_last_engine_pgn = True
                elif self.emulation_mode():
                    if not self.state.flag_last_engine_emu:
                        self.state.tc_init_last = self.state.time_control.get_parameters()
                    self.state.flag_last_engine_emu = True
                else:
                    # molli restore last saved timecontrol
                    if (
                        (self.state.flag_last_engine_pgn or self.state.flag_last_engine_emu)
                        and self.state.tc_init_last is not None
                        and not self.online_mode()
                        and not self.emulation_mode()
                        and not self.pgn_mode()
                    ):
                        self.state.stop_clock()
                        text = self.state.dgttranslate.text("N00_oktime")
                        await Observable.fire(
                            Event.SET_TIME_CONTROL(tc_init=self.state.tc_init_last, time_text=text, show_ok=True)
                        )
                        self.state.stop_clock()
                        DisplayMsg.show(Message.EXIT_MENU())
                    self.state.flag_last_engine_pgn = False
                    self.state.flag_last_engine_emu = False
                    self.state.tc_init_last = None

                self.state.comment_file = self.get_comment_file()  # for picotutor game comments like Boris & Sargon
                self.state.picotutor.init_comments(self.state.comment_file)

                if self.emulation_mode():
                    await self.set_emulation_tctrl()

                if self.pgn_mode():
                    pgn_fen = ""
                    (
                        pgn_game_name,
                        pgn_problem,
                        pgn_fen,
                        pgn_result,
                        pgn_white,
                        pgn_black,
                    ) = await read_pgn_info()
                    if "mate in" in pgn_problem or "Mate in" in pgn_problem or pgn_fen != "":
                        await self.set_fen_from_pgn(pgn_fen)
                        self.state.play_mode = (
                            PlayMode.USER_WHITE if self.state.game.turn == chess.WHITE else PlayMode.USER_BLACK
                        )
                        msg = Message.PLAY_MODE(
                            play_mode=self.state.play_mode,
                            play_mode_text=self.state.dgttranslate.text(self.state.play_mode.value),
                        )
                        DisplayMsg.show(msg)
                        await asyncio.sleep(1)

                if self.online_mode():
                    ModeInfo.set_online_mode(mode=True)
                    logger.debug("online game fen: %s", self.state.game.fen())
                    if (not self.state.flag_last_engine_online) or (
                        self.state.game.board_fen() == chess.STARTING_BOARD_FEN
                    ):
                        pos960 = 518
                        await Observable.fire(Event.NEW_GAME(pos960=pos960))
                    self.state.flag_last_engine_online = True
                else:
                    self.state.flag_last_engine_online = False
                    ModeInfo.set_online_mode(mode=False)

                if self.pgn_mode():
                    ModeInfo.set_pgn_mode(mode=True)
                    pos960 = 518
                    await Observable.fire(Event.NEW_GAME(pos960=pos960))
                else:
                    ModeInfo.set_pgn_mode(mode=False)

                self.update_elo_display()

            elif isinstance(event, Event.SETUP_POSITION):
                logger.debug("setting up custom fen: %s", event.fen)
                uci960 = event.uci960
                self.state.position_mode = False

                if self.state.game.move_stack:
                    if not (self.state.game.is_game_over() or self.state.game_declared):
                        result = GameResult.ABORT
                        DisplayMsg.show(
                            Message.GAME_ENDS(
                                tc_init=self.state.time_control.get_parameters(),
                                result=result,
                                play_mode=self.state.play_mode,
                                game=self.state.game.copy(),
                            )
                        )
                self.state.game = chess.Board(event.fen)  # check what uci960 should do here
                # see new_game
                await self.stop_search_and_clock()
                if self.engine.has_chess960():
                    self.engine.option("UCI_Chess960", uci960)
                    await self.engine.send()

                DisplayMsg.show(Message.SHOW_TEXT(text_string="NEW_POSITION_SCAN"))
                self.engine.newgame(self.state.game.copy())
                self.state.done_computer_fen = None
                self.state.done_move = self.state.pb_move = chess.Move.null()
                self.state.legal_fens_after_cmove = []
                self.is_out_of_time_already = False
                self.state.time_control.reset()
                self.state.searchmoves.reset()
                self.state.game_declared = False

                if self.picotutor_mode():
                    self.state.picotutor.reset()
                    await self.state.picotutor.set_position(
                        self.state.game.fen(), i_turn=self.state.game.turn, i_ignore_expl=True
                    )
                    if self.state.play_mode == PlayMode.USER_BLACK:
                        await self.state.picotutor.set_user_color(chess.BLACK)
                    else:
                        await self.state.picotutor.set_user_color(chess.WHITE)
                await self.set_wait_state(Message.START_NEW_GAME(game=self.state.game.copy(), newgame=True))
                if self.emulation_mode():
                    if self.state.dgtmenu.get_engine_rdisplay() and self.state.artwork_in_use:
                        # switch windows/tasks
                        cmd = "xdotool keydown alt key Tab; sleep 0.2; xdotool keyup alt"
                        subprocess.run(
                            cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            universal_newlines=True,
                            shell=True,
                        )
                    DisplayMsg.show(Message.SHOW_TEXT(text_string="NEW_POSITION"))
                    self.engine.is_ready()
                self.state.position_mode = False
                tutor_str = "POSOK"
                msg = Message.PICOTUTOR_MSG(eval_str=tutor_str, game=self.state.game.copy())
                DisplayMsg.show(msg)
                await asyncio.sleep(1)

            elif isinstance(event, Event.NEW_GAME):
                last_move_no = self.state.game.fullmove_number
                self.state.takeback_active = False
                self.state.automatic_takeback = False
                self.state.reset_auto = False
                self.state.flag_startup = False
                self.state.flag_pgn_game_over = False
                ModeInfo.set_game_ending(result="*")  # initialize game result for game saving status
                self.state.position_mode = False
                self.state.fen_error_occured = False
                self.state.error_fen = None
                self.state.newgame_happened = True
                newgame = (
                    self.state.game.move_stack
                    or (self.state.game.chess960_pos() != event.pos960)
                    or self.state.best_move_posted
                    or self.state.done_computer_fen
                )
                if newgame:
                    logger.debug("starting a new game with code: %s", event.pos960)
                    uci960 = event.pos960 != 518

                    if not (self.state.game.is_game_over() or self.state.game_declared) or self.pgn_mode():
                        if self.emulation_mode():  # force abortion for mame
                            if self.state.is_not_user_turn():
                                # clock must be stopped BEFORE the "book_move"
                                # event cause SetNRun resets the clock display
                                self.state.stop_clock()
                                self.state.best_move_posted = True
                                # @todo 8/8/R6P/1R6/7k/2B2K1p/8/8 and sliding Ra6 over a5 to a4
                                # handle this in correct way!!
                                self.state.game_declared = True
                                self.state.stop_fen_timer()
                                self.state.legal_fens_after_cmove = []

                        result = GameResult.ABORT
                        DisplayMsg.show(
                            Message.GAME_ENDS(
                                tc_init=self.state.time_control.get_parameters(),
                                result=result,
                                play_mode=self.state.play_mode,
                                game=self.state.game.copy(),
                            )
                        )
                        await asyncio.sleep(0.3)

                    self.state.game = chess.Board()
                    self.state.game.turn = chess.WHITE

                    if uci960:
                        self.state.game.set_chess960_pos(event.pos960)

                    if self.state.play_mode != PlayMode.USER_WHITE:
                        self.state.play_mode = PlayMode.USER_WHITE
                        msg = Message.PLAY_MODE(
                            play_mode=self.state.play_mode,
                            play_mode_text=self.state.dgttranslate.text(str(self.state.play_mode.value)),
                        )
                        DisplayMsg.show(msg)
                    await self.stop_search_and_clock()

                    # see setup_position
                    if self.engine.has_chess960():
                        self.engine.option("UCI_Chess960", uci960)
                        await self.engine.send()

                    if self.state.interaction_mode == Mode.TRAINING:
                        self.engine.stop()

                    if self.online_mode():
                        DisplayMsg.show(Message.SEEKING())
                        self.engine.stop()
                        self.state.seeking_flag = True
                        self.state.stop_fen_timer()
                        ModeInfo.set_online_mode(mode=True)
                    else:
                        ModeInfo.set_online_mode(mode=False)

                    if self.emulation_mode():
                        self.engine.stop()
                    self.engine.newgame(self.state.game.copy())

                    self.state.done_computer_fen = None
                    self.state.done_move = self.state.pb_move = chess.Move.null()
                    self.state.time_control.reset()
                    self.state.best_move_posted = False
                    self.state.searchmoves.reset()
                    self.state.game_declared = False
                    self.update_elo_display()

                    if self.online_mode():
                        await asyncio.sleep(0.5)
                        (
                            self.login,
                            own_color,
                            self.own_user,
                            self.opp_user,
                            self.game_time,
                            self.fischer_inc,
                        ) = await read_online_user_info()
                        if "no_user" in self.own_user and not self.login == "ok":
                            # user login failed check login settings!!!
                            DisplayMsg.show(Message.ONLINE_USER_FAILED())
                            await asyncio.sleep(3)
                        elif "no_player" in self.opp_user:
                            # no opponent found start new game or engine again!!!
                            DisplayMsg.show(Message.ONLINE_NO_OPPONENT())
                            await asyncio.sleep(3)
                        else:
                            DisplayMsg.show(Message.ONLINE_NAMES(own_user=self.own_user, opp_user=self.opp_user))
                            await asyncio.sleep(3)
                        self.state.seeking_flag = False
                        self.state.best_move_displayed = None

                    self.state.legal_fens = await compute_legal_fens(self.state.game.copy())
                    self.state.last_legal_fens = []
                    self.state.legal_fens_after_cmove = []
                    self.is_out_of_time_already = False
                    if self.pgn_mode():
                        if self.state.max_guess > 0:
                            self.state.max_guess_white = self.state.max_guess
                            self.state.max_guess_black = 0
                        pgn_fen = ""
                        (
                            pgn_game_name,
                            pgn_problem,
                            pgn_fen,
                            pgn_result,
                            pgn_white,
                            pgn_black,
                        ) = await read_pgn_info()
                        if "mate in" in pgn_problem or "Mate in" in pgn_problem or pgn_fen != "":
                            await self.set_fen_from_pgn(pgn_fen)
                    await self.set_wait_state(Message.START_NEW_GAME(game=self.state.game.copy(), newgame=newgame))
                    if "no_player" not in self.opp_user and "no_user" not in self.own_user:
                        await self.switch_online()
                    if self.picotutor_mode():
                        self.state.picotutor.reset()
                        if not self.state.flag_startup:
                            if self.state.play_mode == PlayMode.USER_BLACK:
                                await self.state.picotutor.set_user_color(chess.BLACK)
                            else:
                                await self.state.picotutor.set_user_color(chess.WHITE)
                else:
                    if self.online_mode():
                        logger.debug("starting a new game with code: %s", event.pos960)
                        uci960 = event.pos960 != 518
                        self.state.stop_clock()

                        self.state.game.turn = chess.WHITE

                        if uci960:
                            self.state.game.set_chess960_pos(event.pos960)

                        if self.state.play_mode != PlayMode.USER_WHITE:
                            self.state.play_mode = PlayMode.USER_WHITE
                            msg = Message.PLAY_MODE(
                                play_mode=self.state.play_mode,
                                play_mode_text=self.state.dgttranslate.text(str(self.state.play_mode.value)),
                            )
                            DisplayMsg.show(msg)

                        # see setup_position
                        await self.stop_search_and_clock()
                        self.state.stop_fen_timer()

                        if self.engine.has_chess960():
                            self.engine.option("UCI_Chess960", uci960)
                            await self.engine.send()

                        self.state.time_control.reset()
                        self.state.searchmoves.reset()

                        DisplayMsg.show(Message.SEEKING())
                        self.engine.stop()
                        self.state.seeking_flag = True

                        self.engine.newgame(self.state.game.copy())

                        (
                            self.login,
                            own_color,
                            self.own_user,
                            self.opp_user,
                            self.game_time,
                            self.fischer_inc,
                        ) = await read_online_user_info()
                        if "no_user" in self.own_user:
                            # user login failed check login settings!!!
                            DisplayMsg.show(Message.ONLINE_USER_FAILED())
                            await asyncio.sleep(3)
                        elif "no_player" in self.opp_user:
                            # no opponent found start new game & search!!!
                            DisplayMsg.show(Message.ONLINE_NO_OPPONENT())
                            await asyncio.sleep(3)
                        else:
                            DisplayMsg.show(Message.ONLINE_NAMES(own_user=self.own_user, opp_user=self.opp_user))
                            await asyncio.sleep(1)
                        self.state.seeking_flag = False
                        self.state.best_move_displayed = None
                        self.state.takeback_active = False
                        self.state.automatic_takeback = False
                        self.state.done_computer_fen = None
                        self.state.done_move = self.state.pb_move = chess.Move.null()
                        self.state.legal_fens = await compute_legal_fens(self.state.game.copy())
                        self.state.last_legal_fens = []
                        self.state.legal_fens_after_cmove = []
                        self.is_out_of_time_already = False
                        self.state.game_declared = False
                        await self.set_wait_state(
                            Message.START_NEW_GAME(game=self.state.game.copy(), newgame=newgame),
                        )
                        if "no_player" not in self.opp_user and "no_user" not in self.own_user:
                            await self.switch_online()
                    else:
                        logger.debug("no need to start a new game")
                        if self.pgn_mode():
                            pgn_fen = ""
                            self.state.takeback_active = False
                            self.state.automatic_takeback = False
                            (
                                pgn_game_name,
                                pgn_problem,
                                pgn_fen,
                                pgn_result,
                                pgn_white,
                                pgn_black,
                            ) = await read_pgn_info()
                            if "mate in" in pgn_problem or "Mate in" in pgn_problem or pgn_fen != "":
                                await self.set_fen_from_pgn(pgn_fen)
                                await self.set_wait_state(
                                    Message.START_NEW_GAME(game=self.state.game.copy(), newgame=newgame),
                                )
                            else:
                                DisplayMsg.show(Message.START_NEW_GAME(game=self.state.game.copy(), newgame=newgame))
                        else:
                            DisplayMsg.show(Message.START_NEW_GAME(game=self.state.game.copy(), newgame=newgame))

                if self.picotutor_mode():
                    self.state.picotutor.reset()
                    if not self.state.flag_startup:
                        if self.state.play_mode == PlayMode.USER_BLACK:
                            await self.state.picotutor.set_user_color(chess.BLACK)
                        else:
                            await self.state.picotutor.set_user_color(chess.WHITE)

                if self.state.interaction_mode != Mode.REMOTE and not self.online_mode():
                    if self.state.dgtmenu.get_enginename():
                        await asyncio.sleep(0.7)  # give time for ABORT message
                        msg = Message.ENGINE_NAME(engine_name=self.state.engine_text)
                        DisplayMsg.show(msg)
                    if self.pgn_mode():
                        pgn_white = ""
                        pgn_black = ""
                        await asyncio.sleep(1)
                        (
                            pgn_game_name,
                            pgn_problem,
                            pgn_fen,
                            pgn_result,
                            pgn_white,
                            pgn_black,
                        ) = await read_pgn_info()

                        if not pgn_white:
                            pgn_white = "????"
                        DisplayMsg.show(Message.SHOW_TEXT(text_string=pgn_white))

                        DisplayMsg.show(Message.SHOW_TEXT(text_string="versus"))

                        if not pgn_black:
                            pgn_black = "????"
                        DisplayMsg.show(Message.SHOW_TEXT(text_string=pgn_black))

                        if pgn_result:
                            DisplayMsg.show(Message.SHOW_TEXT(text_string=pgn_result))
                        if "mate in" in pgn_problem or "Mate in" in pgn_problem:
                            DisplayMsg.show(Message.SHOW_TEXT(text_string=pgn_problem))
                        else:
                            DisplayMsg.show(Message.SHOW_TEXT(text_string=pgn_game_name))

                        # reset pgn guess counters
                        if last_move_no > 1:
                            self.state.no_guess_black = 1
                            self.state.no_guess_white = 1
                        else:
                            await log_pgn(self.state)
                            if self.state.max_guess_white > 0:
                                if self.state.no_guess_white > self.state.max_guess_white:
                                    self.state.last_legal_fens = []
                                    await self.get_next_pgn_move()

            elif isinstance(event, Event.PAUSE_RESUME):
                if self.pgn_mode():
                    self.engine.pause_pgn_audio()  # @todo this does not do anything
                else:
                    if self.engine.is_thinking():
                        self.state.stop_clock()
                        self.engine.stop()
                    elif not self.state.done_computer_fen:
                        if self.state.time_control.internal_running():
                            self.state.stop_clock()
                        else:
                            self.state.start_clock()
                    else:
                        logger.debug("best move displayed, dont start/stop clock")

            elif isinstance(event, Event.ALTERNATIVE_MOVE):
                if self.state.done_computer_fen and not self.emulation_mode():
                    self.state.done_computer_fen = None
                    self.state.done_move = chess.Move.null()
                    if self.state.interaction_mode in (
                        Mode.NORMAL,
                        Mode.BRAIN,
                        Mode.TRAINING,
                    ):  # @todo handle Mode.REMOTE too
                        if self.state.time_control.mode == TimeMode.FIXED:
                            self.state.time_control.reset()
                        # set computer to move - in case the user just changed the engine
                        self.state.play_mode = (
                            PlayMode.USER_WHITE if self.state.game.turn == chess.BLACK else PlayMode.USER_BLACK
                        )
                        if not self.state.check_game_state():
                            if self.picotutor_mode():
                                await self.state.picotutor.pop_last_move()
                            await self.think(
                                Message.ALTERNATIVE_MOVE(game=self.state.game.copy(), play_mode=self.state.play_mode),
                                searchlist=True,
                            )
                    else:
                        logger.warning("wrong function call [alternative]! mode: %s", self.state.interaction_mode)

            elif isinstance(event, Event.SWITCH_SIDES):
                self.state.flag_startup = False
                DisplayMsg.show(Message.EXIT_MENU())

                if self.state.interaction_mode == Mode.PONDER:
                    # molli: allow switching sides in flexble ponder mode
                    fen = self.state.game.board_fen()

                    if self.state.game.turn == chess.WHITE:
                        fen += " b KQkq - 0 1"
                    else:
                        fen += " w KQkq - 0 1"
                    # ask python-chess to correct the castling string
                    bit_board = chess.Board(fen)
                    bit_board.set_fen(bit_board.fen())
                    if bit_board.is_valid():
                        self.state.game = chess.Board(bit_board.fen())
                        await self.stop_search_and_clock()
                        self.engine.newgame(self.state.game.copy())
                        self.state.done_computer_fen = None
                        self.state.done_move = self.state.pb_move = chess.Move.null()
                        self.state.time_control.reset()
                        self.state.searchmoves.reset()
                        self.state.game_declared = False
                        self.state.legal_fens = await compute_legal_fens(self.state.game.copy())
                        self.state.legal_fens_after_cmove = []
                        self.state.last_legal_fens = []
                        await self.analyse()
                        self.state.play_mode = (
                            PlayMode.USER_WHITE if self.state.game.turn == chess.WHITE else PlayMode.USER_BLACK
                        )
                        msg = Message.PLAY_MODE(
                            play_mode=self.state.play_mode,
                            play_mode_text=self.state.dgttranslate.text(self.state.play_mode.value),
                        )
                        DisplayMsg.show(msg)
                    else:
                        logger.debug("illegal fen %s", fen)
                        DisplayMsg.show(Message.WRONG_FEN())
                        DisplayMsg.show(Message.EXIT_MENU())

                elif self.state.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.TRAINING):
                    if not self.engine.is_waiting():
                        await self.stop_search_and_clock()
                    self.state.automatic_takeback = False
                    self.state.takeback_active = False
                    self.state.reset_auto = False
                    self.state.last_legal_fens = []
                    self.state.legal_fens_after_cmove = []
                    self.state.best_move_displayed = self.state.done_computer_fen
                    if self.state.best_move_displayed:
                        move = self.state.done_move
                        self.state.done_computer_fen = None
                        self.state.done_move = self.state.pb_move = chess.Move.null()
                    else:
                        move = chess.Move.null()  # not really needed

                    self.state.play_mode = (
                        PlayMode.USER_WHITE if self.state.play_mode == PlayMode.USER_BLACK else PlayMode.USER_BLACK
                    )
                    msg = Message.PLAY_MODE(
                        play_mode=self.state.play_mode,
                        play_mode_text=self.state.dgttranslate.text(self.state.play_mode.value),
                    )

                    if self.state.time_control.mode == TimeMode.FIXED:
                        self.state.time_control.reset()

                    if self.picotutor_mode():
                        if self.state.play_mode == PlayMode.USER_BLACK:
                            await self.state.picotutor.set_user_color(chess.BLACK)
                        else:
                            await self.state.picotutor.set_user_color(chess.WHITE)
                        if self.state.best_move_posted:
                            self.state.best_move_posted = False
                            await self.state.picotutor.pop_last_move()

                    self.state.legal_fens = []

                    if self.pgn_mode():  # molli change pgn guessing game sides
                        if self.state.max_guess_black > 0:
                            self.state.max_guess_white = self.state.max_guess_black
                            self.state.max_guess_black = 0
                        elif self.state.max_guess_white > 0:
                            self.state.max_guess_black = self.state.max_guess_white
                            self.state.max_guess_white = 0
                        self.state.no_guess_black = 1
                        self.state.no_guess_white = 1

                    cond1 = self.state.game.turn == chess.WHITE and self.state.play_mode == PlayMode.USER_BLACK
                    cond2 = self.state.game.turn == chess.BLACK and self.state.play_mode == PlayMode.USER_WHITE
                    if cond1 or cond2:
                        self.state.time_control.reset_start_time()
                        await self.think(msg)
                    else:
                        DisplayMsg.show(msg)
                        self.state.start_clock()
                        self.state.legal_fens = await compute_legal_fens(self.state.game.copy())

                    if self.state.best_move_displayed:
                        DisplayMsg.show(Message.SWITCH_SIDES(game=self.state.game.copy(), move=move))

                elif self.state.interaction_mode == Mode.REMOTE:
                    if not self.engine.is_waiting():
                        await self.stop_search_and_clock()

                    self.state.last_legal_fens = []
                    self.state.legal_fens_after_cmove = []
                    self.state.best_move_displayed = self.state.done_computer_fen
                    if self.state.best_move_displayed:
                        move = self.state.done_move
                        self.state.done_computer_fen = None
                        self.state.done_move = self.state.pb_move = chess.Move.null()
                    else:
                        move = chess.Move.null()  # not really needed

                    self.state.play_mode = (
                        PlayMode.USER_WHITE if self.state.play_mode == PlayMode.USER_BLACK else PlayMode.USER_BLACK
                    )
                    msg = Message.PLAY_MODE(
                        play_mode=self.state.play_mode,
                        play_mode_text=self.state.dgttranslate.text(self.state.play_mode.value),
                    )

                    if self.state.time_control.mode == TimeMode.FIXED:
                        self.state.time_control.reset()

                    self.state.legal_fens = []
                    game_end = self.state.check_game_state()
                    if game_end:
                        DisplayMsg.show(msg)
                    else:
                        cond1 = self.state.game.turn == chess.WHITE and self.state.play_mode == PlayMode.USER_BLACK
                        cond2 = self.state.game.turn == chess.BLACK and self.state.play_mode == PlayMode.USER_WHITE
                        if cond1 or cond2:
                            self.state.time_control.reset_start_time()
                            await self.think(msg)
                        else:
                            DisplayMsg.show(msg)
                            self.state.start_clock()
                            self.state.legal_fens = await compute_legal_fens(self.state.game.copy())

                    if self.state.best_move_displayed:
                        DisplayMsg.show(Message.SWITCH_SIDES(game=self.state.game.copy(), move=move))

            elif isinstance(event, Event.DRAWRESIGN):
                if not self.state.game_declared:  # in case user leaves kings in place while moving other pieces
                    await self.stop_search_and_clock()
                    l_result = ""
                    if event.result == GameResult.DRAW:
                        l_result = "1/2-1/2"
                    elif event.result in (GameResult.WIN_WHITE, GameResult.WIN_BLACK):
                        l_result = "1-0" if event.result == GameResult.WIN_WHITE else "0-1"
                    ModeInfo.set_game_ending(result=l_result)
                    DisplayMsg.show(
                        Message.GAME_ENDS(
                            tc_init=self.state.time_control.get_parameters(),
                            result=event.result,
                            play_mode=self.state.play_mode,
                            game=self.state.game.copy(),
                        )
                    )
                    await asyncio.sleep(1.5)
                    self.state.game_declared = True
                    self.state.stop_fen_timer()
                    self.state.legal_fens_after_cmove = []
                    await self.update_elo(event.result)

            elif isinstance(event, Event.REMOTE_MOVE):
                self.state.flag_startup = False
                if self.board_type == dgt.util.EBoard.NOEBOARD:
                    await self.user_move(event.move, sliding=False)
                else:
                    if self.state.interaction_mode == Mode.REMOTE and self.state.is_not_user_turn():
                        await self.stop_search_and_clock()
                        DisplayMsg.show(
                            Message.COMPUTER_MOVE(
                                move=event.move,
                                ponder=chess.Move.null(),
                                game=self.state.game.copy(),
                                wait=False,
                            )
                        )
                        game_copy = self.state.game.copy()
                        game_copy.push(event.move)
                        self.state.done_computer_fen = game_copy.board_fen()
                        self.state.done_move = event.move
                        self.state.pb_move = chess.Move.null()
                        self.state.legal_fens_after_cmove = await compute_legal_fens(game_copy)
                    else:
                        logger.warning(
                            "wrong function call [remote]! mode: %s turn: %s",
                            self.state.interaction_mode,
                            self.state.game.turn,
                        )

            elif isinstance(event, Event.BEST_MOVE):
                self.state.flag_startup = False
                self.state.take_back_locked = False
                self.state.best_move_posted = False
                self.state.takeback_active = False

                if self.state.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.TRAINING):
                    if self.state.is_not_user_turn():
                        # clock must be stopped BEFORE the "book_move" event cause SetNRun resets the clock display
                        self.state.stop_clock()
                        self.state.best_move_posted = True
                        # @todo 8/8/R6P/1R6/7k/2B2K1p/8/8 and sliding Ra6 over a5 to a4 - handle this in correct way!!
                        if self.state.game.is_game_over() and not self.online_mode():
                            logger.warning(
                                "illegal move on game_end - sliding? move: %s fen: %s",
                                event.move,
                                self.state.game.fen(),
                            )
                        elif event.move is None:  # online game aborted or pgn move wrong or end of pgn game
                            self.state.game_declared = True
                            self.state.stop_fen_timer()
                            self.state.legal_fens_after_cmove = []
                            game_msg = self.state.game.copy()

                            if self.online_mode():
                                winner = ""
                                result_str = ""
                                await asyncio.sleep(0.5)
                                result_str, winner = await read_online_result()
                                logger.debug("molli result_str:%s", result_str)
                                logger.debug("molli winner:%s", winner)
                                gameresult_tmp: Optional[GameResult] = None
                                gameresult_tmp2: Optional[GameResult] = None

                                if "Checkmate" in result_str or "checkmate" in result_str or "mate" in result_str:
                                    gameresult_tmp = GameResult.MATE
                                elif "Game abort" in result_str or "timeout" in result_str:
                                    if winner:
                                        if "white" in winner:
                                            gameresult_tmp = GameResult.ABORT
                                            gameresult_tmp2 = GameResult.WIN_WHITE
                                        else:
                                            gameresult_tmp = GameResult.ABORT
                                            gameresult_tmp2 = GameResult.WIN_BLACK
                                    else:
                                        gameresult_tmp = GameResult.ABORT
                                elif result_str == "Draw" or result_str == "draw":
                                    gameresult_tmp = GameResult.DRAW
                                elif "Out of time: White wins" in result_str:
                                    gameresult_tmp = GameResult.OUT_OF_TIME
                                    gameresult_tmp2 = GameResult.WIN_WHITE
                                elif "Out of time: Black wins" in result_str:
                                    gameresult_tmp = GameResult.OUT_OF_TIME
                                    gameresult_tmp2 = GameResult.WIN_BLACK
                                elif "Out of time" in result_str or "outoftime" in result_str:
                                    if winner:
                                        if "white" in winner:
                                            gameresult_tmp = GameResult.OUT_OF_TIME
                                            gameresult_tmp2 = GameResult.WIN_WHITE
                                        else:
                                            gameresult_tmp = GameResult.OUT_OF_TIME
                                            gameresult_tmp2 = GameResult.WIN_BLACK
                                    else:
                                        gameresult_tmp = GameResult.OUT_OF_TIME
                                elif "White wins" in result_str:
                                    gameresult_tmp = GameResult.ABORT
                                    gameresult_tmp2 = GameResult.WIN_WHITE
                                elif "Black wins" in result_str:
                                    gameresult_tmp = GameResult.ABORT
                                    gameresult_tmp2 = GameResult.WIN_BLACK
                                elif "OPP. resigns" in result_str or "resign" in result_str or "abort" in result_str:
                                    gameresult_tmp = GameResult.ABORT
                                    logger.debug("molli resign handling")
                                    if winner == "":
                                        logger.debug("molli winner not set")
                                        if self.state.play_mode == PlayMode.USER_BLACK:
                                            gameresult_tmp2 = GameResult.WIN_BLACK
                                        else:
                                            gameresult_tmp2 = GameResult.WIN_WHITE
                                    else:
                                        logger.debug("molli winner %s", winner)
                                        if "white" in winner:
                                            gameresult_tmp2 = GameResult.WIN_WHITE
                                        else:
                                            gameresult_tmp2 = GameResult.WIN_BLACK

                                else:
                                    logger.debug("molli unknown result")
                                    gameresult_tmp = GameResult.ABORT

                                logger.debug("molli result_tmp:%s", gameresult_tmp)
                                logger.debug("molli result_tmp2:%s", gameresult_tmp2)

                                if gameresult_tmp2 and not (
                                    self.state.game.is_game_over() and gameresult_tmp == GameResult.ABORT
                                ):
                                    if gameresult_tmp == GameResult.OUT_OF_TIME:
                                        DisplayMsg.show(Message.LOST_ON_TIME())
                                        await asyncio.sleep(2)
                                        DisplayMsg.show(
                                            Message.GAME_ENDS(
                                                tc_init=self.state.time_control.get_parameters(),
                                                result=gameresult_tmp2,
                                                play_mode=self.state.play_mode,
                                                game=game_msg,
                                            )
                                        )
                                    else:
                                        DisplayMsg.show(
                                            Message.GAME_ENDS(
                                                tc_init=self.state.time_control.get_parameters(),
                                                result=gameresult_tmp,
                                                play_mode=self.state.play_mode,
                                                game=game_msg,
                                            )
                                        )
                                        await asyncio.sleep(2)
                                        DisplayMsg.show(
                                            Message.GAME_ENDS(
                                                tc_init=self.state.time_control.get_parameters(),
                                                result=gameresult_tmp2,
                                                play_mode=self.state.play_mode,
                                                game=game_msg,
                                            )
                                        )
                                else:
                                    if gameresult_tmp == GameResult.ABORT and gameresult_tmp2:
                                        DisplayMsg.show(
                                            Message.GAME_ENDS(
                                                tc_init=self.state.time_control.get_parameters(),
                                                result=gameresult_tmp2,
                                                play_mode=self.state.play_mode,
                                                game=game_msg,
                                            )
                                        )
                                    else:
                                        DisplayMsg.show(
                                            Message.GAME_ENDS(
                                                tc_init=self.state.time_control.get_parameters(),
                                                result=gameresult_tmp,
                                                play_mode=self.state.play_mode,
                                                game=game_msg,
                                            )
                                        )
                            else:
                                if self.pgn_mode():
                                    # molli: check if last move of pgn game file
                                    await self.stop_search_and_clock()
                                    await log_pgn(self.state)
                                    if self.state.flag_pgn_game_over:
                                        logger.debug("molli pgn: PGN END")
                                        (
                                            pgn_game_name,
                                            pgn_problem,
                                            pgn_fen,
                                            pgn_result,
                                            pgn_white,
                                            pgn_black,
                                        ) = await read_pgn_info()
                                        DisplayMsg.show(Message.PGN_GAME_END(result=pgn_result))
                                    elif self.state.pgn_book_test:
                                        l_game_copy = self.state.game.copy()
                                        l_game_copy.pop()
                                        l_found = self.state.searchmoves.check_book(self.bookreader, l_game_copy)

                                        if not l_found:
                                            DisplayMsg.show(Message.PGN_GAME_END(result="*"))
                                        else:
                                            logger.debug("molli pgn: Wrong Move! Try Again!")
                                            # increase pgn guess counters
                                            if self.state.max_guess_black > 0 and self.state.game.turn == chess.WHITE:
                                                self.state.no_guess_black = self.state.no_guess_black + 1
                                                if self.state.no_guess_black > self.state.max_guess_black:
                                                    DisplayMsg.show(Message.MOVE_WRONG())
                                                else:
                                                    DisplayMsg.show(Message.MOVE_RETRY())
                                            elif self.state.max_guess_white > 0 and self.state.game.turn == chess.BLACK:
                                                self.state.no_guess_white = self.state.no_guess_white + 1
                                                if self.state.no_guess_white > self.state.max_guess_white:
                                                    DisplayMsg.show(Message.MOVE_WRONG())
                                                else:
                                                    DisplayMsg.show(Message.MOVE_RETRY())
                                            else:
                                                # user move wrong in pgn display mode only
                                                DisplayMsg.show(Message.MOVE_RETRY())
                                            if self.board_type == dgt.util.EBoard.NOEBOARD:
                                                await Observable.fire(Event.TAKE_BACK(take_back="PGN_TAKEBACK"))
                                            else:
                                                self.state.takeback_active = True
                                                self.state.automatic_takeback = True
                                                await self.set_wait_state(
                                                    Message.TAKE_BACK(game=self.state.game.copy()),
                                                )  # automatic takeback mode
                                    else:
                                        logger.debug("molli pgn: Wrong Move! Try Again!")

                                        if self.state.max_guess_black > 0 and self.state.game.turn == chess.WHITE:
                                            self.state.no_guess_black = self.state.no_guess_black + 1
                                            if self.state.no_guess_black > self.state.max_guess_black:
                                                DisplayMsg.show(Message.MOVE_WRONG())
                                            else:
                                                DisplayMsg.show(Message.MOVE_RETRY())
                                        elif self.state.max_guess_white > 0 and self.state.game.turn == chess.BLACK:
                                            self.state.no_guess_white = self.state.no_guess_white + 1
                                            if self.state.no_guess_white > self.state.max_guess_white:
                                                DisplayMsg.show(Message.MOVE_WRONG())
                                            else:
                                                DisplayMsg.show(Message.MOVE_RETRY())
                                        else:
                                            # user move wrong in pgn display mode only
                                            DisplayMsg.show(Message.MOVE_RETRY())

                                        if self.board_type == dgt.util.EBoard.NOEBOARD:
                                            await Observable.fire(Event.TAKE_BACK(take_back="PGN_TAKEBACK"))
                                        else:
                                            self.state.takeback_active = True
                                            self.state.automatic_takeback = True
                                            await self.set_wait_state(
                                                Message.TAKE_BACK(game=self.state.game.copy())
                                            )  # automatic takeback mode
                                else:
                                    DisplayMsg.show(
                                        Message.GAME_ENDS(
                                            tc_init=self.state.time_control.get_parameters(),
                                            result=GameResult.ABORT,
                                            play_mode=self.state.play_mode,
                                            game=self.state.game.copy(),
                                        )
                                    )

                            await asyncio.sleep(0.5)
                        else:
                            # normal computer move
                            if event.inbook:
                                DisplayMsg.show(Message.BOOK_MOVE())
                            self.state.searchmoves.exclude(event.move)

                            if self.online_mode() or self.emulation_mode():
                                self.state.start_time_cmove_done = time.time()  # time should alraedy run for the player
                            DisplayMsg.show(Message.EXIT_MENU())
                            DisplayMsg.show(
                                Message.COMPUTER_MOVE(
                                    move=event.move,
                                    ponder=event.ponder,
                                    game=self.state.game.copy(),
                                    wait=event.inbook,
                                )
                            )
                            game_copy = self.state.game.copy()
                            game_copy.push(event.move)

                            if self.picotutor_mode():
                                if self.pgn_mode():
                                    t_color = self.state.picotutor.get_user_color()
                                    if t_color == chess.BLACK:
                                        await self.state.picotutor.set_user_color(chess.WHITE)
                                    else:
                                        await self.state.picotutor.set_user_color(chess.BLACK)

                                valid = await self.state.picotutor.push_move(event.move)

                                if not valid:
                                    await self.state.picotutor.set_position(game_copy.fen(), i_turn=game_copy.turn)

                                    if self.state.play_mode == PlayMode.USER_BLACK:
                                        await self.state.picotutor.set_user_color(chess.BLACK)
                                    else:
                                        await self.state.picotutor.set_user_color(chess.WHITE)

                            self.state.done_computer_fen = game_copy.board_fen()
                            self.state.done_move = event.move

                            self.state.pb_move = (
                                event.ponder if event.ponder and not event.inbook else chess.Move.null()
                            )
                            self.state.legal_fens_after_cmove = await compute_legal_fens(game_copy)

                            if self.pgn_mode():
                                # molli pgn: reset pgn guess counters
                                if self.state.max_guess_black > 0 and not self.state.game.turn == chess.BLACK:
                                    self.state.no_guess_black = 1
                                elif self.state.max_guess_white > 0 and not self.state.game.turn == chess.WHITE:
                                    self.state.no_guess_white = 1

                            # molli: noeboard/WEB-Play
                            if self.board_type == dgt.util.EBoard.NOEBOARD:
                                logger.info("done move detected")
                                assert self.state.interaction_mode in (
                                    Mode.NORMAL,
                                    Mode.BRAIN,
                                    Mode.REMOTE,
                                    Mode.TRAINING,
                                ), (
                                    "wrong mode: %s" % self.state.interaction_mode
                                )

                                await asyncio.sleep(0.5)
                                DisplayMsg.show(Message.COMPUTER_MOVE_DONE())

                                self.state.best_move_posted = False
                                self.state.game.push(self.state.done_move)  # computer move without human assistance
                                self.state.done_computer_fen = None
                                self.state.done_move = chess.Move.null()

                                if self.online_mode() or self.emulation_mode():
                                    # for online or emulation engine the user time alraedy runs with move announcement
                                    # => subtract time between announcement and execution
                                    end_time_cmove_done = time.time()
                                    cmove_time = math.floor(end_time_cmove_done - self.state.start_time_cmove_done)
                                    if cmove_time > 0:
                                        self.state.time_control.sub_online_time(self.state.game.turn, cmove_time)
                                    cmove_time = 0
                                    self.state.start_time_cmove_done = 0

                                game_end = self.state.check_game_state()
                                if game_end:
                                    await self.update_elo(game_end)
                                    self.state.legal_fens = []
                                    self.state.legal_fens_after_cmove = []
                                    if self.online_mode():
                                        await self.stop_search_and_clock()
                                        self.state.stop_fen_timer()
                                    await self.stop_search_and_clock()
                                    if not self.pgn_mode():
                                        DisplayMsg.show(game_end)
                                else:
                                    self.state.searchmoves.reset()

                                    self.state.time_control.add_time(not self.state.game.turn)

                                    # molli new tournament time control
                                    if (
                                        self.state.time_control.moves_to_go_orig > 0
                                        and (self.state.game.fullmove_number - 1)
                                        == self.state.time_control.moves_to_go_orig
                                    ):
                                        self.state.time_control.add_game2(not self.state.game.turn)
                                        t_player = False
                                        msg = Message.TIMECONTROL_CHECK(
                                            player=t_player,
                                            movestogo=self.state.time_control.moves_to_go_orig,
                                            time1=self.state.time_control.game_time,
                                            time2=self.state.time_control.game_time2,
                                        )
                                        DisplayMsg.show(msg)

                                    if not self.online_mode() or self.state.game.fullmove_number > 1:
                                        self.state.start_clock()
                                    else:
                                        DisplayMsg.show(Message.EXIT_MENU())  # show clock
                                        end_time_cmove_done = 0

                                    self.state.legal_fens = await compute_legal_fens(self.state.game.copy())

                                    if self.pgn_mode():
                                        await log_pgn(self.state)
                                        if self.state.game.turn == chess.WHITE:
                                            if self.state.max_guess_white > 0:
                                                if self.state.no_guess_white > self.state.max_guess_white:
                                                    self.state.last_legal_fens = []
                                                    await self.get_next_pgn_move()
                                            else:
                                                self.state.last_legal_fens = []
                                                await self.get_next_pgn_move()
                                        elif self.state.game.turn == chess.BLACK:
                                            if self.state.max_guess_black > 0:
                                                if self.state.no_guess_black > self.state.max_guess_black:
                                                    self.state.last_legal_fens = []
                                                    await self.get_next_pgn_move()
                                            else:
                                                self.state.last_legal_fens = []
                                                await self.get_next_pgn_move()

                                self.state.last_legal_fens = []
                                self.state.newgame_happened = False

                                if self.state.game.fullmove_number < 1:
                                    ModeInfo.reset_opening()
                                if self.picotutor_mode() and self.state.dgtmenu.get_picoexplorer():
                                    (
                                        op_eco,
                                        op_name,
                                        op_moves,
                                        op_in_book,
                                    ) = self.state.picotutor.get_opening()
                                    if op_in_book and op_name:
                                        logger.debug("opening book set to %s", op_name)
                                        ModeInfo.set_opening(self.state.book_in_use, str(op_name), op_eco)
                                        DisplayMsg.show(Message.SHOW_TEXT(text_string=op_name))
                            # molli end noeboard/Web-Play
                    else:
                        logger.warning(
                            "wrong function call [best]! mode: %s turn: %s",
                            self.state.interaction_mode,
                            self.state.game.turn,
                        )
                else:
                    logger.warning(
                        "wrong function call [best]! mode: %s turn: %s",
                        self.state.interaction_mode,
                        self.state.game.turn,
                    )

            elif isinstance(event, Event.NEW_PV):
                if event.pv[0]:
                    # illegal moves can occur if a pv from the engine arrives
                    # at the same time as an user move
                    if self.state.game.is_legal(event.pv[0]):
                        # only pv received from event
                        DisplayMsg.show(
                            Message.NEW_PV(pv=event.pv, mode=self.state.interaction_mode, game=self.state.game.copy())
                        )
                    else:
                        logger.info(
                            "illegal move can not be displayed. move: %s fen: %s",
                            event.pv[0],
                            self.state.game.fen(),
                        )
                        logger.info("engine status: t:%s p:%s", self.engine.is_thinking(), self.engine.is_pondering())

            elif isinstance(event, Event.NEW_SCORE):
                if event.score:
                    if event.score == 999 or event.score == -999:
                        self.state.flag_pgn_game_over = True  # molli pgn mode: signal that pgn is at end
                    else:
                        self.state.flag_pgn_game_over = False

                    # only score and mate received from event
                    DisplayMsg.show(
                        Message.NEW_SCORE(
                            score=event.score,
                            mate=event.mate,
                            mode=self.state.interaction_mode,
                            turn=self.state.game.turn,
                        )
                    )

            elif isinstance(event, Event.NEW_DEPTH):
                if event.depth:
                    if event.depth == 999:
                        self.state.flag_pgn_game_over = True
                    else:
                        self.state.flag_pgn_game_over = False
                    DisplayMsg.show(Message.NEW_DEPTH(depth=event.depth))

            elif isinstance(event, Event.START_SEARCH):
                DisplayMsg.show(Message.SEARCH_STARTED())

            elif isinstance(event, Event.STOP_SEARCH):
                DisplayMsg.show(Message.SEARCH_STOPPED())

            elif isinstance(event, Event.SET_INTERACTION_MODE):
                if (
                    event.mode not in (Mode.NORMAL, Mode.REMOTE, Mode.TRAINING) and self.state.done_computer_fen
                ):  # @todo check why still needed
                    self.state.dgtmenu.set_mode(self.state.interaction_mode)  # undo the button4 stuff
                    logger.warning("mode cant be changed to a pondering mode as long as a move is displayed")
                    mode_text = self.state.dgttranslate.text("Y10_errormode")
                    msg = Message.INTERACTION_MODE(mode=self.state.interaction_mode, mode_text=mode_text, show_ok=False)
                    DisplayMsg.show(msg)
                else:
                    if event.mode == Mode.PONDER:
                        self.state.newgame_happened = False
                    await self.stop_search_and_clock()
                    self.state.interaction_mode = event.mode
                    self.engine_mode()
                    msg = Message.INTERACTION_MODE(mode=event.mode, mode_text=event.mode_text, show_ok=event.show_ok)
                    await self.set_wait_state(msg)  # dont clear searchmoves here

            elif isinstance(event, Event.SET_OPENING_BOOK):
                write_picochess_ini("book", event.book["file"])
                logger.debug("changing opening book [%s]", event.book["file"])
                self.bookreader = chess.polyglot.open_reader(event.book["file"])
                DisplayMsg.show(Message.OPENING_BOOK(book_text=event.book_text, show_ok=event.show_ok))
                self.state.book_in_use = event.book["file"]
                self.state.stop_fen_timer()

            elif isinstance(event, Event.SHOW_ENGINENAME):
                DisplayMsg.show(Message.SHOW_ENGINENAME(show_enginename=event.show_enginename))

            elif isinstance(event, Event.SAVE_GAME):
                if event.pgn_filename:
                    self.state.stop_clock()
                    DisplayMsg.show(
                        Message.SAVE_GAME(
                            tc_init=self.state.time_control.get_parameters(),
                            play_mode=self.state.play_mode,
                            game=self.state.game.copy(),
                            pgn_filename=event.pgn_filename,
                        )
                    )

            elif isinstance(event, Event.READ_GAME):
                if event.pgn_filename:
                    DisplayMsg.show(Message.READ_GAME(pgn_filename=event.pgn_filename))
                    await self.read_pgn_file(event.pgn_filename)

            elif isinstance(event, Event.CONTLAST):
                DisplayMsg.show(Message.CONTLAST(contlast=event.contlast))

            elif isinstance(event, Event.ALTMOVES):
                DisplayMsg.show(Message.ALTMOVES(altmoves=event.altmoves))

            elif isinstance(event, Event.PICOWATCHER):
                self.state.picotutor.set_status(
                    self.state.dgtmenu.get_picowatcher(),
                    self.state.dgtmenu.get_picocoach(),
                    self.state.dgtmenu.get_picoexplorer(),
                    self.state.dgtmenu.get_picocomment(),
                )
                if event.picowatcher:
                    self.state.flag_picotutor = True
                    await self.state.picotutor.set_position(self.state.game.fen(), i_turn=self.state.game.turn)
                    if self.state.play_mode == PlayMode.USER_BLACK:
                        await self.state.picotutor.set_user_color(chess.BLACK)
                    else:
                        await self.state.picotutor.set_user_color(chess.WHITE)
                elif self.state.dgtmenu.get_picocoach() != PicoCoach.COACH_OFF:
                    self.state.flag_picotutor = True
                elif self.state.dgtmenu.get_picoexplorer():
                    self.state.flag_picotutor = True
                else:
                    self.state.flag_picotutor = False

                DisplayMsg.show(Message.PICOWATCHER(picowatcher=event.picowatcher))

            elif isinstance(event, Event.PICOCOACH):
                self.state.picotutor.set_status(
                    self.state.dgtmenu.get_picowatcher(),
                    self.state.dgtmenu.get_picocoach(),
                    self.state.dgtmenu.get_picoexplorer(),
                    self.state.dgtmenu.get_picocomment(),
                )

                if event.picocoach != PicoCoach.COACH_OFF:
                    self.state.flag_picotutor = True
                    await self.state.picotutor.set_position(self.state.game.fen(), i_turn=self.state.game.turn)
                    if self.state.play_mode == PlayMode.USER_BLACK:
                        await self.state.picotutor.set_user_color(chess.BLACK)
                    else:
                        await self.state.picotutor.set_user_color(chess.WHITE)
                elif self.state.dgtmenu.get_picowatcher():
                    self.state.flag_picotutor = True
                elif self.state.dgtmenu.get_picoexplorer():
                    self.state.flag_picotutor = True
                else:
                    self.state.flag_picotutor = False

                if self.state.dgtmenu.get_picocoach() == PicoCoach.COACH_OFF:
                    DisplayMsg.show(Message.PICOCOACH(picocoach=False))
                elif self.state.dgtmenu.get_picocoach() == PicoCoach.COACH_ON and event.picocoach != 2:
                    DisplayMsg.show(Message.PICOCOACH(picocoach=True))
                elif self.state.dgtmenu.get_picocoach() == PicoCoach.COACH_LIFT and event.picocoach != 2:
                    DisplayMsg.show(Message.PICOCOACH(picocoach=True))

                if self.state.dgtmenu.get_picocoach() != PicoCoach.COACH_OFF and event.picocoach == 2:
                    # call pico coach in case it was already set to on
                    self.call_pico_coach()

            elif isinstance(event, Event.PICOEXPLORER):
                self.state.picotutor.set_status(
                    self.state.dgtmenu.get_picowatcher(),
                    self.state.dgtmenu.get_picocoach(),
                    self.state.dgtmenu.get_picoexplorer(),
                    self.state.dgtmenu.get_picocomment(),
                )
                if event.picoexplorer:
                    self.state.flag_picotutor = True
                else:
                    if self.state.dgtmenu.get_picowatcher() or (
                        self.state.dgtmenu.get_picocoach() != PicoCoach.COACH_OFF
                    ):
                        self.state.flag_picotutor = True
                    else:
                        self.state.flag_picotutor = False

                DisplayMsg.show(Message.PICOEXPLORER(picoexplorer=event.picoexplorer))

            elif isinstance(event, Event.RSPEED):
                if self.emulation_mode():
                    # restart engine with new retro speed
                    self.state.artwork_in_use = False
                    engine_file_to_load = self.state.engine_file  # assume not mame
                    if "/mame/" in self.state.engine_file and self.state.dgtmenu.get_engine_rdisplay():
                        engine_file_art = self.state.engine_file + "_art"
                        my_file = Path(engine_file_art)
                        if my_file.is_file():
                            self.state.artwork_in_use = True
                            engine_file_to_load = engine_file_art  # load mame
                    old_options = self.engine.get_pgn_options()
                    DisplayMsg.show(Message.ENGINE_SETUP())
                    await self.engine.quit()
                    self.engine = UciEngine(
                        file=engine_file_to_load,
                        uci_shell=self.uci_local_shell,
                        mame_par=self.calc_engine_mame_par(),
                        loop=self.loop,
                    )
                    await self.engine.open_engine()
                    if engine_file_to_load != self.state.engine_file:
                        await asyncio.sleep(1)  # mame artwork wait
                    await self.engine.startup(old_options, self.state.rating)
                    await self.stop_search_and_clock()

                    if (
                        self.state.dgtmenu.get_engine_rdisplay()
                        and not self.state.dgtmenu.get_engine_rwindow()
                        and self.state.artwork_in_use
                    ):
                        # switch to fullscreen
                        cmd = "xdotool keydown alt key F11; sleep 0.2 xdotool keyup alt"
                        subprocess.run(
                            cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            universal_newlines=True,
                            shell=True,
                        )
                    game_fen = self.state.game.board_fen()
                    self.state.game = chess.Board()
                    self.state.game.turn = chess.WHITE
                    self.state.play_mode = PlayMode.USER_WHITE
                    if game_fen != chess.STARTING_BOARD_FEN:
                        msg = Message.START_NEW_GAME(game=self.state.game.copy(), newgame=True)
                        DisplayMsg.show(msg)
                    self.engine.newgame(self.state.game.copy())
                    self.state.done_computer_fen = None
                    self.state.done_move = self.state.pb_move = chess.Move.null()
                    self.state.searchmoves.reset()
                    self.state.game_declared = False
                    self.state.legal_fens = await compute_legal_fens(self.state.game.copy())
                    self.state.last_legal_fens = []
                    self.state.legal_fens_after_cmove = []
                    self.is_out_of_time_already = False
                    self.engine_mode()
                    DisplayMsg.show(Message.RSPEED(rspeed=event.rspeed))
                    self.update_elo_display()

            elif isinstance(event, Event.TAKE_BACK):
                if self.state.game.move_stack and (
                    event.take_back == "PGN_TAKEBACK"
                    or not (
                        self.state.take_back_locked
                        or self.online_mode()
                        or (self.emulation_mode() and not self.state.automatic_takeback)
                    )
                ):
                    await self.takeback()

            elif isinstance(event, Event.PICOCOMMENT):
                if event.picocomment == "comment-factor":
                    self.pico_talker.set_comment_factor(comment_factor=self.state.dgtmenu.get_comment_factor())
                    DisplayMsg.show(Message.PICOCOMMENT(picocomment="ok"))
                else:
                    DisplayMsg.show(Message.PICOCOMMENT(picocomment=event.picocomment))

            elif isinstance(event, Event.SET_TIME_CONTROL):
                self.state.time_control.stop_internal(log=False)
                tc_init = event.tc_init

                self.state.time_control = TimeControl(**tc_init)

                if not self.pgn_mode() and not self.online_mode():
                    if tc_init["moves_to_go"] > 0:
                        if self.state.time_control.mode == TimeMode.BLITZ:
                            write_picochess_ini(
                                "time",
                                "{:d} {:d} 0 {:d}".format(tc_init["moves_to_go"], tc_init["blitz"], tc_init["blitz2"]),
                            )
                        elif self.state.time_control.mode == TimeMode.FISCHER:
                            write_picochess_ini(
                                "time",
                                "{:d} {:d} {:d} {:d}".format(
                                    tc_init["moves_to_go"],
                                    tc_init["blitz"],
                                    tc_init["fischer"],
                                    tc_init["blitz2"],
                                ),
                            )
                    elif self.state.time_control.mode == TimeMode.BLITZ:
                        write_picochess_ini("time", "{:d} 0".format(tc_init["blitz"]))
                    elif self.state.time_control.mode == TimeMode.FISCHER:
                        write_picochess_ini("time", "{:d} {:d}".format(tc_init["blitz"], tc_init["fischer"]))
                    elif self.state.time_control.mode == TimeMode.FIXED:
                        write_picochess_ini("time", "{:d}".format(tc_init["fixed"]))

                    if self.state.time_control.depth > 0:
                        write_picochess_ini("depth", "{:d}".format(tc_init["depth"]))
                    else:
                        write_picochess_ini("depth", "{:d}".format(0))

                    if self.state.time_control.node > 0:
                        write_picochess_ini("node", "{:d}".format(tc_init["node"]))
                    else:
                        write_picochess_ini("node", "{:d}".format(0))

                text = Message.TIME_CONTROL(time_text=event.time_text, show_ok=event.show_ok, tc_init=tc_init)
                DisplayMsg.show(text)
                self.state.stop_fen_timer()

            elif isinstance(event, Event.CLOCK_TIME):
                if self.dgtdispatcher.is_prio_device(
                    event.dev, event.connect
                ):  # transfer only the most prio clock's time
                    logger.debug(
                        "setting tc clock time - prio: %s w:%s b:%s",
                        event.dev,
                        hms_time(event.time_white),
                        hms_time(event.time_black),
                    )

                    if self.state.time_control.mode != TimeMode.FIXED and (
                        event.time_white == self.state.time_control.game_time
                        and event.time_black == self.state.time_control.game_time
                    ):
                        pass
                    else:
                        moves_to_go = self.state.time_control.moves_to_go_orig - self.state.game.fullmove_number + 1
                        if moves_to_go < 0:
                            moves_to_go = 0
                        logger.debug("setting tc clock times")
                        self.state.time_control.set_clock_times(
                            white_time=event.time_white,
                            black_time=event.time_black,
                            moves_to_go=moves_to_go,
                        )

                    low_time = False  # molli allow the speech output even for less than 60 seconds
                    self.dgtboard.low_time = low_time
                    if self.state.interaction_mode == Mode.TRAINING or self.state.position_mode:
                        pass
                    else:
                        DisplayMsg.show(
                            Message.CLOCK_TIME(
                                time_white=event.time_white,
                                time_black=event.time_black,
                                low_time=low_time,
                            )
                        )
                else:
                    logger.debug("ignore clock time - too low prio: %s", event.dev)
            elif isinstance(event, Event.OUT_OF_TIME):
                # molli: allow further playing even when run out of time
                if (
                    not self.is_out_of_time_already and not self.online_mode()
                ):  # molli in online mode the server decides
                    self.state.stop_clock()
                    result = GameResult.OUT_OF_TIME
                    DisplayMsg.show(
                        Message.GAME_ENDS(
                            tc_init=self.state.time_control.get_parameters(),
                            result=result,
                            play_mode=self.state.play_mode,
                            game=self.state.game.copy(),
                        )
                    )
                    self.is_out_of_time_already = True
                    await self.update_elo(result)

            elif isinstance(event, Event.SHUTDOWN):
                await self.stop_search()
                self.state.stop_clock()
                await self.engine.quit()

                try:
                    if self.uci_remote_shell:
                        if self.uci_remote_shell.get():
                            try:
                                self.uci_remote_shell.get().__exit__(
                                    None, None, None
                                )  # force to call __exit__ (close shell connection)
                            except Exception:
                                pass
                except Exception:
                    pass

                result = GameResult.ABORT
                DisplayMsg.show(
                    Message.GAME_ENDS(
                        tc_init=self.state.time_control.get_parameters(),
                        result=result,
                        play_mode=self.state.play_mode,
                        game=self.state.game.copy(),
                    )
                )
                DisplayMsg.show(Message.SYSTEM_SHUTDOWN())
                await asyncio.sleep(5)  # molli allow more time for commentary chat
                shutdown(self.args.dgtpi, dev=event.dev)  # @todo make independant of remote eng

            elif isinstance(event, Event.REBOOT):
                await self.stop_search()
                self.state.stop_clock()
                await self.engine.quit()
                result = GameResult.ABORT
                DisplayMsg.show(
                    Message.GAME_ENDS(
                        tc_init=self.state.time_control.get_parameters(),
                        result=result,
                        play_mode=self.state.play_mode,
                        game=self.state.game.copy(),
                    )
                )
                DisplayMsg.show(Message.SYSTEM_REBOOT())
                await asyncio.sleep(5)  # molli allow more time for commentary chat
                reboot(
                    self.args.dgtpi and self.uci_local_shell.get() is None, dev=event.dev
                )  # @todo make independant of remote eng

            elif isinstance(event, Event.EXIT):
                await self.stop_search()
                self.state.stop_clock()
                await self.engine.quit()
                result = GameResult.ABORT
                DisplayMsg.show(
                    Message.GAME_ENDS(
                        tc_init=self.state.time_control.get_parameters(),
                        result=result,
                        play_mode=self.state.play_mode,
                        game=self.state.game.copy(),
                    )
                )
                #  DisplayMsg.show(Message.SYSTEM_EXIT())
                await asyncio.sleep(5)  # molli allow more time for commentary chat
                exit(self.args.dgtpi, dev=event.dev)  # @todo make independant of remote eng

            elif isinstance(event, Event.EMAIL_LOG):
                email_logger = Emailer(email=self.args.email, mailgun_key=self.args.mailgun_key)
                email_logger.set_smtp(
                    sserver=self.args.smtp_server,
                    suser=self.args.smtp_user,
                    spass=self.args.smtp_pass,
                    sencryption=self.args.smtp_encryption,
                    sstarttls=args.smtp_starttls,
                    sport=args.smtp_port,
                    sfrom=self.args.smtp_from,
                )
                body = "You probably want to forward this file to a picochess developer ;-)"
                email_logger.send("Picochess LOG", body, "/opt/picochess/logs/{}".format(self.args.log_file))

            elif isinstance(event, Event.SET_VOICE):
                DisplayMsg.show(
                    Message.SET_VOICE(type=event.type, lang=event.lang, speaker=event.speaker, speed=event.speed)
                )

            elif isinstance(event, Event.KEYBOARD_BUTTON):
                DisplayMsg.show(Message.DGT_BUTTON(button=event.button, dev=event.dev))

            elif isinstance(event, Event.KEYBOARD_FEN):
                DisplayMsg.show(Message.DGT_FEN(fen=event.fen, raw=False))

            elif isinstance(event, Event.EXIT_MENU):
                DisplayMsg.show(Message.EXIT_MENU())

            elif isinstance(event, Event.UPDATE_PICO):
                DisplayMsg.show(Message.UPDATE_PICO())
                checkout_tag(event.tag)
                DisplayMsg.show(Message.EXIT_MENU())

            elif isinstance(event, Event.REMOTE_ROOM):
                DisplayMsg.show(Message.REMOTE_ROOM(inside=event.inside))

            elif isinstance(event, Event.PROMOTION):
                DisplayMsg.show(Message.PROMOTION_DONE(move=event.move))

            else:  # Default
                logger.warning("event not handled : [%s]", event)

            # evt_queue.task_done()

    my_main = MainLoop(
        own_user,
        opp_user,
        game_time,
        fischer_inc,
        login,
        state,
        pico_talker,
        dgtdispatcher,
        dgtboard,
        board_type,
        main_loop,
        args,
    )

    await my_main.initialise(time_text)
    main_task = main_loop.create_task(my_main.event_consumer())  # start main message loop
    await asyncio.gather(main_task)
    await asyncio.Event().wait()  # wait forever


if __name__ == "__main__":
    asyncio.run(main())
