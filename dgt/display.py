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

from math import floor
import logging
import copy
import asyncio
import chess  # type: ignore
import chess.variant  # type: ignore
from pgn import ModeInfo
from utilities import DisplayMsg, Observable, DispatchDgt, AsyncRepeatingTimer, write_picochess_ini, get_window_command
from timecontrol import TimeControl
from dgt.menu import DgtMenu
from dgt.util import ClockSide, ClockIcons, BeepLevel, Mode, GameResult, TimeMode, PlayMode, Top, flip_board_fen
from dgt.api import Dgt, Event, Message
from dgt.board import Rev2Info
from dgt.translate import DgtTranslate
import pairing_ipc

logger = logging.getLogger(__name__)


class DgtDisplay(DisplayMsg):
    """Dispatcher for Messages towards DGT hardware or back to the event system (picochess)."""

    ANALYSIS_MESSAGE_TYPES = (Message.NEW_DEPTH, Message.NEW_PV, Message.NEW_SCORE)

    def __init__(
        self, dgttranslate: DgtTranslate, dgtmenu: DgtMenu, time_control: TimeControl, loop: asyncio.AbstractEventLoop
    ):
        super(DgtDisplay, self).__init__(loop)
        self.dgttranslate = dgttranslate
        self.dgtmenu = dgtmenu
        self.time_control = time_control
        self.last_pos_start = True
        self._current_game_has_moves = False
        self._current_game_start_pos960 = 518
        self._setpieces_restore_pending = False
        self._start_position_restore_pending = False

        self.drawresign_fen = None
        self.have_seen_a_fen: bool = False  # issue #76 - avoid reboot/restart/exit looping
        self.show_move_or_value = 0
        self.leds_are_on = False

        self.play_move = self.hint_move = self.last_move = self.take_back_move = chess.Move.null()
        self.play_fen = self.hint_fen = self.last_fen = None
        self._current_variant = "chess"  # Updated by picochess via Message attributes
        self.play_turn = self.hint_turn = self.last_turn = None
        self.score = self.dgttranslate.text("N10_score", None)
        self.depth = 0
        self.node = 0
        self.uci960 = False
        self.play_mode = PlayMode.USER_WHITE
        self.low_time = False
        self.c_last_player = ""
        self.c_time_counter = 0
        self._task = None  # task for message consumer
        self.timer = AsyncRepeatingTimer(1, self._process_once_per_second, loop=self.loop)

    def start_once_per_second_timer(self):
        """start the once per second timer for rolling display"""
        self.timer.start()

    def stop_once_per_second_timer(self):
        """stop the once per second timer for rolling display"""
        self.timer.stop()

    def _convert_pico_string(self, pico_string):
        # print routine for longer text output like opening name, comments
        result_list = []
        result = ""
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
                    helptext = result + " " + op_part
                else:
                    helptext = op_part
                if len(helptext) == text_length:
                    result_list.append(helptext)
                    helptext = ""
                    result = ""
                elif (text_length - len(helptext)) > 0:
                    # there is a small chance that we can still add another word
                    result = helptext
                    helptext = ""
                else:
                    # too long: save last result and keep current part
                    if result:
                        result_list.append(result)
                        if len(op_part) > text_length:
                            result_list.append(op_part[:text_length])
                            result_list.append(op_part[text_length:])
                            result = ""
                        else:
                            result = op_part
                        helptext = ""
                    else:
                        # too long: keep remain. result for next loop
                        result_list.append(helptext[:text_length])
                        result = helptext[text_length:]
                        helptext = ""

            if result:
                # if still chars left add them to the list!!!!
                if len(result) > text_length:
                    result_list.append(result[:text_length])
                    result = result[text_length:]

                result_list.append(result)
        return result_list

    async def _exit_menu(self):
        if self.dgtmenu.exit_menu():
            await DispatchDgt.fire(self.dgttranslate.text("K05_exitmenu"))
            return True
        return False

    async def _power_off(self, dev="web"):
        await DispatchDgt.fire(self.dgttranslate.text("Y15_goodbye"))
        self.dgtmenu.set_engine_restart(True)
        await Observable.fire(Event.SHUTDOWN(dev=dev))

    async def _reboot(self, dev="web"):
        await DispatchDgt.fire(self.dgttranslate.text("Y15_pleasewait"))
        self.dgtmenu.set_engine_restart(True)
        self.c_last_player = ""
        self.c_time_counter = 0
        await Observable.fire(Event.REBOOT(dev=dev))

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
        self.score = self.dgttranslate.text("N10_score", None)
        self.depth = 0

    @staticmethod
    def _score_to_string(score_val, length="l"):
        if Rev2Info.get_web_only():
            try:
                return "{:9.2f}".format(int(score_val) / 100), False
            except ValueError:
                return score_val, True
        else:
            if Rev2Info.get_new_rev2_mode():
                if length == "s":
                    return "{:5.2f}".format(int(score_val) / 100)
                if length == "m":
                    return "{:7.2f}".format(int(score_val) / 100)
                if length == "l":
                    return "{:9.2f}".format(int(score_val) / 100)
            else:
                if length == "s":
                    return "{:5.2f}".format(int(score_val) / 100).replace(".", "")
                if length == "m":
                    return "{:7.2f}".format(int(score_val) / 100).replace(".", "")
                if length == "l":
                    return "{:9.2f}".format(int(score_val) / 100).replace(".", "")

    def _combine_depth_and_score(self):
        score = copy.copy(self.score)
        text_depth = self.dgttranslate.text("B10_analysis_depth")
        text_score = self.dgttranslate.text("B10_analysis_score")
        if Rev2Info.get_web_only():
            try:
                score_val, is_string = self._score_to_string(score.large_text[-15:])
                if is_string:
                    text_score.small_text = ""
                    score.web_text = (
                        text_depth.small_text + " " + str(self.depth) + " | " + text_score.small_text + " " + score_val
                    )
                score.large_text = (
                    text_depth.small_text + " " + str(self.depth) + " | " + text_score.small_text + " " + score_val
                )
            except ValueError:
                score.web_text = text_depth + " - | " + text_score + " - "
                score.large_text = text_depth + " - | " + text_score + " - "
            return score
        else:
            try:
                if int(score.small_text) <= -1000:
                    score.small_text = "-999"
                if int(score.small_text) >= 1000:
                    score.small_text = "999"
                if Rev2Info.get_new_rev2_mode():
                    score.web_text = "{:2d}{:s}".format(self.depth, self._score_to_string(score.large_text[-8:], "l"))
                    score.large_text = "{:2d}{:s}".format(self.depth, self._score_to_string(score.large_text[-8:], "l"))
                    score.medium_text = "{:2d}{:s}".format(
                        self.depth % 100, self._score_to_string(score.medium_text[-6:], "m")
                    )
                    score.small_text = "{:2d}{:s}".format(
                        self.depth % 100, self._score_to_string(score.small_text[-4:], "s")
                    )
                else:
                    score.web_text = "{:3d}{:s}".format(self.depth, self._score_to_string(score.large_text[-8:], "l"))
                    score.large_text = "{:3d}{:s}".format(self.depth, self._score_to_string(score.large_text[-8:], "l"))
                    score.medium_text = "{:2d}{:s}".format(
                        self.depth % 100, self._score_to_string(score.medium_text[-6:], "m")
                    )
                    score.small_text = "{:2d}{:s}".format(
                        self.depth % 100, self._score_to_string(score.small_text[-4:], "s")
                    )
                score.rd = ClockIcons.DOT
            except ValueError:
                pass
            return score

    def _move_language(self, text: str, language: str, capital: bool, short: bool):
        """Return move text for clock display."""
        if short:
            directory = {}
            if language == "de":
                directory = {"R": "T", "N": "S", "B": "L", "Q": "D"}
            if language == "nl":
                directory = {"R": "T", "N": "P", "B": "L", "Q": "D"}
            if language == "fr":
                directory = {"R": "T", "N": "C", "B": "F", "Q": "D", "K": "@"}
            if language == "es":
                directory = {"R": "T", "N": "C", "B": "A", "Q": "D", "K": "@"}
            if language == "it":
                directory = {"R": "T", "N": "C", "B": "A", "Q": "D", "K": "@"}
            for i, j in directory.items():
                text = text.replace(i, j)
            text = text.replace("@", "R")  # replace the King "@" from fr, es, it languages
        if capital:
            return text.upper()
        else:
            return text

    def _combine_depth_and_score_and_hint(self):
        score = copy.copy(self.score)
        text_depth = self.dgttranslate.text("B10_analysis_depth")
        text_score = self.dgttranslate.text("B10_analysis_score")
        try:
            score_val, is_string = self._score_to_string(score.large_text[-15:])
            if is_string:
                text_score.small_text = ""
            evaluation = text_depth.small_text + " " + str(self.depth) + " | " + text_score.small_text + " " + score_val
        except ValueError:
            evaluation = text_depth + " - | " + text_score + " - "

        if self.hint_move:
            bit_board = chess.Board(self.hint_fen)
            move_text = bit_board.san(self.hint_move)
        else:
            move_text = " - "
        short = True
        move_lang = self._move_language(move_text, self.dgttranslate.language, self.dgttranslate.capital, short)
        score.web_text = evaluation + " | " + move_lang
        score.large_text = evaluation + " | " + move_lang
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

    async def _process_button0(self, dev):
        logger.debug("(%s) clock handle button 0 press", dev)
        if self._inside_main_menu():
            text = self.dgtmenu.main_up()  # button0 can exit the menu, so check
            if text:
                await DispatchDgt.fire(text)
            else:
                await self._exit_display()
        elif self._inside_updt_menu():
            self.dgtmenu.updt_up(dev)
            await self._exit_display()  # button0 always exits the menu
        else:
            if self.last_move:
                side = self._get_clock_side(self.last_turn)
                beep = self.dgttranslate.bl(BeepLevel.BUTTON)
                text = Dgt.DISPLAY_MOVE(
                    move=self.last_move,
                    fen=self.last_fen,
                    side=side,
                    wait=False,
                    maxtime=3,
                    beep=beep,
                    devs={"ser", "i2c", "web"},
                    uci960=self.uci960,
                    lang=self.dgttranslate.language,
                    capital=self.dgttranslate.capital,
                    long=self.dgttranslate.notation,
                )
            else:
                text = self.dgttranslate.text("B10_nomove")
            await DispatchDgt.fire(text)
            await self._exit_display()

    async def _process_button1(self, dev):
        logger.debug("(%s) clock handle button 1 press", dev)
        if self._inside_main_menu():
            await DispatchDgt.fire(self.dgtmenu.main_left())  # button1 cant exit the menu
        elif self._inside_updt_menu():
            await DispatchDgt.fire(self.dgtmenu.updt_left())  # button1 cant exit the menu
        else:
            text = self._combine_depth_and_score()
            text.beep = self.dgttranslate.bl(BeepLevel.BUTTON)
            text.maxtime = 3
            await DispatchDgt.fire(text)
            await self._exit_display()

    async def _process_button2(self, dev):
        logger.debug("(%s) clock handle button 2 press", dev)
        if self._inside_main_menu() or self.dgtmenu.inside_picochess_time(dev):
            text = self.dgtmenu.main_middle(dev)  # button2 can exit the menu (if in "position"), so check
            if text:
                await DispatchDgt.fire(text)
            else:
                await Observable.fire(Event.EXIT_MENU())
        else:
            if self.dgtmenu.get_mode() in (Mode.ANALYSIS, Mode.KIBITZ, Mode.PONDER):
                await DispatchDgt.fire(self.dgttranslate.text("B00_nofunction"))
            elif self.dgtmenu.get_mode() == Mode.PGNREPLAY:
                # launch new built in pgn game replay in autoplay mode
                await Observable.fire(Event.PAUSE_RESUME())
            else:
                if ModeInfo.get_pgn_mode():
                    await Observable.fire(Event.PAUSE_RESUME())
                else:
                    if self.play_move:
                        self.play_move = chess.Move.null()
                        self.play_fen = None
                        self.play_turn = None
                        await Observable.fire(Event.ALTERNATIVE_MOVE())
                    else:
                        await Observable.fire(Event.PAUSE_RESUME())

    async def _process_button3(self, dev):
        logger.debug("(%s) clock handle button 3 press", dev)
        if self._inside_main_menu():
            await DispatchDgt.fire(self.dgtmenu.main_right())  # button3 cant exit the menu
        elif self._inside_updt_menu():
            await DispatchDgt.fire(self.dgtmenu.updt_right())  # button3 cant exit the menu
        else:
            if self.hint_move:
                side = self._get_clock_side(self.hint_turn)
                beep = self.dgttranslate.bl(BeepLevel.BUTTON)
                text = Dgt.DISPLAY_MOVE(
                    move=self.hint_move,
                    fen=self.hint_fen,
                    side=side,
                    wait=False,
                    maxtime=3,
                    beep=beep,
                    devs={"ser", "i2c", "web"},
                    uci960=self.uci960,
                    lang=self.dgttranslate.language,
                    capital=self.dgttranslate.capital,
                    long=self.dgttranslate.notation,
                )
            else:
                text = self.dgttranslate.text("B10_nomove")
            await DispatchDgt.fire(text)
            await self._exit_display()

    async def _process_button4(self, dev):
        logger.debug("(%s) clock handle button 4 press", dev)
        if self._inside_updt_menu():
            tag = self.dgtmenu.updt_down(dev)
            await Observable.fire(Event.UPDATE_PICO(tag=tag))
        else:
            text = await self.dgtmenu.main_down()  # button4 can exit the menu, so check
            if text:
                await DispatchDgt.fire(text)
            else:
                await Observable.fire(Event.EXIT_MENU())

    async def _process_lever(self, right_side_down, dev):
        logger.debug("(%s) clock handle lever press - right_side_down: %s", dev, right_side_down)
        self.c_time_counter = 0

        if self.c_last_player == "C" or self.c_last_player == "":
            self.c_last_player = "U"
        else:
            self.c_last_player = "C"

        if not self._inside_main_menu():
            self.play_move = chess.Move.null()
            self.play_fen = None
            self.play_turn = None
            await Observable.fire(Event.SWITCH_SIDES())
        else:
            await self._exit_menu()
            # molli: necessary for engine name display after new game
            self.play_move = chess.Move.null()
            self.play_fen = None
            self.play_turn = None
            await Observable.fire(Event.SWITCH_SIDES())

    async def _process_button(self, message):
        button = int(message.button)
        logger.debug("DGT button: %d processed", button)
        if pairing_ipc.is_active():
            await pairing_ipc.forward_button(button, message.dev)
            return
        if not self.dgtmenu.get_engine_restart():
            if button == 0:
                await self._process_button0(message.dev)
            elif button == 1:
                await self._process_button1(message.dev)
            elif button == 2:
                await self._process_button2(message.dev)
            elif button == 3:
                await self._process_button3(message.dev)
            elif button == 4:
                await self._process_button4(message.dev)
            elif button == 0x11:
                await self._reboot(message.dev)
            elif button == 0x20:
                await self._power_off(message.dev)
            elif button == 0x40:
                await self._process_lever(right_side_down=True, dev=message.dev)
            elif button == -0x40:
                await self._process_lever(right_side_down=False, dev=message.dev)

    async def _process_fen(self, fen, raw):
        level_map = (
            "rnbqkbnr/pppppppp/8/q7/8/8/PPPPPPPP/RNBQKBNR",
            "rnbqkbnr/pppppppp/8/1q6/8/8/PPPPPPPP/RNBQKBNR",
            "rnbqkbnr/pppppppp/8/2q5/8/8/PPPPPPPP/RNBQKBNR",
            "rnbqkbnr/pppppppp/8/3q4/8/8/PPPPPPPP/RNBQKBNR",
            "rnbqkbnr/pppppppp/8/4q3/8/8/PPPPPPPP/RNBQKBNR",
            "rnbqkbnr/pppppppp/8/5q2/8/8/PPPPPPPP/RNBQKBNR",
            "rnbqkbnr/pppppppp/8/6q1/8/8/PPPPPPPP/RNBQKBNR",
            "rnbqkbnr/pppppppp/8/7q/8/8/PPPPPPPP/RNBQKBNR",
        )

        book_map = (
            "rnbqkbnr/pppppppp/8/8/8/q7/PPPPPPPP/RNBQKBNR",
            "rnbqkbnr/pppppppp/8/8/8/1q6/PPPPPPPP/RNBQKBNR",
            "rnbqkbnr/pppppppp/8/8/8/2q5/PPPPPPPP/RNBQKBNR",
            "rnbqkbnr/pppppppp/8/8/8/3q4/PPPPPPPP/RNBQKBNR",
            "rnbqkbnr/pppppppp/8/8/8/4q3/PPPPPPPP/RNBQKBNR",
            "rnbqkbnr/pppppppp/8/8/8/5q2/PPPPPPPP/RNBQKBNR",
            "rnbqkbnr/pppppppp/8/8/8/6q1/PPPPPPPP/RNBQKBNR",
            "rnbqkbnr/pppppppp/8/8/8/7q/PPPPPPPP/RNBQKBNR",
            "rnbqkbnr/pppppppp/8/8/q7/8/PPPPPPPP/RNBQKBNR",
            "rnbqkbnr/pppppppp/8/8/1q6/8/PPPPPPPP/RNBQKBNR",
            "rnbqkbnr/pppppppp/8/8/2q5/8/PPPPPPPP/RNBQKBNR",
            "rnbqkbnr/pppppppp/8/8/3q4/8/PPPPPPPP/RNBQKBNR",
            "rnbqkbnr/pppppppp/8/8/4q3/8/PPPPPPPP/RNBQKBNR",
            "rnbqkbnr/pppppppp/8/8/5q2/8/PPPPPPPP/RNBQKBNR",
            "rnbqkbnr/pppppppp/8/8/6q1/8/PPPPPPPP/RNBQKBNR",
            "rnbqkbnr/pppppppp/8/8/7q/8/PPPPPPPP/RNBQKBNR",
        )

        engine_map = (
            "rnbqkbnr/pppppppp/q7/8/8/8/PPPPPPPP/RNBQKBNR",
            "rnbqkbnr/pppppppp/1q6/8/8/8/PPPPPPPP/RNBQKBNR",
            "rnbqkbnr/pppppppp/2q5/8/8/8/PPPPPPPP/RNBQKBNR",
            "rnbqkbnr/pppppppp/3q4/8/8/8/PPPPPPPP/RNBQKBNR",
            "rnbqkbnr/pppppppp/4q3/8/8/8/PPPPPPPP/RNBQKBNR",
            "rnbqkbnr/pppppppp/5q2/8/8/8/PPPPPPPP/RNBQKBNR",
            "rnbqkbnr/pppppppp/6q1/8/8/8/PPPPPPPP/RNBQKBNR",
            "rnbqkbnr/pppppppp/7q/8/8/8/PPPPPPPP/RNBQKBNR",
        )

        shutdown_map = (
            "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQQBNR",
            "RNBQQBNR/PPPPPPPP/8/8/8/8/pppppppp/rnbkqbnr",
            "8/8/8/8/8/8/8/3QQ3",
            "3QQ3/8/8/8/8/8/8/8",
        )

        reboot_map = (
            "rnbqqbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR",
            "RNBKQBNR/PPPPPPPP/8/8/8/8/pppppppp/rnbqqbnr",
            "8/8/8/8/8/8/8/3qq3",
            "3qq3/8/8/8/8/8/8/8",
        )

        mode_map = {
            "rnbqkbnr/pppppppp/8/Q7/8/8/PPPPPPPP/RNBQKBNR": Mode.NORMAL,
            "rnbqkbnr/pppppppp/8/1Q6/8/8/PPPPPPPP/RNBQKBNR": Mode.BRAIN,
            "rnbqkbnr/pppppppp/8/2Q5/8/8/PPPPPPPP/RNBQKBNR": Mode.ANALYSIS,
            "rnbqkbnr/pppppppp/8/3Q4/8/8/PPPPPPPP/RNBQKBNR": Mode.PGNREPLAY,
            "rnbqkbnr/pppppppp/8/4Q3/8/8/PPPPPPPP/RNBQKBNR": Mode.OBSERVE,
            "rnbqkbnr/pppppppp/8/5Q2/8/8/PPPPPPPP/RNBQKBNR": Mode.PONDER,
            "rnbqkbnr/pppppppp/8/6Q1/8/8/PPPPPPPP/RNBQKBNR": Mode.TRAINING,
            "rnbqkbnr/pppppppp/8/7Q/8/8/PPPPPPPP/RNBQKBNR": Mode.REMOTE,
        }

        drawresign_map = {
            "8/8/8/3k4/4K3/8/8/8": GameResult.WIN_WHITE,
            "8/8/8/3K4/4k3/8/8/8": GameResult.WIN_WHITE,
            "8/8/8/4k3/3K4/8/8/8": GameResult.WIN_BLACK,
            "8/8/8/4K3/3k4/8/8/8": GameResult.WIN_BLACK,
            "8/8/8/3kK3/8/8/8/8": GameResult.DRAW,
            "8/8/8/3Kk3/8/8/8/8": GameResult.DRAW,
            "8/8/8/8/3kK3/8/8/8": GameResult.DRAW,
            "8/8/8/8/3Kk3/8/8/8": GameResult.DRAW,
        }

        bit_board = chess.Board(fen + " w - - 0 1")  # try a standard board and check for any starting pos
        if bit_board.chess960_pos(ignore_castling=True):
            logger.debug("flipping the board - W infront")
            self.dgtmenu.set_position_reverse_flipboard(False, self.play_mode)
        bit_board = chess.Board(flip_board_fen(fen) + " w - - 0 1")  # try a reversed board and check for any starting pos
        if bit_board.chess960_pos(ignore_castling=True):
            logger.debug("flipping the board - B infront")
            self.dgtmenu.set_position_reverse_flipboard(True, self.play_mode)

        if self.dgtmenu.get_flip_board() and raw:  # Flip the board if needed
            fen = flip_board_fen(fen)

        logger.debug("DGT-Fen [%s]", fen)
        if fen == self.dgtmenu.get_dgt_fen():
            logger.debug("ignore same fen")
            self.have_seen_a_fen = True
            return
        self.dgtmenu.set_dgt_fen(fen)
        self.drawresign_fen = self._drawresign()
        # Fire the appropriate event
        if fen in level_map:
            eng = self.dgtmenu.get_engine()
            level_dict = eng["level_dict"]
            if level_dict:
                inc = len(level_dict) / 7
                level = min(floor(inc * level_map.index(fen)), len(level_dict) - 1)  # type: int
                self.dgtmenu.set_engine_level(level)
                msg = sorted(level_dict)[level]
                text = self.dgttranslate.text("M10_level", msg)
                text.wait = await self._exit_menu()
                logger.debug("map: New level %s", msg)
                if (
                    not self.dgtmenu.remote_engine
                    and "Remote" not in str(eng)
                    and "Online" not in str(eng)
                    and "FICS" not in str(eng)
                    and "lichess" not in str(eng)
                    and "Lichess" not in str(eng)
                    and "Lichess" not in str(eng)
                    and "PGN" not in str(eng)
                ):
                    write_picochess_ini("engine-level", msg)
                await Observable.fire(Event.LEVEL(options=level_dict[msg], level_text=text, level_name=msg))
            else:
                logger.debug("engine doesnt support levels")
        elif fen in book_map:
            book_index = book_map.index(fen)
            try:
                book = self.dgtmenu.all_books[book_index]
                self.dgtmenu.set_book(book_index)
                logger.debug("map: Opening book [%s]", book["file"])
                text = book["text"]
                text.beep = self.dgttranslate.bl(BeepLevel.MAP)
                text.maxtime = 1
                text.wait = await self._exit_menu()
                await Observable.fire(Event.SET_OPENING_BOOK(book=book, book_text=text, show_ok=False))
            except IndexError:
                pass
        elif fen in engine_map:
            if self.dgtmenu.installed_engines:
                try:
                    self.dgtmenu.set_engine_index(engine_map.index(fen))
                    eng = self.dgtmenu.get_engine()
                    self.dgtmenu.set_state_current_engine(eng["file"])
                    level_dict = eng["level_dict"]
                    logger.debug("map: Engine name [%s]", eng["name"])
                    eng_text = eng["text"]
                    eng_text.beep = self.dgttranslate.bl(BeepLevel.MAP)
                    eng_text.maxtime = 1
                    eng_text.wait = await self._exit_menu()
                    if level_dict:
                        len_level = len(level_dict)
                        if self.dgtmenu.get_engine_level() is None or len_level <= self.dgtmenu.get_engine_level():
                            self.dgtmenu.set_engine_level(len_level - 1)
                        msg = sorted(level_dict)[self.dgtmenu.get_engine_level()]
                        options = level_dict[msg]  # cause of "new-engine", send options lateron - now only {}
                        await Observable.fire(
                            Event.LEVEL(
                                options={},
                                level_text=self.dgttranslate.text("M10_level", msg),
                                level_name=msg,
                            )
                        )
                    else:
                        msg = None
                        options = {}
                    if (
                        not self.dgtmenu.remote_engine
                        and "Remote" not in str(eng)
                        and "Online" not in str(eng)
                        and "FICS" not in str(eng)
                        and "lichess" not in str(eng)
                        and "Lichess" not in str(eng)
                        and "Lichess" not in str(eng)
                        and "PGN" not in str(eng)
                    ):
                        write_picochess_ini("engine-level", msg)
                    await Observable.fire(Event.NEW_ENGINE(eng=eng, eng_text=eng_text, options=options, show_ok=False))
                    self.dgtmenu.set_engine_restart(True)
                except IndexError:
                    pass
            else:
                await DispatchDgt.fire(self.dgttranslate.text("Y10_erroreng"))
        elif fen in mode_map:
            logger.debug("map: Interaction mode [%s]", mode_map[fen])
            if mode_map[fen] == Mode.BRAIN and not self.dgtmenu.get_engine_has_ponder():
                await DispatchDgt.fire(self.dgttranslate.text("Y10_erroreng"))
            else:
                self.dgtmenu.set_mode(mode_map[fen])
                text = self.dgttranslate.text(mode_map[fen].value)
                text.beep = self.dgttranslate.bl(BeepLevel.MAP)
                text.maxtime = 1  # wait 1sec not forever
                text.wait = await self._exit_menu()
                await Observable.fire(Event.SET_INTERACTION_MODE(mode=mode_map[fen], mode_text=text, show_ok=False))

        elif fen in self.dgtmenu.tc_fixed_map:
            logger.debug("map: Time control fixed")
            self.dgtmenu.set_time_mode(TimeMode.FIXED)
            self.dgtmenu.set_time_fixed(list(self.dgtmenu.tc_fixed_map.keys()).index(fen))
            text = self.dgttranslate.text("M10_tc_fixed", self.dgtmenu.tc_fixed_list[self.dgtmenu.get_time_fixed()])
            text.wait = await self._exit_menu()
            timectrl = self.dgtmenu.tc_fixed_map[fen]  # type: TimeControl
            await Observable.fire(
                Event.SET_TIME_CONTROL(tc_init=timectrl.get_parameters(), time_text=text, show_ok=False)
            )
        elif fen in self.dgtmenu.tc_blitz_map:
            logger.debug("map: Time control blitz")
            self.dgtmenu.set_time_mode(TimeMode.BLITZ)
            self.dgtmenu.set_time_blitz(list(self.dgtmenu.tc_blitz_map.keys()).index(fen))
            text = self.dgttranslate.text("M10_tc_blitz", self.dgtmenu.tc_blitz_list[self.dgtmenu.get_time_blitz()])
            text.wait = await self._exit_menu()
            timectrl = self.dgtmenu.tc_blitz_map[fen]  # type: TimeControl
            await Observable.fire(
                Event.SET_TIME_CONTROL(tc_init=timectrl.get_parameters(), time_text=text, show_ok=False)
            )
        elif fen in self.dgtmenu.tc_fisch_map:
            logger.debug("map: Time control fischer")
            self.dgtmenu.set_time_mode(TimeMode.FISCHER)
            self.dgtmenu.set_time_fisch(list(self.dgtmenu.tc_fisch_map.keys()).index(fen))
            text = self.dgttranslate.text("M10_tc_fisch", self.dgtmenu.tc_fisch_list[self.dgtmenu.get_time_fisch()])
            text.wait = await self._exit_menu()
            timectrl = self.dgtmenu.tc_fisch_map[fen]  # type: TimeControl
            await Observable.fire(
                Event.SET_TIME_CONTROL(tc_init=timectrl.get_parameters(), time_text=text, show_ok=False)
            )
        elif fen in shutdown_map:
            logger.debug("map: shutdown")
            if self.have_seen_a_fen:
                await self._power_off()
            else:
                logger.debug("map: shutdown ignored on first fen seen")
                await DisplayMsg.show(Message.WRONG_FEN())
        elif fen in reboot_map:
            logger.debug("map: reboot")
            if self.have_seen_a_fen:
                await self._reboot()
            else:
                logger.debug("map: reboot ignored on first fen seen")
                await DisplayMsg.show(Message.WRONG_FEN())
        elif self.drawresign_fen in drawresign_map:
            if not self._inside_main_menu():
                logger.debug("map: drawresign")
                await Observable.fire(Event.DRAWRESIGN(result=drawresign_map[self.drawresign_fen]))
        else:
            bit_board = chess.Board(fen + " w - - 0 1")
            pos960 = bit_board.chess960_pos(ignore_castling=True)
            if pos960 is not None:
                if pos960 == 518 or self.dgtmenu.get_engine_has_960():
                    if self._setpieces_restore_pending:
                        logger.debug("bypassing start-position new-game map after set pieces restore")
                        self._setpieces_restore_pending = False
                        self._start_position_restore_pending = False
                        await Observable.fire(Event.FEN(fen=fen))
                        self.have_seen_a_fen = True
                        return
                    if self._start_position_restore_pending:
                        logger.debug("bypassing start-position new-game map after quick restore")
                        self._start_position_restore_pending = False
                        await Observable.fire(Event.FEN(fen=fen))
                        self.have_seen_a_fen = True
                        return
                    if self._current_game_has_moves and self._current_game_start_pos960 == pos960:
                        logger.debug("routing start-position board scan through Event.FEN for takeback handling")
                        self.last_pos_start = True
                        self._start_position_restore_pending = False
                        await Observable.fire(Event.FEN(fen=fen))
                        self.have_seen_a_fen = True
                        return
                    if self.last_pos_start:
                        # trigger window switch
                        if ModeInfo.get_emulation_mode() and self.dgtmenu.get_engine_rdisplay():
                            cmd = get_window_command("switch_window")
                            if cmd:
                                process = await asyncio.create_subprocess_shell(
                                    cmd,
                                    stdout=asyncio.subprocess.PIPE,
                                    stderr=asyncio.subprocess.PIPE,
                                )
                                stdout, stderr = await process.communicate()
                                if process.returncode != 0:
                                    logger.error("Command failed with error: %s", stderr.decode())
                    else:
                        self.last_pos_start = True
                    self._start_position_restore_pending = False
                    logger.debug("map: New game")
                    await Observable.fire(Event.NEW_GAME(pos960=pos960))
                else:
                    # self._reset_moves_and_score()
                    await DispatchDgt.fire(self.dgttranslate.text("Y10_error960"))
            else:
                self._setpieces_restore_pending = False
                self._start_position_restore_pending = self.last_pos_start
                await Observable.fire(Event.FEN(fen=fen))
        self.have_seen_a_fen = True  # remember that we have seen a fen for issue #76

    async def _process_engine_ready(self, message):
        for index in range(0, len(self.dgtmenu.installed_engines)):
            if self.dgtmenu.installed_engines[index]["file"] == message.eng["file"]:
                self.dgtmenu.set_engine_index(index)
        self.dgtmenu.set_engine_has_960(message.has_960)
        self.dgtmenu.set_engine_has_ponder(message.has_ponder)
        if not self.dgtmenu.get_confirm() or not message.show_ok:
            await DispatchDgt.fire(message.eng_text)
        self.dgtmenu.set_engine_restart(False)

    def _process_engine_startup(self, message):
        self.dgtmenu.installed_engines = message.installed_engines
        was_in_menu = self.dgtmenu.inside_main_menu()
        for index in range(0, len(self.dgtmenu.installed_engines)):
            eng = self.dgtmenu.installed_engines[index]
            if eng["file"] == message.file:
                self.dgtmenu.set_state_current_engine(message.file)
                self.dgtmenu.set_engine_index(index)
                self.dgtmenu.set_engine_has_960(message.has_960)
                self.dgtmenu.set_engine_has_ponder(message.has_ponder)
                self.dgtmenu.set_engine_level(message.level_index)
        if not was_in_menu:
            # avoid leaving the menu positioned inside the engine submenu when startup messages arrive
            self.dgtmenu.enter_top_menu()
            self.dgtmenu.menu_top = Top.ENGINE

    async def force_leds_off(self, log=False):
        """Clear the rev2 lights if they still on."""
        if self.leds_are_on:
            if log:
                logger.warning("(rev) leds still on")
        self.leds_are_on = False
        await DispatchDgt.fire(Dgt.LIGHT_CLEAR(devs={"ser", "web"}))

    async def _process_start_new_game(self, message):
        self.c_time_counter = 0
        self.c_last_player = ""
        await self.force_leds_off()
        self._reset_moves_and_score()
        self._start_position_restore_pending = False
        self._current_game_has_moves = bool(message.game.move_stack)
        # Always reset variant context for the new game.
        # If variant is not attached to the message, treat it as normal chess.
        msg_variant = getattr(message, "variant", "chess")
        self._current_variant = msg_variant
        logger.debug("_process_start_new_game: variant set to %s", msg_variant)
        self.time_control.reset()

        if message.newgame:
            self.last_pos_start = True
            pos960 = message.game.chess960_pos(ignore_castling=True)
            self._current_game_start_pos960 = pos960
            self.uci960 = pos960 is not None and pos960 != 518
            await DispatchDgt.fire(self.dgttranslate.text("C10_ucigame" if self.uci960 else "C10_newgame", str(pos960)))
        else:
            self._current_game_start_pos960 = message.game.chess960_pos(ignore_castling=True)
            self.last_pos_start = True
        if self.dgtmenu.get_mode() in (
            Mode.NORMAL,
            Mode.BRAIN,
            Mode.OBSERVE,
            Mode.REMOTE,
            Mode.TRAINING,
        ):
            await self._set_clock()

    def _variant_fen_from_game(self, game: chess.Board) -> tuple[str, str]:
        """Determine variant name and return correct FEN for variant boards.

        For atomic chess, the standard chess.Board does not track explosions,
        so we replay all moves on an AtomicBoard to get the correct FEN.
        The variant is detected from (in order):
        1. game._variant_name attribute (set by picochess.game_copy())
        2. self._current_variant (instance state, set via Message attributes)
        Returns (variant_name, fen).
        """
        game_variant = getattr(game, '_variant_name', None)
        variant_name = game_variant or self._current_variant
        # Keep _current_variant in sync when game carries variant info
        if game_variant and game_variant != self._current_variant:
            self._current_variant = game_variant
            logger.debug("_variant_fen_from_game: updated _current_variant to %s", game_variant)
        class_name = game.__class__.__name__

        # If the board object is already a variant board, use it directly
        if class_name == "AtomicBoard":
            return "atomic", game.fen()
        elif class_name == "KingOfTheHillBoard":
            return "kingofthehill", game.fen()
        elif class_name == "ThreeCheckBoard":
            return "3check", game.fen()
        elif class_name == "RacingKingsBoard":
            return "racingkings", game.fen()
        elif class_name == "AntichessBoard":
            return "antichess", game.fen()

        # For atomic variant with a standard chess.Board, replay on AtomicBoard
        if variant_name == "atomic" and game.move_stack:
            try:
                atm = chess.variant.AtomicBoard()
                for move in game.move_stack:
                    atm.push(move)
                return variant_name, atm.fen()
            except Exception as exc:
                logger.warning("_variant_fen_from_game: atomic replay failed: %s", exc)

        # For 3check variant with a standard chess.Board, replay on ThreeCheckBoard
        # to include the check-count suffix (e.g. +3+2) in the FEN.
        if variant_name == "3check" and game.move_stack:
            try:
                tcb = chess.variant.ThreeCheckBoard()
                for move in game.move_stack:
                    tcb.push(move)
                return variant_name, tcb.fen()
            except Exception as exc:
                logger.warning("_variant_fen_from_game: 3check replay failed: %s", exc)

        # For racingkings variant with a standard chess.Board, replay on RacingKingsBoard
        if variant_name == "racingkings" and game.move_stack:
            try:
                rkb = chess.variant.RacingKingsBoard()
                for move in game.move_stack:
                    rkb.push(move)
                return variant_name, rkb.fen()
            except Exception as exc:
                logger.warning("_variant_fen_from_game: racingkings replay failed: %s", exc)

        # For antichess variant with a standard chess.Board, replay on AntichessBoard
        if variant_name == "antichess" and game.move_stack:
            try:
                ach = chess.variant.AntichessBoard()
                for move in game.move_stack:
                    ach.push(move)
                return variant_name, ach.fen()
            except Exception as exc:
                logger.warning("_variant_fen_from_game: antichess replay failed: %s", exc)

        return variant_name or "chess", game.fen()

    async def _process_computer_move(self, message):
        if not message.is_user_move:
            self.last_pos_start = False  # issue 54, see below
            self._start_position_restore_pending = False
            await self.force_leds_off(log=True)  # can happen in case of a book move
        move = message.move
        ponder = message.ponder

        # Get variant-aware FEN for the current position
        variant_name, game_fen = self._variant_fen_from_game(message.game)

        if not message.is_user_move:
            # @todo issue 54 misuse this as USER_MOVE until we have such a message
            # do not update state variables
            self.play_move = move
            self.play_fen = game_fen
            self.play_turn = message.game.turn
        if ponder:
            game_copy = message.game.copy()
            # Preserve _variant_name which chess.Board.copy() does not copy
            vn = getattr(message.game, '_variant_name', None)
            if vn:
                game_copy._variant_name = vn
            game_copy.push(move)
            _, hint_fen = self._variant_fen_from_game(game_copy)
            self.hint_move = ponder
            self.hint_fen = hint_fen
            self.hint_turn = game_copy.turn
        else:
            self.hint_move = chess.Move.null()
            self.hint_fen = None
            self.hint_turn = None
        # Display the move
        side = self._get_clock_side(message.game.turn)
        beep = self.dgttranslate.bl(BeepLevel.CONFIG)

        disp = Dgt.DISPLAY_MOVE(
            move=move,
            fen=game_fen,
            side=side,
            wait=message.wait,
            maxtime=0,
            beep=beep,
            devs={"ser", "i2c", "web"},
            uci960=self.uci960,
            lang=self.dgttranslate.language,
            capital=self.dgttranslate.capital,
            long=self.dgttranslate.notation,
        )
        disp.variant = variant_name  # Attach variant info for iface.py
        await DispatchDgt.fire(disp)

        await DispatchDgt.fire(Dgt.LIGHT_SQUARES(uci_move=move.uci(), devs={"ser", "web"}))
        self.leds_are_on = True
        self.c_time_counter = 0
        self.c_last_player = "C"

    async def _set_clock(self, side=ClockSide.NONE, devs=None):
        if devs is None:  # prevent W0102 error
            devs = {"ser", "i2c", "web"}
        time_left, time_right = self.time_control.get_internal_time(flip_board=self.dgtmenu.get_flip_board())
        await DispatchDgt.fire(Dgt.CLOCK_SET(time_left=time_left, time_right=time_right, devs=devs))
        await DispatchDgt.fire(Dgt.CLOCK_START(side=side, wait=True, devs=devs))

    async def _display_confirm(self, text_key):
        if not self.low_time and not self.dgtmenu.get_confirm():  # only display if the user has >60sec on his clock
            await DispatchDgt.fire(self.dgttranslate.text(text_key))

    async def _process_computer_move_done(self):
        self._current_game_has_moves = True
        self.c_last_player = "C"
        self.c_time_counter = 0
        await self.force_leds_off()
        self.last_move = self.play_move
        self.last_fen = self.play_fen
        self.last_turn = self.play_turn
        self.play_move = chess.Move.null()
        self.play_fen = None
        self.play_turn = None
        await self._exit_menu()

        if self.dgtmenu.get_time_mode() == TimeMode.FIXED:  # go back to a stopped time display and reset times
            self.time_control.reset()
            await self._set_clock()

        if self.dgtmenu.get_mode() == Mode.TRAINING:
            await self._display_confirm("K05_okmove")
            text = self._combine_depth_and_score()
            text.wait = True
            await DispatchDgt.fire(text)
        else:
            await self._display_confirm("K05_okpico")

    async def _process_user_move_done(self, message):
        self._current_game_has_moves = bool(message.game.move_stack)
        self.last_pos_start = False
        self._start_position_restore_pending = False
        await self.force_leds_off(log=True)  # can happen in case of a sliding move

        if self.c_last_player == "C" or self.c_last_player == "":
            self.c_last_player = "U"
        else:
            self.c_last_player = "U"

        self.c_time_counter = 0

        self.last_move = message.move
        self.last_fen = message.fen
        self.last_turn = message.turn
        self.play_move = chess.Move.null()
        self.play_fen = None
        self.play_turn = None
        await self._exit_menu()

        if self.dgtmenu.get_mode() == Mode.TRAINING:
            await self._display_confirm("K05_okmove")
            text = self._combine_depth_and_score()
            text.wait = True
            await DispatchDgt.fire(text)
        else:
            await self._display_confirm("K05_okuser")

    async def _process_review_move_done(self, message):
        self._current_game_has_moves = bool(message.game.move_stack)
        await self.force_leds_off(log=True)  # can happen in case of a sliding move
        self.last_move = message.move
        self.last_fen = message.fen
        self.last_turn = message.turn
        await self._exit_menu()
        await self._display_confirm("K05_okmove")
        self.c_last_player = ""
        self.c_time_counter = 0

    async def _process_time_control(self, message):
        wait = not self.dgtmenu.get_confirm() or not message.show_ok
        if wait:
            await DispatchDgt.fire(message.time_text)
        self.time_control = TimeControl(**message.tc_init)
        await self._set_clock()

    async def _process_new_score(self, message):
        if not message.mate:
            score = int(message.score)
            text = self.dgttranslate.text("N10_score", score)
            self.score = text
        else:
            text = self.dgttranslate.text("N10_mate", str(message.mate))
            self.score = text
        if message.mode in (Mode.PGNREPLAY, Mode.KIBITZ, Mode.TRAINING) and not self._inside_main_menu():
            text = self._combine_depth_and_score()
            text.wait = True
            text.analysis_update = True
            await DispatchDgt.fire(text)

    async def _process_new_pv(self, message):
        self.hint_move = message.pv[0]
        pv_variant, pv_fen = self._variant_fen_from_game(message.game)
        self.hint_fen = pv_fen
        self.hint_turn = message.game.turn
        if message.mode == Mode.ANALYSIS and not self._inside_main_menu():
            side = self._get_clock_side(self.hint_turn)
            beep = self.dgttranslate.bl(BeepLevel.NO)
            disp = Dgt.DISPLAY_MOVE(
                move=self.hint_move,
                fen=self.hint_fen,
                side=side,
                wait=True,
                maxtime=0,
                beep=beep,
                devs={"ser", "i2c", "web"},
                uci960=self.uci960,
                lang=self.dgttranslate.language,
                capital=self.dgttranslate.capital,
                long=self.dgttranslate.notation,
            )
            disp.variant = pv_variant  # Attach variant info for iface.py
            disp.analysis_update = True
            await DispatchDgt.fire(disp)

    async def _process_startup_info(self, message):
        self.play_mode = message.info["play_mode"]
        self.dgtmenu.set_mode(message.info["interaction_mode"])
        self.dgtmenu.set_book(message.info["book_index"])
        self.dgtmenu.all_books = message.info["books"]
        tc_init = message.info["tc_init"]
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
                self.dgtmenu.tc_fixed_map.update({("", timectrl)})
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
                self.dgtmenu.tc_blitz_map.update({("", timectrl)})
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
                self.dgtmenu.tc_fisch_map.update({("", timectrl)})
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
            logger.debug("molli: startup info Timemode Depth")
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
            logger.debug("molli: startup info Timemode Node")
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

    async def _process_clock_start(self, message):
        self.time_control = TimeControl(**message.tc_init)
        side = ClockSide.LEFT if (message.turn == chess.WHITE) != self.dgtmenu.get_flip_board() else ClockSide.RIGHT
        await self._set_clock(side=side, devs=message.devs)

    async def _process_once_per_second(self):
        """called by AsyncRepeatingTimer"""
        # logger.debug("process_once_per_second running")
        # molli: rolling display
        if not self._inside_main_menu():
            if self.dgtmenu.get_mode() == Mode.PONDER:
                if not Rev2Info.get_web_only():
                    if self.show_move_or_value >= self.dgtmenu.get_ponderinterval():
                        if self.hint_move:
                            side = self._get_clock_side(self.hint_turn)
                            beep = self.dgttranslate.bl(BeepLevel.NO)
                            text = Dgt.DISPLAY_MOVE(
                                move=self.hint_move,
                                fen=self.hint_fen,
                                side=side,
                                wait=True,
                                maxtime=1,
                                beep=beep,
                                devs={"ser", "i2c", "web"},
                                uci960=self.uci960,
                                lang=self.dgttranslate.language,
                                capital=self.dgttranslate.capital,
                                long=self.dgttranslate.notation,
                            )
                        else:
                            text = self.dgttranslate.text("N10_nomove")
                    else:
                        text = self._combine_depth_and_score()
                    text.wait = True
                    await DispatchDgt.fire(text)
                    self.show_move_or_value = (self.show_move_or_value + 1) % (self.dgtmenu.get_ponderinterval() * 2)
                else:
                    text = self._combine_depth_and_score_and_hint()
                    text.wait = True
                    await DispatchDgt.fire(text)
            elif (self.dgtmenu.get_mode() == Mode.BRAIN and self.dgtmenu.get_rolldispbrain()) or (
                self.dgtmenu.get_mode() == Mode.NORMAL and self.dgtmenu.get_rolldispnorm()
            ):
                # molli: allow rolling information display (time/score/hint_move) in BRAIN mode according to
                #      ponder interval
                if self.play_move == chess.Move.null():
                    if self.c_time_counter > 2 * self.dgtmenu.get_ponderinterval():
                        text = self._combine_depth_and_score()
                        text.wait = True
                        await DispatchDgt.fire(text)
                        self.c_time_counter = (self.c_time_counter + 1) % (self.dgtmenu.get_ponderinterval() * 3)
                    elif self.c_time_counter > self.dgtmenu.get_ponderinterval():
                        if self.hint_move:
                            side = self._get_clock_side(self.hint_turn)
                            beep = self.dgttranslate.bl(BeepLevel.NO)
                            text = Dgt.DISPLAY_MOVE(
                                move=self.hint_move,
                                fen=self.hint_fen,
                                side=side,
                                wait=True,
                                maxtime=1,
                                beep=beep,
                                devs={"ser", "i2c", "web"},
                                uci960=self.uci960,
                                lang=self.dgttranslate.language,
                                capital=self.dgttranslate.capital,
                                long=self.dgttranslate.notation,
                            )
                        else:
                            text = self.dgttranslate.text("N10_nomove")
                        text.wait = True
                        self.c_time_counter = (self.c_time_counter + 1) % (self.dgtmenu.get_ponderinterval() * 3)
                        await DispatchDgt.fire(text)
                        if self.c_time_counter == 2 * self.dgtmenu.get_ponderinterval():
                            await asyncio.sleep(0.3)
                    else:
                        if self.c_time_counter == 0:
                            await asyncio.sleep(0.3)
                        self.c_time_counter = (self.c_time_counter + 1) % (self.dgtmenu.get_ponderinterval() * 3)
                        await self._exit_display()
                        if self.c_time_counter == self.dgtmenu.get_ponderinterval():
                            await asyncio.sleep(0.3)

    def _drawresign(self):
        _, _, _, rnk_5, rnk_4, _, _, _ = self.dgtmenu.get_dgt_fen().split("/")
        return "8/8/8/" + rnk_5 + "/" + rnk_4 + "/8/8/8"

    async def _exit_display(self, devs=None):
        if devs is None:  # prevent W0102 error
            devs = {"ser", "i2c", "web"}
        if self.play_move and self.dgtmenu.get_mode() in (
            Mode.NORMAL,
            Mode.BRAIN,
            Mode.REMOTE,
            Mode.TRAINING,
        ):
            side = self._get_clock_side(self.play_turn)
            beep = self.dgttranslate.bl(BeepLevel.BUTTON)
            text = Dgt.DISPLAY_MOVE(
                move=self.play_move,
                fen=self.play_fen,
                side=side,
                wait=True,
                maxtime=1,
                beep=beep,
                devs=devs,
                uci960=self.uci960,
                lang=self.dgttranslate.language,
                capital=self.dgttranslate.capital,
                long=self.dgttranslate.notation,
            )
            await DispatchDgt.fire(Dgt.LIGHT_SQUARES(uci_move=self.play_move.uci(), devs={"ser", "web"}))
        else:
            text = None
            if self._inside_main_menu():
                text = self.dgtmenu.get_current_text()
            if text:
                text.wait = True  # in case of "bad pos" message send before
            else:
                mode = self.dgtmenu.get_mode()
                if mode == Mode.ANALYSIS and self.hint_move and self.hint_move != chess.Move.null() and self.hint_fen:
                    side = self._get_clock_side(self.hint_turn)
                    beep = self.dgttranslate.bl(BeepLevel.NO)
                    text = Dgt.DISPLAY_MOVE(
                        move=self.hint_move,
                        fen=self.hint_fen,
                        side=side,
                        wait=True,
                        maxtime=0,
                        beep=beep,
                        devs=devs,
                        uci960=self.uci960,
                        lang=self.dgttranslate.language,
                        capital=self.dgttranslate.capital,
                        long=self.dgttranslate.notation,
                    )
                elif mode in (Mode.TRAINING, Mode.KIBITZ, Mode.PGNREPLAY):
                    text = self._combine_depth_and_score()
                    text.wait = True
                else:
                    text = Dgt.DISPLAY_TIME(force=True, wait=True, devs=devs)

        await DispatchDgt.fire(text)

    async def _process_message(self, message):
        """message task consumer"""
        # switch-case
        if isinstance(message, Message.ENGINE_READY):
            await self._process_engine_ready(message)

        elif isinstance(message, Message.ENGINE_STARTUP):
            self._process_engine_startup(message)

        elif isinstance(message, Message.ENGINE_FAIL):
            await DispatchDgt.fire(self.dgttranslate.text("Y10_erroreng"))
            self.dgtmenu.set_engine_restart(False)

        elif isinstance(message, Message.REMOTE_FAIL):
            await DispatchDgt.fire(self.dgttranslate.text("Y10_erroreng"))

        elif isinstance(message, Message.COMPUTER_MOVE):
            await self._process_computer_move(message)

        elif isinstance(message, Message.START_NEW_GAME):
            await self._process_start_new_game(message)

        elif isinstance(message, Message.COMPUTER_MOVE_DONE):
            await self._process_computer_move_done()

        elif isinstance(message, Message.USER_MOVE_DONE):
            await self._process_user_move_done(message)

        elif isinstance(message, Message.REVIEW_MOVE_DONE):
            await self._process_review_move_done(message)

        elif isinstance(message, Message.ALTERNATIVE_MOVE):
            await self.force_leds_off()
            self.play_mode = message.play_mode
            self.play_move = chess.Move.null()
            await DispatchDgt.fire(self.dgttranslate.text("B05_altmove"))

        elif isinstance(message, Message.LEVEL):
            if not self.dgtmenu.get_engine_restart():
                await DispatchDgt.fire(message.level_text)

        elif isinstance(message, Message.TIME_CONTROL):
            await self._process_time_control(message)

        elif isinstance(message, Message.OPENING_BOOK):
            if self.play_move == chess.Move.null():
                # issue #45 - skip if user has not made computer move on eboard
                if not self.dgtmenu.get_confirm() or not message.show_ok:
                    await DispatchDgt.fire(message.book_text)

        elif isinstance(message, Message.TAKE_BACK):
            self._current_game_has_moves = bool(message.game.move_stack)
            self.take_back_move: chess.Move = chess.Move.null()
            game_copy: chess.Board = message.game.copy()
            # Preserve _variant_name which chess.Board.copy() does not copy
            vn = getattr(message.game, '_variant_name', None)
            if vn:
                game_copy._variant_name = vn

            await self.force_leds_off()
            self._reset_moves_and_score()
            await DispatchDgt.fire(self.dgttranslate.text("C10_takeback"))

            try:
                self.take_back_move = game_copy.pop()
            except IndexError:
                self.take_back_move = chess.Move.null()

            if self.take_back_move != chess.Move.null():
                #  and not ModeInfo.get_pgn_mode()
                side = self._get_clock_side(game_copy.turn)
                beep = self.dgttranslate.bl(BeepLevel.NO)
                _, tb_fen = self._variant_fen_from_game(game_copy)
                text = Dgt.DISPLAY_MOVE(
                    move=self.take_back_move,
                    fen=tb_fen,
                    side=side,
                    wait=True,
                    maxtime=1,
                    beep=beep,
                    devs={"ser", "i2c", "web"},
                    uci960=self.uci960,
                    lang=self.dgttranslate.language,
                    capital=self.dgttranslate.capital,
                    long=True,
                )  # molli: for take back display use long notation
                if vn:
                    text.variant = vn
                text.wait = True
                await DispatchDgt.fire(text)
                await self.force_leds_off()
                await DispatchDgt.fire(Dgt.LIGHT_SQUARES(uci_move=self.take_back_move.uci(), devs={"ser", "web"}))
                self.leds_are_on = True
            else:
                await DispatchDgt.fire(Dgt.DISPLAY_TIME(force=True, wait=True, devs={"ser", "i2c", "web"}))

            self.c_time_counter = 0
            self.c_last_player = ""

        elif isinstance(message, Message.GAME_ENDS):
            logger.debug("game_ends outside if: result %s", message.result)
            if not self.dgtmenu.get_engine_restart():  # filter out the shutdown/reboot process
                logger.debug("inside if: result.value %s", message.result.value)
                if message.result == GameResult.DRAW:
                    ModeInfo.set_game_ending(result="1/2-1/2")
                elif message.result == GameResult.WIN_WHITE:
                    ModeInfo.set_game_ending(result="1-0")
                elif message.result == GameResult.WIN_BLACK:
                    ModeInfo.set_game_ending(result="0-1")
                elif message.result == GameResult.THREE_CHECK_WHITE:
                    ModeInfo.set_game_ending(result="1-0")
                elif message.result == GameResult.THREE_CHECK_BLACK:
                    ModeInfo.set_game_ending(result="0-1")
                elif message.result == GameResult.ATOMIC_WHITE:
                    ModeInfo.set_game_ending(result="1-0")
                elif message.result == GameResult.ATOMIC_BLACK:
                    ModeInfo.set_game_ending(result="0-1")
                elif message.result == GameResult.KOTH_WHITE:
                    ModeInfo.set_game_ending(result="1-0")
                elif message.result == GameResult.KOTH_BLACK:
                    ModeInfo.set_game_ending(result="0-1")
                elif message.result == GameResult.RK_WHITE:
                    ModeInfo.set_game_ending(result="1-0")
                elif message.result == GameResult.RK_BLACK:
                    ModeInfo.set_game_ending(result="0-1")
                elif message.result == GameResult.ANTICHESS_WHITE:
                    ModeInfo.set_game_ending(result="1-0")
                elif message.result == GameResult.ANTICHESS_BLACK:
                    ModeInfo.set_game_ending(result="0-1")
                elif message.result == GameResult.OUT_OF_TIME or message.result == GameResult.MATE:
                    # last moved has won
                    if message.game.turn == chess.WHITE:
                        ModeInfo.set_game_ending(result="0-1")
                    else:
                        ModeInfo.set_game_ending(result="1-0")

                text = self.dgttranslate.text(message.result.value)
                text.beep = self.dgttranslate.bl(BeepLevel.CONFIG)
                text.maxtime = 1
                await DispatchDgt.fire(text)
                await asyncio.sleep(1)
                if self.dgtmenu.get_mode() in (Mode.PONDER, Mode.TRAINING):
                    self._reset_moves_and_score()
                    text.beep = False
                    text.maxtime = 1
                    self.score = text

            self.c_last_player = ""
            self.c_time_counter = 0

        elif isinstance(message, Message.INTERACTION_MODE):
            if not self.dgtmenu.get_confirm() or not message.show_ok:
                await DispatchDgt.fire(message.mode_text)

        elif isinstance(message, Message.PLAY_MODE):
            await self.force_leds_off()  # molli: in case of flashing take back move
            self.play_mode = message.play_mode
            await DispatchDgt.fire(message.play_mode_text)

        elif isinstance(message, Message.NEW_SCORE):
            await self._process_new_score(message)

        elif isinstance(message, Message.BOOK_MOVE):
            self.score = self.dgttranslate.text("N10_score", None)
            await DispatchDgt.fire(self.dgttranslate.text("N10_bookmove"))

        elif isinstance(message, Message.NEW_PV):
            await self._process_new_pv(message)

        elif isinstance(message, Message.NEW_DEPTH):
            self.depth = message.depth

        elif isinstance(message, Message.IP_INFO):
            self.dgtmenu.int_ip = message.info["int_ip"]
            self.dgtmenu.ext_ip = message.info["ext_ip"]

        elif isinstance(message, Message.STARTUP_INFO):
            await self.force_leds_off()
            await self._process_startup_info(message)

        elif isinstance(message, Message.SEARCH_STARTED):
            logger.debug("search started")

        elif isinstance(message, Message.SEARCH_STOPPED):
            logger.debug("search stopped")

        elif isinstance(message, Message.CLOCK_START):
            await self._process_clock_start(message)

        elif isinstance(message, Message.CLOCK_STOP):
            await DispatchDgt.fire(Dgt.CLOCK_STOP(devs=message.devs, wait=True))

        elif isinstance(message, Message.DGT_BUTTON):
            await self._process_button(message)

        elif isinstance(message, Message.DGT_FEN):
            if self.dgtmenu.inside_updt_menu():
                logger.debug("inside update menu => ignore fen %s", message.fen)
            else:
                await self._process_fen(message.fen, message.raw)

        elif isinstance(message, Message.DGT_CLOCK_VERSION):
            await DispatchDgt.fire(Dgt.CLOCK_VERSION(main=message.main, sub=message.sub, devs={message.dev}))
            text = self.dgttranslate.text("Y21_picochess", devs={message.dev})
            text.rd = ClockIcons.DOT
            await DispatchDgt.fire(text)

            if message.dev == "ser":  # send the "board connected message" to serial clock
                await DispatchDgt.fire(message.text)
            await self._set_clock(devs={message.dev})
            await self._exit_display(devs={message.dev})

        elif isinstance(message, Message.DGT_CLOCK_TIME):
            time_white = message.time_left
            time_black = message.time_right
            if self.dgtmenu.get_flip_board():
                time_white, time_black = time_black, time_white
            await Observable.fire(
                Event.CLOCK_TIME(
                    time_white=time_white,
                    time_black=time_black,
                    connect=message.connect,
                    dev=message.dev,
                )
            )

        elif isinstance(message, Message.CLOCK_TIME):
            self.low_time = message.low_time
            if self.low_time:
                logger.debug(
                    "time too low, disable confirm - w: %i, b: %i",
                    message.time_white,
                    message.time_black,
                )

        elif isinstance(message, Message.DGT_SERIAL_NR):
            pass

        elif isinstance(message, Message.DGT_JACK_CONNECTED_ERROR):  # only working in case of 2 clocks connected!
            await DispatchDgt.fire(self.dgttranslate.text("Y00_errorjack"))

        elif isinstance(message, Message.DGT_EBOARD_VERSION):
            if self.dgtmenu.inside_updt_menu():
                logger.debug("inside update menu => board channel not displayed")
            else:
                await DispatchDgt.fire(message.text)
                await self._exit_display(devs={"i2c", "web"})  # ser is done, when clock found

        elif isinstance(message, Message.DGT_NO_EBOARD_ERROR):
            if (
                self.dgtmenu.inside_updt_menu()
                or self.dgtmenu.inside_main_menu()
                or self.dgtmenu.is_no_eboard_spinner_suppressed()
            ):
                pass  # avoid filling logbook with DGT search
                # logger.debug("inside menu => board error not displayed")
            else:
                await DispatchDgt.fire(message.text)

        elif isinstance(message, Message.DGT_NO_CLOCK_ERROR):
            pass

        elif isinstance(message, Message.SWITCH_SIDES):
            self.c_time_counter = 0

            # this code had double == in assignments in Pico 2.0
            # so for 6 years this code maybe had no meaning
            # playmode message probably set it correct anyway
            # now in 4.0.6 it actually switches side in this code
            if self.play_mode == PlayMode.USER_WHITE:
                self.play_mode = PlayMode.USER_BLACK
            else:
                self.play_mode = PlayMode.USER_WHITE

            self.play_move = chess.Move.null()
            self.play_fen = None
            self.play_turn = None

            self.hint_move = chess.Move.null()
            self.hint_fen = None
            self.hint_turn = None
            await self.force_leds_off()
            logger.debug("user ignored move %s", message.move)

        elif isinstance(message, Message.EXIT_MENU):
            await self._exit_display()

        elif isinstance(message, Message.WRONG_FEN):
            self._setpieces_restore_pending = True
            await DispatchDgt.fire(self.dgttranslate.text("C10_setpieces"))
            await asyncio.sleep(1)

        elif isinstance(message, Message.UPDATE_PICO):
            await DispatchDgt.fire(self.dgttranslate.text("Y00_update"))

        elif isinstance(message, Message.BATTERY):
            if message.percent == 0x7F:
                percent = " NA"
            elif message.percent > 99:
                percent = " 99"
            else:
                percent = str(message.percent)
            self.dgtmenu.battery = percent

        elif isinstance(message, Message.REMOTE_ROOM):
            self.dgtmenu.inside_room = message.inside

        elif isinstance(message, Message.RESTORE_GAME):
            await DispatchDgt.fire(self.dgttranslate.text("C10_restoregame"))

        elif isinstance(message, Message.ENGINE_NAME):
            await DispatchDgt.fire(self.dgttranslate.text("K20_enginename", message.engine_name))
            await asyncio.sleep(1.5)

        elif isinstance(message, Message.SHOW_TEXT):
            if self.play_move == chess.Move.null():
                # issue #45 - skip if user has not made computer move on eboard
                string_part = ""
                if "K20_" in str(message.text_string):
                    await DispatchDgt.fire(self.dgttranslate.text(message.text_string))
                elif message.text_string == "NO_ARTWORK":
                    await DispatchDgt.fire(self.dgttranslate.text("K20_no_artwork"))
                    await asyncio.sleep(2)
                elif message.text_string == "NEW_POSITION":
                    await DispatchDgt.fire(self.dgttranslate.text("K20_newposition"))
                    await asyncio.sleep(1.5)
                elif message.text_string == "NEW_POSITION_SCAN":
                    await asyncio.sleep(0.5)
                else:
                    for string_part in self._convert_pico_string(message.text_string):
                        await DispatchDgt.fire(self.dgttranslate.text("K20_default", string_part))
                        await asyncio.sleep(1.5)

        elif isinstance(message, Message.SEEKING):
            await DispatchDgt.fire(self.dgttranslate.text("C10_seeking"))

        elif isinstance(message, Message.ENGINE_SETUP):
            await DispatchDgt.fire(self.dgttranslate.text("C20_enginesetup"))

        elif isinstance(message, Message.MOVE_RETRY):
            await DispatchDgt.fire(self.dgttranslate.text("C10_moveretry"))

        elif isinstance(message, Message.MOVE_WRONG):
            await DispatchDgt.fire(self.dgttranslate.text("C10_movewrong"))

        elif isinstance(message, Message.SET_PLAYMODE):
            await self.force_leds_off()  # molli: in case of flashing take back move
            self.play_mode = message.play_mode

        elif isinstance(message, Message.ONLINE_NAMES):
            logger.debug("molli: user online name %s", message.own_user)
            logger.debug("molli: opponent online name %s", message.opp_user)
            await DispatchDgt.fire(self.dgttranslate.text("C10_onlineuser", message.opp_user))

        elif isinstance(message, Message.ONLINE_LOGIN):
            await DispatchDgt.fire(self.dgttranslate.text("C10_login"))

        elif isinstance(message, Message.ONLINE_FAILED):
            await DispatchDgt.fire(self.dgttranslate.text("C10_serverfailed"))

        elif isinstance(message, Message.ONLINE_USER_FAILED):
            await DispatchDgt.fire(self.dgttranslate.text("C10_userfailed"))

        elif isinstance(message, Message.ONLINE_NO_OPPONENT):
            await DispatchDgt.fire(self.dgttranslate.text("C10_noopponent"))

        elif isinstance(message, Message.LOST_ON_TIME):
            await DispatchDgt.fire(self.dgttranslate.text("C10_gameresult_time"))

        elif isinstance(message, Message.SET_NOBOOK):
            self.dgtmenu.set_book(message.book_index)  # molli for emulation, online & pgn modes

        elif isinstance(message, Message.PICOTUTOR_MSG):
            if self.play_move == chess.Move.null():
                # issue #45 - we do not want eval display while user needs to perform computer move
                await DispatchDgt.fire(self.dgttranslate.text("C10_picotutor_msg", message.eval_str))
            if message.eval_str == "POSOK" or message.eval_str == "ANALYSIS" and self.play_move == chess.Move.null():
                # molli: sometime if you move the pieces too quickly a LED may still flash on the rev2
                await self.force_leds_off()

        elif isinstance(message, Message.POSITION_FAIL):
            await self.force_leds_off()
            await DispatchDgt.fire(self.dgttranslate.text("C10_position_fail", message.fen_result))
            await DispatchDgt.fire(Dgt.LIGHT_SQUARE(square=message.fen_result[-2:], devs={"ser", "web"}))
            self.leds_are_on = True
            await asyncio.sleep(3)

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
            await DispatchDgt.fire(self.dgttranslate.text("C10_game_read_menu"))

        elif isinstance(message, Message.TIMECONTROL_CHECK):
            msg_str = "TC"
            await DispatchDgt.fire(self.dgttranslate.text("C10_timecontrol_check", msg_str))
            await asyncio.sleep(2.5)
            msg_str = "M" + str(message.movestogo) + "mv/" + str(message.time1)
            await DispatchDgt.fire(self.dgttranslate.text("C10_timecontrol_check", msg_str))
            await asyncio.sleep(3.5)
            msg_str = "A" + str(message.time2) + "min"
            await DispatchDgt.fire(self.dgttranslate.text("C10_timecontrol_check", msg_str))
            await asyncio.sleep(3.5)

        elif isinstance(message, Message.PGN_GAME_END):
            await DispatchDgt.fire(self.dgttranslate.text("C10_pgngame_end", message.result))

            if "1-0" in message.result:
                text = self.dgttranslate.text("C10_gameresult_white")
            elif "0-1" in message.result:
                text = self.dgttranslate.text("C10_gameresult_black")
            elif "0.5-0.5" in message.result or "1/2-1/2" in message.result:
                text = self.dgttranslate.text("C10_gameresult_draw")
            elif "*" in message.result:
                text = self.dgttranslate.text("C10_gameresult_unknown")
            else:
                text = self.dgttranslate.text("C10_gameresult_unknown")
            await asyncio.sleep(1.5)

            text.beep = self.dgttranslate.bl(BeepLevel.CONFIG)
            text.maxtime = 0.5

            await DispatchDgt.fire(text)

        elif isinstance(message, Message.PROMOTION_DONE):
            await DispatchDgt.fire(Dgt.PROMOTION_DONE(uci_move=message.move.uci(), devs={"ser"}))

    def _grab_only_latest(self, message):
        """Return the latest analysis message of the same type by dropping stale duplicates."""
        if not isinstance(message, self.ANALYSIS_MESSAGE_TYPES):
            return message

        queue = getattr(self.msg_queue, "_queue", None)
        if queue is None:
            return message

        message_type = type(message)
        latest_message, stale_in_queue, replaced_original = self._strip_stale_analysis_messages(
            queue, message_type, message
        )

        total_dropped = stale_in_queue
        if replaced_original:
            # The message we originally got becomes stale if a newer one exists.
            self.msg_queue.task_done()
            total_dropped += 1

        if total_dropped:
            logger.debug(
                "Dropped %d stale %s message from msg_queue",
                total_dropped,
                message_type.__name__,
            )

        return latest_message

    def _strip_stale_analysis_messages(self, queue, message_type, latest_message):
        """Walk the queue once, removing older instances of the same analysis message."""
        kept = []
        same_type_count = 0
        initial_length = len(queue)

        for _ in range(initial_length):
            queued_message = queue.popleft()
            if isinstance(queued_message, message_type):
                latest_message = queued_message
                same_type_count += 1
                continue
            kept.append(queued_message)

        if kept:
            queue.extendleft(reversed(kept))

        stale_in_queue = max(same_type_count - 1, 0)
        for _ in range(stale_in_queue):
            self.msg_queue.task_done()

        replaced_original = same_type_count > 0
        return latest_message, stale_in_queue, replaced_original

    async def message_consumer(self):
        """DgtDisplay message consumer"""
        logger.debug("DgtDisplay msg_queue ready")
        try:
            while True:
                # Check if we have something to display
                message = await self.msg_queue.get()
                # message = self._grab_only_latest(message)
                if (
                    not isinstance(message, Message.DGT_SERIAL_NR)
                    and not isinstance(message, Message.DGT_CLOCK_TIME)
                    and not isinstance(message, Message.CLOCK_TIME)
                    and not isinstance(message, Message.NEW_DEPTH)
                    and not isinstance(message, Message.NEW_SCORE)
                    and not isinstance(message, Message.NEW_PV)
                    and not isinstance(message, Message.WEB_ANALYSIS)
                ):
                    logger.debug("received message from msg_queue: %s", message)
                # issue #45 just process one message at a time - dont spawn task
                # asyncio.create_task(self._process_message(message))
                try:
                    await self._process_message(message)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("DgtDisplay: unhandled exception processing %s", message)
                self.msg_queue.task_done()
                await asyncio.sleep(0.05)  # balancing message queues
        except asyncio.CancelledError:
            logger.debug("DgtDisplay msg_queue cancelled")
