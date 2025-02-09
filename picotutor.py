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
import chess  # type: ignore
from chess.engine import InfoDict
import chess.engine
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
    ):
        self.user_color = i_player_color
        self.engine_path = i_engine_path

        self.engine = None # or UciEngine
        self.best_info : list[InfoDict] = []  # best = deep
        self.obvious_info : list[InfoDict] = []  # obvious = low = shallow

        # history contain user made moves from above best or obvious
        # stored in list of tuple(index, move, score, mate)
        # index = None indicates not found in InfoDict results
        self.best_history = []
        self.best_history.append((0, chess.Move.null(), 0.00, 0))
        self.obvious_history = []
        self.obvious_history.append((0, chess.Move.null(), 0.00, 0))

        self.pv_user_move = []
        self.pv_best_move = []
        self.hint_move = chess.Move.null()
        self.mate = 0
        self.best_moves = []
        self.obvious_moves = []
        self.op = [] # list of played uci moves not needed?
        self.last_inside_book_moveno = 0
        self.alt_best_moves = []
        self.comments = []
        self.comment_no = 0
        self.comments_all = []
        self.comment_all_no = 0
        self.lang = i_lang
        self.expl_start_position = True
        self.pos = False # do we need this in the new PicoTutor?
        self.watcher_on = True
        self.coach_on = False
        self.explorer_on = False
        self.comments_on = False
        self.mame_par = "" # @todo create this info?
        self.board = chess.Board()
        self.ucishell = i_ucishell
        self.coach_analyser = i_coach_analyser
        self.loop = loop  # main loop everywhere

        try:
            with open("chess-eco_pos.txt") as fp:
                self.book_data = list(
                    csv.DictReader(
                        filter(lambda row: row[0] != "#", fp.readlines()), delimiter="|"
                    )
                )
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
        """ open the tutor engine """            
        if not self.engine and (self.watcher_on or self.coach_on):
            # start engine only if needed, obvious moves in first_limit
            self.engine = UciEngine(
                self.engine_path,
                self.ucishell,
                self.mame_par,
                self.loop
            )
            # avoid spreading await in this case
            await self.engine.open_engine()
            if self.engine.loaded_ok() is True:
                options = {
                    "MultiPV": c.VALID_ROOT_MOVES,
                    "Contempt": 0,
                    "Threads": c.NUM_THREADS
                }
                await self.engine.startup(options=options)
                self.engine.set_mode()  # not needed as we dont ponder?
            else:
                # No need to call engine quit if its not loaded?
                self.engine = None
        if self.engine is None:
            logger.debug("Engine loading failed in Picotutor")

    
    def is_coach_analyser(self) -> bool:
        return (
            self.coach_analyser and
            self.coach_on and
            self.watcher_on
        )


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
            general_comment_file = (
                "/opt/picochess/engines/aarch64/general_game_comments_" + i_lang + ".txt"
            )
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
        self._reset_int()
        self.board = chess.Board()


    def _reset_int(self):
        self.stop()
        self.pos = False
        self.best_moves = []
        self.obvious_moves = []
        self.op = []
        self.user_color = chess.WHITE

        self.best_info = []
        self.obvious_info = []

        self.best_history = []
        self.obvious_history = []
        self.best_history.append((0, chess.Move.null(), 0.00, 0))
        self.obvious_history.append((0, chess.Move.null(), 0.00, 0))

        self.alt_best_moves = []
        self.pv_best_move = []
        self.pv_user_move = []

        self.hint_move = chess.Move.null()
        self.mate = 0
        self.expl_start_position = True


    def set_user_color(self, i_user_color):

        self.pause()
        self.best_history = []
        self.obvious_history = []
        self.best_history.append((0, chess.Move.null(), 0.00, 0))
        self.obvious_history.append((0, chess.Move.null(), 0.00, 0))
        self.best_moves = []
        self.obvious_moves = []
        self.hint_move = chess.Move.null()
        self.mate = 0
        self.pv_best_move = []
        self.pv_user_move = []

        self.user_color = i_user_color
        if self.user_color == self.board.turn and self.board.fullmove_number > 1:
            self.start()

    def get_user_color(self):
        return self.user_color

    def set_position(self, i_fen, i_turn=chess.WHITE, i_ignore_expl=False):
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

        if self.board.turn == self.user_color:
            # if it is user player's turn then start analyse engine
            # otherwise it is computer opponents turn and anaylze negine
            # should be paused
            self.start()
        else:
            self.pause()

    def push_move(self, i_uci_move: chess.Move):
        if i_uci_move not in self.board.legal_moves:
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
            self.start()
        else:
            self.eval_legal_moves()  # take snapshot of current evaluation
            self.eval_user_move(i_uci_move)  # determine & save evaluation of user move
            # push the move after evaluation
            self.op.append(self.board.san(i_uci_move))
            self.board.push(i_uci_move)
            self.pause()

        return True


    def _update_internal_history_after_pop(self, poped_move: chess.Move) -> None:
        try:
            if self.best_history[-1] == poped_move:
                self.best_history.pop()
        except IndexError:
            self.best_history.append((-1, chess.Move.null(), 0.00, 0))
        try:
            if self.obvious_history[-1] == poped_move:
                self.obvious_history.pop()
        except IndexError:
            self.obvious_history.append((-1, chess.Move.null(), 0.00, 0))


    def _update_internal_state_after_pop(self, poped_move: chess.Move) -> None:
        try:
            self.op.pop()
        except IndexError:
            pass

        if not (self.coach_on or self.watcher_on):
            return chess.Move.null()

        self._update_internal_history_after_pop(poped_move=poped_move)

        if self.board.turn == self.user_color:
            # if it is user player's turn then start analyse engine
            # otherwise it is computer opponents turn and analyze negine
            # should be paused
            self.start()
        else:
            self.pause()

    def pop_last_move(self):
        poped_move = chess.Move.null()
        self.best_moves = []
        self.obvious_moves = []

        if self.board.move_stack:
            poped_move = self.board.pop()
            self._update_internal_state_after_pop(poped_move)

        return poped_move

    def get_stack(self):
        return self.board.move_stack

    def get_move_counter(self):
        return self.board.fullmove_number

    def start(self):
        # after newgame event
        if self.engine:
            if self.engine.loaded_ok():
                low_limit = chess.engine.Limit(depth=c.LOW_DEPTH)
                low_kwargs = {"limit": low_limit, "multipv": c.LOW_ROOT_MOVES}
                deep_limit = chess.engine.Limit(depth=c.DEEP_DEPTH)
                deep_kwargs = {"limit": deep_limit, "multipv": c.VALID_ROOT_MOVES}
                self.engine.start_analysis(self.board, deep_kwargs, low_kwargs)
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
            self.best_info = []
            self.obvious_info = []


    def log_pv_lists(self):
        """ logging help for picotutor developers """
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


    def eval_user_move(self, user_move:chess.Move):
        """ add user move to best and obvious history
            update the pv_best_move selection """
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
        t =self.in_obvious_moves(user_move)
        # add score to history list
        if t:
            #pv_key = t[0]
            self.obvious_history.append(t)
        else:
            logger.debug("did not find user move %s in obvious moves", user_move.uci())
            # @todo should we put pv_key -1 here instead?
            pv_key = None  # so that we know its not found
            score = mate = 0
            if self.obvious_moves:
                # user move is <= lowest score seen, last on list
                pv_extra_key, extra_move, score, mate = self.obvious_moves[-1]
            self.obvious_history.append((pv_key, user_move, score, mate))
    

    def in_best_moves(self, user_move: chess.Move) -> tuple:
        """ find move in obvious moves 
            return None or tuple(pv_key, move, score, mate) """
        for t in self.best_moves:
            # tuple index 1 is move
            if t[1] == user_move:
                return t
        return None

    def in_obvious_moves(self, user_move: chess.Move) -> tuple:
        """ find move in obvious moves 
            return None or tuple(pv_key, move, score) """
        for t in self.obvious_moves:
            # tuple index 1 is move
            if t[1] == user_move:
                return t
        return None

    def sort_score(self, tupel):
        """ define score:int as sort key """
        return tupel[2]


    @staticmethod
    def _get_score(user_color: chess.Color, info: chess.engine.InfoDict) -> tuple:
        """ return tuple (move, score, mate) extracted from info """
        move = info["pv"][0] if "pv" in info else chess.Move.null()
        score = mate = 0
        if "score" in info:
            score_val = info["score"]
            m = score_val.pov(user_color).mate()
            mate = 0 if m is None else m
            if score_val.is_mate():
                score = score_val.pov(user_color).score(mate_score=999)
            else:
                score = score_val.pov(user_color).score()
            return (move, score, mate)
        return (move, score, mate)


    # @todo re-design this method?
    @staticmethod
    def _eval_pv_list(user_color: chess.Color, info_list: list[InfoDict], best_moves) -> int | None:
        """ fill in best_moves from InfoDict list
            it assumes best_moves is emptied before called
            :return the best score """
        best_score = -999
        pv_key = 0  # index in InfoDict list
        while pv_key < len(info_list):
            info: InfoDict = info_list[pv_key]
            move, score, mate = PicoTutor._get_score(user_color, info)
            # put an score: int here for sorting best moves
            best_moves.append((pv_key, move, score, mate))
            best_score = max(best_score, score)
            pv_key = pv_key + 1
        return best_score


    def eval_legal_moves(self):
        """ Update analysis information from engine """
        if not (self.coach_on or self.watcher_on):
            return
        self.best_moves = []
        self.obvious_moves = []
        self.alt_best_moves = []
        # eval_pv_list below will build new lists
        result = self.engine.get_analysis(self.board)
        self.obvious_info: list[chess.engine.InfoDict] = result.get("low")
        self.best_info: list[chess.engine.InfoDict]  = result.get("best")
        if self.best_info:
            best_score = PicoTutor._eval_pv_list(self.user_color, self.best_info, self.best_moves)
            if self.best_moves:
                self.best_moves.sort(key=self.sort_score, reverse=True)
                # collect possible good alternative moves
                for (pv_key, move, score, mate) in self.best_moves:
                    if move:
                        diff = abs(best_score - score)
                        if diff <= 0.2:
                            self.alt_best_moves.append(move)
        if self.obvious_info:
            PicoTutor._eval_pv_list(self.user_color, self.obvious_info, self.obvious_moves)
            self.obvious_moves.sort(key= self.sort_score, reverse=True)
        self.log_pv_lists()


    def get_analysis(self) -> dict:
        """ get best move info if exists - during user thinking """
        # failed answer is empty lists
        result = {"low": [], "best": [], "fen": ""}
        if self.engine:
            if self.engine.is_analyser_running():
                result = self.engine.get_analysis(self.board)
        return result


    def get_user_move_eval(self) -> tuple:
        """ return eval str and moves to mate """
        if not (self.coach_on or self.watcher_on):
            return
        eval_string = ""
        best_mate = 0
        best_score = 0
        best_move = chess.Move.null()

        # check precondition for calculations
        if (
            len(self.best_history) < 2 or
            len(self.obvious_history) < 1 or
            len(self.best_moves) < 2 or
            len(self.obvious_moves) < 2
            ):
            eval_string = ""
            return eval_string, self.mate

        # user move score and previoues score
        # last evaluation = for current user move
        current_pv, current_move, current_score, current_mate = self.best_history[-1]
        # current_pv can be None if no best_move had been found

        before_pv, before_move, before_score, before_mate = self.best_history[-2]
        # before_pv can be None if no obvious move had been found

        # best deep engine score/move
        best_pv, best_move, best_score, best_mate = self.best_moves[0]
        # tupel (pv,move,score,mate)

        # calculate diffs based on low depth search for obvious moves
        low_pv, low_move, low_score, low_mate = self.obvious_history[-1]
        # last evaluation = for current user move
        # low_pv can be None if no if user move found in obvious_moves

        best_deep_diff = best_score - current_score
        logger.debug("lost centipawns %d for move %s", best_deep_diff, current_move.uci())
        # optimisations end of 2024 - no 200 wide multipv searches
        # not_in_obvious is compensating when low_pv is not reliable
        # user move might be missing in obvious history - can happen!
        #  --> low_score is lowest seen score, low_pv is None
        # obvious list is shorter --> low_score is not fully reliable
        # user move might also be missing in best history - not so likely
        #  --> current_score is lowest seen score, current_pv is None
        # best list is longer --> current_score and before_score reliable enough
        # not_in_best can be used to determine dubious or bad move
        deep_low_diff = current_score - low_score
        logger.debug("evaluation deep_low_diff = %d", deep_low_diff)
        not_in_obvious = low_pv is None and len(self.obvious_moves) > 3
        if not_in_obvious:
            logger.debug("user did not chose obvious move")
        # not_in_obvious is designed to be added to "> tests" with "or"
        score_hist_diff = current_score - before_score  # reliable enough
        not_in_best = current_pv is None  # user missed all top best moves
        if not_in_best:
            logger.debug("user missed all best moves")

        # count legal moves in current position (for this we have to undo the user move)
        board_copy = self.board.copy()
        board_copy.pop()
        legal_no = board_copy.legal_moves.count()
        logger.debug("number of legal moves %d", legal_no)
        if legal_no < 2:
            # there is no point evaluating the only legal move?
            eval_string = ""
            return eval_string, self.mate

        ###############################################################
        # 1. bad moves
        ##############################################################
        eval_string = ""

        # Blunder ??
        if best_deep_diff > c.VERY_BAD_MOVE_TH and legal_no:
            eval_string = "??"

        # Mistake ?
        elif best_deep_diff > c.BAD_MOVE_TH:
            eval_string = "?"

        # Dubious
        elif ((
            best_deep_diff > c.DUBIOUS_TH
            and (abs(deep_low_diff) > c.UNCLEAR_DIFF or not_in_obvious)
            and (score_hist_diff > c.POS_INCREASE))
            or (not_in_best and len(self.best_moves) > 4)
        ):
            eval_string = "?!"

        ###############################################################
        # 2. good moves
        ##############################################################
        eval_string2 = ""

        # very good moves
        if best_deep_diff <= c.VERY_GOOD_MOVE_TH and (deep_low_diff > c.VERY_GOOD_IMPROVE_TH or not_in_obvious):
            if (best_score == 999 and (best_mate == current_mate)) and legal_no <= 2:
                pass
            else:
                eval_string2 = "!!"

        # good move
        elif (
            best_deep_diff <= c.GOOD_MOVE_TH and (deep_low_diff > c.GOOD_IMPROVE_TH or not_in_obvious) and legal_no > 1
        ):
            eval_string2 = "!"

        # interesting move
        elif (
            best_deep_diff < c.INTERESTING_TH
            and (abs(deep_low_diff) > c.UNCLEAR_DIFF or not_in_obvious)
            and (score_hist_diff < c.POS_DECREASE)
        ):
            eval_string2 = "!?"

        if eval_string2 != "":
            if eval_string == "":
                eval_string = eval_string2

        # information return in addition:
        # threat move / bestmove/ pv line of user and best pv line so picochess can comment on that as well
        # or call a pico talker method with that information
        self.mate = current_mate
        self.hint_move = best_move

        logger.debug("evaluation %s", eval_string)
        return eval_string, self.mate


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
            score = 999
        elif mate < 0:
            score = -999

        return best_move, score, mate, pv_best_move, self.alt_best_moves
