#!/usr/bin/env python3

# Copyright (C) 2013-2018 Jean-Francois Romang (jromang@posteo.de)
#                         Shivkumar Shivaji ()
#                         Jürgen Précour (LocutusOfPenguin@posteo.de)
#                         Wilhelm
#                         Dirk ("Molli")
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
import threading
import copy
import gc
import logging
from logging.handlers import RotatingFileHandler
import time
import queue
import configargparse  # type: ignore
import paramiko
import math
from typing import Optional, Set, Tuple

from uci.engine import UciShell, UciEngine
from uci.engine_provider import EngineProvider
from uci.rating import Rating, determine_result
import chess  # type: ignore
import chess.pgn  # type: ignore
import chess.polyglot  # type: ignore
import chess.uci  # type: ignore

from timecontrol import TimeControl
from theme import calc_theme
from utilities import get_location, update_picochess, get_opening_books, shutdown, reboot, checkout_tag
from utilities import Observable, DisplayMsg, version, evt_queue, write_picochess_ini, hms_time, get_engine_rspeed_par
from pgn import Emailer, PgnDisplay, ModeInfo
from server import WebServer
from picotalker import PicoTalkerDisplay
from dispatcher import Dispatcher

from dgt.api import Dgt, Message, Event
from dgt.util import GameResult, TimeMode, Mode, PlayMode, PicoComment
from dgt.hw import DgtHw
from dgt.pi import DgtPi
from dgt.display import DgtDisplay
from eboard import EBoard
from dgt.board import DgtBoard, Rev2Info
from chesslink.board import ChessLinkBoard
from chessnut.board import ChessnutBoard
from certabo.board import CertaboBoard
from dgt.translate import DgtTranslate
from dgt.menu import DgtMenu

from picotutor import PicoTutor
from pathlib import Path


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

    def book(self, bookreader, game_copy: chess.Board):
        """Get a BookMove or None from game position."""
        try:
            choice = bookreader.weighted_choice(game_copy, self._excludedmoves)
        except IndexError:
            return None

        book_move = choice.move()
        self.exclude(book_move)
        game_copy.push(book_move)
        try:
            choice = bookreader.weighted_choice(game_copy)
            book_ponder = choice.move()
        except IndexError:
            book_ponder = None
        return chess.uci.BestMove(book_move, book_ponder)

    def check_book(self, bookreader, game_copy: chess.Board) -> bool:
        """Checks if a BookMove exists in current game position."""
        try:
            choice = bookreader.weighted_choice(game_copy)
        except IndexError:
            return False

        book_move = choice.move()

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


flag_startup = False
online_prefix = 'Online'
seeking_flag = False
fen_error_occured = False
position_mode = False
start_time_cmove_done = 0.0
reset_auto = False
newgame_happened = False


class PicochessState:
    """Class to keep track of state in Picochess."""

    def __init__(self):
        self.automatic_takeback = False
        self.best_move_displayed = None
        self.best_move_posted = False
        self.book_in_use = ''
        self.com_factor = 0
        self.comment_file = ''
        self.dgtmenu = None
        self.dgttranslate = None
        self.done_computer_fen = None
        self.done_move = chess.Move.null()
        self.engine_text = None
        self.engine_level = ''
        self.new_engine_level = ''
        self.old_engine_level = ''
        self.error_fen = None
        self.fen_timer = None
        self.fen_timer_running = False
        self.flag_flexible_ponder = False
        self.flag_picotutor = True
        self.flag_premove = False
        self.game = None
        self.game_declared = False  # User declared resignation or draw
        self.interaction_mode = Mode.NORMAL
        self.last_legal_fens = []
        self.last_move = None
        self.legal_fens = []
        self.legal_fens_after_cmove = []
        self.max_guess = 0
        self.max_guess_black = 0
        self.max_guess_white = 0
        self.no_guess_black = 1
        self.no_guess_white = 1
        self.online_decrement = 0
        self.pb_move = chess.Move.null()  # Best ponder move
        self.pgn_book_test = False
        self.picotutor: PicoTutor = None
        self.play_mode = PlayMode.USER_WHITE
        self.searchmoves: AlternativeMover = None
        self.set_location = ''
        self.take_back_locked = False
        self.takeback_active = False
        self.tc_init_last = None
        self.think_time = 0
        self.time_control: TimeControl = None
        self.rating: Rating = None

    def start_clock(self):
        """Start the clock."""
        if self.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.OBSERVE, Mode.REMOTE, Mode.TRAINING):
            self.time_control.start_internal(self.game.turn)
            tc_init = self.time_control.get_parameters()
            if self.interaction_mode == Mode.TRAINING:
                pass
            else:
                DisplayMsg.show(Message.CLOCK_START(turn=self.game.turn, tc_init=tc_init, devs={'ser', 'i2c', 'web'}))
                time.sleep(0.5)  # @todo give some time to clock to really do it. Find a better solution!
        else:
            logging.warning('wrong function call [start]! mode: %s', self.interaction_mode)

    def stop_clock(self):
        """Stop the clock."""
        if self.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.OBSERVE, Mode.REMOTE, Mode.TRAINING):
            self.time_control.stop_internal()
            if self.interaction_mode == Mode.TRAINING:
                pass
            else:
                DisplayMsg.show(Message.CLOCK_STOP(devs={'ser', 'i2c', 'web'}))
                time.sleep(0.5)  # @todo give some time to clock to really do it. Find a better solution!
        else:
            logging.warning('wrong function call [stop]! mode: %s', self.interaction_mode)

    def stop_fen_timer(self):
        """Stop the fen timer cause another fen string been send."""
        if self.fen_timer_running:
            self.fen_timer.cancel()
            self.fen_timer.join()
            self.fen_timer_running = False

    def is_not_user_turn(self):
        """Return if it is users turn (only valid in normal, brain or remote mode)."""
        assert self.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.REMOTE, Mode.TRAINING), 'wrong mode: %s' % self.interaction_mode
        condition1 = (self.play_mode == PlayMode.USER_WHITE and self.game.turn == chess.BLACK)
        condition2 = (self.play_mode == PlayMode.USER_BLACK and self.game.turn == chess.WHITE)
        return condition1 or condition2

    def set_online_tctrl(self, game_time, fischer_inc):
        l_game_time = 0
        l_fischer_inc = 0

        logging.debug('molli online set_online_tctrl input %s %s', game_time, fischer_inc)
        l_game_time = int(game_time)
        l_fischer_inc = int(fischer_inc)
        self.stop_clock()
        self.time_control.stop_internal(log=False)

        self.time_control = TimeControl()
        tc_init = self.time_control.get_parameters()

        if l_fischer_inc == 0:
            tc_init['mode'] = TimeMode.BLITZ
            tc_init['blitz'] = l_game_time
            tc_init['fischer'] = 0
        else:
            tc_init['mode'] = TimeMode.FISCHER
            tc_init['blitz'] = l_game_time
            tc_init['fischer'] = l_fischer_inc

        tc_init['blitz2'] = 0
        tc_init['moves_to_go'] = 0

        lt_white = l_game_time * 60 + l_fischer_inc
        lt_black = l_game_time * 60 + l_fischer_inc
        tc_init['internal_time'] = {chess.WHITE: lt_white, chess.BLACK: lt_black}

        self.time_control = TimeControl(**tc_init)
        text = self.dgttranslate.text('N00_oktime')
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

        return Message.GAME_ENDS(tc_init=self.time_control.get_parameters(), result=result, play_mode=self.play_mode, game=self.game.copy())

    @staticmethod
    def _num(time_str):
        try:
            value = int(time_str)
            if value > 999:
                value = 999
            return value
        except ValueError:
            return 1

    def transfer_time(self, time_list: list, depth=0, node=0):
        """Transfer the time list to a TimeControl Object and a Text Object."""
        i_depth = self._num(depth)
        i_node = self._num(node)

        if i_depth > 0:
            fixed = 671
            timec = TimeControl(TimeMode.FIXED, fixed=fixed, depth=i_depth)
            textc = self.dgttranslate.text('B00_tc_depth', timec.get_list_text())
        elif i_node > 0:
            fixed = 671
            timec = TimeControl(TimeMode.FIXED, fixed=fixed, node=i_node)
            textc = self.dgttranslate.text('B00_tc_node', timec.get_list_text())
        elif len(time_list) == 1:
            fixed = self._num(time_list[0])
            timec = TimeControl(TimeMode.FIXED, fixed=fixed)
            textc = self.dgttranslate.text('B00_tc_fixed', timec.get_list_text())
        elif len(time_list) == 2:
            blitz = self._num(time_list[0])
            fisch = self._num(time_list[1])
            if fisch == 0:
                timec = TimeControl(TimeMode.BLITZ, blitz=blitz)
                textc = self.dgttranslate.text('B00_tc_blitz', timec.get_list_text())
            else:
                timec = TimeControl(TimeMode.FISCHER, blitz=blitz, fischer=fisch)
                textc = self.dgttranslate.text('B00_tc_fisch', timec.get_list_text())
        elif len(time_list) == 3:
            moves_to_go = self._num(time_list[0])
            blitz = self._num(time_list[1])
            blitz2 = self._num(time_list[2])
            if blitz2 == 0:
                timec = TimeControl(TimeMode.BLITZ, blitz=blitz, moves_to_go=moves_to_go, blitz2=blitz2)
                textc = self.dgttranslate.text('B00_tc_tourn', timec.get_list_text())
            else:
                fisch = blitz2
                blitz2 = 0
                timec = TimeControl(TimeMode.FISCHER, blitz=blitz, fischer=fisch, moves_to_go=moves_to_go, blitz2=blitz2)
                textc = self.dgttranslate.text('B00_tc_tourn', timec.get_list_text())
        elif len(time_list) == 4:
            moves_to_go = self._num(time_list[0])
            blitz = self._num(time_list[1])
            fisch = self._num(time_list[2])
            blitz2 = self._num(time_list[3])
            if fisch == 0:
                timec = TimeControl(TimeMode.BLITZ, blitz=blitz, moves_to_go=moves_to_go, blitz2=blitz2)
                textc = self.dgttranslate.text('B00_tc_tourn', timec.get_list_text())
            else:
                timec = TimeControl(TimeMode.FISCHER, blitz=blitz, fischer=fisch, moves_to_go=moves_to_go, blitz2=blitz2)
                textc = self.dgttranslate.text('B00_tc_tourn', timec.get_list_text())
        else:
            timec = TimeControl(TimeMode.BLITZ, blitz=5)
            textc = self.dgttranslate.text('B00_tc_blitz', timec.get_list_text())
        return timec, textc


def check_ssh(host, username, password):
    l_ssh = True
    try:
        s = paramiko.SSHClient()
        s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        s.connect(host, username=username, password=password, timeout=7)
        s.close()
    except Exception:
        l_ssh = False

    return (l_ssh)


def log_pgn(state: PicochessState):
    logging.debug('molli pgn: pgn_book_test: %s', str(state.pgn_book_test))
    logging.debug('molli pgn: game turn: %s', state.game.turn)
    logging.debug('molli pgn: max_guess_white: %s', state.max_guess)
    logging.debug('molli pgn: max_guess_white: %s', state.max_guess_white)
    logging.debug('molli pgn: max_guess_black: %s', state.max_guess_black)
    logging.debug('molli pgn: no_guess_white: %s', state.no_guess_white)
    logging.debug('molli pgn: no_guess_black: %s', state.no_guess_black)


def read_pgn_info():
    info = {}
    try:
        with open('pgn_game_info.txt') as info_file:
            for line in info_file:
                name, value = line.partition("=")[::2]
                info[name.strip()] = value.strip()
        return (info['PGN_GAME'], info['PGN_PROBLEM'], info['PGN_FEN'], info['PGN_RESULT'], info['PGN_White'],
                info['PGN_Black'])
    except (OSError, KeyError):
        logging.error('Could not read pgn_game_info file')
        return 'Game Error', '', '', '*', '', ''


def read_online_result():
    result_line = ''
    winner = ''

    try:
        log_u = open('online_game.txt', 'r')
    except Exception:
        log_u = ''
        logging.error('Could not read online game file')
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
        result_line = ''

    log_u.close()
    logging.debug('Molli in read_result: %s', result_line)
    logging.debug('Molli in read_result: %s', winner)
    return (str(result_line), str(winner))


def read_online_user_info() -> Tuple[str, str, str, str, int, int]:
    own_user = 'unknown'
    opp_user = 'unknown'
    login = 'failed'
    own_color = ''

    try:
        log_u = open('online_game.txt', 'r')
        lines = log_u.readlines()
        for line in lines:
            key, value = line.split('=')
            if key == 'LOGIN':
                login = value.strip()
            elif key == 'COLOR':
                own_color = value.strip()
            elif key == 'OWN_USER':
                own_user = value.strip()
            elif key == 'OPPONENT_USER':
                opp_user = value.strip()
            elif key == 'GAME_TIME':
                game_time = int(value.strip())
            elif key == 'FISCHER_INC':
                fischer_inc = int(value.strip())
    except Exception:
        logging.error('Could not read online game file')
        return login, own_color, own_user, opp_user, 0, 0

    log_u.close()
    logging.debug('online game_time %s fischer_inc: %s', game_time, fischer_inc)

    return login, own_color, own_user, opp_user, game_time, fischer_inc


def compare_fen(fen_board_external='', fen_board_internal='') -> str:
    # <Piece Placement> ::= <rank8>'/'<rank7>'/'<rank6>'/'<rank5>'/'<rank4>'/'<rank3>'/'<rank2>'/'<rank1>
    # <ranki>       ::= [<digit17>]<piece> {[<digit17>]<piece>} [<digit17>] | '8'
    # <piece>       ::= <white Piece> | <black Piece>
    # <digit17>     ::= '1' | '2' | '3' | '4' | '5' | '6' | '7'
    # <white Piece> ::= 'P' | 'N' | 'B' | 'R' | 'Q' | 'K'
    # <black Piece> ::= 'p' | 'n' | 'b' | 'r' | 'q' | 'k'
    # eg. starting position 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR'
    #                       'a8 b8 c8 d8... / a7 b7... / a1 b1 c1 ... h1'

    if fen_board_external == fen_board_internal or fen_board_external == '' or fen_board_internal == '':
        return ''

    internal_board = chess.Board()
    internal_board.set_board_fen(fen_board_internal)

    external_board = chess.Board()
    external_board.set_board_fen(fen_board_external)

    # now compare each square and return first difference
    # and return first all fields to be cleared and then
    # all fields where to put new/different pieces on
    # start first with all squares to be cleared
    put_field = ''
    for square_no in range(0, 63):
        if internal_board.piece_at(square_no) != external_board.piece_at(square_no):
            if internal_board.piece_at(square_no) is None:
                return (str('clear ' + chess.square_name(square_no)))
            else:
                put_field = str('put ' + str(internal_board.piece_at(square_no)) + ' ' + chess.square_name(square_no))
    return put_field


def compute_legal_fens(game_copy: chess.Board):
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


def main() -> None:
    """Main function."""
    state = PicochessState()
    flag_last_engine_pgn = False
    flag_last_engine_emu = False
    flag_last_engine_online = False
    global reset_auto
    global flag_startup
    global position_mode
    global seeking_flag
    global fen_error_occured
    global position_mode
    global start_time_cmove_done
    global newgame_happened

    def det_pgn_guess_tctrl(state: PicochessState):
        state.max_guess_white = 0
        state.max_guess_black = 0

        logging.debug('molli pgn: determine pgn guess')

        uci_options = engine.get_pgn_options()

        logging.debug('molli pgn: uci_options %s', str(uci_options))

        if "max_guess" in uci_options:
            state.max_guess = int(uci_options["max_guess"])
        else:
            state.max_guess = 0

        if "think_time" in uci_options:
            state.think_time = int(uci_options["think_time"])
        else:
            state.think_time = 0

        if "pgn_game_file" in uci_options:
            logging.debug('molli pgn: pgn_game_file; %s', str(uci_options["pgn_game_file"]))
            if 'book_test' in str(uci_options["pgn_game_file"]):
                state.pgn_book_test = True
                logging.debug('molli pgn: pgn_book_test set to True')
            else:
                state.pgn_book_test = False
                logging.debug('molli pgn: pgn_book_test set to False')
        else:
            logging.debug('molli pgn: pgn_book_test not found => False')
            state.pgn_book_test = False

        state.max_guess_white = state.max_guess
        state.max_guess_black = 0

        tc_init = state.time_control.get_parameters()
        tc_init['mode'] = TimeMode.FIXED
        tc_init['fixed'] = state.think_time
        tc_init['blitz'] = 0
        tc_init['fischer'] = 0

        tc_init['blitz2'] = 0
        tc_init['moves_to_go'] = 0
        tc_init['depth'] = 0
        tc_init['node'] = 0

        state.stop_clock()
        text = state.dgttranslate.text('N00_oktime')
        state.time_control.reset()
        Observable.fire(Event.SET_TIME_CONTROL(tc_init=tc_init, time_text=text, show_ok=True))
        state.stop_clock()
        DisplayMsg.show(Message.EXIT_MENU())

    def set_emulation_tctrl(state: PicochessState):
        logging.debug('molli: set_emulation_tctrl')
        if emulation_mode():
            pico_depth = 0
            pico_node = 0
            pico_tctrl_str = ''

            state.stop_clock()
            state.time_control.stop_internal(log=False)

            uci_options = engine.get_pgn_options()
            pico_tctrl_str = ''

            try:
                if "PicoTimeControl" in uci_options:
                    pico_tctrl_str = str(uci_options["PicoTimeControl"])
            except IndexError:
                pico_tctrl_str = ''

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
                logging.debug('molli: set_emulation_tctrl input %s', pico_tctrl_str)
                state.time_control, time_text = state.transfer_time(pico_tctrl_str.split(), depth=pico_depth, node=pico_node)
                tc_init = state.time_control.get_parameters()
                text = state.dgttranslate.text('N00_oktime')
                Observable.fire(Event.SET_TIME_CONTROL(tc_init=tc_init, time_text=text, show_ok=True))
                state.stop_fen_timer()

    def set_fen_from_pgn(pgn_fen, state: PicochessState):
        bit_board = chess.Board(pgn_fen)
        bit_board.set_fen(bit_board.fen())
        logging.debug('molli PGN Fen: %s', bit_board.fen())
        if bit_board.is_valid():
            logging.debug('molli PGN fen is valid!')
            state.game = chess.Board(bit_board.fen())
            state.done_computer_fen = None
            state.done_move = state.pb_move = chess.Move.null()
            state.searchmoves.reset()
            state.game_declared = False
            state.legal_fens = compute_legal_fens(state.game.copy())
            state.legal_fens_after_cmove = []
            state.last_legal_fens = []
            if picotutor_mode(state):
                state.picotutor.reset()
                state.picotutor.set_position(state.game.fen(), i_turn=state.game.turn)
                if state.play_mode == PlayMode.USER_BLACK:
                    state.picotutor.set_user_color(chess.BLACK)
                else:
                    state.picotutor.set_user_color(chess.WHITE)
        else:
            logging.debug('molli PGN fen is invalid!')

    def picotutor_mode(state: PicochessState):
        enabled = False

        if state.flag_picotutor and state.interaction_mode in (Mode.NORMAL, Mode.TRAINING, Mode.BRAIN) and not online_mode() and not pgn_mode() and (state.dgtmenu.get_picowatcher() or state.dgtmenu.get_picocoach() or state.dgtmenu.get_picoexplorer()) and state.picotutor is not None:
            enabled = True
        else:
            enabled = False

        return enabled

    def get_comment_file() -> str:
        comment_path = engine.get_file() + '_comments_' + args.language + '.txt'
        logging.debug('molli comment file: %s', comment_path)
        comment_file = Path(comment_path)
        if comment_file.is_file():
            logging.debug('molli comment file exists')
            return comment_path
        else:
            logging.debug('molli comment file does not exist')
            return ''

    def pgn_mode():
        if 'pgn_' in engine_file:
            return (True)
        else:
            return (False)

    def remote_engine_mode():
        if 'remote' in engine_file:
            return (True)
        else:
            return (False)

    def emulation_mode():
        emulation = False
        if '(mame' in engine_name or '(mess' in engine_name or engine.is_mame:
            emulation = True
        return (emulation)

    def online_mode():
        online = False
        if len(engine_name) >= 6:
            if engine_name[0:6] == online_prefix:
                online = True
            else:
                online = False
        return (online)

    def remote_windows():
        windows = False
        if '\\' in engine_remote_home:
            windows = True
        else:
            windows = False
        return (windows)

    def display_ip_info(state: PicochessState):
        """Fire an IP_INFO message with the IP adr."""
        location, ext_ip, int_ip = get_location()

        if state.set_location == 'auto':
            pass
        else:
            location = state.set_location

        info = {'location': location, 'ext_ip': ext_ip, 'int_ip': int_ip, 'version': version}
        DisplayMsg.show(Message.IP_INFO(info=info))

    def read_pgn_file(file_name: str, state: PicochessState):
        """Read game from PGN file"""
        logging.debug('molli: read game from pgn file')

        l_filename = 'games' + os.sep + file_name
        try:
            l_file_pgn = open(l_filename)
            if not l_file_pgn:
                return
        except OSError:
            return

        l_game_pgn = chess.pgn.read_game(l_file_pgn)
        l_file_pgn.close()

        logging.debug('molli: read game filename %s', l_filename)

        stop_search_and_clock()

        if picotutor_mode(state):
            state.picotutor.reset()

        state.game = chess.Board()
        l_move = chess.Move.null()

        if l_game_pgn.headers['Event']:
            DisplayMsg.show(Message.SHOW_TEXT(text_string=str(l_game_pgn.headers['Event'])))

        if l_game_pgn.headers['White']:
            DisplayMsg.show(Message.SHOW_TEXT(text_string=str(l_game_pgn.headers['White'])))

        DisplayMsg.show(Message.SHOW_TEXT(text_string='versus'))

        if l_game_pgn.headers['Black']:
            DisplayMsg.show(Message.SHOW_TEXT(text_string=str(l_game_pgn.headers['Black'])))

        if l_game_pgn.headers['Result']:
            DisplayMsg.show(Message.SHOW_TEXT(text_string=str(l_game_pgn.headers['Result'])))

        time.sleep(2)
        DisplayMsg.show(Message.READ_GAME)
        time.sleep(2)

        for l_move in l_game_pgn.main_line():
            state.game.push(l_move)

        # take back last move in order to send it with user_move for web publishing
        if l_move:
            state.game.pop()

        engine.newgame(state.game.copy())

        # switch temporarly picotutor off
        state.flag_picotutor = False

        if l_move:
            user_move(l_move, sliding=True, state=state)  # publish current position to webserver

        state.flag_picotutor = True

        stop_search_and_clock()
        turn = state.game.turn
        state.done_computer_fen = None
        state.done_move = state.pb_move = chess.Move.null()
        state.play_mode = PlayMode.USER_WHITE if turn == chess.WHITE else PlayMode.USER_BLACK

        l_pico_depth = 0
        try:
            if 'PicoDepth' in l_game_pgn.headers and l_game_pgn.headers['PicoDepth']:
                l_pico_depth = int(l_game_pgn.headers['PicoDepth'])
        except ValueError:
            pass

        l_pico_node = 0
        try:
            if 'PicoNode' in l_game_pgn.headers and l_game_pgn.headers['PicoNode']:
                l_pico_node = int(l_game_pgn.headers['PicoNode'])
        except ValueError:
            pass

        if 'PicoTimeControl' in l_game_pgn.headers and l_game_pgn.headers['PicoTimeControl']:
            l_pico_tc = str(l_game_pgn.headers['PicoTimeControl'])
            state.time_control, time_text = state.transfer_time(l_pico_tc.split(), depth=l_pico_depth, node=l_pico_node)

        try:
            if 'PicoRemTimeW' in l_game_pgn.headers and l_game_pgn.headers['PicoRemTimeW']:
                lt_white = int(l_game_pgn.headers['PicoRemTimeW'])
        except ValueError:
            lt_white = 0

        try:
            if 'PicoRemTimeB' in l_game_pgn.headers and l_game_pgn.headers['PicoRemTimeB']:
                lt_black = int(l_game_pgn.headers['PicoRemTimeB'])
        except ValueError:
            lt_black = 0

        tc_init = state.time_control.get_parameters()
        state.tc_init_last = state.time_control.get_parameters()

        tc_init['internal_time'] = {chess.WHITE: lt_white, chess.BLACK: lt_black}
        text = state.dgttranslate.text('N00_oktime')
        state.time_control.reset()

        Observable.fire(Event.SET_TIME_CONTROL(tc_init=tc_init, time_text=text, show_ok=False))
        state.stop_clock()
        DisplayMsg.show(Message.EXIT_MENU())

        state.searchmoves.reset()
        state.game_declared = False

        state.legal_fens = compute_legal_fens(state.game.copy())
        state.legal_fens_after_cmove = []
        state.last_legal_fens = []
        assert engine.is_waiting(), 'molli: read_pgn engine not waiting! thinking status: %s' % engine.is_thinking()
        engine.position(copy.deepcopy(state.game))

        game_end = state.check_game_state()
        if game_end:
            state.play_mode = PlayMode.USER_WHITE if turn == chess.WHITE else PlayMode.USER_BLACK
            state.legal_fens = []
            state.legal_fens_after_cmove = []
            DisplayMsg.show(game_end)
        else:
            state.play_mode = PlayMode.USER_WHITE if turn == chess.WHITE else PlayMode.USER_BLACK
            text = state.play_mode.value
            msg = Message.PLAY_MODE(play_mode=state.play_mode, play_mode_text=state.dgttranslate.text(text))
            DisplayMsg.show(msg)
            time.sleep(1)

        state.take_back_locked = True  # important otherwise problems for setting up the position

    def expired_fen_timer(state: PicochessState):
        """Handle times up for an unhandled fen string send from board."""
        global flag_startup
        global seeking_flag
        global fen_error_occured
        global position_mode
        global newgame_happened
        fen_i = ''
        game_fen = ''

        state.fen_timer_running = False

        if state.error_fen:
            game_fen = state.game.board_fen()
            if (state.interaction_mode in (Mode.NORMAL, Mode.TRAINING, Mode.BRAIN) and game_fen != chess.STARTING_BOARD_FEN and not online_mode() and not pgn_mode() and not emulation_mode() and state.error_fen != game_fen and state.take_back_locked):
                # check for inverse setup
                fen_i = state.error_fen[::-1]
                if fen_i == game_fen:
                    logging.debug('molli: reverse the board!')
                    state.dgtmenu.set_position_reverse_flipboard(True)

            if (state.interaction_mode in (Mode.NORMAL, Mode.TRAINING, Mode.BRAIN) and game_fen != chess.STARTING_BOARD_FEN and flag_startup and state.dgtmenu.get_game_contlast() and not online_mode() and not pgn_mode() and not emulation_mode()):
                # molli: read the pgn of last game and restore correct game status and times
                flag_startup = False
                DisplayMsg.show(Message.RESTORE_GAME())
                time.sleep(2)

                l_pgn_file_name = 'last_game.pgn'
                read_pgn_file(l_pgn_file_name, state)

            elif (state.interaction_mode == Mode.PONDER and state.flag_flexible_ponder):
                if (not newgame_happened) or flag_startup:
                    # molli: no error in analysis(ponder) mode => start new game with current fen
                    # and try to keep same player to play (white or black) but check
                    # if it is a legal position (otherwise switch sides or return error)
                    fen1 = state.error_fen
                    fen2 = state.error_fen
                    if state.game.turn == chess.WHITE:
                        fen1 += ' w KQkq - 0 1'
                        fen2 += ' b KQkq - 0 1'
                    else:
                        fen1 += ' b KQkq - 0 1'
                        fen2 += ' w KQkq - 0 1'
                    # ask python-chess to correct the castling string
                    bit_board = chess.Board(fen1)
                    bit_board.set_fen(bit_board.fen())
                    if bit_board.is_valid():
                        state.game = chess.Board(bit_board.fen())
                        stop_search_and_clock()
                        engine.newgame(state.game.copy())
                        state.done_computer_fen = None
                        state.done_move = state.pb_move = chess.Move.null()
                        state.searchmoves.reset()
                        state.game_declared = False
                        state.legal_fens = compute_legal_fens(state.game.copy())
                        state.legal_fens_after_cmove = []
                        state.last_legal_fens = []
                        DisplayMsg.show(Message.SHOW_TEXT(text_string='NEW_POSITION'))
                        set_wait_state(Message.START_NEW_GAME(game=state.game.copy(), newgame=False), state)
                        assert engine.is_waiting(), 'engine not waiting! thinking status: %s' % engine.is_thinking()
                        engine.position(copy.deepcopy(state.game))
                        engine.ponder()
                    else:
                        # ask python-chess to correct the castling string
                        bit_board = chess.Board(fen2)
                        bit_board.set_fen(bit_board.fen())
                        if bit_board.is_valid():
                            state.game = chess.Board(bit_board.fen())
                            stop_search_and_clock()
                            engine.newgame(state.game.copy())
                            state.done_computer_fen = None
                            state.done_move = state.pb_move = chess.Move.null()
                            state.searchmoves.reset()
                            state.game_declared = False
                            state.legal_fens = compute_legal_fens(state.game.copy())
                            state.legal_fens_after_cmove = []
                            state.last_legal_fens = []
                            DisplayMsg.show(Message.SHOW_TEXT(text_string='NEW_POSITION'))
                            set_wait_state(Message.START_NEW_GAME(game=state.game.copy(), newgame=False), state)
                            assert engine.is_waiting(), 'engine not waiting! thinking status: %s' % engine.is_thinking()
                            engine.position(copy.deepcopy(state.game))
                            engine.ponder()
                        else:
                            logging.info('wrong fen %s for 4 secs', state.error_fen)
                            DisplayMsg.show(Message.WRONG_FEN())
            else:
                logging.info('wrong fen %s for 4 secs', state.error_fen)

                if online_mode():
                    # show computer opponents move again
                    if seeking_flag:
                        DisplayMsg.show(Message.SEEKING())
                    elif state.best_move_displayed:
                        DisplayMsg.show(Message.COMPUTER_MOVE(move=state.done_move, ponder=False, game=state.game.copy(), wait=False))

                fen_res = ''
                internal_fen = state.game.board_fen()
                external_fen = state.error_fen
                fen_res = compare_fen(external_fen, internal_fen)

                if not position_mode and fen_res:
                    DisplayMsg.show(Message.WRONG_FEN())
                    time.sleep(2)
                if fen_error_occured and state.game.board_fen() and fen_res:
                    # molli: Picochess correction messages (not for starting position)
                    # show incorrect square(s) and piece to put or be removed
                    if fen_res:
                        position_mode = True
                        if not online_mode():
                            state.stop_clock()
                        msg = Message.POSITION_FAIL(fen_result=fen_res)
                        DisplayMsg.show(msg)
                        time.sleep(1)
                    else:
                        DisplayMsg.show(Message.EXIT_MENU())
                else:
                    DisplayMsg.show(Message.EXIT_MENU())

                if state.interaction_mode in (Mode.NORMAL, Mode.TRAINING, Mode.BRAIN) and game_fen != chess.STARTING_BOARD_FEN and flag_startup:

                    if state.dgtmenu.get_enginename():
                        DisplayMsg.show(Message.ENGINE_NAME(engine_name=state.engine_text))

                    if pgn_mode():
                        pgn_white = ''
                        pgn_black = ''
                        pgn_game_name, pgn_problem, pgn_fen, pgn_result, pgn_white, pgn_black = read_pgn_info()

                        if pgn_white:
                            DisplayMsg.show(Message.SHOW_TEXT(text_string=pgn_white))
                        if pgn_black:
                            DisplayMsg.show(Message.SHOW_TEXT(text_string=pgn_black))

                        if pgn_result:
                            DisplayMsg.show(Message.SHOW_TEXT(text_string=pgn_result))

                        if 'mate in' in pgn_problem or 'Mate in' in pgn_problem:
                            set_fen_from_pgn(pgn_fen, state)
                            DisplayMsg.show(Message.SHOW_TEXT(text_string=pgn_problem))
                        else:
                            DisplayMsg.show(Message.SHOW_TEXT(text_string=pgn_game_name))

                else:
                    if state.done_computer_fen and not position_mode:
                        DisplayMsg.show(Message.EXIT_MENU())
                fen_error_occured = True  # to be reset in fen_handling
        flag_startup = False
        newgame_happened = False

    def start_fen_timer(state: PicochessState):
        """Start the fen timer in case an unhandled fen string been received from board."""
        global position_mode
        delay = 0

        if position_mode:
            delay = 1  # if a fen error already occured don't wait too long for next check
        else:
            delay = 4
        state.fen_timer = threading.Timer(delay, expired_fen_timer, args=[state])
        state.fen_timer.start()
        state.fen_timer_running = True

    def think(game: chess.Board, timec: TimeControl, msg: Message, state: PicochessState, searchlist=False):
        """
        Start a new search on the current game.

        If a move is found in the opening book, fire an event in a few seconds.
        """
        DisplayMsg.show(msg)
        if not online_mode() or game.fullmove_number > 1:
            state.start_clock()
        book_res = state.searchmoves.book(bookreader, game.copy())
        if (book_res and not emulation_mode() and not online_mode() and not pgn_mode()) or (book_res and (pgn_mode() and state.pgn_book_test)):
            Observable.fire(Event.BEST_MOVE(move=book_res.bestmove, ponder=book_res.ponder, inbook=True))
        else:
            while not engine.is_waiting():
                time.sleep(0.05)
                logging.warning('engine is still not waiting')
            uci_dict = timec.uci()
            if searchlist:
                # molli: otherwise might lead to problems with internal books
                uci_dict['searchmoves'] = state.searchmoves.all(game)
            engine.position(copy.deepcopy(game))
            engine.go(uci_dict)
        state.automatic_takeback = False

    def mame_endgame(game: chess.Board, timec: TimeControl, msg: Message, searchlist=False):
        """
        Start a new search on the current game.

        If a move is found in the opening book, fire an event in a few seconds.
        """

        while not engine.is_waiting():
            time.sleep(0.05)
            logging.warning('engine is still not waiting')
        engine.position(copy.deepcopy(game))

    def analyse(game: chess.Board, msg: Message):
        """Start a new ponder search on the current game."""
        DisplayMsg.show(msg)
        engine.position(copy.deepcopy(game))
        engine.ponder()

    def observe(game: chess.Board, msg: Message):
        """Start a new ponder search on the current game."""
        analyse(game, msg)
        state.start_clock()

    def brain(game: chess.Board, timec: TimeControl, state: PicochessState):
        """Start a new permanent brain search on the game with pondering move made."""
        assert not state.done_computer_fen, 'brain() called with displayed move - fen: %s' % state.done_computer_fen
        if state.pb_move:
            game_copy = copy.deepcopy(game)
            game_copy.push(state.pb_move)
            logging.info('start permanent brain with pondering move [%s] fen: %s', state.pb_move, game_copy.fen())
            engine.position(game_copy)
            engine.brain(timec.uci())
        else:
            logging.info('ignore permanent brain cause no pondering move available')

    def stop_search_and_clock(ponder_hit=False):
        """Depending on the interaction mode stop search and clock."""
        if state.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.TRAINING):
            state.stop_clock()
            if engine.is_waiting():
                logging.info('engine already waiting')
            else:
                if ponder_hit:
                    pass  # we send the engine.hit() lateron!
                else:
                    stop_search()
        elif state.interaction_mode in (Mode.REMOTE, Mode.OBSERVE):
            state.stop_clock()
            stop_search()
        elif state.interaction_mode in (Mode.ANALYSIS, Mode.KIBITZ, Mode.PONDER):
            stop_search()

    def stop_search():
        """Stop current search."""
        engine.stop()
        if not emulation_mode():
            while not engine.is_waiting():
                time.sleep(0.05)
                logging.warning('engine is still not waiting')

    def user_move(move: chess.Move, sliding: bool, state: PicochessState):
        """Handle an user move."""
        global fen_error_occured
        global position_mode

        eval_str = ''

        state.take_back_locked = False

        logging.info('user move [%s] sliding: %s', move, sliding)
        if move not in state.game.legal_moves:
            logging.warning('illegal move [%s]', move)
        else:

            if state.interaction_mode == Mode.BRAIN:
                ponder_hit = (move == state.pb_move)
                logging.info('pondering move: [%s] res: Ponder%s', state.pb_move, 'Hit' if ponder_hit else 'Miss')
            else:
                ponder_hit = False
            if sliding and ponder_hit:
                logging.warning('sliding detected, turn ponderhit off')
                ponder_hit = False

            stop_search_and_clock(ponder_hit=ponder_hit)
            if state.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.OBSERVE, Mode.REMOTE, Mode.TRAINING) and not sliding:
                state.time_control.add_time(state.game.turn)
                # molli new tournament time control
                if state.time_control.moves_to_go_orig > 0 and state.game.fullmove_number == state.time_control.moves_to_go_orig:
                    state.time_control.add_game2(state.game.turn)
                    t_player = True
                    msg = Message.TIMECONTROL_CHECK(player=t_player, movestogo=state.time_control.moves_to_go_orig, time1=state.time_control.game_time, time2=state.time_control.game_time2)
                    DisplayMsg.show(msg)
                if online_mode():
                    # molli for online pseudo time sync
                    if state.online_decrement > 0:
                        state.time_control.sub_online_time(state.game.turn, state.online_decrement)

            game_before = state.game.copy()

            state.done_computer_fen = None
            state.done_move = chess.Move.null()
            fen = state.game.fen()
            turn = state.game.turn
            state.game.push(move)
            eval_str = ''

            if picotutor_mode(state) and not position_mode and not state.takeback_active:
                l_mate = ''
                t_hint_move = chess.Move.null()
                valid = state.picotutor.push_move(move)
                # get evalutaion result and give user feedback
                if state.dgtmenu.get_picowatcher():
                    if valid:
                        eval_str, l_mate, l_hint = state.picotutor.get_user_move_eval()
                    else:
                        # invalid move from tutor side!? Something went wrong
                        eval_str = 'ER'
                        state.picotutor.set_position(state.game.fen(), i_turn=state.game.turn)
                        if state.play_mode == PlayMode.USER_BLACK:
                            state.picotutor.set_user_color(chess.BLACK)
                        else:
                            state.picotutor.set_user_color(chess.WHITE)
                            l_mate = ''
                        eval_str = ''  # no error message
                    if eval_str != '' and state.last_move != move:  # molli takeback_mame
                        msg = Message.PICOTUTOR_MSG(eval_str=eval_str)
                        DisplayMsg.show(msg)
                        if '??' in eval_str:
                            time.sleep(3)
                        else:
                            time.sleep(1)
                    if l_mate:
                        n_mate = int(l_mate)
                    else:
                        n_mate = 0
                    if n_mate < 0:
                        msg_str = 'USRMATE_' + str(abs(n_mate))
                        msg = Message.PICOTUTOR_MSG(eval_str=msg_str)
                        DisplayMsg.show(msg)
                        time.sleep(1.5)
                    elif n_mate > 1:
                        n_mate = n_mate - 1
                        msg_str = 'PICMATE_' + str(abs(n_mate))
                        msg = Message.PICOTUTOR_MSG(eval_str=msg_str)
                        DisplayMsg.show(msg)
                        time.sleep(1.5)
                    # get additional info in case of blunder
                    if eval_str == '??' and state.last_move != move:
                        t_hint_move = chess.Move.null()
                        threat_move = chess.Move.null()
                        t_mate, t_hint_move, t_pv_best_move, t_pv_user_move = state.picotutor.get_user_move_info()

                        try:
                            threat_move = t_pv_user_move[1]
                        except IndexError:
                            threat_move = chess.Move.null()

                        if threat_move != chess.Move.null():
                            game_tutor = game_before.copy()
                            game_tutor.push(move)
                            san_move = game_tutor.san(threat_move)
                            game_tutor.push(t_pv_user_move[1])

                            tutor_str = 'THREAT' + san_move
                            msg = Message.PICOTUTOR_MSG(eval_str=tutor_str, game=game_tutor.copy())
                            DisplayMsg.show(msg)
                            time.sleep(5)

                        if t_hint_move.uci() != chess.Move.null():
                            game_tutor = game_before.copy()
                            san_move = game_tutor.san(t_hint_move)
                            game_tutor.push(t_hint_move)
                            tutor_str = 'HINT' + san_move
                            msg = Message.PICOTUTOR_MSG(eval_str=tutor_str, game=game_tutor.copy())
                            DisplayMsg.show(msg)
                            time.sleep(5)

                if state.game.fullmove_number < 1:
                    ModeInfo.reset_opening()

            state.searchmoves.reset()
            if state.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.TRAINING):
                msg = Message.USER_MOVE_DONE(move=move, fen=fen, turn=turn, game=state.game.copy())
                game_end = state.check_game_state()
                if game_end:
                    update_elo(state, game_end.result)
                    # molli: for online/emulation mode we have to publish this move as well to the engine
                    if online_mode():
                        logging.info('starting think()')
                        think(state.game, state.time_control, msg, state)
                    elif emulation_mode():
                        logging.info('molli: starting mame_endgame()')
                        mame_endgame(state.game, state.time_control, msg)
                        DisplayMsg.show(msg)
                        DisplayMsg.show(game_end)
                        state.legal_fens_after_cmove = []  # molli
                    else:
                        DisplayMsg.show(msg)
                        DisplayMsg.show(game_end)
                        state.legal_fens_after_cmove = []  # molli
                else:
                    if state.interaction_mode in (Mode.NORMAL, Mode.TRAINING) or not ponder_hit:
                        if not state.check_game_state():
                            # molli: automatic takeback of blunder moves for mame engines
                            if emulation_mode() and eval_str == '??' and state.last_move != move:
                                # molli: do not send move to engine
                                # wait for take back or lever button in case of no takeback
                                state.takeback_active = True
                                state.automatic_takeback = True  # to be reset in think!
                                set_wait_state(Message.TAKE_BACK(game=state.game.copy()), state)
                            else:
                                # send move to engine
                                logging.info('starting think()')
                                think(state.game, state.time_control, msg, state)
                    else:
                        logging.info('think() not started cause ponderhit')
                        DisplayMsg.show(msg)
                        state.start_clock()
                        engine.hit()  # finally tell the engine
                state.last_move = move
            elif state.interaction_mode == Mode.REMOTE:
                msg = Message.USER_MOVE_DONE(move=move, fen=fen, turn=turn, game=state.game.copy())
                game_end = state.check_game_state()
                if game_end:
                    DisplayMsg.show(msg)
                    DisplayMsg.show(game_end)
                else:
                    observe(state.game, msg)
            elif state.interaction_mode == Mode.OBSERVE:
                msg = Message.REVIEW_MOVE_DONE(move=move, fen=fen, turn=turn, game=state.game.copy())
                game_end = state.check_game_state()
                if game_end:
                    DisplayMsg.show(msg)
                    DisplayMsg.show(game_end)
                else:
                    observe(state.game, msg)
            else:  # state.interaction_mode in (Mode.ANALYSIS, Mode.KIBITZ, Mode.PONDER):
                msg = Message.REVIEW_MOVE_DONE(move=move, fen=fen, turn=turn, game=state.game.copy())
                game_end = state.check_game_state()
                if game_end:
                    DisplayMsg.show(msg)
                    DisplayMsg.show(game_end)
                else:
                    analyse(state.game, msg)

            if picotutor_mode(state) and not position_mode and not state.takeback_active and not state.automatic_takeback:
                if state.dgtmenu.get_picoexplorer():
                    opening_name = ''
                    opening_in_book = False
                    opening_eco, opening_name, _, opening_in_book = state.picotutor.get_opening()
                    if opening_in_book and opening_name:
                        ModeInfo.set_opening(state.book_in_use, str(opening_name), opening_eco)
                        DisplayMsg.show(Message.SHOW_TEXT(text_string=opening_name))
                        time.sleep(0.7)

                if state.dgtmenu.get_picocomment() != PicoComment.COM_OFF and not game_end:
                    game_comment = ''
                    game_comment = state.picotutor.get_game_comment(pico_comment=state.dgtmenu.get_picocomment(), com_factor=state.com_factor)
                    if game_comment:
                        DisplayMsg.show(Message.SHOW_TEXT(text_string=game_comment))
                        time.sleep(0.7)
            state.takeback_active = False

    def update_elo(state, result):
        if engine.is_adaptive:
            state.rating = engine.update_rating(state.rating, determine_result(result, state.play_mode,
                                                state.game.turn == chess.WHITE))

    def update_elo_display(state):
        DisplayMsg.show(Message.SYSTEM_INFO(info={'rspeed': state.dgtmenu.get_engine_rspeed()}))
        if engine.is_adaptive:
            DisplayMsg.show(Message.SYSTEM_INFO(
                info={'user_elo': int(state.rating.rating), 'engine_elo': engine.engine_rating}))
        elif engine.engine_rating > 0:
            user_elo = args.pgn_elo
            if state.rating is not None:
                user_elo = str(int(state.rating.rating))
            DisplayMsg.show(Message.SYSTEM_INFO(
                info={'user_elo': user_elo, 'engine_elo': engine.engine_rating}))

    def process_fen(fen: str, state: PicochessState):
        """Process given fen like doMove, undoMove, takebackPosition, handleSliding."""
        global flag_startup
        global fen_error_occured
        global position_mode
        global start_time_cmove_done
        global newgame_happened

        handled_fen = True
        state.error_fen = None
        legal_fens_pico = compute_legal_fens(state.game.copy())
        # Check for same position
        if fen == state.game.board_fen():
            logging.debug('Already in this fen: %s', fen)
            flag_startup = False
            # molli: Chess tutor
            if picotutor_mode(state) and state.dgtmenu.get_picocoach() and fen != chess.STARTING_BOARD_FEN and not state.take_back_locked and not fen_error_occured and not position_mode and not state.automatic_takeback:
                if ((state.game.turn == chess.WHITE and state.play_mode == PlayMode.USER_WHITE) or (state.game.turn == chess.BLACK and state.play_mode == PlayMode.USER_BLACK)) and not (state.game.is_checkmate() or state.game.is_stalemate()):
                    state.stop_clock()
                    state.stop_fen_timer()
                    eval_str = 'ANALYSIS'
                    msg = Message.PICOTUTOR_MSG(eval_str=eval_str)
                    DisplayMsg.show(msg)
                    time.sleep(2)

                    t_best_move, t_best_score, t_best_mate, t_pv_best_move, t_alt_best_moves = state.picotutor.get_pos_analysis()

                    tutor_str = 'POS' + str(t_best_score)
                    msg = Message.PICOTUTOR_MSG(eval_str=tutor_str, score=t_best_score)
                    DisplayMsg.show(msg)
                    time.sleep(5)

                    if t_best_mate:
                        l_mate = int(t_best_mate)
                        if t_best_move != chess.Move.null():
                            game_tutor = state.game.copy()
                            san_move = game_tutor.san(t_best_move)
                            game_tutor.push(t_best_move)  # for picotalker (last move spoken)
                            tutor_str = 'BEST' + san_move
                            msg = Message.PICOTUTOR_MSG(eval_str=tutor_str, game=game_tutor.copy())
                            DisplayMsg.show(msg)
                            time.sleep(5)
                    else:
                        l_mate = 0
                    if l_mate > 0:
                        eval_str = 'PICMATE_' + str(abs(l_mate))
                        msg = Message.PICOTUTOR_MSG(eval_str=eval_str)
                        DisplayMsg.show(msg)
                        time.sleep(5)
                    elif l_mate < 0:
                        eval_str = 'USRMATE_' + str(abs(l_mate))
                        msg = Message.PICOTUTOR_MSG(eval_str=eval_str)
                        DisplayMsg.show(msg)
                        time.sleep(5)
                    else:
                        l_max = 0
                        for alt_move in t_alt_best_moves:
                            l_max = l_max + 1
                            if l_max <= 3:
                                game_tutor = state.game.copy()
                                san_move = game_tutor.san(alt_move)
                                game_tutor.push(alt_move)  # for picotalker (last move spoken)

                                tutor_str = 'BEST' + san_move
                                msg = Message.PICOTUTOR_MSG(eval_str=tutor_str, game=game_tutor.copy())
                                DisplayMsg.show(msg)
                                time.sleep(5)
                            else:
                                break

                    state.start_clock()
            else:
                if position_mode:
                    # position finally alright!
                    tutor_str = 'POSOK'
                    msg = Message.PICOTUTOR_MSG(eval_str=tutor_str, game=state.game.copy())
                    DisplayMsg.show(msg)
                    position_mode = False
                    time.sleep(1)
                    if not state.done_computer_fen:
                        state.start_clock()
                    DisplayMsg.show(Message.EXIT_MENU())

        # Check if we have to undo a previous move (sliding)
        elif fen in state.last_legal_fens:
            logging.info('sliding move detected')
            if state.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.TRAINING):
                if state.is_not_user_turn():
                    stop_search()
                    state.game.pop()
                    if picotutor_mode(state):
                        if state.best_move_posted:
                            state.picotutor.pop_last_move()  # bestmove already sent to tutor
                            state.best_move_posted = False
                        state.picotutor.pop_last_move()  # no switch of sides
                    logging.info('user move in computer turn, reverting to: %s', state.game.fen())
                elif state.done_computer_fen:
                    state.done_computer_fen = None
                    state.done_move = chess.Move.null()
                    state.game.pop()
                    if picotutor_mode(state):
                        if state.best_move_posted:
                            state.picotutor.pop_last_move()  # bestmove already sent to tutor
                            state.best_move_posted = False
                        state.picotutor.pop_last_move()  # no switch of sides
                    logging.info('user move while computer move is displayed, reverting to: %s', state.game.fen())
                else:
                    handled_fen = False
                    logging.error('last_legal_fens not cleared: %s', state.game.fen())
            elif state.interaction_mode == Mode.REMOTE:
                if state.is_not_user_turn():
                    state.game.pop()
                    if picotutor_mode(state):
                        if state.best_move_posted:
                            state.picotutor.pop_last_move()  # bestmove already sent to tutor
                            state.best_move_posted = False
                        state.picotutor.pop_last_move()
                    logging.info('user move in remote turn, reverting to: %s', state.game.fen())
                elif state.done_computer_fen:
                    state.done_computer_fen = None
                    state.done_move = chess.Move.null()
                    state.game.pop()
                    if picotutor_mode(state):
                        if state.best_move_posted:
                            state.picotutor.pop_last_move()  # bestmove already sent to tutor
                            state.best_move_posted = False
                        state.picotutor.pop_last_move()
                    logging.info('user move while remote move is displayed, reverting to: %s', state.game.fen())
                else:
                    handled_fen = False
                    logging.error('last_legal_fens not cleared: %s', state.game.fen())
            else:
                state.game.pop()
                if picotutor_mode(state):
                    if state.best_move_posted:
                        state.picotutor.pop_last_move()  # bestmove already sent to tutor
                        state.best_move_posted = False
                    state.picotutor.pop_last_move()
                    # just to be sure set fen pos.
                    game_copy = copy.deepcopy(state.game)
                    state.picotutor.set_position(game_copy.fen(), i_turn=game_copy.turn)
                    if state.play_mode == PlayMode.USER_BLACK:
                        state.picotutor.set_user_color(chess.BLACK)
                    else:
                        state.picotutor.set_user_color(chess.WHITE)
                logging.info('wrong color move -> sliding, reverting to: %s', state.game.fen())
            legal_moves = list(state.game.legal_moves)
            move = legal_moves[state.last_legal_fens.index(fen)]
            user_move(move, sliding=True, state=state)
            if state.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.REMOTE, Mode.TRAINING):
                state.legal_fens = []
            else:
                state.legal_fens = compute_legal_fens(state.game.copy())

        # allow playing/correcting moves for pico's side in TRAINING mode:
        elif fen in legal_fens_pico and state.interaction_mode == Mode.TRAINING:
            legal_moves = list(state.game.legal_moves)
            move = legal_moves[legal_fens_pico.index(fen)]

            if state.done_computer_fen:
                if fen == state.done_computer_fen:
                    pass
                else:
                    DisplayMsg.show(Message.WRONG_FEN())  # display set pieces/pico's move
                    time.sleep(3)  # display set pieces again and accept new players move as pico's move
                    DisplayMsg.show(Message.ALTERNATIVE_MOVE(game=state.game.copy(), play_mode=state.play_mode))
                    time.sleep(2)
                    DisplayMsg.show(Message.COMPUTER_MOVE(move=move, ponder=False, game=state.game.copy(), wait=False))
                    time.sleep(2)
            logging.info('user move did a move for pico')

            user_move(move, sliding=False, state=state)
            state.last_legal_fens = state.legal_fens
            if state.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.REMOTE, Mode.TRAINING):
                state.legal_fens = []
            else:
                state.legal_fens = compute_legal_fens(state.game.copy())

        # standard legal move
        elif fen in state.legal_fens:
            logging.info('standard move detected')
            newgame_happened = False
            legal_moves = list(state.game.legal_moves)
            move = legal_moves[state.legal_fens.index(fen)]
            user_move(move, sliding=False, state=state)
            state.last_legal_fens = state.legal_fens
            if state.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.REMOTE):
                state.legal_fens = []
            else:
                state.legal_fens = compute_legal_fens(state.game.copy())

    # molli: allow direct play of an alternative move for pico
        elif fen in legal_fens_pico and fen not in state.legal_fens and fen != state.done_computer_fen and state.done_computer_fen and state.interaction_mode in (Mode.NORMAL, Mode.BRAIN) and not online_mode() and not emulation_mode() and not pgn_mode() and state.dgtmenu.get_game_altmove() and not state.takeback_active:
            legal_moves = list(state.game.legal_moves)
            computer_move = state.done_move
            state.done_move = legal_moves[legal_fens_pico.index(fen)]
            state.best_move_posted = False
            state.best_move_displayed = None
            if computer_move:
                DisplayMsg.show(Message.COMPUTER_MOVE(move=computer_move, ponder=False, game=state.game.copy(), wait=False))
                time.sleep(3)
            DisplayMsg.show(Message.ALTERNATIVE_MOVE(game=state.game.copy(), play_mode=state.play_mode))
            time.sleep(3)
            if state.done_move:
                DisplayMsg.show(Message.COMPUTER_MOVE(move=state.done_move, ponder=False, game=state.game.copy(), wait=False))
                time.sleep(1.5)

            DisplayMsg.show(Message.COMPUTER_MOVE_DONE())
            logging.info('user did a move for pico')
            state.game.push(state.done_move)
            state.done_computer_fen = None
            state.done_move = chess.Move.null()
            game_end = state.check_game_state()
            valid = True
            if picotutor_mode(state):
                state.picotutor.pop_last_move()
                valid = state.picotutor.push_move(state.done_move)
                if not valid:
                    eval_str = 'ER'
                    state.picotutor.reset()
                    state.picotutor.set_position(state.game.fen(), i_turn=state.game.turn)

            if game_end:
                state.legal_fens = []
                state.legal_fens_after_cmove = []
                if online_mode():
                    stop_search_and_clock()
                    state.stop_fen_timer()
                stop_search_and_clock()
                DisplayMsg.show(game_end)
            else:
                state.searchmoves.reset()
                state.time_control.add_time(not state.game.turn)

                # molli new tournament time control
                if state.time_control.moves_to_go_orig > 0 and (state.game.fullmove_number - 1) == state.time_control.moves_to_go_orig:
                    state.time_control.add_game2(not state.game.turn)
                    t_player = False
                    msg = Message.TIMECONTROL_CHECK(player=t_player, movestogo=state.time_control.moves_to_go_orig, time1=state.time_control.game_time, time2=state.time_control.game_time2)
                    DisplayMsg.show(msg)

                state.start_clock()

                if state.interaction_mode == Mode.BRAIN:
                    brain(state.game, state.time_control, state)

            state.legal_fens = compute_legal_fens(state.game.copy())  # calc. new legal moves based on alt. move
            state.last_legal_fens = []

        # Player has done the computer or remote move on the board
        elif fen == state.done_computer_fen:
            logging.info('done move detected')
            assert state.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.REMOTE, Mode.TRAINING), 'wrong mode: %s' % state.interaction_mode
            DisplayMsg.show(Message.COMPUTER_MOVE_DONE())

            state.best_move_posted = False
            state.game.push(state.done_move)
            state.done_computer_fen = None
            state.done_move = chess.Move.null()

            if online_mode() or emulation_mode():
                # for online or emulation engine the user time alraedy runs with move announcement
                # => subtract time between announcement and execution
                end_time_cmove_done = time.time()
                cmove_time = math.floor(end_time_cmove_done - start_time_cmove_done)
                if cmove_time > 0:
                    state.time_control.sub_online_time(state.game.turn, cmove_time)
                cmove_time = 0
                start_time_cmove_done = 0

            game_end = state.check_game_state()
            if game_end:
                update_elo(state, game_end.result)
                state.legal_fens = []
                state.legal_fens_after_cmove = []
                if online_mode():
                    stop_search_and_clock()
                    state.stop_fen_timer()
                stop_search_and_clock()
                if not pgn_mode():
                    DisplayMsg.show(game_end)
            else:
                state.searchmoves.reset()

                state.time_control.add_time(not state.game.turn)

                # molli new tournament time control
                if state.time_control.moves_to_go_orig > 0 and (state.game.fullmove_number - 1) == state.time_control.moves_to_go_orig:
                    state.time_control.add_game2(not state.game.turn)
                    t_player = False
                    msg = Message.TIMECONTROL_CHECK(player=t_player, movestogo=state.time_control.moves_to_go_orig, time1=state.time_control.game_time, time2=state.time_control.game_time2)
                    DisplayMsg.show(msg)

                if not online_mode() or state.game.fullmove_number > 1:
                    state.start_clock()
                else:
                    DisplayMsg.show(Message.EXIT_MENU())  # show clock
                    end_time_cmove_done = 0

                if state.interaction_mode == Mode.BRAIN:
                    brain(state.game, state.time_control, state)

                state.legal_fens = compute_legal_fens(state.game.copy())

                if pgn_mode():
                    log_pgn(state)
                    if state.game.turn == chess.WHITE:
                        if state.max_guess_white > 0:
                            if state.no_guess_white > state.max_guess_white:
                                state.last_legal_fens = []
                                get_next_pgn_move(state)
                        else:
                            state.last_legal_fens = []
                            get_next_pgn_move(state)
                    elif state.game.turn == chess.BLACK:
                        if state.max_guess_black > 0:
                            if state.no_guess_black > state.max_guess_black:
                                state.last_legal_fens = []
                                get_next_pgn_move(state)
                        else:
                            state.last_legal_fens = []
                            get_next_pgn_move(state)

            state.last_legal_fens = []
            newgame_happened = False

            if state.game.fullmove_number < 1:
                ModeInfo.reset_opening()
            if picotutor_mode(state) and state.dgtmenu.get_picoexplorer():
                op_eco, op_name, op_moves, op_in_book = state.picotutor.get_opening()
                if op_in_book and op_name:
                    ModeInfo.set_opening(state.book_in_use, str(op_name), op_eco)
                    DisplayMsg.show(Message.SHOW_TEXT(text_string=op_name))

        # molli: Premove/fast move: Player has done the computer move and his own move in rapid sequence
        elif fen in state.legal_fens_after_cmove and state.flag_premove and state.done_move != chess.Move.null():  # and state.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.TRAINING):
            logging.info('standard move after computer move detected')
            # molli: execute computer move first
            state.game.push(state.done_move)
            state.done_computer_fen = None
            state.done_move = chess.Move.null()
            state.best_move_posted = False
            state.searchmoves.reset()

            state.time_control.add_time(not state.game.turn)
            # molli new tournament time control
            if state.time_control.moves_to_go_orig > 0 and (state.game.fullmove_number - 1) == state.time_control.moves_to_go_orig:
                state.time_control.add_game2(not state.game.turn)
                t_player = False
                msg = Message.TIMECONTROL_CHECK(player=t_player, movestogo=state.time_control.moves_to_go_orig, time1=state.time_control.game_time, time2=state.time_control.game_time2)
                DisplayMsg.show(msg)

            if state.interaction_mode == Mode.BRAIN:
                brain(state.game, state.time_control, state)

            state.last_legal_fens = []
            state.legal_fens_after_cmove = []
            state.legal_fens = compute_legal_fens(state.game.copy())  # molli new legal fance based on cmove

            # standard user move handling
            legal_moves = list(state.game.legal_moves)
            move = legal_moves[state.legal_fens.index(fen)]
            user_move(move, sliding=False, state=state)
            state.last_legal_fens = state.legal_fens
            newgame_happened = False
            if state.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.REMOTE, Mode.TRAINING):
                state.legal_fens = []
            else:
                state.legal_fens = compute_legal_fens(state.game.copy())

        # Check if this is a previous legal position and allow user to restart from this position
        else:
            if state.take_back_locked or online_mode() or (emulation_mode() and not state.automatic_takeback):
                handled_fen = False
            else:
                handled_fen = False
                game_copy = copy.deepcopy(state.game)
                while game_copy.move_stack:
                    game_copy.pop()
                    if game_copy.board_fen() == fen:
                        handled_fen = True
                        logging.info('current game fen      : %s', state.game.fen())
                        logging.info('undoing game until fen: %s', fen)
                        stop_search_and_clock()
                        while len(game_copy.move_stack) < len(state.game.move_stack):
                            state.game.pop()

                            if picotutor_mode(state):
                                if state.best_move_posted:  # molli computer move already sent to tutor!
                                    state.picotutor.pop_last_move()
                                    state.best_move_posted = False
                                state.picotutor.pop_last_move()

                        # its a complete new pos, delete saved values
                        state.done_computer_fen = None
                        state.done_move = state.pb_move = chess.Move.null()
                        state.searchmoves.reset()
                        state.takeback_active = True
                        set_wait_state(Message.TAKE_BACK(game=state.game.copy()), state)  # new: force stop no matter if picochess turn

                        break

                if pgn_mode():  # molli pgn
                    log_pgn(state)
                    if state.max_guess_white > 0:
                        if state.game.turn == chess.WHITE:
                            if state.no_guess_white > state.max_guess_white:
                                get_next_pgn_move(state)
                    elif state.max_guess_black > 0:
                        if state.game.turn == chess.BLACK:
                            if state.no_guess_black > state.max_guess_black:
                                get_next_pgn_move(state)

        logging.debug('fen: %s result: %s', fen, handled_fen)
        state.stop_fen_timer()
        if handled_fen:
            flag_startup = False
            state.error_fen = None
            fen_error_occured = False
            if position_mode:
                tutor_str = 'POSOK'
                msg = Message.PICOTUTOR_MSG(eval_str=tutor_str, game=state.game.copy())
                DisplayMsg.show(msg)
                position_mode = False
                time.sleep(1)
                if not state.done_computer_fen:
                    state.start_clock()
                DisplayMsg.show(Message.EXIT_MENU())
        else:
            if fen == chess.STARTING_BOARD_FEN:
                pos960 = 518
                state.error_fen = None
                if position_mode:
                    tutor_str = 'POSOK'
                    msg = Message.PICOTUTOR_MSG(eval_str=tutor_str, game=state.game.copy())
                    DisplayMsg.show(msg)
                    position_mode = False
                    if not state.done_computer_fen:
                        state.start_clock()
                Observable.fire(Event.NEW_GAME(pos960=pos960))
            else:
                state.error_fen = fen
                start_fen_timer(state)

    def set_wait_state(msg: Message, state: PicochessState, start_search=True):
        global reset_auto
        """Enter engine waiting (normal mode) and maybe (by parameter) start pondering."""
        if not state.done_computer_fen:
            state.legal_fens = compute_legal_fens(state.game.copy())
            state.last_legal_fens = []
        if state.interaction_mode in (Mode.NORMAL, Mode.BRAIN):  # @todo handle Mode.REMOTE too
            if state.done_computer_fen:
                logging.debug('best move displayed, dont search and also keep play mode: %s', state.play_mode)
                start_search = False
            else:
                old_mode = state.play_mode
                state.play_mode = PlayMode.USER_WHITE if state.game.turn == chess.WHITE else PlayMode.USER_BLACK
                if old_mode != state.play_mode:
                    logging.debug('new play mode: %s', state.play_mode)
                    text = state.play_mode.value  # type: str
                    if state.play_mode == PlayMode.USER_BLACK:
                        user_color = chess.BLACK
                    else:
                        user_color = chess.WHITE
                    if picotutor_mode(state):
                        state.picotutor.set_user_color(user_color)
                    DisplayMsg.show(Message.PLAY_MODE(play_mode=state.play_mode, play_mode_text=state.dgttranslate.text(text)))
        if start_search:
            assert engine.is_waiting(), 'engine not waiting! thinking status: %s' % engine.is_thinking()
            # Go back to analysing or observing
            if state.interaction_mode == Mode.BRAIN and not state.done_computer_fen:
                brain(state.game, state.time_control, state)
            if state.interaction_mode in (Mode.ANALYSIS, Mode.KIBITZ, Mode.PONDER, Mode.TRAINING):
                analyse(state.game, msg)
                return
            if state.interaction_mode in (Mode.OBSERVE, Mode.REMOTE):
                analyse(state.game, msg)
                return
        if not reset_auto:
            if state.automatic_takeback:
                stop_search_and_clock()
                reset_auto = True
            DisplayMsg.show(msg)
        else:
            state.automatic_takeback = False
            state.takeback_active = False
            reset_auto = False
        state.stop_fen_timer()

    def get_engine_level_dict(engine_level):
        """Transfer an engine level to its level_dict plus an index."""
        for eng in EngineProvider.installed_engines:
            if eng['file'] == engine.get_file():
                level_list = sorted(eng['level_dict'])
                try:
                    level_index = level_list.index(engine_level)
                    return eng['level_dict'][level_list[level_index]], level_index
                except ValueError:
                    break
        return {}, None

    def engine_mode():
        ponder_mode = analyse_mode = False
        if state.interaction_mode == Mode.BRAIN:
            ponder_mode = True
        elif state.interaction_mode in (Mode.ANALYSIS, Mode.KIBITZ, Mode.OBSERVE, Mode.PONDER):
            analyse_mode = True
        engine.mode(ponder=ponder_mode, analyse=analyse_mode)

    def switch_online(state: PicochessState):
        color = ''

        if online_mode():
            login, own_color, own_user, opp_user, game_time, fischer_inc = read_online_user_info()
            logging.debug('molli own_color in switch_online [%s]', own_color)
            logging.debug('molli own_user in switch_online [%s]', own_user)
            logging.debug('molli opp_user in switch_online [%s]', opp_user)
            logging.debug('molli game_time in switch_online [%s]', game_time)
            logging.debug('molli fischer_inc in switch_online [%s]', fischer_inc)

            ModeInfo.set_online_mode(mode=True)
            ModeInfo.set_online_own_user(name=own_user)
            ModeInfo.set_online_opponent(name=opp_user)

            if len(own_color) > 1:
                color = own_color[2]
            else:
                color = own_color

            logging.debug('molli switch_online start timecontrol')
            state.set_online_tctrl(game_time, fischer_inc)
            state.time_control.reset_start_time()

            logging.debug('molli switch_online new_color: %s', color)
            if (color == 'b' or color == 'B') and state.game.turn == chess.WHITE and state.play_mode == PlayMode.USER_WHITE and state.done_move == chess.Move.null():
                # switch to black color for user and send a 'go' to the engine
                state.play_mode = PlayMode.USER_BLACK
                text = state.play_mode.value  # type: str
                msg = Message.PLAY_MODE(play_mode=state.play_mode, play_mode_text=state.dgttranslate.text(text))

                stop_search_and_clock()

                state.last_legal_fens = []
                state.legal_fens_after_cmove = []
                state.legal_fens = []

                think(state.game, state.time_control, msg, state)

        else:
            ModeInfo.set_online_mode(mode=False)

        if pgn_mode():
            ModeInfo.set_pgn_mode(mode=True)
        else:
            ModeInfo.set_pgn_mode(mode=False)

    def get_next_pgn_move(state: PicochessState):
        log_pgn(state)
        time.sleep(0.5)

        if state.max_guess_black > 0:
            state.no_guess_black = 1
        elif state.max_guess_white > 0:
            state.no_guess_white = 1

        if not engine.is_waiting():
            stop_search_and_clock()

        state.last_legal_fens = []
        state.legal_fens_after_cmove = []
        state.best_move_displayed = state.done_computer_fen
        if state.best_move_displayed:
            state.done_computer_fen = None
            state.done_move = state.pb_move = chess.Move.null()

        state.play_mode = PlayMode.USER_WHITE if state.play_mode == PlayMode.USER_BLACK else PlayMode.USER_BLACK
        msg = Message.SET_PLAYMODE(play_mode=state.play_mode)
        DisplayMsg.show(msg)
        msg = Message.COMPUTER_MOVE_DONE()

        if state.time_control.mode == TimeMode.FIXED:
            state.time_control.reset()

        state.legal_fens = []

        cond1 = state.game.turn == chess.WHITE and state.play_mode == PlayMode.USER_BLACK
        cond2 = state.game.turn == chess.BLACK and state.play_mode == PlayMode.USER_WHITE
        if cond1 or cond2:
            state.time_control.reset_start_time()
            think(state.game, state.time_control, msg, state)
        else:
            DisplayMsg.show(msg)
            state.start_clock()
            state.legal_fens = compute_legal_fens(state.game.copy())

    # Enable garbage collection - needed for engne swapping as objects orphaned
    gc.enable()

    # Command line argument parsing
    parser = configargparse.ArgParser(default_config_files=[os.path.join(os.path.dirname(__file__), 'picochess.ini')])
    parser.add_argument('-e', '--engine', type=str, help="UCI engine filename/path such as 'engines/armv7l/a-stockf'",
                        default=None)
    parser.add_argument('-el', '--engine-level', type=str, help='UCI engine level', default=None)
    parser.add_argument('-er', '--engine-remote', type=str,
                        help="UCI engine filename/path such as 'engines/armv7l/a-stockf'", default=None)
    parser.add_argument('-ers', '--engine-remote-server', type=str, help='adress of the remote engine server',
                        default=None)
    parser.add_argument('-eru', '--engine-remote-user', type=str, help='username for the remote engine server')
    parser.add_argument('-erp', '--engine-remote-pass', type=str, help='password for the remote engine server')
    parser.add_argument('-erk', '--engine-remote-key', type=str, help='key file for the remote engine server')
    parser.add_argument('-erh', '--engine-remote-home', type=str, help='engine home path for the remote engine server',
                        default='')
    parser.add_argument('-d', '--dgt-port', type=str,
                        help="enable dgt board on the given serial port such as '/dev/ttyUSB0'")
    parser.add_argument('-b', '--book', type=str, help="path of book such as 'books/b-flank.bin'",
                        default='books/h-varied.bin')
    parser.add_argument('-t', '--time', type=str, default='5 0',
                        help="Time settings <FixSec> or <StMin IncSec> like '10'(move) or '5 0'(game) or '3 2'(fischer) or '40 120 60' (tournament). \
                        All values must be below 999")
    parser.add_argument('-dept', '--depth', type=int, default=0, choices=range(0, 99), help="searchdepth per move for the engine")
    parser.add_argument('-node', '--node', type=int, default=0, choices=range(0, 99), help="search nodes per move for the engine")
    parser.add_argument('-norl', '--disable-revelation-leds', action='store_true', help='disable Revelation leds')
    parser.add_argument('-l', '--log-level', choices=['notset', 'debug', 'info', 'warning', 'error', 'critical'],
                        default='warning', help='logging level')
    parser.add_argument('-lf', '--log-file', type=str, help='log to the given file')
    parser.add_argument('-pf', '--pgn-file', type=str, help='pgn file used to store the games', default='games.pgn')
    parser.add_argument('-pu', '--pgn-user', type=str, help='user name for the pgn file', default=None)
    parser.add_argument('-pe', '--pgn-elo', type=str,
                        help='user elo for the pgn file, also used for auto-adjusting the elo', default='-')
    parser.add_argument('-w', '--web-server', dest='web_server_port', nargs='?', const=80, type=int, metavar='PORT',
                        help='launch web server')
    parser.add_argument('-m', '--email', type=str, help='email used to send pgn/log files', default=None)
    parser.add_argument('-ms', '--smtp-server', type=str, help='adress of email server', default=None)
    parser.add_argument('-mu', '--smtp-user', type=str, help='username for email server', default=None)
    parser.add_argument('-mp', '--smtp-pass', type=str, help='password for email server', default=None)
    parser.add_argument('-me', '--smtp-encryption', action='store_true',
                        help='use ssl encryption connection to email server')
    parser.add_argument('-mf', '--smtp-from', type=str, help='From email', default='no-reply@picochess.org')
    parser.add_argument('-mk', '--mailgun-key', type=str, help='key used to send emails via Mailgun Webservice',
                        default=None)
    parser.add_argument('-bc', '--beep-config', choices=['none', 'some', 'all', 'sample'], help='sets standard beep config',
                        default='some')
    parser.add_argument('-bs', '--beep-some-level', type=int, default=0x03,
                        help='sets (some-)beep level from 0(=no beeps) to 15(=all beeps)')
    parser.add_argument('-uv', '--user-voice', type=str, help='voice for user', default=None)
    parser.add_argument('-cv', '--computer-voice', type=str, help='voice for computer', default=None)
    parser.add_argument('-sv', '--speed-voice', type=int, help='voice speech factor from 0(=90%%) to 9(=135%%)',
                        default=2, choices=range(0, 10))
    parser.add_argument('-vv', '--volume-voice', type=int, help='voice volume factor from 0(=50%%) to 10(=100%%)', default=10, choices=range(0, 11))
    parser.add_argument('-sp', '--enable-setpieces-voice', action='store_true',
                        help="speak last computer move again when 'set pieces' displayed")
    parser.add_argument('-u', '--enable-update', action='store_true', help='enable picochess updates')
    parser.add_argument('-ur', '--enable-update-reboot', action='store_true', help='reboot system after update')
    parser.add_argument('-nocm', '--disable-confirm-message', action='store_true', help='disable confirmation messages')
    parser.add_argument('-v', '--version', action='version', version='%(prog)s version {}'.format(version),
                        help='show current version', default=None)
    parser.add_argument('-pi', '--dgtpi', action='store_true', help='use the DGTPi hardware')
    parser.add_argument('-pt', '--ponder-interval', type=int, default=3, choices=range(1, 9),
                        help='how long each part of ponder display should be visible (default=3secs)')
    parser.add_argument('-lang', '--language', choices=['en', 'de', 'nl', 'fr', 'es', 'it'], default='en',
                        help='picochess language')
    parser.add_argument('-c', '--enable-console', action='store_true', help='use console interface')
    parser.add_argument('-cl', '--enable-capital-letters', action='store_true', help='clock messages in capital letters')
    parser.add_argument('-noet', '--disable-et', action='store_true', help='some clocks need this to work - deprecated')
    parser.add_argument('-ss', '--slow-slide', type=int, default=0, choices=range(0, 10),
                        help='extra wait time factor for a stable board position (sliding detect)')
    parser.add_argument('-nosn', '--disable-short-notation', action='store_true', help='disable short notation')
    parser.add_argument('-comf', '--comment-factor', type=int, help='comment factor from 0 to 100 for voice and written commands', default=100, choices=range(0, 100))
    parser.add_argument('-roln', '--rolling-display-normal', action='store_true', help='switch on rolling display normal mode')
    parser.add_argument('-rolp', '--rolling-display-ponder', action='store_true', help='switch on rolling display ponder mode')
    parser.add_argument('-flex', '--flexible-analysis', action='store_false', help='switch off flexible analysis mode')
    parser.add_argument('-prem', '--premove', action='store_false', help='switch off premove detection')
    parser.add_argument('-ctga', '--continue-game', action='store_true', help='continue last game after (re)start of picochess')
    parser.add_argument('-seng', '--show-engine', action='store_false', help='show engine after startup and new game')
    parser.add_argument('-teng', '--tutor-engine', type=str, default='/opt/picochess/engines/armv7l/a-stockf', help='engine used for PicoTutor analysis')
    parser.add_argument('-watc', '--tutor-watcher', action='store_true', help='Pico Watcher: atomatic move evaluation, blunder warning & move suggestion, default is off')
    parser.add_argument('-coch', '--tutor-coach', action='store_true', help='Pico Coach: move and position evaluation, move suggestion etc. on demand, default is off')
    parser.add_argument('-open', '--tutor-explorer', action='store_true', help='Pico Opening Explorer: shows the name(s) of the opening (based on ECO file), default is off')
    parser.add_argument('-tcom', '--tutor-comment', type=str, default='off', help='show game comments based on specific engines (=single) or in general (=all). Default value is off')
    parser.add_argument('-loc', '--location', type=str, default='auto', help='determine automatically location for pgn file if set to auto, otherwise the location string which is set will be used')
    parser.add_argument('-dtcs', '--def-timectrl', type=str, default='5 0', help='default time control setting when leaving an emulation engine after startup')
    parser.add_argument('-altm', '--alt-move', action='store_true', help='Playing direct alternative move for pico: default is off')
    parser.add_argument('-odec', '--online-decrement', type=float, default=2.0, help='Seconds to be subtracted after each own online move in order to sync with server times')
    parser.add_argument('-board', '--board-type', type=str, default='dgt', help='Type of e-board: "dgt", "certabo", "chesslink", "chessnut" or "noeboard" (for basic web-play only), default is "dgt"')
    parser.add_argument('-theme', '--theme', type=str, default='dark', help='Web theme, "light", "dark" , "auto" or blank, default is "dark", leave blank for another light theme, or auto for a sunrise/sunset dependent theme setting')
    parser.add_argument('-rspeed', '--rspeed', type=str, default='1.0', help='RetroSpeed factor for mame eingines, 0.0 for fullspeed, 1.0 for original speed, 0.5 for half of the original speed or any other value from 0.0 to 7.0')
    parser.add_argument('-ratdev', '--rating-deviation', type=str, help='Player rating deviation for automatic adjustment of ELO', default=350)
    args, unknown = parser.parse_known_args()

    # Enable logging
    if args.log_file:
        handler = RotatingFileHandler('logs' + os.sep + args.log_file, maxBytes=1 * 1024 * 1024, backupCount=5)
        logging.basicConfig(level=getattr(logging, args.log_level.upper()),
                            format='%(asctime)s.%(msecs)03d %(levelname)7s %(module)10s - %(funcName)s: %(message)s',
                            datefmt="%Y-%m-%d %H:%M:%S", handlers=[handler])
    logging.getLogger('chess.engine').setLevel(logging.INFO)  # don't want to get so many python-chess uci messages

    logging.debug('#' * 20 + ' PicoChess v%s ' + '#' * 20, version)
    # log the startup parameters but hide the password fields
    a_copy = copy.copy(vars(args))
    a_copy['mailgun_key'] = a_copy['smtp_pass'] = a_copy['engine_remote_key'] = a_copy['engine_remote_pass'] = '*****'
    logging.debug('startup parameters: %s', a_copy)
    if unknown:
        logging.warning('invalid parameter given %s', unknown)

    EngineProvider.init()

    Rev2Info.set_dgtpi(args.dgtpi)
    flag_pgn_game_over = False
    state.flag_flexible_ponder = args.flexible_analysis
    state.flag_premove = args.premove
    own_user = ''
    opp_user = ''
    game_time = 0
    fischer_inc = 0
    login = ''
    state.set_location = args.location
    state.online_decrement = args.online_decrement

    # wire some dgt classes
    if args.board_type.lower() == 'chesslink':
        dgtboard: EBoard = ChessLinkBoard()
    elif args.board_type.lower() == 'chessnut':
        dgtboard = ChessnutBoard()
    elif args.board_type.lower() == 'certabo':
        dgtboard = CertaboBoard()
    else:
        dgtboard = DgtBoard(args.dgt_port, args.disable_revelation_leds, args.dgtpi, args.disable_et, args.slow_slide)
    state.dgttranslate = DgtTranslate(args.beep_config, args.beep_some_level, args.language, version)
    state.dgtmenu = DgtMenu(args.disable_confirm_message, args.ponder_interval,
                            args.user_voice, args.computer_voice, args.speed_voice, args.enable_capital_letters,
                            args.disable_short_notation, args.log_file, args.engine_remote_server,
                            args.rolling_display_normal, max(0, min(10, args.volume_voice)), args.board_type, args.theme, round(float(args.rspeed), 2),
                            args.rolling_display_ponder, args.show_engine, args.tutor_coach, args.tutor_watcher,
                            args.tutor_explorer, PicoComment.from_str(args.tutor_comment),
                            args.continue_game, args.alt_move,
                            state.dgttranslate)

    dgtdispatcher = Dispatcher(state.dgtmenu)

    tutor_engine = args.tutor_engine

    logging.debug('node %s', args.node)

    state.time_control, time_text = state.transfer_time(args.time.split(), depth=args.depth, node=args.node)
    state.tc_init_last = state.time_control.get_parameters()
    time_text.beep = False

    # The class dgtDisplay fires Event (Observable) & DispatchDgt (Dispatcher)
    DgtDisplay(state.dgttranslate, state.dgtmenu, state.time_control).start()

    # Create PicoTalker for speech output
    # molli: add probability factor for game comments args.com_fact
    state.com_factor = args.comment_factor
    logging.debug('molli: probability factor for game comments args.comment_factor %s', state.com_factor)
    state.com_factor = args.comment_factor
    if args.beep_config == 'sample':
        beeper = True
    else:
        beeper = False
    PicoTalkerDisplay(args.user_voice, args.computer_voice, args.speed_voice, args.enable_setpieces_voice, state.com_factor, beeper).start()

    # Launch web server
    if args.web_server_port:
        WebServer(args.web_server_port, dgtboard, calc_theme(args.theme, state.set_location)).start()
        dgtdispatcher.register('web')

    if args.board_type.lower() == 'noeboard':
        logging.debug('starting PicoChess in no eboard mode')
    else:
        # Connect to DGT board
        logging.debug('starting PicoChess in board mode')
        if args.dgtpi:
            DgtPi(dgtboard).start()
            dgtdispatcher.register('i2c')
        else:
            logging.debug('(ser) starting the board connection')
            dgtboard.run()  # a clock can only be online together with the board, so we must start it infront
        DgtHw(dgtboard).start()
        dgtdispatcher.register('ser')

    # The class Dispatcher sends DgtApi messages at the correct (delayed) time out
    dgtdispatcher.start()

    # Save to PGN
    emailer = Emailer(email=args.email, mailgun_key=args.mailgun_key)
    emailer.set_smtp(sserver=args.smtp_server, suser=args.smtp_user, spass=args.smtp_pass,
                     sencryption=args.smtp_encryption, sfrom=args.smtp_from)

    PgnDisplay('games' + os.sep + args.pgn_file, emailer).start()
    if args.pgn_user:
        user_name = args.pgn_user
    else:
        if args.email:
            user_name = args.email.split('@')[0]
        else:
            user_name = 'Player'

    # Update
    if args.enable_update:
        update_picochess(args.dgtpi, args.enable_update_reboot, state.dgttranslate)

    #################################################

    ip_info_thread = threading.Timer(12, display_ip_info, args=[state])  # give RaspberyPi 10sec time to startup its network devices
    ip_info_thread.start()

    state.fen_timer = threading.Timer(4, expired_fen_timer, args=[state])
    state.fen_timer_running = False
    ###########################################

    # try the given engine first and if that fails the first from "engines.ini" then exit
    engine_file = args.engine

    engine_remote_home = args.engine_remote_home.rstrip(os.sep)

    engine_name = None
    uci_remote_shell = None

    uci_local_shell = UciShell(hostname='', username='', key_file='', password='')

    if engine_file is None:
        engine_file = EngineProvider.installed_engines[0]['file']

    engine = UciEngine(file=engine_file, uci_shell=uci_local_shell,
                       retrospeed=get_engine_rspeed_par(state.dgtmenu.get_engine_rspeed()))
    try:
        engine_name = engine.get_name()
    except AttributeError:
        logging.error('engine %s not started', engine_file)
        time.sleep(3)
        DisplayMsg.show(Message.ENGINE_FAIL())
        time.sleep(2)
        sys.exit(-1)

    # Startup - internal
    state.game = chess.Board()  # Create the current game
    fen = state.game.fen()
    state.legal_fens = compute_legal_fens(state.game.copy())  # Compute the legal FENs
    is_out_of_time_already = False  # molli: out of time message only once
    flag_startup = True

    all_books = get_opening_books()
    try:
        book_index = [book['file'] for book in all_books].index(args.book)
    except ValueError:
        logging.warning('selected book not present, defaulting to %s', all_books[7]['file'])
        book_index = 7
    state.book_in_use = args.book
    bookreader = chess.polyglot.open_reader(all_books[book_index]['file'])
    state.searchmoves = AlternativeMover()

    if args.pgn_elo and args.pgn_elo.isnumeric() and args.rating_deviation:
        state.rating = Rating(float(args.pgn_elo), float(args.rating_deviation))
    args.engine_level = None if args.engine_level == 'None' else args.engine_level
    if args.engine_level == '""':
        args.engine_level = None
    engine_opt, level_index = get_engine_level_dict(args.engine_level)
    engine.startup(engine_opt, state.rating)

    # Startup - external
    state.engine_level = args.engine_level
    state.old_engine_level = state.engine_level
    state.new_engine_level = state.engine_level

    if state.engine_level:
        level_text = state.dgttranslate.text('B00_level', state.engine_level)
        level_text.beep = False
    else:
        level_text = None
        state.engine_level = ''

    sys_info = {'version': version, 'engine_name': engine_name, 'user_name': user_name, 'user_elo': args.pgn_elo, 'rspeed': round(float(args.rspeed), 2)}

    DisplayMsg.show(Message.SYSTEM_INFO(info=sys_info))
    DisplayMsg.show(Message.STARTUP_INFO(info={'interaction_mode': state.interaction_mode, 'play_mode': state.play_mode,
                                               'books': all_books, 'book_index': book_index,
                                               'level_text': level_text, 'level_name': state.engine_level,
                                               'tc_init': state.time_control.get_parameters(), 'time_text': time_text}))

    DisplayMsg.show(Message.ENGINE_SETUP())
    # engines setup
    DisplayMsg.show(Message.ENGINE_STARTUP(installed_engines=EngineProvider.installed_engines, file=engine.get_file(), level_index=level_index, has_960=engine.has_chess960(), has_ponder=engine.has_ponder()))
    update_elo_display(state)

    # set timecontrol restore data set for normal engines after leaving emulation mode
    pico_time = args.def_timectrl

    if emulation_mode():
        flag_last_engine_emu = True
        time_control_l, time_text_l = state.transfer_time(pico_time.split(), depth=0, node=0)
        state.tc_init_last = time_control_l.get_parameters()

    if pgn_mode():
        ModeInfo.set_pgn_mode(mode=True)
        flag_last_engine_pgn = True
        det_pgn_guess_tctrl(state)
    else:
        ModeInfo.set_pgn_mode(mode=False)

    if online_mode():
        ModeInfo.set_online_mode(mode=True)
        set_wait_state(Message.START_NEW_GAME(game=state.game.copy(), newgame=True), state)
    else:
        ModeInfo.set_online_mode(mode=False)
        engine.newgame(state.game.copy())

    DisplayMsg.show(Message.PICOCOMMENT(picocomment='ok'))

    state.comment_file = get_comment_file()
    state.picotutor = PicoTutor(i_engine_path=tutor_engine, i_comment_file=state.comment_file, i_lang=args.language)
    state.picotutor.set_status(state.dgtmenu.get_picowatcher(), state.dgtmenu.get_picocoach(), state.dgtmenu.get_picoexplorer(), state.dgtmenu.get_picocomment())

    ModeInfo.set_game_ending(result='*')

    state.dgtmenu.set_state_current_engine(engine_file)
    text: Dgt.DISPLAY_TEXT = state.dgtmenu.get_current_engine_name()
    state.engine_text = text
    state.dgtmenu.enter_top_menu()

    if state.dgtmenu.get_enginename():
        DisplayMsg.show(Message.ENGINE_NAME(engine_name=state.engine_text))

    # Event loop
    logging.info('evt_queue ready')
    while True:
        try:
            event = evt_queue.get()
        except queue.Empty:
            pass
        else:
            logging.debug('received event from evt_queue: %s', event)
            if False:  # switch-case
                pass
            elif isinstance(event, Event.FEN):
                process_fen(event.fen, state)

            elif isinstance(event, Event.KEYBOARD_MOVE):
                move = event.move
                logging.debug('keyboard move [%s]', move)
                if move not in state.game.legal_moves:
                    logging.warning('illegal move. fen: [%s]', state.game.fen())
                else:
                    game_copy = state.game.copy()
                    game_copy.push(move)
                    fen = game_copy.board_fen()
                    DisplayMsg.show(Message.DGT_FEN(fen=fen, raw=False))

            elif isinstance(event, Event.LEVEL):
                if event.options:
                    engine.startup(event.options, state.rating)
                state.new_engine_level = event.level_name
                DisplayMsg.show(Message.LEVEL(level_text=event.level_text, level_name=event.level_name,
                                              do_speak=bool(event.options)))

            elif isinstance(event, Event.NEW_ENGINE):
                old_file = engine.get_file()
                old_options = {}
                old_options = engine.get_pgn_options()
                engine_fallback = False
                # Stop the old engine cleanly
                if not emulation_mode():
                    stop_search()
                # Closeout the engine process and threads

                engine_file = event.eng['file']
                help_str = engine_file.rsplit(os.sep, 1)[1]
                remote_file = engine_remote_home + os.sep + help_str

                flag_eng = False
                flag_eng = check_ssh(args.engine_remote_server, args.engine_remote_user, args.engine_remote_pass)

                logging.debug('molli check_ssh:%s', flag_eng)
                DisplayMsg.show(Message.ENGINE_SETUP())

                if remote_engine_mode():
                    if flag_eng:
                        if not uci_remote_shell:
                            if remote_windows():
                                logging.info('molli: Remote Windows Connection')
                                uci_remote_shell = UciShell(hostname=args.engine_remote_server, username=args.engine_remote_user, key_file=args.engine_remote_key, password=args.engine_remote_pass, windows=True)
                            else:
                                logging.info('molli: Remote Mac/UNIX Connection')
                                uci_remote_shell = UciShell(hostname=args.engine_remote_server, username=args.engine_remote_user, key_file=args.engine_remote_key, password=args.engine_remote_pass)
                    else:
                        engine_fallback = True
                        DisplayMsg.show(Message.ONLINE_FAILED())
                        time.sleep(2)
                        DisplayMsg.show(Message.REMOTE_FAIL())
                        time.sleep(2)

                if engine.quit():
                    # Load the new one and send args.
                    if remote_engine_mode() and flag_eng and uci_remote_shell:
                        engine = UciEngine(file=remote_file, uci_shell=uci_remote_shell,
                                           retrospeed=get_engine_rspeed_par(state.dgtmenu.get_engine_rspeed()))
                    else:
                        engine = UciEngine(file=engine_file, uci_shell=uci_local_shell,
                                           retrospeed=get_engine_rspeed_par(state.dgtmenu.get_engine_rspeed()))
                    try:
                        engine_name = engine.get_name()
                    except AttributeError:
                        # New engine failed to start, restart old engine
                        logging.error('new engine failed to start, reverting to %s', old_file)
                        engine_fallback = True
                        event.options = old_options
                        engine_file = old_file
                        help_str = old_file.rsplit(os.sep, 1)[1]
                        remote_file = engine_remote_home + os.sep + help_str

                        if remote_engine_mode() and flag_eng and uci_remote_shell:
                            engine = UciEngine(file=remote_file, uci_shell=uci_remote_shell,
                                               retrospeed=get_engine_rspeed_par(state.dgtmenu.get_engine_rspeed()))
                        else:
                            engine = UciEngine(file=old_file, uci_shell=uci_local_shell,
                                               retrospeed=get_engine_rspeed_par(state.dgtmenu.get_engine_rspeed()))
                        try:
                            engine_name = engine.get_name()
                        except AttributeError:
                            # Help - old engine failed to restart. There is no engine
                            logging.error('no engines started')
                            DisplayMsg.show(Message.ENGINE_FAIL())
                            time.sleep(3)
                            sys.exit(-1)

                    # All done - rock'n'roll
                    if state.interaction_mode == Mode.BRAIN and not engine.has_ponder():
                        logging.debug('new engine doesnt support brain mode, reverting to %s', old_file)
                        engine_fallback = True
                        if engine.quit():
                            if remote_engine_mode() and flag_eng and uci_remote_shell:
                                engine = UciEngine(file=remote_file, uci_shell=uci_remote_shell,
                                                   retrospeed=get_engine_rspeed_par(state.dgtmenu.get_engine_rspeed()))
                            else:
                                engine = UciEngine(file=old_file, uci_shell=uci_local_shell,
                                                   retrospeed=get_engine_rspeed_par(state.dgtmenu.get_engine_rspeed()))
                            engine.startup(old_options, state.rating)
                            engine.newgame(state.game.copy())
                            try:
                                engine_name = engine.get_name()
                            except AttributeError:
                                logging.error('no engines started')
                                DisplayMsg.show(Message.ENGINE_FAIL())
                                time.sleep(3)
                                sys.exit(-1)
                        else:
                            logging.error('engine shutdown failure')
                            DisplayMsg.show(Message.ENGINE_FAIL())

                    engine.startup(event.options, state.rating)

                    if online_mode():
                        state.stop_clock()
                        DisplayMsg.show(Message.ONLINE_LOGIN())
                        # check if login successful (correct server & correct user)
                        login, own_color, own_user, opp_user, game_time, fischer_inc = read_online_user_info()
                        logging.debug('molli online login: %s', login)

                        if 'ok' not in login:
                            # server connection failed: check settings!
                            DisplayMsg.show(Message.ONLINE_FAILED())
                            time.sleep(3)
                            engine_fallback = True
                            event.options = dict()
                            old_file = 'engines/armv7l/a-stockf'
                            help_str = old_file.rsplit(os.sep, 1)[1]
                            remote_file = engine_remote_home + os.sep + help_str

                            if remote_engine_mode() and flag_eng and uci_remote_shell:
                                engine = UciEngine(file=remote_file, uci_shell=uci_remote_shell,
                                                   retrospeed=get_engine_rspeed_par(state.dgtmenu.get_engine_rspeed()))
                            else:
                                engine = UciEngine(file=old_file, uci_shell=uci_local_shell,
                                                   retrospeed=get_engine_rspeed_par(state.dgtmenu.get_engine_rspeed()))
                            try:
                                engine_name = engine.get_name()
                            except AttributeError:
                                # Help - old engine failed to restart. There is no engine
                                logging.error('no engines started')
                                DisplayMsg.show(Message.ENGINE_FAIL())
                                time.sleep(3)
                                sys.exit(-1)
                            engine.startup(event.options, state.rating)
                        else:
                            time.sleep(2)
                    elif emulation_mode() or pgn_mode():
                        # molli for emulation engine we have to reset to starting position
                        stop_search_and_clock()
                        state.game = chess.Board()
                        state.game.turn = chess.WHITE
                        state.play_mode = PlayMode.USER_WHITE
                        engine.newgame(state.game.copy())
                        state.done_computer_fen = None
                        state.done_move = state.pb_move = chess.Move.null()
                        state.searchmoves.reset()
                        state.game_declared = False
                        state.legal_fens = compute_legal_fens(state.game.copy())
                        state.last_legal_fens = []
                        state.legal_fens_after_cmove = []
                        is_out_of_time_already = False
                    else:
                        engine.newgame(state.game.copy())

                    engine_mode()

                    if engine_fallback:
                        msg = Message.ENGINE_FAIL()
                        # molli: in case of engine fail, set correct old engine display settings
                        for index in range(0, len(EngineProvider.installed_engines)):
                            if EngineProvider.installed_engines[index]['file'] == old_file:
                                logging.debug('molli index:%s', str(index))
                                state.dgtmenu.set_engine_index(index)
                        # in case engine fails, reset level as well
                        if state.old_engine_level:
                            level_text = state.dgttranslate.text('B00_level', state.old_engine_level)
                            level_text.beep = False
                        else:
                            level_text = None
                        DisplayMsg.show(Message.LEVEL(level_text=level_text, level_name=state.old_engine_level,
                                                      do_speak=False))
                        state.new_engine_level = state.old_engine_level
                    else:
                        state.searchmoves.reset()
                        msg = Message.ENGINE_READY(eng=event.eng, engine_name=engine_name,
                                                   eng_text=event.eng_text, has_levels=engine.has_levels(),
                                                   has_960=engine.has_chess960(), has_ponder=engine.has_ponder(),
                                                   show_ok=event.show_ok)
                    # Schedule cleanup of old objects
                    gc.collect()

                    set_wait_state(msg, state, not engine_fallback)
                    if state.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.TRAINING):   # engine isnt started/searching => stop the clock
                        state.stop_clock()
                    state.engine_text = state.dgtmenu.get_current_engine_name()
                    state.dgtmenu.exit_menu()
                else:
                    logging.error('engine shutdown failure')
                    DisplayMsg.show(Message.ENGINE_FAIL())

                state.old_engine_level = state.new_engine_level
                state.engine_level = state.new_engine_level
                state.dgtmenu.set_state_current_engine(engine_file)
                state.dgtmenu.exit_menu()
                # here dont care if engine supports pondering, cause Mode.NORMAL from startup
                if not remote_engine_mode() and not online_mode() and not pgn_mode() and not engine_fallback:
                    # dont write engine(_level) if remote/online engine or engine failure
                    write_picochess_ini('engine', event.eng['file'])
                    write_picochess_ini('engine-level', state.engine_level)

                if pgn_mode():
                    if not flag_last_engine_pgn:
                        state.tc_init_last = state.time_control.get_parameters()

                    det_pgn_guess_tctrl(state)

                    flag_last_engine_pgn = True
                elif emulation_mode():
                    if not flag_last_engine_emu:
                        state.tc_init_last = state.time_control.get_parameters()
                    flag_last_engine_emu = True
                else:
                    # molli restore last saved timecontrol
                    if (flag_last_engine_pgn or flag_last_engine_emu) and state.tc_init_last is not None and not online_mode() and not emulation_mode() and not pgn_mode():
                        state.stop_clock()
                        text = state.dgttranslate.text('N00_oktime')
                        Observable.fire(Event.SET_TIME_CONTROL(tc_init=state.tc_init_last, time_text=text, show_ok=True))
                        state.stop_clock()
                        DisplayMsg.show(Message.EXIT_MENU())
                    flag_last_engine_pgn = False
                    flag_last_engine_emu = False
                    state.tc_init_last = None

                state.comment_file = get_comment_file()  # for picotutor game comments like Boris & Sargon
                state.picotutor.init_comments(state.comment_file)

                if pgn_mode() or emulation_mode():
                    # molli: in these cases we can't continue from current position but
                    #        have to start a new game
                    if emulation_mode():
                        set_emulation_tctrl(state)
                    # prepare new game
                    if pgn_mode():
                        pgn_game_name, pgn_problem, pgn_fen, pgn_result, pgn_white, pgn_black = read_pgn_info()
                        if 'mate in' in pgn_problem or 'Mate in' in pgn_problem:
                            set_fen_from_pgn(pgn_fen, state)
                            state.play_mode = PlayMode.USER_WHITE if state.game.turn == chess.WHITE else PlayMode.USER_BLACK
                            msg = Message.PLAY_MODE(play_mode=state.play_mode, play_mode_text=state.dgttranslate.text(state.play_mode.value))
                            DisplayMsg.show(msg)
                            time.sleep(1)
                    pos960 = 518
                    Observable.fire(Event.NEW_GAME(pos960=pos960))

                if online_mode():
                    ModeInfo.set_online_mode(mode=True)
                    logging.debug('online game fen: %s', state.game.fen())
                    if (not flag_last_engine_online) or (state.game.board_fen() == chess.STARTING_BOARD_FEN):
                        pos960 = 518
                        Observable.fire(Event.NEW_GAME(pos960=pos960))
                    flag_last_engine_online = True
                else:
                    flag_last_engine_online = False
                    ModeInfo.set_online_mode(mode=False)

                if pgn_mode():
                    ModeInfo.set_pgn_mode(mode=True)
                else:
                    ModeInfo.set_pgn_mode(mode=False)

                update_elo_display(state)

            elif isinstance(event, Event.SETUP_POSITION):
                logging.debug('setting up custom fen: %s', event.fen)
                uci960 = event.uci960

                if state.game.move_stack:
                    if not (state.game.is_game_over() or state.game_declared):
                        result = GameResult.ABORT
                        DisplayMsg.show(Message.GAME_ENDS(tc_init=state.time_control.get_parameters(), result=result, play_mode=state.play_mode, game=state.game.copy()))
                state.game = chess.Board(event.fen, uci960)
                # see new_game
                stop_search_and_clock()
                if engine.has_chess960():
                    engine.option('UCI_Chess960', uci960)
                    engine.send()

                engine.newgame(state.game.copy())
                state.done_computer_fen = None
                state.done_move = state.pb_move = chess.Move.null()
                state.legal_fens_after_cmove = []
                is_out_of_time_already = False
                state.time_control.reset()
                state.searchmoves.reset()
                state.game_declared = False
                if picotutor_mode(state):
                    state.picotutor.reset()
                    state.picotutor.set_position(state.game.fen(), i_turn=state.game.turn)
                    if state.play_mode == PlayMode.USER_BLACK:
                        state.picotutor.set_user_color(chess.BLACK)
                    else:
                        state.picotutor.set_user_color(chess.WHITE)
                set_wait_state(Message.START_NEW_GAME(game=state.game.copy(), newgame=True), state)

            elif isinstance(event, Event.NEW_GAME):
                last_move_no = state.game.fullmove_number
                state.takeback_active = False
                flag_startup = False
                flag_pgn_game_over = False
                ModeInfo.set_game_ending(result='*')  # initialize game result for game saving status
                engine_name = engine.get_name()
                position_mode = False
                fen_error_occured = False
                newgame_happened = True
                newgame = state.game.move_stack or (state.game.chess960_pos() != event.pos960)

                if newgame:
                    logging.debug('starting a new game with code: %s', event.pos960)
                    uci960 = event.pos960 != 518

                    if not (state.game.is_game_over() or state.game_declared):

                        if emulation_mode():  # force abortion for mame ## molli mame enhance
                            if state.is_not_user_turn():
                                # clock must be stopped BEFORE the "book_move" event cause SetNRun resets the clock display
                                state.stop_clock()
                                state.best_move_posted = True
                                # @todo 8/8/R6P/1R6/7k/2B2K1p/8/8 and sliding Ra6 over a5 to a4 - handle this in correct way!!
                                state.game_declared = True
                                state.stop_fen_timer()
                                state.legal_fens_after_cmove = []

                        result = GameResult.ABORT
                        DisplayMsg.show(Message.GAME_ENDS(tc_init=state.time_control.get_parameters(), result=result, play_mode=state.play_mode, game=state.game.copy()))
                        time.sleep(0.3)

                    state.game = chess.Board()
                    state.game.turn = chess.WHITE

                    if uci960:
                        state.game.set_chess960_pos(event.pos960)

                    if state.play_mode != PlayMode.USER_WHITE:
                        state.play_mode = PlayMode.USER_WHITE
                        msg = Message.PLAY_MODE(play_mode=state.play_mode,
                                                play_mode_text=state.dgttranslate.text(str(state.play_mode.value)))
                        DisplayMsg.show(msg)
                    stop_search_and_clock()

                    # see setup_position
                    if engine.has_chess960():
                        engine.option('UCI_Chess960', uci960)
                        engine.send()

                    if state.interaction_mode == Mode.TRAINING:
                        engine.stop()

                    if online_mode():
                        DisplayMsg.show(Message.SEEKING())
                        engine.stop()
                        seeking_flag = True
                        state.stop_fen_timer()
                        ModeInfo.set_online_mode(mode=True)
                    else:
                        ModeInfo.set_online_mode(mode=False)

                    if emulation_mode():
                        DisplayMsg.show(Message.ENGINE_SETUP())

                    engine.newgame(state.game.copy())

                    state.done_computer_fen = None
                    state.done_move = state.pb_move = chess.Move.null()
                    state.time_control.reset()
                    state.best_move_posted = False
                    state.searchmoves.reset()
                    state.game_declared = False
                    update_elo_display(state)

                    if online_mode():
                        time.sleep(0.5)
                        login, own_color, own_user, opp_user, game_time, fischer_inc = read_online_user_info()
                        if 'no_user' in own_user and not login == 'ok':
                            # user login failed check login settings!!!
                            DisplayMsg.show(Message.ONLINE_USER_FAILED())
                            time.sleep(3)
                        elif 'no_player' in opp_user:
                            # no opponent found start new game or engine again!!!
                            DisplayMsg.show(Message.ONLINE_NO_OPPONENT())
                            time.sleep(3)
                        else:
                            DisplayMsg.show(Message.ONLINE_NAMES(own_user=own_user, opp_user=opp_user))
                            time.sleep(3)
                        seeking_flag = False
                        state.best_move_displayed = None

                    state.legal_fens = compute_legal_fens(state.game.copy())
                    state.last_legal_fens = []
                    state.legal_fens_after_cmove = []
                    is_out_of_time_already = False
                    if pgn_mode():
                        if state.max_guess > 0:
                            state.max_guess_white = state.max_guess
                            state.max_guess_black = 0
                        pgn_game_name, pgn_problem, pgn_fen, pgn_result, pgn_white, pgn_black = read_pgn_info()
                        if 'mate in' in pgn_problem or 'Mate in' in pgn_problem:
                            set_fen_from_pgn(pgn_fen, state)
                    set_wait_state(Message.START_NEW_GAME(game=state.game.copy(), newgame=newgame), state)
                    if 'no_player' not in opp_user and 'no_user' not in own_user:
                        switch_online(state)

                else:
                    if online_mode():
                        logging.debug('starting a new game with code: %s', event.pos960)
                        uci960 = event.pos960 != 518
                        state.stop_clock()

                        state.game.turn = chess.WHITE

                        if uci960:
                            state.game.set_chess960_pos(event.pos960)

                        if state.play_mode != PlayMode.USER_WHITE:
                            state.play_mode = PlayMode.USER_WHITE
                            msg = Message.PLAY_MODE(play_mode=state.play_mode,
                                                    play_mode_text=state.dgttranslate.text(str(state.play_mode.value)))
                            DisplayMsg.show(msg)

                        # see setup_position
                        stop_search_and_clock()
                        state.stop_fen_timer()

                        if engine.has_chess960():
                            engine.option('UCI_Chess960', uci960)
                            engine.send()

                        state.time_control.reset()
                        state.searchmoves.reset()

                        DisplayMsg.show(Message.SEEKING())
                        engine.stop()
                        seeking_flag = True

                        engine.newgame(state.game.copy())

                        login, own_color, own_user, opp_user, game_time, fischer_inc = read_online_user_info()
                        if 'no_user' in own_user:
                            # user login failed check login settings!!!
                            DisplayMsg.show(Message.ONLINE_USER_FAILED())
                            time.sleep(3)
                        elif 'no_player' in opp_user:
                            # no opponent found start new game & search!!!
                            DisplayMsg.show(Message.ONLINE_NO_OPPONENT())
                            time.sleep(3)
                        else:
                            DisplayMsg.show(Message.ONLINE_NAMES(own_user=own_user, opp_user=opp_user))
                            time.sleep(1)
                        seeking_flag = False
                        state.best_move_displayed = None
                        state.done_computer_fen = None
                        state.done_move = state.pb_move = chess.Move.null()
                        state.legal_fens = compute_legal_fens(state.game.copy())
                        state.last_legal_fens = []
                        state.legal_fens_after_cmove = []
                        is_out_of_time_already = False
                        state.game_declared = False
                        set_wait_state(Message.START_NEW_GAME(game=state.game.copy(), newgame=newgame), state)
                        if 'no_player' not in opp_user and 'no_user' not in own_user:
                            switch_online(state)
                    else:
                        logging.debug('no need to start a new game')
                        if pgn_mode():
                            pgn_game_name, pgn_problem, pgn_fen, pgn_result, pgn_white, pgn_black = read_pgn_info()
                            if 'mate in' in pgn_problem or 'Mate in' in pgn_problem:
                                set_fen_from_pgn(pgn_fen, state)
                                set_wait_state(Message.START_NEW_GAME(game=state.game.copy(), newgame=newgame), state)
                            else:
                                DisplayMsg.show(Message.START_NEW_GAME(game=state.game.copy(), newgame=newgame))
                        else:
                            DisplayMsg.show(Message.START_NEW_GAME(game=state.game.copy(), newgame=newgame))

                if picotutor_mode(state):
                    state.picotutor.reset()
                    if not flag_startup:
                        if state.play_mode == PlayMode.USER_BLACK:
                            state.picotutor.set_user_color(chess.BLACK)
                        else:
                            state.picotutor.set_user_color(chess.WHITE)

                if state.interaction_mode != Mode.REMOTE and not online_mode():
                    if state.dgtmenu.get_enginename():
                        time.sleep(0.7)  # give time for ABORT message
                        DisplayMsg.show(Message.ENGINE_NAME(engine_name=state.engine_text))
                    if pgn_mode():
                        pgn_white = ''
                        pgn_black = ''
                        time.sleep(1)
                        pgn_game_name, pgn_problem, pgn_fen, pgn_result, pgn_white, pgn_black = read_pgn_info()

                        if not pgn_white:
                            pgn_white = '????'
                        DisplayMsg.show(Message.SHOW_TEXT(text_string=pgn_white))

                        DisplayMsg.show(Message.SHOW_TEXT(text_string='versus'))

                        if not pgn_black:
                            pgn_black = '????'
                        DisplayMsg.show(Message.SHOW_TEXT(text_string=pgn_black))

                        if pgn_result:
                            DisplayMsg.show(Message.SHOW_TEXT(text_string=pgn_result))
                        if 'mate in' in pgn_problem or 'Mate in' in pgn_problem:
                            DisplayMsg.show(Message.SHOW_TEXT(text_string=pgn_problem))
                        else:
                            DisplayMsg.show(Message.SHOW_TEXT(text_string=pgn_game_name))

                        # reset pgn guess counters
                        if last_move_no > 1:
                            state.no_guess_black = 1
                            state.no_guess_white = 1
                        else:
                            log_pgn(state)
                            if state.max_guess_white > 0:
                                if state.no_guess_white > state.max_guess_white:
                                    state.last_legal_fens = []
                                    get_next_pgn_move(state)

            elif isinstance(event, Event.PAUSE_RESUME):
                if pgn_mode():
                    engine.pause_pgn_audio()
                else:
                    if engine.is_thinking():
                        state.stop_clock()
                        engine.stop(show_best=True)
                    elif not state.done_computer_fen:
                        if state.time_control.internal_running():
                            state.stop_clock()
                        else:
                            state.start_clock()
                    else:
                        logging.debug('best move displayed, dont start/stop clock')

            elif isinstance(event, Event.ALTERNATIVE_MOVE):
                if state.done_computer_fen and not emulation_mode():
                    state.done_computer_fen = None
                    state.done_move = chess.Move.null()
                    if state.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.TRAINING):   # @todo handle Mode.REMOTE too
                        if state.time_control.mode == TimeMode.FIXED:
                            state.time_control.reset()
                        # set computer to move - in case the user just changed the engine
                        state.play_mode = PlayMode.USER_WHITE if state.game.turn == chess.BLACK else PlayMode.USER_BLACK
                        if not state.check_game_state():
                            if picotutor_mode(state):
                                state.picotutor.pop_last_move()
                            think(state.game, state.time_control, Message.ALTERNATIVE_MOVE(game=state.game.copy(), play_mode=state.play_mode), state, searchlist=True)
                    else:
                        logging.warning('wrong function call [alternative]! mode: %s', state.interaction_mode)

            elif isinstance(event, Event.SWITCH_SIDES):
                flag_startup = False
                DisplayMsg.show(Message.EXIT_MENU())

                if state.interaction_mode == Mode.PONDER:
                    # molli: allow switching sides in flexble ponder mode
                    fen = state.game.board_fen()

                    if state.game.turn == chess.WHITE:
                        fen += ' b KQkq - 0 1'
                    else:
                        fen += ' w KQkq - 0 1'
                    # ask python-chess to correct the castling string
                    bit_board = chess.Board(fen)
                    bit_board.set_fen(bit_board.fen())
                    if bit_board.is_valid():
                        state.game = chess.Board(bit_board.fen())
                        stop_search_and_clock()
                        engine.newgame(state.game.copy())
                        state.done_computer_fen = None
                        state.done_move = state.pb_move = chess.Move.null()
                        state.time_control.reset()
                        state.searchmoves.reset()
                        state.game_declared = False
                        state.legal_fens = compute_legal_fens(state.game.copy())
                        state.legal_fens_after_cmove = []
                        state.last_legal_fens = []
                        engine.position(copy.deepcopy(state.game))
                        engine.ponder()
                        state.play_mode = PlayMode.USER_WHITE if state.game.turn == chess.WHITE else PlayMode.USER_BLACK
                        msg = Message.PLAY_MODE(play_mode=state.play_mode, play_mode_text=state.dgttranslate.text(state.play_mode.value))
                        DisplayMsg.show(msg)
                    else:
                        logging.debug('illegal fen %s', fen)
                        DisplayMsg.show(Message.WRONG_FEN())
                        DisplayMsg.show(Message.EXIT_MENU())

                elif state.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.TRAINING):
                    if not engine.is_waiting():
                        stop_search_and_clock()
                    state.automatic_takeback = False
                    state.takeback_active = False
                    reset_auto = False
                    state.last_legal_fens = []
                    state.legal_fens_after_cmove = []
                    state.best_move_displayed = state.done_computer_fen
                    if state.best_move_displayed:
                        move = state.done_move
                        state.done_computer_fen = None
                        state.done_move = state.pb_move = chess.Move.null()
                    else:
                        move = chess.Move.null()  # not really needed

                    state.play_mode = PlayMode.USER_WHITE if state.play_mode == PlayMode.USER_BLACK else PlayMode.USER_BLACK
                    msg = Message.PLAY_MODE(play_mode=state.play_mode, play_mode_text=state.dgttranslate.text(state.play_mode.value))

                    if state.time_control.mode == TimeMode.FIXED:
                        state.time_control.reset()

                    if picotutor_mode(state):
                        if state.play_mode == PlayMode.USER_BLACK:
                            state.picotutor.set_user_color(chess.BLACK)
                        else:
                            state.picotutor.set_user_color(chess.WHITE)
                        if state.best_move_posted:
                            state.best_move_posted = False
                            state.picotutor.pop_last_move()

                    state.legal_fens = []

                    if pgn_mode():  # molli change pgn guessing game sides
                        if state.max_guess_black > 0:
                            state.max_guess_white = state.max_guess_black
                            state.max_guess_black = 0
                        elif state.max_guess_white > 0:
                            state.max_guess_black = state.max_guess_white
                            state.max_guess_white = 0
                        state.no_guess_black = 1
                        state.no_guess_white = 1

                    cond1 = state.game.turn == chess.WHITE and state.play_mode == PlayMode.USER_BLACK
                    cond2 = state.game.turn == chess.BLACK and state.play_mode == PlayMode.USER_WHITE
                    if cond1 or cond2:
                        state.time_control.reset_start_time()
                        think(state.game, state.time_control, msg, state)
                    else:
                        DisplayMsg.show(msg)
                        state.start_clock()
                        state.legal_fens = compute_legal_fens(state.game.copy())

                    if state.best_move_displayed:
                        DisplayMsg.show(Message.SWITCH_SIDES(game=state.game.copy(), move=move))

                elif state.interaction_mode == Mode.REMOTE:
                    if not engine.is_waiting():
                        stop_search_and_clock()

                    state.last_legal_fens = []
                    state.legal_fens_after_cmove = []
                    state.best_move_displayed = state.done_computer_fen
                    if state.best_move_displayed:
                        move = state.done_move
                        state.done_computer_fen = None
                        state.done_move = state.pb_move = chess.Move.null()
                    else:
                        move = chess.Move.null()  # not really needed

                    state.play_mode = PlayMode.USER_WHITE if state.play_mode == PlayMode.USER_BLACK else PlayMode.USER_BLACK
                    msg = Message.PLAY_MODE(play_mode=state.play_mode, play_mode_text=state.dgttranslate.text(state.play_mode.value))

                    if state.time_control.mode == TimeMode.FIXED:
                        state.time_control.reset()

                    state.legal_fens = []
                    game_end = state.check_game_state()
                    if game_end:
                        DisplayMsg.show(msg)
                    else:
                        cond1 = state.game.turn == chess.WHITE and state.play_mode == PlayMode.USER_BLACK
                        cond2 = state.game.turn == chess.BLACK and state.play_mode == PlayMode.USER_WHITE
                        if cond1 or cond2:
                            state.time_control.reset_start_time()
                            think(state.game, state.time_control, msg, state)
                        else:
                            DisplayMsg.show(msg)
                            state.start_clock()
                            state.legal_fens = compute_legal_fens(state.game.copy())

                    if state.best_move_displayed:
                        DisplayMsg.show(Message.SWITCH_SIDES(game=state.game.copy(), move=move))

            elif isinstance(event, Event.DRAWRESIGN):
                if not state.game_declared:  # in case user leaves kings in place while moving other pieces
                    stop_search_and_clock()
                    DisplayMsg.show(Message.GAME_ENDS(tc_init=state.time_control.get_parameters(), result=event.result, play_mode=state.play_mode, game=state.game.copy()))
                    state.game_declared = True
                    state.stop_fen_timer()
                    state.legal_fens_after_cmove = []
                    update_elo(state, event.result)

            elif isinstance(event, Event.REMOTE_MOVE):
                flag_startup = False
                if args.board_type.lower() == 'noeboard':
                    user_move(event.move, sliding=True, state=state)
                else:
                    if state.interaction_mode == Mode.REMOTE and state.is_not_user_turn():
                        stop_search_and_clock()
                        DisplayMsg.show(Message.COMPUTER_MOVE(move=event.move, ponder=chess.Move.null(), game=state.game.copy(),
                                                              wait=False))
                        game_copy = state.game.copy()
                        game_copy.push(event.move)
                        state.done_computer_fen = game_copy.board_fen()
                        state.done_move = event.move
                        state.pb_move = chess.Move.null()
                        state.legal_fens_after_cmove = compute_legal_fens(game_copy)
                    else:
                        logging.warning('wrong function call [remote]! mode: %s turn: %s', state.interaction_mode, state.game.turn)

            elif isinstance(event, Event.BEST_MOVE):
                flag_startup = False
                state.take_back_locked = False
                state.best_move_posted = False
                state.takeback_active = False

                if state.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.TRAINING):
                    if state.is_not_user_turn():
                        # clock must be stopped BEFORE the "book_move" event cause SetNRun resets the clock display
                        state.stop_clock()
                        state.best_move_posted = True
                        # @todo 8/8/R6P/1R6/7k/2B2K1p/8/8 and sliding Ra6 over a5 to a4 - handle this in correct way!!
                        if state.game.is_game_over() and not online_mode():
                            logging.warning('illegal move on game_end - sliding? move: %s fen: %s', event.move, state.game.fen())
                        elif event.move is None:  # online game aborted or pgn move wrong or end of pgn game
                            state.game_declared = True
                            state.stop_fen_timer()
                            state.legal_fens_after_cmove = []
                            game_msg = state.game.copy()

                            if online_mode():
                                winner = ''
                                result_str = ''
                                time.sleep(0.5)
                                result_str, winner = read_online_result()
                                logging.debug('molli result_str:%s', result_str)
                                logging.debug('molli winner:%s', winner)
                                gameresult_tmp: Optional[GameResult] = None
                                gameresult_tmp2: Optional[GameResult] = None

                                if 'Checkmate' in result_str or 'checkmate' in result_str or 'mate' in result_str:
                                    gameresult_tmp = GameResult.MATE
                                elif 'Game abort' in result_str or 'timeout' in result_str:
                                    if winner:
                                        if 'white' in winner:
                                            gameresult_tmp = GameResult.ABORT
                                            gameresult_tmp2 = GameResult.WIN_WHITE
                                        else:
                                            gameresult_tmp = GameResult.ABORT
                                            gameresult_tmp2 = GameResult.WIN_BLACK
                                    else:
                                        gameresult_tmp = GameResult.ABORT
                                elif result_str == 'Draw' or result_str == 'draw':
                                    gameresult_tmp = GameResult.DRAW
                                elif 'Out of time: White wins' in result_str:
                                    gameresult_tmp = GameResult.OUT_OF_TIME
                                    gameresult_tmp2 = GameResult.WIN_WHITE
                                elif 'Out of time: Black wins' in result_str:
                                    gameresult_tmp = GameResult.OUT_OF_TIME
                                    gameresult_tmp2 = GameResult.WIN_BLACK
                                elif 'Out of time' in result_str or 'outoftime' in result_str:
                                    if winner:
                                        if 'white' in winner:
                                            gameresult_tmp = GameResult.OUT_OF_TIME
                                            gameresult_tmp2 = GameResult.WIN_WHITE
                                        else:
                                            gameresult_tmp = GameResult.OUT_OF_TIME
                                            gameresult_tmp2 = GameResult.WIN_BLACK
                                    else:
                                        gameresult_tmp = GameResult.OUT_OF_TIME
                                elif 'White wins' in result_str:
                                    gameresult_tmp = GameResult.ABORT
                                    gameresult_tmp2 = GameResult.WIN_WHITE
                                elif 'Black wins' in result_str:
                                    gameresult_tmp = GameResult.ABORT
                                    gameresult_tmp2 = GameResult.WIN_BLACK
                                elif 'OPP. resigns' in result_str or 'resign' in result_str or 'abort' in result_str:
                                    gameresult_tmp = GameResult.ABORT
                                    logging.debug('molli resign handling')
                                    if winner == '':
                                        logging.debug('molli winner not set')
                                        if state.play_mode == PlayMode.USER_BLACK:
                                            gameresult_tmp2 = GameResult.WIN_BLACK
                                        else:
                                            gameresult_tmp2 = GameResult.WIN_WHITE
                                    else:
                                        logging.debug('molli winner %s', winner)
                                        if 'white' in winner:
                                            gameresult_tmp2 = GameResult.WIN_WHITE
                                        else:
                                            gameresult_tmp2 = GameResult.WIN_BLACK

                                else:
                                    logging.debug('molli unknown result')
                                    gameresult_tmp = GameResult.ABORT

                                logging.debug('molli result_tmp:%s', gameresult_tmp)
                                logging.debug('molli result_tmp2:%s', gameresult_tmp2)

                                if gameresult_tmp2 and not (state.game.is_game_over() and gameresult_tmp == GameResult.ABORT):
                                    if gameresult_tmp == GameResult.OUT_OF_TIME:
                                        DisplayMsg.show(Message.LOST_ON_TIME())
                                        time.sleep(2)
                                        DisplayMsg.show(Message.GAME_ENDS(tc_init=state.time_control.get_parameters(), result=gameresult_tmp2, play_mode=state.play_mode, game=game_msg))
                                    else:
                                        DisplayMsg.show(Message.GAME_ENDS(tc_init=state.time_control.get_parameters(), result=gameresult_tmp, play_mode=state.play_mode, game=game_msg))
                                        time.sleep(2)
                                        DisplayMsg.show(Message.GAME_ENDS(tc_init=state.time_control.get_parameters(), result=gameresult_tmp2, play_mode=state.play_mode, game=game_msg))
                                else:
                                    if gameresult_tmp == GameResult.ABORT and gameresult_tmp2:
                                        DisplayMsg.show(Message.GAME_ENDS(tc_init=state.time_control.get_parameters(), result=gameresult_tmp2, play_mode=state.play_mode, game=game_msg))
                                    else:
                                        DisplayMsg.show(Message.GAME_ENDS(tc_init=state.time_control.get_parameters(), result=gameresult_tmp, play_mode=state.play_mode, game=game_msg))
                            else:

                                if pgn_mode():
                                    # molli: check if last move of pgn game file
                                    stop_search_and_clock()
                                    log_pgn(state)
                                    if flag_pgn_game_over:
                                        logging.debug('molli pgn: PGN END')
                                        pgn_game_name, pgn_problem, pgn_fen, pgn_result, pgn_white, pgn_black = read_pgn_info()
                                        DisplayMsg.show(Message.PGN_GAME_END(result=pgn_result))
                                    elif state.pgn_book_test:
                                        l_game_copy = state.game.copy()
                                        l_game_copy.pop()
                                        l_found = state.searchmoves.check_book(bookreader, l_game_copy)

                                        if not l_found:
                                            DisplayMsg.show(Message.PGN_GAME_END(result='*'))
                                        else:
                                            logging.debug('molli pgn: Wrong Move! Try Again!')
                                            # increase pgn guess counters
                                            if state.max_guess_black > 0 and state.game.turn == chess.WHITE:
                                                state.no_guess_black = state.no_guess_black + 1
                                                if state.no_guess_black > state.max_guess_black:
                                                    DisplayMsg.show(Message.MOVE_WRONG())
                                                else:
                                                    DisplayMsg.show(Message.MOVE_RETRY())
                                            elif state.max_guess_white > 0 and state.game.turn == chess.BLACK:
                                                state.no_guess_white = state.no_guess_white + 1
                                                if state.no_guess_white > state.max_guess_white:
                                                    DisplayMsg.show(Message.MOVE_WRONG())
                                                else:
                                                    DisplayMsg.show(Message.MOVE_RETRY())
                                            else:
                                                # user move wrong in pgn display mode only
                                                DisplayMsg.show(Message.MOVE_RETRY())
                                            state.takeback_active = True
                                            state.automatic_takeback = True
                                            set_wait_state(Message.TAKE_BACK(game=state.game.copy()), state)  # automatic takeback mode
                                    else:
                                        logging.debug('molli pgn: Wrong Move! Try Again!')

                                        if state.max_guess_black > 0 and state.game.turn == chess.WHITE:
                                            state.no_guess_black = state.no_guess_black + 1
                                            if state.no_guess_black > state.max_guess_black:
                                                DisplayMsg.show(Message.MOVE_WRONG())
                                            else:
                                                DisplayMsg.show(Message.MOVE_RETRY())
                                        elif state.max_guess_white > 0 and state.game.turn == chess.BLACK:
                                            state.no_guess_white = state.no_guess_white + 1
                                            if state.no_guess_white > state.max_guess_white:
                                                DisplayMsg.show(Message.MOVE_WRONG())
                                            else:
                                                DisplayMsg.show(Message.MOVE_RETRY())
                                        else:
                                            # user move wrong in pgn display mode only
                                            DisplayMsg.show(Message.MOVE_RETRY())
                                        state.takeback_active = True
                                        state.automatic_takeback = True
                                        set_wait_state(Message.TAKE_BACK(game=state.game.copy()), state)  # automatic takeback mode
                                else:
                                    DisplayMsg.show(Message.GAME_ENDS(tc_init=state.time_control.get_parameters(), result=GameResult.ABORT, play_mode=state.play_mode, game=state.game.copy()))

                            time.sleep(0.5)
                        else:
                            if event.inbook:
                                DisplayMsg.show(Message.BOOK_MOVE())
                            state.searchmoves.exclude(event.move)

                            if online_mode() or emulation_mode():
                                start_time_cmove_done = time.time()  # time should alraedy run for the player
                            DisplayMsg.show(Message.EXIT_MENU())
                            DisplayMsg.show(Message.COMPUTER_MOVE(move=event.move, ponder=event.ponder, game=state.game.copy(), wait=event.inbook))
                            game_copy = state.game.copy()
                            game_copy.push(event.move)

                            if picotutor_mode(state):
                                if pgn_mode():
                                    t_color = state.picotutor.get_user_color()
                                    if t_color == chess.BLACK:
                                        state.picotutor.set_user_color(chess.WHITE)
                                    else:
                                        state.picotutor.set_user_color(chess.BLACK)

                                valid = state.picotutor.push_move(event.move)

                                if not valid:
                                    state.picotutor.set_position(game_copy.fen(), i_turn=game_copy.turn)

                                    if state.play_mode == PlayMode.USER_BLACK:
                                        state.picotutor.set_user_color(chess.BLACK)
                                    else:
                                        state.picotutor.set_user_color(chess.WHITE)

                            state.done_computer_fen = game_copy.board_fen()
                            state.done_move = event.move

                            brain_book = state.interaction_mode == Mode.BRAIN and event.inbook
                            state.pb_move = event.ponder if event.ponder and not brain_book else chess.Move.null()
                            state.legal_fens_after_cmove = compute_legal_fens(game_copy)

                            if pgn_mode():
                                # molli pgn: reset pgn guess counters
                                if state.max_guess_black > 0 and not state.game.turn == chess.BLACK:
                                    state.no_guess_black = 1
                                elif state.max_guess_white > 0 and not state.game.turn == chess.WHITE:
                                    state.no_guess_white = 1

                            # molli: noeboard/WEB-Play
                            if args.board_type.lower() == 'noeboard':
                                logging.info('done move detected')
                                assert state.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.REMOTE, Mode.TRAINING), 'wrong mode: %s' % state.interaction_mode

                                time.sleep(0.5)
                                DisplayMsg.show(Message.COMPUTER_MOVE_DONE())

                                state.best_move_posted = False
                                state.game.push(state.done_move)
                                state.done_computer_fen = None
                                state.done_move = chess.Move.null()

                                if online_mode() or emulation_mode():
                                    # for online or emulation engine the user time alraedy runs with move announcement
                                    # => subtract time between announcement and execution
                                    end_time_cmove_done = time.time()
                                    cmove_time = math.floor(end_time_cmove_done - start_time_cmove_done)
                                    if cmove_time > 0:
                                        state.time_control.sub_online_time(state.game.turn, cmove_time)
                                    cmove_time = 0
                                    start_time_cmove_done = 0

                                game_end = state.check_game_state()
                                if game_end:
                                    update_elo(state, game_end.result)
                                    state.legal_fens = []
                                    state.legal_fens_after_cmove = []
                                    if online_mode():
                                        stop_search_and_clock()
                                        state.stop_fen_timer()
                                    stop_search_and_clock()
                                    if not pgn_mode():
                                        DisplayMsg.show(game_end)
                                else:
                                    state.searchmoves.reset()

                                    state.time_control.add_time(not state.game.turn)

                                    # molli new tournament time control
                                    if state.time_control.moves_to_go_orig > 0 and (state.game.fullmove_number - 1) == state.time_control.moves_to_go_orig:
                                        state.time_control.add_game2(not state.game.turn)
                                        t_player = False
                                        msg = Message.TIMECONTROL_CHECK(player=t_player, movestogo=state.time_control.moves_to_go_orig, time1=state.time_control.game_time, time2=state.time_control.game_time2)
                                        DisplayMsg.show(msg)

                                    if not online_mode() or state.game.fullmove_number > 1:
                                        state.start_clock()
                                    else:
                                        DisplayMsg.show(Message.EXIT_MENU())  # show clock
                                        end_time_cmove_done = 0

                                    if state.interaction_mode == Mode.BRAIN:
                                        brain(state.game, state.time_control, state)

                                    state.legal_fens = compute_legal_fens(state.game.copy())

                                    if pgn_mode():
                                        log_pgn(state)
                                        if state.game.turn == chess.WHITE:
                                            if state.max_guess_white > 0:
                                                if state.no_guess_white > state.max_guess_white:
                                                    state.last_legal_fens = []
                                                    get_next_pgn_move(state)
                                            else:
                                                state.last_legal_fens = []
                                                get_next_pgn_move(state)
                                        elif state.game.turn == chess.BLACK:
                                            if state.max_guess_black > 0:
                                                if state.no_guess_black > state.max_guess_black:
                                                    state.last_legal_fens = []
                                                    get_next_pgn_move(state)
                                            else:
                                                state.last_legal_fens = []
                                                get_next_pgn_move(state)

                                state.last_legal_fens = []
                                newgame_happened = False

                                if state.game.fullmove_number < 1:
                                    ModeInfo.reset_opening()
                                if picotutor_mode(state) and state.dgtmenu.get_picoexplorer():
                                    op_eco, op_name, op_moves, op_in_book = state.picotutor.get_opening()
                                    if op_in_book and op_name:
                                        ModeInfo.set_opening(state.book_in_use, str(op_name), op_eco)
                                        DisplayMsg.show(Message.SHOW_TEXT(text_string=op_name))
                            # molli end noeboard/Web-Play
                    else:
                        logging.warning('wrong function call [best]! mode: %s turn: %s', state.interaction_mode, state.game.turn)
                else:
                    logging.warning('wrong function call [best]! mode: %s turn: %s', state.interaction_mode, state.game.turn)

            elif isinstance(event, Event.NEW_PV):
                if state.interaction_mode == Mode.BRAIN and engine.is_pondering():
                    logging.debug('in brain mode and pondering ignore pv %s', event.pv[:3])
                else:
                    # illegal moves can occur if a pv from the engine arrives at the same time as an user move
                    if state.game.is_legal(event.pv[0]):
                        DisplayMsg.show(Message.NEW_PV(pv=event.pv, mode=state.interaction_mode, game=state.game.copy()))
                    else:
                        logging.info('illegal move can not be displayed. move: %s fen: %s', event.pv[0], state.game.fen())
                        logging.info('engine status: t:%s p:%s', engine.is_thinking(), engine.is_pondering())

            elif isinstance(event, Event.NEW_SCORE):
                if state.interaction_mode == Mode.BRAIN and engine.is_pondering():
                    logging.debug('in brain mode and pondering, ignore score %s', event.score)
                else:
                    if event.score == 999 or event.score == -999:
                        flag_pgn_game_over = True  # molli pgn mode: signal that pgn is at end
                    else:
                        flag_pgn_game_over = False

                    DisplayMsg.show(Message.NEW_SCORE(score=event.score, mate=event.mate, mode=state.interaction_mode,
                                                      turn=state.game.turn))

            elif isinstance(event, Event.NEW_DEPTH):
                if state.interaction_mode == Mode.BRAIN and engine.is_pondering():
                    logging.debug('in brain mode and pondering, ignore depth %s', event.depth)
                else:
                    if event.depth == 999:
                        flag_pgn_game_over = True
                    else:
                        flag_pgn_game_over = False
                    DisplayMsg.show(Message.NEW_DEPTH(depth=event.depth))

            elif isinstance(event, Event.START_SEARCH):
                DisplayMsg.show(Message.SEARCH_STARTED())

            elif isinstance(event, Event.STOP_SEARCH):
                DisplayMsg.show(Message.SEARCH_STOPPED())

            elif isinstance(event, Event.SET_INTERACTION_MODE):
                if event.mode not in (Mode.NORMAL, Mode.REMOTE, Mode.TRAINING) and state.done_computer_fen:  # @todo check why still needed
                    state.dgtmenu.set_mode(state.interaction_mode)  # undo the button4 stuff
                    logging.warning('mode cant be changed to a pondering mode as long as a move is displayed')
                    mode_text = state.dgttranslate.text('Y10_errormode')
                    msg = Message.INTERACTION_MODE(mode=state.interaction_mode, mode_text=mode_text, show_ok=False)
                    DisplayMsg.show(msg)
                else:
                    if event.mode == Mode.PONDER:
                        newgame_happened = False
                    stop_search_and_clock()
                    state.interaction_mode = event.mode
                    engine_mode()
                    msg = Message.INTERACTION_MODE(mode=event.mode, mode_text=event.mode_text, show_ok=event.show_ok)
                    set_wait_state(msg, state)  # dont clear searchmoves here

            elif isinstance(event, Event.SET_OPENING_BOOK):
                write_picochess_ini('book', event.book['file'])
                logging.debug('changing opening book [%s]', event.book['file'])
                bookreader = chess.polyglot.open_reader(event.book['file'])
                DisplayMsg.show(Message.OPENING_BOOK(book_text=event.book_text, show_ok=event.show_ok))
                state.book_in_use = event.book['file']
                state.stop_fen_timer()

            elif isinstance(event, Event.SHOW_ENGINENAME):
                DisplayMsg.show(Message.SHOW_ENGINENAME(show_enginename=event.show_enginename))

            elif isinstance(event, Event.SAVE_GAME):
                if event.pgn_filename:
                    state.stop_clock()
                    DisplayMsg.show(Message.SAVE_GAME(tc_init=state.time_control.get_parameters(), play_mode=state.play_mode, game=state.game.copy(), pgn_filename=event.pgn_filename))

            elif isinstance(event, Event.READ_GAME):
                if event.pgn_filename:
                    DisplayMsg.show(Message.READ_GAME(pgn_filename=event.pgn_filename))
                    read_pgn_file(event.pgn_filename, state)

            elif isinstance(event, Event.CONTLAST):
                DisplayMsg.show(Message.CONTLAST(contlast=event.contlast))

            elif isinstance(event, Event.ALTMOVES):
                DisplayMsg.show(Message.ALTMOVES(altmoves=event.altmoves))

            elif isinstance(event, Event.PICOWATCHER):
                if (state.dgtmenu.get_picowatcher() or state.dgtmenu.get_picocoach()):
                    pico_calc = True
                else:
                    pico_calc = False
                state.picotutor.set_status(state.dgtmenu.get_picowatcher(), state.dgtmenu.get_picocoach(), state.dgtmenu.get_picoexplorer(), state.dgtmenu.get_picocomment())
                if event.picowatcher:
                    state.flag_picotutor = True
                    state.picotutor.set_position(state.game.fen(), i_turn=state.game.turn)
                    if state.play_mode == PlayMode.USER_BLACK:
                        state.picotutor.set_user_color(chess.BLACK)
                    else:
                        state.picotutor.set_user_color(chess.WHITE)
                elif state.dgtmenu.get_picocoach():
                    state.flag_picotutor = True
                elif state.dgtmenu.get_picoexplorer():
                    state.flag_picotutor = True
                else:
                    state.flag_picotutor = False
                    if pico_calc:
                        state.picotutor.stop()
                DisplayMsg.show(Message.PICOWATCHER(picowatcher=event.picowatcher))

            elif isinstance(event, Event.PICOCOACH):

                if (state.dgtmenu.get_picowatcher() or state.dgtmenu.get_picocoach()):
                    pico_calc = True
                else:
                    pico_calc = False

                pico_calc = False
                state.picotutor.set_status(state.dgtmenu.get_picowatcher(), state.dgtmenu.get_picocoach(), state.dgtmenu.get_picoexplorer(), state.dgtmenu.get_picocomment())

                if event.picocoach:
                    state.flag_picotutor = True
                    state.picotutor.set_position(state.game.fen(), i_turn=state.game.turn)
                    if state.play_mode == PlayMode.USER_BLACK:
                        state.picotutor.set_user_color(chess.BLACK)
                    else:
                        state.picotutor.set_user_color(chess.WHITE)
                elif state.dgtmenu.get_picowatcher():
                    state.flag_picotutor = True
                elif state.dgtmenu.get_picoexplorer():
                    state.flag_picotutor = True
                else:
                    state.flag_picotutor = False
                    if pico_calc:
                        state.picotutor.stop()

                DisplayMsg.show(Message.PICOCOACH(picocoach=event.picocoach))

            elif isinstance(event, Event.PICOEXPLORER):
                if (state.dgtmenu.get_picowatcher() or state.dgtmenu.get_picocoach()):
                    pico_calc = True
                else:
                    pico_calc = False
                state.picotutor.set_status(state.dgtmenu.get_picowatcher(), state.dgtmenu.get_picocoach(), state.dgtmenu.get_picoexplorer(), state.dgtmenu.get_picocomment())
                if event.picoexplorer:
                    state.flag_picotutor = True
                else:
                    if state.dgtmenu.get_picowatcher() or state.dgtmenu.get_picocoach():
                        state.flag_picotutor = True
                    else:
                        state.flag_picotutor = False
                        if pico_calc:
                            state.picotutor.stop()
                DisplayMsg.show(Message.PICOEXPLORER(picoexplorer=event.picoexplorer))

            elif isinstance(event, Event.RSPEED):
                if emulation_mode():
                    # restart engine with new retro speed
                    old_options = engine.get_pgn_options()
                    DisplayMsg.show(Message.ENGINE_SETUP())
                    if engine.quit():
                        engine = UciEngine(file=engine_file, uci_shell=uci_local_shell,
                                           retrospeed=get_engine_rspeed_par(state.dgtmenu.get_engine_rspeed()))
                        engine.startup(old_options, state.rating)
                        stop_search_and_clock()
                        state.game = chess.Board()
                        state.game.turn = chess.WHITE
                        state.play_mode = PlayMode.USER_WHITE
                        engine.newgame(state.game.copy())
                        state.done_computer_fen = None
                        state.done_move = state.pb_move = chess.Move.null()
                        state.searchmoves.reset()
                        state.game_declared = False
                        state.legal_fens = compute_legal_fens(state.game.copy())
                        state.last_legal_fens = []
                        state.legal_fens_after_cmove = []
                        is_out_of_time_already = False
                        engine_mode()
                        DisplayMsg.show(Message.RSPEED(rspeed=event.rspeed))
                        update_elo_display(state)
                    else:
                        logging.error('engine shutdown failure')
                        DisplayMsg.show(Message.ENGINE_FAIL())

            elif isinstance(event, Event.TAKE_BACK):
                if not (state.take_back_locked or online_mode() or (emulation_mode() and not state.automatic_takeback)) and state.game.move_stack:
                    stop_search_and_clock()
                    l_error = False
                    try:
                        state.game.pop()
                        l_error = False
                    except Exception:
                        l_error = True
                        logging.debug('takeback not possible!')

                    if not l_error:
                        if picotutor_mode(state):
                            if state.best_move_posted:
                                state.picotutor.pop_last_move()
                                state.best_move_posted = False
                            state.picotutor.pop_last_move()
                        state.done_computer_fen = None
                        state.done_move = state.pb_move = chess.Move.null()
                        state.searchmoves.reset()
                        state.takeback_active = True
                        set_wait_state(Message.TAKE_BACK(game=state.game.copy()), state)

                        if pgn_mode():  # molli pgn
                            log_pgn(state)
                            if state.max_guess_white > 0:
                                if state.game.turn == chess.WHITE:
                                    if state.no_guess_white > state.max_guess_white:
                                        get_next_pgn_move(state)
                            elif state.max_guess_black > 0:
                                if state.game.turn == chess.BLACK:
                                    if state.no_guess_black > state.max_guess_black:
                                        get_next_pgn_move(state)

                        if (state.game.board_fen() == chess.STARTING_BOARD_FEN):
                            pos960 = 518
                            Observable.fire(Event.NEW_GAME(pos960=pos960))

            elif isinstance(event, Event.PICOCOMMENT):
                DisplayMsg.show(Message.PICOCOMMENT(picocomment=event.picocomment))

            elif isinstance(event, Event.SET_TIME_CONTROL):
                state.time_control.stop_internal(log=False)
                tc_init = event.tc_init

                state.time_control = TimeControl(**tc_init)

                if not pgn_mode() and not online_mode():
                    if tc_init['moves_to_go'] > 0:
                        if state.time_control.mode == TimeMode.BLITZ:
                            write_picochess_ini('time', '{:d} {:d} 0 {:d}'.format(tc_init['moves_to_go'], tc_init['blitz'], tc_init['blitz2']))
                        elif state.time_control.mode == TimeMode.FISCHER:
                            write_picochess_ini('time', '{:d} {:d} {:d} {:d}'.format(tc_init['moves_to_go'], tc_init['blitz'], tc_init['fischer'], tc_init['blitz2']))
                    elif state.time_control.mode == TimeMode.BLITZ:
                        write_picochess_ini('time', '{:d} 0'.format(tc_init['blitz']))
                    elif state.time_control.mode == TimeMode.FISCHER:
                        write_picochess_ini('time', '{:d} {:d}'.format(tc_init['blitz'], tc_init['fischer']))
                    elif state.time_control.mode == TimeMode.FIXED:
                        write_picochess_ini('time', '{:d}'.format(tc_init['fixed']))

                    if state.time_control.depth > 0:
                        write_picochess_ini('depth', '{:d}'.format(tc_init['depth']))
                    else:
                        write_picochess_ini('depth', '{:d}'.format(0))

                    if state.time_control.node > 0:
                        write_picochess_ini('node', '{:d}'.format(tc_init['node']))
                    else:
                        write_picochess_ini('node', '{:d}'.format(0))

                text = Message.TIME_CONTROL(time_text=event.time_text, show_ok=event.show_ok, tc_init=tc_init)
                DisplayMsg.show(text)
                state.stop_fen_timer()

            elif isinstance(event, Event.CLOCK_TIME):
                if dgtdispatcher.is_prio_device(event.dev, event.connect):  # transfer only the most prio clock's time
                    logging.debug('setting tc clock time - prio: %s w:%s b:%s', event.dev,
                                  hms_time(event.time_white), hms_time(event.time_black))

                    if state.time_control.mode != TimeMode.FIXED and (event.time_white == state.time_control.game_time and event.time_black == state.time_control.game_time):
                        pass
                    else:
                        moves_to_go = state.time_control.moves_to_go_orig - state.game.fullmove_number + 1
                        if moves_to_go < 0:
                            moves_to_go = 0
                        state.time_control.set_clock_times(white_time=event.time_white, black_time=event.time_black, moves_to_go=moves_to_go)

                    # find out, if we are in bullet time (<=60secs on users clock or lowest time if user side unknown)
                    time_u = event.time_white
                    time_c = event.time_black
                    if state.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.TRAINING):   # @todo handle Mode.REMOTE too
                        if state.play_mode == PlayMode.USER_BLACK:
                            time_u, time_c = time_c, time_u
                    else:  # here, we use the lowest time
                        if time_c < time_u:
                            time_u, time_c = time_c, time_u
                    low_time = False  # molli allow the speech output even for less than 60 seconds
                    dgtboard.low_time = low_time
                    if state.interaction_mode == Mode.TRAINING or position_mode:
                        pass
                    else:
                        DisplayMsg.show(Message.CLOCK_TIME(time_white=event.time_white, time_black=event.time_black,
                                                           low_time=low_time))
                else:
                    logging.debug('ignore clock time - too low prio: %s', event.dev)
            elif isinstance(event, Event.OUT_OF_TIME):
                # molli: allow further playing even when run out of time
                if not is_out_of_time_already and not online_mode():  # molli in online mode the server decides
                    state.stop_clock()
                    result = GameResult.OUT_OF_TIME
                    DisplayMsg.show(Message.GAME_ENDS(tc_init=state.time_control.get_parameters(), result=result, play_mode=state.play_mode, game=state.game.copy()))
                    is_out_of_time_already = True
                    update_elo(state, result)

            elif isinstance(event, Event.SHUTDOWN):
                stop_search()
                state.stop_clock()
                engine.quit()

                try:
                    if uci_remote_shell:
                        if uci_remote_shell.get():
                            try:
                                uci_remote_shell.get().__exit__(None, None, None)  # force to call __exit__ (close shell connection)
                            except Exception:
                                pass
                except Exception:
                    pass

                result = GameResult.ABORT
                DisplayMsg.show(Message.GAME_ENDS(tc_init=state.time_control.get_parameters(), result=result, play_mode=state.play_mode, game=state.game.copy()))
                DisplayMsg.show(Message.SYSTEM_SHUTDOWN())
                time.sleep(5)  # molli allow more time for commentary chat
                shutdown(args.dgtpi, dev=event.dev)  # @todo make independant of remote eng

            elif isinstance(event, Event.REBOOT):
                stop_search()
                state.stop_clock()
                engine.quit()
                result = GameResult.ABORT
                DisplayMsg.show(Message.GAME_ENDS(tc_init=state.time_control.get_parameters(), result=result, play_mode=state.play_mode, game=state.game.copy()))
                DisplayMsg.show(Message.SYSTEM_REBOOT())
                time.sleep(5)  # molli allow more time for commentary chat
                reboot(args.dgtpi and uci_local_shell.get() is None, dev=event.dev)  # @todo make independant of remote eng

            elif isinstance(event, Event.EMAIL_LOG):
                email_logger = Emailer(email=args.email, mailgun_key=args.mailgun_key)
                email_logger.set_smtp(sserver=args.smtp_server, suser=args.smtp_user, spass=args.smtp_pass,
                                      sencryption=args.smtp_encryption, sfrom=args.smtp_from)
                body = 'You probably want to forward this file to a picochess developer ;-)'
                email_logger.send('Picochess LOG', body, '/opt/picochess/logs/{}'.format(args.log_file))

            elif isinstance(event, Event.SET_VOICE):
                DisplayMsg.show(Message.SET_VOICE(type=event.type, lang=event.lang, speaker=event.speaker,
                                                  speed=event.speed))

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

            else:  # Default
                logging.warning('event not handled : [%s]', event)

            evt_queue.task_done()


if __name__ == '__main__':
    main()
