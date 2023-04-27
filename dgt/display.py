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

from math import floor
from pgn import ModeInfo
import logging
import copy
import queue
import threading
import time
import chess  # type: ignore
from utilities import DisplayMsg, Observable, DispatchDgt, RepeatedTimer, write_picochess_ini
from dgt.menu import DgtMenu
from dgt.util import EBoard, ClockSide, ClockIcons, BeepLevel, Mode, GameResult, TimeMode, PlayMode
from dgt.api import Dgt, Event, Message
from timecontrol import TimeControl
from dgt.board import Rev2Info
from dgt.translate import DgtTranslate


logger = logging.getLogger(__name__)


class DgtDisplay(DisplayMsg, threading.Thread):

    """Dispatcher for Messages towards DGT hardware or back to the event system (picochess)."""

    def __init__(self, dgttranslate: DgtTranslate, dgtmenu: DgtMenu, time_control: TimeControl):
        super(DgtDisplay, self).__init__()
        self.dgttranslate = dgttranslate
        self.dgtmenu = dgtmenu
        self.time_control = time_control

        self.drawresign_fen = None
        self.show_move_or_value = 0
        self.leds_are_on = False

        self.play_move = self.hint_move = self.last_move = self.take_back_move = chess.Move.null()
        self.play_fen = self.hint_fen = self.last_fen = None
        self.play_turn = self.hint_turn = self.last_turn = None
        self.score: Dgt.DISPLAY_TEXT = self.dgttranslate.text('N10_score', None)
        self.depth = 0
        self.node = 0
        self.uci960 = False
        self.play_mode = PlayMode.USER_WHITE
        self.low_time = False
        self.c_last_player = ''
        self.c_time_counter = 0
        RepeatedTimer(1, self._process_once_per_second).start()

    def _convert_pico_string(self, pico_string):
        # print routine for longer text output like opening name, comments
        result_list = []
        result = ''
        if Rev2Info.get_web_only():
            text_length = 30
        else:
            text_length = 0
            if Rev2Info.get_new_rev2_mode():
                text_length = 11
            elif Rev2Info.get_pi_mode():
                text_length = 8
            else:
                text_length = 11

        if pico_string:
            op_list = pico_string.split()
            for op_part in op_list:
                if result:
                    help = result + ' ' + op_part
                else:
                    help = op_part
                if len(help) == text_length:
                    result_list.append(help)
                    help = ''
                    result = ''
                elif (text_length - len(help)) > 0:
                    # there is a small chance that we can still add another word
                    result = help
                    help = ''
                else:
                    # too long: save last result and keep current part
                    if result:
                        result_list.append(result)
                        if len(op_part) > text_length:
                            result_list.append(op_part[:text_length])
                            result_list.append(op_part[text_length:])
                            result = ''
                        else:
                            result = op_part
                        help = ''
                    else:
                        # too long: keep remain. result for next loop
                        result_list.append(help[:text_length])
                        result = help[text_length:]
                        help = ''

            if result:
                # if still chars left add them to the list!!!!
                if len(result) > text_length:
                    result_list.append(result[:text_length])
                    result = result[text_length:]

                result_list.append(result)
        return result_list

    def _exit_menu(self):
        if self.dgtmenu.exit_menu():
            DispatchDgt.fire(self.dgttranslate.text('K05_exitmenu'))
            return True
        return False

    def _power_off(self, dev='web'):
        DispatchDgt.fire(self.dgttranslate.text('Y15_goodbye'))
        self.dgtmenu.set_engine_restart(True)
        Observable.fire(Event.SHUTDOWN(dev=dev))

    def _reboot(self, dev='web'):
        DispatchDgt.fire(self.dgttranslate.text('Y15_pleasewait'))
        self.dgtmenu.set_engine_restart(True)
        self.c_last_player = ''
        self.c_time_counter = 0
        Observable.fire(Event.REBOOT(dev=dev))

    def _reset_moves_and_score(self):
        self.play_move = chess.Move.null()
        self.play_fen = None
        self.play_turn = None
        self.hint_move = chess.Move.null()
        self.hint_fen = None
        self.hint_turn = None
        self.last_move = chess.Move.null()
        self.last_fen = None
        self.last_turn = None
        self.score = self.dgttranslate.text('N10_score', None)
        self.depth = 0

    @staticmethod
    def _score_to_string(score_val, length='l'):
        if Rev2Info.get_web_only():
            try:
                return '{:9.2f}'.format(int(score_val) / 100), False
            except ValueError:
                return score_val, True
        else:
            if Rev2Info.get_new_rev2_mode():
                if length == 's':
                    return '{:5.2f}'.format(int(score_val) / 100)
                if length == 'm':
                    return '{:7.2f}'.format(int(score_val) / 100)
                if length == 'l':
                    return '{:9.2f}'.format(int(score_val) / 100)
            else:
                if length == 's':
                    return '{:5.2f}'.format(int(score_val) / 100).replace('.', '')
                if length == 'm':
                    return '{:7.2f}'.format(int(score_val) / 100).replace('.', '')
                if length == 'l':
                    return '{:9.2f}'.format(int(score_val) / 100).replace('.', '')

    def _combine_depth_and_score(self) -> Dgt.DISPLAY_TEXT:
        score = copy.copy(self.score)
        text_depth = self.dgttranslate.text('B10_analysis_depth')
        text_score = self.dgttranslate.text('B10_analysis_score')
        if Rev2Info.get_web_only():
            try:
                score_val, is_string = self._score_to_string(score.large_text[-15:])
                if is_string:
                    text_score.small_text = ''
                    score.web_text = text_depth.small_text + ' ' + str(
                        self.depth) + ' | ' + text_score.small_text + ' ' + score_val
                score.large_text = text_depth.small_text + ' ' + str(
                    self.depth) + ' | ' + text_score.small_text + ' ' + score_val
            except ValueError:
                score.web_text = text_depth + ' - | ' + text_score + ' - '
                score.large_text = text_depth + ' - | ' + text_score + ' - '
            return score
        else:
            try:
                if int(score.small_text) <= -1000:
                    score.small_text = '-999'
                if int(score.small_text) >= 1000:
                    score.small_text = '999'
                if Rev2Info.get_new_rev2_mode():
                    score.web_text = '{:2d}{:s}'.format(self.depth, self._score_to_string(score.large_text[-8:], 'l'))
                    score.large_text = '{:2d}{:s}'.format(self.depth, self._score_to_string(score.large_text[-8:], 'l'))
                    score.medium_text = '{:2d}{:s}'.format(self.depth % 100, self._score_to_string(score.medium_text[-6:], 'm'))
                    score.small_text = '{:2d}{:s}'.format(self.depth % 100, self._score_to_string(score.small_text[-4:], 's'))
                else:
                    score.web_text = '{:3d}{:s}'.format(self.depth, self._score_to_string(score.large_text[-8:], 'l'))
                    score.large_text = '{:3d}{:s}'.format(self.depth, self._score_to_string(score.large_text[-8:], 'l'))
                    score.medium_text = '{:2d}{:s}'.format(self.depth % 100, self._score_to_string(score.medium_text[-6:], 'm'))
                    score.small_text = '{:2d}{:s}'.format(self.depth % 100, self._score_to_string(score.small_text[-4:], 's'))
                score.rd = ClockIcons.DOT
            except ValueError:
                pass
            return score

    def _move_language(self, text: str, language: str, capital: bool, short: bool):
        """Return move text for clock display."""
        if short:
            directory = {}
            if language == 'de':
                directory = {'R': 'T', 'N': 'S', 'B': 'L', 'Q': 'D'}
            if language == 'nl':
                directory = {'R': 'T', 'N': 'P', 'B': 'L', 'Q': 'D'}
            if language == 'fr':
                directory = {'R': 'T', 'N': 'C', 'B': 'F', 'Q': 'D', 'K': '@'}
            if language == 'es':
                directory = {'R': 'T', 'N': 'C', 'B': 'A', 'Q': 'D', 'K': '@'}
            if language == 'it':
                directory = {'R': 'T', 'N': 'C', 'B': 'A', 'Q': 'D', 'K': '@'}
            for i, j in directory.items():
                text = text.replace(i, j)
            text = text.replace('@', 'R')  # replace the King "@" from fr, es, it languages
        if capital:
            return text.upper()
        else:
            return text

    def _combine_depth_and_score_and_hint(self) -> Dgt.DISPLAY_TEXT:
        score = copy.copy(self.score)
        text_depth = self.dgttranslate.text('B10_analysis_depth')
        text_score = self.dgttranslate.text('B10_analysis_score')
        try:
            score_val, is_string = self._score_to_string(score.large_text[-15:])
            if is_string:
                text_score.small_text = ''
            evaluation = text_depth.small_text + ' ' + str(self.depth) + ' | ' + text_score.small_text + ' ' + score_val
        except ValueError:
            evaluation = text_depth + ' - | ' + text_score + ' - '

        if self.hint_move:
            bit_board = chess.Board(self.hint_fen)
            side = self._get_clock_side(self.hint_turn)
            beep = self.dgttranslate.bl(BeepLevel.NO)
            text = Dgt.DISPLAY_MOVE(move=self.hint_move, fen=self.hint_fen, side=side, wait=True, maxtime=1,
                                    beep=beep, devs={'ser', 'i2c', 'web'}, uci960=self.uci960,
                                    lang=self.dgttranslate.language, capital=self.dgttranslate.capital,
                                    long=self.dgttranslate.notation)
            move_text = bit_board.san(text.move)
        else:
            move_text = ' - '
        short = True
        move_lang = self._move_language(move_text, self.dgttranslate.language, self.dgttranslate.capital, short)
        score.web_text = evaluation + ' | ' + move_lang
        score.large_text = evaluation + ' | ' + move_lang
        score.rd = ClockIcons.DOT
        return score

    @classmethod
    def _get_clock_side(cls, turn):
        side = ClockSide.LEFT if turn == chess.WHITE else ClockSide.RIGHT
        return side

    def _inside_main_menu(self):
        return self.dgtmenu.inside_main_menu()

    def _inside_updt_menu(self):
        return self.dgtmenu.inside_updt_menu()

    def _process_button0(self, dev):
        logger.debug('(%s) clock handle button 0 press', dev)
        if self._inside_main_menu():
            text = self.dgtmenu.main_up()  # button0 can exit the menu, so check
            if text:
                DispatchDgt.fire(text)
            else:
                self._exit_display()
        elif self._inside_updt_menu():
            self.dgtmenu.updt_up(dev)
            self._exit_display()  # button0 always exit the menu
        else:
            if self.last_move:
                side = self._get_clock_side(self.last_turn)
                beep = self.dgttranslate.bl(BeepLevel.BUTTON)
                text = Dgt.DISPLAY_MOVE(move=self.last_move, fen=self.last_fen, side=side, wait=False, maxtime=3,
                                        beep=beep, devs={'ser', 'i2c', 'web'}, uci960=self.uci960,
                                        lang=self.dgttranslate.language, capital=self.dgttranslate.capital,
                                        long=self.dgttranslate.notation)
            else:
                text = self.dgttranslate.text('B10_nomove')
            DispatchDgt.fire(text)
            self._exit_display()

    def _process_button1(self, dev):
        logger.debug('(%s) clock handle button 1 press', dev)
        if self._inside_main_menu():
            DispatchDgt.fire(self.dgtmenu.main_left())  # button1 cant exit the menu
        elif self._inside_updt_menu():
            DispatchDgt.fire(self.dgtmenu.updt_left())  # button1 cant exit the menu
        else:
            text = self._combine_depth_and_score()
            text.beep = self.dgttranslate.bl(BeepLevel.BUTTON)
            text.maxtime = 3
            DispatchDgt.fire(text)
            self._exit_display()

    def _process_button2(self, dev):
        logger.debug('(%s) clock handle button 2 press', dev)
        if self._inside_main_menu() or self.dgtmenu.inside_picochess_time(dev):
            text = self.dgtmenu.main_middle(dev)  # button2 can exit the menu (if in "position"), so check
            if text:
                DispatchDgt.fire(text)
            else:
                Observable.fire(Event.EXIT_MENU())
        else:
            if self.dgtmenu.get_mode() in (Mode.ANALYSIS, Mode.KIBITZ, Mode.PONDER):
                DispatchDgt.fire(self.dgttranslate.text('B00_nofunction'))
            else:
                if ModeInfo.get_pgn_mode():
                    Observable.fire(Event.PAUSE_RESUME())
                else:
                    if self.play_move:
                        self.play_move = chess.Move.null()
                        self.play_fen = None
                        self.play_turn = None
                        Observable.fire(Event.ALTERNATIVE_MOVE())
                    else:
                        Observable.fire(Event.PAUSE_RESUME())

    def _process_button3(self, dev):
        logger.debug('(%s) clock handle button 3 press', dev)
        if self._inside_main_menu():
            DispatchDgt.fire(self.dgtmenu.main_right())  # button3 cant exit the menu
        elif self._inside_updt_menu():
            DispatchDgt.fire(self.dgtmenu.updt_right())  # button3 cant exit the menu
        else:
            if self.hint_move:
                side = self._get_clock_side(self.hint_turn)
                beep = self.dgttranslate.bl(BeepLevel.BUTTON)
                text = Dgt.DISPLAY_MOVE(move=self.hint_move, fen=self.hint_fen, side=side, wait=False, maxtime=3,
                                        beep=beep, devs={'ser', 'i2c', 'web'}, uci960=self.uci960,
                                        lang=self.dgttranslate.language, capital=self.dgttranslate.capital,
                                        long=self.dgttranslate.notation)
            else:
                text = self.dgttranslate.text('B10_nomove')
            DispatchDgt.fire(text)
            self._exit_display()

    def _process_button4(self, dev):
        logger.debug('(%s) clock handle button 4 press', dev)
        if self._inside_updt_menu():
            tag = self.dgtmenu.updt_down(dev)
            Observable.fire(Event.UPDATE_PICO(tag=tag))
        else:
            text = self.dgtmenu.main_down()  # button4 can exit the menu, so check
            if text:
                DispatchDgt.fire(text)
            else:
                Observable.fire(Event.EXIT_MENU())

    def _process_lever(self, right_side_down, dev):
        logger.debug('(%s) clock handle lever press - right_side_down: %s', dev, right_side_down)
        self.c_time_counter = 0

        if self.c_last_player == 'C' or self.c_last_player == '':
            self.c_last_player = 'U'
        else:
            self.c_last_player = 'C'

        if not self._inside_main_menu():
            self.play_move = chess.Move.null()
            self.play_fen = None
            self.play_turn = None
            Observable.fire(Event.SWITCH_SIDES())
        else:
            self._exit_menu()
            # molli: necessary for engine name display after new game
            self.play_move = chess.Move.null()
            self.play_fen = None
            self.play_turn = None
            Observable.fire(Event.SWITCH_SIDES())

    def _process_button(self, message):
        button = int(message.button)
        if not self.dgtmenu.get_engine_restart():
            if button == 0:
                self._process_button0(message.dev)
            elif button == 1:
                self._process_button1(message.dev)
            elif button == 2:
                self._process_button2(message.dev)
            elif button == 3:
                self._process_button3(message.dev)
            elif button == 4:
                self._process_button4(message.dev)
            elif button == 0x11:
                self._reboot(message.dev)
            elif button == 0x20:
                self._power_off(message.dev)
            elif button == 0x40:
                self._process_lever(right_side_down=True, dev=message.dev)
            elif button == -0x40:
                self._process_lever(right_side_down=False, dev=message.dev)

    def _process_fen(self, fen, raw):
        level_map = ('rnbqkbnr/pppppppp/8/q7/8/8/PPPPPPPP/RNBQKBNR',
                     'rnbqkbnr/pppppppp/8/1q6/8/8/PPPPPPPP/RNBQKBNR',
                     'rnbqkbnr/pppppppp/8/2q5/8/8/PPPPPPPP/RNBQKBNR',
                     'rnbqkbnr/pppppppp/8/3q4/8/8/PPPPPPPP/RNBQKBNR',
                     'rnbqkbnr/pppppppp/8/4q3/8/8/PPPPPPPP/RNBQKBNR',
                     'rnbqkbnr/pppppppp/8/5q2/8/8/PPPPPPPP/RNBQKBNR',
                     'rnbqkbnr/pppppppp/8/6q1/8/8/PPPPPPPP/RNBQKBNR',
                     'rnbqkbnr/pppppppp/8/7q/8/8/PPPPPPPP/RNBQKBNR')

        book_map = ('rnbqkbnr/pppppppp/8/8/8/q7/PPPPPPPP/RNBQKBNR',
                    'rnbqkbnr/pppppppp/8/8/8/1q6/PPPPPPPP/RNBQKBNR',
                    'rnbqkbnr/pppppppp/8/8/8/2q5/PPPPPPPP/RNBQKBNR',
                    'rnbqkbnr/pppppppp/8/8/8/3q4/PPPPPPPP/RNBQKBNR',
                    'rnbqkbnr/pppppppp/8/8/8/4q3/PPPPPPPP/RNBQKBNR',
                    'rnbqkbnr/pppppppp/8/8/8/5q2/PPPPPPPP/RNBQKBNR',
                    'rnbqkbnr/pppppppp/8/8/8/6q1/PPPPPPPP/RNBQKBNR',
                    'rnbqkbnr/pppppppp/8/8/8/7q/PPPPPPPP/RNBQKBNR',
                    'rnbqkbnr/pppppppp/8/8/q7/8/PPPPPPPP/RNBQKBNR',
                    'rnbqkbnr/pppppppp/8/8/1q6/8/PPPPPPPP/RNBQKBNR',
                    'rnbqkbnr/pppppppp/8/8/2q5/8/PPPPPPPP/RNBQKBNR',
                    'rnbqkbnr/pppppppp/8/8/3q4/8/PPPPPPPP/RNBQKBNR',
                    'rnbqkbnr/pppppppp/8/8/4q3/8/PPPPPPPP/RNBQKBNR',
                    'rnbqkbnr/pppppppp/8/8/5q2/8/PPPPPPPP/RNBQKBNR',
                    'rnbqkbnr/pppppppp/8/8/6q1/8/PPPPPPPP/RNBQKBNR',
                    'rnbqkbnr/pppppppp/8/8/7q/8/PPPPPPPP/RNBQKBNR')

        engine_map = ('rnbqkbnr/pppppppp/q7/8/8/8/PPPPPPPP/RNBQKBNR',
                      'rnbqkbnr/pppppppp/1q6/8/8/8/PPPPPPPP/RNBQKBNR',
                      'rnbqkbnr/pppppppp/2q5/8/8/8/PPPPPPPP/RNBQKBNR',
                      'rnbqkbnr/pppppppp/3q4/8/8/8/PPPPPPPP/RNBQKBNR',
                      'rnbqkbnr/pppppppp/4q3/8/8/8/PPPPPPPP/RNBQKBNR',
                      'rnbqkbnr/pppppppp/5q2/8/8/8/PPPPPPPP/RNBQKBNR',
                      'rnbqkbnr/pppppppp/6q1/8/8/8/PPPPPPPP/RNBQKBNR',
                      'rnbqkbnr/pppppppp/7q/8/8/8/PPPPPPPP/RNBQKBNR')

        shutdown_map = ('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQQBNR',
                        'RNBQQBNR/PPPPPPPP/8/8/8/8/pppppppp/rnbkqbnr',
                        '8/8/8/8/8/8/8/3QQ3',
                        '3QQ3/8/8/8/8/8/8/8')

        reboot_map = ('rnbqqbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR',
                      'RNBKQBNR/PPPPPPPP/8/8/8/8/pppppppp/rnbqqbnr',
                      '8/8/8/8/8/8/8/3qq3',
                      '3qq3/8/8/8/8/8/8/8')

        mode_map = {'rnbqkbnr/pppppppp/8/Q7/8/8/PPPPPPPP/RNBQKBNR': Mode.NORMAL,
                    'rnbqkbnr/pppppppp/8/1Q6/8/8/PPPPPPPP/RNBQKBNR': Mode.BRAIN,
                    'rnbqkbnr/pppppppp/8/2Q5/8/8/PPPPPPPP/RNBQKBNR': Mode.ANALYSIS,
                    'rnbqkbnr/pppppppp/8/3Q4/8/8/PPPPPPPP/RNBQKBNR': Mode.KIBITZ,
                    'rnbqkbnr/pppppppp/8/4Q3/8/8/PPPPPPPP/RNBQKBNR': Mode.OBSERVE,
                    'rnbqkbnr/pppppppp/8/5Q2/8/8/PPPPPPPP/RNBQKBNR': Mode.PONDER,
                    'rnbqkbnr/pppppppp/8/6Q1/8/8/PPPPPPPP/RNBQKBNR': Mode.TRAINING,
                    'rnbqkbnr/pppppppp/8/7Q/8/8/PPPPPPPP/RNBQKBNR': Mode.REMOTE}

        drawresign_map = {'8/8/8/3k4/4K3/8/8/8': GameResult.WIN_WHITE,
                          '8/8/8/3K4/4k3/8/8/8': GameResult.WIN_WHITE,
                          '8/8/8/4k3/3K4/8/8/8': GameResult.WIN_BLACK,
                          '8/8/8/4K3/3k4/8/8/8': GameResult.WIN_BLACK,
                          '8/8/8/3kK3/8/8/8/8': GameResult.DRAW,
                          '8/8/8/3Kk3/8/8/8/8': GameResult.DRAW,
                          '8/8/8/8/3kK3/8/8/8': GameResult.DRAW,
                          '8/8/8/8/3Kk3/8/8/8': GameResult.DRAW}

        bit_board = chess.Board(fen + ' w - - 0 1')  # try a standard board and check for any starting pos
        if bit_board.chess960_pos(ignore_castling=True):
            logger.debug('flipping the board - W infront')
            self.dgtmenu.set_position_reverse_flipboard(False)
        bit_board = chess.Board(fen[::-1] + ' w - - 0 1')  # try a revered board and check for any starting pos
        if bit_board.chess960_pos(ignore_castling=True):
            logger.debug('flipping the board - B infront')
            self.dgtmenu.set_position_reverse_flipboard(True)
        if self.dgtmenu.get_flip_board() and raw:  # Flip the board if needed
            fen = fen[::-1]

        logger.debug('DGT-Fen [%s]', fen)
        if fen == self.dgtmenu.get_dgt_fen():
            logger.debug('ignore same fen')
            return
        self.dgtmenu.set_dgt_fen(fen)
        self.drawresign_fen = self._drawresign()
        # Fire the appropriate event
        if fen in level_map:
            eng = self.dgtmenu.get_engine()
            level_dict = eng['level_dict']
            if level_dict:
                inc = len(level_dict) / 7
                level = min(floor(inc * level_map.index(fen)), len(level_dict) - 1)  # type: int
                self.dgtmenu.set_engine_level(level)
                msg = sorted(level_dict)[level]
                text = self.dgttranslate.text('M10_level', msg)
                text.wait = self._exit_menu()
                logger.debug('map: New level %s', msg)
                if not self.dgtmenu.remote_engine and 'Remote' not in str(eng) and 'Online' not in str(eng) and 'FICS' not in str(eng) and 'lichess' not in str(eng) and 'Lichess' not in str(eng) and 'Lichess' not in str(eng) and 'PGN' not in str(eng):
                    write_picochess_ini('engine-level', msg)
                Observable.fire(Event.LEVEL(options=level_dict[msg], level_text=text, level_name=msg))
            else:
                logger.debug('engine doesnt support levels')
        elif fen in book_map:
            book_index = book_map.index(fen)
            try:
                book = self.dgtmenu.all_books[book_index]
                self.dgtmenu.set_book(book_index)
                logger.debug('map: Opening book [%s]', book['file'])
                text = book['text']
                text.beep = self.dgttranslate.bl(BeepLevel.MAP)
                text.maxtime = 1
                text.wait = self._exit_menu()
                Observable.fire(Event.SET_OPENING_BOOK(book=book, book_text=text, show_ok=False))
            except IndexError:
                pass
        elif fen in engine_map:
            if self.dgtmenu.installed_engines:
                try:
                    self.dgtmenu.set_engine_index(engine_map.index(fen))
                    eng = self.dgtmenu.get_engine()
                    self.dgtmenu.set_state_current_engine(eng['file'])
                    level_dict = eng['level_dict']
                    logger.debug('map: Engine name [%s]', eng['name'])
                    eng_text = eng['text']
                    eng_text.beep = self.dgttranslate.bl(BeepLevel.MAP)
                    eng_text.maxtime = 1
                    eng_text.wait = self._exit_menu()
                    if level_dict:
                        len_level = len(level_dict)
                        if self.dgtmenu.get_engine_level() is None or len_level <= self.dgtmenu.get_engine_level():
                            self.dgtmenu.set_engine_level(len_level - 1)
                        msg = sorted(level_dict)[self.dgtmenu.get_engine_level()]
                        options = level_dict[msg]  # cause of "new-engine", send options lateron - now only {}
                        Observable.fire(Event.LEVEL(options={}, level_text=self.dgttranslate.text('M10_level', msg),
                                                    level_name=msg))
                    else:
                        msg = None
                        options = {}
                    if not self.dgtmenu.remote_engine and 'Remote' not in str(eng) and 'Online' not in str(eng) and 'FICS' not in str(eng) and 'lichess' not in str(eng) and 'Lichess' not in str(eng) and 'Lichess' not in str(eng) and 'PGN' not in str(eng):
                        write_picochess_ini('engine-level', msg)
                    Observable.fire(Event.NEW_ENGINE(eng=eng, eng_text=eng_text, options=options, show_ok=False))
                    self.dgtmenu.set_engine_restart(True)
                except IndexError:
                    pass
            else:
                DispatchDgt.fire(self.dgttranslate.text('Y10_erroreng'))
        elif fen in mode_map:
            logger.debug('map: Interaction mode [%s]', mode_map[fen])
            if mode_map[fen] == Mode.BRAIN and not self.dgtmenu.get_engine_has_ponder():
                DispatchDgt.fire(self.dgttranslate.text('Y10_erroreng'))
            else:
                self.dgtmenu.set_mode(mode_map[fen])
                text = self.dgttranslate.text(mode_map[fen].value)
                text.beep = self.dgttranslate.bl(BeepLevel.MAP)
                text.maxtime = 1  # wait 1sec not forever
                text.wait = self._exit_menu()
                Observable.fire(Event.SET_INTERACTION_MODE(mode=mode_map[fen], mode_text=text, show_ok=False))

        elif fen in self.dgtmenu.tc_fixed_map:
            logger.debug('map: Time control fixed')
            self.dgtmenu.set_time_mode(TimeMode.FIXED)
            self.dgtmenu.set_time_fixed(list(self.dgtmenu.tc_fixed_map.keys()).index(fen))
            text = self.dgttranslate.text('M10_tc_fixed', self.dgtmenu.tc_fixed_list[self.dgtmenu.get_time_fixed()])
            text.wait = self._exit_menu()
            timectrl = self.dgtmenu.tc_fixed_map[fen]  # type: TimeControl
            Observable.fire(Event.SET_TIME_CONTROL(tc_init=timectrl.get_parameters(), time_text=text, show_ok=False))
        elif fen in self.dgtmenu.tc_blitz_map:
            logger.debug('map: Time control blitz')
            self.dgtmenu.set_time_mode(TimeMode.BLITZ)
            self.dgtmenu.set_time_blitz(list(self.dgtmenu.tc_blitz_map.keys()).index(fen))
            text = self.dgttranslate.text('M10_tc_blitz', self.dgtmenu.tc_blitz_list[self.dgtmenu.get_time_blitz()])
            text.wait = self._exit_menu()
            timectrl = self.dgtmenu.tc_blitz_map[fen]  # type: TimeControl
            Observable.fire(Event.SET_TIME_CONTROL(tc_init=timectrl.get_parameters(), time_text=text, show_ok=False))
        elif fen in self.dgtmenu.tc_fisch_map:
            logger.debug('map: Time control fischer')
            self.dgtmenu.set_time_mode(TimeMode.FISCHER)
            self.dgtmenu.set_time_fisch(list(self.dgtmenu.tc_fisch_map.keys()).index(fen))
            text = self.dgttranslate.text('M10_tc_fisch', self.dgtmenu.tc_fisch_list[self.dgtmenu.get_time_fisch()])
            text.wait = self._exit_menu()
            timectrl = self.dgtmenu.tc_fisch_map[fen]  # type: TimeControl
            Observable.fire(Event.SET_TIME_CONTROL(tc_init=timectrl.get_parameters(), time_text=text, show_ok=False))
        elif fen in shutdown_map:
            logger.debug('map: shutdown')
            self._power_off()
        elif fen in reboot_map:
            logger.debug('map: reboot')
            self._reboot()
        elif self.drawresign_fen in drawresign_map:
            if not self._inside_main_menu():
                logger.debug('map: drawresign')
                Observable.fire(Event.DRAWRESIGN(result=drawresign_map[self.drawresign_fen]))
        else:
            bit_board = chess.Board(fen + ' w - - 0 1')
            pos960 = bit_board.chess960_pos(ignore_castling=True)
            if pos960 is not None:
                if pos960 == 518 or self.dgtmenu.get_engine_has_960():
                    logger.debug('map: New game')
                    Observable.fire(Event.NEW_GAME(pos960=pos960))
                else:
                    # self._reset_moves_and_score()
                    DispatchDgt.fire(self.dgttranslate.text('Y10_error960'))
            else:
                Observable.fire(Event.FEN(fen=fen))

    def _process_engine_ready(self, message):
        for index in range(0, len(self.dgtmenu.installed_engines)):
            if self.dgtmenu.installed_engines[index]['file'] == message.eng['file']:
                self.dgtmenu.set_engine_index(index)
        self.dgtmenu.set_engine_has_960(message.has_960)
        self.dgtmenu.set_engine_has_ponder(message.has_ponder)
        if not self.dgtmenu.get_confirm() or not message.show_ok:
            DispatchDgt.fire(message.eng_text)
        self.dgtmenu.set_engine_restart(False)

    def _process_engine_startup(self, message):
        self.dgtmenu.installed_engines = message.installed_engines
        for index in range(0, len(self.dgtmenu.installed_engines)):
            eng = self.dgtmenu.installed_engines[index]
            if eng['file'] == message.file:
                self.dgtmenu.set_state_current_engine(message.file)
                self.dgtmenu.set_engine_index(index)
                self.dgtmenu.set_engine_has_960(message.has_960)
                self.dgtmenu.set_engine_has_ponder(message.has_ponder)
                self.dgtmenu.set_engine_level(message.level_index)

    def force_leds_off(self, log=False):
        """Clear the rev2 lights if they still on."""
        if self.leds_are_on:
            if log:
                logger.warning('(rev) leds still on')
        self.leds_are_on = False
        DispatchDgt.fire(Dgt.LIGHT_CLEAR(devs={'ser', 'web'}))

    def _process_start_new_game(self, message):
        self.c_time_counter = 0
        self.c_last_player = ''
        self.force_leds_off()
        self._reset_moves_and_score()
        self.time_control.reset()
        if message.newgame:
            pos960 = message.game.chess960_pos()
            self.uci960 = pos960 is not None and pos960 != 518
            DispatchDgt.fire(self.dgttranslate.text('C10_ucigame' if self.uci960 else 'C10_newgame', str(pos960)))
        if self.dgtmenu.get_mode() in (Mode.NORMAL, Mode.BRAIN, Mode.OBSERVE, Mode.REMOTE, Mode.TRAINING):
            self._set_clock()

    def _process_computer_move(self, message):
        self.force_leds_off(log=True)  # can happen in case of a book move
        move = message.move
        ponder = message.ponder
        self.play_move = move
        self.play_fen = message.game.fen()
        self.play_turn = message.game.turn
        if self.dgtmenu.current_board_type == EBoard.NOEBOARD:
            game_copy_dgt = message.game.copy()
            game_copy_dgt.push(move)
            self.dgtmenu.set_dgt_fen(game_copy_dgt.board_fen())

        if ponder:
            game_copy = message.game.copy()
            game_copy.push(move)
            self.hint_move = ponder
            self.hint_fen = game_copy.fen()
            self.hint_turn = game_copy.turn
        else:
            self.hint_move = chess.Move.null()
            self.hint_fen = None
            self.hint_turn = None
        # Display the move
        side = self._get_clock_side(message.game.turn)
        beep = self.dgttranslate.bl(BeepLevel.CONFIG)
        disp = Dgt.DISPLAY_MOVE(move=move, fen=message.game.fen(), side=side, wait=message.wait, maxtime=0,
                                beep=beep, devs={'ser', 'i2c', 'web'}, uci960=self.uci960,
                                lang=self.dgttranslate.language, capital=self.dgttranslate.capital,
                                long=self.dgttranslate.notation)
        DispatchDgt.fire(disp)
        DispatchDgt.fire(Dgt.LIGHT_SQUARES(uci_move=move.uci(), devs={'ser', 'web'}))
        self.leds_are_on = True
        self.c_time_counter = 0
        self.c_last_player = 'C'

    def _set_clock(self, side=ClockSide.NONE, devs=None):
        if devs is None:  # prevent W0102 error
            devs = {'ser', 'i2c', 'web'}
        time_left, time_right = self.time_control.get_internal_time(flip_board=self.dgtmenu.get_flip_board())
        DispatchDgt.fire(Dgt.CLOCK_SET(time_left=time_left, time_right=time_right, devs=devs))
        DispatchDgt.fire(Dgt.CLOCK_START(side=side, wait=True, devs=devs))

    def _display_confirm(self, text_key):
        if not self.low_time and not self.dgtmenu.get_confirm():  # only display if the user has >60sec on his clock
            DispatchDgt.fire(self.dgttranslate.text(text_key))

    def _process_computer_move_done(self):

        self.c_last_player = 'C'
        self.c_time_counter = 0
        self.force_leds_off()
        self.last_move = self.play_move
        self.last_fen = self.play_fen
        self.last_turn = self.play_turn
        self.play_move = chess.Move.null()
        self.play_fen = None
        self.play_turn = None
        self._exit_menu()

        if self.dgtmenu.get_time_mode() == TimeMode.FIXED:  # go back to a stopped time display and reset times
            self.time_control.reset()
            self._set_clock()

        if self.dgtmenu.get_mode() == Mode.TRAINING:
            self._display_confirm('K05_okmove')
            text = self._combine_depth_and_score()
            text.wait = True
            DispatchDgt.fire(text)
        else:
            self._display_confirm('K05_okpico')

    def _process_user_move_done(self, message):
        self.force_leds_off(log=True)  # can happen in case of a sliding move

        if self.c_last_player == 'C' or self.c_last_player == '':
            self.c_last_player = 'U'
        else:
            self.c_last_player = 'U'

        self.c_time_counter = 0

        self.last_move = message.move
        self.last_fen = message.fen
        if self.dgtmenu.current_board_type == EBoard.NOEBOARD:
            self.dgtmenu.set_dgt_fen(message.game.board_fen())

        self.last_turn = message.turn
        self.play_move = chess.Move.null()
        self.play_fen = None
        self.play_turn = None
        self._exit_menu()

        if self.dgtmenu.get_mode() == Mode.TRAINING:
            self._display_confirm('K05_okmove')
            text = self._combine_depth_and_score()
            text.wait = True
            DispatchDgt.fire(text)
        else:
            self._display_confirm('K05_okuser')

    def _process_review_move_done(self, message):

        self.force_leds_off(log=True)  # can happen in case of a sliding move
        self.last_move = message.move
        self.last_fen = message.fen
        self.last_turn = message.turn
        self._exit_menu()
        self._display_confirm('K05_okmove')
        self.c_last_player = ''
        self.c_time_counter = 0

    def _process_time_control(self, message):
        wait = not self.dgtmenu.get_confirm() or not message.show_ok
        if wait:
            DispatchDgt.fire(message.time_text)
        self.time_control = TimeControl(**message.tc_init)
        self._set_clock()

    def _process_new_score(self, message):
        if message.mate is None:
            score = int(message.score)
            if message.turn == chess.BLACK:
                score *= -1
            text = self.dgttranslate.text('N10_score', score)
        else:
            if message.turn == chess.BLACK:
                message.mate *= -1
            text = self.dgttranslate.text('N10_mate', str(message.mate))
        self.score = text
        if message.mode in (Mode.KIBITZ, Mode.TRAINING) and not self._inside_main_menu():
            text = self._combine_depth_and_score()
            text.wait = True
            DispatchDgt.fire(text)

    def _process_new_pv(self, message):
        self.hint_move = message.pv[0]
        self.hint_fen = message.game.fen()
        self.hint_turn = message.game.turn
        if message.mode == Mode.ANALYSIS and not self._inside_main_menu():
            side = self._get_clock_side(self.hint_turn)
            beep = self.dgttranslate.bl(BeepLevel.NO)
            disp = Dgt.DISPLAY_MOVE(move=self.hint_move, fen=self.hint_fen, side=side, wait=True, maxtime=0,
                                    beep=beep, devs={'ser', 'i2c', 'web'}, uci960=self.uci960,
                                    lang=self.dgttranslate.language, capital=self.dgttranslate.capital,
                                    long=self.dgttranslate.notation)
            DispatchDgt.fire(disp)

    def _process_startup_info(self, message):
        self.play_mode = message.info['play_mode']
        self.dgtmenu.set_mode(message.info['interaction_mode'])
        self.dgtmenu.set_book(message.info['book_index'])
        self.dgtmenu.all_books = message.info['books']
        tc_init = message.info['tc_init']
        timectrl = self.time_control = TimeControl(**tc_init)

        if timectrl.mode != TimeMode.FIXED and int(timectrl.moves_to_go_orig) > 0:
            l_timemode = TimeMode.TOURN
        elif int(timectrl.depth) > 0:
            l_timemode = TimeMode.DEPTH
        elif int(timectrl.node) > 0:
            l_timemode = TimeMode.NODE
        else:
            l_timemode = timectrl.mode

        self.dgtmenu.set_time_mode(l_timemode)
        # try to find the index from the given time_control (timectrl)
        # if user gave a non-existent timectrl value update map & list
        index = 0
        isnew = True
        if l_timemode == TimeMode.FIXED:
            for val in self.dgtmenu.tc_fixed_map.values():
                if val == timectrl:
                    self.dgtmenu.set_time_fixed(index)
                    isnew = False
                    break
                index += 1
            if isnew:
                self.dgtmenu.tc_fixed_map.update({('', timectrl)})
                self.dgtmenu.tc_fixed_list.append(timectrl.get_list_text())
                self.dgtmenu.set_time_fixed(index)
        elif l_timemode == TimeMode.BLITZ:
            for val in self.dgtmenu.tc_blitz_map.values():
                if val == timectrl:
                    self.dgtmenu.set_time_blitz(index)
                    isnew = False
                    break
                index += 1
            if isnew:
                self.dgtmenu.tc_blitz_map.update({('', timectrl)})
                self.dgtmenu.tc_blitz_list.append(timectrl.get_list_text())
                self.dgtmenu.set_time_blitz(index)
        elif l_timemode == TimeMode.FISCHER:
            for val in self.dgtmenu.tc_fisch_map.values():
                if val == timectrl:
                    self.dgtmenu.set_time_fisch(index)
                    isnew = False
                    break
                index += 1
            if isnew:
                self.dgtmenu.tc_fisch_map.update({('', timectrl)})
                self.dgtmenu.tc_fisch_list.append(timectrl.get_list_text())
                self.dgtmenu.set_time_fisch(index)
        elif l_timemode == TimeMode.TOURN:
            for val in self.dgtmenu.tc_tournaments:
                if val == timectrl:
                    self.dgtmenu.set_time_tourn(index)
                    isnew = False
                    break
                index += 1
            if isnew:
                self.dgtmenu.tc_tournaments.append(timectrl)
                self.dgtmenu.tc_tourn_list.append(timectrl.get_list_text())
                self.dgtmenu.set_time_tourn(index)
        elif l_timemode == TimeMode.DEPTH:
            logger.debug('molli: startup info Timemode Depth')
            for val in self.dgtmenu.tc_depths:
                if val.depth == timectrl.depth:
                    self.dgtmenu.set_time_depth(index)
                    isnew = False
                    break
                index += 1
            if isnew:
                self.dgtmenu.tc_depths.append(timectrl)
                self.dgtmenu.tc_depth_list.append(timectrl.get_list_text())
                self.dgtmenu.set_time_depth(index)
        elif l_timemode == TimeMode.NODE:
            logger.debug('molli: startup info Timemode Node')
            for val in self.dgtmenu.tc_nodes:
                if val.node == timectrl.node:
                    self.dgtmenu.set_time_node(index)
                    isnew = False
                    break
                index += 1
            if isnew:
                self.dgtmenu.tc_nodes.append(timectrl)
                self.dgtmenu.tc_node_list.append(timectrl.get_list_text())
                self.dgtmenu.set_time_node(index)

    def _process_clock_start(self, message):
        self.time_control = TimeControl(**message.tc_init)
        side = ClockSide.LEFT if (message.turn == chess.WHITE) != self.dgtmenu.get_flip_board() else ClockSide.RIGHT
        self._set_clock(side=side, devs=message.devs)

    def _process_once_per_second(self):
        # logger.debug('Serial number {}'.format(message.number))  # actually used for watchdog (once a second)
        # molli: rolling display
        if not self._inside_main_menu():
            if self.dgtmenu.get_mode() == Mode.PONDER:
                if not Rev2Info.get_web_only():
                    if self.show_move_or_value >= self.dgtmenu.get_ponderinterval():
                        if self.hint_move:
                            side = self._get_clock_side(self.hint_turn)
                            beep = self.dgttranslate.bl(BeepLevel.NO)
                            text = Dgt.DISPLAY_MOVE(move=self.hint_move, fen=self.hint_fen, side=side, wait=True, maxtime=1,
                                                    beep=beep, devs={'ser', 'i2c', 'web'}, uci960=self.uci960,
                                                    lang=self.dgttranslate.language, capital=self.dgttranslate.capital,
                                                    long=self.dgttranslate.notation)
                        else:
                            text = self.dgttranslate.text('N10_nomove')
                    else:
                        text = self._combine_depth_and_score()
                    text.wait = True
                    DispatchDgt.fire(text)
                    self.show_move_or_value = (self.show_move_or_value + 1) % (self.dgtmenu.get_ponderinterval() * 2)
                else:
                    text = self._combine_depth_and_score_and_hint()
                    text.wait = True
                    DispatchDgt.fire(text)
            elif (self.dgtmenu.get_mode() == Mode.BRAIN and self.dgtmenu.get_rolldispbrain()) or (self.dgtmenu.get_mode() == Mode.NORMAL and self.dgtmenu.get_rolldispnorm()):
                # molli: allow rolling information display (time/score/hint_move) in BRAIN mode according to
                #      ponder interval
                if self.play_move == chess.Move.null() and self.c_last_player == 'U':
                    if self.c_time_counter > 2 * self.dgtmenu.get_ponderinterval():
                        text = self._combine_depth_and_score()
                        text.wait = True
                        DispatchDgt.fire(text)
                        self.c_time_counter = (self.c_time_counter + 1) % (self.dgtmenu.get_ponderinterval() * 3)
                    elif self.c_time_counter > self.dgtmenu.get_ponderinterval():
                        if self.hint_move:
                            side = self._get_clock_side(self.hint_turn)
                            beep = self.dgttranslate.bl(BeepLevel.NO)
                            text = Dgt.DISPLAY_MOVE(move=self.hint_move, fen=self.hint_fen, side=side, wait=True, maxtime=1,
                                                    beep=beep, devs={'ser', 'i2c', 'web'}, uci960=self.uci960,
                                                    lang=self.dgttranslate.language, capital=self.dgttranslate.capital,
                                                    long=self.dgttranslate.notation)
                        else:
                            text = self.dgttranslate.text('N10_nomove')
                        text.wait = True
                        self.c_time_counter = (self.c_time_counter + 1) % (self.dgtmenu.get_ponderinterval() * 3)
                        DispatchDgt.fire(text)
                        if self.c_time_counter == 2 * self.dgtmenu.get_ponderinterval():
                            time.sleep(0.3)
                    else:
                        if self.c_time_counter == 0:
                            time.sleep(0.3)
                        self.c_time_counter = (self.c_time_counter + 1) % (self.dgtmenu.get_ponderinterval() * 3)
                        self._exit_display()
                        if self.c_time_counter == self.dgtmenu.get_ponderinterval():
                            time.sleep(0.3)

    def _drawresign(self):
        _, _, _, rnk_5, rnk_4, _, _, _ = self.dgtmenu.get_dgt_fen().split('/')
        return '8/8/8/' + rnk_5 + '/' + rnk_4 + '/8/8/8'

    def _exit_display(self, devs=None):
        if devs is None:  # prevent W0102 error
            devs = {'ser', 'i2c', 'web'}
        if self.play_move and self.dgtmenu.get_mode() in (Mode.NORMAL, Mode.BRAIN, Mode.REMOTE, Mode.TRAINING):
            side = self._get_clock_side(self.play_turn)
            beep = self.dgttranslate.bl(BeepLevel.BUTTON)
            text = Dgt.DISPLAY_MOVE(move=self.play_move, fen=self.play_fen, side=side, wait=True, maxtime=1,
                                    beep=beep, devs=devs, uci960=self.uci960, lang=self.dgttranslate.language,
                                    capital=self.dgttranslate.capital, long=self.dgttranslate.notation)
            DispatchDgt.fire(Dgt.LIGHT_SQUARES(uci_move=self.play_move.uci(), devs={'ser', 'web'}))
        else:
            text = None
            if self._inside_main_menu():
                text = self.dgtmenu.get_current_text()
            if text:
                text.wait = True  # in case of "bad pos" message send before
            else:
                if self.dgtmenu.get_mode() == Mode.TRAINING:
                    text = self._combine_depth_and_score()
                    text.wait = True
                else:
                    text = Dgt.DISPLAY_TIME(force=True, wait=True, devs=devs)

        DispatchDgt.fire(text)

    def _process_message(self, message):
        if False:  # switch-case
            pass

        elif isinstance(message, Message.ENGINE_READY):
            self._process_engine_ready(message)

        elif isinstance(message, Message.ENGINE_STARTUP):
            self._process_engine_startup(message)

        elif isinstance(message, Message.ENGINE_FAIL):
            DispatchDgt.fire(self.dgttranslate.text('Y10_erroreng'))
            self.dgtmenu.set_engine_restart(False)

        elif isinstance(message, Message.REMOTE_FAIL):
            DispatchDgt.fire(self.dgttranslate.text('Y10_erroreng'))

        elif isinstance(message, Message.COMPUTER_MOVE):
            self._process_computer_move(message)

        elif isinstance(message, Message.START_NEW_GAME):
            self._process_start_new_game(message)

        elif isinstance(message, Message.COMPUTER_MOVE_DONE):
            self._process_computer_move_done()

        elif isinstance(message, Message.USER_MOVE_DONE):
            self._process_user_move_done(message)

        elif isinstance(message, Message.REVIEW_MOVE_DONE):
            self._process_review_move_done(message)

        elif isinstance(message, Message.ALTERNATIVE_MOVE):
            self.force_leds_off()
            self.play_mode = message.play_mode
            self.play_move = chess.Move.null()
            DispatchDgt.fire(self.dgttranslate.text('B05_altmove'))

        elif isinstance(message, Message.LEVEL):
            if not self.dgtmenu.get_engine_restart():
                DispatchDgt.fire(message.level_text)

        elif isinstance(message, Message.TIME_CONTROL):
            self._process_time_control(message)

        elif isinstance(message, Message.OPENING_BOOK):
            if not self.dgtmenu.get_confirm() or not message.show_ok:
                DispatchDgt.fire(message.book_text)

        elif isinstance(message, Message.TAKE_BACK):
            self.take_back_move = chess.Move.null()
            game_copy = message.game.copy()

            self.force_leds_off()
            self._reset_moves_and_score()
            DispatchDgt.fire(self.dgttranslate.text('C10_takeback'))

            try:
                self.take_back_move = game_copy.pop()
            except Exception:
                self.take_back_move = chess.Move.null()

            if self.take_back_move != chess.Move.null():
                #  and not ModeInfo.get_pgn_mode()
                side = self._get_clock_side(game_copy.turn)
                beep = self.dgttranslate.bl(BeepLevel.NO)
                text = Dgt.DISPLAY_MOVE(move=self.take_back_move, fen=game_copy.fen(), side=side, wait=True, maxtime=1,
                                        beep=beep, devs={'ser', 'i2c', 'web'}, uci960=self.uci960,
                                        lang=self.dgttranslate.language, capital=self.dgttranslate.capital, long=True)  # molli: for take back display use long notation
                text.wait = True
                DispatchDgt.fire(text)
                self.force_leds_off()
                DispatchDgt.fire(Dgt.LIGHT_SQUARES(uci_move=self.take_back_move.uci(), devs={'ser', 'web'}))
                self.leds_are_on = True
            else:
                DispatchDgt.fire(Dgt.DISPLAY_TIME(force=True, wait=True, devs={'ser', 'i2c', 'web'}))

            self.c_time_counter = 0
            self.c_last_player = ''

        elif isinstance(message, Message.GAME_ENDS):
            logger.debug('game_ends outside if: result %s', message.result)
            if not self.dgtmenu.get_engine_restart():  # filter out the shutdown/reboot process
                logger.debug('inside if: result.value %s', message.result.value)
                if message.result == GameResult.DRAW:
                    ModeInfo.set_game_ending(result='1/2-1/2')
                elif message.result == GameResult.WIN_WHITE:
                    ModeInfo.set_game_ending(result='1-0')
                elif message.result == GameResult.WIN_BLACK:
                    ModeInfo.set_game_ending(result='0-1')
                elif message.result == GameResult.OUT_OF_TIME:
                    if message.game.turn == chess.WHITE:
                        ModeInfo.set_game_ending(result='0-1')
                    else:
                        ModeInfo.set_game_ending(result='1-0')

                text = self.dgttranslate.text(message.result.value)
                text.beep = self.dgttranslate.bl(BeepLevel.CONFIG)
                text.maxtime = 1
                DispatchDgt.fire(text)
                time.sleep(1)
                if self.dgtmenu.get_mode() in (Mode.PONDER, Mode.TRAINING):
                    self._reset_moves_and_score()
                    text.beep = False
                    text.maxtime = 1
                    self.score = text

            self.c_last_player = ''
            self.c_time_counter = 0

        elif isinstance(message, Message.INTERACTION_MODE):
            if not self.dgtmenu.get_confirm() or not message.show_ok:
                DispatchDgt.fire(message.mode_text)

        elif isinstance(message, Message.PLAY_MODE):
            self.force_leds_off()  # molli: in case of flashing take back move
            self.play_mode = message.play_mode
            DispatchDgt.fire(message.play_mode_text)

        elif isinstance(message, Message.NEW_SCORE):
            self._process_new_score(message)

        elif isinstance(message, Message.BOOK_MOVE):
            self.score = self.dgttranslate.text('N10_score', None)
            DispatchDgt.fire(self.dgttranslate.text('N10_bookmove'))

        elif isinstance(message, Message.NEW_PV):
            self._process_new_pv(message)

        elif isinstance(message, Message.NEW_DEPTH):
            self.depth = message.depth

        elif isinstance(message, Message.IP_INFO):
            self.dgtmenu.int_ip = message.info['int_ip']
            self.dgtmenu.ext_ip = message.info['ext_ip']

        elif isinstance(message, Message.STARTUP_INFO):
            self.force_leds_off()
            self._process_startup_info(message)

        elif isinstance(message, Message.SEARCH_STARTED):
            logger.debug('search started')

        elif isinstance(message, Message.SEARCH_STOPPED):
            logger.debug('search stopped')

        elif isinstance(message, Message.CLOCK_START):
            self._process_clock_start(message)

        elif isinstance(message, Message.CLOCK_STOP):
            DispatchDgt.fire(Dgt.CLOCK_STOP(devs=message.devs, wait=True))

        elif isinstance(message, Message.DGT_BUTTON):
            self._process_button(message)

        elif isinstance(message, Message.DGT_FEN):
            if self.dgtmenu.inside_updt_menu():
                logger.debug('inside update menu => ignore fen %s', message.fen)
            else:
                self._process_fen(message.fen, message.raw)

        elif isinstance(message, Message.DGT_CLOCK_VERSION):
            DispatchDgt.fire(Dgt.CLOCK_VERSION(main=message.main, sub=message.sub, devs={message.dev}))
            text = self.dgttranslate.text('Y21_picochess', devs={message.dev})
            text.rd = ClockIcons.DOT
            DispatchDgt.fire(text)

            if message.dev == 'ser':  # send the "board connected message" to serial clock
                DispatchDgt.fire(message.text)
            self._set_clock(devs={message.dev})
            self._exit_display(devs={message.dev})

        elif isinstance(message, Message.DGT_CLOCK_TIME):
            time_white = message.time_left
            time_black = message.time_right
            if self.dgtmenu.get_flip_board():
                time_white, time_black = time_black, time_white
            Observable.fire(Event.CLOCK_TIME(time_white=time_white, time_black=time_black, connect=message.connect, dev=message.dev))

        elif isinstance(message, Message.CLOCK_TIME):
            self.low_time = message.low_time
            if self.low_time:
                logger.debug('time too low, disable confirm - w: %i, b: %i', message.time_white, message.time_black)

        elif isinstance(message, Message.DGT_SERIAL_NR):
            pass

        elif isinstance(message, Message.DGT_JACK_CONNECTED_ERROR):  # only working in case of 2 clocks connected!
            DispatchDgt.fire(self.dgttranslate.text('Y00_errorjack'))

        elif isinstance(message, Message.DGT_EBOARD_VERSION):
            if self.dgtmenu.inside_updt_menu():
                logger.debug('inside update menu => board channel not displayed')
            else:
                DispatchDgt.fire(message.text)
                self._exit_display(devs={'i2c', 'web'})  # ser is done, when clock found

        elif isinstance(message, Message.DGT_NO_EBOARD_ERROR):
            if self.dgtmenu.inside_updt_menu() or self.dgtmenu.inside_main_menu():
                logger.debug('inside menu => board error not displayed')
            else:
                DispatchDgt.fire(message.text)

        elif isinstance(message, Message.DGT_NO_CLOCK_ERROR):
            pass

        elif isinstance(message, Message.SWITCH_SIDES):
            self.c_time_counter = 0

            if self.play_mode == PlayMode.USER_WHITE:
                self.play_mode == PlayMode.USER_BLACK
            else:
                self.play_mode == PlayMode.USER_WHITE

            self.play_move = chess.Move.null()
            self.play_fen = None
            self.play_turn = None

            self.hint_move = chess.Move.null()
            self.hint_fen = None
            self.hint_turn = None
            self.force_leds_off()
            logger.debug('user ignored move %s', message.move)

        elif isinstance(message, Message.EXIT_MENU):
            self._exit_display()

        elif isinstance(message, Message.WRONG_FEN):
            DispatchDgt.fire(self.dgttranslate.text('C10_setpieces'))
            time.sleep(1)

        elif isinstance(message, Message.UPDATE_PICO):
            DispatchDgt.fire(self.dgttranslate.text('Y00_update'))

        elif isinstance(message, Message.BATTERY):
            if message.percent == 0x7f:
                percent = ' NA'
            elif message.percent > 99:
                percent = ' 99'
            else:
                percent = str(message.percent)
            self.dgtmenu.battery = percent

        elif isinstance(message, Message.REMOTE_ROOM):
            self.dgtmenu.inside_room = message.inside

        elif isinstance(message, Message.RESTORE_GAME):
            DispatchDgt.fire(self.dgttranslate.text('C10_restoregame'))

        elif isinstance(message, Message.ENGINE_NAME):
            DispatchDgt.fire(self.dgttranslate.text('K20_enginename', message.engine_name))
            time.sleep(1.5)

        elif isinstance(message, Message.SHOW_TEXT):
            string_part = ''
            if message.text_string == 'NEW_POSITION':
                DispatchDgt.fire(self.dgttranslate.text('K20_newposition'))
                time.sleep(1.5)
            elif message.text_string == 'NEW_POSITION_SCAN':
                time.sleep(0.5)
            else:
                for string_part in self._convert_pico_string(message.text_string):
                    DispatchDgt.fire(self.dgttranslate.text('K20_default', string_part))
                    time.sleep(1.5)

        elif isinstance(message, Message.SEEKING):
            DispatchDgt.fire(self.dgttranslate.text('C10_seeking'))

        elif isinstance(message, Message.ENGINE_SETUP):
            DispatchDgt.fire(self.dgttranslate.text('C20_enginesetup'))

        elif isinstance(message, Message.MOVE_RETRY):
            DispatchDgt.fire(self.dgttranslate.text('C10_moveretry'))

        elif isinstance(message, Message.MOVE_WRONG):
            DispatchDgt.fire(self.dgttranslate.text('C10_movewrong'))

        elif isinstance(message, Message.SET_PLAYMODE):
            self.force_leds_off()  # molli: in case of flashing take back move
            self.play_mode = message.play_mode

        elif isinstance(message, Message.ONLINE_NAMES):
            logger.debug('molli: user online name %s', message.own_user)
            logger.debug('molli: opponent online name %s', message.opp_user)
            DispatchDgt.fire(self.dgttranslate.text('C10_onlineuser', message.opp_user))

        elif isinstance(message, Message.ONLINE_LOGIN):
            DispatchDgt.fire(self.dgttranslate.text('C10_login'))

        elif isinstance(message, Message.ONLINE_FAILED):
            DispatchDgt.fire(self.dgttranslate.text('C10_serverfailed'))

        elif isinstance(message, Message.ONLINE_USER_FAILED):
            DispatchDgt.fire(self.dgttranslate.text('C10_userfailed'))

        elif isinstance(message, Message.ONLINE_NO_OPPONENT):
            DispatchDgt.fire(self.dgttranslate.text('C10_noopponent'))

        elif isinstance(message, Message.LOST_ON_TIME):
            DispatchDgt.fire(self.dgttranslate.text('C10_gameresult_time'))

        elif isinstance(message, Message.SET_NOBOOK):
            self.dgtmenu.set_book(message.book_index)  # molli for emulation, online & pgn modes

        elif isinstance(message, Message.PICOTUTOR_MSG):
            DispatchDgt.fire(self.dgttranslate.text('C10_picotutor_msg', message.eval_str))
            if message.eval_str == 'POSOK' or message.eval_str == 'ANALYSIS' and self.play_move == chess.Move.null():
                self.force_leds_off()  # molli: sometime if you move the pieces too quickly a LED may still flash on the rev2

        elif isinstance(message, Message.POSITION_FAIL):
            self.force_leds_off()
            DispatchDgt.fire(self.dgttranslate.text('C10_position_fail', message.fen_result))
            DispatchDgt.fire(Dgt.LIGHT_SQUARE(square=message.fen_result[-2:], devs={'ser', 'web'}))
            self.leds_are_on = True
            time.sleep(3)

        elif isinstance(message, Message.SHOW_ENGINENAME):
            pass

        elif isinstance(message, Message.PICOWATCHER):
            pass

        elif isinstance(message, Message.PICOCOACH):
            pass

        elif isinstance(message, Message.PICOEXPLORER):
            pass

        elif isinstance(message, Message.PICOCOMMENT):
            pass

        elif isinstance(message, Message.RSPEED):
            pass

        elif isinstance(message, Message.CONTLAST):
            pass

        elif isinstance(message, Message.ALTMOVES):
            pass

        elif isinstance(message, Message.SAVE_GAME):
            pass

        elif isinstance(message, Message.READ_GAME):
            DispatchDgt.fire(self.dgttranslate.text('C10_game_read_menu'))

        elif isinstance(message, Message.TIMECONTROL_CHECK):
            msg_str = 'TC'
            DispatchDgt.fire(self.dgttranslate.text('C10_timecontrol_check', msg_str))
            time.sleep(2.5)
            msg_str = 'M' + str(message.movestogo) + 'mv/' + str(message.time1)
            DispatchDgt.fire(self.dgttranslate.text('C10_timecontrol_check', msg_str))
            time.sleep(3.5)
            msg_str = 'A' + str(message.time2) + 'min'
            DispatchDgt.fire(self.dgttranslate.text('C10_timecontrol_check', msg_str))
            time.sleep(3.5)

        elif isinstance(message, Message.PGN_GAME_END):
            DispatchDgt.fire(self.dgttranslate.text('C10_pgngame_end', message.result))

            if '1-0' in message.result:
                text = self.dgttranslate.text('C10_gameresult_white')
            elif '0-1' in message.result:
                text = self.dgttranslate.text('C10_gameresult_black')
            elif '0.5-0.5' in message.result or '1/2-1/2' in message.result:
                text = self.dgttranslate.text('C10_gameresult_draw')
            elif '*' in message.result:
                text = self.dgttranslate.text('C10_gameresult_unknown')
            else:
                text = self.dgttranslate.text('C10_gameresult_unknown')
            time.sleep(1.5)

            text.beep = self.dgttranslate.bl(BeepLevel.CONFIG)
            text.maxtime = 0.5

            DispatchDgt.fire(text)

        elif isinstance(message, Message.PROMOTION_DONE):
            DispatchDgt.fire(Dgt.PROMOTION_DONE(uci_move=message.move.uci(), devs={'ser'}))

        else:  # Default
            pass

    def run(self):
        """Call by threading.Thread start() function."""
        logger.info('msg_queue ready')
        while True:
            # Check if we have something to display
            try:
                message = self.msg_queue.get()
                if not isinstance(message, Message.DGT_SERIAL_NR):
                    logger.debug('received message from msg_queue: %s', message)
                self._process_message(message)
            except queue.Empty:
                pass
