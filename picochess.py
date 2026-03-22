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
import signal
import time
import os
import subprocess
import copy
import gc
import logging
from logging.handlers import RotatingFileHandler
import math
import traceback
from typing import Any, List, Optional, Set, Tuple
import asyncio
from pathlib import Path
import platform

import chess.pgn
from chess.pgn import Game
import chess.polyglot
import chess.engine
import chess.variant
from tornado.platform.asyncio import AsyncIOMainLoop
from chess.engine import InfoDict, Limit, BestMove, PlayResult
import dgt.util

from configuration import Configuration
from uci.engine import UciShell, UciEngine
from uci.engine_provider import EngineProvider
from uci.rating import Rating, determine_result

from timecontrol import TimeControl
from theme import calc_theme
from utilities import (
    get_location,
    update_pico_v4,
    update_pico_engines,
    get_opening_books,
    shutdown,
    reboot,
    exit_pico,
    checkout_tag,
    ensure_important_headers,
)
from utilities import (
    Observable,
    DisplayMsg,
    version,
    evt_queue,
    write_picochess_ini,
    get_engine_mame_par,
    get_window_command,
    is_wayland_session,
    set_window_control_backend_preference,
)
from utilities import AsyncRepeatingTimer
from pgn import Emailer, PgnDisplay, ModeInfo
from server import WebDisplay, WebServer, WebVr, EventHandler
from picotalker import PicoTalkerDisplay
from dispatcher import Dispatcher

from dgt.api import Message, Event
from dgt.util import GameResult, TimeMode, Mode, PlayMode, PicoComment, PicoCoach, game_result_from_header
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
from picotutor_constants import DEEP_DEPTH
import pairing_ipc

FLOAT_MIN_BACKGROUND_TIME = 1.0  # how often to send PV,SCORE,DEPTH
# Limit analysis of engine
# ENGINE WATCHING
FLOAT_ENGINE_MAX_ANALYSIS_DEPTH = 50  # max limit for any analysis
# since tutor analyses about 50 lines wide it cannot go so deep
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
        return BestMove(book_move, book_ponder)

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


class BestSeenDepth:
    """a small utility class to help picochess remember last sent depth, bestmove info
    can at the moment only be used when getting analysis from playing engine
    it remembers the _last_seen_depth for _last_half_move_nr"""

    def __init__(self):
        self.last_seen_depth = 0  # last seen depth - info sent
        self.last_half_move_nr = 0  # nr of halfmoves done at depth
        self.ponder_move: chess.Move = chess.Move.null()

    def reset(self):
        """forget seen depth"""
        self.last_seen_depth = 0
        self.last_half_move_nr = 0
        self.ponder_move = chess.Move.null()

    def is_better(self, info: InfoDict | None, analysed_fen: str, game: chess.Board) -> bool:
        """Return True if a deeper depth was found for the analysed FEN (no state updates here).
        info         - InfoDict from engine analysis
        analysed_fen - the fen from which the info comes
        game         - current game board"""
        if not self.ponder_move:
            return True  # special case - without ponder_move we accept any info
        is_better = False
        curr_half_move_nr = len(game.move_stack)  # half_move dont work in library
        if info and analysed_fen == game.fen():
            if "depth" in info:
                # calc how much depth has been lost by comparing half-moves
                depth_diff = curr_half_move_nr - self.last_half_move_nr
                if depth_diff < 0:
                    logger.debug("best depth out of sync - resetting it")
                    self.reset()  # throw away the worthless values
                    is_better = True  # whatever caller sent is better than "future" depth values
                elif info.get("depth") > self.last_seen_depth - depth_diff:
                    is_better = True  # caller has a better depth than our old
        return is_better

    def set_best(self, info: InfoDict | None, analysed_fen: str, game: chess.Board, ponder_move: chess.Move) -> None:
        """Use this when you send the latest info - being sent means it's the latest seen.
        if ponder_move is None or chess.Move.null() it's ok to call, but it will never be is_better"""
        curr_half_move_nr = len(game.move_stack)  # half_move dont work in library
        if info and analysed_fen == game.fen():
            if "depth" in info:
                self.last_seen_depth = info.get("depth")
                self.last_half_move_nr = curr_half_move_nr
                # best sent ponder_move - sama as plus-button
                # if this ponder_move is missing is_better has to return True otherwise we
                # would not get a ponder move until new depth has reached old depth
                self.ponder_move = ponder_move if ponder_move else chess.Move.null()


class PicochessState:
    """Class to keep track of state in Picochess."""

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.automatic_takeback = False
        self.best_move_displayed = None  # temporary copy of done_computer_fen? should be cleaned out
        self.best_move_posted = False  # True when "extra" computer move already posted to Picotutor
        self.book_in_use = ""
        self.comment_file = ""
        self.dgtmenu = None
        self.dgttranslate = None
        self.done_computer_fen = None  # FEN of last done computer move when not yet pushed to game board
        self.done_move = chess.Move.null()  # last done move by computer, not yet pushed to game board
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
        self.engine_move_was_book = False
        self.game_declared = False  # User declared resignation or draw
        self.interaction_mode = Mode.NORMAL
        self.last_legal_fens: List[Any] = []
        self.last_move = None
        self.legal_fens: List[Any] = []
        self.legal_fens_after_cmove: List[Any] = []
        self.max_guess = 0
        self.max_guess_black = 0
        self.max_guess_white = 0
        self.pgn_engine_games: list[dict[str, Any]] = []
        self.pgn_engine_game_index = -1
        self.pgn_engine_total_halfmoves: int | None = None
        self.pgn_engine_result = "*"
        self.no_guess_black = 1
        self.no_guess_white = 1
        self.online_decrement = 0
        self.pb_move = chess.Move.null()  # Best ponder move
        self.pgn_book_test = False
        self.pgn_replay_next_move_fen = ""
        self.pgn_replay_next_move = None
        self.pgn_replay_book_cache = {}
        self.picotutor: PicoTutor | None = None
        self.play_mode = PlayMode.USER_WHITE
        self.position_mode = False
        self.setpieces_switch_anchor_fen = ""
        self.setpieces_switch_armed = False
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
        self.main_loop = loop
        self.ignore_next_engine_move = False  # True only after takeback during think
        self.autoplay_pgn_file = False  # Play/Pause button toggles auto replay of pgn file
        self.autoplay_half_moves = 0  # last seen autoplayed half-move (user can deviate)
        self.best_sent_depth = BestSeenDepth()  # best seen depth for a playing enginge
        self.pending_engine_result: str | None = None
        # Chess variant support (e.g., "3check", "atomic")
        self.variant = "chess"
        self._threecheck_board = None  # chess.variant.ThreeCheckBoard instance when variant == "3check"
        self._atomic_board = None  # chess.variant.AtomicBoard instance when variant == "atomic"
        self._racingkings_board = None  # chess.variant.RacingKingsBoard instance when variant == "racingkings"
        self._antichess_board = None  # chess.variant.AntichessBoard instance when variant == "antichess"

    def push_move(self, move: chess.Move) -> None:
        """Push a move to the game board and sync variant board if active."""
        self.game.push(move)
        if self.variant == "3check" and self._threecheck_board is not None:
            self._threecheck_board.push(move)
        elif self.variant == "atomic" and self._atomic_board is not None:
            self._atomic_board.push(move)
        elif self.variant == "racingkings" and self._racingkings_board is not None:
            self._racingkings_board.push(move)
        elif self.variant == "antichess" and self._antichess_board is not None:
            self._antichess_board.push(move)

    def pop_move(self) -> chess.Move:
        """Pop a move from the game board and sync variant board if active."""
        move = self.game.pop()
        if self.variant == "3check" and self._threecheck_board is not None:
            try:
                self._threecheck_board.pop()
            except IndexError:
                pass  # History already empty
        elif self.variant == "atomic" and self._atomic_board is not None:
            try:
                self._atomic_board.pop()
            except IndexError:
                pass  # History already empty
        elif self.variant == "racingkings" and self._racingkings_board is not None:
            try:
                self._racingkings_board.pop()
            except IndexError:
                pass  # History already empty
        elif self.variant == "antichess" and self._antichess_board is not None:
            try:
                self._antichess_board.pop()
            except IndexError:
                pass  # History already empty
        return move

    def game_copy(self) -> chess.Board:
        """Return a copy of the game board with variant name attached.

        The _variant_name attribute allows the display layer to reconstruct
        the correct variant FEN (e.g. atomic explosions) from the move_stack.
        """
        copy = self.game.copy()
        if self.variant != "chess":
            copy._variant_name = self.variant
        return copy

    def engine_board_copy(self):
        """Return a board copy suitable for engine communication.

        For variants with a dedicated board (racingkings, atomic, 3check) return
        a copy of the variant board so that python-chess sends the correct
        UCI_Variant to the engine.  Falls back to self.game.copy().
        """
        vb = self.get_variant_board()
        if vb is not None:
            return vb.copy()
        return self.game.copy()

    def new_game_msg(self, newgame: bool):
        """Create a START_NEW_GAME message with variant info attached."""
        msg = Message.START_NEW_GAME(game=self.game_copy(), newgame=newgame)
        if self.variant != "chess":
            msg.variant = self.variant
        return msg

    def get_variant_board(self):
        """Return the variant-specific board, or None for standard chess.

        Returns the appropriate variant board object which can be used for:
        - Legal move generation (atomic has different rules)
        - FEN retrieval (atomic shows explosions, 3check has check counts)
        - Variant detection via class name in display layer
        """
        if self.variant == "atomic" and self._atomic_board is not None:
            return self._atomic_board
        elif self.variant == "3check" and self._threecheck_board is not None:
            return self._threecheck_board
        elif self.variant == "racingkings" and self._racingkings_board is not None:
            return self._racingkings_board
        elif self.variant == "antichess" and self._antichess_board is not None:
            return self._antichess_board
        # KOTH uses standard board with special win condition only
        return None

    def get_board_fen(self) -> str:
        """Return board FEN from variant board if active, otherwise from game.

        For atomic variant, this returns the position with explosions applied.
        For 3check, piece positions are identical to standard chess (included for consistency).
        """
        if self.variant == "atomic" and self._atomic_board is not None:
            return self._atomic_board.board_fen()
        elif self.variant == "3check" and self._threecheck_board is not None:
            return self._threecheck_board.board_fen()
        elif self.variant == "racingkings" and self._racingkings_board is not None:
            return self._racingkings_board.board_fen()
        elif self.variant == "antichess" and self._antichess_board is not None:
            return self._antichess_board.board_fen()
        return self.game.board_fen()

    def get_fen(self) -> str:
        """Return full FEN from variant board if active, otherwise from game.

        For atomic variant, this returns the position with explosions applied.
        This is the full FEN string (pieces + turn + castling + en passant + clocks).
        """
        if self.variant == "atomic" and self._atomic_board is not None:
            return self._atomic_board.fen()
        elif self.variant == "3check" and self._threecheck_board is not None:
            return self._threecheck_board.fen()
        elif self.variant == "racingkings" and self._racingkings_board is not None:
            return self._racingkings_board.fen()
        elif self.variant == "antichess" and self._antichess_board is not None:
            return self._antichess_board.fen()
        return self.game.fen()

    def reset_variant_board(self) -> None:
        """Reset the active variant board to starting position."""
        if self.variant == "3check" and self._threecheck_board is not None:
            self._threecheck_board.reset()
        elif self.variant == "atomic" and self._atomic_board is not None:
            self._atomic_board.reset()
        elif self.variant == "racingkings" and self._racingkings_board is not None:
            self._racingkings_board.reset()
        elif self.variant == "antichess" and self._antichess_board is not None:
            self._antichess_board.reset()

    def get_move_check_board(self):
        """Return the board to use for move legality checks.

        Returns the variant board (atomic/3check/racingkings/antichess) when
        active, otherwise the standard game board.  This is the single point
        of truth for 'which board object do I check legal_moves against?'.
        """
        return self.get_variant_board() or self.game

    async def start_clock(self) -> None:
        """Start the clock."""
        if self.interaction_mode in (
            Mode.NORMAL,
            Mode.BRAIN,
            Mode.OBSERVE,
            Mode.REMOTE,
            Mode.TRAINING,
        ):
            self.time_control.start_internal(self.game.turn, self.main_loop)
            tc_init = self.time_control.get_parameters()
            if self.interaction_mode == Mode.TRAINING:
                pass
            else:
                await DisplayMsg.show(
                    Message.CLOCK_START(turn=self.game.turn, tc_init=tc_init, devs={"ser", "i2c", "web"})
                )
                await asyncio.sleep(0.5)
                # @todo give some time to clock to really do it. Check this solution!
        else:
            logger.warning("wrong function call [start]! mode: %s", self.interaction_mode)

    async def stop_clock(self) -> None:
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
                await DisplayMsg.show(Message.CLOCK_STOP(devs={"ser", "i2c", "web"}))
                await asyncio.sleep(0.7)
                # @todo give some time to clock to really do it. Check this solution!
        else:
            # stop_clock is called once by read_pgn_file when going into PGNREPLAY mode
            if self.interaction_mode != Mode.PGNREPLAY:
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

    async def set_online_tctrl(self, game_time, fischer_inc) -> None:
        l_game_time = 0
        l_fischer_inc = 0

        logger.debug("molli online set_online_tctrl input %s %s", game_time, fischer_inc)
        l_game_time = int(game_time)
        l_fischer_inc = int(fischer_inc)
        await self.stop_clock()
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

        lt_white = l_game_time * 60 + l_fischer_inc
        lt_black = l_game_time * 60 + l_fischer_inc
        tc_init["internal_time"] = {chess.WHITE: lt_white, chess.BLACK: lt_black}

        self.time_control = TimeControl(**tc_init)
        text = self.dgttranslate.text("N00_oktime")
        msg = Message.TIME_CONTROL(time_text=text, show_ok=True, tc_init=tc_init)
        await DisplayMsg.show(msg)
        self.stop_fen_timer()

    def check_game_state(self):
        """
        Check if the game has ended or not ; it also sends Message to Displays if the game has ended.

        :param game:
        :param play_mode:
        :return: False is the game continues, Game_Ends() Message if it has ended
        """
        # Check 3check variant win condition first
        if self.variant == "3check" and self._threecheck_board is not None:
            if self._threecheck_board.is_variant_end():
                tc_result = self._threecheck_board.result()
                if tc_result == "1-0":
                    result = GameResult.THREE_CHECK_WHITE
                elif tc_result == "0-1":
                    result = GameResult.THREE_CHECK_BLACK
                else:
                    result = GameResult.DRAW
                return Message.GAME_ENDS(
                    tc_init=self.time_control.get_parameters(),
                    result=result,
                    play_mode=self.play_mode,
                    game=self.game_copy(),
                    mode=self.interaction_mode,
                )

        # Check King of the Hill variant win condition
        if self.variant == "kingofthehill":
            koth_center = {chess.D4, chess.D5, chess.E4, chess.E5}
            # Check if either king is in the center (win for that player)
            white_king = self.game.king(chess.WHITE)
            black_king = self.game.king(chess.BLACK)
            if white_king in koth_center:
                return Message.GAME_ENDS(
                    tc_init=self.time_control.get_parameters(),
                    result=GameResult.KOTH_WHITE,
                    play_mode=self.play_mode,
                    game=self.game_copy(),
                    mode=self.interaction_mode,
                )
            if black_king in koth_center:
                return Message.GAME_ENDS(
                    tc_init=self.time_control.get_parameters(),
                    result=GameResult.KOTH_BLACK,
                    play_mode=self.play_mode,
                    game=self.game_copy(),
                    mode=self.interaction_mode,
                )

        # Check Atomic variant win condition (king exploded)
        if self.variant == "atomic" and self._atomic_board is not None:
            white_king = self._atomic_board.king(chess.WHITE)
            black_king = self._atomic_board.king(chess.BLACK)
            if white_king is None:
                return Message.GAME_ENDS(
                    tc_init=self.time_control.get_parameters(),
                    result=GameResult.ATOMIC_BLACK,
                    play_mode=self.play_mode,
                    game=self.game_copy(),
                    mode=self.interaction_mode,
                )
            if black_king is None:
                return Message.GAME_ENDS(
                    tc_init=self.time_control.get_parameters(),
                    result=GameResult.ATOMIC_WHITE,
                    play_mode=self.play_mode,
                    game=self.game_copy(),
                    mode=self.interaction_mode,
                )

        # Check Racing Kings variant win condition (king reaches 8th rank)
        if self.variant == "racingkings" and self._racingkings_board is not None:
            if self._racingkings_board.is_variant_end():
                rk_result = self._racingkings_board.result()
                if rk_result == "1-0":
                    result = GameResult.RK_WHITE
                elif rk_result == "0-1":
                    result = GameResult.RK_BLACK
                else:
                    result = GameResult.DRAW
                return Message.GAME_ENDS(
                    tc_init=self.time_control.get_parameters(),
                    result=result,
                    play_mode=self.play_mode,
                    game=self.game_copy(),
                    mode=self.interaction_mode,
                )

        # Check Antichess variant win condition (lost all pieces or stalemated)
        if self.variant == "antichess" and self._antichess_board is not None:
            if self._antichess_board.is_variant_end():
                ac_result = self._antichess_board.result()
                if ac_result == "1-0":
                    result = GameResult.ANTICHESS_WHITE
                elif ac_result == "0-1":
                    result = GameResult.ANTICHESS_BLACK
                else:
                    result = GameResult.DRAW
                return Message.GAME_ENDS(
                    tc_init=self.time_control.get_parameters(),
                    result=result,
                    play_mode=self.play_mode,
                    game=self.game_copy(),
                    mode=self.interaction_mode,
                )

        # Standard game end conditions
        # For variant boards with different rules, use variant board for correct state
        if self.variant == "atomic" and self._atomic_board:
            check_board = self._atomic_board
        elif self.variant == "racingkings" and self._racingkings_board:
            check_board = self._racingkings_board
        elif self.variant == "antichess" and self._antichess_board:
            check_board = self._antichess_board
        else:
            check_board = self.game
        if check_board.is_stalemate():
            if self.variant == "antichess":
                # In antichess, the stalemated player wins
                if check_board.turn == chess.BLACK:
                    result = GameResult.ANTICHESS_BLACK
                else:
                    result = GameResult.ANTICHESS_WHITE
            else:
                result = GameResult.STALEMATE
        elif check_board.is_insufficient_material():
            result = GameResult.INSUFFICIENT_MATERIAL
        elif check_board.is_seventyfive_moves():
            result = GameResult.SEVENTYFIVE_MOVES
        elif check_board.is_fivefold_repetition():
            result = GameResult.FIVEFOLD_REPETITION
        elif check_board.is_checkmate():
            result = GameResult.MATE
        else:
            return False

        return Message.GAME_ENDS(
            tc_init=self.time_control.get_parameters(),
            result=result,
            play_mode=self.play_mode,
            game=self.game_copy(),
            mode=self.interaction_mode,
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


def log_pgn(state: PicochessState):
    logger.debug("molli pgn: pgn_book_test: %s", str(state.pgn_book_test))
    logger.debug("molli pgn: game turn: %s", state.game.turn)
    logger.debug("molli pgn: max_guess_white: %s", state.max_guess)
    logger.debug("molli pgn: max_guess_white: %s", state.max_guess_white)
    logger.debug("molli pgn: max_guess_black: %s", state.max_guess_black)
    logger.debug("molli pgn: no_guess_white: %s", state.no_guess_white)
    logger.debug("molli pgn: no_guess_black: %s", state.no_guess_black)




def read_online_result():
    result_line = ""
    winner = ""

    try:
        with open("online_game.txt", "r") as log_u:
            lines = log_u.readlines()
            for i, line in enumerate(lines, start=1):
                if i == 9:
                    result_line = line[12:].strip()
                elif i == 10:
                    winner = line[7:].strip()
    except FileNotFoundError:
        logger.error("Could not read online game file: file not found")
    except OSError as e:
        logger.error("Could not read online game file: %s", e)

    return (str(result_line), str(winner))


def read_online_user_info() -> Tuple[str, str, str, str, int, int]:
    own_user, opp_user = "unknown", "unknown"
    login, own_color = "failed", ""
    game_time, fischer_inc = 0, 0

    try:
        with open("online_game.txt", "r") as log_u:
            for line in log_u:
                if "=" not in line:
                    continue
                key, value = line.strip().split("=", 1)

                if key == "LOGIN":
                    login = value
                elif key == "COLOR":
                    own_color = value
                elif key == "OWN_USER":
                    own_user = value
                elif key == "OPPONENT_USER":
                    opp_user = value
                elif key == "GAME_TIME":
                    try:
                        game_time = int(value)
                    except ValueError:
                        logger.warning("Invalid GAME_TIME value: %s", value)
                elif key == "FISCHER_INC":
                    try:
                        fischer_inc = int(value)
                    except ValueError:
                        logger.warning("Invalid FISCHER_INC value: %s", value)
    except FileNotFoundError:
        logger.warning("Online game file not found")
    except Exception as e:
        logger.error("Error reading online game file: %s", e)

    logger.debug("online game_time %s fischer_inc: %s", game_time, fischer_inc)
    return login, own_color, own_user, opp_user, game_time, fischer_inc


# Racing Kings starting board FEN (piece positions only, no turn/castling/etc.)
RK_STARTING_BOARD_FEN = "8/8/8/8/8/8/krbnNBRK/qrbnNBRQ"


def compare_fen(fen_board_external="", fen_board_internal="", board_type: type = None) -> str:
    # <Piece Placement> ::= <rank8>'/'<rank7>'/'<rank6>'/'<rank5>'/'<rank4>'/'<rank3>'/'<rank2>'/'<rank1>
    # <ranki>       ::= [<digit17>]<piece> {[<digit17>]<piece>} [<digit17>] | '8'
    # <piece>       ::= <white Piece> | <black Piece>
    # <digit17>     ::= '1' | '2' | '3' | '4' | '5' | '6' | '7'
    # <white Piece> ::= 'P' | 'N' | 'B' | 'R' | 'Q' | 'K'
    # <black Piece> ::= 'p' | 'n' | 'b' | 'r' | 'q' | 'k'
    # eg. starting position 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR'
    #                       'a8 b8 c8 d8... / a7 b7... / a1 b1 c1 ... h1'
    #
    # board_type: Optional board class (e.g., chess.Board, chess.variant.AtomicBoard).
    #             If None, defaults to chess.Board.

    if fen_board_external == fen_board_internal or fen_board_external == "" or fen_board_internal == "":
        return ""

    if board_type is None:
        board_type = chess.Board

    internal_board = board_type()
    internal_board.set_board_fen(fen_board_internal)

    external_board = board_type()
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


def compute_legal_fens(game_copy: chess.Board, variant_board=None):
    """
    Compute a list of legal FENs for the given game.

    :param game_copy: The game (standard chess.Board)
    :param variant_board: Optional variant-specific board (e.g., AtomicBoard) for legal move generation
    :return: A list of legal FENs
    """
    # Use variant board for legal moves if provided (e.g., Atomic has different legal moves)
    board = variant_board if variant_board is not None else game_copy
    fens = []
    for move in board.legal_moves:
        board.push(move)
        fens.append(board.board_fen())
        board.pop()
    return fens


async def main() -> None:
    """Main function."""
    # Use asyncio's event loop as the Tornado IOLoop
    AsyncIOMainLoop().install()
    main_loop = asyncio.get_event_loop()

    state = PicochessState(main_loop)
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
        await DisplayMsg.show(Message.IP_INFO(info=info))

    config = Configuration()
    args, unknown = config._args, config.unknown
    set_window_control_backend_preference(args.window_control_backend)

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
        dgtboard: EBoard = ChessLinkBoard(main_loop)
    elif board_type == dgt.util.EBoard.CHESSNUT:
        dgtboard = ChessnutBoard(main_loop)
    elif board_type == dgt.util.EBoard.ICHESSONE:
        dgtboard = IChessOneBoard(main_loop)
    elif board_type == dgt.util.EBoard.CERTABO:
        dgtboard = CertaboBoard(main_loop)
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

    dgtdispatcher = Dispatcher(state.dgtmenu, main_loop)

    logger.debug("node %s", args.node)

    state.time_control, time_text = await state.transfer_time(args.time.split(), depth=args.depth, node=args.node)
    state.tc_init_last = state.time_control.get_parameters()
    time_text.beep = False

    # collect all tasks for later cancellation at exit, shutdown, or reboot
    # except the main_loop task which we terminate by sending a None into the async queue
    non_main_tasks: Set[asyncio.Task] = set()

    # The class dgtDisplay fires Event (Observable) & DispatchDgt (Dispatcher)
    my_dgt_display = DgtDisplay(state.dgttranslate, state.dgtmenu, state.time_control, main_loop)
    non_main_tasks.add(asyncio.create_task(my_dgt_display.message_consumer()))
    my_dgt_display.start_once_per_second_timer()
    # @todo optimise to start this timer only when playmode is needing it?

    async def show_pairing_text(text: str) -> None:
        await DisplayMsg.show(Message.SHOW_TEXT(text_string=text))

    pairing_bridge = pairing_ipc.PairingBridge(main_loop, show_pairing_text)
    try:
        await pairing_bridge.start()
        pairing_ipc.set_bridge(pairing_bridge)
        state.pairing_bridge = pairing_bridge
        if pairing_bridge.server_task is not None:
            non_main_tasks.add(pairing_bridge.server_task)
    except Exception as exc:
        logger.warning("pairing IPC not available: %s", exc)

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

    def _emit_web_audio(audio_data: dict):
        EventHandler.write_to_clients({"event": "WebAudio", "audio": audio_data})

    def _should_emit_web_audio() -> bool:
        return EventHandler.has_remote_clients()

    pico_talker = PicoTalkerDisplay(
        args.user_voice,
        args.computer_voice,
        args.speed_voice,
        args.audio_backend,
        bool(args.web_server_port and args.web_audio_backend_remote),
        _emit_web_audio,
        _should_emit_web_audio,
        args.enable_setpieces_voice,
        args.comment_factor,
        sample_beeper,
        sample_beeper_level,
        board_type,
        main_loop,
    )

    non_main_tasks.add(asyncio.create_task(pico_talker.message_consumer()))

    # Launch web server
    if args.web_server_port:
        my_web_server = WebServer()
        shared: dict = {}
        shared["web_speech_local"] = args.web_speech_local
        shared["web_speech_remote"] = args.web_speech_remote
        shared["web_audio_backend_remote"] = args.web_audio_backend_remote
        shared["tutor_watch_active"] = bool(
            state.dgtmenu.get_picowatcher() or state.dgtmenu.get_picocoach() != PicoCoach.COACH_OFF
        )
        shared["tutor_watch_watcher"] = bool(state.dgtmenu.get_picowatcher())
        shared["tutor_watch_coach"] = bool(state.dgtmenu.get_picocoach() != PicoCoach.COACH_OFF)
        shared["tutor_watch_coach_pref"] = (
            state.dgtmenu.get_picocoach()
            if state.dgtmenu.get_picocoach() != PicoCoach.COACH_OFF
            else PicoCoach.COACH_ON
        )
        # moved starting WebDisplayt and WebVr here so that they are in same main loop
        logger.info("initializing message queues")
        my_web_display = WebDisplay(shared, main_loop)
        non_main_tasks.add(asyncio.create_task(my_web_display.message_consumer()))
        my_web_vr = WebVr(shared, dgtboard, main_loop)
        await my_web_vr.initialize()
        non_main_tasks.add(asyncio.create_task(my_web_vr.dgt_consumer()))
        logger.info("message queues ready - starting web server")
        dgtdispatcher.register("web")
        theme: str = calc_theme(args.theme, state.set_location)
        shared["pieces"] = args.pieces
        shared["web-board-theme"] = args.web_board_theme
        web_app = my_web_server.make_app(theme, args.pieces, args.web_board_theme, shared)
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
            non_main_tasks.add(asyncio.create_task(my_dgtpi.dgt_consumer()))
            non_main_tasks.add(asyncio.create_task(my_dgtpi.process_incoming_clock_forever()))
        else:
            logger.debug("(ser) starting the board connection")
            dgtboard.run()  # a clock can only be online together with the board, so we must start it infront
        my_dgthw = DgtHw(dgtboard, main_loop)
        dgtdispatcher.register("ser")
        non_main_tasks.add(asyncio.create_task(my_dgthw.dgt_consumer()))

    # The class Dispatcher sends DgtApi messages at the correct (delayed) time out
    non_main_tasks.add(asyncio.create_task(dgtdispatcher.dispatch_consumer()))

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

    my_pgn_display = PgnDisplay("games" + os.sep + args.pgn_file, emailer, shared, main_loop)
    non_main_tasks.add(asyncio.create_task(my_pgn_display.message_consumer()))

    # Update
    if args.enable_update:
        # picov3: await update_picochess(args.dgtpi, args.enable_update_reboot, state.dgttranslate)
        update_pico_v4()  # next boot will trigger picochess-update.service

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
            shared: dict,
            non_main_tasks: Set[asyncio.Task],
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
            self.shared = shared
            self.non_main_tasks = non_main_tasks
            self.update_status = None
            self.git_status = None
            ###########################################

            # Keep the normal startup path untouched unless the configured engine has gone missing.
            self.requested_engine_file = self.args.engine
            self.state.engine_file = self.requested_engine_file
            if self.state.engine_file is None:
                resolved_engine = EngineProvider.resolve_engine(None)
                if resolved_engine is None:
                    logger.error("no installed engines available at startup")
                    self.state.engine_file = ""
                else:
                    self.state.engine_file = resolved_engine["file"]
            elif not EngineProvider.has_engine(self.state.engine_file):
                resolved_engine = EngineProvider.resolve_engine(self.state.engine_file)
                if resolved_engine is None:
                    logger.error("no installed engines available at startup")
                    self.state.engine_file = self.requested_engine_file or ""
                else:
                    self.state.engine_file = resolved_engine["file"]
                    logger.warning(
                        "configured engine '%s' not found; starting with '%s'",
                        self.requested_engine_file,
                        self.state.engine_file,
                    )

            self.engine_remote_home = self.args.engine_remote_home

            self.uci_local_shell = UciShell(hostname="", username="", key_file="", password="")
            self.uci_remote_shell = None
            if self.args.engine_remote_server:
                self.uci_remote_shell = UciShell(
                    hostname=self.args.engine_remote_server,
                    username=self.args.engine_remote_user,
                    key_file=self.args.engine_remote_key,
                    password=self.args.engine_remote_pass,
                    remote_home=self.engine_remote_home,
                    windows=self.remote_windows(),
                )
            self.tutor_remote_engine = self.args.tutor_remote_engine

            # ensure dgtmenu knows which engine will actually be loaded so the startup
            # announcement reflects the saved configuration
            if self.state.dgtmenu and self.state.engine_file:
                self.state.dgtmenu.set_state_current_engine(self.state.engine_file)

            self.is_out_of_time_already = False  # molli: out of time message only once
            self.all_books = get_opening_books()
            if not self.all_books:
                logger.error("no opening books available; continuing without book support")
                self.book_index = None
                self.state.book_in_use = ""
                self.bookreader = None
            else:
                try:
                    self.book_index = [book["file"] for book in self.all_books].index(args.book)
                except ValueError:
                    logger.error("selected book not present, defaulting to %s", self.all_books[0]["file"])
                    self.book_index = 0
                self.state.book_in_use = self.all_books[self.book_index]["file"]
                try:
                    self.bookreader = chess.polyglot.open_reader(self.all_books[self.book_index]["file"])
                except OSError as exc:
                    book_file = self.all_books[self.book_index]["file"]
                    logger.warning("failed to open book '%s': %s", book_file, exc)
                    self.bookreader = None
                    self.state.book_in_use = ""
            self.state.searchmoves = AlternativeMover()
            self.state.artwork_in_use = False

            # Register signal handlers for kill signal
            signal.signal(signal.SIGTERM, self.exit_sigterm)
            signal.signal(signal.SIGINT, self.exit_sigterm)

        async def initialise(self, time_text):
            """Due to use of async some initialisation is moved here"""

            # issue 106 - get update and git status information for the user
            self.update_status = self.get_last_update_status()
            logger.info("Update status: %s", self.update_status)
            # This is shown for a very short time - you can also see it in the menu
            if self.update_status:
                self.state.dgttranslate.set_last_updated_info(self.update_status)
                msg = Message.SHOW_TEXT(text_string=self.update_status)
                await DisplayMsg.show(msg)
            self.git_status = self.get_git_status()
            if self.git_status:
                self.state.dgttranslate.set_git_info(self.git_status)

            engine_file_to_load = self.state.engine_file  # assume not mame
            if "/mame/" in self.state.engine_file and self.state.dgtmenu.get_engine_rdisplay():
                engine_file_art = self.state.engine_file + "_art"
                my_file = Path(engine_file_art)
                if my_file.is_file():
                    self.state.artwork_in_use = True
                    engine_file_to_load = engine_file_art  # load mame

            uci_shell = self.uci_remote_shell if self.remote_engine_mode() and self.uci_remote_shell else self.uci_local_shell

            self.engine = UciEngine(
                file=engine_file_to_load,
                uci_shell=uci_shell,
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
                await DisplayMsg.show(Message.ENGINE_FAIL())
                await asyncio.sleep(2)
                sys.exit(-1)

            # Startup - internal
            self.state.game = chess.Board()  # Create the current game
            self.state.legal_fens = compute_legal_fens(self.state.game.copy(), self.state.get_variant_board())  # Compute the legal FENs
            self.state.flag_startup = True

            if self.args.pgn_elo and self.args.pgn_elo.isnumeric() and self.args.rating_deviation:
                self.state.rating = Rating(float(args.pgn_elo), float(args.rating_deviation))
            self.args.engine_level = None if self.args.engine_level == "None" else self.args.engine_level
            if self.args.engine_level == '""':
                self.args.engine_level = None
            engine_opt, level_index = await self.get_engine_level_dict(args.engine_level)
            if self.args.engine_level and level_index is None:
                logger.warning(
                    "configured engine level '%s' not found for engine '%s'; using engine default",
                    self.args.engine_level,
                    self.state.engine_file,
                )
                self.args.engine_level = None
            startup_ok = await self.engine.startup(engine_opt, self.state.rating)

            # Initialize variant support from engine settings
            self._init_variant_from_engine()

            if (
                self.emulation_mode()
                and self.state.dgtmenu.get_engine_rdisplay()
                and self.state.artwork_in_use
                and not self.state.dgtmenu.get_engine_rwindow()
            ):
                # switch to fullscreen
                cmd = get_window_command("toggle_fullscreen")
                if cmd:
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

            await DisplayMsg.show(Message.SYSTEM_INFO(info=sys_info))
            await DisplayMsg.show(
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
            await DisplayMsg.show(
                Message.ENGINE_STARTUP(
                    installed_engines=EngineProvider.installed_engines,
                    file=self.state.engine_file,
                    level_index=level_index,
                    has_960=self.engine.has_chess960(),
                    has_ponder=self.engine.has_ponder(),
                )
            )
            await DisplayMsg.show(Message.ENGINE_SETUP())
            if startup_ok:
                # Confirm startup after startup announcements to keep spoken order:
                # "picochess", "engine setup", "ok".
                await DisplayMsg.show(Message.PICOCOMMENT(picocomment="ok"))
            # update_elo_display sends "rspeed", "user_elo", "engine_elo" in SYSTEM_INFO
            await self.update_elo_display()

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
                await self.set_wait_state(self.state.new_game_msg(newgame=True))
            else:
                ModeInfo.set_online_mode(mode=False)
                await self.engine.newgame(self.state.engine_board_copy())

            self.state.comment_file = self.get_comment_file()
            tutor_engine = self.args.tutor_engine
            remote_tutor_override = self.tutor_remote_engine
            # try remote tutor first if configured and remote shell exists
            self.state.picotutor = None
            if remote_tutor_override and self.uci_remote_shell:
                logger.info("using remote tutor engine via ssh: %s", remote_tutor_override)
                self.state.picotutor = PicoTutor(
                    i_ucishell=self.uci_remote_shell,
                    i_engine_path=tutor_engine,
                    i_comment_file=self.state.comment_file,
                    i_lang=self.args.language,
                    loop=self.loop,
                    remote_binary_override=remote_tutor_override,
                )
                await self.state.picotutor.set_status(
                    self.state.dgtmenu.get_picowatcher(),
                    self.state.dgtmenu.get_picocoach(),
                    self.state.dgtmenu.get_picoexplorer(),
                    self.state.dgtmenu.get_picocomment(),
                )
                await self.state.picotutor.open_engine()
                # fallback if remote tutor failed to load
                if not self.state.picotutor.best_engine or not self.state.picotutor.obvious_engine:
                    logger.warning("remote tutor failed to start - falling back to local tutor")
                    self.state.picotutor = None

            if not self.state.picotutor:
                self.state.picotutor = PicoTutor(
                    i_ucishell=self.uci_local_shell,
                    i_engine_path=tutor_engine,
                    i_comment_file=self.state.comment_file,
                    i_lang=self.args.language,
                    loop=self.loop,
                )
                await self.state.picotutor.set_status(
                    self.state.dgtmenu.get_picowatcher(),
                    self.state.dgtmenu.get_picocoach(),
                    self.state.dgtmenu.get_picoexplorer(),
                    self.state.dgtmenu.get_picocomment(),
                )
                await self.state.picotutor.open_engine()
            if self.shared is not None:
                self.shared["picotutor"] = self.state.picotutor
            my_pgn_display.set_picotutor(self.state.picotutor)  # needed for comments in pgn
            # set_mode in picotutor init set to False

            ModeInfo.set_game_ending(result="*")

            text = self.state.dgtmenu.get_current_engine_name()
            self.state.engine_text = text
            self.state.dgtmenu.enter_top_menu()

            if self.state.dgtmenu.get_enginename():
                msg = Message.ENGINE_NAME(engine_name=self.state.engine_text)
                await DisplayMsg.show(msg)

            # board connection wait moved to wait_for_board_connection to avoid blocking startup

        def get_last_update_status(self) -> str | None:
            """
            Runs the check-update-status.sh script and returns its output as a string.
            Returns None if there was an error running the script.
            """
            script_path = "/opt/picochess/check-update-status.sh"

            try:
                result = subprocess.run(
                    [script_path],
                    cwd="/opt/picochess",
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,  # capture as string
                    check=False,  # don't raise exception on non-zero exit
                )

                # Return stripped output
                return result.stdout.strip()

            except Exception:
                # Optionally log or print error
                logger.info("Error running update status script")
                return None

        def get_git_status(self) -> str | None:
            """
            Runs the check-git-status.sh script and returns the git status string.
            Returns None if there was an error running the script.
            """
            script_path = "/opt/picochess/check-git-status.sh"

            try:
                result = subprocess.run(
                    [script_path],
                    cwd="/opt/picochess",
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,  # capture output as string
                    check=False,  # don't raise exception on non-zero exit
                )

                # Return the full output string from the shell script
                return result.stdout.strip()

            except Exception:
                logger.info("Error running git status script:")
                return None

        async def _cache_engine_abort_result(self):
            """Ensure the fallback result for a missing engine move is cached."""
            if self.pgn_mode() or self.online_mode():
                return
            if self.state.pending_engine_result is None:
                # For any engine that produces bestmove 0000 or an illegal move we always
                # ping it (isready) in handle_bestmove_0000() to decide between resignation and crash.
                vb = self.state.get_variant_board()
                self.state.pending_engine_result = await self.engine.handle_bestmove_0000(
                    self.state.game.copy(), variant_board=vb.copy() if vb else None
                )

        async def think(
            self,
            msg: Message,
            searchlist=False,
        ):
            """
            Start a new search on the current game.

            If a move is found in the opening book, fire an event in a few seconds.
            """
            await DisplayMsg.show(msg)
            if not self.online_mode() or self.state.game.fullmove_number > 1:
                await self.state.start_clock()
            book_res = None
            if self.bookreader and self.state.variant not in ("atomic", "racingkings", "antichess"):
                # Skip opening book for atomic/racingkings/antichess - non-standard rules
                # For 3check variant, use standard FEN for book lookup
                if self.state.variant == "3check" and self.state._threecheck_board is not None:
                    # Strip check-count field (field 5 of 7) from 3check extended FEN
                    parts = self.state._threecheck_board.fen().split()
                    book_lookup_board = chess.Board(f"{parts[0]} {parts[1]} {parts[2]} {parts[3]} {parts[5]} {parts[6]}")
                else:
                    book_lookup_board = self.state.game.copy()
                book_res = self.state.searchmoves.book(self.bookreader, book_lookup_board)
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
                    root_moves = self.state.searchmoves.all(self.state.game)
                else:
                    root_moves = None
                try:
                    # engine moves are received here
                    # webplay: Event.BEST_MOVE pushes the move on display
                    # dgt board: BEST_MOVE 1) informs 2) user moves, 3) dgt event to process_fen() push
                    result_queue = asyncio.Queue()  # engines move result
                    # For variant chess, pass the variant board to engine for correct FEN
                    variant_board = None
                    if self.state.variant == "3check" and self.state._threecheck_board is not None:
                        variant_board = self.state._threecheck_board.copy()
                    elif self.state.variant == "atomic" and self.state._atomic_board is not None:
                        variant_board = self.state._atomic_board.copy()
                    elif self.state.variant == "racingkings" and self.state._racingkings_board is not None:
                        variant_board = self.state._racingkings_board.copy()
                    elif self.state.variant == "antichess" and self.state._antichess_board is not None:
                        variant_board = self.state._antichess_board.copy()
                    await self.engine.go(
                        time_dict=uci_dict,
                        game=self.state.game,
                        result_queue=result_queue,
                        root_moves=root_moves,
                        expected_turn=self.state.game.turn,
                        variant_board=variant_board,
                    )
                    engine_res: PlayResult = await result_queue.get()  # on engine error its None
                    if engine_res:
                        logger.debug("engine moved %s", engine_res.move.uci)
                        if self.state.ignore_next_engine_move:
                            self.state.ignore_next_engine_move = False  # make sure we handle next move
                            logger.debug("ignored engine move - takeback or state change forced move")
                        else:
                            move = engine_res.move if engine_res.move != chess.Move.null() else None
                            ponder_move = engine_res.ponder
                            if not ponder_move:
                                logger.debug("engine sent no ponder move")
                            if move is None:
                                await self._cache_engine_abort_result()
                            info: InfoDict | None = engine_res.info
                            analysed_fen = getattr(engine_res, "analysed_fen", "")
                            if move and not ponder_move and info and "pv" in info:
                                pv_line = info["pv"]
                                if pv_line and pv_line[0] == move and len(pv_line) > 1:
                                    logger.debug("engine sent info - extracting ponder move")
                                    ponder_move = pv_line[1]  # not likely to happen
                            if move and not ponder_move:
                                # no ponder means we should allow the next analysis info to be sent ASAP
                                self.state.best_sent_depth.reset()
                            if info:
                                # send pv, score, not sendpv as it's sent by BEST_MOVE below
                                ponder_cache = ponder_move if ponder_move else chess.Move.null()
                                # Fast clock feedback only; not a full analysis update.
                                await self.send_analyse(
                                    info,
                                    analysed_fen,
                                    send_pv=False,
                                    ponder_move=ponder_cache,
                                )
                            await Observable.fire(Event.BEST_MOVE(move=move, ponder=ponder_move, inbook=False))
                    else:
                        logger.error("Engine returned Exception when asked to make a move")
                        await self._cache_engine_abort_result()
                        await Observable.fire(Event.BEST_MOVE(move=None, ponder=None, inbook=False))
                except Exception as e:
                    # most likely never reached, engine exceptions in UciEngine return None above
                    logger.error("fatal - engine failed to make a move %s", e)
                    await Observable.fire(Event.BEST_MOVE(move=None, ponder=None, inbook=False))
            # set state variables wait for computer move
            # @todo: should we add set self.state.done_computer_fen = None
            self.state.automatic_takeback = False
            self.state.ignore_next_engine_move = False  # dont ignore engine move we now request

        async def stop_search(self):
            """Stop current search."""
            await self.engine.stop()
            if self.engine.consume_forced_analyser_stop():
                logger.debug("forced analyser stop detected - resetting best depth cache")
                self.state.best_sent_depth.reset()
            if not self.emulation_mode():
                while not self.engine.is_waiting():
                    await asyncio.sleep(0.05)
                    logger.debug("engine is still not waiting")

        async def stop_search_and_clock(self, ponder_hit=False):
            """Depending on the interaction mode stop search and clock."""
            logger.debug(
                "stop_search_and_clock called (mode=%s, ponder_hit=%s, thinking=%s, waiting=%s)\n%s",
                self.state.interaction_mode,
                ponder_hit,
                self.engine.is_thinking(),
                self.engine.is_waiting(),
                "".join(traceback.format_stack(limit=6)),
            )
            if self.state.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.TRAINING):
                await self.state.stop_clock()
                if self.engine.is_waiting():
                    logger.debug("engine already waiting")
                else:
                    # @ todo check and simplify this logic
                    if ponder_hit:
                        pass  # we send the self.engine.hit() lateron!
                    else:
                        await self.stop_search()
            elif self.state.interaction_mode in (Mode.REMOTE, Mode.OBSERVE):
                await self.state.stop_clock()
                await self.stop_search()
            elif self.state.interaction_mode in (Mode.ANALYSIS, Mode.KIBITZ, Mode.PONDER, Mode.PGNREPLAY):
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
                await self.state.stop_clock()
                await asyncio.sleep(0.5)
                self.state.stop_fen_timer()
                await asyncio.sleep(0.5)
                eval_str = "ANALYSIS"
                msg = Message.PICOTUTOR_MSG(eval_str=eval_str)
                await DisplayMsg.show(msg)
                await asyncio.sleep(2)

                (
                    t_best_move,
                    t_best_score,
                    t_best_mate,
                    t_alt_best_moves,
                ) = await self.state.picotutor.get_pos_analysis()
                logger.debug(
                    "call_pico_coach analysis result: best_move=%s best_score=%s best_mate=%s alt_moves=%d",
                    t_best_move,
                    t_best_score,
                    t_best_mate,
                    len(t_alt_best_moves),
                )

                tutor_str = "POS" + str(t_best_score)
                msg = Message.PICOTUTOR_MSG(eval_str=tutor_str, score=t_best_score)
                await DisplayMsg.show(msg)
                await asyncio.sleep(5)

                if t_best_mate:
                    l_mate = int(t_best_mate)
                    if t_best_move != chess.Move.null():
                        game_tutor = self.state.game.copy()
                        san_move = game_tutor.san(t_best_move)
                        game_tutor.push(t_best_move)  # for picotalker (last move spoken)
                        tutor_str = "BEST" + san_move
                        msg = Message.PICOTUTOR_MSG(eval_str=tutor_str, game=game_tutor.copy())
                        await DisplayMsg.show(msg)
                        await asyncio.sleep(5)
                else:
                    l_mate = 0
                if l_mate > 0:
                    eval_str = "PICMATE_" + str(abs(l_mate))
                    msg = Message.PICOTUTOR_MSG(eval_str=eval_str)
                    await DisplayMsg.show(msg)
                    await asyncio.sleep(5)
                elif l_mate < 0:
                    eval_str = "USRMATE_" + str(abs(l_mate))
                    msg = Message.PICOTUTOR_MSG(eval_str=eval_str)
                    await DisplayMsg.show(msg)
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
                            await DisplayMsg.show(msg)
                            await asyncio.sleep(5)
                        else:
                            break
                await self.state.start_clock()

        def reset_setpieces_window_switch(self):
            self.state.setpieces_switch_anchor_fen = ""
            self.state.setpieces_switch_armed = False

        def switch_artwork_window(self):
            if self.emulation_mode() and self.state.dgtmenu.get_engine_rdisplay() and self.state.artwork_in_use:
                cmd = get_window_command("switch_window")
                if cmd:
                    subprocess.run(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        universal_newlines=True,
                        shell=True,
                    )

        def calc_engine_mame_par(self):
            engine_rwindow = None
            if is_wayland_session():
                engine_rwindow = self.state.dgtmenu.get_engine_rwindow()
            return get_engine_mame_par(
                self.state.dgtmenu.get_engine_rspeed(),
                self.state.dgtmenu.get_engine_rsound(),
                engine_rwindow=engine_rwindow,
            )

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
                # Sync variant boards with new position
                if self.state.variant == "3check" and self.state._threecheck_board is not None:
                    self.state._threecheck_board.set_fen(bit_board.fen())
                elif self.state.variant == "atomic" and self.state._atomic_board is not None:
                    self.state._atomic_board.set_fen(bit_board.fen())
                elif self.state.variant == "racingkings" and self.state._racingkings_board is not None:
                    self.state._racingkings_board.set_fen(bit_board.fen())
                elif self.state.variant == "antichess" and self.state._antichess_board is not None:
                    self.state._antichess_board.set_fen(bit_board.fen())
                self.state.done_computer_fen = None
                self.state.done_move = self.state.pb_move = chess.Move.null()
                self.state.searchmoves.reset()
                self.state.game_declared = False
                self.state.legal_fens = compute_legal_fens(self.state.game.copy(), self.state.get_variant_board())
                self.state.legal_fens_after_cmove = []
                self.state.last_legal_fens = []
                await self.set_picotutor_position(new_game=True)
            else:
                logger.debug("molli PGN fen is invalid!")

        async def set_picotutor_position(self, new_game=False):
            """tutor is either off sync or we are starting from a new position
            set tutor back to same position as main board game"""
            if self.picotutor_mode():
                # we dont really need to copy the self.state.game but just to be sure...
                await self.state.picotutor.set_position(self.state.game.copy(), new_game=new_game)
                if self.state.play_mode == PlayMode.USER_BLACK:
                    await self.state.picotutor.set_user_color(chess.BLACK, self.pgn_mode() or not self.eng_plays())
                else:
                    await self.state.picotutor.set_user_color(chess.WHITE, self.pgn_mode() or not self.eng_plays())

        def picotutor_mode(self):
            enabled = False

            # Disable PicoTutor for chess variants (3check, etc.)
            if self.state.variant != "chess":
                return False

            # issue #61 - pgn_mode shall not prevent picotutor
            if (
                self.state.flag_picotutor
                and not self.online_mode()
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

        def _init_variant_from_engine(self):
            """Initialize variant state from engine settings."""
            prev_variant = self.state.variant
            if self.engine and hasattr(self.engine, "variant"):
                new_variant = self.engine.variant
                # Variants with non-standard board state should reset when switching away.
                # Racing Kings has a custom start position; Atomic keeps explosions only
                # on its variant board while self.state.game keeps standard captures.
                # Antichess can also diverge from standard-chess legal-state assumptions.
                if (prev_variant == "racingkings" and new_variant != "racingkings") or (
                    prev_variant == "atomic" and new_variant != "atomic"
                ) or (
                    prev_variant == "antichess" and new_variant != "antichess"
                ):
                    self.state.game = chess.Board()
                self.state.variant = new_variant
                if self.state.variant == "3check":
                    self.state._threecheck_board = chess.variant.ThreeCheckBoard()
                    self.state._atomic_board = None
                    self.state._racingkings_board = None
                    self.state._antichess_board = None
                    # Sync with existing move_stack from game (for engine switch mid-game)
                    if self.state.game.move_stack:
                        logger.info("3check: syncing with existing %d moves", len(self.state.game.move_stack))
                        for move in self.state.game.move_stack:
                            self.state._threecheck_board.push(move)
                    logger.info("3check variant initialized")
                elif self.state.variant == "kingofthehill":
                    logger.info("King of the Hill variant initialized")
                    self.state._threecheck_board = None
                    self.state._atomic_board = None
                    self.state._racingkings_board = None
                    self.state._antichess_board = None
                elif self.state.variant == "atomic":
                    self.state._atomic_board = chess.variant.AtomicBoard()
                    self.state._threecheck_board = None
                    self.state._racingkings_board = None
                    self.state._antichess_board = None
                    # Sync with existing move_stack from game (for engine switch mid-game)
                    if self.state.game.move_stack:
                        logger.info("atomic: syncing with existing %d moves", len(self.state.game.move_stack))
                        for move in self.state.game.move_stack:
                            self.state._atomic_board.push(move)
                    logger.info("Atomic variant initialized")
                elif self.state.variant == "racingkings":
                    self.state._racingkings_board = chess.variant.RacingKingsBoard()
                    self.state._threecheck_board = None
                    self.state._atomic_board = None
                    self.state._antichess_board = None
                    # Sync with existing move_stack from game (for engine switch mid-game)
                    if self.state.game.move_stack:
                        logger.info("racingkings: syncing with existing %d moves", len(self.state.game.move_stack))
                        for move in self.state.game.move_stack:
                            self.state._racingkings_board.push(move)
                    else:
                        # Fresh game: set main board to RK starting position
                        # (standard chess.Board defaults to standard chess starting FEN)
                        self.state.game = chess.Board("8/8/8/8/8/8/krbnNBRK/qrbnNBRQ w - - 0 1")
                    logger.info("Racing Kings variant initialized")
                elif self.state.variant == "antichess":
                    self.state._antichess_board = chess.variant.AntichessBoard()
                    self.state._threecheck_board = None
                    self.state._atomic_board = None
                    self.state._racingkings_board = None
                    # Sync with existing move_stack from game (for engine switch mid-game)
                    if self.state.game.move_stack:
                        logger.info("antichess: syncing with existing %d moves", len(self.state.game.move_stack))
                        for move in self.state.game.move_stack:
                            self.state._antichess_board.push(move)
                    logger.info("Antichess variant initialized")
                else:
                    self.state._threecheck_board = None
                    self.state._atomic_board = None
                    self.state._racingkings_board = None
                    self.state._antichess_board = None
            else:
                self.state.variant = "chess"
                self.state._threecheck_board = None
                self.state._atomic_board = None
                self.state._racingkings_board = None
                self.state._antichess_board = None

            # Update shared dict for web interface
            self._update_variant_shared()
            ModeInfo.set_variant(self.state.variant)

        def _update_variant_shared(self):
            """Update shared dict with variant info for web interface."""
            if self.shared is not None:
                self.shared["variant"] = self.state.variant
                if self.state.variant == "3check" and self.state._threecheck_board:
                    self.shared["checks_remaining"] = {
                        "white": self.state._threecheck_board.remaining_checks[chess.WHITE],
                        "black": self.state._threecheck_board.remaining_checks[chess.BLACK],
                    }
                else:
                    self.shared.pop("checks_remaining", None)

        def _prepare_engine_move(self, game_copy: chess.Board, move: chess.Move, pb_move: chess.Move = None) -> None:
            """Record an announced engine move: set done_computer_fen, done_move, pb_move, legal_fens_after_cmove.

            game_copy must already have move pushed onto it.
            For variant boards a copy at N+1 (move applied) is used so that FENs reflect
            the correct post-move position rather than the live board still at N.
            """
            if pb_move is None:
                pb_move = chess.Move.null()
            vb = self.state.get_variant_board()
            vb_after = None
            if vb is not None:
                vb_after = vb.copy()
                vb_after.push(move)
            self.state.done_computer_fen = vb_after.board_fen() if vb_after is not None else game_copy.board_fen()
            self.state.done_move = move
            self.state.pb_move = pb_move
            self.state.legal_fens_after_cmove = compute_legal_fens(game_copy, vb_after)

        async def set_wait_state(self, msg: Message, start_search=True):
            """Enter engine waiting (normal mode) and maybe (by parameter) start pondering."""
            if not self.state.done_computer_fen:
                self.state.legal_fens = compute_legal_fens(self.state.game.copy(), self.state.get_variant_board())
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
                            await self.state.picotutor.set_user_color(
                                self.state.get_user_color(), self.pgn_mode() or not self.eng_plays()
                            )
                        await DisplayMsg.show(
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
                    Mode.PGNREPLAY,
                ):
                    await DisplayMsg.show(msg)
                    await self.analyse()
                    return
            if not self.state.reset_auto:
                if self.state.automatic_takeback:
                    await self.stop_search_and_clock()
                    self.state.reset_auto = True
                await DisplayMsg.show(msg)
            else:
                await DisplayMsg.show(msg)  # molli: fix for web display refresh
                if self.state.automatic_takeback and self.state.takeback_active:
                    if self.state.play_mode == PlayMode.USER_WHITE:
                        text_pl = "K20_playmode_white_user"
                    else:
                        text_pl = "K20_playmode_black_user"
                    await DisplayMsg.show(Message.SHOW_TEXT(text_string=text_pl))
                self.state.automatic_takeback = False
                self.state.takeback_active = False
                self.state.reset_auto = False

            self.state.stop_fen_timer()

        async def takeback(self):
            await self.stop_search_and_clock()
            l_error = False
            try:
                self.state.pop_move()
                l_error = False
            except Exception:
                l_error = True
                logger.debug("takeback not possible!")
            if not l_error:
                self._update_variant_shared()  # Update check counts after takeback
                if self.picotutor_mode():
                    if self.state.best_move_posted:
                        await self.state.picotutor.pop_last_move(self.state.game)
                        self.state.best_move_posted = False
                    await self.state.picotutor.pop_last_move(self.state.game)
                self.state.done_computer_fen = None
                self.state.done_move = self.state.pb_move = chess.Move.null()
                self.state.searchmoves.reset()
                self.state.takeback_active = True
                # it seems call to set_wait_state assumes its always user move
                # so after engine move takeback user needs to press lever
                await self.set_wait_state(Message.TAKE_BACK(game=self.state.game.copy()))

                if self.pgn_mode():  # molli pgn
                    log_pgn(self.state)
                    if self.state.max_guess_white > 0:
                        if self.state.game.turn == chess.WHITE:
                            if self.state.no_guess_white > self.state.max_guess_white:
                                await self.get_next_pgn_move()
                    elif self.state.max_guess_black > 0:
                        if self.state.game.turn == chess.BLACK:
                            if self.state.no_guess_black > self.state.max_guess_black:
                                await self.get_next_pgn_move()

        async def get_next_pgn_move(self):
            log_pgn(self.state)
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

            # issue #61 - in issue #23 - PR #35 these 3 lines were wrongly removed
            # without these lines there is no automatic replay with pgn engine
            # switching sides makes pgn engine make the next move
            # This might confuse the picotutor - Need to debug tutor push move
            self.state.play_mode = (
                PlayMode.USER_WHITE if self.state.play_mode == PlayMode.USER_BLACK else PlayMode.USER_BLACK
            )
            msg = Message.SET_PLAYMODE(play_mode=self.state.play_mode)

            if self.state.time_control.mode == TimeMode.FIXED:
                self.state.time_control.reset()

            self.state.legal_fens = []

            cond1 = self.state.game.turn == chess.WHITE and self.state.play_mode == PlayMode.USER_BLACK
            cond2 = self.state.game.turn == chess.BLACK and self.state.play_mode == PlayMode.USER_WHITE
            if cond1 or cond2:
                self.state.time_control.reset_start_time()
                await self.think(msg)
            else:
                await DisplayMsg.show(msg)
                await self.state.start_clock()
                self.state.legal_fens = compute_legal_fens(self.state.game.copy(), self.state.get_variant_board())

        async def switch_online(self):
            color = ""
            if self.online_mode():
                login, own_color, own_user, opp_user, game_time, fischer_inc = read_online_user_info()
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
                self.state.set_online_tctrl(game_time, fischer_inc)
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
            # Use variant board for legal move enumeration when available (atomic has
            # different legal moves than standard chess).  The same board must be used
            # for both FEN computation AND move-index lookup — mixing them produces
            # wrong moves.
            _move_board = self.state.get_move_check_board()
            legal_fens_pico = compute_legal_fens(self.state.game.copy(), self.state.get_variant_board())

            # Check for same position (use variant board_fen for atomic explosions)
            if fen == self.state.get_board_fen():
                logger.debug("Already in this fen: %s", fen)
                self.state.flag_startup = False
                self.reset_setpieces_window_switch()
                # molli: Chess tutor
                if (
                    self.picotutor_mode()
                    and self.state.dgtmenu.get_picocoach() == PicoCoach.COACH_LIFT
                    and fen != chess.STARTING_BOARD_FEN
                    and not (self.state.variant == "racingkings" and fen == RK_STARTING_BOARD_FEN)
                    and not self.state.take_back_locked
                    and self.state.coach_triggered
                    and not self.state.position_mode
                    and not self.state.automatic_takeback
                ):
                    await self.call_pico_coach()
                    self.state.coach_triggered = False
                elif self.state.position_mode:
                    self.state.position_mode = False
                    if self.state.delay_fen_error == 1:
                        # position finally alright!
                        tutor_str = "POSOK"
                        msg = Message.PICOTUTOR_MSG(eval_str=tutor_str, game=self.state.game.copy())
                        await DisplayMsg.show(msg)
                        self.state.delay_fen_error = 4
                        await asyncio.sleep(1)
                        if not self.state.done_computer_fen:
                            await self.state.start_clock()
                    await DisplayMsg.show(Message.EXIT_MENU())
                elif self.emulation_mode() and self.state.dgtmenu.get_engine_rdisplay() and self.state.artwork_in_use:
                    # switch windows/tasks
                    self.switch_artwork_window()
            # Check if we have to undo a previous move (sliding)
            elif fen in self.state.last_legal_fens:
                logger.info("sliding move detected")
                if self.state.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.TRAINING):
                    if self.state.is_not_user_turn():
                        await self.stop_search()
                        self.state.pop_move()
                        if self.picotutor_mode():
                            if self.state.best_move_posted:
                                await self.state.picotutor.pop_last_move(
                                    self.state.game
                                )  # bestmove already sent to tutor
                                self.state.best_move_posted = False
                            await self.state.picotutor.pop_last_move(self.state.game)  # no switch of sides
                        logger.info("user move in computer turn, reverting to: %s", self.state.game.fen())
                    elif self.state.done_computer_fen:
                        self.state.done_computer_fen = None
                        self.state.done_move = chess.Move.null()
                        self.state.pop_move()
                        if self.picotutor_mode():
                            if self.state.best_move_posted:
                                await self.state.picotutor.pop_last_move(
                                    self.state.game
                                )  # bestmove already sent to tutor
                                self.state.best_move_posted = False
                            await self.state.picotutor.pop_last_move(self.state.game)  # no switch of sides
                        logger.info(
                            "user move while computer move is displayed, reverting to: %s",
                            self.state.game.fen(),
                        )
                    else:
                        handled_fen = False
                        logger.error("last_legal_fens not cleared: %s", self.state.game.fen())
                elif self.state.interaction_mode == Mode.REMOTE:
                    if self.state.is_not_user_turn():
                        self.state.pop_move()
                        if self.picotutor_mode():
                            if self.state.best_move_posted:
                                await self.state.picotutor.pop_last_move(
                                    self.state.game
                                )  # bestmove already sent to tutor
                                self.state.best_move_posted = False
                            await self.state.picotutor.pop_last_move(self.state.game)
                        logger.info("user move in remote turn, reverting to: %s", self.state.game.fen())
                    elif self.state.done_computer_fen:
                        self.state.done_computer_fen = None
                        self.state.done_move = chess.Move.null()
                        self.state.pop_move()
                        if self.picotutor_mode():
                            if self.state.best_move_posted:
                                await self.state.picotutor.pop_last_move(
                                    self.state.game
                                )  # bestmove already sent to tutor
                                self.state.best_move_posted = False
                            await self.state.picotutor.pop_last_move(self.state.game)
                        logger.info(
                            "user move while remote move is displayed, reverting to: %s",
                            self.state.game.fen(),
                        )
                    else:
                        handled_fen = False
                        logger.error("last_legal_fens not cleared: %s", self.state.game.fen())
                else:
                    self.state.pop_move()
                    if self.picotutor_mode():
                        if self.state.best_move_posted:
                            await self.state.picotutor.pop_last_move(self.state.game)  # bestmove already sent to tutor
                            self.state.best_move_posted = False
                        await self.state.picotutor.pop_last_move(self.state.game)
                        # just to be sure set fen pos.
                        # @todo - check valid here - dont reset position if valid
                        await self.set_picotutor_position()
                    logger.info("wrong color move -> sliding, reverting to: %s", self.state.game.fen())
                legal_moves = list(_move_board.legal_moves)
                move = legal_moves[state.last_legal_fens.index(fen)]
                ok = await self.user_move(move, sliding=True)
                if ok:
                    if self.state.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.REMOTE, Mode.TRAINING):
                        self.state.legal_fens = []
                    else:
                        self.state.legal_fens = compute_legal_fens(self.state.game.copy(), self.state.get_variant_board())
                else:
                    handled_fen = False

            # allow playing/correcting moves for pico's side in TRAINING mode:
            elif fen in legal_fens_pico and self.state.interaction_mode in (Mode.TRAINING, Mode.PGNREPLAY):
                legal_moves = list(_move_board.legal_moves)
                move = legal_moves[legal_fens_pico.index(fen)]

                if self.state.done_computer_fen:
                    if fen == self.state.done_computer_fen:
                        pass
                    else:
                        if self.state.interaction_mode == Mode.PGNREPLAY:
                            # its a legal move, so let the user deviate from PGN replay but stop autoplay
                            self.state.autoplay_pgn_file = False
                        else:  # TRAINING mode as before, user did an alternativ move for Pico engine
                            await DisplayMsg.show(Message.WRONG_FEN())  # display set pieces/pico's move
                            await asyncio.sleep(3)
                            # display set pieces again and accept new players move as pico's move
                            await DisplayMsg.show(
                                Message.ALTERNATIVE_MOVE(game=self.state.game.copy(), play_mode=self.state.play_mode)
                            )
                            await asyncio.sleep(2)
                            await DisplayMsg.show(
                                Message.COMPUTER_MOVE(
                                    move=move,
                                    ponder=False,
                                    game=self.state.game_copy(),
                                    wait=False,
                                    is_user_move=False,
                                )
                            )
                            await asyncio.sleep(2)
                logger.debug("user move did a move for pico")

                ok = await self.user_move(move, sliding=False)
                if ok:
                    self.state.last_legal_fens = self.state.legal_fens
                    if self.state.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.REMOTE, Mode.TRAINING):
                        self.state.legal_fens = []
                    else:
                        self.state.legal_fens = compute_legal_fens(self.state.game.copy(), self.state.get_variant_board())
                else:
                    handled_fen = False

            # standard legal move
            elif fen in self.state.legal_fens:
                logger.debug("standard move detected")
                self.state.newgame_happened = False
                legal_moves = list(_move_board.legal_moves)
                move = legal_moves[state.legal_fens.index(fen)]
                ok = await self.user_move(move, sliding=False)
                if ok:
                    self.state.last_legal_fens = self.state.legal_fens
                    if self.state.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.REMOTE):
                        self.state.legal_fens = []
                    else:
                        self.state.legal_fens = compute_legal_fens(self.state.game.copy(), self.state.get_variant_board())
                else:
                    handled_fen = False

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
                legal_moves = list(_move_board.legal_moves)
                self.state.done_move = legal_moves[legal_fens_pico.index(fen)]
                await DisplayMsg.show(
                    Message.ALTERNATIVE_MOVE(game=self.state.game.copy(), play_mode=self.state.play_mode)
                )
                await asyncio.sleep(1.5)
                if self.state.done_move:
                    await DisplayMsg.show(
                        Message.COMPUTER_MOVE(
                            move=self.state.done_move,
                            ponder=False,
                            game=self.state.game_copy(),
                            wait=False,
                            is_user_move=False,
                        )
                    )
                    await asyncio.sleep(1.5)
                await DisplayMsg.show(Message.COMPUTER_MOVE_DONE())
                logger.info("user did a move for pico")
                if self.state.best_move_posted and self.picotutor_mode():
                    # issue 86 - user force alt direct move for pico - pop comp move
                    valid = await self.state.picotutor.pop_last_move(self.state.game)
                else:
                    valid = True
                # if valid is True tutor board and game are in sync (no comp move)
                # now proceed and push the forced direct alt move to both
                self.state.best_move_posted = False
                self.state.best_move_displayed = None
                self.state.push_move(self.state.done_move)
                self._update_variant_shared()
                if self.picotutor_mode():
                    if valid:
                        valid = await self.state.picotutor.push_move(self.state.done_move, self.state.game)
                    if not valid:
                        await self.set_picotutor_position()
                self.state.done_computer_fen = None
                self.state.done_move = chess.Move.null()
                game_end = self.state.check_game_state()
                if game_end:
                    self.state.legal_fens = []
                    self.state.legal_fens_after_cmove = []
                    if self.online_mode():
                        await self.stop_search_and_clock()
                        self.state.stop_fen_timer()
                    await self.stop_search_and_clock()
                    self.game_end_event()
                    await DisplayMsg.show(game_end)
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
                        await DisplayMsg.show(msg)

                    await self.state.start_clock()

                self.state.legal_fens = compute_legal_fens(
                    self.state.game.copy(), self.state.get_variant_board()
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
                    Mode.PGNREPLAY,
                ), (
                    "wrong mode: %s" % self.state.interaction_mode
                )
                await DisplayMsg.show(Message.COMPUTER_MOVE_DONE())

                self.state.best_move_posted = False
                self.state.push_move(self.state.done_move)
                self._update_variant_shared()
                # Keep this clear after push_move(): analysis gating uses done_computer_fen
                # to block stale analysis while waiting for the engine move to be executed.
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
                        self.game_end_event()
                        await DisplayMsg.show(game_end)
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
                        await DisplayMsg.show(msg)

                    if self.state.game.fullmove_number < 1:
                        ModeInfo.reset_opening()
                    if self.picotutor_mode() and self.state.dgtmenu.get_picoexplorer():
                        op_eco, op_name, op_moves, op_in_book = self.state.picotutor.get_opening()
                        if op_in_book and op_name:
                            ModeInfo.set_opening(self.state.book_in_use, str(op_name), op_eco)
                            await DisplayMsg.show(Message.SHOW_TEXT(text_string=op_name))
                            await asyncio.sleep(0.7)

                    if not self.online_mode() or self.state.game.fullmove_number > 1:
                        await self.state.start_clock()
                    else:
                        await DisplayMsg.show(Message.EXIT_MENU())  # show clock
                        end_time_cmove_done = 0

                    self.state.legal_fens = compute_legal_fens(self.state.game.copy(), self.state.get_variant_board())

                    if self.pgn_mode():
                        log_pgn(self.state)
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

            # molli: Premove/fast move: Player has done the computer move and his own move in rapid sequence
            elif (
                fen in self.state.legal_fens_after_cmove
                and self.state.flag_premove
                and self.state.done_move != chess.Move.null()
            ):  # and self.state.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.TRAINING):
                logger.info("standard move after computer move detected")
                # molli: execute computer move first
                self.state.push_move(self.state.done_move)
                self._update_variant_shared()
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
                    await DisplayMsg.show(msg)

                self.state.last_legal_fens = []
                self.state.legal_fens_after_cmove = []
                self.state.legal_fens = compute_legal_fens(
                    self.state.game.copy(), self.state.get_variant_board()
                )  # molli new legal fance based on cmove

                # standard user move handling
                legal_moves = list(_move_board.legal_moves)
                move = legal_moves[state.legal_fens.index(fen)]
                ok = await self.user_move(move, sliding=False)
                if ok:
                    self.state.last_legal_fens = self.state.legal_fens
                    self.state.newgame_happened = False
                    if self.state.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.REMOTE, Mode.TRAINING):
                        self.state.legal_fens = []
                    else:
                        self.state.legal_fens = compute_legal_fens(self.state.game.copy(), self.state.get_variant_board())
                else:
                    handled_fen = False

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
                            # Racing Kings: if all moves have been popped we are back
                            # at the RK starting position.  Treat this as a NEW GAME,
                            # not a takeback, so that Event.NEW_GAME fires below.
                            if (
                                not game_copy.move_stack
                                and self.state.variant == "racingkings"
                                and fen == RK_STARTING_BOARD_FEN
                            ):
                                logger.info("racingkings: takeback reached starting position – treating as new game")
                                break  # handled_fen stays False → falls through to NEW_GAME
                            handled_fen = True
                            logger.info("current game fen      : %s", self.state.game.fen())
                            logger.info("undoing game until fen: %s", fen)
                            await self.stop_search_and_clock()
                            while len(game_copy.move_stack) < len(self.state.game.move_stack):
                                self.state.pop_move()

                                if self.picotutor_mode():
                                    if self.state.best_move_posted:  # molli computer move already sent to tutor!
                                        await self.state.picotutor.pop_last_move(self.state.game)
                                        self.state.best_move_posted = False
                                    await self.state.picotutor.pop_last_move(self.state.game)

                            # its a complete new pos, delete saved values
                            self.state.done_computer_fen = None
                            self.state.done_move = self.state.pb_move = chess.Move.null()
                            self.state.searchmoves.reset()
                            self.state.takeback_active = True
                            self._update_variant_shared()  # sync check counts etc. after multi-pop
                            await self.set_wait_state(
                                Message.TAKE_BACK(game=self.state.game.copy())
                            )  # new: force stop no matter if picochess turn

                            break

                    if self.pgn_mode():  # molli pgn
                        log_pgn(self.state)
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
                self.reset_setpieces_window_switch()
                if self.state.position_mode and self.state.delay_fen_error == 1:
                    tutor_str = "POSOK"
                    msg = Message.PICOTUTOR_MSG(eval_str=tutor_str, game=self.state.game.copy())
                    await DisplayMsg.show(msg)
                    await asyncio.sleep(1)
                    if not self.state.done_computer_fen:
                        await self.state.start_clock()
                    await DisplayMsg.show(Message.EXIT_MENU())
                self.state.position_mode = False
            else:
                if fen == chess.STARTING_BOARD_FEN or (
                    self.state.variant == "racingkings" and fen == RK_STARTING_BOARD_FEN
                ):
                    pos960 = 518
                    self.state.error_fen = None
                    self.reset_setpieces_window_switch()
                    if self.state.position_mode and self.state.delay_fen_error == 1:
                        tutor_str = "POSOK"
                        msg = Message.PICOTUTOR_MSG(eval_str=tutor_str, game=self.state.game.copy())
                        await DisplayMsg.show(msg)
                        if not self.state.done_computer_fen:
                            await self.state.start_clock()
                    self.state.position_mode = False
                    await Observable.fire(Event.NEW_GAME(pos960=pos960))
                else:
                    if self.state.setpieces_switch_anchor_fen and fen != self.state.setpieces_switch_anchor_fen:
                        self.state.setpieces_switch_armed = True
                    self.state.error_fen = fen
                    self.start_fen_timer()

        async def user_move(self, move: chess.Move, sliding: bool) -> bool:
            """Handle an user move."""

            eval_str = ""
            pending_picotutor_msgs: list[tuple[Message, float | None]] = []

            self.state.take_back_locked = False

            logger.info("user move [%s] sliding: %s", move, sliding)
            # Use variant board for legality check (atomic has different legal moves after explosions)
            move_check_board = self.state.get_move_check_board()
            if move not in move_check_board.legal_moves:
                logger.warning("illegal move [%s]", move)
                return False
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

                # before pushing a user move check if we got a ponder hit - for analysis modes
                if not self.eng_plays():
                    ponder_hit = False
                    # which analyser to use? same logic as in analyse() - try tutor first
                    if self.is_coach_analyser() and self.state.picotutor.can_use_coach_analyser():
                        play_result = await self.state.picotutor.get_analysis_chosen_move(move)
                        if play_result.info:
                            # ponder hit from tutor list - make an info_list to trigger ponder hit below
                            info_list = [play_result.info]  # construct a list for "pv first" below
                        else:
                            info_list = None  # no ponder hit in tutor
                        analysed_fen = getattr(play_result, "analysed_fen", "")
                    else:
                        # tutor not replacing engine analysis, so try normal engine analysis
                        info_result = await self.engine.get_analysis(self.state.game)
                        info_list: list[InfoDict] = info_result.get("info")
                        analysed_fen = info_result.get("fen")
                    if info_list:
                        info = info_list[0]  # pv first
                        if info and "pv" in info:
                            pv_moves = info["pv"]
                            expected_ponder_move = pv_moves[0] if pv_moves else chess.Move.null()
                            if move == expected_ponder_move:
                                # ponder hit! user chose the best ponder move
                                ponder_reply = pv_moves[1] if pv_moves and len(pv_moves) > 1 else chess.Move.null()
                                send_pv = pv_moves and len(pv_moves) > 1
                                # Fast clock feedback only; not a full analysis update.
                                await self.send_analyse(
                                    info, analysed_fen, send_pv=bool(send_pv), ponder_move=ponder_reply
                                )
                                if not send_pv:
                                    self.state.pb_move = chess.Move.null()
                                    self.state.best_sent_depth.reset()
                                ponder_hit = True
                    if not ponder_hit:
                        # user deviated from analysed line (or no info available) - reset cache
                        self.state.best_sent_depth.reset()

                # Clock logic after user move
                #
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
                        await DisplayMsg.show(msg)
                    if self.online_mode():
                        # molli for online pseudo time sync
                        if self.state.online_decrement > 0:
                            self.state.time_control.sub_online_time(self.state.game.turn, self.state.online_decrement)

                #
                # Remember game_before user move for picotutor thread
                # And for sending USER_MOVE_DONE below
                #
                game_before = self.state.game.copy()
                self.state.push_move(move)  # this is where user move is made
                self._update_variant_shared()
                logger.debug("user did a move for user")
                #
                # Set and reset information after user move
                #
                self.state.done_computer_fen = None
                self.state.done_move = chess.Move.null()
                self.state.searchmoves.reset()  # empty list of excluded engine rootmoves
                self.state.ignore_next_engine_move = False  # real user move has been made

                #
                # Picotutor check
                #
                eval_str = ""
                if self.picotutor_mode() and not self.state.position_mode:
                    l_mate = ""
                    t_hint_move = chess.Move.null()
                    valid = await self.state.picotutor.push_move(move, self.state.game)
                    # get evalutaion result and give user feedback
                    if self.state.dgtmenu.get_picowatcher():
                        if valid:
                            eval_str, l_mate = self.state.picotutor.get_user_move_eval()
                        else:
                            # invalid move from tutor side!? Something went wrong
                            eval_str = "ER"
                            await self.set_picotutor_position()
                            l_mate = ""
                            eval_str = ""  # no error message
                        if eval_str != "" and self.state.last_move != move:  # molli takeback_mame
                            msg = Message.PICOTUTOR_MSG(eval_str=eval_str)
                            delay = 3.0 if "??" in eval_str else 1.0
                            pending_picotutor_msgs.append((msg, delay))
                        if l_mate:
                            n_mate = int(l_mate)
                        else:
                            n_mate = 0
                        if n_mate < 0:
                            msg_str = "USRMATE_" + str(abs(n_mate))
                            msg = Message.PICOTUTOR_MSG(eval_str=msg_str)
                            pending_picotutor_msgs.append((msg, 1.5))
                        elif n_mate > 1:
                            n_mate = n_mate - 1
                            msg_str = "PICMATE_" + str(abs(n_mate))
                            msg = Message.PICOTUTOR_MSG(eval_str=msg_str)
                            pending_picotutor_msgs.append((msg, 1.5))
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
                                pending_picotutor_msgs.append((msg, 5.0))

                            if t_hint_move != chess.Move.null():
                                game_tutor = game_before.copy()
                                san_move = game_tutor.san(t_hint_move)
                                game_tutor.push(t_hint_move)
                                tutor_str = "HINT" + san_move
                                msg = Message.PICOTUTOR_MSG(eval_str=tutor_str, game=game_tutor.copy())
                                pending_picotutor_msgs.append((msg, 5.0))

                    if self.state.game.fullmove_number < 1:
                        ModeInfo.reset_opening()

                #
                # Start engine think
                #
                if self.state.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.TRAINING):
                    msg = Message.USER_MOVE_DONE(
                        move=move, fen=game_before.fen(), turn=game_before.turn, game=self.state.game.copy()
                    )
                    game_end = self.state.check_game_state()
                    if game_end:
                        await self.update_elo(game_end.result)
                        # molli: for online/emulation mode we have to publish this move as well to the engine
                        if self.online_mode():
                            logger.info("starting think()")
                            await self._deliver_picotutor_messages(pending_picotutor_msgs)
                            await self.think(msg)
                        elif self.emulation_mode():
                            logger.info("molli: starting mame_endgame()")
                            self.mame_endgame()
                            await DisplayMsg.show(msg)
                            await self._deliver_picotutor_messages(pending_picotutor_msgs)
                            self.game_end_event()
                            await DisplayMsg.show(game_end)
                            self.state.legal_fens_after_cmove = []  # molli
                        else:
                            await DisplayMsg.show(msg)
                            await self._deliver_picotutor_messages(pending_picotutor_msgs)
                            self.game_end_event()
                            await DisplayMsg.show(game_end)
                            self.state.legal_fens_after_cmove = []  # molli
                    else:
                        if self.state.interaction_mode in (Mode.NORMAL, Mode.TRAINING):
                            if not self.state.check_game_state():
                                # molli: automatic takeback of blunder moves for mame engines
                                if self.emulation_mode() and eval_str == "??" and self.state.last_move != move:
                                    # Ensure tutor feedback is shown before takeback prompt/move display.
                                    await self._deliver_picotutor_messages(pending_picotutor_msgs)
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
                                    await self._deliver_picotutor_messages(pending_picotutor_msgs)
                                    if self.state.takeback_active and self.state.is_not_user_turn():
                                        # Allow additional takebacks to settle before starting engine search.
                                        await asyncio.sleep(0.6)
                                    if self.state.is_not_user_turn():
                                        await self.think(msg)
                                    else:
                                        logger.debug("skipping think() after takeback debounce: user turn")
                        else:
                            assert self.state.interaction_mode == Mode.BRAIN
                            logger.debug("new implementation of ponderhit - starting think")
                            await self._deliver_picotutor_messages(pending_picotutor_msgs)
                            if self.state.takeback_active and self.state.is_not_user_turn():
                                # Allow additional takebacks to settle before starting engine search.
                                await asyncio.sleep(0.6)
                            if self.state.is_not_user_turn():
                                await self.think(msg)
                            else:
                                logger.debug("skipping think() after takeback debounce: user turn")

                    self.state.last_move = move
                elif self.state.interaction_mode == Mode.REMOTE:
                    msg = Message.USER_MOVE_DONE(
                        move=move, fen=game_before.fen(), turn=game_before.turn, game=self.state.game.copy()
                    )
                    game_end = self.state.check_game_state()
                    await DisplayMsg.show(msg)
                    await self._deliver_picotutor_messages(pending_picotutor_msgs)
                    if game_end:
                        self.game_end_event()
                        await DisplayMsg.show(game_end)
                    else:
                        await self.observe()
                elif self.state.interaction_mode == Mode.OBSERVE:
                    msg = Message.REVIEW_MOVE_DONE(
                        move=move, fen=game_before.fen(), turn=game_before.turn, game=self.state.game.copy()
                    )
                    game_end = self.state.check_game_state()
                    if game_end:
                        await DisplayMsg.show(msg)
                        await self._deliver_picotutor_messages(pending_picotutor_msgs)
                        self.game_end_event()
                        await DisplayMsg.show(game_end)
                    else:
                        await DisplayMsg.show(msg)
                        await self._deliver_picotutor_messages(pending_picotutor_msgs)
                        await self.observe()
                else:  # self.state.interaction_mode in (Mode.ANALYSIS, Mode.KIBITZ, Mode.PONDER, Mode.PGNREPLAY):
                    msg = Message.REVIEW_MOVE_DONE(
                        move=move, fen=game_before.fen(), turn=game_before.turn, game=self.state.game.copy()
                    )
                    game_end = self.state.check_game_state()
                    if game_end:
                        await DisplayMsg.show(msg)
                        await self._deliver_picotutor_messages(pending_picotutor_msgs)
                        self.game_end_event()
                        await DisplayMsg.show(game_end)
                    else:
                        await DisplayMsg.show(msg)
                        await self._deliver_picotutor_messages(pending_picotutor_msgs)
                        await self.analyse()

                await self._deliver_picotutor_messages(pending_picotutor_msgs)

                #
                # More picotutor logic (eval above)
                # @todo check this one also
                #
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
                            await DisplayMsg.show(Message.SHOW_TEXT(text_string=opening_name))
                            await asyncio.sleep(0.7)

                    if self.state.dgtmenu.get_picocomment() != PicoComment.COM_OFF and not game_end:
                        game_comment = ""
                        game_comment = self.state.picotutor.get_game_comment(
                            pico_comment=self.state.dgtmenu.get_picocomment(),
                            com_factor=self.state.dgtmenu.get_comment_factor(),
                        )
                        if game_comment:
                            await DisplayMsg.show(Message.SHOW_TEXT(text_string=game_comment))
                            await asyncio.sleep(0.7)
                self.state.takeback_active = False

                return True

        async def _deliver_picotutor_messages(self, pending_messages: list[tuple[Message, float | None]]) -> None:
            """Send queued picotutor messages after the move announcement."""
            if not pending_messages:
                return
            for message, delay in pending_messages:
                await DisplayMsg.show(message)
                if delay and delay > 0:
                    await asyncio.sleep(delay)
            pending_messages.clear()

        async def observe(self) -> InfoDict | None:
            """Start a new ponder search on the current game."""
            info = await self.analyse()
            await self.state.start_clock()
            return info

        async def update_elo(self, result):
            if self.engine.is_adaptive:
                self.state.rating = await self.engine.update_rating(
                    self.state.rating,
                    determine_result(result, self.state.play_mode, self.state.game.turn == chess.WHITE),
                )

        async def update_elo_display(self):
            if self.emulation_mode():
                await DisplayMsg.show(Message.SYSTEM_INFO(info={"rspeed": self.state.dgtmenu.get_engine_rspeed()}))
            if self.state.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.TRAINING):
                if self.engine.is_adaptive:
                    await DisplayMsg.show(
                        Message.SYSTEM_INFO(
                            info={"user_elo": int(self.state.rating.rating), "engine_elo": self.engine.engine_rating}
                        )
                    )
                elif self.engine.engine_rating > 0:
                    user_elo = self.args.pgn_elo
                    if self.state.rating is not None:
                        user_elo = str(int(self.state.rating.rating))
                    await DisplayMsg.show(
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
                logger.warning("engine is still not waiting")
            # @ todo - check how to do this in new chess library
            # self.engine.position(copy.deepcopy(game))


        # Analysis routing has four main cases.
        # IMPORTANT: `analyse()` has two outputs:
        # 1) clock/DGT output via send_analyse() (depth-gated by best_sent_depth)
        # 2) web client output via send_web_analysis() (source-tagged engine/tutor).
        #
        # 1. Engine is playing and tutor is on:
        #   - Engine turn: use engine PlayingContinuousAnalysis (engine-thinking info).
        #   - User turn: keep clock hint/value engine-driven (do NOT overwrite with tutor info);
        #     tutor info may still be sent to web client output.
        # 2. Engine is playing and tutor is off:
        #   - User turn: use engine ContinuousAnalysis for clock updates.
        #   - Engine turn: use engine PlayingContinuousAnalysis.
        # 3. Engine is not playing and tutor is on:
        #   - Tutor (best engine ContinuousAnalysis) drives clock and web client output.
        # 4. Engine is not playing and tutor is off:
        #   - Engine ContinuousAnalysis drives clock and web client output.
        #
        # Goal: for clock-driving analysis we run only one deep analyser at a time:
        # A. picotutor best_engine ContinuousAnalysis
        #    - tutor-on analysis paths when it's user turn
        # B. engine ContinuousAnalysis
        #    - tutor-off analysis paths, especially when engine is not playing and we analyse both sides
        # C. engine PlayingContinuousAnalysis
        #    - engine-thinking path when it's engine's turn (used regardless of tutor on/off)
        # (ignore picotutor obvious_engine here; it is shallow helper analysis)

        def is_coach_analyser(self) -> bool:
            """Return True when tutor analysis should replace engine analysis."""
            if self.pgn_mode() or (self.engine and self.engine.should_skip_engine_analyser()):
                result = True  # PGN Replay and mame engines always use tutor analysis only
            else:
                # the other analysis modes ie engine not playing moves: use tutor if same engine chosen
                # this saves a lot of CPU on Raspberry Pi
                # issue# 128 save even more cpu - always use tutor for all analysis modes
                result = not self.eng_plays()
                # special case - when playing opening book we need to use tutor when playing engine
                if not result:
                    result = self.eng_plays() and self.state.engine_move_was_book and self.state.is_user_turn()
            return result

        def need_engine_analyser(self) -> bool:
            """return true if engine is analysing moves based on PlayMode"""
            if self.pgn_mode() or (self.engine and self.engine.should_skip_engine_analyser()):
                return False
            # Save CPU at game start: in normal engine-play modes, skip analyser on the
            # untouched standard starting position (no moves played yet).
            if (
                self.eng_plays()
                and self.state.variant == "chess"
                and self.state.game is not None
                and not self.state.game.move_stack
                and self.state.game.fen() == chess.STARTING_FEN
            ):
                return False
            # Engine move has already been selected/displayed but not pushed on the game yet.
            # In this waiting window the old position is stale, so avoid launching the
            # engine ContinuousAnalysis sister for it.
            if self.eng_plays() and self.state.done_computer_fen is not None:
                return False
            engine_thinking = bool(self.engine and self.engine.is_thinking())
            # reverse the first if in analyse(), meaning: it does not use tutor analysis
            result = not (self.is_coach_analyser() and self.state.picotutor.can_use_coach_analyser())
            # 128 - skip engine analyser when engine is thinking about its move
            # because as of 128 the engine play will get info from PlayingContinuousAnalyser
            result = result and not (self.eng_plays() and not self.state.is_user_turn() and engine_thinking)
            # skip engine analyser if tutor can be used on engine waiting for user turn
            # this needs to match the if not self.state.picotutor.can_use_coach_analyser():
            # in analyse
            result = result and not (
                self.eng_plays()
                and self.state.picotutor.can_use_coach_analyser()
                and self.state.is_user_turn()
                and not engine_thinking
            )
            # if engine plays engine analyser is only started if tutor cannot be used - and only on user turn
            return result

        def eng_plays(self) -> bool:
            """return true if engine is playing moves"""
            return bool(self.state.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.TRAINING))

        async def get_rid_of_engine_move(self):
            """in some mode switches we need to get rid of a move engine is thinking about"""
            if self.eng_plays() and self.engine.is_thinking():
                # force a move and skip it to get rid of engine thinking
                self.state.ignore_next_engine_move = True
                self.engine.force_move()
                await asyncio.sleep(0.5)  # wait for forced move to be handled

        async def _start_or_stop_analysis_as_needed(self):
            """start or stop engine analyser as needed (tutor handles this on its own)"""
            if self.engine:
                if self.need_engine_analyser():
                    limit = Limit(depth=FLOAT_ENGINE_MAX_ANALYSIS_DEPTH)
                    # Use variant board if available for correct position representation
                    analysis_board = self.state.get_move_check_board()
                    await self.engine.start_analysis(analysis_board, limit=limit)
                else:
                    await self.engine.stop_analysis()

        def debug_pv_info(self, info: InfoDict):
            if info and "pv" in info and info["pv"]:
                logger.debug(
                    "engine pv move: %s - depth %d - score %s",
                    info.get("pv")[0].uci(),
                    info.get("depth"),
                    str(info["score"]),
                )
            else:
                logger.debug("empty InfoDict")

        async def analyse(self, triggered_by_timer: bool = False) -> InfoDict | None:
            """analyse, observe etc depening on mode - create analysis info
            this is executed periodically in the background_analyse_timer task"""
            info: InfoDict | None = None
            info_list: list[InfoDict] = None
            info_list_source: str | None = None
            info_for_web_engine: InfoDict | None = None
            info_for_web_tutor: InfoDict | None = None
            analysed_fen = ""  # analysis is only valid for this fen
            analysed_fen_for_web_engine = ""
            analysed_fen_for_web_tutor = ""
            if self.is_coach_analyser() and self.state.picotutor.can_use_coach_analyser():
                # here picotutor engine replaces playing engine analysis to save cpu
                result = await self.state.picotutor.get_analysis()
                info_list: list[InfoDict] = result.get("info")
                info_list_source = "tutor"
                analysed_fen = result.get("fen", "")
                info_for_web_tutor = info_list[0] if info_list else None
                analysed_fen_for_web_tutor = analysed_fen
                if self.state.picotutor.get_board().fen() != self.state.game.fen():
                    logger.warning("picotutor board out of sync with game")
                info_candidate = info_list[0] if info_list else None
                if not self.state.best_sent_depth.is_better(info_candidate, analysed_fen, self.state.game):
                    info_list = None  # optimised - prevent this info from being sent
            elif not self.eng_plays() and not self.pgn_mode():
                # we need to analyse both sides without tutor - use engine analyser
                result = await self.engine.get_analysis(self.state.game)
                info_list: list[InfoDict] = result.get("info")
                info_list_source = "engine"
                analysed_fen = result.get("fen", "")
                info_for_web_engine = info_list[0] if info_list else None
                analysed_fen_for_web_engine = analysed_fen
                info_candidate = info_list[0] if info_list else None
                if not self.state.best_sent_depth.is_better(info_candidate, analysed_fen, self.state.game):
                    info_list = None  # optimised - prevent this info from being sent
                await self._start_or_stop_analysis_as_needed()
            else:
                # Issue #109 and #49 before that - how to get engine thinking
                if not self.pgn_mode():
                    engine_thinking = bool(self.engine and self.engine.is_thinking())
                    if not self.state.is_user_turn() and engine_thinking:
                        result = await self.engine.get_thinking_analysis(self.state.game)
                        info_list: list[InfoDict] = result.get("info")
                        info_list_source = "engine-thinking"
                        analysed_fen = result.get("fen", "")
                        info_for_web_engine = info_list[0] if info_list else None
                        analysed_fen_for_web_engine = analysed_fen
                    else:
                        if self.state.picotutor.can_use_coach_analyser():
                            # In engine-play mode this tutor snapshot is intentionally web-only.
                            # Clock +/- remains engine-driven (ponder/engine analysis path).
                            result = await self.state.picotutor.get_analysis()
                            info_candidate_list: list[InfoDict] = result.get("info")
                            info_for_web_tutor = info_candidate_list[0] if info_candidate_list else None
                            analysed_fen_for_web_tutor = result.get("fen", "")
                        else:
                            # is_coach_analyser() must be False here; otherwise the first branch above
                            # would already have routed analysis through picotutor. Only fall back to
                            # engine analysis when tutor info cannot be used.
                            # save cpu - only run engine analysis on user turn if coach/watcher off
                            analysis_board = self.state.get_move_check_board()
                            result = await self.engine.get_analysis(analysis_board)
                            info_list: list[InfoDict] = result.get("info")
                            info_list_source = "engine"
                            analysed_fen = result.get("fen", "")
                            info_for_web_engine = info_list[0] if info_list else None
                            analysed_fen_for_web_engine = analysed_fen
                            info_candidate = info_list[0] if info_list else None
                            if not self.state.best_sent_depth.is_better(info_candidate, analysed_fen, self.state.game):
                                info_list = None  # optimised else: prevent this info from being sent
                    await self._start_or_stop_analysis_as_needed()
            if info_for_web_engine:
                await self.send_web_analysis(
                    info_for_web_engine,
                    analysed_fen_for_web_engine,
                    "engine",
                    suppress_engine_line=False,
                )
            if info_for_web_tutor:
                await self.send_web_analysis(
                    info_for_web_tutor,
                    analysed_fen_for_web_tutor,
                    "tutor",
                    suppress_engine_line=not self.eng_plays(),
                )
            if info_list and (info_list_source != "tutor" or not self.eng_plays()):
                info = info_list[0]  # pv first
                await self.send_analyse(info, analysed_fen)
            # autoplay is temporarily piggybacking on this once-a-second analyse call
            # @todo give it a separate timer task when this is stable
            if self.state.autoplay_pgn_file and self.can_do_next_pgn_replay_move():
                next_move = self._get_cached_pgn_next_move()
                if self._pgn_next_move_in_book(next_move):
                    await asyncio.sleep(1.0)
                    await self.autoplay_pgnreplay_move(allow_game_ends=True, next_move=next_move)  # book move
                elif self.state.picotutor.can_use_coach_analyser():
                    if analysed_fen == self.state.get_fen():
                        latest_depth = await self.state.picotutor.get_latest_seen_depth()
                        min_depth = max(DEEP_DEPTH - 2, 1)
                        if latest_depth >= min_depth:
                            await self.autoplay_pgnreplay_move(allow_game_ends=True, next_move=next_move)  # tutor ready
                else:
                    if triggered_by_timer:
                        await self.autoplay_pgnreplay_move(allow_game_ends=True, next_move=next_move)  # timer triggered
            elif self.state.interaction_mode == Mode.PGNREPLAY and self.state.game.is_game_over():
                if self.state.autoplay_pgn_file:
                    self.state.autoplay_pgn_file = False
                    logger.debug("PGN replay ended; autoplay stopped")
            return info

        async def send_analyse(
            self, info: InfoDict, analysed_fen: str, send_pv: bool = True, ponder_move: chess.Move | None = None
        ):
            """send pv, depth, and score events for a specific analysed fen
            with send_pv False pv message is not sent - use if its previous move InfoDict
            ponder_move overrides the cached ponder the optimiser remembers (None keeps previous behaviour)
            this is executed periodically in the background_analyse_timer task"""
            if not info:
                return
            current_fen = self.state.get_fen()
            if analysed_fen != current_fen:
                logger.debug("ignoring analysis info for old fen: %s != %s", analysed_fen, current_fen)
                return
            # ask for score from white's perspective
            (move, score, mate) = PicoTutor.get_score(info)
            if "depth" in info:
                depth = info.get("depth")
                cache_ponder = move
                if ponder_move is not None:
                    cache_ponder = ponder_move
                self.state.best_sent_depth.set_best(info, analysed_fen, self.state.game, cache_ponder)
                # send depth before score as score is assembling depth in receiver end
                await Observable.fire(Event.NEW_DEPTH(depth=depth))
            if send_pv:
                pv_move_to_send = ponder_move if ponder_move and ponder_move != chess.Move.null() else move
                pv_moves = list(info.get("pv") or [])
                if pv_moves:
                    if pv_move_to_send and pv_move_to_send != chess.Move.null():
                        pv_moves[0] = pv_move_to_send
                    pv_to_send = pv_moves
                else:
                    pv_to_send = [pv_move_to_send] if pv_move_to_send != chess.Move.null() else []
                if pv_to_send:
                    self.state.pb_move = pv_to_send[0]  # backward compatibility
                    await Observable.fire(Event.NEW_PV(pv=pv_to_send))
            if score is not None:
                await Observable.fire(Event.NEW_SCORE(score=score, mate=mate))

        async def send_web_analysis(
            self,
            info: InfoDict,
            analysed_fen: str,
            source: str,
            suppress_engine_line: bool = False,
        ):
            """Send full analysis info to the web client without depth gating."""
            if not info:
                return
            current_fen = self.state.get_fen()
            if analysed_fen != current_fen:
                logger.debug("ignoring web analysis for old fen: %s != %s", analysed_fen, current_fen)
                return
            (move, score, mate) = PicoTutor.get_score(info)
            depth = info.get("depth")
            pv_moves = list(info.get("pv") or [])
            pv_to_send = [m.uci() for m in pv_moves if m] if pv_moves else []
            if not pv_to_send and move and move != chess.Move.null():
                pv_to_send = [move.uci()]
            analysis_payload = {
                "depth": depth,
                "score": score,
                "mate": mate,
                "pv": pv_to_send,
                "fen": analysed_fen,
                "source": source,
                "suppress_engine_line": suppress_engine_line,
            }
            await DisplayMsg.show(Message.WEB_ANALYSIS(analysis=analysis_payload))

        async def autoplay_pgnreplay_move(
            self, allow_game_ends, next_move: chess.Move | None = None
        ) -> chess.Move:
            """play the next PGN move if one found - return None if next move was found
            for future its allowed to return chess.Move.null() if move not found"""
            if next_move is None:
                next_move = self._get_cached_pgn_next_move()
            moves_game = len(self.state.game.move_stack)  # half_move dont work in library
            moves_pgn = -1
            if next_move:
                await self.do_pgn_replay_move(next_move)
                self.state.autoplay_half_moves = moves_game + 1  # remember last seen autoplay move
            elif allow_game_ends:
                # preferred elif instead of if here to avoid checking end of game often
                moves_pgn = self.state.picotutor.get_pgn_halfmove_clock()  # slow call
                if moves_game == moves_pgn:
                    # signal end of pgn replay game - not using PGN_GAME_ENDS ...
                    # lets first see if we can use same GAME_ENDS as for normal endings
                    try:
                        result = game_result_from_header(self.shared["headers"].get("Result", ""))
                    except ValueError:
                        result = GameResult.ABORT
                    # @todo deviated from the original moves with takeback result in ABORT
                    # because the PGN game header "Result" changed when you deviated
                    self.game_end_event()  # sets autoplay to False
                    await DisplayMsg.show(
                        Message.GAME_ENDS(
                            tc_init=self.state.time_control.get_parameters(),
                            result=result,
                            play_mode=self.state.play_mode,
                            game=self.state.game.copy(),
                            mode=self.state.interaction_mode,
                        )
                    )
            if not next_move:
                self.state.autoplay_pgn_file = False  # always stop autoplay, not only else/elif
                logger.debug(
                    "No more PGN replay moves: halfmoves game %d, pgn %d, last seen automove %d",
                    moves_game,
                    moves_pgn,
                    self.state.autoplay_half_moves,
                )
            return next_move

        async def expired_fen_timer(self):
            """Handle times up for an unhandled fen string send from board."""
            game_fen = ""
            self.state.fen_timer_running = False
            external_fen = ""
            internal_fen = ""

            if self.state.error_fen:
                logger.debug("fen_timer expired %s", self.state.error_fen)
                game_fen = self.state.get_board_fen()
                internal_fen = game_fen
                external_fen = self.state.error_fen
                fen_res = compare_fen(external_fen, internal_fen)
                if fen_res and (fen_res[4] == "K" or fen_res[4] == "k"):
                    self.state.coach_triggered = True
                if (
                    self.state.interaction_mode in (Mode.NORMAL, Mode.TRAINING, Mode.BRAIN)
                    and self.state.error_fen != chess.STARTING_BOARD_FEN
                    and not (self.state.variant == "racingkings" and self.state.error_fen == RK_STARTING_BOARD_FEN)
                    and (game_fen == chess.STARTING_BOARD_FEN or (self.state.variant == "racingkings" and game_fen == RK_STARTING_BOARD_FEN))
                    and self.state.flag_startup
                    and self.state.dgtmenu.get_game_contlast()
                    and not self.online_mode()
                    and not self.pgn_mode()
                    and not self.emulation_mode()
                ):
                    # molli: read the pgn of last game and restore correct game status and times
                    self.state.flag_startup = False
                    await DisplayMsg.show(Message.RESTORE_GAME())
                    await asyncio.sleep(2)

                    l_pgn_file_name = "last_game.pgn"
                    await self.read_pgn_file(l_pgn_file_name)

                # issue #78 - fast moving ponder mode - commit c253f2c 15.6.2025 was first
                # see also issue #82 - allow switching sides in PONDER mode
                elif (
                    self.state.interaction_mode == Mode.PONDER
                    and self.state.flag_flexible_ponder
                    and not self.state.coach_triggered
                ):
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
                            # Sync variant boards with new position
                            if self.state.variant == "3check" and self.state._threecheck_board is not None:
                                self.state._threecheck_board.set_fen(bit_board.fen())
                            elif self.state.variant == "atomic" and self.state._atomic_board is not None:
                                self.state._atomic_board.set_fen(bit_board.fen())
                            await self.engine.newgame(self.state.engine_board_copy(), False)
                            self.state.best_sent_depth.reset()
                            self.state.done_computer_fen = None
                            self.state.done_move = self.state.pb_move = chess.Move.null()
                            self.state.searchmoves.reset()
                            self.state.game_declared = False
                            self.state.legal_fens = compute_legal_fens(self.state.game.copy(), self.state.get_variant_board())
                            self.state.legal_fens_after_cmove = []
                            self.state.last_legal_fens = []
                            await DisplayMsg.show(Message.SHOW_TEXT(text_string="NEW_POSITION"))
                            await DisplayMsg.show(self.state.new_game_msg(newgame=False))
                            await self.set_picotutor_position(new_game=True)  # issue #78 new code
                        else:
                            # ask python-chess to correct the castling string
                            bit_board = chess.Board(fen2)
                            bit_board.set_fen(bit_board.fen())
                            if bit_board.is_valid():
                                self.state.game = chess.Board(bit_board.fen())
                                # Sync variant boards with new position
                                if self.state.variant == "3check" and self.state._threecheck_board is not None:
                                    self.state._threecheck_board.set_fen(bit_board.fen())
                                elif self.state.variant == "atomic" and self.state._atomic_board is not None:
                                    self.state._atomic_board.set_fen(bit_board.fen())
                                await self.engine.newgame(self.state.engine_board_copy(), False)
                                self.state.best_sent_depth.reset()
                                self.state.done_computer_fen = None
                                self.state.done_move = self.state.pb_move = chess.Move.null()
                                self.state.searchmoves.reset()
                                self.state.game_declared = False
                                self.state.legal_fens = compute_legal_fens(self.state.game.copy(), self.state.get_variant_board())
                                self.state.legal_fens_after_cmove = []
                                self.state.last_legal_fens = []
                                await DisplayMsg.show(Message.SHOW_TEXT(text_string="NEW_POSITION"))
                                await DisplayMsg.show(
                                    self.state.new_game_msg(newgame=False)
                                )
                                await self.set_picotutor_position(new_game=True)  # issue #78 new code
                            else:
                                logger.info("wrong fen %s for 4 secs", self.state.error_fen)
                                await DisplayMsg.show(Message.WRONG_FEN())
                else:
                    logger.info("wrong fen %s for 4 secs", self.state.error_fen)
                    if self.online_mode():
                        # show computer opponents move again
                        if self.state.seeking_flag:
                            await DisplayMsg.show(Message.SEEKING())
                        elif self.state.best_move_displayed:
                            await DisplayMsg.show(
                                Message.COMPUTER_MOVE(
                                    move=self.state.done_move,
                                    ponder=False,
                                    game=self.state.game_copy(),
                                    wait=False,
                                    is_user_move=False,
                                )
                            )
                    fen_res = ""
                    internal_fen = self.state.get_board_fen()
                    external_fen = self.state.error_fen
                    fen_res = compare_fen(external_fen, internal_fen)

                    if self.state.setpieces_switch_anchor_fen:
                        if external_fen == self.state.setpieces_switch_anchor_fen:
                            if self.state.setpieces_switch_armed:
                                self.state.setpieces_switch_armed = False
                                self.switch_artwork_window()
                        else:
                            self.state.setpieces_switch_armed = True

                    if (not self.state.position_mode) and fen_res:
                        if fen_res[4] == "K" or fen_res[4] == "k":
                            self.state.coach_triggered = True
                            if not self.picotutor_mode():
                                self.state.position_mode = True
                        else:
                            self.state.position_mode = True
                            self.state.coach_triggered = False
                        if external_fen != chess.STARTING_BOARD_FEN and not (
                            self.state.variant == "racingkings" and external_fen == RK_STARTING_BOARD_FEN
                        ):
                            if not self.state.setpieces_switch_anchor_fen:
                                self.state.setpieces_switch_anchor_fen = external_fen
                                self.state.setpieces_switch_armed = False
                            await DisplayMsg.show(Message.WRONG_FEN())
                            await asyncio.sleep(2)
                        self.state.delay_fen_error = 4
                        # molli: Picochess correction messages
                        # show incorrect square(s) and piece to put or be removed
                    elif self.state.position_mode and fen_res:
                        self.state.delay_fen_error = 1
                        if not self.online_mode():
                            await self.state.stop_clock()
                        msg = Message.POSITION_FAIL(fen_result=fen_res)
                        await DisplayMsg.show(msg)
                        await asyncio.sleep(1)
                    else:
                        await DisplayMsg.show(Message.EXIT_MENU())
                        self.state.delay_fen_error = 4

                    _start_fen = RK_STARTING_BOARD_FEN if self.state.variant == "racingkings" else chess.STARTING_BOARD_FEN
                    if (
                        self.state.interaction_mode in (Mode.NORMAL, Mode.TRAINING, Mode.BRAIN)
                        and game_fen != _start_fen
                        and self.state.flag_startup
                    ):
                        if self.state.dgtmenu.get_enginename():
                            msg = Message.ENGINE_NAME(engine_name=self.state.engine_text)
                            await DisplayMsg.show(msg)

                        if self.pgn_mode():
                            headers = self.shared.get("headers", {}) or {}
                            pgn_white = headers.get("White", "")
                            pgn_black = headers.get("Black", "")
                            pgn_game_name = headers.get("Event", "")
                            pgn_problem = headers.get("Problem", "")
                            pgn_fen = headers.get("FEN", "")
                            pgn_result = headers.get("Result", "")

                            async def show_pgn_headers():
                                update_speed = 1.0
                                if pgn_white:
                                    await DisplayMsg.show(Message.SHOW_TEXT(text_string=pgn_white))
                                    await asyncio.sleep(update_speed)
                                if pgn_black:
                                    await DisplayMsg.show(Message.SHOW_TEXT(text_string=pgn_black))
                                    await asyncio.sleep(update_speed)
                                if pgn_result:
                                    await DisplayMsg.show(Message.SHOW_TEXT(text_string=pgn_result))
                                    await asyncio.sleep(update_speed)
                                if "mate in" in pgn_problem or "Mate in" in pgn_problem:
                                    await DisplayMsg.show(Message.SHOW_TEXT(text_string=pgn_problem))
                                else:
                                    await DisplayMsg.show(Message.SHOW_TEXT(text_string=pgn_game_name))
                                await asyncio.sleep(update_speed)

                            if "mate in" in pgn_problem or "Mate in" in pgn_problem:
                                await self.set_fen_from_pgn(pgn_fen)
                            asyncio.create_task(show_pgn_headers())

                    else:
                        if self.state.done_computer_fen and not self.state.position_mode:
                            await DisplayMsg.show(Message.EXIT_MENU())
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

            l_game_pgn: Game | None = chess.pgn.read_game(l_file_pgn)
            l_file_pgn.close()

            logger.debug("molli: read game filename %s", l_filename)

            await self.stop_search_and_clock()
            # reset best depth so new analysis results are not filtered by previous game
            self.state.best_sent_depth.reset()

            # forget possible previously loaded PGN game
            self.state.picotutor.set_pgn_game_to_step(None)
            if self.picotutor_mode():
                await self.state.picotutor.newgame()

            fen_header_raw = l_game_pgn.headers.get("FEN") if l_game_pgn.headers else None
            fen_header = str(fen_header_raw).strip() if fen_header_raw else ""
            fen_board_valid = True
            try:
                base_board = l_game_pgn.board()
                self.state.game = base_board.copy()
            except ValueError:
                fen_board_valid = False
                logger.warning("Invalid board setup in PGN headers: %s", fen_header)
                self.state.game = chess.Board()
            l_move = chess.Move.null()

            update_speed = 1.0
            is_pico_save_game: bool = False
            if l_game_pgn.headers["Event"]:
                event_str = l_game_pgn.headers["Event"]
                if (event_str or "").startswith("PicoChess"):
                    is_pico_save_game = True  # game was saved by Pico
                logger.debug(f"is_pico_save_game: {is_pico_save_game}")  # TODO clarify usage of is_pico_save_game
                await DisplayMsg.show(Message.SHOW_TEXT(text_string=str(event_str)))
                await asyncio.sleep(update_speed)

            if l_game_pgn.headers["White"]:
                await DisplayMsg.show(Message.SHOW_TEXT(text_string=str(l_game_pgn.headers["White"])))
                await asyncio.sleep(update_speed)

            await DisplayMsg.show(Message.SHOW_TEXT(text_string="versus"))
            await asyncio.sleep(update_speed)

            if l_game_pgn.headers["Black"]:
                await DisplayMsg.show(Message.SHOW_TEXT(text_string=str(l_game_pgn.headers["Black"])))
                await asyncio.sleep(update_speed)

            result_header_raw = l_game_pgn.headers.get("Result") if l_game_pgn.headers else None
            result_header = str(result_header_raw).strip() if result_header_raw else ""
            if result_header_raw:
                display_result = result_header or str(result_header_raw)
                await DisplayMsg.show(Message.SHOW_TEXT(text_string=display_result))
                await asyncio.sleep(update_speed)

            # make sure we have "?" in important missing headers to
            # prevent overwrite by existing user or engine names or elos etc
            ensure_important_headers(l_game_pgn.headers)

            await DisplayMsg.show(Message.READ_GAME)

            # check if we should stop loading pgn game "in the middle"
            # this feature can be used to "jump to" a certain position in pgn
            # PicoStop value shall be given in half moves
            try:
                if "PicoStop" in l_game_pgn.headers and l_game_pgn.headers["PicoStop"]:
                    l_stop_at_halfmove = int(l_game_pgn.headers["PicoStop"])
                else:
                    l_stop_at_halfmove = None
            except ValueError:
                l_stop_at_halfmove = None

            if not l_stop_at_halfmove:
                # no PicoStop override found above - check game result
                if result_header and result_header not in ("*", "?"):
                    # a game with a final result was loaded - issue #54
                    if self.board_type == dgt.util.EBoard.NOEBOARD:
                        # @todo cant use zero on web display because Pico code below
                        # does a pop and user_move just to update web display - see todo below
                        # maybe this is ok, or some other web display update could be found?
                        l_stop_at_halfmove = 1
                    else:
                        l_stop_at_halfmove = 0  # for DGT board its better with zero

            if not fen_header and l_stop_at_halfmove != 0:
                for l_move in l_game_pgn.mainline_moves():
                    self.state.push_move(l_move)
                    if l_stop_at_halfmove and len(self.state.game.move_stack) >= l_stop_at_halfmove:
                        # stop loading pgn game moves... Store them so user can step through them
                        break
                self._update_variant_shared()

            # take back last move in order to send it with user_move for web publishing
            # @ todo Pico V3 made user + engine move here = unnecessary waiting for engine move
            # Pico V4 only makes an engine move... just to update the web screen and main states?
            # maybe there is a smarter way to do this?
            if not fen_header and l_move and l_stop_at_halfmove != 0:
                self.state.pop_move()
                self._update_variant_shared()

            # issue #72 - newgame sends a ucinewgame unless stopped
            await self.engine.newgame(self.state.engine_board_copy(), send_ucinewgame=False)
            if fen_header and fen_board_valid:
                # publish FEN-started game to displays/engine listeners
                await DisplayMsg.show(self.state.new_game_msg(newgame=False))

            # switch temporarly picotutor off
            old_flag_picotutor = self.state.flag_picotutor
            self.state.flag_picotutor = False
            old_interaction_mode = self.state.interaction_mode
            self.state.interaction_mode = Mode.PGNREPLAY  # new mode for loaded PGN games
            self.state.autoplay_pgn_file = False  # if you load a 2nd PGN it will autosave from move 1
            self.state.dgtmenu.set_mode(Mode.PGNREPLAY)
            self.state.dgtmenu.exit_menu()  # leave menu so that PAUSE_RESUME avoids "no function"

            if l_move and l_stop_at_halfmove != 0:
                # publish current position to webserver
                await self.user_move(l_move, sliding=True)

            if fen_header and fen_board_valid:
                # any FEN in PGN forces kibitz/analysis mode (Mode.KIBITZ)
                self.state.interaction_mode = Mode.KIBITZ
                self.state.dgtmenu.set_mode(Mode.KIBITZ)
            elif fen_header:
                logger.warning("FEN header found but could not apply board setup: %s", fen_header)
            elif not result_header or result_header in ("*", "?"):
                # issue #54 game is not finished - switch back to playing mode
                if old_interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.TRAINING):
                    # same as eng_plays() - preserve previous playing mode
                    self.state.interaction_mode = old_interaction_mode
                else:
                    self.state.interaction_mode = Mode.NORMAL
                self.state.dgtmenu.set_mode(self.state.interaction_mode)
            # else remain in PGNREPLAY mode

            # restore picotutor flag to previous state
            self.state.flag_picotutor = old_flag_picotutor
            # always fix the picotutor if-to-analyse both sides and depth
            await self.engine.stop_analysis()  # stop possible engine analyser
            if self.eng_plays():
                await self.state.picotutor.stop()  # stop possible old tutor analysers
            await self.state.picotutor.set_mode(self.pgn_mode() or not self.eng_plays())

            await self.stop_search_and_clock()
            await self.engine_mode()
            turn = self.state.game.turn
            self.state.done_computer_fen = None
            self.state.done_move = self.state.pb_move = chess.Move.null()
            self.state.play_mode = PlayMode.USER_WHITE if turn == chess.WHITE else PlayMode.USER_BLACK

            # game state should be done now, start picotutor
            await self.set_picotutor_position(new_game=True)

            # ensure analysis optimisation is fresh after header display/setup
            self.state.best_sent_depth.reset()

            self.state.tc_init_last = self.state.time_control.get_parameters()
            self.state.time_control.reset()  # fallback is same as ini setting
            # if we find settings from the file we use them to override fallback
            l_pico_depth = 0
            try:
                if "PicoDepth" in l_game_pgn.headers and l_game_pgn.headers["PicoDepth"]:
                    l_pico_depth = int(l_game_pgn.headers["PicoDepth"])
                else:
                    l_pico_depth = 0
            except ValueError:
                l_pico_depth = 0

            l_pico_node = 0
            try:
                if "PicoNode" in l_game_pgn.headers and l_game_pgn.headers["PicoNode"]:
                    l_pico_node = int(l_game_pgn.headers["PicoNode"])
                else:
                    l_pico_node = 0
            except ValueError:
                l_pico_node = 0

            # override time control if its found in pgn file
            if "PicoTimeControl" in l_game_pgn.headers and l_game_pgn.headers["PicoTimeControl"]:
                l_pico_tc = str(l_game_pgn.headers["PicoTimeControl"])
                self.state.time_control, time_text = await self.state.transfer_time(
                    l_pico_tc.split(), depth=l_pico_depth, node=l_pico_node
                )

            # override remaining thinking time
            try:
                if "PicoRemTimeW" in l_game_pgn.headers and l_game_pgn.headers["PicoRemTimeW"]:
                    lt_white = int(l_game_pgn.headers["PicoRemTimeW"])
                else:
                    lt_white = None
            except ValueError:
                lt_white = None

            try:
                if "PicoRemTimeB" in l_game_pgn.headers and l_game_pgn.headers["PicoRemTimeB"]:
                    lt_black = int(l_game_pgn.headers["PicoRemTimeB"])
                else:
                    lt_black = None
            except ValueError:
                lt_black = None

            # send TIME_CONTROL event based on info collected above
            tc_init = self.state.time_control.get_parameters()
            if lt_white and lt_black:
                tc_init["internal_time"] = {chess.WHITE: lt_white, chess.BLACK: lt_black}
            text = self.state.dgttranslate.text("N00_oktime")
            await Observable.fire(Event.SET_TIME_CONTROL(tc_init=tc_init, time_text=text, show_ok=False))
            await self.state.stop_clock()
            await DisplayMsg.show(Message.EXIT_MENU())

            self.state.searchmoves.reset()
            self.state.game_declared = False

            self.state.legal_fens = compute_legal_fens(self.state.game.copy(), self.state.get_variant_board())
            self.state.legal_fens_after_cmove = []
            self.state.last_legal_fens = []
            await self.stop_search_and_clock()

            self.shared["headers"] = l_game_pgn.headers  # update headers from file
            EventHandler.write_to_clients({"event": "Header", "headers": dict(self.shared["headers"])})
            await asyncio.sleep(0.1)  # give time to write_to_clients

            game_end = self.state.check_game_state()
            if game_end:
                self.state.play_mode = PlayMode.USER_WHITE if turn == chess.WHITE else PlayMode.USER_BLACK
                self.state.legal_fens = []
                self.state.legal_fens_after_cmove = []
                self.game_end_event()
                await DisplayMsg.show(game_end)
            else:
                self.state.play_mode = PlayMode.USER_WHITE if turn == chess.WHITE else PlayMode.USER_BLACK
                if self.eng_plays():
                    # we continue in a mode where engine is playing, not analysis
                    text = self.state.play_mode.value
                    msg = Message.PLAY_MODE(
                        play_mode=self.state.play_mode,
                        play_mode_text=self.state.dgttranslate.text(text),
                    )
                    await DisplayMsg.show(msg)
                    await asyncio.sleep(1)

            self.state.take_back_locked = True  # important otherwise problems for setting up the position
            if not fen_header:
                pgn_game_to_step = None if l_stop_at_halfmove is None else l_game_pgn
                if pgn_game_to_step:
                    # this PGN game was not loaded to the end (above) - remember it
                    self.state.picotutor.set_pgn_game_to_step(pgn_game_to_step)
                    self.state.autoplay_half_moves = 0  # remember last seen autoplay move
                    if self.state.interaction_mode == Mode.PGNREPLAY:
                        self._start_pgn_replay_autoplay()

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

                await self.state.stop_clock()
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

            await self.state.stop_clock()
            text = self.state.dgttranslate.text("N00_oktime")
            self.state.time_control.reset()
            await Observable.fire(Event.SET_TIME_CONTROL(tc_init=tc_init, time_text=text, show_ok=True))
            await self.state.stop_clock()
            await DisplayMsg.show(Message.EXIT_MENU())

        async def engine_mode(self):
            """call when engine mode is changed"""
            if self.state.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.TRAINING):
                # optimisation, dont ask for ponder unless needed
                ponder_mode = True if self.state.interaction_mode == Mode.BRAIN else False
                self.engine.set_mode(ponder=ponder_mode)
                # mode might have changed back to playing, activate tutor
                await self.state.picotutor.set_status(
                    self.state.dgtmenu.get_picowatcher(),
                    self.state.dgtmenu.get_picocoach(),
                    self.state.dgtmenu.get_picoexplorer(),
                    self.state.dgtmenu.get_picocomment(),
                )
            elif self.state.interaction_mode in (Mode.ANALYSIS, Mode.KIBITZ, Mode.OBSERVE, Mode.PONDER, Mode.PGNREPLAY):
                self.engine.set_mode()
                # Pico v4 allow picotutor to run also when watching
                await self.state.picotutor.set_status(
                    self.state.dgtmenu.get_picowatcher(),
                    self.state.dgtmenu.get_picocoach(),
                    self.state.dgtmenu.get_picoexplorer(),
                    self.state.dgtmenu.get_picocomment(),
                )
            if self.state.flag_picotutor:
                # always fix the picotutor if-to-analyse both sides and depth
                await self.state.picotutor.set_mode(self.pgn_mode() or not self.eng_plays())
            await self._start_or_stop_analysis_as_needed()  # engine mode changed

        def remote_engine_mode(self):
            if "remote" in self.state.engine_file:
                return True
            else:
                return False

        async def _pv_score_depth_analyser(self):
            """Analyse PV score depth in the background"""
            if self.state.game:
                if not self.state.game.is_game_over():
                    await self.analyse(triggered_by_timer=True)

        async def event_consumer(self):
            """Event consumer for main"""
            logger.debug("evt_queue ready")
            try:
                while True:
                    event = await evt_queue.get()
                    if event is None:
                        # this is the signal to stop the main loop
                        logger.debug("evt_queue received None, stopping main loop")
                        break
                    # issue #45 still let main loop create tasks
                    # @todo check if this should not do create_task either
                    # create_task should make program more responsive to user tasks
                    asyncio.create_task(self.process_main_events(event))
                    evt_queue.task_done()
                    await asyncio.sleep(0.05)  # balancing message queues
            except asyncio.CancelledError:
                logger.debug("evt_queue cancelled")

        async def pre_exit_or_reboot_cleanups(self):
            """First immediate cleanups before exit or reboot"""
            logger.debug("pre exit_or_reboot_cleanups")
            if self.state.fen_timer_running:
                self.state.stop_fen_timer()
            # @todo are there other timers to stop here?
            # as we wait 5 secs before exiting we only want to prevent timer actions
            await self.stop_search()
            await self.state.stop_clock()
            await self.engine.quit()
            if self.state.picotutor:
                # close all the picotutor engines
                await self.state.picotutor.exit_or_reboot_cleanups()

        async def final_exit_or_reboot_cleanups(self):
            """Last cleanups before exit or reboot"""
            logger.debug("final exit_or_reboot_cleanups")
            if getattr(self.state, "pairing_bridge", None):
                await self.state.pairing_bridge.close()
            if self.pico_talker:
                # close the sound system (this is why final is a separate call)
                await self.pico_talker.exit_or_reboot_cleanups()
            # cancel all non-main tasks, this task will stop itself
            # and a None has been placed in the main event queue to stop it
            for task in self.non_main_tasks:
                task.cancel()
            # as the final step stop the main loop task
            # by putting None in the main event queue
            logger.debug("final exit_or_reboot_cleanups done - stopping main evt_queue")
            await Observable.fire(None)

        def can_do_next_pgn_replay_move(self) -> bool:
            """check if we can do the next pgn move"""
            if self.state.interaction_mode != Mode.PGNREPLAY or self.state.game.is_game_over():
                return False
            if self.state.picotutor.get_pgn_game_to_step is None:
                return False  # No game to try to step through
            if self.board_type == dgt.util.EBoard.NOEBOARD:
                # on web display we can always autoplay the next pgn move
                return True
            # on a eboard we have to check if its waiting for
            # the previous move to be done by the user
            if self.state.done_computer_fen is None:
                # not waiting for a move, ok to do next move
                return True
            # the most tricky part, we are waiting for a move, has it been done?
            # Use get_board_fen() for variant-aware comparison (atomic explosions, etc.)
            if self.state.get_board_fen() == self.state.done_computer_fen:
                # yes, the move has been done, we can do the next move
                return True
            return False

        def _start_pgn_replay_autoplay(self) -> None:
            """Enable PGN replay autoplay without advancing immediately."""
            if self.can_do_next_pgn_replay_move():
                self.state.autoplay_pgn_file = True

        def _get_cached_pgn_next_move(self) -> chess.Move | None:
            """Return cached next PGN move for current FEN, computing when needed."""
            if not self.state.picotutor:
                return None
            current_fen = self.state.game.fen()
            if self.state.pgn_replay_next_move_fen == current_fen:
                return self.state.pgn_replay_next_move
            next_move = self.state.picotutor.get_next_pgn_move(self.state.game)
            self.state.pgn_replay_next_move_fen = current_fen
            self.state.pgn_replay_next_move = next_move
            return next_move

        def _get_cached_book_moves(self) -> set[chess.Move] | None:
            """Return cached opening book moves for current FEN."""
            if not self.bookreader:
                return None
            current_fen = self.state.game.fen()
            cached_moves = self.state.pgn_replay_book_cache.get(current_fen)
            if cached_moves is not None:
                return cached_moves
            moves = set()
            try:
                for entry in self.bookreader.find_all(self.state.game):
                    moves.add(entry.move)
            except Exception as exc:
                logger.debug("opening book lookup failed: %s", exc)
                return moves
            if len(self.state.pgn_replay_book_cache) >= 64:
                self.state.pgn_replay_book_cache.pop(next(iter(self.state.pgn_replay_book_cache)))
            self.state.pgn_replay_book_cache[current_fen] = moves
            return moves

        def _pgn_next_move_in_book(self, next_move: chess.Move | None) -> bool:
            """Check whether the next PGN move is present in the current opening book."""
            if not next_move:
                return False
            book_moves = self._get_cached_book_moves()
            if not book_moves:
                return False
            return next_move in book_moves

        async def do_pgn_replay_move(self, next_move: chess.Move):
            """Used by autoplay to execute the next PGN replay move"""
            assert self.state.interaction_mode == Mode.PGNREPLAY
            if self.board_type == dgt.util.EBoard.NOEBOARD:
                await self.user_move(next_move, sliding=False)
            else:
                game_copy = self.state.game_copy()
                await DisplayMsg.show(
                    Message.COMPUTER_MOVE(
                        move=next_move,
                        ponder=False,
                        game=game_copy,
                        wait=False,
                        is_user_move=True,
                    )
                )
                # set state variables as waiting for the move to be done on the eboard
                game_copy.push(next_move)
                # For atomic variant, use atomic board to get FEN with explosions applied
                if self.state.variant == "atomic" and self.state._atomic_board is not None:
                    atomic_copy = self.state._atomic_board.copy()
                    atomic_copy.push(next_move)
                    self.state.done_computer_fen = atomic_copy.board_fen()
                else:
                    self.state.done_computer_fen = game_copy.board_fen()  # expected fen after move
                self.state.done_move = next_move  # expected move

        def game_end_event(self):
            #  @todo1 should have an EVENT message for game end, function for now
            #  @todo2 should be more state variables to reset here?
            self.state.autoplay_pgn_file = False  # prevent autoplay starting for next pgn read

        def _load_pgn_engine_games(self, pgn_file: str) -> None:
            self.state.pgn_engine_games = []
            self.state.pgn_engine_game_index = -1
            self.state.pgn_engine_total_halfmoves = None
            self.state.pgn_engine_result = "*"
            if not pgn_file:
                return
            try:
                with open(pgn_file) as f:
                    while True:
                        pgn_game = chess.pgn.read_game(f)
                        if not pgn_game:
                            break
                        if getattr(pgn_game, "errors", []):
                            logger.error("Skipping remaining PGN games after parse error: %s", pgn_game.errors)
                            break
                        headers = dict(pgn_game.headers)
                        self.state.pgn_engine_games.append(
                            {
                                "headers": headers,
                                "total_halfmoves": sum(1 for _ in pgn_game.mainline_moves()),
                                "result": headers.get("Result", "*"),
                            }
                        )
            except (OSError, ValueError) as exc:
                logger.debug("Could not read pgn_engine file %s: %s", pgn_file, exc)

        def _apply_pgn_engine_game(self, game_info: dict[str, Any]) -> None:
            headers = dict(game_info.get("headers", {}))
            ensure_important_headers(headers)
            self.shared["headers"] = headers
            EventHandler.write_to_clients({"event": "Header", "headers": dict(headers)})
            self.state.pgn_engine_total_halfmoves = game_info.get("total_halfmoves")
            self.state.pgn_engine_result = game_info.get("result", "*")

        def _advance_pgn_engine_game(self) -> None:
            if not self.state.pgn_engine_games:
                return
            next_index = (self.state.pgn_engine_game_index + 1) % len(self.state.pgn_engine_games)
            self.state.pgn_engine_game_index = next_index
            self._apply_pgn_engine_game(self.state.pgn_engine_games[next_index])

        async def process_main_events(self, event):
            """Consume event from evt_queue"""
            if (
                not isinstance(event, Event.CLOCK_TIME)
                and not isinstance(event, Event.NEW_DEPTH)
                and not isinstance(event, Event.NEW_PV)
                and not isinstance(event, Event.NEW_SCORE)
            ):
                logger.debug("received event from evt_queue: %s", event)
            if isinstance(event, Event.FEN):
                await self.process_fen(event.fen, self.state)

            elif isinstance(event, Event.KEYBOARD_MOVE):
                move = event.move
                logger.debug("keyboard move [%s]", move)
                # Use variant board for legality check (atomic has different legal moves)
                _check_board = self.state.get_move_check_board()
                if move not in _check_board.legal_moves:
                    logger.warning("illegal move. fen: [%s]", self.state.game.fen())
                else:
                    game_copy = self.state.game.copy()
                    game_copy.push(move)
                    # For atomic variant, use atomic board to get FEN with explosions applied
                    if self.state.variant == "atomic" and self.state._atomic_board is not None:
                        atomic_copy = self.state._atomic_board.copy()
                        atomic_copy.push(move)
                        fen = atomic_copy.board_fen()
                    else:
                        fen = game_copy.board_fen()
                    await DisplayMsg.show(Message.DGT_FEN(fen=fen, raw=False))

            elif isinstance(event, Event.LEVEL):
                if event.options:
                    startup_ok = await self.engine.startup(event.options, self.state.rating)
                    if not startup_ok:
                        logger.error("engine startup failed; invalid .uci options")
                        await DisplayMsg.show(Message.ENGINE_FAIL())
                        return
                self.state.new_engine_level = event.level_name
                await DisplayMsg.show(
                    Message.LEVEL(
                        level_text=event.level_text,
                        level_name=event.level_name,
                        do_speak=bool(event.options),
                    )
                )

            elif isinstance(event, Event.NEW_ENGINE):
                # if we are waiting for an engine move, get rid of that first
                await self.get_rid_of_engine_move()
                self.state.best_sent_depth.reset()
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
                        await DisplayMsg.show(Message.SHOW_TEXT(text_string="NO_ARTWORK"))

                await DisplayMsg.show(Message.ENGINE_SETUP())
                await self.engine.quit()
                # Load the new one and send self.args.
                uci_shell = self.uci_remote_shell if self.remote_engine_mode() and self.uci_remote_shell else self.uci_local_shell
                self.engine = UciEngine(
                    file=engine_file_to_load,
                    uci_shell=uci_shell,
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
                    # restart old mame engine?
                    self.state.artwork_in_use = False
                    if "/mame/" in old_file and self.state.dgtmenu.get_engine_rdisplay():
                        old_file_art = old_file + "_art"
                        my_file = Path(old_file_art)
                        if my_file.is_file():
                            self.state.artwork_in_use = True
                            old_file = old_file_art

                    uci_shell = self.uci_remote_shell if self.remote_engine_mode() and self.uci_remote_shell else self.uci_local_shell

                    self.engine = UciEngine(
                        file=old_file,
                        uci_shell=uci_shell,
                        mame_par=self.calc_engine_mame_par(),
                        loop=self.loop,
                    )
                    await self.engine.open_engine()
                    if not self.engine.loaded_ok():
                        # Help - old engine failed to restart. There is no engine
                        logger.error("no engines started")
                        await DisplayMsg.show(Message.ENGINE_FAIL())
                        await asyncio.sleep(3)
                        sys.exit(-1)
                # All done - rock'n'roll

                if (
                    self.emulation_mode()
                    and self.state.dgtmenu.get_engine_rdisplay()
                    and self.state.artwork_in_use
                    and not self.state.dgtmenu.get_engine_rwindow()
                ):
                    # switch to fullscreen
                    cmd = get_window_command("toggle_fullscreen")
                    if cmd:
                        process = await asyncio.create_subprocess_shell(
                            cmd,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                        )
                        stdout, stderr = await process.communicate()
                        if process.returncode != 0:
                            logger.error(
                                "Command failed with return code %s: %s", process.returncode, stderr.decode()
                            )

                startup_ok = await self.engine.startup(event.options, self.state.rating)
                if startup_ok:
                    # Initialize variant support from new engine settings
                    self._init_variant_from_engine()
                if not startup_ok:
                    logger.error("new engine options missing, reverting to %s", old_file)
                    engine_fallback = True
                    event.options = old_options
                    self.state.engine_file = old_file
                    self.state.artwork_in_use = False
                    await self.engine.quit()
                    if "/mame/" in old_file and self.state.dgtmenu.get_engine_rdisplay():
                        old_file_art = old_file + "_art"
                        my_file = Path(old_file_art)
                        if my_file.is_file():
                            self.state.artwork_in_use = True
                            old_file = old_file_art

                    uci_shell = self.uci_remote_shell if self.remote_engine_mode() and self.uci_remote_shell else self.uci_local_shell

                    self.engine = UciEngine(
                        file=old_file,
                        uci_shell=uci_shell,
                        mame_par=self.calc_engine_mame_par(),
                        loop=self.loop,
                    )
                    await self.engine.open_engine()
                    if not self.engine.loaded_ok():
                        # Help - old engine failed to restart. There is no engine
                        logger.error("no engines started")
                        await DisplayMsg.show(Message.ENGINE_FAIL())
                        await asyncio.sleep(3)
                        sys.exit(-1)
                    startup_ok = await self.engine.startup(event.options, self.state.rating)
                    if not startup_ok:
                        logger.error("old engine options missing; no engines started")
                        await DisplayMsg.show(Message.ENGINE_FAIL())
                        await asyncio.sleep(3)
                        sys.exit(-1)

                if self.online_mode():
                    await self.state.stop_clock()
                    await DisplayMsg.show(Message.ONLINE_LOGIN())
                    # check if login successful (correct server & correct user)
                    (
                        self.login,
                        own_color,
                        self.self.own_user,
                        self.self.opp_user,
                        self.game_time,
                        self.fischer_inc,
                    ) = read_online_user_info()
                    logger.debug("molli online login: %s", self.login)

                    if "ok" not in self.login:
                        # server connection failed: check settings!
                        await DisplayMsg.show(Message.ONLINE_FAILED())
                        await asyncio.sleep(3)
                        engine_fallback = True
                        event.options = dict()
                        old_file = "engines/aarch64/a-stockf"

                        uci_shell = self.uci_remote_shell if self.remote_engine_mode() and self.uci_remote_shell else self.uci_local_shell

                        self.engine = UciEngine(
                            file=old_file,
                            uci_shell=uci_shell,
                            mame_par=self.calc_engine_mame_par(),
                            loop=self.loop,
                        )
                        await self.engine.open_engine()
                        if not self.engine.loaded_ok():
                            # Help - old engine failed to restart. There is no engine
                            logger.error("no engines started")
                            await DisplayMsg.show(Message.ENGINE_FAIL())
                            await asyncio.sleep(3)
                            sys.exit(-1)
                        startup_ok = await self.engine.startup(event.options, self.state.rating)
                        if not startup_ok:
                            logger.error("engine options missing; no engines started")
                            await DisplayMsg.show(Message.ENGINE_FAIL())
                            await asyncio.sleep(3)
                            sys.exit(-1)
                    else:
                        await asyncio.sleep(2)
                elif self.emulation_mode() or self.pgn_mode():
                    # molli for emulation engines we have to reset to starting position
                    await self.stop_search_and_clock()
                    game_fen = self.state.game.board_fen()
                    if self.state.variant == "racingkings":
                        self.state.game = chess.Board("8/8/8/8/8/8/krbnNBRK/qrbnNBRQ w - - 0 1")
                    else:
                        self.state.game = chess.Board()
                    self.state.game.turn = chess.WHITE
                    self.state.reset_variant_board()
                    self.state.play_mode = PlayMode.USER_WHITE
                    if self.pgn_mode():
                        self.engine.option("game_sequence", "forward")
                        await self.engine.send()
                    await self.engine.newgame(self.state.engine_board_copy())
                    self.state.best_sent_depth.reset()
                    self.state.done_computer_fen = None
                    self.state.done_move = self.state.pb_move = chess.Move.null()
                    self.state.searchmoves.reset()
                    self.state.game_declared = False
                    self.state.legal_fens = compute_legal_fens(self.state.game.copy(), self.state.get_variant_board())
                    self.state.last_legal_fens = []
                    self.state.legal_fens_after_cmove = []
                    self.is_out_of_time_already = False
                    starting_fen = RK_STARTING_BOARD_FEN if self.state.variant == "racingkings" else chess.STARTING_BOARD_FEN
                    real_new_game = game_fen != starting_fen
                    msg = self.state.new_game_msg(newgame=real_new_game)
                    await DisplayMsg.show(msg)
                else:
                    # issue #72 - avoid problems by not sending newgame to new engine
                    await self.engine.newgame(self.state.engine_board_copy(), send_ucinewgame=False)
                    # Still notify the display layer about the new game (variant info etc.)
                    await DisplayMsg.show(self.state.new_game_msg(newgame=False))

                await self.engine_mode()

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
                    await DisplayMsg.show(
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
                    await self.state.stop_clock()
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
                        await self.state.stop_clock()
                        text = self.state.dgttranslate.text("N00_oktime")
                        await Observable.fire(
                            Event.SET_TIME_CONTROL(tc_init=self.state.tc_init_last, time_text=text, show_ok=True)
                        )
                        await self.state.stop_clock()
                        await DisplayMsg.show(Message.EXIT_MENU())
                    self.state.flag_last_engine_pgn = False
                    self.state.flag_last_engine_emu = False
                    self.state.tc_init_last = None

                self.state.comment_file = self.get_comment_file()  # for picotutor game comments like Boris & Sargon
                self.state.picotutor.init_comments(self.state.comment_file)

                if self.emulation_mode():
                    await self.set_emulation_tctrl()

                if self.pgn_mode():
                    # read metadata directly from the PGN engine file (headers, move counts, end detection)
                    pgn_options = self.engine.get_pgn_options() or {}
                    pgn_file = pgn_options.get("pgn_game_file")
                    self._load_pgn_engine_games(pgn_file)
                    self._advance_pgn_engine_game()
                    headers = self.shared.get("headers", {}) or {}
                    pgn_problem = headers.get("Problem", "")
                    pgn_fen = headers.get("FEN", "")

                    if "mate in" in pgn_problem or "Mate in" in pgn_problem or pgn_fen != "":
                        await self.set_fen_from_pgn(pgn_fen)
                        self.state.play_mode = (
                            PlayMode.USER_WHITE if self.state.game.turn == chess.WHITE else PlayMode.USER_BLACK
                        )
                        msg = Message.PLAY_MODE(
                            play_mode=self.state.play_mode,
                            play_mode_text=self.state.dgttranslate.text(self.state.play_mode.value),
                        )
                        await DisplayMsg.show(msg)
                        await asyncio.sleep(1)

                if self.online_mode():
                    ModeInfo.set_online_mode(mode=True)
                    logger.debug("online game fen: %s", self.state.game.fen())
                    _start_fen = RK_STARTING_BOARD_FEN if self.state.variant == "racingkings" else chess.STARTING_BOARD_FEN
                    if (not self.state.flag_last_engine_online) or (
                        self.state.game.board_fen() == _start_fen
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

                await self.update_elo_display()

                # new engine might change tutor usage - inform tutor
                await self.state.picotutor.set_mode(self.pgn_mode() or not self.eng_plays())
                # also state of main analyser might have changed
                await self._start_or_stop_analysis_as_needed()
                # end of NEW_ENGINE

            elif isinstance(event, Event.SETUP_POSITION):
                logger.debug("setting up custom fen: %s", event.fen)
                uci960 = event.uci960
                self.state.position_mode = False
                self.reset_setpieces_window_switch()

                if self.state.game.move_stack:
                    if not (self.state.game.is_game_over() or self.state.game_declared):
                        result = GameResult.ABORT
                        self.game_end_event()
                        await DisplayMsg.show(
                            Message.GAME_ENDS(
                                tc_init=self.state.time_control.get_parameters(),
                                result=result,
                                play_mode=self.state.play_mode,
                                game=self.state.game.copy(),
                                mode=self.state.interaction_mode,
                            )
                        )
                self.state.game = chess.Board(event.fen)  # check what uci960 should do here

                # Reset variant boards if active (new position = new state)
                if self.state.variant == "3check" and self.state._threecheck_board is not None:
                    self.state._threecheck_board.set_fen(event.fen)
                    self._update_variant_shared()
                elif self.state.variant == "atomic" and self.state._atomic_board is not None:
                    self.state._atomic_board.set_fen(event.fen)
                elif self.state.variant == "racingkings" and self.state._racingkings_board is not None:
                    self.state._racingkings_board.set_fen(event.fen)

                # see new_game
                await self.stop_search_and_clock()
                if self.engine.has_chess960():
                    self.engine.option("UCI_Chess960", uci960)
                    await self.engine.send()

                await DisplayMsg.show(Message.SHOW_TEXT(text_string="NEW_POSITION_SCAN"))
                await self.engine.newgame(self.state.engine_board_copy())
                self.state.best_sent_depth.reset()
                self.state.done_computer_fen = None
                self.state.done_move = self.state.pb_move = chess.Move.null()
                self.state.legal_fens_after_cmove = []
                self.is_out_of_time_already = False
                self.state.time_control.reset()
                self.state.searchmoves.reset()
                self.state.game_declared = False

                await self.set_picotutor_position(new_game=True)
                await self.set_wait_state(self.state.new_game_msg(newgame=True))
                if self.emulation_mode():
                    if self.state.dgtmenu.get_engine_rdisplay() and self.state.artwork_in_use:
                        # switch windows/tasks
                        cmd = get_window_command("switch_window")
                        if cmd:
                            process = await asyncio.create_subprocess_shell(
                                cmd,
                                stdout=asyncio.subprocess.PIPE,
                                stderr=asyncio.subprocess.PIPE,
                            )
                            stdout, stderr = await process.communicate()
                            if process.returncode != 0:
                                logger.error(
                                    "Command failed with return code %s: %s", process.returncode, stderr.decode()
                                )
                    await DisplayMsg.show(Message.SHOW_TEXT(text_string="NEW_POSITION"))
                    self.engine.is_ready()
                self.state.position_mode = False
                tutor_str = "POSOK"
                msg = Message.PICOTUTOR_MSG(eval_str=tutor_str, game=self.state.game.copy())
                await DisplayMsg.show(msg)
                await asyncio.sleep(1)

            elif isinstance(event, Event.NEW_GAME):
                await self.get_rid_of_engine_move()
                self.state.autoplay_pgn_file = False  # stop auto replay of pgn file if new game started
                last_move_no = self.state.game.fullmove_number
                self.state.takeback_active = False
                self.state.automatic_takeback = False
                self.state.reset_auto = False
                self.state.flag_startup = False
                self.state.flag_pgn_game_over = False
                
                # Check if game already ended BEFORE resetting the game ending status
                # This prevents duplicate PGN saves when user resets board after game ends
                game_already_ended = ModeInfo.get_game_ending() != "*"
                
                ModeInfo.set_game_ending(result="*")  # initialize game result for game saving status
                self.state.position_mode = False
                self.reset_setpieces_window_switch()
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
                                await self.state.stop_clock()
                                self.state.best_move_posted = True
                                # @todo 8/8/R6P/1R6/7k/2B2K1p/8/8 and sliding Ra6 over a5 to a4
                                # handle this in correct way!!
                                self.state.game_declared = True
                                self.state.stop_fen_timer()
                                self.state.legal_fens_after_cmove = []

                        # Only send ABORT message if game hasn't already ended
                        if not game_already_ended:
                            result = GameResult.ABORT
                            self.game_end_event()
                            await DisplayMsg.show(
                                Message.GAME_ENDS(
                                    tc_init=self.state.time_control.get_parameters(),
                                    result=result,
                                    play_mode=self.state.play_mode,
                                    game=self.state.game.copy(),
                                    mode=self.state.interaction_mode,
                                )
                            )
                            await asyncio.sleep(0.3)

                    if self.state.variant == "racingkings":
                        self.state.game = chess.Board("8/8/8/8/8/8/krbnNBRK/qrbnNBRQ w - - 0 1")
                    else:
                        self.state.game = chess.Board()
                    self.state.game.turn = chess.WHITE

                    if uci960:
                        self.state.game.set_chess960_pos(event.pos960)

                    self.state.reset_variant_board()
                    self._update_variant_shared()

                    if self.state.play_mode != PlayMode.USER_WHITE:
                        self.state.play_mode = PlayMode.USER_WHITE
                        msg = Message.PLAY_MODE(
                            play_mode=self.state.play_mode,
                            play_mode_text=self.state.dgttranslate.text(str(self.state.play_mode.value)),
                        )
                        await DisplayMsg.show(msg)
                    await self.stop_search_and_clock()

                    # see setup_position
                    if self.engine.has_chess960():
                        self.engine.option("UCI_Chess960", uci960)
                        try:
                            await self.engine.send()
                        except Exception as exc:
                            logger.warning("engine.send() failed during new game setup: %s", exc)

                    if self.online_mode():
                        await DisplayMsg.show(Message.SEEKING())
                        self.state.seeking_flag = True
                        self.state.stop_fen_timer()
                        ModeInfo.set_online_mode(mode=True)
                    else:
                        ModeInfo.set_online_mode(mode=False)

                    if self.pgn_mode():
                        self._advance_pgn_engine_game()
                    await self.engine.newgame(self.state.engine_board_copy())

                    self.state.best_sent_depth.reset()
                    self.state.done_computer_fen = None
                    self.state.done_move = self.state.pb_move = chess.Move.null()
                    self.state.time_control.reset()
                    self.state.best_move_posted = False
                    self.state.searchmoves.reset()
                    self.state.game_declared = False
                    await self.update_elo_display()

                    if self.online_mode():
                        await asyncio.sleep(0.5)
                        (
                            self.login,
                            own_color,
                            self.own_user,
                            self.opp_user,
                            self.game_time,
                            self.fischer_inc,
                        ) = read_online_user_info()
                        if "no_user" in self.own_user and not self.login == "ok":
                            # user login failed check login settings!!!
                            await DisplayMsg.show(Message.ONLINE_USER_FAILED())
                            await asyncio.sleep(3)
                        elif "no_player" in self.opp_user:
                            # no opponent found start new game or engine again!!!
                            await DisplayMsg.show(Message.ONLINE_NO_OPPONENT())
                            await asyncio.sleep(3)
                        else:
                            await DisplayMsg.show(Message.ONLINE_NAMES(own_user=self.own_user, opp_user=self.opp_user))
                            await asyncio.sleep(3)
                        self.state.seeking_flag = False
                        self.state.best_move_displayed = None

                    self.state.legal_fens = compute_legal_fens(self.state.game.copy(), self.state.get_variant_board())
                    self.state.last_legal_fens = []
                    self.state.legal_fens_after_cmove = []
                    self.is_out_of_time_already = False
                    if self.pgn_mode():
                        if self.state.max_guess > 0:
                            self.state.max_guess_white = self.state.max_guess
                            self.state.max_guess_black = 0
                        headers = self.shared.get("headers", {}) or {}
                        pgn_fen = headers.get("FEN", "")
                        pgn_problem = headers.get("Problem", "")
                        if "mate in" in pgn_problem or "Mate in" in pgn_problem or pgn_fen != "":
                            await self.set_fen_from_pgn(pgn_fen)
                    if self.state.interaction_mode == Mode.PGNREPLAY:
                        # V4 built-in pgn replay done - no game to replay
                        self.state.interaction_mode = Mode.NORMAL  # switch to NORMAL plyaing mode
                        await self.engine_mode()  # see INTERACTION_MODE handling
                    await self.set_wait_state(self.state.new_game_msg(newgame=newgame))
                    if "no_player" not in self.opp_user and "no_user" not in self.own_user:
                        await self.switch_online()
                    if self.picotutor_mode():
                        await self.state.picotutor.newgame()
                        if not self.state.flag_startup:
                            if self.state.play_mode == PlayMode.USER_BLACK:
                                await self.state.picotutor.set_user_color(
                                    chess.BLACK, self.pgn_mode() or not self.eng_plays()
                                )
                            else:
                                await self.state.picotutor.set_user_color(
                                    chess.WHITE, self.pgn_mode() or not self.eng_plays()
                                )
                else:
                    if self.online_mode():
                        logger.debug("starting a new game with code: %s", event.pos960)
                        uci960 = event.pos960 != 518
                        await self.state.stop_clock()

                        self.state.game.turn = chess.WHITE

                        if uci960:
                            self.state.game.set_chess960_pos(event.pos960)

                        if self.state.play_mode != PlayMode.USER_WHITE:
                            self.state.play_mode = PlayMode.USER_WHITE
                            msg = Message.PLAY_MODE(
                                play_mode=self.state.play_mode,
                                play_mode_text=self.state.dgttranslate.text(str(self.state.play_mode.value)),
                            )
                            await DisplayMsg.show(msg)

                        # see setup_position
                        await self.stop_search_and_clock()
                        self.state.stop_fen_timer()

                        if self.engine.has_chess960():
                            self.engine.option("UCI_Chess960", uci960)
                            await self.engine.send()

                        self.state.time_control.reset()
                        self.state.searchmoves.reset()

                        await DisplayMsg.show(Message.SEEKING())
                        self.state.seeking_flag = True

                        await self.engine.newgame(self.state.engine_board_copy())

                        (
                            self.login,
                            own_color,
                            self.own_user,
                            self.opp_user,
                            self.game_time,
                            self.fischer_inc,
                        ) = read_online_user_info()
                        if "no_user" in self.own_user:
                            # user login failed check login settings!!!
                            await DisplayMsg.show(Message.ONLINE_USER_FAILED())
                            await asyncio.sleep(3)
                        elif "no_player" in self.opp_user:
                            # no opponent found start new game & search!!!
                            await DisplayMsg.show(Message.ONLINE_NO_OPPONENT())
                            await asyncio.sleep(3)
                        else:
                            await DisplayMsg.show(Message.ONLINE_NAMES(own_user=self.own_user, opp_user=self.opp_user))
                            await asyncio.sleep(1)
                        self.state.best_sent_depth.reset()
                        self.state.seeking_flag = False
                        self.state.best_move_displayed = None
                        self.state.takeback_active = False
                        self.state.automatic_takeback = False
                        self.state.done_computer_fen = None
                        self.state.done_move = self.state.pb_move = chess.Move.null()
                        self.state.legal_fens = compute_legal_fens(self.state.game.copy(), self.state.get_variant_board())
                        self.state.last_legal_fens = []
                        self.state.legal_fens_after_cmove = []
                        self.is_out_of_time_already = False
                        self.state.game_declared = False
                        await self.set_wait_state(
                            self.state.new_game_msg(newgame=newgame),
                        )
                        if "no_player" not in self.opp_user and "no_user" not in self.own_user:
                            await self.switch_online()
                    else:
                        logger.debug("no need to start a new game")
                        if self.pgn_mode():
                            self.state.takeback_active = False
                            self.state.automatic_takeback = False
                            headers = self.shared.get("headers", {}) or {}
                            pgn_fen = headers.get("FEN", "")
                            pgn_problem = headers.get("Problem", "")
                            if "mate in" in pgn_problem or "Mate in" in pgn_problem or pgn_fen != "":
                                await self.set_fen_from_pgn(pgn_fen)
                                await self.set_wait_state(
                                    self.state.new_game_msg(newgame=newgame),
                                )
                            else:
                                await DisplayMsg.show(
                                    self.state.new_game_msg(newgame=newgame)
                                )
                        else:
                            await DisplayMsg.show(self.state.new_game_msg(newgame=newgame))

                if self.picotutor_mode():
                    await self.state.picotutor.newgame()
                    if not self.state.flag_startup:
                        if self.state.play_mode == PlayMode.USER_BLACK:
                            await self.state.picotutor.set_user_color(
                                chess.BLACK, self.pgn_mode() or not self.eng_plays()
                            )
                        else:
                            await self.state.picotutor.set_user_color(
                                chess.WHITE, self.pgn_mode() or not self.eng_plays()
                            )

                if self.state.interaction_mode != Mode.REMOTE and not self.online_mode():
                    if self.state.dgtmenu.get_enginename():
                        await asyncio.sleep(0.7)  # give time for ABORT message
                        msg = Message.ENGINE_NAME(engine_name=self.state.engine_text)
                        await DisplayMsg.show(msg)
                    if self.pgn_mode():
                        headers = self.shared.get("headers", {}) or {}
                        pgn_white = headers.get("White", "")
                        pgn_black = headers.get("Black", "")
                        pgn_game_name = headers.get("Event", "")
                        pgn_problem = headers.get("Problem", "")
                        pgn_result = headers.get("Result", "")
                        await asyncio.sleep(1)

                        update_speed = 1.0
                        if not pgn_white:
                            pgn_white = "????"
                        await DisplayMsg.show(Message.SHOW_TEXT(text_string=pgn_white))
                        await asyncio.sleep(update_speed)

                        await DisplayMsg.show(Message.SHOW_TEXT(text_string="versus"))
                        await asyncio.sleep(update_speed)

                        if not pgn_black:
                            pgn_black = "????"
                        await DisplayMsg.show(Message.SHOW_TEXT(text_string=pgn_black))
                        await asyncio.sleep(update_speed)

                        if pgn_result:
                            await DisplayMsg.show(Message.SHOW_TEXT(text_string=pgn_result))
                        await asyncio.sleep(update_speed)
                        if "mate in" in pgn_problem or "Mate in" in pgn_problem:
                            await DisplayMsg.show(Message.SHOW_TEXT(text_string=pgn_problem))
                        else:
                            await DisplayMsg.show(Message.SHOW_TEXT(text_string=pgn_game_name))
                        await asyncio.sleep(update_speed)

                        # reset pgn guess counters
                        if last_move_no > 1:
                            self.state.no_guess_black = 1
                            self.state.no_guess_white = 1
                        else:
                            log_pgn(self.state)
                            if self.state.max_guess_white > 0:
                                if self.state.no_guess_white > self.state.max_guess_white:
                                    self.state.last_legal_fens = []
                                    await self.get_next_pgn_move()

            elif isinstance(event, Event.PAUSE_RESUME):
                if self.pgn_mode():
                    self.engine.pause_pgn_audio()
                else:
                    if self.engine.is_thinking():
                        self.engine.force_move()
                    elif (
                        self.eng_plays() and self.state.is_not_user_turn() and self.state.done_computer_fen is not None
                    ):
                        # e-board: engine move still pending on the board; allow user to request another move
                        # (when go() sees searchlist=True it removes already-played moves from the root list)
                        if not self.state.check_game_state():
                            # picotuter should be in sync as takeback already was done
                            await self.think(
                                Message.ALTERNATIVE_MOVE(game=self.state.game.copy(), play_mode=self.state.play_mode),
                                searchlist=True,
                            )
                    elif self.state.interaction_mode == Mode.PGNREPLAY:
                        # Built in PGN Replay mode - toggle autoplay on or off
                        if self.state.autoplay_pgn_file:
                            self.state.autoplay_pgn_file = False  # stop auto replay of pgn
                        else:
                            # if we are not already waiting for an autoplay move make the first move
                            if self.can_do_next_pgn_replay_move():
                                # avoid sending GAME_ENDS when autoplay is started
                                auto_move = await self.autoplay_pgnreplay_move(allow_game_ends=False)
                            else:
                                auto_move = None
                            if auto_move:
                                self.state.autoplay_pgn_file = True  # start auto replay of pgn
                            else:
                                msg = Message.SHOW_TEXT(text_string="no move")
                                await DisplayMsg.show(msg)
                    elif not self.state.done_computer_fen:
                        if self.state.time_control.internal_running():
                            await self.state.stop_clock()
                        else:
                            await self.state.start_clock()
                    else:
                        logger.debug("best move displayed, dont start/stop clock")

            elif isinstance(event, Event.ALTERNATIVE_MOVE):
                if self.state.done_computer_fen and not self.emulation_mode():
                    self.state.done_computer_fen = None
                    self.state.done_move = chess.Move.null()
                    if self.eng_plays():
                        # @todo handle Mode.REMOTE too
                        if self.state.time_control.mode == TimeMode.FIXED:
                            self.state.time_control.reset()
                        # set computer to move - in case the user just changed the engine
                        self.state.play_mode = (
                            PlayMode.USER_WHITE if self.state.game.turn == chess.BLACK else PlayMode.USER_BLACK
                        )
                        if not self.state.check_game_state():
                            if self.picotutor_mode():
                                await self.state.picotutor.pop_last_move(self.state.game)
                            # Allow any late bestmove/info lines from the previous search to drain.
                            await asyncio.sleep(0.2)
                            await self.think(
                                Message.ALTERNATIVE_MOVE(game=self.state.game.copy(), play_mode=self.state.play_mode),
                                searchlist=True,
                            )
                    else:
                        logger.warning("wrong function call [alternative]! mode: %s", self.state.interaction_mode)

            elif isinstance(event, Event.SWITCH_SIDES):
                self.state.best_sent_depth.reset()  # safest to drop optimisation when switching sides
                await self.get_rid_of_engine_move()
                self.state.flag_startup = False
                await DisplayMsg.show(Message.EXIT_MENU())

                if self.state.interaction_mode == Mode.PONDER:
                    # molli: allow switching sides in flexble ponder mode
                    fen = self.state.get_board_fen()

                    if self.state.game.turn == chess.WHITE:
                        fen += " b KQkq - 0 1"
                    else:
                        fen += " w KQkq - 0 1"
                    # ask python-chess to correct the castling string
                    bit_board = chess.Board(fen)
                    bit_board.set_fen(bit_board.fen())
                    if bit_board.is_valid():
                        self.state.game = chess.Board(bit_board.fen())
                        # Sync variant boards with new position
                        if self.state.variant == "3check" and self.state._threecheck_board is not None:
                            self.state._threecheck_board.set_fen(bit_board.fen())
                        elif self.state.variant == "atomic" and self.state._atomic_board is not None:
                            self.state._atomic_board.set_fen(bit_board.fen())
                        #  await self.stop_search_and_clock()
                        await self.engine.newgame(self.state.engine_board_copy())
                        self.state.best_sent_depth.reset()
                        self.state.done_computer_fen = None
                        self.state.done_move = self.state.pb_move = chess.Move.null()
                        self.state.time_control.reset()
                        self.state.searchmoves.reset()
                        self.state.game_declared = False
                        self.state.legal_fens = compute_legal_fens(self.state.game.copy(), self.state.get_variant_board())
                        self.state.legal_fens_after_cmove = []
                        self.state.last_legal_fens = []
                        # switching sides in PONDER (ANALYSIS in menu, not a playing mode)
                        self.state.play_mode = (
                            PlayMode.USER_WHITE if self.state.game.turn == chess.WHITE else PlayMode.USER_BLACK
                        )
                        msg = Message.PLAY_MODE(
                            play_mode=self.state.play_mode,
                            play_mode_text=self.state.dgttranslate.text(self.state.play_mode.value),
                        )
                        await DisplayMsg.show(msg)
                        await self.set_picotutor_position(new_game=True)  # issue #78 inform tutor
                        await self.analyse()  # #78 this should be last when all is done
                    else:
                        logger.debug("illegal fen %s", fen)
                        await DisplayMsg.show(Message.WRONG_FEN())
                        await DisplayMsg.show(Message.EXIT_MENU())

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
                    # switching sides in engine plays modes
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
                            await self.state.picotutor.set_user_color(
                                chess.BLACK, self.pgn_mode() or not self.eng_plays()
                            )
                        else:
                            await self.state.picotutor.set_user_color(
                                chess.WHITE, self.pgn_mode() or not self.eng_plays()
                            )
                        if self.state.best_move_posted:
                            self.state.best_move_posted = False
                            await self.state.picotutor.pop_last_move(self.state.game)

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
                        await self.think(msg)  # PLAY_MODE
                    else:
                        await DisplayMsg.show(msg)  # PLAY_MODE
                        await self.state.start_clock()
                        self.state.legal_fens = compute_legal_fens(self.state.game.copy(), self.state.get_variant_board())

                    if self.state.best_move_displayed:
                        await DisplayMsg.show(Message.SWITCH_SIDES(game=self.state.game.copy(), move=move))

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
                        await DisplayMsg.show(msg)
                    else:
                        cond1 = self.state.game.turn == chess.WHITE and self.state.play_mode == PlayMode.USER_BLACK
                        cond2 = self.state.game.turn == chess.BLACK and self.state.play_mode == PlayMode.USER_WHITE
                        if cond1 or cond2:
                            self.state.time_control.reset_start_time()
                            await self.think(msg)
                        else:
                            await DisplayMsg.show(msg)
                            await self.state.start_clock()
                            self.state.legal_fens = compute_legal_fens(self.state.game.copy(), self.state.get_variant_board())

                    if self.state.best_move_displayed:
                        await DisplayMsg.show(Message.SWITCH_SIDES(game=self.state.game.copy(), move=move))

            elif isinstance(event, Event.DRAWRESIGN):
                if not self.state.game_declared:  # in case user leaves kings in place while moving other pieces
                    await self.stop_search_and_clock()
                    l_result = ""
                    if event.result == GameResult.DRAW:
                        l_result = "1/2-1/2"
                    elif event.result in (GameResult.WIN_WHITE, GameResult.WIN_BLACK):
                        l_result = "1-0" if event.result == GameResult.WIN_WHITE else "0-1"
                    elif event.result == GameResult.THREE_CHECK_WHITE:
                        l_result = "1-0"
                    elif event.result == GameResult.THREE_CHECK_BLACK:
                        l_result = "0-1"
                    elif event.result == GameResult.KOTH_WHITE:
                        l_result = "1-0"
                    elif event.result == GameResult.KOTH_BLACK:
                        l_result = "0-1"
                    elif event.result == GameResult.ATOMIC_WHITE:
                        l_result = "1-0"
                    elif event.result == GameResult.ATOMIC_BLACK:
                        l_result = "0-1"
                    elif event.result == GameResult.RK_WHITE:
                        l_result = "1-0"
                    elif event.result == GameResult.RK_BLACK:
                        l_result = "0-1"
                    elif event.result == GameResult.ANTICHESS_WHITE:
                        l_result = "1-0"
                    elif event.result == GameResult.ANTICHESS_BLACK:
                        l_result = "0-1"
                    ModeInfo.set_game_ending(result=l_result)
                    self.game_end_event()
                    await DisplayMsg.show(
                        Message.GAME_ENDS(
                            tc_init=self.state.time_control.get_parameters(),
                            result=event.result,
                            play_mode=self.state.play_mode,
                            game=self.state.game.copy(),
                            mode=self.state.interaction_mode,
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
                        await DisplayMsg.show(
                            Message.COMPUTER_MOVE(
                                move=event.move,
                                ponder=chess.Move.null(),
                                game=self.state.game_copy(),
                                wait=False,
                                is_user_move=False,
                            )
                        )
                        game_copy = self.state.game.copy()
                        game_copy.push(event.move)
                        self._prepare_engine_move(game_copy, event.move)
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
                self.state.engine_move_was_book = bool(event.inbook) if self.eng_plays() else False

                if self.state.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.TRAINING):
                    if self.state.is_not_user_turn():
                        # clock must be stopped BEFORE the "book_move" event cause SetNRun resets the clock display
                        await self.state.stop_clock()
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
                            self.game_end_event()
                            if self.online_mode():
                                winner = ""
                                result_str = ""
                                await asyncio.sleep(0.5)
                                result_str, winner = read_online_result()
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
                                        await DisplayMsg.show(Message.LOST_ON_TIME())
                                        await asyncio.sleep(2)
                                        await DisplayMsg.show(
                                            Message.GAME_ENDS(
                                                tc_init=self.state.time_control.get_parameters(),
                                                result=gameresult_tmp2,
                                                play_mode=self.state.play_mode,
                                                game=game_msg,
                                                mode=self.state.interaction_mode,
                                            )
                                        )
                                    else:
                                        await DisplayMsg.show(
                                            Message.GAME_ENDS(
                                                tc_init=self.state.time_control.get_parameters(),
                                                result=gameresult_tmp,
                                                play_mode=self.state.play_mode,
                                                game=game_msg,
                                                mode=self.state.interaction_mode,
                                            )
                                        )
                                        await asyncio.sleep(2)
                                        await DisplayMsg.show(
                                            Message.GAME_ENDS(
                                                tc_init=self.state.time_control.get_parameters(),
                                                result=gameresult_tmp2,
                                                play_mode=self.state.play_mode,
                                                game=game_msg,
                                                mode=self.state.interaction_mode,
                                            )
                                        )
                                else:
                                    if gameresult_tmp == GameResult.ABORT and gameresult_tmp2:
                                        await DisplayMsg.show(
                                            Message.GAME_ENDS(
                                                tc_init=self.state.time_control.get_parameters(),
                                                result=gameresult_tmp2,
                                                play_mode=self.state.play_mode,
                                                game=game_msg,
                                                mode=self.state.interaction_mode,
                                            )
                                        )
                                    else:
                                        await DisplayMsg.show(
                                            Message.GAME_ENDS(
                                                tc_init=self.state.time_control.get_parameters(),
                                                result=gameresult_tmp,
                                                play_mode=self.state.play_mode,
                                                game=game_msg,
                                                mode=self.state.interaction_mode,
                                            )
                                        )
                            else:
                                if self.pgn_mode():
                                    # molli: check if last move of pgn game file
                                    await self.stop_search_and_clock()
                                    log_pgn(self.state)
                                    # in Pico V4 we cannot detect end of pgn game by depth
                                    # if max_guess uci option is zero - this must be end of game
                                    if self.state.max_guess == 0 or (
                                        self.state.pgn_engine_total_halfmoves is not None
                                        and len(self.state.game.move_stack) >= self.state.pgn_engine_total_halfmoves
                                    ):
                                        logger.debug("molli pgn: PGN END")
                                        pgn_result = self.state.pgn_engine_result or "*"
                                        await DisplayMsg.show(Message.PGN_GAME_END(result=pgn_result))
                                    elif self.state.pgn_book_test:
                                        l_game_copy = self.state.game.copy()
                                        l_game_copy.pop()
                                        l_found = False
                                        if self.bookreader:
                                            l_found = self.state.searchmoves.check_book(self.bookreader, l_game_copy)

                                        if not l_found:
                                            await DisplayMsg.show(Message.PGN_GAME_END(result="*"))
                                        else:
                                            logger.debug("molli pgn: Wrong Move! Try Again!")
                                            # increase pgn guess counters
                                            if self.state.max_guess_black > 0 and self.state.game.turn == chess.WHITE:
                                                self.state.no_guess_black = self.state.no_guess_black + 1
                                                if self.state.no_guess_black > self.state.max_guess_black:
                                                    await DisplayMsg.show(Message.MOVE_WRONG())
                                                else:
                                                    await DisplayMsg.show(Message.MOVE_RETRY())
                                            elif self.state.max_guess_white > 0 and self.state.game.turn == chess.BLACK:
                                                self.state.no_guess_white = self.state.no_guess_white + 1
                                                if self.state.no_guess_white > self.state.max_guess_white:
                                                    await DisplayMsg.show(Message.MOVE_WRONG())
                                                else:
                                                    await DisplayMsg.show(Message.MOVE_RETRY())
                                            else:
                                                # user move wrong in pgn display mode only
                                                await DisplayMsg.show(Message.MOVE_RETRY())
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
                                                await DisplayMsg.show(Message.MOVE_WRONG())
                                            else:
                                                await DisplayMsg.show(Message.MOVE_RETRY())
                                        elif self.state.max_guess_white > 0 and self.state.game.turn == chess.BLACK:
                                            self.state.no_guess_white = self.state.no_guess_white + 1
                                            if self.state.no_guess_white > self.state.max_guess_white:
                                                await DisplayMsg.show(Message.MOVE_WRONG())
                                            else:
                                                await DisplayMsg.show(Message.MOVE_RETRY())
                                        else:
                                            # user move wrong in pgn display mode only
                                            await DisplayMsg.show(Message.MOVE_RETRY())

                                        if self.board_type == dgt.util.EBoard.NOEBOARD:
                                            await Observable.fire(Event.TAKE_BACK(take_back="PGN_TAKEBACK"))
                                        else:
                                            self.state.takeback_active = True
                                            self.state.automatic_takeback = True
                                            await self.set_wait_state(
                                                Message.TAKE_BACK(game=self.state.game.copy())
                                            )  # automatic takeback mode
                                else:
                                    #  issue #14 0000 bestmove - not pgn replay - reload engine
                                    result_str = self.state.pending_engine_result
                                    self.state.pending_engine_result = None  # discard cached fallback once consumed
                                    if not result_str:
                                        # Same logic as above: ping every engine after an illegal move
                                        # so we can distinguish a resignation from a crashed process.
                                        vb = self.state.get_variant_board()
                                        result_str = await self.engine.handle_bestmove_0000(
                                            self.state.game.copy(), variant_board=vb.copy() if vb else None
                                        )
                                    result = game_result_from_header(result_str)  # "*" maps to ABORT
                                    if result != GameResult.ABORT:
                                        await DisplayMsg.show(
                                            Message.GAME_ENDS(
                                                tc_init=self.state.time_control.get_parameters(),
                                                result=result,
                                                play_mode=self.state.play_mode,
                                                game=self.state.game.copy(),
                                                mode=self.state.interaction_mode,
                                            )
                                        )
                                    else:
                                        logger.error("engine crashed - game has not ended")
                                        await DisplayMsg.show(Message.ENGINE_FAIL())
                                        await asyncio.sleep(0.5)
                                        # mimic the automatic-takeback logic used for mame blunders (see ~2360)
                                        # so the user can try a different move or pick another engine
                                        if self.board_type == dgt.util.EBoard.NOEBOARD:
                                            await Observable.fire(Event.TAKE_BACK(take_back="ENGINE_FAIL"))
                                        else:
                                            self.state.takeback_active = True
                                            self.state.automatic_takeback = True
                                            await self.set_wait_state(Message.TAKE_BACK(game=self.state.game.copy()))
                                        loaded_ok = await self.engine.reopen_engine()
                                        if loaded_ok:
                                            level_index = self.state.dgtmenu.get_engine_level_index()
                                            await DisplayMsg.show(
                                                Message.ENGINE_STARTUP(
                                                    installed_engines=EngineProvider.installed_engines,
                                                    file=self.state.engine_file,
                                                    level_index=level_index,
                                                    has_960=self.engine.has_chess960(),
                                                    has_ponder=self.engine.has_ponder(),
                                                )
                                            )
                                            await asyncio.sleep(0.5)
                                            await DisplayMsg.show(Message.ENGINE_SETUP())
                                        else:
                                            logger.error("engine re-load failed")
                                            await DisplayMsg.show(Message.ENGINE_FAIL())
                            await asyncio.sleep(0.5)
                        else:
                            # normal computer move
                            if event.inbook:
                                await DisplayMsg.show(Message.BOOK_MOVE())
                            self.state.searchmoves.exclude(event.move)

                            if self.online_mode() or self.emulation_mode():
                                self.state.start_time_cmove_done = time.time()  # time should alraedy run for the player
                            await DisplayMsg.show(Message.EXIT_MENU())
                            await DisplayMsg.show(
                                Message.COMPUTER_MOVE(
                                    move=event.move,
                                    ponder=event.ponder,
                                    game=self.state.game_copy(),
                                    wait=event.inbook,
                                    is_user_move=False,
                                )
                            )
                            game_copy = self.state.game.copy()
                            game_copy.push(event.move)

                            if self.picotutor_mode():
                                if self.pgn_mode():
                                    t_color = self.state.picotutor.get_user_color()
                                    if t_color == chess.BLACK:
                                        await self.state.picotutor.set_user_color(
                                            chess.WHITE, self.pgn_mode() or not self.eng_plays()
                                        )
                                    else:
                                        await self.state.picotutor.set_user_color(
                                            chess.BLACK, self.pgn_mode() or not self.eng_plays()
                                        )

                                valid = await self.state.picotutor.push_move(event.move, game_copy)
                                if not valid:
                                    await self.set_picotutor_position()
                            self._prepare_engine_move(
                                game_copy,
                                event.move,
                                event.ponder if event.ponder and not event.inbook else chess.Move.null(),
                            )

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
                                await DisplayMsg.show(Message.COMPUTER_MOVE_DONE())

                                self.state.best_move_posted = False
                                self.state.push_move(self.state.done_move)  # computer move without human assistance
                                self._update_variant_shared()
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
                                        self.game_end_event()
                                        await DisplayMsg.show(game_end)
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
                                        await DisplayMsg.show(msg)

                                    if self.state.game.fullmove_number < 1:
                                        ModeInfo.reset_opening()
                                    if self.picotutor_mode() and self.state.dgtmenu.get_picoexplorer():
                                        op_eco, op_name, op_moves, op_in_book = self.state.picotutor.get_opening()
                                        if op_in_book and op_name:
                                            logger.debug("opening book set to %s", op_name)
                                            ModeInfo.set_opening(self.state.book_in_use, str(op_name), op_eco)
                                            await DisplayMsg.show(Message.SHOW_TEXT(text_string=op_name))
                                            await asyncio.sleep(0.7)

                                    if not self.online_mode() or self.state.game.fullmove_number > 1:
                                        await self.state.start_clock()
                                    else:
                                        await DisplayMsg.show(Message.EXIT_MENU())  # show clock
                                        end_time_cmove_done = 0

                                    self.state.legal_fens = compute_legal_fens(self.state.game.copy(), self.state.get_variant_board())

                                    if self.pgn_mode():
                                        log_pgn(self.state)
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
                    # Use variant board for legality check (atomic has different legal moves)
                    pv_check_board = self.state.get_move_check_board()
                    if pv_check_board.is_legal(event.pv[0]):
                        # only pv received from event
                        await DisplayMsg.show(
                            Message.NEW_PV(
                                pv=event.pv,
                                mode=self.state.interaction_mode,
                                game=self.state.game_copy(),
                            )
                        )
                    else:
                        self.state.best_sent_depth.reset()
                        logger.info(
                            "illegal move can not be displayed. move: %s fen: %s",
                            event.pv[0],
                            self.state.get_fen(),
                        )
                        logger.info("engine status: t:%s p:%s", self.engine.is_thinking(), self.engine.is_pondering())

            elif isinstance(event, Event.NEW_SCORE):
                if event.score:
                    if event.score == 99999 or event.score == -99999:
                        self.state.flag_pgn_game_over = True  # molli pgn mode: signal that pgn is at end
                    else:
                        self.state.flag_pgn_game_over = False

                    # only score and mate received from event, turn is missing
                    await DisplayMsg.show(
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
                    await DisplayMsg.show(Message.NEW_DEPTH(depth=event.depth))

            elif isinstance(event, Event.START_SEARCH):
                await DisplayMsg.show(Message.SEARCH_STARTED())

            elif isinstance(event, Event.STOP_SEARCH):
                await DisplayMsg.show(Message.SEARCH_STOPPED())

            elif isinstance(event, Event.SET_INTERACTION_MODE):
                self.state.best_sent_depth.reset()  # dont use optimisation when switching modes
                if self.eng_plays() and event.mode not in (Mode.NORMAL, Mode.BRAIN, Mode.TRAINING):
                    # things to do when we change from a playing mode to non-playing
                    await self.get_rid_of_engine_move()  # force/get-rid of engine move
                if not self.eng_plays() and event.mode in (Mode.NORMAL, Mode.BRAIN, Mode.TRAINING):
                    # things to do i we change from a non-playing mode to a playing mode
                    self.state.autoplay_pgn_file = False  # stop possible auto replay of pgn file
                if (
                    event.mode not in (Mode.NORMAL, Mode.REMOTE, Mode.TRAINING) and self.state.done_computer_fen
                ):  # @todo check why still needed
                    self.state.dgtmenu.set_mode(self.state.interaction_mode)  # undo the button4 stuff
                    logger.warning("mode cant be changed to a pondering mode as long as a move is displayed")
                    mode_text = self.state.dgttranslate.text("Y10_errormode")
                    msg = Message.INTERACTION_MODE(mode=self.state.interaction_mode, mode_text=mode_text, show_ok=False)
                    await DisplayMsg.show(msg)
                else:
                    if event.mode == Mode.PONDER:
                        self.state.newgame_happened = False
                    await self.stop_search_and_clock()
                    if event.mode == Mode.PGNREPLAY:
                        file_name_only = "last_game.pgn"
                        await DisplayMsg.show(Message.READ_GAME(pgn_filename=file_name_only))
                        await self.read_pgn_file(file_name_only)
                        await self._start_or_stop_analysis_as_needed()
                    else:
                        self.state.interaction_mode = event.mode
                        await self.engine_mode()
                        msg = Message.INTERACTION_MODE(
                            mode=event.mode, mode_text=event.mode_text, show_ok=event.show_ok
                        )
                        await self.set_wait_state(msg)  # dont clear searchmoves here

            elif isinstance(event, Event.SET_OPENING_BOOK):
                book_file = event.book["file"]
                logger.debug("changing opening book [%s]", book_file)
                try:
                    bookreader = chess.polyglot.open_reader(book_file)
                except OSError as exc:
                    logger.warning("failed to open book '%s': %s", book_file, exc)
                    return
                write_picochess_ini("book", book_file)
                self.bookreader = bookreader
                await DisplayMsg.show(Message.OPENING_BOOK(book_text=event.book_text, show_ok=event.show_ok))
                self.state.book_in_use = book_file
                self.state.stop_fen_timer()

            elif isinstance(event, Event.SHOW_ENGINENAME):
                await DisplayMsg.show(Message.SHOW_ENGINENAME(show_enginename=event.show_enginename))

            elif isinstance(event, Event.SAVE_GAME):
                if event.pgn_filename:
                    await self.state.stop_clock()
                    await DisplayMsg.show(
                        Message.SAVE_GAME(
                            tc_init=self.state.time_control.get_parameters(),
                            play_mode=self.state.play_mode,
                            game=self.state.game.copy(),
                            pgn_filename=event.pgn_filename,
                            mode=self.state.interaction_mode,
                        )
                    )

            elif isinstance(event, Event.READ_GAME):
                if event.pgn_filename:
                    await DisplayMsg.show(Message.READ_GAME(pgn_filename=event.pgn_filename))
                    await self.read_pgn_file(event.pgn_filename)
                    await self._start_or_stop_analysis_as_needed()

            elif isinstance(event, Event.CONTLAST):
                await DisplayMsg.show(Message.CONTLAST(contlast=event.contlast))

            elif isinstance(event, Event.ALTMOVES):
                await DisplayMsg.show(Message.ALTMOVES(altmoves=event.altmoves))

            elif isinstance(event, Event.PICOWATCHER):
                self.state.dgtmenu.menu_picotutor_picowatcher = event.picowatcher
                self.state.dgtmenu.res_picotutor_picowatcher = event.picowatcher
                write_picochess_ini("tutor-watcher", event.picowatcher)
                self.state.best_sent_depth.reset()
                await self.state.picotutor.set_status(
                    self.state.dgtmenu.get_picowatcher(),
                    self.state.dgtmenu.get_picocoach(),
                    self.state.dgtmenu.get_picoexplorer(),
                    self.state.dgtmenu.get_picocomment(),
                )
                if event.picowatcher:
                    self.state.flag_picotutor = True
                    # @ todo - why do we need to re-set position in tutor?
                    await self.set_picotutor_position()
                elif self.state.dgtmenu.get_picocoach() != PicoCoach.COACH_OFF:
                    self.state.flag_picotutor = True
                elif self.state.dgtmenu.get_picoexplorer():
                    self.state.flag_picotutor = True
                else:
                    self.state.flag_picotutor = False

                if self.state.flag_picotutor:
                    await self.state.picotutor.set_mode(self.pgn_mode() or not self.eng_plays())
                await DisplayMsg.show(Message.PICOWATCHER(picowatcher=event.picowatcher))

            elif isinstance(event, Event.PICOCOACH):
                coach_request = event.picocoach
                if coach_request in (PicoCoach.COACH_OFF, PicoCoach.COACH_ON, PicoCoach.COACH_LIFT):
                    if coach_request == PicoCoach.COACH_OFF:
                        self.state.dgtmenu.menu_picotutor_picocoach = PicoCoach.COACH_OFF
                        self.state.dgtmenu.res_picotutor_picocoach = PicoCoach.COACH_OFF
                        write_picochess_ini("tutor-coach", "off")
                    elif coach_request == PicoCoach.COACH_ON:
                        self.state.dgtmenu.menu_picotutor_picocoach = PicoCoach.COACH_ON
                        self.state.dgtmenu.res_picotutor_picocoach = PicoCoach.COACH_ON
                        write_picochess_ini("tutor-coach", "on")
                    else:
                        self.state.dgtmenu.menu_picotutor_picocoach = PicoCoach.COACH_LIFT
                        self.state.dgtmenu.res_picotutor_picocoach = PicoCoach.COACH_LIFT
                        write_picochess_ini("tutor-coach", "lift")
                elif coach_request == 0:
                    self.state.dgtmenu.menu_picotutor_picocoach = PicoCoach.COACH_OFF
                    self.state.dgtmenu.res_picotutor_picocoach = PicoCoach.COACH_OFF
                    write_picochess_ini("tutor-coach", "off")
                elif coach_request == 1 and self.state.dgtmenu.get_picocoach() == PicoCoach.COACH_OFF:
                    self.state.dgtmenu.menu_picotutor_picocoach = PicoCoach.COACH_ON
                    self.state.dgtmenu.res_picotutor_picocoach = PicoCoach.COACH_ON
                    write_picochess_ini("tutor-coach", "on")
                self.state.best_sent_depth.reset()
                await self.state.picotutor.set_status(
                    self.state.dgtmenu.get_picowatcher(),
                    self.state.dgtmenu.get_picocoach(),
                    self.state.dgtmenu.get_picoexplorer(),
                    self.state.dgtmenu.get_picocomment(),
                )

                if event.picocoach != PicoCoach.COACH_OFF:
                    self.state.flag_picotutor = True
                    # @ todo - why do we need to set tutor pos here?
                    await self.set_picotutor_position()
                elif self.state.dgtmenu.get_picowatcher():
                    self.state.flag_picotutor = True
                elif self.state.dgtmenu.get_picoexplorer():
                    self.state.flag_picotutor = True
                else:
                    self.state.flag_picotutor = False

                if self.state.flag_picotutor:
                    await self.state.picotutor.set_mode(self.pgn_mode() or not self.eng_plays())
                if coach_request != 2:
                    coach_mode = self.state.dgtmenu.get_picocoach()
                    coach_msg = 0
                    if coach_mode == PicoCoach.COACH_ON:
                        coach_msg = 1
                    elif coach_mode == PicoCoach.COACH_LIFT:
                        coach_msg = 2
                    await DisplayMsg.show(Message.PICOCOACH(picocoach=coach_msg))
                    if self.shared is not None:
                        if coach_mode != PicoCoach.COACH_OFF:
                            self.shared["tutor_watch_coach_pref"] = coach_mode
                        self.shared["tutor_watch_coach"] = coach_mode != PicoCoach.COACH_OFF
                        self.shared["tutor_watch_active"] = bool(
                            self.shared.get("tutor_watch_watcher") or self.shared.get("tutor_watch_coach")
                        )

                if self.state.dgtmenu.get_picocoach() != PicoCoach.COACH_OFF and coach_request == 2:
                    # call pico coach in case it was already set to on
                    await self.call_pico_coach()

            elif isinstance(event, Event.PICOEXPLORER):
                self.state.best_sent_depth.reset()
                await self.state.picotutor.set_status(
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

                if self.state.flag_picotutor:
                    await self.state.picotutor.set_mode(self.pgn_mode() or not self.eng_plays())
                await DisplayMsg.show(Message.PICOEXPLORER(picoexplorer=event.picoexplorer))

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
                    await DisplayMsg.show(Message.ENGINE_SETUP())
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
                        cmd = get_window_command("toggle_fullscreen")
                        if cmd:
                            process = await asyncio.create_subprocess_shell(
                                cmd,
                                stdout=asyncio.subprocess.PIPE,
                                stderr=asyncio.subprocess.PIPE,
                            )
                            stdout, stderr = await process.communicate()
                            if process.returncode != 0:
                                logger.error(
                                    "Command failed with return code %s: %s", process.returncode, stderr.decode()
                                )
                    game_fen = self.state.game.board_fen()
                    if self.state.variant == "racingkings":
                        self.state.game = chess.Board("8/8/8/8/8/8/krbnNBRK/qrbnNBRQ w - - 0 1")
                    else:
                        self.state.game = chess.Board()
                    self.state.game.turn = chess.WHITE
                    self.state.reset_variant_board()
                    self.state.play_mode = PlayMode.USER_WHITE
                    starting_fen = RK_STARTING_BOARD_FEN if self.state.variant == "racingkings" else chess.STARTING_BOARD_FEN
                    if game_fen != starting_fen:
                        msg = self.state.new_game_msg(newgame=True)
                        await DisplayMsg.show(msg)
                    await self.engine.newgame(self.state.engine_board_copy())
                    self.state.best_sent_depth.reset()
                    self.state.done_computer_fen = None
                    self.state.done_move = self.state.pb_move = chess.Move.null()
                    self.state.searchmoves.reset()
                    self.state.game_declared = False
                    self.state.legal_fens = compute_legal_fens(self.state.game.copy(), self.state.get_variant_board())
                    self.state.last_legal_fens = []
                    self.state.legal_fens_after_cmove = []
                    self.is_out_of_time_already = False
                    await self.engine_mode()
                    await DisplayMsg.show(Message.RSPEED(rspeed=event.rspeed))
                    await self.update_elo_display()

            elif isinstance(event, Event.TAKE_BACK):
                self.state.best_sent_depth.reset()
                if self.state.game.move_stack and (
                    event.take_back == "PGN_TAKEBACK"
                    or not (
                        self.state.take_back_locked
                        or self.online_mode()
                        or (self.emulation_mode() and not self.state.automatic_takeback)
                    )
                ):
                    await self.get_rid_of_engine_move()  # unnecessary engine move not yet done
                    await self.takeback()

            elif isinstance(event, Event.PICOCOMMENT):
                if event.picocomment == "comment-factor":
                    self.pico_talker.set_comment_factor(comment_factor=self.state.dgtmenu.get_comment_factor())
                    await DisplayMsg.show(Message.PICOCOMMENT(picocomment="ok"))
                else:
                    await DisplayMsg.show(Message.PICOCOMMENT(picocomment=event.picocomment))

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
                        # issue 87 - store user override depth/node if flag set
                        # New user choice overrides possibly loaded engine dummy uci options
                        # Node/Depth is a pair - drop both from uci and write both to ini
                        # this guarantees that we dont mix ini and uci file settings
                        # 671 (11 minutes 11 seconds) is the flag
                        if self.state.time_control.move_time == 671:
                            self.engine.drop_engine_uci_option("PicoDepth")  # user override
                            write_picochess_ini("depth", "{:d}".format(tc_init["depth"]))
                            self.engine.drop_engine_uci_option("PicoNode")  # user overrides
                            write_picochess_ini("node", "{:d}".format(tc_init["node"]))
                text = Message.TIME_CONTROL(time_text=event.time_text, show_ok=event.show_ok, tc_init=tc_init)
                await DisplayMsg.show(text)
                self.state.stop_fen_timer()

            elif isinstance(event, Event.CLOCK_TIME):
                if self.dgtdispatcher.is_prio_device(
                    event.dev, event.connect
                ):  # transfer only the most prio clock's time
                    # avoid debugs for every second
                    #                    logger.debug(
                    #                        "setting tc clock time - prio: %s w:%s b:%s",
                    #                        event.dev,
                    #                        hms_time(event.time_white),
                    #                        hms_time(event.time_black),
                    #                    )

                    if self.state.time_control.mode != TimeMode.FIXED and (
                        event.time_white == self.state.time_control.game_time
                        and event.time_black == self.state.time_control.game_time
                    ):
                        pass
                    else:
                        moves_to_go = self.state.time_control.moves_to_go_orig - self.state.game.fullmove_number + 1
                        if moves_to_go < 0:
                            moves_to_go = 0
                        # logger.debug("setting tc clock times")
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
                        await DisplayMsg.show(
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
                    await self.state.stop_clock()
                    result = GameResult.OUT_OF_TIME
                    self.game_end_event()
                    await DisplayMsg.show(
                        Message.GAME_ENDS(
                            tc_init=self.state.time_control.get_parameters(),
                            result=result,
                            play_mode=self.state.play_mode,
                            game=self.state.game.copy(),
                            mode=self.state.interaction_mode,
                        )
                    )
                    self.is_out_of_time_already = True
                    await self.update_elo(result)

            elif isinstance(event, Event.SHUTDOWN):
                await self.get_rid_of_engine_move()
                await self.pre_exit_or_reboot_cleanups()
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
                self.game_end_event()
                await DisplayMsg.show(
                    Message.GAME_ENDS(
                        tc_init=self.state.time_control.get_parameters(),
                        result=result,
                        play_mode=self.state.play_mode,
                        game=self.state.game.copy(),
                        mode=self.state.interaction_mode,
                    )
                )
                await DisplayMsg.show(Message.SYSTEM_SHUTDOWN())
                # no messaging or events beyond this point
                await asyncio.sleep(3)  # molli allow more time (5) for commentary chat
                shutdown(self.args.dgtpi, dev=event.dev)  # @todo make independant of remote eng
                await self.final_exit_or_reboot_cleanups()

            elif isinstance(event, Event.REBOOT):
                await self.get_rid_of_engine_move()
                await self.pre_exit_or_reboot_cleanups()
                result = GameResult.ABORT
                self.game_end_event()
                await DisplayMsg.show(
                    Message.GAME_ENDS(
                        tc_init=self.state.time_control.get_parameters(),
                        result=result,
                        play_mode=self.state.play_mode,
                        game=self.state.game.copy(),
                        mode=self.state.interaction_mode,
                    )
                )
                await DisplayMsg.show(Message.SYSTEM_REBOOT())
                # no messaging or events beyond this point
                await asyncio.sleep(3)  # molli allow more time (5) for commentary chat
                reboot(
                    self.args.dgtpi and self.uci_local_shell.get() is None, dev=event.dev
                )  # @todo make independant of remote eng
                await self.final_exit_or_reboot_cleanups()

            elif isinstance(event, Event.EXIT):
                await self.get_rid_of_engine_move()
                await self.pre_exit_or_reboot_cleanups()
                result = GameResult.ABORT
                self.game_end_event()
                await DisplayMsg.show(
                    Message.GAME_ENDS(
                        tc_init=self.state.time_control.get_parameters(),
                        result=result,
                        play_mode=self.state.play_mode,
                        game=self.state.game.copy(),
                        mode=self.state.interaction_mode,
                    )
                )
                # await DisplayMsg.show(Message.SYSTEM_EXIT())
                # no messaging or events beyond this point
                await asyncio.sleep(3)  # molli allow more time (5) for commentary chat
                exit_pico(self.args.dgtpi, dev=event.dev)  # @todo make independant of remote eng
                await self.final_exit_or_reboot_cleanups()

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
                await DisplayMsg.show(
                    Message.SET_VOICE(type=event.type, lang=event.lang, speaker=event.speaker, speed=event.speed)
                )

            elif isinstance(event, Event.KEYBOARD_BUTTON):
                await DisplayMsg.show(Message.DGT_BUTTON(button=event.button, dev=event.dev))

            elif isinstance(event, Event.KEYBOARD_FEN):
                await DisplayMsg.show(Message.DGT_FEN(fen=event.fen, raw=False))

            elif isinstance(event, Event.EXIT_MENU):
                await DisplayMsg.show(Message.EXIT_MENU())

            elif isinstance(event, Event.UPDATE_PICO):
                await DisplayMsg.show(Message.UPDATE_PICO())
                if not event.tag or event.tag == "":
                    # full update at next boot for all scripts
                    update_pico_v4()  # in utilities for now
                else:
                    # only update code to a specific tag
                    checkout_tag(event.tag)
                await DisplayMsg.show(Message.EXIT_MENU())

            elif isinstance(event, Event.UPDATE_ENGINES):
                await DisplayMsg.show(Message.UPDATE_PICO())
                update_pico_engines()  # in utilities for now
                await DisplayMsg.show(Message.EXIT_MENU())

            elif isinstance(event, Event.REMOTE_ROOM):
                await DisplayMsg.show(Message.REMOTE_ROOM(inside=event.inside))

            elif isinstance(event, Event.PROMOTION):
                await DisplayMsg.show(Message.PROMOTION_DONE(move=event.move))

            else:  # Default
                logger.info("event not handled : [%s]", event)
                await asyncio.sleep(0.05)  # balance message queues

        def exit_sigterm(self, signum, frame):
            """A handler function to register for systemctl stop signal"""
            logger.debug("Received kill signal, shutting down")
            asyncio.create_task(self._exit_async())

        async def _exit_async(self):
            """Async function to handle systemctl stop signal"""
            logger.debug("Shutting down all async tasks")
            try:
                await self.pre_exit_or_reboot_cleanups()
                await self.final_exit_or_reboot_cleanups()
            except Exception as e:
                logger.error("Error during shutdown: %s", e)
                sys.exit(-1)  # force exit on error

        async def wait_for_board_connection(self):
            """Wait for the DGT eBoard connection without blocking other startup tasks."""
            # Wait for eBoard connection unless we are in no-eboards mode
            if self.board_type != dgt.util.EBoard.NOEBOARD:
                board_connected = getattr(self.dgtboard, "is_connected", None)
                if callable(board_connected):
                    while not board_connected():
                        await asyncio.sleep(0.2)

            await self._start_or_stop_analysis_as_needed()  # start analysis if needed
            self.background_analyse_timer.start()  # always run background analyser

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
        shared,
        non_main_tasks,
    )

    await my_main.initialise(time_text)
    main_task = main_loop.create_task(my_main.event_consumer())  # start main message loop
    board_wait_task = main_loop.create_task(my_main.wait_for_board_connection())
    non_main_tasks.add(board_wait_task)  # ensure it gets cancelled on shutdown if still waiting
    all_tasks = non_main_tasks
    all_tasks.add(main_task)
    await asyncio.gather(*all_tasks)  # wait until all tasks are done
    logger.debug("all tasks done, exiting main loop and picochess program")
    # await asyncio.Event().wait()  # wait forever


if __name__ == "__main__":
    asyncio.run(main())
