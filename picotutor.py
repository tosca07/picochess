#!/usr/bin/env python3

# Copyright (C) 2013-2019 Jean-Francois Romang (jromang@posteo.de)
#                         Shivkumar Shivaji ()
#                         Jürgen Précour (LocutusOfPenguin@posteo.de)
#                         Molli (and thanks to Martin  for his opening
#                         identification code)
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
import chess  # type: ignore
import chess.uci  # type: ignore
import chess.engine  # type: ignore
from random import randint
from dgt.util import PicoComment
from typing import Tuple

# PicoTutor Constants
import picotutor_constants as c


class PicoTutor:

    def __init__(self, i_engine_path='/opt/picochess/engines/armv7l/a-stockf', i_player_color=chess.WHITE, i_fen='', i_comment_file='', i_lang='en'):
        self.user_color = i_player_color
        self.max_valid_moves = 200
        self.engine_path = i_engine_path
        self.engine = chess.uci.popen_engine(i_engine_path)
        self.engine2 = chess.uci.popen_engine(i_engine_path)
        self.engine.uci()
        self.engine2.uci()
        self.engine.setoption({"MultiPV": self.max_valid_moves})
        self.engine.setoption({"Contempt": 0})
        self.engine.setoption({"Threads": c.NUM_THREADS})
        self.engine2.setoption({"MultiPV": self.max_valid_moves})
        self.engine2.setoption({"Contempt": 0})
        self.engine2.setoption({"Threads": c.NUM_THREADS})
        self.engine.isready()
        self.engine2.isready()
        self.info_handler = chess.uci.InfoHandler()
        self.info_handler2 = chess.uci.InfoHandler()
        self.engine.info_handlers.append(self.info_handler)
        self.engine2.info_handlers.append(self.info_handler2)
        self.history = []
        self.history2 = []
        self.history.append((0, chess.Move.null(), 0.00, 0))
        self.history2.append((0, chess.Move.null(), 0.00, 0))
        self.pv_best_move = []
        self.pv_user_move = []
        self.pv_best_move2 = []
        self.pv_user_move2 = []
        self.hint_move = chess.Move.null()
        self.mate = 0
        self.legal_moves = []
        self.legal_moves2 = []
        self.op = []
        self.last_inside_book_moveno = 0
        self.alt_best_moves = []
        self.comments = []
        self.comment_no = 0
        self.comments_all = []
        self.comment_all_no = 0
        self.lang = i_lang
        self.pos = False
        self.watcher_on = True
        self.coach_on = False
        self.explorer_on = False
        self.comments_on = False

        try:
            with open("chess-eco_pos.txt") as fp:
                self.book_data = list(csv.DictReader(filter(lambda row: row[0] != '#', fp.readlines()), delimiter='|'))
        except EnvironmentError:
            self.book_data = []

        try:
            with open("opening_name_fen.txt") as fp:
                self.book_fen_data = fp.readlines()
        except Exception:
            self.book_fen_data = []

        self._setup_comments(i_lang, i_comment_file)

        self._setup_board(i_fen)

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
            general_comment_file = '/opt/picochess/engines/armv7l/general_game_comments_' + i_lang + '.txt'
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

    def set_status(self, watcher=False, coach=False, explorer=False, comments=False):

        if (self.watcher_on or self.coach_on):
            self.watcher_on = watcher
            self.coach_on = coach
            self.explorer_on = explorer
            self.comments_on = comments
            if (watcher or coach):
                self.reset()
            else:
                self.stop()
        else:
            self.watcher_on = watcher
            self.coach_on = coach
            self.explorer_on = explorer
            self.comments_on = comments
            if (watcher or coach):
                self.reset()
            else:
                pass

    def get_game_comment(self, pico_comment=PicoComment.COM_OFF, com_factor=0):
        max_range = 0
        max_range_all = 0
        range_fac = 0

        if com_factor == 0:
            return ''
        range_fac = round(100 / com_factor)
        max_range = self.comment_no * range_fac
        max_range_all = self.comment_all_no * range_fac

        if pico_comment == PicoComment.COM_ON_ENG:
            # get a comment by pure chance
            if self.comments and self.comment_no > 0:
                index = randint(0, max_range)
                if index > self.comment_no - 1:
                    return ''
                return self.comments[index]
            else:
                return ''
        elif pico_comment == PicoComment.COM_ON_ALL:
            # get a comment by pure chance
            if self.comments and self.comment_no > 0:
                index = randint(0, max_range)
                if index > self.comment_no - 1:
                    return ''
                return self.comments[index]
            else:
                if self.comments_all and self.comment_all_no > 0:
                    index = randint(0, max_range_all)
                    if index > self.comment_all_no - 1:
                        return ''
                    return self.comments_all[index]
                else:
                    return ''

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
        opening_name = moves = eco = ''
        for opening in self.book_data:
            # if len(opening.get('moves')) > 5:
            if played[:len(opening.get('moves'))] == opening.get('moves'):
                if len(opening.get('moves')) > len(moves):
                    opening_name = opening.get('opening_name')
                    moves = opening.get('moves')
                    eco = opening.get('eco')
        return opening_name, moves, eco

    def get_opening(self) -> Tuple[str, str, str, bool]:

        diff = self.board.fullmove_number - self.last_inside_book_moveno
        inside_book_opening = False

        opening_name = moves = eco = ''

        if self.op == [] or diff > 2:
            return eco, opening_name, moves, inside_book_opening

        played = '%s' % (' '.join(self.op))

        opening_name, moves, eco = self._find_longest_matching_opening(played)

        halfmoves = 2 * self.board.fullmove_number

        if self.board.turn:
            halfmoves -= 2
        else:
            halfmoves -= 1

        if halfmoves <= len(moves.split()):
            inside_book_opening = True
            self.last_inside_book_moveno = self.board.fullmove_number
        else:
            # try opening name based on FEN
            op_name = ''
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
        opening_name = ''

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
        self.pos = False
        self.legal_moves = []
        self.legal_moves2 = []
        self.op = []
        self.user_color = chess.WHITE
        self.board = chess.Board()

        self.stop()

        self.engine = chess.uci.popen_engine(self.engine_path)
        self.engine2 = chess.uci.popen_engine(self.engine_path)
        self.engine.uci()
        self.engine2.uci()
        self.engine.setoption({"MultiPV": self.max_valid_moves})
        self.engine.setoption({"Contempt": 0})
        self.engine.setoption({"Threads": c.NUM_THREADS})
        self.engine2.setoption({"MultiPV": self.max_valid_moves})
        self.engine2.setoption({"Contempt": 0})
        self.engine2.setoption({"Threads": c.NUM_THREADS})
        self.engine.isready()
        self.engine2.isready()
        self.info_handler = chess.uci.InfoHandler()
        self.info_handler2 = chess.uci.InfoHandler()
        self.engine.info_handlers.append(self.info_handler)
        self.engine2.info_handlers.append(self.info_handler2)
        self.engine.position(self.board)
        self.engine2.position(self.board)

        self.history = []
        self.history2 = []
        self.history.append((0, chess.Move.null(), 0.00, 0))
        self.history2.append((0, chess.Move.null(), 0.00, 0))

        self.alt_best_moves = []
        self.pv_best_move = []
        self.pv_user_move = []
        self.hint_move = chess.Move.null()
        self.mate = 0

    def set_user_color(self, i_user_color):

        self.pause()
        self.history = []
        self.history2 = []
        self.history.append((0, chess.Move.null(), 0.00, 0))
        self.history2.append((0, chess.Move.null(), 0.00, 0))
        self.legal_moves = []
        self.legal_moves2 = []
        self.hint_move = chess.Move.null()
        self.mate = 0
        self.pv_best_move = []
        self.pv_user_move = []
        self.hint_move = chess.Move.null()
        self.mate = 0

        self.user_color = i_user_color
        if self.user_color == self.board.turn and self.board.fullmove_number > 1:
            self.start()

    def get_user_color(self):
        return self.user_color

    def set_position(self, i_fen, i_turn=chess.WHITE):
        if not (self.coach_on or self.watcher_on):
            return
        self.reset()

        self.board = chess.Board(i_fen)
        chess.Board.turn = i_turn
        self.engine.position(self.board)
        self.engine2.position(self.board)
        self.pos = True

        if self.board.turn == self.user_color:
            # if it is user player's turn then start analyse engine
            # otherwise it is computer opponents turn and anaylze negine
            # should be paused
            self.start()
        else:
            self.pause()

    def push_move(self, i_uci_move):
        if i_uci_move not in self.board.legal_moves:
            return False

        self.op.append(self.board.san(i_uci_move))
        self.board.push(i_uci_move)

        if not (self.coach_on or self.watcher_on):
            return True

        self.pause()
        self.engine.position(self.board)
        self.engine.isready()
        self.engine2.position(self.board)
        self.engine2.isready()

        if self.board.turn == self.user_color:
            # if it is user player's turn then start analyse engine
            # otherwise it is computer opponents turn and analysis engine
            # should be paused
            self.start()
        else:
            self.eval_legal_moves()  # take snapshot of current evaluation
            self.eval_legal_moves2()
            self.eval_user_move(i_uci_move)  # determine & save evaluation of user move
            self.eval_user_move2(i_uci_move)  # determine & save evaluation of user move

        return True

    def _update_internal_history_after_pop(self, poped_move: chess.Move) -> None:
        try:
            if self.history[-1] == poped_move:
                self.history.pop()
        except IndexError:
            self.history.append((0, chess.Move.null(), 0.00, 0))

        try:
            if self.board.turn != self.user_color:
                if self.history2[-1] == poped_move:
                    self.history2.pop()
        except IndexError:
            self.history2.append((0, chess.Move.null(), 0.00, 0))

    def _update_internal_state_after_pop(self, poped_move: chess.Move) -> None:
        try:
            self.op.pop()
        except IndexError:
            pass

        if not (self.coach_on or self.watcher_on):
            return chess.Move.null()

        self.pause()
        self.engine.position(self.board)
        self.engine.isready()
        self.engine2.position(self.board)
        self.engine2.isready()

        if self.board.turn == self.user_color:
            # if it is user player's turn then start analyse engine
            # otherwise it is computer opponents turn and analyze negine
            # should be paused
            self.start()
        else:
            self.eval_legal_moves()
            self.eval_legal_moves2()

    def pop_last_move(self):
        poped_move = chess.Move.null()
        self.legal_moves = []
        self.legal_moves2 = []

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
        if self.engine2:
            self.engine2.position(self.board)
            self.engine2.go(depth=c.LOW_DEPTH, async_callback=True)

        if self.engine:
            self.engine.position(self.board)
            self.engine.go(depth=c.DEEP_DEPTH, async_callback=True)

    def pause(self):
        # during thinking time of opponent tutor should be paused
        # after the user move has been pushed
        if self.engine:
            self.engine.stop()
        if self.engine2:
            self.engine2.stop()

    def stop(self):
        if self.engine:
            self.engine.stop()
            self.engine.quit()
            self.engine = None
            self.info_handler = None
        if self.engine2:
            self.engine2.stop()
            self.engine2.quit()
            self.engine2 = None
            self.info_handler2 = None

    def print_score(self):
        if self.board.turn:
            print('White to move...')
        else:
            print('Black to move...')
            print(self.info_handler.info["pv"])
            print(self.info_handler.info["score"])

    def eval_user_move(self, user_move):
        if not (self.coach_on or self.watcher_on):
            return
        pv_no = 0
        eval = 0
        mate = 0
        loop_move = chess.Move.null()
        j = 0
        while loop_move != user_move and j < len(self.legal_moves):
            (pv_no, loop_move, eval, mate) = self.legal_moves[j]
            j = j + 1

        # add score to history list
        if loop_move == chess.Move.null() or loop_move != user_move:
            self.history.append((pv_no, user_move, eval, mate))
        else:
            self.history.append((pv_no, loop_move, eval, mate))
        if j > 0 and pv_no > 0:
            self.pv_best_move = self.info_handler.info["pv"][1]
            self.pv_user_move = self.info_handler.info["pv"][pv_no]
        else:
            self.pv_best_move = []
            self.pv_user_move = []

    def eval_user_move2(self, user_move):
        if not (self.coach_on or self.watcher_on):
            return
        pv_no = 0
        eval = 0
        mate = 0
        loop_move = chess.Move.null()
        j = 0
        while loop_move != user_move and j < len(self.legal_moves2):
            (pv_no, loop_move, eval, mate) = self.legal_moves2[j]
            j = j + 1

        # add score to history list
        if loop_move == chess.Move.null() or loop_move != user_move:
            self.history2.append((pv_no, user_move, eval, mate))
        else:
            self.history2.append((pv_no, loop_move, eval, mate))

        if j > 0 and pv_no > 0:
            self.pv_best_move2 = self.info_handler2.info["pv"][1]
            self.pv_user_move2 = self.info_handler2.info["pv"][pv_no]
        else:
            self.pv_best_move2 = []
            self.pv_user_move2 = []

    def sort_score(self, tupel):
        return tupel[2]

    @staticmethod
    def _eval_pv_list(pv_list, info_handler, legal_moves):
        best_score = -999

        for pv_key, pv_list in pv_list.items():
            if info_handler.info["score"][pv_key]:
                score_val = info_handler.info["score"][pv_key]
                move = chess.Move.null()

                score = 0
                mate = 0
                if score_val.cp:
                    score = score_val.cp / 100
                if pv_list[0]:
                    move = pv_list[0]
                if score_val.mate:
                    mate = int(score_val.mate)
                    if mate < 0:
                        score = -999
                    elif mate > 0:
                        score = 999
                legal_moves.append((pv_key, move, score, mate))
                if score >= best_score:
                    best_score = score

        return best_score

    def eval_legal_moves(self):
        if not (self.coach_on or self.watcher_on):
            return
        self.legal_moves = []
        self.alt_best_moves = []

        pv_list = self.info_handler.info["pv"]

        if pv_list:
            best_score = PicoTutor._eval_pv_list(pv_list, self.info_handler, self.legal_moves)

            # collect possible good alternative moves
            self.legal_moves.sort(key=self.sort_score, reverse=True)
            for (pv_key, move, score, mate) in self.legal_moves:
                if move:
                    diff = abs(best_score - score)
                    if diff <= 0.2:
                        self.alt_best_moves.append(move)

    def eval_legal_moves2(self):
        if not (self.coach_on or self.watcher_on):
            return
        self.legal_moves2 = []

        pv_list = self.info_handler2.info["pv"]

        if pv_list:
            PicoTutor._eval_pv_list(pv_list, self.info_handler2, self.legal_moves2)

        self.legal_moves2.sort(key=self.sort_score, reverse=True)

    def get_user_move_eval(self):
        if not (self.coach_on or self.watcher_on):
            return
        eval_string = ''
        best_mate = 0
        best_score = 0
        best_move = chess.Move.null()
        best_pv = []

        # user move score and previoues score
        if len(self.history) > 1:
            try:
                # last evaluation = for current user move
                current_pv, current_move, current_score, current_mate = self.history[-1]
            except IndexError:
                current_score = 0.0
                current_mate = ''
                eval_string = ''
                return eval_string, self.mate, self.hint_move

            try:
                before_pv, before_move, before_score, before_mate = self.history[-2]
            except IndexError:
                before_score = 0.0
                eval_string = ''
                return eval_string, self.mate, self.hint_move

        else:
            current_score = 0.0
            current_mate = ''
            before_score = 0.0
            eval_string = ''
            return eval_string, self.mate, self.hint_move

        # best deep engine score/move
        if self.legal_moves:
            best_pv, best_move, best_score, best_mate = self.legal_moves[0]  # tupel (pv,move,score,mate)

        # calculate diffs based on low depth search for obvious moves
        if len(self.history2) > 0:
            try:
                low_pv, low_move, low_score, low_mate = self.history2[-1]  # last evaluation = for current user move
            except IndexError:
                low_score = 0.0
                eval_string = ''
                return eval_string, self.mate, self.hint_move
        else:
            low_score = 0.0
            eval_string = ''
            return eval_string, self.mate, self.hint_move

        best_deep_diff = best_score - current_score
        deep_low_diff = current_score - low_score
        score_hist_diff = current_score - before_score

        # count legal moves in current position (for this we have to undo the user move)
        board_copy = self.board.copy()
        board_copy.pop()
        legal_no = len(list(board_copy.legal_moves))

        ###############################################################
        # 1. bad moves
        ##############################################################
        eval_string = ''

        # Blunder ??
        if best_deep_diff > c.VERY_BAD_MOVE_TH and legal_no:
            eval_string = '??'

        # Mistake ?
        elif best_deep_diff > c.BAD_MOVE_TH:
            eval_string = '?'

        # Dubious
        elif best_deep_diff > c.DUBIOUS_TH and abs(deep_low_diff) > c.UNCLEAR_DIFF and score_hist_diff > c.POS_INCREASE:
            eval_string = '?!'

        ###############################################################
        # 2. good moves
        ##############################################################
        eval_string2 = ''

        # very good moves
        if best_deep_diff <= c.VERY_GOOD_MOVE_TH and deep_low_diff > c.VERY_GOOD_IMPROVE_TH:
            if (best_score == 999 and (best_mate == current_mate)) and legal_no <= 2:
                pass
            else:
                eval_string2 = '!!'

        # good move
        elif best_deep_diff <= c.GOOD_MOVE_TH and deep_low_diff > c.GOOD_IMPROVE_TH and legal_no > 1:
            eval_string2 = '!'

        # interesting move
        elif best_deep_diff < c.INTERESTING_TH and abs(
                deep_low_diff) > c.UNCLEAR_DIFF and score_hist_diff < c.POS_DECREASE:
            eval_string2 = '!?'

        if eval_string2 != '':
            if eval_string == '':
                eval_string = eval_string2

        # information return in addition:
        # threat move / bestmove/ pv line of user and best pv line so picochess can comment on that as well
        # or call a pico talker method with that information
        self.mate = current_mate
        self.hint_move = best_move

        return eval_string, self.mate, self.hint_move

    def get_user_move_info(self):
        if not (self.coach_on or self.watcher_on):
            return
        return self.mate, self.hint_move, self.pv_best_move, self.pv_user_move

    def get_pos_analysis(self):
        if not (self.coach_on or self.watcher_on):
            return
        # calculate material / position / mobility / development / threats / best move / best score
        # call a picotalker method with these information
        mate = 0
        score = 0

        self.eval_legal_moves()  # take snapshot of current evaluation
        self.eval_legal_moves2()  # take snapshot of current evaluation

        try:
            best_move = self.info_handler.info["pv"][1][0]
        except IndexError:
            best_move = ''

        try:
            best_score = self.info_handler.info["score"][1]
        except IndexError:
            best_score = 0

        if best_score.cp:
            score = best_score.cp / 100
        if best_score.mate:
            mate = best_score.mate

        try:
            pv_best_move = self.info_handler.info["pv"][1]
        except IndexError:
            pv_best_move = []

        if mate > 0:
            score = 999
        elif mate < 0:
            score = -999

        return best_move, score, mate, pv_best_move, self.alt_best_moves
