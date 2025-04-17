#!/usr/bin/env python3

# Copyright (C) 2013-2019 Jean-Francois Romang (jromang@posteo.de)
#                         Shivkumar Shivaji ()
#                         Jürgen Précour (LocutusOfPenguin@posteo.de)
#                         Molli (and thanks to Martin  for his opening
#                         identification code)
#                         Johan Sjöblom
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

import csv
import logging
from random import randint
from typing import Tuple
import platform
import chess  # type: ignore
from chess.engine import InfoDict
import chess.engine
import chess.pgn
from uci.engine import UciShell, UciEngine
from dgt.util import PicoComment, PicoCoach

# PicoTutor Constants
import picotutor_constants as c

logger = logging.getLogger(__name__)

class PicoTutor:
    def __init__(
        self,
        i_ucishell: UciShell,
        i_engine_path="/opt/picochess/engines/aarch64/a-stockf",
        i_player_color=chess.WHITE,
        i_fen="",
        i_comment_file="",
        i_lang="en",
        i_coach_analyser=False,
        loop=None,
        i_depth=None,
    ):
        self.user_color: chess.Color = i_player_color
        self.engine_path: str = i_engine_path

        self.engine: UciEngine | None = None # Pico4 uses UciEngine, not direct chess api
        # snapshot list of best = deep/max-ply, and obvious = shallow/low-ply
        # lists of InfoDict per color - filled in eval_legal_moves()
        self.best_info = {color: [] for color in [chess.WHITE, chess.BLACK]}
        self.obvious_info = {color: [] for color in [chess.WHITE, chess.BLACK]}
        # snapshot of best_moves and obvious_moves are filled in _eval_pv_list()
        # information comes from InfoDict snapshot lists above: best_info and obvious_info
        # "almost" complete 5-50 list of tuple(pv_key, move, score, mate)
        self.best_moves = {color: [] for color in [chess.WHITE, chess.BLACK]}
        self.obvious_moves = {color: [] for color in [chess.WHITE, chess.BLACK]}
        # history list of user move selected from best_moves and obvious_moves above
        # tuple(pv_key, move, score, mate) copy for selected user move
        # pv_key is the index to the snapshot best_info and obvious_info
        # index = None indicates was not found in InfoDict results
        # index not None has no value in history as its an index to a snapshot above
        self.best_history = {color: [] for color in [chess.WHITE, chess.BLACK]}
        self.obvious_history = {color: [] for color in [chess.WHITE, chess.BLACK]}
        # pv_user_move and pv_best_move are the pv array from InfoDict analysis
        self.pv_user_move = {color: [] for color in [chess.WHITE, chess.BLACK]}
        self.pv_best_move = {color: [] for color in [chess.WHITE, chess.BLACK]}
        self.hint_move = {color: chess.Move.null() for color in [chess.WHITE, chess.BLACK]}
        self.op = []  # used for opening book
        self.last_inside_book_moveno = 0
        # alt_best_moves are filled in eval_legal_moves()
        self.alt_best_moves = {color: [] for color in [chess.WHITE, chess.BLACK]}
        self.comments = []
        self.comment_no = 0
        self.comments_all = []
        self.comment_all_no = 0
        self.lang = i_lang
        self.expl_start_position = True
        self.watcher_on = False
        self.coach_on = False
        self.explorer_on = False
        self.comments_on = False
        self.mame_par = ""  # @todo create this info?
        # one of the challenges is to keep this board in sync
        # with the state.game board in picochess.py main
        self.board = chess.Board()
        self.ucishell = i_ucishell
        # user ini file coach-analyser value, if set PicoTutor is used
        # as PV and Score analyser instead of the engine you are playing
        self.coach_analyser = i_coach_analyser
        self.loop = loop  # main loop everywhere
        self.deep_limit_depth = i_depth  # override picotutor value
        # evaluated moves keeps a memory of all non zero evaluation strings
        # it can then be used to print comments in the PGN file
        self.evaluated_moves = {} # key=(fullmove_number, turn, move) value={}
        # the following setting can be True if engine is not playing
        # or if you want to analyse also engine moves (like pgn_engine)
        self.analyse_both_sides = False  # analyse only user side as default

        try:
            with open("chess-eco_pos.txt") as fp:
                self.book_data = list(csv.DictReader(filter(lambda row: row[0] != "#", fp.readlines()), delimiter="|"))
        except EnvironmentError:
            self.book_data = []

        try:
            with open("opening_name_fen.txt") as fp:
                self.book_fen_data = fp.readlines()
        except FileNotFoundError:
            self.book_fen_data = []

        self._setup_comments(i_lang, i_comment_file)

        self._setup_board(i_fen)

    async def open_engine(self):
        """open the tutor engine"""
        # @todo we have to start the engine always as the set_status has
        # not yet been changed to async --> causes changes in main
        # set_status might later be changed that require this engine
        if not self.engine:
            self.engine = UciEngine(self.engine_path, self.ucishell, self.mame_par, self.loop, "picotutor")
            await self.engine.open_engine()
            if self.engine.loaded_ok() is True:
                options = {"MultiPV": c.VALID_ROOT_MOVES, "Contempt": 0, "Threads": c.NUM_THREADS}
                await self.engine.startup(options=options)
                self.engine.set_mode()  # not needed as we dont ponder?
            else:
                # No need to call engine quit if its not loaded?
                self.engine = None
        if self.engine is None:
            logger.debug("Engine loading failed in Picotutor")

    async def set_mode(self, analyse_both_sides: bool):
        """ normally analyse_both_sides is False but if True
            both sides will be analysed """
        if self.analyse_both_sides != analyse_both_sides:
            self.analyse_both_sides = analyse_both_sides
            await self._start_or_stop_as_needed()

    def is_coach_analyser(self) -> bool:
        # to be an analyser for main we have to have a loaded engine
        # and the setting coach_analyser must be True in picochess.ini
        return (self.engine.loaded_ok() and self.coach_analyser) if self.engine else False

    def _setup_comments(self, i_lang, i_comment_file):
        if i_comment_file:
            try:
                with open(i_comment_file) as fp:
                    self.comments = fp.readlines()
            except OSError:
                self.comments = []

            if self.comments:
                self.comment_no = len(self.comments)

        try:
            arch = platform.machine()
            general_comment_file = "/opt/picochess/engines/" + arch + "/general_game_comments_" + i_lang + ".txt"
            with open(general_comment_file) as fp:
                self.comments_all = fp.readlines()
        except (OSError, IOError):
            self.comments_all = []

        if self.comments_all:
            self.comment_all_no = len(self.comments_all)

    def _setup_board(self, i_fen):
        if i_fen:
            self.board = chess.Board(i_fen)
        else:
            self.board = chess.Board()  # starting position if no other set_position command comes

    async def set_status(self, watcher=False, coach=PicoCoach.COACH_OFF, explorer=False, comments=False):
        if coach == PicoCoach.COACH_OFF:
            b_coach = False
        else:
            b_coach = True

        self.watcher_on = watcher
        self.coach_on = b_coach
        self.explorer_on = explorer
        self.comments_on = comments
        # @ todo - check if something changed before calling
        await self._start_or_stop_as_needed()

    def get_game_comment(self, pico_comment=PicoComment.COM_OFF, com_factor=0):
        max_range = 0
        max_range_all = 0
        range_fac = 0

        if com_factor == 0:
            return ""
        range_fac = round(100 / com_factor)
        max_range = self.comment_no * range_fac
        max_range_all = self.comment_all_no * range_fac

        if pico_comment == PicoComment.COM_ON_ENG:
            # get a comment by pure chance
            if self.comments and self.comment_no > 0:
                index = randint(0, max_range)
                if index > self.comment_no - 1:
                    return ""
                return self.comments[index]
            else:
                return ""
        elif pico_comment == PicoComment.COM_ON_ALL:
            # get a comment by pure chance
            if self.comments and self.comment_no > 0:
                index = randint(0, max_range)
                if index > self.comment_no - 1:
                    return ""
                return self.comments[index]
            else:
                if self.comments_all and self.comment_all_no > 0:
                    index = randint(0, max_range_all)
                    if index > self.comment_all_no - 1:
                        return ""
                    return self.comments_all[index]
                else:
                    return ""

    def init_comments(self, i_comment_file):
        self.comments = []
        self.comment_no = 0
        if i_comment_file:
            try:
                self.comments = open(i_comment_file).readlines()
            except OSError:
                self.comments = []

            if self.comments:
                self.comment_no = len(self.comments)

        else:
            self.comments = []

    def _find_longest_matching_opening(self, played: str) -> Tuple[str, str, str]:
        opening_name = moves = eco = ""
        for opening in self.book_data:
            # if len(opening.get('moves')) > 5:
            if played[: len(opening.get("moves"))] == opening.get("moves"):
                if len(opening.get("moves")) > len(moves):
                    opening_name = opening.get("opening_name")
                    moves = opening.get("moves")
                    eco = opening.get("eco")
        return opening_name, moves, eco

    def get_opening(self) -> Tuple[str, str, str, bool]:
        # check if game started really from start position
        # (otherwise we can't use opening based on just the moves)

        halfmoves = 2 * self.board.fullmove_number
        if self.board.turn:
            halfmoves -= 2
        else:
            halfmoves -= 1

        diff = self.board.fullmove_number - self.last_inside_book_moveno
        inside_book_opening = False

        opening_name = moves = eco = ""

        if self.op == [] or diff > 2:
            return eco, opening_name, moves, inside_book_opening

        played = "%s" % (" ".join(self.op))

        opening_name, moves, eco = self._find_longest_matching_opening(played)

        if self.expl_start_position and halfmoves <= len(moves.split()):
            inside_book_opening = True
            self.last_inside_book_moveno = self.board.fullmove_number
        else:
            # try opening name based on FEN
            op_name = ""
            i_book = False

            op_name, i_book = self.get_fen_opening()
            if i_book and op_name:
                opening_name = op_name
                inside_book_opening = True
                self.last_inside_book_moveno = self.board.fullmove_number
            else:
                inside_book_opening = False

        return eco, opening_name, moves, inside_book_opening

    def get_fen_opening(self):
        fen = self.board.board_fen()

        if not fen:
            return "", False

        index = 0
        opening_name = ""

        for line in self.book_fen_data:
            line_list = line.split()
            if line_list[0] == fen:
                opening_name = self.book_fen_data[index + 1]
                break
            index = index + 1

        if opening_name:
            return opening_name, True
        else:
            return "", False


    def is_same_board(self, game: chess.Board) -> bool:
        """ main program can check if tutor game is still in sync with same move stacks"""
        return self.board.fen() == game.fen()

    def reset(self):
        """ this is newgame reset - all is re-initialised 
        see also set_position"""
        # @ todo - let main program call reset_to_newgame?
        self._reset_to_newgame()

    def _reset_to_newgame(self):
        """ reset everything - game board becomes starting position
        analyser is stopped"""
        self._reset_to_new_position(chess.Board(), new_game=True)
        self.expl_start_position = True # make sure opening moves are explored


    def _reset_to_new_position(self, game: chess.Board, new_game: bool = False):
        """ update position and delete history - re-sync position
        the engine analyser will be stopped, start it again if needed
        you can indicate that this is a new game 
        eval comments to PGN will reset if new_game is True"""
        self.stop()
        if new_game:
            self.evaluated_moves = {}  # forget evals from last game
            logger.debug("picotutor reset to new position and newgame")
        else:
            logger.debug("picotutor reset to new position")
        self._reset_color_coded_vars()
        self.board = game.copy()
        # opening move explorer vars
        self.op = []
        if self.board.board_fen() == chess.STARTING_BOARD_FEN:
            if not new_game:
                logger.debug("strange - tutor position set to starting without newgame")
            self.expl_start_position = True
        else:
            self.expl_start_position = False


    def _reset_history_vars(self, game: chess.Board):
        """ reset and forget history only - needed when history is out of sync
        this is a lighter version of _reset_to_new_position
        it leaves analyser running - caller must check board sync
        if you send a different game board analyser is stopped and board copied"""
        if game.fen() != self.board.fen():
            self.stop() # only stop analysing if its wrong game
            self.board = game.copy()
        self._reset_color_coded_vars()  # all has to go? analysis starts over?
        # opening move history should be ok, so no self.op = []


    def _reset_color_coded_vars(self):
        """ reset and forget all color coded variables - needs to be done on new position"""
        # snapshot list of best = deep/max-ply, and obvious = shallow/low-ply
        # lists of InfoDict per color - filled in eval_legal_moves()
        self.best_info = {color: [] for color in [chess.WHITE, chess.BLACK]}
        self.obvious_info = {color: [] for color in [chess.WHITE, chess.BLACK]}
        # snapshot of best_moves and obvious_moves are filled in _eval_pv_list()
        # information comes from InfoDict snapshot lists above: best_info and obvious_info
        # "almost" complete 5-50 list of tuple(pv_key, move, score, mate)
        self.best_moves = {color: [] for color in [chess.WHITE, chess.BLACK]}
        self.obvious_moves = {color: [] for color in [chess.WHITE, chess.BLACK]}
        # history list of user move selected from best_moves and obvious_moves above
        # tuple(pv_key, move, score, mate) copy for selected user move
        # pv_key is the index to the snapshot best_info and obvious_info
        # index = None indicates was not found in InfoDict results
        # index not None has no value in history as its an index to a snapshot above
        self.best_history = {color: [] for color in [chess.WHITE, chess.BLACK]}
        self.obvious_history = {color: [] for color in [chess.WHITE, chess.BLACK]}
        # pv_user_move and pv_best_move are the pv array from InfoDict analysis
        # these could be changed to local variables in eval_user_moves
        self.pv_user_move = {color: [] for color in [chess.WHITE, chess.BLACK]}
        self.pv_best_move = {color: [] for color in [chess.WHITE, chess.BLACK]}
        self.hint_move = {color: chess.Move.null() for color in [chess.WHITE, chess.BLACK]}
        # alt_best_moves are filled in eval_legal_moves()
        self.alt_best_moves = {color: [] for color in [chess.WHITE, chess.BLACK]}


    async def set_user_color(self, i_user_color, analyse_both_sides: bool):
        """ set the user color to analyse moves for, normally engine is playing the other side
        if you send analyse_both_sides True it means both sides will be analysed """
        logger.debug("picotutor set user color %s", i_user_color)
        if self.user_color != i_user_color or self.analyse_both_sides != analyse_both_sides:
            # if new user colour and we are not going to analyse both sides
            # one history colour is going to become old and obsolete
            # but pop_user_move will detect it and delete history
            self.user_color = i_user_color
            self.analyse_both_sides = analyse_both_sides
            # no need to reset_color_coded_vars
            await self._start_or_stop_as_needed()

    def get_user_color(self):
        return self.user_color

    async def set_position(self, game: chess.Board, new_game: bool = False):
        """ main calls this to re-set position to same as main
        this re-synchronizes the main chess board with tutors own
        it is not a newgame - for newgame call reset or send new_game True"""
        logger.debug("set_position called")
        self._reset_to_new_position(game, new_game)

        if not (self.coach_on or self.watcher_on):
            return
        # at the moment pico main always calls set_user_color after this
        # therefore no self._start_or_stop_as_needed()
        # @ todo: combine set_colour into this call

    async def push_move(self, i_uci_move: chess.Move, game: chess.Board) -> bool:
        """inform picotutor that a board move was made
           returns False if tutor board is out of sync
           and caller must set_position again"""
        self.op.append(self.board.san(i_uci_move)) # for opening matching
        self.board.push(i_uci_move)  # now boards should be in sync, check!
        if game.fen() != self.board.fen():
            logger.debug("picotutor board not in sync when pushing move %s", i_uci_move.uci())
            return False

        if not (self.coach_on or self.watcher_on):
            return True

        c_filler_str = PicoTutor.printable_move_filler(self.board.ply(), self.board.turn)
        logger.debug("picotutor push move %s%s", c_filler_str, i_uci_move.uci())

        if not self.analyse_both_sides:
            # Pico V3 functionality
            if self.board.turn == self.user_color:
                # if it is user player's turn then start analyse engine
                if self.board.ply() > 1:
                    await self.start()
            else:
                # otherwise it is computer turn and analysis to be paused
                try:
                    await self.eval_legal_moves()  # take snapshot of current evaluation
                    self.eval_user_move(i_uci_move)  # determine & save evaluation of user move
                except IndexError:
                    logger.debug("program internal error - no move pushed before evaluation attempt")
                self.stop()
        else:
            # Pico V4 can analyse both sides in HINT mode - do all steps above
            try:
                await self.eval_legal_moves()  # take snapshot of current evaluation
                self.eval_user_move(i_uci_move)  # determine & save evaluation of user move
            except IndexError:
                logger.debug("program internal error - no move pushed before evaluation attempt")
            await self.start()

        # self.log_sync_info()  # normally commented out
        return True

    def _update_internal_history_after_pop(self, poped_move: chess.Move) -> bool:
        """return True if history sync with board is ok after pop"""
        result = True
        if self.analyse_both_sides or self.board.turn == self.user_color:
            # need to pop user move - this will fail if game starts in
            # hint/ANALYSIS mode and continues as NORMAL, BRAIN etc
            # part of the history has move for both sides, part has not

            # we have already poped move - turn coding need to be reversed
            if self.board.turn == chess.WHITE:
                turn = chess.BLACK
            else:
                turn = chess.WHITE
            try:
                pv_key, move, score, mate = self.best_history[turn][-1]
                if move == poped_move:
                    self.best_history[turn].pop()
                else:
                    result = False
                    logger.debug("picotutor pop best move not in sync - probably due to user color change")
                pv_key, move, score, mate = self.obvious_history[turn][-1]
                if move == poped_move:
                    self.obvious_history[turn].pop()
                else:
                    result = False
                    logger.debug("picotutor pop obvious move not in sync - probably due to user color change")
            except IndexError:
                result = False
                logger.debug("picotutor no move history to pop from, color=%s", self.board.turn)
        return result

    def _update_internal_state_after_pop(self, poped_move: chess.Move) -> bool:
        """return True if history sync with board is ok after pop"""
        try:
            self.op.pop()
        except IndexError:
            pass

        if not (self.coach_on or self.watcher_on):
            return False

        result = self._update_internal_history_after_pop(poped_move=poped_move)
        return result

    async def pop_last_move(self, game: chess.Board) -> bool:
        """inform picotutor that move takeback has been done
        returns False if tutor board is out of sync
        and caller must set_position again"""
        result = True
        if self.board.move_stack:
            if game.fen() != self.board.fen():  # not same before pop = ok
                poped_move = self.board.pop() # now they should be same
                if self.board.fen() == game.fen():
                    logger.debug("picotutor pop move %s colour=%s", poped_move.uci(), self.board.turn)
                    history_ok = self._update_internal_state_after_pop(poped_move)
                    if not history_ok:
                        # result is still True, boards are in sync, history is not
                        logger.warning("picotutor eval for next move must be done without history")
                        self._reset_history_vars(game) # same game - no re-sync
                else:
                    result = False
                    logger.debug("picotutor board not in sync after takeback")
                    self._reset_history_vars(game)  # re-sync new game board
            else:
                # result is still True, boards have same fen already before pop
                logger.debug("strange - picotutor board already pop last move in takeback")
        else:
            logger.debug("picotutor board has no move stack in takeback - doing nothing")
            if game.fen() != self.board.fen():
                result = False  # why ask for pop if move stack is empty in main?
        if result:
            await self._start_or_stop_as_needed()  # boards in sync, keep analysing
        else:
            logger.warning("picotutor board out of sync after takeback move")
        self.log_sync_info()  # debug only
        return result

    def get_stack(self):
        return self.board.move_stack

    def get_move_counter(self):
        return self.board.fullmove_number

    async def start(self):
        # after newgame event
        if self.engine:
            if self.engine.loaded_ok():
                if self.coach_on or self.watcher_on:
                    low_limit = chess.engine.Limit(depth=c.LOW_DEPTH)
                    low_kwargs = {"limit": low_limit, "multipv": c.LOW_ROOT_MOVES}
                else:
                    low_kwargs = None  # main program dont need first low
                if self.deep_limit_depth:
                    # override for main program when using coach_analyser True
                    deep_limit = chess.engine.Limit(depth=self.deep_limit_depth)
                else:
                    deep_limit = chess.engine.Limit(depth=c.DEEP_DEPTH)
                deep_kwargs = {"limit": deep_limit, "multipv": c.VALID_ROOT_MOVES}
                await self.engine.start_analysis(self.board, deep_kwargs, low_kwargs)
            else:
                logger.error("engine has terminated in picotutor?")

    def stop(self):
        # during thinking time of opponent tutor should be paused
        # after the user move has been pushed
        if self.engine:
            self.engine.stop()


    async def _start_or_stop_as_needed(self):
        """start or stop analyser as needed"""
        if(
            (self.analyse_both_sides or self.board.turn == self.user_color)
            and self.board.ply() > 1
        ):
            # if it is user player's turn then start analyse engine
            # otherwise it is computer opponents turn and analysis engine
            # should be paused
            await self.start()
        else:
            self.stop()

    def _stop_if_needed(self):
        """ stop analyser if needed """
        if(
            not (self.analyse_both_sides or self.board.turn == self.user_color)
            or self.board.ply() <= 1
        ):
            # reversed logic from _start_or_stop_as_needed above 
            self.stop()

    def log_sync_info(self):
        """logging help to check if picotutor and main picochess are in sync"""
        logger.debug("picotutor op moves %s", self.op)
        moves = self.board.move_stack
        uci_moves = []
        for move in moves:
            uci_moves.append(move.uci())
        logger.debug("picotutor board moves %s", uci_moves)
        hist_moves = []
        for turn in (chess.WHITE, chess.BLACK):
            if self.best_history[turn]:
                for pv_key, move, score, mate in self.best_history[turn]:
                    hist_moves.append(move.uci())
            logger.debug("picotutor history moves %s", hist_moves)
        self.log_eval_moves()


    def log_pv_lists(self, long_version: bool = False):
        """logging help for picotutor developers"""
        if self.board.turn == chess.WHITE:
            logger.debug("PicoTutor White to move")
        else:
            logger.debug("PicoTutor Black to move")
        if self.best_info[self.board.turn]:
            logger.debug("%d best:", len(self.best_info[self.board.turn]))
            for info in self.best_info[self.board.turn]:
                if "pv" in info and "score" in info and "depth" in info:
                    # score_turn must be as BEFORE the move - so opposite
                    score_turn = chess.WHITE if self.board.turn == chess.BLACK else chess.BLACK
                    move, score, mate = PicoTutor._get_score(score_turn, info)
                    logger.debug("%s score %d mate in %d depth %d", move.uci(), score, mate, info["depth"])
                if not long_version:
                    break
        if self.obvious_info[self.board.turn]:
            logger.debug("%d obvious:", len(self.obvious_info[self.board.turn]))
            for info in self.obvious_info[self.board.turn]:
                if "pv" in info and "score" in info and "depth" in info:
                    # score_turn must be as BEFORE the move - so opposite
                    score_turn = chess.WHITE if self.board.turn == chess.BLACK else chess.BLACK
                    move, score, mate = PicoTutor._get_score(score_turn, info)
                    logger.debug("%s score %d mate in %d depth %d", move.uci(), score, mate, info["depth"])
                if not long_version:
                    break

    def eval_user_move(self, user_move: chess.Move):
        """add user move to self.best_history and self.obvious_history
        update self.pv_user_move and self.pv_best_move
        throws IndexError if self.best_info and self.obvious_info is not prepared"""
        if not (self.coach_on or self.watcher_on):
            return
        # t tuple(pv_key, move, score, mate)
        t = self.in_best_moves(user_move)
        # add score to history list
        if t:
            pv_key = t[0]
            self.best_history[self.board.turn].append(t)
            self.pv_best_move = self.best_info[self.board.turn][0]["pv"]
            self.pv_user_move[self.board.turn] = self.best_info[self.board.turn][pv_key]["pv"]
        else:
            logger.debug("did not find user move %s in best moves", user_move.uci())
            pv_key = None  # so that we know its not found
            score = mate = 0
            if self.best_moves[self.board.turn]:
                # user move is <= lowest score seen, last on list
                pv_extra_key, extra_move, score, mate = self.best_moves[self.board.turn][-1]
            self.best_history[self.board.turn].append((pv_key, user_move, score, mate))
            self.pv_user_move = {color: [] for color in [chess.WHITE, chess.BLACK]}
            self.pv_best_move = {color: [] for color in [chess.WHITE, chess.BLACK]}
        t = self.in_obvious_moves(user_move)
        # add score to history list
        if t:
            # pv_key = t[0]
            self.obvious_history[self.board.turn].append(t)
        else:
            logger.debug("did not find user move %s in obvious moves", user_move.uci())
            pv_key = None  # so that we know its not found
            score = mate = 0
            if self.obvious_moves[self.board.turn]:
                # user move is <= lowest score seen, last on list
                pv_extra_key, extra_move, score, mate = self.obvious_moves[self.board.turn][-1]
            self.obvious_history[self.board.turn].append((pv_key, user_move, score, mate))

    def in_best_moves(self, user_move: chess.Move) -> tuple:
        """find move in obvious moves
        return None or tuple(pv_key, move, score, mate)"""
        for t in self.best_moves[self.board.turn]:
            # tuple index 1 is move
            if t[1] == user_move:
                return t
        return None

    def in_obvious_moves(self, user_move: chess.Move) -> tuple:
        """find move in obvious moves
        return None or tuple(pv_key, move, score)"""
        for t in self.obvious_moves[self.board.turn]:
            # tuple index 1 is move
            if t[1] == user_move:
                return t
        return None

    def sort_score(self, tupel):
        """define score:int as sort key"""
        return tupel[2]

    @staticmethod
    def _get_score(turn: chess.Color, info: chess.engine.InfoDict) -> tuple:
        """return tuple (move, score, mate) extracted from info"""
        move = info["pv"][0] if "pv" in info else chess.Move.null()
        score = mate = 0
        if "score" in info:
            score_val = info["score"]
            m = score_val.pov(turn).mate()
            mate = 0 if m is None else m
            if score_val.is_mate():
                score = score_val.pov(turn).score(mate_score=99999)
            else:
                score = score_val.pov(turn).score()
            return (move, score, mate)
        return (move, score, mate)

    # @todo re-design this method?
    @staticmethod
    def _eval_pv_list(turn: chess.Color, info_list: list[InfoDict], moves) -> int | None:
        """fill in best_moves or obvious_moves (param moves) from InfoDict list
        it assumes best_moves is emptied before called
        :return the best score"""
        best_score = -99999
        pv_key = 0  # index in InfoDict list
        while pv_key < len(info_list):
            info: InfoDict = info_list[pv_key]
            # score_turn must be as BEFORE the move - so opposite
            score_turn = chess.WHITE if turn == chess.BLACK else chess.BLACK
            move, score, mate = PicoTutor._get_score(score_turn, info)
            # put an score: int here for sorting best moves
            moves.append((pv_key, move, score, mate))
            best_score = max(best_score, score)
            pv_key = pv_key + 1
        return best_score

    async def eval_legal_moves(self):
        """ Update analysis information from engine analysis snapshot """
        # @todo check if this can throw exceptions
        if not (self.coach_on or self.watcher_on):
            return
        self.best_moves = {color: [] for color in [chess.WHITE, chess.BLACK]}
        self.obvious_moves = {color: [] for color in [chess.WHITE, chess.BLACK]}
        self.alt_best_moves = {color: [] for color in [chess.WHITE, chess.BLACK]}
        # eval_pv_list below will build new lists
        board_before_usermove: chess.Board = self.board.copy()
        try:
            #  for some strange reason the following line shows E1101
            board_before_usermove.pop()  # we ask for analysis done before user move
        except ValueError:
            logger.debug("can not evaluate empty board 1st move")
            return
        result = await self.engine.get_analysis(board_before_usermove)
        self.obvious_info[self.board.turn] = result.get("low")
        self.best_info[self.board.turn] = result.get("best")
        if self.best_info[self.board.turn]:
            best_score = PicoTutor._eval_pv_list(self.board.turn, self.best_info[self.board.turn], self.best_moves[self.board.turn])
            if self.best_moves[self.board.turn]:
                self.best_moves[self.board.turn].sort(key=self.sort_score, reverse=True)
                # collect possible good alternative moves
                for pv_key, move, score, mate in self.best_moves[self.board.turn]:
                    if move:
                        diff = abs(best_score - score)
                        if diff <= 20:
                            self.alt_best_moves[self.board.turn].append(move)
        if self.obvious_info[self.board.turn]:
            PicoTutor._eval_pv_list(self.board.turn, self.obvious_info[self.board.turn], self.obvious_moves[self.board.turn])
            self.obvious_moves[self.board.turn].sort(key=self.sort_score, reverse=True)
        self.log_pv_lists() # debug only

    async def get_analysis(self) -> dict:
        """get best move info if exists - during user thinking"""
        # failed answer is empty lists
        result = {"low": [], "best": [], "fen": ""}
        if self.engine:
            if self.engine.is_analyser_running():
                result = await self.engine.get_analysis(self.board)
        return result

    def get_user_move_eval(self) -> tuple:
        """return (eval sts, moves to mate"""
        eval_string = ""
        best_mate = 0
        best_score = 0
        best_move = chess.Move.null()
        if not (self.coach_on or self.watcher_on):
            return eval_string, 0

        # check precondition for calculations
        # more than one best and obvious move have to be found
        if (
            len(self.best_history[self.board.turn]) < 1
            or len(self.obvious_history[self.board.turn]) < 1
            or len(self.best_moves[self.board.turn]) < 2
            or len(self.obvious_moves[self.board.turn]) < 2
        ):
            eval_string = ""
            return eval_string, 0

        # user move score and previoues score
        # last evaluation = for current user move
        current_pv, current_move, current_score, current_mate = self.best_history[self.board.turn][-1]
        # current_pv can be None if no best_move had been found
        # but current_move is always the user move

        if len(self.best_history[self.board.turn]) > 1:
            before_pv, before_move, before_score, before_mate = self.best_history[self.board.turn][-2]
            if before_pv is None:  # pv_key index - move not analysed
                before_score = None  # history not usable, fake-move or missed
        else:
            before_score = None
        # before_pv can be None if no obvious move had been found

        # best deep engine score/move
        best_pv, best_move, best_score, best_mate = self.best_moves[self.board.turn][0]
        # tupel (pv,move,score,mate)

        # calculate diffs based on low depth search for obvious moves
        low_pv, low_move, low_score, low_mate = self.obvious_history[self.board.turn][-1]
        # last evaluation = for current user move
        # low_pv can be None if no if user move found in obvious_moves

        # optimisations in Picochess 4 - 200 wide multipv searches reduced to 5 to 50 ish
        # approximation_in_use is True when user misses either obvious or best history
        # user move might be missing in obvious history - can happen!
        #  --> low_score is lowest seen score, low_pv is None
        # user move might also be missing in best history
        #  --> current_score is lowest seen score, current_pv is None
        logger.debug("Score: %d", current_score)
        best_deep_diff = best_score - current_score
        deep_low_diff = current_score - low_score
        approximations_in_use = current_pv is None or low_pv is None
        c_move_str = PicoTutor.printable_move_filler(self.board.ply(), self.board.turn)
        c_move_str += current_move.uci()
        if approximations_in_use:
            logger.debug("approximations in use - only evaluating ? and ??")
            logger.debug("current_pv=%s low_pv=%s", current_pv, low_pv)
            logger.debug("approximated minimum CPL: %d for move %s", best_deep_diff, c_move_str)
        else:
            logger.debug("CPL: %d for move %s", best_deep_diff, c_move_str)
            logger.debug("deep_low_diff = %d", deep_low_diff)
        if before_score is not None:
            score_hist_diff = current_score - before_score
            history_in_use = True
            logger.debug("score_hist_diff = %d", score_hist_diff)
        else:
            score_hist_diff = 0  # missing history before score
            history_in_use = False
            logger.debug("history before move not available - not evaluating !? and ?!")

        # count legal moves in current position (for this we have to undo the user move)
        try:
            board_before_usermove: chess.Board = self.board.copy()
            board_before_usermove.pop()
            legal_no = board_before_usermove.legal_moves.count()
            logger.debug("number of legal moves %d", legal_no)
        except IndexError:
            # board_before_usermove.pop() failed, legal_no = 0
            legal_no = 0
            logger.debug("program internal error - no move pushed before evaluation attempt")
        if legal_no < 2:
            # there is no point evaluating the only legal or no pop()?
            eval_string = ""
            return eval_string, 0

        ###############################################################
        # 1. bad moves
        ##############################################################
        eval_string = ""

        # Blunder ??
        if best_deep_diff > c.VERY_BAD_MOVE_TH:
            eval_string = "??"

        # Mistake ?
        elif best_deep_diff > c.BAD_MOVE_TH:
            eval_string = "?"

        # Dubious
        # Dont score if approximations in use
        elif (
            not approximations_in_use
            and history_in_use
            and best_deep_diff > c.DUBIOUS_TH
            and (abs(deep_low_diff) > c.UNCLEAR_DIFF)
            and (score_hist_diff > c.POS_INCREASE)
        ):
            eval_string = "?!"

        ###############################################################
        # 2. good moves
        ##############################################################
        eval_string2 = ""

        if not approximations_in_use:
            # very good moves
            if best_deep_diff <= c.VERY_GOOD_MOVE_TH and (deep_low_diff > c.VERY_GOOD_IMPROVE_TH):
                if (best_score == 99999 and (best_mate == current_mate)) and legal_no <= 2:
                    pass
                else:
                    eval_string2 = "!!"

            # good move
            elif best_deep_diff <= c.GOOD_MOVE_TH and (deep_low_diff > c.GOOD_IMPROVE_TH) and legal_no > 1:
                eval_string2 = "!"

            # interesting move
            elif (
                history_in_use
                and best_deep_diff < c.INTERESTING_TH
                and (abs(deep_low_diff) > c.UNCLEAR_DIFF)
                and (score_hist_diff < c.POS_DECREASE)
            ):
                eval_string2 = "!?"

        if eval_string2 != "":
            if eval_string == "":
                eval_string = eval_string2

        # remember this evaluation for later pgn generation in PgnDisplay
        # key to find evaluation later =(ply halfmove number: int, move: chess.Move)
        # not always unique if we have takeback sequence with other moves
        # should work since we evaluate all moves and remove if no evaluation
        e_key = (self.board.ply(), current_move, self.board.turn) # halfmove key AFTER the move
        if eval_string == "":
            # due to takeback remove any possible previous evaluation
            self.evaluated_moves.pop(e_key, None)  # None prevents KeyError
        else:
            e_value = {}  # clear possible old value
            e_value["nag"] = PicoTutor.symbol_to_nag(eval_string)
            if current_pv:  # user move identified, not approximated
                e_value["score"] = current_score # eval score
                e_value["CPL"] = best_deep_diff  # lost centipawns
                if low_pv:  # low also identified, needs both current AND low
                    e_value["deep_low_diff"] = deep_low_diff # Cambridge delta S
                if before_score:  # not approximated, need both current AND history
                    e_value["score_hist_diff"] = score_hist_diff
            try:
                # board_before_usermove is where we have popped the user move above
                e_value["best_move"] = board_before_usermove.san(best_move)
                e_value["user_move"] = board_before_usermove.san(current_move)
            except (KeyError, ValueError, AttributeError):
                logger.warning("picotutor failed to convert to san for %s", current_move)
            finally:
                self.evaluated_moves[e_key] = e_value  # sometimes overwritten after takeback

        self.log_sync_info()  # debug only

        # information return in addition:
        # threat move / bestmove/ pv line of user and best pv line so picochess can comment on that as well
        # or call a pico talker method with that information
        self.hint_move[self.board.turn] = best_move

        logger.debug("evaluation %s", eval_string)
        return eval_string, current_mate

    @staticmethod
    def symbol_to_nag(eval_string: str) -> int:
        """convert an evaluation string like ! to NAG format like NAG_GOOD_MOVE"""
        symbol_to_nag = {
            "!": chess.pgn.NAG_GOOD_MOVE,         # $1
            "?": chess.pgn.NAG_MISTAKE,           # $2
            "!!": chess.pgn.NAG_BRILLIANT_MOVE,   # $3
            "??": chess.pgn.NAG_BLUNDER,          # $4
            "!?": chess.pgn.NAG_SPECULATIVE_MOVE, # $5
            "?!": chess.pgn.NAG_DUBIOUS_MOVE,     # $6
        }
        # empty or unrecognized str becomes NAG_NULL
        return symbol_to_nag.get(eval_string, chess.pgn.NAG_NULL)

    @staticmethod
    def nag_to_symbol(nag: int) -> str:
        """convert NAG format like NAG_GOOD_MOVE to an evaluation string like !"""
        nag_to_symbol = {
            chess.pgn.NAG_GOOD_MOVE: "!",
            chess.pgn.NAG_MISTAKE: "?",
            chess.pgn.NAG_BRILLIANT_MOVE: "!!",
            chess.pgn.NAG_BLUNDER: "??",
            chess.pgn.NAG_SPECULATIVE_MOVE: "!?",
            chess.pgn.NAG_DUBIOUS_MOVE: "?!",
            chess.pgn.NAG_NULL: "",
        }
        # NAG_NULL or unrecognized NAG becomes empty str
        return nag_to_symbol.get(nag, "")

    # Logic on halfmoves and fullmoves and move identification is
    # that we consider things AFTER the move has been done
    # fullmove, halfmove (ply), turn, all AFTER...
    # Example: After Bb5 we have 5 halfs, and 2 full, Black turn
    # Halfmove | Turn   | Fullmove | SAN
    # -------- | ------ | -------- | -----
    #    0     | White  |    0     | —
    #    1     | Black  |    0     | e4
    #    2     | White  |    1     | e5
    #    3     | Black  |    1     | Nf3
    #    4     | White  |    2     | Nc6
    #    5     | Black  |    2     | Bb5
    #    6     | White  |    3     | a6
    #    7     | Black  |    3     | Ba4
    #
    # SPECIAL: Black starts from a position setup, for example
    # assume 1.e4 was done but we dont know the move, just the position
    # Halfmove | Turn   | Fullmove | SAN
    # -------- | ------ | -------- | -----
    #    0     | Black  |    0     | e5
    #    1     | White  |    1     | Nf3
    #    2     | Black  |    1     | Nc6
    #    3     | White  |    2     | Bb5
    #    4     | Black  |    2     | a6
    #    5     | White  |    3     | Ba4
    #    6     | Black  |    3     | Nf6
    #    7     | White  |    4     | —

    # Note that board.fullmove_number does NOT decrease after board.pop()
    # but ply() is correct, so always take ply() first then convert to fullmove_number
    @staticmethod
    def halvmove_to_simple_fullmove(halfmove_nr: int, turn: chess.Color) -> int:
        """ simplified method when you know turn and
        dont care if it was first_move_black """
        t = PicoTutor.halfmove_to_fullmove(halfmove_nr, turn)
        return t[0]  # see tuple returned from method below

    @staticmethod
    def halfmove_to_fullmove(halfmove_nr: int, known_turn: chess.Color = None) -> Tuple:
        """convert halfmove_nr after a move to a fullmove_nr and turn
        1. e4 = halfmove 1 = fullmove 0, 1.-e5 = halfmove 2 = fullmove 1
        To support setup position with a black first move we need known_turn
        if known_turn not given its assumed that White made the first move
        and in this case the first_move_black will always return False"""
        assert halfmove_nr >= 0
        ply = halfmove_nr
        # BLACK has even halfnumbers = next turn is WHITE (see table above)
        turn = chess.WHITE if halfmove_nr % 2 == 0 else chess.BLACK
        if known_turn is not None and known_turn != turn:
            ply = ply + 1  # add missing whites first move before converting
            turn = known_turn  # return known turn as it differs
            first_move_black = True # inform caller that Black move first
        else:
            first_move_black = False # normal situation with White move first
        fullmove_nr = ply // 2  # simplest, see table above
        return fullmove_nr, turn, first_move_black

    @staticmethod
    def printable_fullmove(halfmove_nr: int, turn: chess.Color) -> int:
        """return fullmove to use when printing moves
        1. e4 = = fullmove 0 --> 1, 1.-e5 = fullmove 1 --> 1"""
        assert halfmove_nr >= 0
        fullmove_nr = PicoTutor.halvmove_to_simple_fullmove(halfmove_nr, turn)
        # for fullmove 0 and turn WHITE return value will be zero = unprintable
        return fullmove_nr + 1 if turn == chess.BLACK else fullmove_nr

    @staticmethod
    def printable_move_filler(halfmove_nr: int, turn: chess.Color) -> str:
        """ return filler str to put in front of uci or san move str 
        notice that input is halfmove_nr you get using board.ply()"""
        filler_str = str(PicoTutor.printable_fullmove(halfmove_nr, turn))
        filler_str += ". - " if turn == chess.WHITE else ". "
        return filler_str

    @staticmethod
    def fullmove_to_halfmove(fullmove_nr: int, turn: chess.Color, first_move_black: bool = None) -> int:
        """ convert back from fullmove to halfmove after a move
        1. e4 = halfmove 1 = fullmove 0, 1.-e5 = halfmove 2 = fullmove 1
        Note that board.pop() does not reduce fullmove number
        To support setup position with black first move we need to know first_move_black
        By default its assumed that White made the first move unless first_move_black=True"""
        assert fullmove_nr >= 0
        # for fullmove 0 and turn WHITE return value will be 0 = no move done
        # for fullmove 0 and turn BLACK White has moved once, or position setup
        halfmove_nr = fullmove_nr * 2
        if turn == chess.BLACK:
            halfmove_nr = halfmove_nr + 1 # add one halfmove after WHITE move
        if first_move_black is not None and first_move_black is True and halfmove_nr > 0:
            halfmove_nr = halfmove_nr - 1 # reduce with missing first WHITE move
        return halfmove_nr

    def get_eval_moves(self) -> dict:
        """return a dict of all evaluated moves"""
        return self.evaluated_moves

    def log_eval_moves(self):
        """debugging help to check list of evaluated moves"""
        logger.debug("picotutor evaluated moves:")
        for (halfmove_nr, user_move, known_turn), value in self.evaluated_moves.items():
            try:
                # example 2. d4! (fullmove 1) or 2. - exd4! (fullmove 2)
                # example 2. d4! (halfmove 3) or 2. - exd4! (halfmove 4)
                move_str = PicoTutor.printable_move_filler(halfmove_nr, known_turn)
                move_str += value.get("user_move", "")  # pre-stored short san for user_move
                best_move_str = value.get("best_move", "")
                nag_str = PicoTutor.nag_to_symbol(value.get("nag"))
                eval_score = " Score: " + str(value.get("score")) if "score" in value else ""
                lcp_str = " CPL: " + str(value.get("CPL")) if "CPL" in value else ""
                diff_str = " DS: " + str(value.get("deep_low_diff")) if "deep_low_diff" in value else ""
                hist_str = " hist: " + str(value.get("score_hist_diff")) if "score_hist_diff" in value else ""
                logger.debug("%s%s {best was %s%s%s%s%s}", move_str, nag_str, best_move_str, eval_score, lcp_str, diff_str, hist_str)
            except (KeyError, ValueError, AttributeError):
                logger.debug("failed to log full list of evaluated moves in picotutor")
                # dont care, just dont let this debug crash picotutor

    def get_user_move_info(self):
        """ return the hint move and the analysed InfoDict pv array of user chosen move"""
        if not (self.coach_on or self.watcher_on):
            return
        # not sending self.pv_best_move as its not used?
        return self.hint_move[self.board.turn], self.pv_user_move[self.board.turn]

    def get_pos_analysis(self):
        if not (self.coach_on or self.watcher_on):
            return
        # calculate material / position / mobility / development / threats / best move / best score
        # call a picotalker method with these information
        mate = 0
        score = 0

        try:
            self.eval_legal_moves()  # @todo - why do we need to call this?
            best_move = self.best_info[self.board.turn][0]["pv"][0]
        except IndexError:
            best_move = ""

        try:
            best_score = self.best_info[self.board.turn][0]["score"]
        except IndexError:
            best_score = 0

        if best_score.cp:
            score = best_score.cp / 100
        if best_score.mate:
            mate = best_score.mate

        try:
            pv_best_move = self.best_info[self.board.turn][0]["pv"]
        except IndexError:
            pv_best_move = []

        if mate > 0:
            score = 99999
        elif mate < 0:
            score = -99999

        return best_move, score, mate, pv_best_move, self.alt_best_moves[self.board.turn]
