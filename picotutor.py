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

symbol_to_nag = {
    "!": chess.pgn.NAG_GOOD_MOVE,         # $1
    "?": chess.pgn.NAG_MISTAKE,           # $2
    "!!": chess.pgn.NAG_BRILLIANT_MOVE,   # $3
    "??": chess.pgn.NAG_BLUNDER,          # $4
    "!?": chess.pgn.NAG_SPECULATIVE_MOVE, # $5
    "?!": chess.pgn.NAG_DUBIOUS_MOVE,     # $6
}

nag_to_symbol = {
    chess.pgn.NAG_GOOD_MOVE: "!",
    chess.pgn.NAG_MISTAKE: "?",
    chess.pgn.NAG_BRILLIANT_MOVE: "!!",
    chess.pgn.NAG_BLUNDER: "??",
    chess.pgn.NAG_SPECULATIVE_MOVE: "!?",
    chess.pgn.NAG_DUBIOUS_MOVE: "?!",
}

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
        self.user_color = i_player_color
        self.engine_path = i_engine_path

        self.engine = None  # or UciEngine
        self.best_info: list[InfoDict] = []  # best = deep
        self.obvious_info: list[InfoDict] = []  # obvious = low = shallow

        # history contain user made moves from above best or obvious
        # stored in list of tuple(index, move, score, mate)
        # index = None indicates not found in InfoDict results
        self.best_history = []
        self.obvious_history = []
        self.pv_user_move = []
        self.pv_best_move = []
        self.hint_move = chess.Move.null()
        self.mate = 0
        self.best_moves = []
        self.obvious_moves = []
        self.op = []  # used for opening book
        self.last_inside_book_moveno = 0
        self.alt_best_moves = []
        self.comments = []
        self.comment_no = 0
        self.comments_all = []
        self.comment_all_no = 0
        self.lang = i_lang
        self.expl_start_position = True
        self.pos = False  # do we need this in the new PicoTutor?
        self.watcher_on = False
        self.coach_on = False
        self.explorer_on = False
        self.comments_on = False
        self.mame_par = ""  # @todo create this info?
        self.board = chess.Board()
        self.ucishell = i_ucishell
        self.coach_analyser = i_coach_analyser
        self.loop = loop  # main loop everywhere
        self.deep_limit_depth = i_depth  # override picotutor value
        self.evaluated_moves = {} # key=(fullmove_number, turn, move) value={}

        try:
            with open("chess-eco_pos.txt") as fp:
                self.book_data = list(csv.DictReader(filter(lambda row: row[0] != "#", fp.readlines()), delimiter="|"))
        except EnvironmentError:
            self.book_data = []

        try:
            with open("opening_name_fen.txt") as fp:
                self.book_fen_data = fp.readlines()
        except Exception:
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

    def is_coach_analyser(self) -> bool:
        # to be an analyser for main we have to have a loaded engine
        # and the setting coach_analyser must be True in picochess.ini
        return (self.engine.loaded_ok() and self.coach_analyser) if self.engine else False

    def _setup_comments(self, i_lang, i_comment_file):
        if i_comment_file:
            try:
                with open(i_comment_file) as fp:
                    self.comments = fp.readlines()
            except Exception:
                self.comments = []

            if self.comments:
                self.comment_no = len(self.comments)

        try:
            arch = platform.machine()
            general_comment_file = "/opt/picochess/engines/" + arch + "/general_game_comments_" + i_lang + ".txt"
            with open(general_comment_file) as fp:
                self.comments_all = fp.readlines()
        except Exception:
            self.comments_all = []

        if self.comments_all:
            self.comment_all_no = len(self.comments_all)

    def _setup_board(self, i_fen):
        if i_fen:
            self.board = chess.Board(i_fen)
        else:
            self.board = chess.Board()  # starting position if no other set_position command comes

    def set_status(self, watcher=False, coach=PicoCoach.COACH_OFF, explorer=False, comments=False):
        if coach == PicoCoach.COACH_OFF:
            b_coach = False
        else:
            b_coach = True

        self.watcher_on = watcher
        self.coach_on = b_coach
        self.explorer_on = explorer
        self.comments_on = comments

        self.stop()

        if watcher or b_coach:
            self._reset_int()

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
            except Exception:
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

    def reset(self):
        # only called from one picotutor place, maybe not needed really?
        # set_status calls _reset_int anyway .... it could do that when needed
        self._reset_int()
        self.board = chess.Board()

    def _reset_int(self):
        logger.debug("picotutor reset")
        self.stop()
        self.pos = False
        self.best_moves = []
        self.obvious_moves = []
        self.op = []

        self.best_info = []
        self.obvious_info = []

        self.best_history = []
        self.obvious_history = []
        self.evaluated_moves = {}

        self.alt_best_moves = []
        self.pv_best_move = []
        self.pv_user_move = []

        self.hint_move = chess.Move.null()
        self.mate = 0
        self.expl_start_position = True

    async def set_user_color(self, i_user_color):
        logger.debug("picotutor set user color %s", i_user_color)
        self.pause()
        self.best_history = []
        self.obvious_history = []
        self.best_moves = []
        self.obvious_moves = []
        self.hint_move = chess.Move.null()
        self.mate = 0
        self.pv_best_move = []
        self.pv_user_move = []

        self.user_color = i_user_color
        if self.user_color == self.board.turn and self.board.fullmove_number > 1:
            await self.start()

    def get_user_color(self):
        return self.user_color

    async def set_position(self, i_fen, i_turn=chess.WHITE, i_ignore_expl=False):
        self.reset()
        self.board = chess.Board(i_fen)
        chess.Board.turn = i_turn

        if i_ignore_expl:
            fen = self.board.board_fen()
            if fen == chess.STARTING_BOARD_FEN:
                self.expl_start_position = True
            else:
                self.expl_start_position = False

        if not (self.coach_on or self.watcher_on):
            return

        self.pos = True

        # below code probably have no effect...
        # caller must call set_color to start analysis
        if self.board.turn == self.user_color:
            # if it is user player's turn then start analyse engine
            # otherwise it is computer opponents turn and anaylze negine
            # should be paused
            await self.start()
        else:
            self.pause()

    async def push_move(self, i_uci_move: chess.Move) -> bool:
        """inform picotutor that a board move was made"""
        logger.debug("picotutor push move %s", i_uci_move.uci())
        if i_uci_move not in self.board.legal_moves:
            logger.debug("picotutor received illegal move %s", i_uci_move.uci())
            # @todo take board as parameter so that we can resync in this case
            return False

        if not (self.coach_on or self.watcher_on):
            return True

        if self.board.turn != self.user_color:
            # if it is going to be user's turn start analyse engine
            # after the move has been pushed - and its users turn
            # otherwise it is computer opponents turn and analysis engine
            # should be paused
            self.op.append(self.board.san(i_uci_move))
            self.board.push(i_uci_move)
            await self.start()
        else:
            await self.eval_legal_moves()  # take snapshot of current evaluation
            self.eval_user_move(i_uci_move)  # determine & save evaluation of user move
            # push the move after evaluation
            self.op.append(self.board.san(i_uci_move))
            self.board.push(i_uci_move)
            self.pause()

        # self.log_sync_info()  # normally commented out
        return True

    def _update_internal_history_after_pop(self, poped_move: chess.Move) -> bool:
        """return True if sync is ok after pop = keep history"""
        result = True
        if self.board.turn == self.user_color:
            # need to pop user move
            try:
                pv_key, move, score, mate = self.best_history[-1]
                if move == poped_move:
                    self.best_history.pop()
                else:
                    result = False
                    logger.debug("picotutor pop best move not in sync")
                pv_key, move, score, mate = self.obvious_history[-1]
                if move == poped_move:
                    self.obvious_history.pop()
                else:
                    result = False
                    logger.debug("picotutor pop obvious move not in sync")
            except IndexError:
                result = False
                logger.debug("picotutor no obvious move to pop - not in sync")
        return result

    async def _update_internal_state_after_pop(self, poped_move: chess.Move) -> bool:
        """return True if sync is ok after pop = keep history"""
        try:
            self.op.pop()
        except IndexError:
            pass

        if not (self.coach_on or self.watcher_on):
            return False

        result = self._update_internal_history_after_pop(poped_move=poped_move)
        if self.board.turn == self.user_color:
            # if it is user player's turn then start analyse engine
            # otherwise it is computer opponents turn and analyze engine
            # should be paused
            await self.start()
        else:
            self.pause()
        return result

    async def pop_last_move(self) -> chess.Move:
        """inform picotutor that move takeback has been done"""
        poped_move = chess.Move.null()

        if self.board.move_stack:
            poped_move = self.board.pop()
            logger.debug("picotutor pop move %s", poped_move.uci())
            result = await self._update_internal_state_after_pop(poped_move)
            if not result:
                logger.debug("picotutor pop move not in sync - erasing history")
                self.best_moves = []
                self.obvious_moves = []

        self.log_sync_info()  # debug only
        return poped_move

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

    def pause(self):
        # during thinking time of opponent tutor should be paused
        # after the user move has been pushed
        if self.engine:
            self.engine.stop()

    def stop(self):
        if self.engine:
            self.engine.stop()

    def log_sync_info(self):
        """logging help to check if picotutor and main picochess are in sync"""
        logger.debug("picotutor op moves %s", self.op)
        moves = self.board.move_stack
        uci_moves = []
        for move in moves:
            uci_moves.append(move.uci())
        logger.debug("picotutor board moves %s", uci_moves)
        hist_moves = []
        if self.best_history:
            for pv_key, move, score, mate in self.best_history:
                hist_moves.append(move.uci())
        logger.debug("picotutor history moves %s", hist_moves)

    def log_pv_lists(self):
        """logging help for picotutor developers"""
        if self.board.turn:
            logger.debug("PicoTutor White to move %d", self.board.fullmove_number)
        else:
            logger.debug("PicoTutor Black to move %d", self.board.fullmove_number)
        if self.best_info:
            logger.debug("%d best:", len(self.best_info))
            for info in self.best_info:
                if "pv" in info and "score" in info and "depth" in info:
                    move, score, mate = PicoTutor._get_score(self.user_color, info)
                    logger.debug("%s score %d mate in %d depth %d", move.uci(), score, mate, info["depth"])
        if self.obvious_info:
            logger.debug("%d obvious:", len(self.obvious_info))
            for info in self.obvious_info:
                if "pv" in info and "score" in info and "depth" in info:
                    move, score, mate = PicoTutor._get_score(self.user_color, info)
                    logger.debug("%s score %d mate in %d depth %d", move.uci(), score, mate, info["depth"])

    def eval_user_move(self, user_move: chess.Move):
        """add user move to best and obvious history
        update the pv_best_move selection"""
        if not (self.coach_on or self.watcher_on):
            return
        # t tuple(pv_key, move, score, mate)
        t = self.in_best_moves(user_move)
        # add score to history list
        if t:
            pv_key = t[0]
            self.best_history.append(t)
            self.pv_best_move = self.best_info[0]["pv"]
            self.pv_user_move = self.best_info[pv_key]["pv"]
        else:
            logger.debug("did not find user move %s in best moves", user_move.uci())
            pv_key = None  # so that we know its not found
            score = mate = 0
            if self.best_moves:
                # user move is <= lowest score seen, last on list
                pv_extra_key, extra_move, score, mate = self.best_moves[-1]
            self.best_history.append((pv_key, user_move, score, mate))
            self.pv_best_move = []
            self.pv_user_move = []
        t = self.in_obvious_moves(user_move)
        # add score to history list
        if t:
            # pv_key = t[0]
            self.obvious_history.append(t)
        else:
            logger.debug("did not find user move %s in obvious moves", user_move.uci())
            pv_key = None  # so that we know its not found
            score = mate = 0
            if self.obvious_moves:
                # user move is <= lowest score seen, last on list
                pv_extra_key, extra_move, score, mate = self.obvious_moves[-1]
            self.obvious_history.append((pv_key, user_move, score, mate))

    def in_best_moves(self, user_move: chess.Move) -> tuple:
        """find move in obvious moves
        return None or tuple(pv_key, move, score, mate)"""
        for t in self.best_moves:
            # tuple index 1 is move
            if t[1] == user_move:
                return t
        return None

    def in_obvious_moves(self, user_move: chess.Move) -> tuple:
        """find move in obvious moves
        return None or tuple(pv_key, move, score)"""
        for t in self.obvious_moves:
            # tuple index 1 is move
            if t[1] == user_move:
                return t
        return None

    def sort_score(self, tupel):
        """define score:int as sort key"""
        return tupel[2]

    @staticmethod
    def _get_score(user_color: chess.Color, info: chess.engine.InfoDict) -> tuple:
        """return tuple (move, score, mate) extracted from info"""
        move = info["pv"][0] if "pv" in info else chess.Move.null()
        score = mate = 0
        if "score" in info:
            score_val = info["score"]
            m = score_val.pov(user_color).mate()
            mate = 0 if m is None else m
            if score_val.is_mate():
                score = score_val.pov(user_color).score(mate_score=99999)
            else:
                score = score_val.pov(user_color).score()
            return (move, score, mate)
        return (move, score, mate)

    # @todo re-design this method?
    @staticmethod
    def _eval_pv_list(user_color: chess.Color, info_list: list[InfoDict], best_moves) -> int | None:
        """fill in best_moves from InfoDict list
        it assumes best_moves is emptied before called
        :return the best score"""
        best_score = -99999
        pv_key = 0  # index in InfoDict list
        while pv_key < len(info_list):
            info: InfoDict = info_list[pv_key]
            move, score, mate = PicoTutor._get_score(user_color, info)
            # put an score: int here for sorting best moves
            best_moves.append((pv_key, move, score, mate))
            best_score = max(best_score, score)
            pv_key = pv_key + 1
        return best_score

    async def eval_legal_moves(self):
        """Update analysis information from engine"""
        if not (self.coach_on or self.watcher_on):
            return
        self.best_moves = []
        self.obvious_moves = []
        self.alt_best_moves = []
        # eval_pv_list below will build new lists
        result = await self.engine.get_analysis(self.board)
        self.obvious_info: list[chess.engine.InfoDict] = result.get("low")
        self.best_info: list[chess.engine.InfoDict] = result.get("best")
        if self.best_info:
            best_score = PicoTutor._eval_pv_list(self.user_color, self.best_info, self.best_moves)
            if self.best_moves:
                self.best_moves.sort(key=self.sort_score, reverse=True)
                # collect possible good alternative moves
                for pv_key, move, score, mate in self.best_moves:
                    if move:
                        diff = abs(best_score - score)
                        if diff <= 20:
                            self.alt_best_moves.append(move)
        if self.obvious_info:
            PicoTutor._eval_pv_list(self.user_color, self.obvious_info, self.obvious_moves)
            self.obvious_moves.sort(key=self.sort_score, reverse=True)
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
            return eval_string, self.mate

        # check precondition for calculations
        # more than one best and obvious move have to be found
        if (
            len(self.best_history) < 1
            or len(self.obvious_history) < 1
            or len(self.best_moves) < 2
            or len(self.obvious_moves) < 2
        ):
            eval_string = ""
            return eval_string, self.mate

        # user move score and previoues score
        # last evaluation = for current user move
        current_pv, current_move, current_score, current_mate = self.best_history[-1]
        # current_pv can be None if no best_move had been found

        if len(self.best_history) > 1:
            before_pv, before_move, before_score, before_mate = self.best_history[-2]
        else:
            before_score = None
        # before_pv can be None if no obvious move had been found

        # best deep engine score/move
        best_pv, best_move, best_score, best_mate = self.best_moves[0]
        # tupel (pv,move,score,mate)

        # calculate diffs based on low depth search for obvious moves
        low_pv, low_move, low_score, low_mate = self.obvious_history[-1]
        # last evaluation = for current user move
        # low_pv can be None if no if user move found in obvious_moves

        # optimisations in Picochess 4 - 200 wide multipv searches reduced to 5 to 50 ish
        # approximation_in_use is True when user misses either obvious or best history
        # user move might be missing in obvious history - can happen!
        #  --> low_score is lowest seen score, low_pv is None
        # user move might also be missing in best history
        #  --> current_score is lowest seen score, current_pv is None
        logger.debug("current evaluation score %d", current_score)
        best_deep_diff = best_score - current_score
        deep_low_diff = current_score - low_score
        approximations_in_use = current_pv is None or low_pv is None
        if approximations_in_use:
            logger.debug("approximations in use - only evaluating ? and ??")
            logger.debug("current_pv=%s low_pv=%s", current_pv, low_pv)
            logger.debug("approximated lost more than centipawns %d for move %s", best_deep_diff, current_move.uci())
        else:
            logger.debug("best_deep_diff lost centipawns %d for move %s", best_deep_diff, current_move.uci())
            logger.debug("evaluation deep_low_diff = %d", deep_low_diff)
        if before_score:
            score_hist_diff = current_score - before_score
            history_in_use = True
            logger.debug("evaluation score_hist_diff = %d", score_hist_diff)
        else:
            score_hist_diff = 0  # missing history before score
            history_in_use = False
            logger.debug("history before move not available - not evaluating !? and ?!")

        # count legal moves in current position (for this we have to undo the user move)
        legal_no = 0
        try:
            board_before_usermove: chess.Board = self.board.copy()
            board_before_usermove.pop()
            legal_no = board_before_usermove.legal_moves.count()
            logger.debug("number of legal moves %d", legal_no)
        except IndexError:
            # board_before_usermove.pop() failed, legal_no = 0
            logger.debug("strange - no user move to pop")
        if legal_no < 2:
            # there is no point evaluating the only legal or no pop()?
            eval_string = ""
            return eval_string, self.mate

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

        if eval_string != "":
            # we have an evaluation... remember it for later pgn generation
            # key=(fullmove_number, turn, move)
            try:
                # board_before_usermove is where we have popped the user move above
                e_key = (board_before_usermove.fullmove_number, board_before_usermove.turn, current_move)
                e_value = {}
                e_value["best_move"] = board_before_usermove.san(best_move)
                e_value["eval_string"] = eval_string  # pico eval string
                e_value["eval_nag"] = symbol_to_nag.get(eval_string, chess.pgn.NAG_NULL)
                e_value["user_move"] = board_before_usermove.san(current_move)
                if current_pv:
                    # we know the best and user move correct scores (not approximated)
                    e_value["eval_score"] = current_score # eval score
                    e_value["lcp"] = best_deep_diff  # lcp = lost centipawns
                    if low_pv:
                        # we know the score for min-ply obvious low (not approximated)
                        e_value["deep_low_diff"] = deep_low_diff # Cambridge delta S
                    if before_score:
                        # we know the score for previous move (not approximated)
                        e_value["score_hist_diff"] = score_hist_diff
                self.evaluated_moves[e_key] = e_value  # sometimes overwritten after takeback
                self.log_eval_moves() # debug only
            except Exception:
                logger.warning("failed to store evaluation of move %s", current_move)


        # information return in addition:
        # threat move / bestmove/ pv line of user and best pv line so picochess can comment on that as well
        # or call a pico talker method with that information
        self.mate = current_mate
        self.hint_move = best_move

        logger.debug("evaluation %s", eval_string)
        return eval_string, self.mate

    def log_eval_moves(self):
        """debugging help to check list of evaluated moves"""
        logger.debug("picotutor evaluated moves:")
        for key, value in self.evaluated_moves.items():
            try:
                # key=(fullmove_number, turn, chess.Move)
                move_nr_str = str(key[0]) # 2. d4! or 2. - exd4!
                filler_str = ". - " if key[1] == chess.BLACK else ". "
                move_str = value.get("user_move", "")
                best_move_str = value.get("best_move", "")
                eval_str = nag_to_symbol.get(value.get("eval_nag"))
                # Follow Stockfish standard evaluation in pawns
                eval_score = " eval " + str(value.get("eval_score") / 100.0) if "eval_score" in value else ""
                lcp_str = " lcp " + str(value.get("lcp")) if "lcp" in value else ""
                diff_str = " ds " + str(value.get("deep_low_diff")) if "deep_low_diff" in value else ""
                hist_str = " hist " + str(value.get("score_hist_diff")) if "score_hist_diff" in value else ""
                logger.debug("%s%s%s%s {best was %s%s%s%s%s}", move_nr_str, filler_str, move_str, eval_str, best_move_str, eval_score, lcp_str, diff_str, hist_str)
            except Exception:
                pass  # dont care, just dont let this debug crash picotutor

    def get_user_move_info(self):
        if not (self.coach_on or self.watcher_on):
            return
        # not sending self.pv_best_move as its not used?
        return self.hint_move, self.pv_user_move

    def get_pos_analysis(self):
        if not (self.coach_on or self.watcher_on):
            return
        # calculate material / position / mobility / development / threats / best move / best score
        # call a picotalker method with these information
        mate = 0
        score = 0

        self.eval_legal_moves()  # take snapshot of current evaluation

        try:
            best_move = self.best_info[0]["pv"][0]
        except IndexError:
            best_move = ""

        try:
            best_score = self.best_info[0]["score"]
        except IndexError:
            best_score = 0

        if best_score.cp:
            score = best_score.cp / 100
        if best_score.mate:
            mate = best_score.mate

        try:
            pv_best_move = self.best_info[0]["pv"]
        except IndexError:
            pv_best_move = []

        if mate > 0:
            score = 99999
        elif mate < 0:
            score = -99999

        return best_move, score, mate, pv_best_move, self.alt_best_moves
