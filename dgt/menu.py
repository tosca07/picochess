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

import os
import subprocess
import logging
import dgt.util
import asyncio
from configobj import ConfigObj  # type: ignore
from collections import OrderedDict
from typing import Dict, List, Set
from pgn import ModeInfo
import chess  # type: ignore
from timecontrol import TimeControl
from utilities import Observable, DispatchDgt, get_tags, version, write_picochess_ini, get_window_command
from dgt.util import (
    TimeMode,
    TimeModeLoop,
    Top,
    TopLoop,
    Mode,
    ModeLoop,
    Language,
    LanguageLoop,
    BeepLevel,
    BeepLoop,
    EBoard,
    EBoardLoop,
    Theme,
    ThemeLoop,
    EngineTop,
    EngineTopLoop,
    System,
    SystemLoop,
    Display,
    DisplayLoop,
    ClockIcons,
    Voice,
    VoiceLoop,
    Info,
    InfoLoop,
    PicoTutor,
    Game,
    GameLoop,
    GameEnd,
    GameEndLoop,
    GameSave,
    GameSaveLoop,
    GameRead,
    GameReadLoop,
    PicoComment,
    PicoCommentLoop,
    PicoCoach,
    PicoCoachLoop,
    EngineRetroSettings,
    EngineRetroSettingsLoop,
    Power,
    PowerLoop,
    GameResult,
    PlayMode,
)

from dgt.api import Dgt, Event
from dgt.board import Rev2Info
from dgt.translate import DgtTranslate
from uci.engine_provider import EngineProvider


logger = logging.getLogger(__name__)


class MenuState(object):
    """Keep the current DgtMenu State."""

    TOP = 100000

    MODE = 200000
    MODE_TYPE = 210000  # normal, observe, ...

    POS = 300000
    POS_COL = 310000
    POS_REV = 311000
    POS_UCI = 311100
    POS_READ = 311110

    TIME = 400000
    TIME_BLITZ = 410000  # blitz, fischer, fixed
    TIME_BLITZ_CTRL = 411000  # time_control objs
    TIME_FISCH = 420000
    TIME_FISCH_CTRL = 421000
    TIME_FIXED = 430000
    TIME_FIXED_CTRL = 431000
    TIME_TOURN = 440000
    TIME_TOURN_CTRL = 441000
    TIME_DEPTH = 450000
    TIME_DEPTH_CTRL = 451000
    TIME_NODE = 460000  # molli: search nodes NNUE
    TIME_NODE_CTRL = 461000  # molli: search nodes NNUE

    BOOK = 500000
    BOOK_NAME = 510000

    ENGINE = 550000

    ENG_MODERN = 600000
    ENG_MODERN_NAME = 610000
    ENG_MODERN_NAME_LEVEL = 611000

    ENG_RETRO = 630000
    ENG_RETRO_NAME = 631000
    ENG_RETRO_NAME_LEVEL = 631100

    ENG_FAV = 650000
    ENG_FAV_NAME = 651000
    ENG_FAV_NAME_LEVEL = 651100

    RETROSETTINGS = 660000
    RETROSETTINGS_RETROWINDOW = 665000
    RETROSETTINGS_RETROSPEED = 661000
    RETROSETTINGS_RETROSPEED_FACTOR = 661100
    RETROSETTINGS_RETROSOUND = 662000
    RETROSETTINGS_RETROSOUND_ONOFF = 662100
    RETROSETTINGS_RETRODISPLAY = 663000
    RETROSETTINGS_RETRODISPLAY_ONOFF = 663100
    RETROSETTINGS_RETROINFO = 664000
    RETROSETTINGS_RETROINFO_SHOW = 664100

    SYS = 700000
    SYS_POWER = 705000
    SYS_POWER_SHUT_DOWN = 705100
    SYS_POWER_EXIT = 705200
    SYS_POWER_RESTART = 705300
    SYS_POWER_UPDATE = 705400
    SYS_POWER_UPDT_ENGINES = 705500
    SYS_INFO = 710000
    SYS_INFO_VERS = 710100
    SYS_INFO_UPDATED = 710200
    SYS_INFO_GIT = 710300
    SYS_INFO_IP = 710400
    SYS_INFO_BATTERY = 710500
    SYS_SOUND = 720000
    SYS_SOUND_BEEP = 721000  # never, always, some
    SYS_LANG = 730000
    SYS_LANG_NAME = 731000  # de, en, ...
    SYS_LOG = 740000
    SYS_VOICE = 750000
    SYS_VOICE_USER = 751000  # user
    SYS_VOICE_USER_MUTE = 751100  # on, off
    SYS_VOICE_USER_MUTE_LANG = 751110  # de, en, ...
    SYS_VOICE_USER_MUTE_LANG_SPEAK = 751111  # al, christina, ...
    SYS_VOICE_COMP = 752000  # computer
    SYS_VOICE_COMP_MUTE = 752100  # on, off
    SYS_VOICE_COMP_MUTE_LANG = 752110  # de, en, ...
    SYS_VOICE_COMP_MUTE_LANG_SPEAK = 752111  # al, christina, ...
    SYS_VOICE_SPEED = 753000  # vspeed
    SYS_VOICE_SPEED_FACTOR = 753100  # 0-7
    SYS_VOICE_VOLUME = 754000
    SYS_VOICE_VOLUME_FACTOR = 754100
    SYS_DISP = 760000
    SYS_DISP_CLOCKSIDE = 761000
    SYS_DISP_CLOCKSIDE_LEFTRIGHT = 761100
    SYS_DISP_CONFIRM = 762000
    SYS_DISP_CONFIRM_YESNO = 762100  # yes,no
    SYS_DISP_PONDER = 763000
    SYS_DISP_PONDER_INTERVAL = 763100  # 1-8
    SYS_DISP_CAPITAL = 764000
    SYS_DISP_CAPTIAL_YESNO = 764100  # yes, no
    SYS_DISP_NOTATION = 765000
    SYS_DISP_NOTATION_MOVE = 765100  # short, long
    SYS_DISP_ENGINENAME = 766000  # molli v3
    SYS_DISP_ENGINENAME_YESNO = 766100  # yes,no
    SYS_EBOARD = 770000
    SYS_EBOARD_TYPE = 771000  # dgt, chesslink, ...
    SYS_THEME = 780000
    SYS_THEME_TYPE = 781000

    PICOTUTOR = 800000
    PICOTUTOR_PICOWATCHER = 810000
    PICOTUTOR_PICOWATCHER_ONOFF = 811000
    PICOTUTOR_PICOCOACH = 820000
    PICOTUTOR_PICOCOACH_ON = 821000
    PICOTUTOR_PICOCOACH_LIFT = 822000
    PICOTUTOR_PICOCOACH_OFF = 823000
    PICOTUTOR_PICOEXPLORER = 830000
    PICOTUTOR_PICOEXPLORER_ONOFF = 831000
    PICOTUTOR_PICOCOMMENT = 840000
    PICOTUTOR_PICOCOMMENT_OFF = 841000
    PICOTUTOR_PICOCOMMENT_ON_ENG = 842000
    PICOTUTOR_PICOCOMMENT_ON_ALL = 843000
    PICOTUTOR_PICOCOMPROB = 850000
    PICOTUTOR_PICOCOMPROB_LIST = 851000

    GAME = 900000
    GAME_GAMENEW = 905000
    GAME_GAMENEW_YESNO = 905100
    GAME_GAMETAKEBACK = 906000
    GAME_GAMEEND = 950000
    GAME_GAMEEND_WHITE_WINS = 951000
    GAME_GAMEEND_BLACK_WINS = 952000
    GAME_GAMEEND_DRAW = 953000
    GAME_GAMESAVE = 910000
    GAME_GAMESAVE_GAME1 = 911000
    GAME_GAMESAVE_GAME2 = 912000
    GAME_GAMESAVE_GAME3 = 913000
    GAME_GAMEREAD = 920000
    GAME_GAMEREAD_GAMELAST = 921000
    GAME_GAMEREAD_GAME1 = 922000
    GAME_GAMEREAD_GAME2 = 923000
    GAME_GAMEREAD_GAME3 = 924000
    GAME_GAMEALTMOVE = 930000
    GAME_GAMEALTMOVE_ONOFF = 931000
    GAME_GAMECONTLAST = 940000
    GAME_GAMECONTLAST_ONOFF = 941000


class DgtMenu(object):
    """Handle the Dgt Menu."""

    def __init__(
        self,
        clockside: str,
        disable_confirm: bool,
        ponder_interval: int,
        user_voice: str,
        comp_voice: str,
        speed_voice: int,
        enable_capital_letters: bool,
        disable_short_move: bool,
        log_file,
        engine_server,
        rol_disp_norm: bool,
        volume_voice: int,
        board_type: EBoard,
        theme_type: str,
        rspeed: float,
        rsound: bool,
        rdisplay: bool,
        rwindow: bool,
        rol_disp_brain: bool,
        show_enginename: bool,
        picocoach: PicoCoach,
        picowatcher: bool,
        picoexplorer: bool,
        picocomment: PicoComment,
        picocomment_prob: int,
        contlast: bool,
        altmove: bool,
        dgttranslate: DgtTranslate,
    ):
        super(DgtMenu, self).__init__()

        self.current_text = None  # save the current text
        self.menu_system_display_rolldispnorm = rol_disp_norm
        self.menu_system_display_rolldispbrain = rol_disp_brain

        self.menu_system_display_enginename = show_enginename

        self.menu_picotutor = PicoTutor.WATCHER
        self.menu_picotutor_picowatcher = picowatcher
        self.menu_picotutor_picocoach = picocoach
        self.menu_picotutor_picoexplorer = picoexplorer
        self.menu_picotutor_picocomment = picocomment

        self.menu_game = Game.NEW
        self.menu_game_end = GameEnd.WHITE_WINS
        self.menu_game_save = GameSave.GAME1
        self.menu_game_read = GameRead.GAMELAST
        self.menu_game_altmove = altmove
        self.menu_game_contlast = contlast

        self.menu_game_new = False

        self.menu_system_display_clockside = clockside
        self.menu_system_display_confirm = disable_confirm
        self.menu_system_display_ponderinterval = ponder_interval
        self.menu_system_display_capital = enable_capital_letters
        self.menu_system_display_notation = disable_short_move  # True = disable short move display => long display
        self.log_file = log_file
        self.remote_engine = bool(engine_server)
        self.dgttranslate = dgttranslate
        if show_enginename:
            self.state = MenuState.ENG_MODERN_NAME
        else:
            self.state = MenuState.TOP

        self.dgt_fen = "8/8/8/8/8/8/8/8"
        self.int_ip = None
        self.ext_ip = None
        self.flip_board = False

        self.menu_position_whitetomove = True
        self.menu_position_reverse = False
        self.menu_position_uci960 = False

        if show_enginename:
            self.menu_top = Top.ENGINE
        else:
            self.menu_top = Top.MODE

        self.menu_mode = Mode.NORMAL
        self.engine_has_960 = False
        self.engine_has_ponder = False
        self.engine_restart = False

        self.menu_engine_index = 0  # index of the currently selected engine within installed engines
        self.menu_engine_level = 0
        self.menu_modern_engine_index = 0  # index of the currently selected engine within installed modern engines
        self.menu_modern_engine_level = 0
        self.menu_retro_engine_index = 0  # index of the currently selected engine within installed retro engines
        self.menu_retro_engine_level = 0
        self.menu_fav_engine_index = 0  # index of the currently selected engine within installed fav engines
        self.menu_fav_engine_level = 0
        self.menu_engine = EngineTop.MODERN_ENGINE

        self.menu_book = 0
        self.all_books: List[Dict[str, str]] = []

        self.menu_system = System.POWER
        self.menu_system_sound = self.dgttranslate.beep

        langs = {
            "en": Language.EN,
            "de": Language.DE,
            "nl": Language.NL,
            "fr": Language.FR,
            "es": Language.ES,
            "it": Language.IT,
        }
        self.menu_system_language = langs[self.dgttranslate.language]

        self.voices_conf = ConfigObj("talker" + os.sep + "voices" + os.sep + "voices.ini")
        self.menu_system_voice = Voice.COMP
        self.menu_system_voice_user_active = bool(user_voice)
        self.menu_system_voice_comp_active = bool(comp_voice)
        try:
            (user_language_name, user_speaker_name) = user_voice.split(":")
            self.menu_system_voice_user_lang = self.voices_conf.keys().index(user_language_name)
            self.menu_system_voice_user_speak = self.voices_conf[user_language_name].keys().index(user_speaker_name)
        except (AttributeError, ValueError):  # None = "not set" throws an AttributeError
            self.menu_system_voice_user_lang = 0
            self.menu_system_voice_user_speak = 0
        try:
            (comp_language_name, comp_speaker_name) = comp_voice.split(":")
            self.menu_system_voice_comp_lang = self.voices_conf.keys().index(comp_language_name)
            self.menu_system_voice_comp_speak = self.voices_conf[comp_language_name].keys().index(comp_speaker_name)
        except (AttributeError, ValueError):  # None = "not set" throws an AttributeError
            self.menu_system_voice_comp_lang = 0
            self.menu_system_voice_comp_speak = 0

        self.menu_system_voice_speedfactor = speed_voice
        self.menu_system_voice_volumefactor = volume_voice
        self._set_volume_voice(volume_voice)

        self.current_board_type = board_type
        self.menu_system_eboard_type = board_type

        self.theme_type = theme_type
        themes = {"light": Theme.LIGHT, "dark": Theme.DARK, "time": Theme.TIME, "auto": Theme.AUTO}
        self.menu_system_theme_type = themes[theme_type]

        self.menu_system_display = Display.CLOCKSIDE
        self.menu_system_info = Info.VERSION
        self.menu_system_power = Power.SHUT_DOWN

        self.menu_time_mode = TimeMode.BLITZ

        self.menu_time_fixed = 0
        self.menu_time_blitz = 2  # Default time control: Blitz, 5min
        self.menu_time_fisch = 0
        self.menu_time_tourn = 0
        self.menu_time_depth = 0
        self.menu_time_node = 0

        self.tc_fixed_list = [" 1", " 3", " 5", "10", "15", "30", "60", "90"]
        self.tc_blitz_list = [" 1", " 3", " 5", "10", "15", "30", "60", "90"]
        self.tc_fisch_list = [
            " 1  1",
            " 3  2",
            " 5  3",
            "10  5",
            "15 10",
            "30 15",
            "60 20",
            "90 30",
            " 0  5",
            " 0 10",
            " 0 15",
            " 0 20",
            " 0 30",
            " 0 60",
            " 0 90",
        ]
        self.tc_tourn_list = [
            "10 10 0 5",
            "20 15 0 15",
            "30 40 0 15",
            "40 120 0 90",
            "40 60 15 30",
            "40 60 30 30",
            "40 90 30 30",
            "40 90 15 60",
            "40 90 30 60",
        ]
        self.tc_depth_list = [" 1", " 2", " 3", " 4", "10", "15", "20", "25"]
        self.tc_node_list = [" 1", " 5", " 10", " 25", "50", "100", "250", "500"]

        self.com_prob_list = [
            "0",
            "5",
            "10",
            "15",
            "20",
            "25",
            "30",
            "40",
            "50",
            "60",
            "70",
            "80",
            "90",
            "100",
        ]

        self.retrospeed_list = [
            "25",
            "50",
            "100",
            "200",
            "300",
            "400",
            "500",
            "600",
            "700",
            "800",
            "900",
            "1000",
            "max.",
        ]
        self.menu_engine_retrospeed_idx = self.retrospeed_list.index("100")
        self.retrospeed_factor = rspeed
        retrospeed = ""
        if float(self.retrospeed_factor) < 0.1:
            self.retrospeed_factor = 0
            retrospeed = "max."
        else:
            retrospeed = str(int(self.retrospeed_factor * 100))
        self.res_engine_retrospeed = self.retrospeed_factor
        if retrospeed in self.retrospeed_list:
            self.menu_engine_retrospeed_idx = self.retrospeed_list.index(retrospeed)

        logger.debug(f"calculated retro speed index: {self.menu_engine_retrospeed_idx}")
        self.res_engine_retrospeed_idx = self.menu_engine_retrospeed_idx

        self.menu_picotutor_picocomment_prob_list = "30"
        self.menu_picocomment_prob_idx = self.com_prob_list.index("30")
        self.menu_picotutor_picocomment_prob_list = str(picocomment_prob)
        self.res_picotutor_picocomment_prob = int(picocomment_prob)
        if self.menu_picotutor_picocomment_prob_list in self.com_prob_list:
            self.menu_picocomment_prob_idx = self.com_prob_list.index(self.menu_picotutor_picocomment_prob_list)
        else:
            self.menu_picocomment_prob_idx = 6
            self.menu_picotutor_picocomment_prob_list = "30"
            self.res_picotutor_picocomment_prob = 30

        display = os.environ.get("DISPLAY")
        if rdisplay and display is not None:
            self.engine_retrodisplay: bool = rdisplay
            self.res_engine_retrodisplay: bool = self.engine_retrodisplay
        else:
            self.engine_retrodisplay = False
            self.res_engine_retrodisplay = False
        self.engine_retrodisplay_onoff = self.engine_retrodisplay
        self.engine_retrosound = rsound
        self.res_engine_retrosound = self.engine_retrosound
        self.engine_retrosound_onoff = self.engine_retrosound
        self.menu_engine_retrosettings = EngineRetroSettings.RETROWINDOW
        self.res_engine_rwindow = rwindow

        self.tc_fixed_map = OrderedDict(
            [
                (
                    "rnbqkbnr/pppppppp/Q7/8/8/8/PPPPPPPP/RNBQKBNR",
                    TimeControl(TimeMode.FIXED, fixed=1),
                ),
                (
                    "rnbqkbnr/pppppppp/1Q6/8/8/8/PPPPPPPP/RNBQKBNR",
                    TimeControl(TimeMode.FIXED, fixed=3),
                ),
                (
                    "rnbqkbnr/pppppppp/2Q5/8/8/8/PPPPPPPP/RNBQKBNR",
                    TimeControl(TimeMode.FIXED, fixed=5),
                ),
                (
                    "rnbqkbnr/pppppppp/3Q4/8/8/8/PPPPPPPP/RNBQKBNR",
                    TimeControl(TimeMode.FIXED, fixed=10),
                ),
                (
                    "rnbqkbnr/pppppppp/4Q3/8/8/8/PPPPPPPP/RNBQKBNR",
                    TimeControl(TimeMode.FIXED, fixed=15),
                ),
                (
                    "rnbqkbnr/pppppppp/5Q2/8/8/8/PPPPPPPP/RNBQKBNR",
                    TimeControl(TimeMode.FIXED, fixed=30),
                ),
                (
                    "rnbqkbnr/pppppppp/6Q1/8/8/8/PPPPPPPP/RNBQKBNR",
                    TimeControl(TimeMode.FIXED, fixed=60),
                ),
                (
                    "rnbqkbnr/pppppppp/7Q/8/8/8/PPPPPPPP/RNBQKBNR",
                    TimeControl(TimeMode.FIXED, fixed=90),
                ),
            ]
        )
        self.tc_blitz_map = OrderedDict(
            [
                (
                    "rnbqkbnr/pppppppp/8/8/Q7/8/PPPPPPPP/RNBQKBNR",
                    TimeControl(TimeMode.BLITZ, blitz=1),
                ),
                (
                    "rnbqkbnr/pppppppp/8/8/1Q6/8/PPPPPPPP/RNBQKBNR",
                    TimeControl(TimeMode.BLITZ, blitz=3),
                ),
                (
                    "rnbqkbnr/pppppppp/8/8/2Q5/8/PPPPPPPP/RNBQKBNR",
                    TimeControl(TimeMode.BLITZ, blitz=5),
                ),
                (
                    "rnbqkbnr/pppppppp/8/8/3Q4/8/PPPPPPPP/RNBQKBNR",
                    TimeControl(TimeMode.BLITZ, blitz=10),
                ),
                (
                    "rnbqkbnr/pppppppp/8/8/4Q3/8/PPPPPPPP/RNBQKBNR",
                    TimeControl(TimeMode.BLITZ, blitz=15),
                ),
                (
                    "rnbqkbnr/pppppppp/8/8/5Q2/8/PPPPPPPP/RNBQKBNR",
                    TimeControl(TimeMode.BLITZ, blitz=30),
                ),
                (
                    "rnbqkbnr/pppppppp/8/8/6Q1/8/PPPPPPPP/RNBQKBNR",
                    TimeControl(TimeMode.BLITZ, blitz=60),
                ),
                (
                    "rnbqkbnr/pppppppp/8/8/7Q/8/PPPPPPPP/RNBQKBNR",
                    TimeControl(TimeMode.BLITZ, blitz=90),
                ),
            ]
        )
        self.tc_fisch_map = OrderedDict(
            [
                (
                    "rnbqkbnr/pppppppp/8/8/8/Q7/PPPPPPPP/RNBQKBNR",
                    TimeControl(TimeMode.FISCHER, blitz=1, fischer=1),
                ),
                (
                    "rnbqkbnr/pppppppp/8/8/8/1Q6/PPPPPPPP/RNBQKBNR",
                    TimeControl(TimeMode.FISCHER, blitz=3, fischer=2),
                ),
                (
                    "rnbqkbnr/pppppppp/8/8/8/2Q5/PPPPPPPP/RNBQKBNR",
                    TimeControl(TimeMode.FISCHER, blitz=5, fischer=3),
                ),
                (
                    "rnbqkbnr/pppppppp/8/8/8/3Q4/PPPPPPPP/RNBQKBNR",
                    TimeControl(TimeMode.FISCHER, blitz=10, fischer=5),
                ),
                (
                    "rnbqkbnr/pppppppp/8/8/8/4Q3/PPPPPPPP/RNBQKBNR",
                    TimeControl(TimeMode.FISCHER, blitz=15, fischer=10),
                ),
                (
                    "rnbqkbnr/pppppppp/8/8/8/5Q2/PPPPPPPP/RNBQKBNR",
                    TimeControl(TimeMode.FISCHER, blitz=30, fischer=15),
                ),
                (
                    "rnbqkbnr/pppppppp/8/8/8/6Q1/PPPPPPPP/RNBQKBNR",
                    TimeControl(TimeMode.FISCHER, blitz=60, fischer=20),
                ),
                (
                    "rnbqkbnr/pppppppp/8/8/8/7Q/PPPPPPPP/RNBQKBNR",
                    TimeControl(TimeMode.FISCHER, blitz=90, fischer=30),
                ),
                ("8/8/8/8/k1K5/8/8/8", TimeControl(TimeMode.FISCHER, blitz=0, fischer=5)),
                ("8/8/8/8/1k1K4/8/8/8", TimeControl(TimeMode.FISCHER, blitz=0, fischer=10)),
                ("8/8/8/8/2k1K3/8/8/8", TimeControl(TimeMode.FISCHER, blitz=0, fischer=15)),
                ("8/8/8/8/3k1K2/8/8/8", TimeControl(TimeMode.FISCHER, blitz=0, fischer=20)),
                ("8/8/8/8/4k1K1/8/8/8", TimeControl(TimeMode.FISCHER, blitz=0, fischer=30)),
                ("8/8/8/8/5k1K/8/8/8", TimeControl(TimeMode.FISCHER, blitz=0, fischer=60)),
                ("8/8/8/8/k2K4/8/8/8", TimeControl(TimeMode.FISCHER, blitz=0, fischer=90)),
            ]
        )
        self.tc_tournaments = [
            TimeControl(TimeMode.BLITZ, blitz=10, fischer=0, moves_to_go=10, blitz2=5),
            TimeControl(TimeMode.BLITZ, blitz=15, fischer=0, moves_to_go=20, blitz2=15),
            TimeControl(TimeMode.BLITZ, blitz=30, fischer=0, moves_to_go=40, blitz2=15),
            TimeControl(TimeMode.BLITZ, blitz=120, fischer=0, moves_to_go=40, blitz2=90),
            TimeControl(TimeMode.FISCHER, blitz=60, fischer=15, moves_to_go=40, blitz2=30),
            TimeControl(TimeMode.FISCHER, blitz=60, fischer=30, moves_to_go=40, blitz2=30),
            TimeControl(TimeMode.FISCHER, blitz=90, fischer=30, moves_to_go=40, blitz2=30),
            TimeControl(TimeMode.FISCHER, blitz=90, fischer=15, moves_to_go=40, blitz2=60),
            TimeControl(TimeMode.FISCHER, blitz=90, fischer=30, moves_to_go=40, blitz2=60),
        ]
        self.tc_depths = [
            TimeControl(TimeMode.FIXED, fixed=900, depth=1),
            TimeControl(TimeMode.FIXED, fixed=900, depth=2),
            TimeControl(TimeMode.FIXED, fixed=900, depth=3),
            TimeControl(TimeMode.FIXED, fixed=900, depth=4),
            TimeControl(TimeMode.FIXED, fixed=900, depth=10),
            TimeControl(TimeMode.FIXED, fixed=900, depth=15),
            TimeControl(TimeMode.FIXED, fixed=900, depth=20),
            TimeControl(TimeMode.FIXED, fixed=900, depth=25),
        ]
        self.tc_nodes = [
            TimeControl(TimeMode.FIXED, fixed=900, node=1),
            TimeControl(TimeMode.FIXED, fixed=900, node=5),
            TimeControl(TimeMode.FIXED, fixed=900, node=10),
            TimeControl(TimeMode.FIXED, fixed=900, node=25),
            TimeControl(TimeMode.FIXED, fixed=900, node=50),
            TimeControl(TimeMode.FIXED, fixed=900, node=100),
            TimeControl(TimeMode.FIXED, fixed=900, node=250),
            TimeControl(TimeMode.FIXED, fixed=900, node=500),
        ]

        # setup the result vars for api (dgtdisplay)
        self.save_choices()
        self.res_engine_index = self.menu_engine_index
        self.res_engine_level = self.menu_engine_level

        # During "picochess" is displayed, some special actions allowed
        self.picochess_displayed: Set[str] = set()
        self.updt_top = False  # inside the update-menu?
        self.updt_devs: Set[str] = set()  # list of devices which are inside the update-menu
        self.updt_tags: List[List[str]] = []
        self.updt_version = 0  # index to current version

        self.battery = "-NA"  # standard value: NotAvailable (discharging)
        self.inside_room = False

    def set_state_current_engine(self, current_engine_file_name: str):
        """Set engine menu index to the one that contains the current engine file name"""
        for index, eng in enumerate(EngineProvider.installed_engines):
            if eng["file"].endswith(current_engine_file_name):
                self.menu_engine_index = index
                break
        self.res_engine_index = self.menu_engine_index
        current_engine = EngineProvider.installed_engines[self.menu_engine_index]
        self.state = MenuState.ENG_MODERN_NAME
        is_modern_engine = False
        is_retro_engine = False
        for index, eng in enumerate(EngineProvider.modern_engines):
            if current_engine["file"] == eng["file"]:
                self.state = MenuState.ENG_MODERN_NAME
                self.menu_modern_engine_index = index
                self.menu_engine = EngineTop.MODERN_ENGINE
                is_modern_engine = True
                break
        for index, eng in enumerate(EngineProvider.retro_engines):
            if current_engine["file"] == eng["file"]:
                self.state = MenuState.ENG_RETRO_NAME
                self.menu_retro_engine_index = index
                self.menu_engine = EngineTop.RETRO_ENGINE
                is_retro_engine = True
                break
        for index, eng in enumerate(EngineProvider.favorite_engines):
            if current_engine["file"] == eng["file"]:
                self.menu_fav_engine_index = index
                if not is_modern_engine and not is_retro_engine:
                    self.state = MenuState.ENG_FAV_NAME
                    self.menu_engine = EngineTop.FAV_ENGINE
                break
        self.menu_top = Top.ENGINE

    def inside_updt_menu(self):
        """Inside update menu."""
        return self.updt_top

    def disable_picochess_displayed(self, dev):
        """Disable picochess display."""
        self.picochess_displayed.discard(dev)

    def enable_picochess_displayed(self, dev):
        """Enable picochess display."""
        self.picochess_displayed.add(dev)
        self.updt_tags = get_tags()
        try:
            self.updt_version = [item[1] for item in self.updt_tags].index(version)
        except ValueError:
            self.updt_version = len(self.updt_tags) - 1

    def inside_picochess_time(self, dev):
        """Picochess displayed on clock."""
        return dev in self.picochess_displayed

    def save_choices(self):
        """Save the user choices to the result vars."""
        self.state = MenuState.TOP

        self.res_mode = self.menu_mode

        self.res_position_whitetomove = self.menu_position_whitetomove
        self.res_position_reverse = self.menu_position_reverse
        self.res_position_uci960 = self.menu_position_uci960

        self.res_time_mode = self.menu_time_mode
        self.res_time_fixed = self.menu_time_fixed
        self.res_time_blitz = self.menu_time_blitz
        self.res_time_fisch = self.menu_time_fisch
        self.res_time_tourn = self.menu_time_tourn
        self.res_time_depth = self.menu_time_depth
        self.res_time_node = self.menu_time_node

        self.res_book_name = self.menu_book

        self.res_system_display_confirm = self.menu_system_display_confirm
        self.res_system_display_ponderinterval = self.menu_system_display_ponderinterval
        self.res_system_display_rolldispnorm = self.menu_system_display_rolldispnorm
        self.res_system_display_rolldispbrain = self.menu_system_display_rolldispbrain
        self.res_system_display_rolldispbrain = self.menu_system_display_rolldispbrain
        self.res_system_display_enginename = self.menu_system_display_enginename
        self.res_picotutor_picocoach = self.menu_picotutor_picocoach
        self.res_picotutor_picowatcher = self.menu_picotutor_picowatcher
        self.res_picotutor_picoexplorer = self.menu_picotutor_picoexplorer
        self.res_picotutor_picocomment = self.menu_picotutor_picocomment
        self.res_picotutor_picocomment_prob = int(self.menu_picotutor_picocomment_prob_list)
        self.res_picotutor = self.menu_picotutor

        self.res_game_game_save = self.menu_game_save
        self.res_game_game_read = self.menu_game_read
        self.res_game_altmove = self.menu_game_altmove
        self.res_game_contlast = self.menu_game_contlast

        self.dgttranslate.set_capital(self.menu_system_display_capital)
        self.dgttranslate.set_notation(self.menu_system_display_notation)
        return False

    def get_comment_factor(self):
        return self.res_picotutor_picocomment_prob

    def get_engine_rwindow(self):
        """Get the flag."""
        return self.res_engine_rwindow

    def get_engine_rspeed(self):
        """Get the flag."""
        return self.res_engine_retrospeed

    def get_engine_rsound(self):
        """Get the flag."""
        return self.res_engine_retrosound

    def get_engine_rdisplay(self):
        """Get the flag."""
        return self.res_engine_retrodisplay

    def set_engine_restart(self, flag: bool):
        """Set the flag."""
        self.engine_restart = flag

    def get_engine_restart(self):
        """Get the flag."""
        return self.engine_restart

    def get_flip_board(self):
        """Get the flag."""
        return self.flip_board

    def get_engine_has_960(self):
        """Get the flag."""
        return self.engine_has_960

    def set_engine_has_960(self, flag: bool):
        """Set the flag."""
        self.engine_has_960 = flag

    def get_engine_has_ponder(self):
        """Get the flag."""
        return self.engine_has_ponder

    def set_engine_has_ponder(self, flag: bool):
        """Set the flag."""
        self.engine_has_ponder = flag

    def get_dgt_fen(self):
        """Get the flag."""
        return self.dgt_fen

    def set_dgt_fen(self, fen: str):
        """Set the flag."""
        self.dgt_fen = fen

    def get_mode(self):
        """Get the flag."""
        return self.res_mode

    def set_mode(self, mode: Mode):
        """Set the flag."""
        self.res_mode = self.menu_mode = mode

    def get_engine(self):
        return EngineProvider.installed_engines[self.res_engine_index]

    def set_engine_index(self, index: int):
        self.res_engine_index = self.menu_engine_index = index

    def get_engine_level_index(self) -> int:
        return self.res_engine_index

    def get_engine_level(self):
        return self.res_engine_level

    def set_engine_level(self, level: int):
        self.res_engine_level = self.menu_engine_level = level
        if self.menu_engine == EngineTop.MODERN_ENGINE:
            self.menu_modern_engine_level = level
        if self.menu_engine == EngineTop.RETRO_ENGINE:
            self.menu_retro_engine_level = level
        if self.menu_engine == EngineTop.FAV_ENGINE:
            self.menu_fav_engine_level = level

    def set_enginename(self, showname: bool):
        """Set the flag."""
        self.res_system_display_enginename = showname

    def get_enginename(self):
        """Get the flag."""
        return self.res_system_display_enginename

    def get_picowatcher(self):
        """Get the flag."""
        return self.res_picotutor_picowatcher

    def get_picocoach(self):
        """Get the flag."""
        return self.res_picotutor_picocoach

    def get_picocomment(self):
        """Get the flag."""
        return self.res_picotutor_picocomment

    def get_picoexplorer(self):
        """Get the flag."""
        return self.res_picotutor_picoexplorer

    def get_game_altmove(self):
        """Get the flag."""
        return self.res_game_altmove

    def get_game_contlast(self):
        """Get the flag."""
        return self.res_game_contlast

    def get_confirm(self):
        """Get the flag."""
        return self.res_system_display_confirm

    def set_book(self, index: int):
        """Set the flag."""
        self.res_book_name = self.menu_book = index

    def set_time_mode(self, mode: TimeMode):
        """Set the flag."""
        self.res_time_mode = self.menu_time_mode = mode

    def get_time_mode(self):
        """Get the flag."""
        return self.res_time_mode

    def set_time_fixed(self, index: int):
        """Set the flag."""
        self.res_time_fixed = self.menu_time_fixed = index

    def get_time_fixed(self):
        """Get the flag."""
        return self.res_time_fixed

    def set_time_blitz(self, index: int):
        """Set the flag."""
        self.res_time_blitz = self.menu_time_blitz = index

    def get_time_blitz(self):
        """Get the flag."""
        return self.res_time_blitz

    def set_time_fisch(self, index: int):
        """Set the flag."""
        self.res_time_fisch = self.menu_time_fisch = index

    def get_time_fisch(self):
        """Get the flag."""
        return self.res_time_fisch

    def set_time_tourn(self, index: int):
        """Set the flag."""
        self.res_time_tourn = self.menu_time_tourn = index

    def get_time_tourn(self):
        """Get the flag."""
        return self.res_time_tourn

    def set_time_depth(self, index: int):
        """Set the flag."""
        self.res_time_depth = self.menu_time_depth = index

    def set_time_node(self, index: int):
        """Set the flag."""
        self.res_time_node = self.menu_time_node = index

    def get_time_depth(self):
        """Get the flag."""
        return self.res_time_depth

    def get_time_node(self):
        """Get the flag."""
        return self.res_time_node

    def set_position_reverse_flipboard(self, flip_board, play_mode):
        """Set the flag."""
        if self.menu_system_eboard_type != dgt.util.EBoard.DGT:
            ModeInfo.set_flipped_board(flip_board)
        else:
            if (not flip_board) and (play_mode == PlayMode.USER_BLACK):
                ModeInfo.set_flipped_board(flip_board)
        self.res_position_reverse = self.flip_board = flip_board

    def get_position_reverse_flipboard(self):
        """Get the flag."""
        return self.res_position_reverse

    def get_ponderinterval(self):
        """Get the flag."""
        return self.res_system_display_ponderinterval

    def get_rolldispnorm(self):
        """Get the flag."""
        return self.res_system_display_rolldispnorm

    def get_rolldispbrain(self):
        """Get the flag."""
        return self.res_system_display_rolldispbrain

    def get(self):
        """Get the current state."""
        return self.state

    def enter_top_menu(self):
        """Set the menu state."""
        self.state = MenuState.TOP
        self.current_text = None
        return False

    def enter_mode_menu(self):
        """Set the menu state."""
        self.state = MenuState.MODE
        text = self.dgttranslate.text(Top.MODE.value)
        return text

    def enter_mode_type_menu(self):
        """Set the menu state."""
        self.state = MenuState.MODE_TYPE
        text = self.dgttranslate.text(self.menu_mode.value)
        return text

    def enter_picotutor_menu(self):
        """Set the picotutor state."""
        self.state = MenuState.PICOTUTOR
        text = self.dgttranslate.text(Top.PICOTUTOR.value)
        return text

    def enter_picotutor_picowatcher_menu(self):
        """Set the picowatcher state."""
        self.state = MenuState.PICOTUTOR_PICOWATCHER
        text = self.dgttranslate.text("B00_picowatcher")
        return text

    def enter_picotutor_picowatcher_onoff_menu(self):
        """Set the menu state."""
        self.state = MenuState.PICOTUTOR_PICOWATCHER_ONOFF
        msg = "on" if self.menu_picotutor_picowatcher else "off"
        text = self.dgttranslate.text("B00_picowatcher_" + msg)
        return text

    def enter_picotutor_picocoach_menu(self):
        """Set the picowcoach state."""
        self.state = MenuState.PICOTUTOR_PICOCOACH
        text = self.dgttranslate.text("B00_picocoach")
        return text

    def enter_picotutor_picocoach_on_menu(self):
        """Set the menu state."""
        self.state = MenuState.PICOTUTOR_PICOCOACH_ON
        text = self.dgttranslate.text("B00_picocoach_on")
        return text

    def enter_picotutor_picocoach_off_menu(self):
        """Set the menu state."""
        self.state = MenuState.PICOTUTOR_PICOCOACH_OFF
        text = self.dgttranslate.text("B00_picocoach_off")
        return text

    def enter_picotutor_picocoach_lift_menu(self):
        """Set the menu state."""
        self.state = MenuState.PICOTUTOR_PICOCOACH_LIFT
        text = self.dgttranslate.text("B00_picocoach_lift")
        return text

    def enter_picotutor_picoexplorer_menu(self):
        """Set the picoeplorer state."""
        self.state = MenuState.PICOTUTOR_PICOEXPLORER
        text = self.dgttranslate.text("B00_picoexplorer")
        return text

    def enter_picotutor_picoexplorer_onoff_menu(self):
        """Set the menu state."""
        self.state = MenuState.PICOTUTOR_PICOEXPLORER_ONOFF
        msg = "on" if self.menu_picotutor_picoexplorer else "off"
        text = self.dgttranslate.text("B00_picoexplorer_" + msg)
        return text

    def enter_picotutor_picocomment_menu(self):
        """Set the picocomment state."""
        self.state = MenuState.PICOTUTOR_PICOCOMMENT
        text = self.dgttranslate.text("B00_picocomment")
        return text

    def enter_picotutor_picocomment_off_menu(self):
        """Set the picocomment state."""
        self.state = MenuState.PICOTUTOR_PICOCOMMENT_OFF
        text = self.dgttranslate.text("B00_picocomment_off")
        return text

    def enter_picotutor_picocomment_on_eng_menu(self):
        """Set the picocomment state."""
        self.state = MenuState.PICOTUTOR_PICOCOMMENT_ON_ENG
        text = self.dgttranslate.text("B00_picocomment_on_eng")
        return text

    def enter_picotutor_picocomment_on_all_menu(self):
        """Set the picocomment state."""
        self.state = MenuState.PICOTUTOR_PICOCOMMENT_ON_ALL
        text = self.dgttranslate.text("B00_picocomment_on_all")
        return text

    def enter_com_prob_menu(self):
        """Set the menu state."""
        self.state = MenuState.PICOTUTOR_PICOCOMPROB
        text = self.dgttranslate.text("B00_picotutor_picoprob_menu")
        return text

    def enter_com_problist_menu(self):
        """Set the menu state."""
        self.state = MenuState.PICOTUTOR_PICOCOMPROB_LIST
        text = self.dgttranslate.text(
            "B00_picocom_prob_list", f"{str(self.com_prob_list[self.menu_picocomment_prob_idx])}%"
        )
        return text

    def enter_game_menu(self):
        """Set the game state."""
        self.state = MenuState.GAME
        text = self.dgttranslate.text(Top.GAME.value)
        return text

    def enter_game_gameend_menu(self):
        """Set the gamesend state."""
        self.state = MenuState.GAME_GAMEEND
        text = self.dgttranslate.text("B00_game_end_menu")
        return text

    def enter_game_gameend_white_wins_menu(self):
        """Set the gameend state."""
        self.state = MenuState.GAME_GAMEEND_WHITE_WINS
        text = self.dgttranslate.text("B00_game_end_white_wins")
        return text

    def enter_game_gameend_black_wins_menu(self):
        """Set the gameend state."""
        self.state = MenuState.GAME_GAMEEND_BLACK_WINS
        text = self.dgttranslate.text("B00_game_end_black_wins")
        return text

    def enter_game_gameend_draw_menu(self):
        """Set the gameend state."""
        self.state = MenuState.GAME_GAMEEND_DRAW
        text = self.dgttranslate.text("B00_game_end_draw")
        return text

    def enter_game_gamesave_menu(self):
        """Set the gamesave state."""
        self.state = MenuState.GAME_GAMESAVE
        text = self.dgttranslate.text("B00_game_save_menu")
        return text

    def enter_game_gamesave_game1_menu(self):
        """Set the gamesave state."""
        self.state = MenuState.GAME_GAMESAVE_GAME1
        text = self.dgttranslate.text("B00_game_save_game1")
        return text

    def enter_game_gamesave_game2_menu(self):
        """Set the gamesave state."""
        self.state = MenuState.GAME_GAMESAVE_GAME2
        text = self.dgttranslate.text("B00_game_save_game2")
        return text

    def enter_game_gamesave_game3_menu(self):
        """Set the gamesave state."""
        self.state = MenuState.GAME_GAMESAVE_GAME3
        text = self.dgttranslate.text("B00_game_save_game3")
        return text

    def enter_game_gameread_menu(self):
        """Set the gameread state."""
        self.state = MenuState.GAME_GAMEREAD
        text = self.dgttranslate.text("B00_game_read_menu")
        return text

    def enter_game_gameread_gamelast_menu(self):
        """Set the gameread state."""
        self.state = MenuState.GAME_GAMEREAD_GAMELAST
        text = self.dgttranslate.text("B00_game_read_gamelast")
        return text

    def enter_game_gameread_game1_menu(self):
        """Set the gameread state."""
        self.state = MenuState.GAME_GAMEREAD_GAME1
        text = self.dgttranslate.text("B00_game_read_game1")
        return text

    def enter_game_gameread_game2_menu(self):
        """Set the gameread state."""
        self.state = MenuState.GAME_GAMEREAD_GAME2
        text = self.dgttranslate.text("B00_game_read_game2")
        return text

    def enter_game_gameread_game3_menu(self):
        """Set the gameread state."""
        self.state = MenuState.GAME_GAMEREAD_GAME3
        text = self.dgttranslate.text("B00_game_read_game3")
        return text

    def enter_game_contlast_menu(self):
        """Set the CONTLAST state."""
        self.state = MenuState.GAME_GAMECONTLAST
        text = self.dgttranslate.text("B00_game_contlast_menu")
        return text

    def enter_game_contlast_onoff_menu(self):
        """Set the menu state."""
        self.state = MenuState.GAME_GAMECONTLAST_ONOFF
        msg = "on" if self.menu_game_contlast else "off"
        text = self.dgttranslate.text("B00_game_contlast_" + msg)
        return text

    def enter_game_altmove_menu(self):
        """Set the ALTMOVE state."""
        self.state = MenuState.GAME_GAMEALTMOVE
        text = self.dgttranslate.text("B00_game_altmove_menu")
        return text

    def enter_game_altmove_onoff_menu(self):
        """Set the menu state."""
        self.state = MenuState.GAME_GAMEALTMOVE_ONOFF
        msg = "on" if self.menu_game_altmove else "off"
        text = self.dgttranslate.text("B00_game_altmove_" + msg)
        return text

    def enter_game_new_menu(self):
        """Set the NEW state."""
        self.state = MenuState.GAME_GAMENEW
        text = self.dgttranslate.text("B00_game_new_menu")
        return text

    def enter_game_takeback_menu(self):
        """Set the TAKEBACK state."""
        self.state = MenuState.GAME_GAMETAKEBACK
        text = self.dgttranslate.text("B00_game_takeback_menu")
        return text

    def enter_game_new_yesno_menu(self):
        """Set the menu state."""
        self.state = MenuState.GAME_GAMENEW_YESNO
        msg = "yes" if self.menu_game_new else "no"
        text = self.dgttranslate.text("B00_game_new_" + msg)
        return text

    def enter_pos_menu(self):
        """Set the menu state."""
        self.state = MenuState.POS
        text = self.dgttranslate.text(Top.POSITION.value)
        return text

    def enter_pos_color_menu(self):
        """Set the menu state."""
        self.state = MenuState.POS_COL
        text = self.dgttranslate.text("B00_sidewhite" if self.menu_position_whitetomove else "B00_sideblack")
        return text

    def enter_pos_rev_menu(self):
        """Set the menu state."""
        self.state = MenuState.POS_REV
        text = self.dgttranslate.text("B00_bw" if self.menu_position_reverse else "B00_wb")
        return text

    def enter_pos_uci_menu(self):
        """Set the menu state."""
        self.state = MenuState.POS_UCI
        text = self.dgttranslate.text("B00_960yes" if self.menu_position_uci960 else "B00_960no")
        return text

    def enter_pos_read_menu(self):
        """Set the menu state."""
        self.state = MenuState.POS_READ
        text = self.dgttranslate.text("B00_scanboard")
        return text

    def enter_time_menu(self):
        """Set the menu state."""
        self.state = MenuState.TIME
        text = self.dgttranslate.text(Top.TIME.value)
        return text

    def enter_time_blitz_menu(self):
        """Set the menu state."""
        self.state = MenuState.TIME_BLITZ
        text = self.dgttranslate.text(self.menu_time_mode.value)
        return text

    def enter_time_blitz_ctrl_menu(self):
        """Set the menu state."""
        self.state = MenuState.TIME_BLITZ_CTRL
        text = self.dgttranslate.text("B00_tc_blitz", self.tc_blitz_list[self.menu_time_blitz])
        return text

    def enter_time_fisch_menu(self):
        """Set the menu state."""
        self.state = MenuState.TIME_FISCH
        text = self.dgttranslate.text(self.menu_time_mode.value)
        return text

    def enter_time_fisch_ctrl_menu(self):
        """Set the menu state."""
        self.state = MenuState.TIME_FISCH_CTRL
        text = self.dgttranslate.text("B00_tc_fisch", self.tc_fisch_list[self.menu_time_fisch])
        return text

    def enter_time_fixed_menu(self):
        """Set the menu state."""
        self.state = MenuState.TIME_FIXED
        text = self.dgttranslate.text(self.menu_time_mode.value)
        return text

    def enter_time_fixed_ctrl_menu(self):
        """Set the menu state."""
        self.state = MenuState.TIME_FIXED_CTRL
        text = self.dgttranslate.text("B00_tc_fixed", self.tc_fixed_list[self.menu_time_fixed])
        return text

    def enter_time_tourn_menu(self):
        """Set the menu state."""
        self.state = MenuState.TIME_TOURN
        text = self.dgttranslate.text(self.menu_time_mode.value)
        return text

    def enter_time_tourn_ctrl_menu(self):
        """Set the menu state."""
        self.state = MenuState.TIME_TOURN_CTRL
        text = self.dgttranslate.text("B00_tc_tourn", self.tc_tourn_list[self.menu_time_tourn])
        return text

    def enter_time_depth_menu(self):
        """Set the menu state."""
        self.state = MenuState.TIME_DEPTH
        text = self.dgttranslate.text(self.menu_time_mode.value)
        return text

    def enter_time_depth_ctrl_menu(self):
        """Set the menu state."""
        self.state = MenuState.TIME_DEPTH_CTRL
        text = self.dgttranslate.text("B00_tc_depth", self.tc_depth_list[self.menu_time_depth])
        return text

    def enter_retrosettings_menu(self):
        """Set the menu state."""
        self.state = MenuState.RETROSETTINGS
        text = self.dgttranslate.text(EngineTop.RETROSETTINGS.value)
        return text

    def enter_retroinfo_menu(self):
        """Set the menu state."""
        self.state = MenuState.RETROSETTINGS_RETROINFO
        text = self.dgttranslate.text(EngineRetroSettings.RETROINFO.value)
        return text

    def enter_retroinfo_show_menu(self):
        """Set the menu state."""
        self.state = MenuState.RETROSETTINGS_RETROINFO_SHOW
        info = ModeInfo.get_retro_features()
        text = self.dgttranslate.text("B00_engine_retroinfo", info)
        return text

    def enter_retrosound_menu(self):
        """Set the menu state."""
        self.state = MenuState.RETROSETTINGS_RETROSOUND
        text = self.dgttranslate.text(EngineRetroSettings.RETROSOUND.value)
        return text

    def enter_retrosound_onoff_menu(self):
        self.state = MenuState.RETROSETTINGS_RETROSOUND_ONOFF
        msg = "on" if self.engine_retrosound else "off"

        self.res_engine_retrosound = self.engine_retrosound
        text = self.dgttranslate.text("B00_engine_retrosound_" + msg)
        return text

    def enter_retrodisplay_menu(self):
        """Set the menu state."""
        self.state = MenuState.RETROSETTINGS_RETRODISPLAY
        text = self.dgttranslate.text(EngineRetroSettings.RETRODISPLAY.value)
        return text

    def enter_retrodisplay_onoff_menu(self):
        self.state = MenuState.RETROSETTINGS_RETRODISPLAY_ONOFF
        msg = "on" if self.engine_retrodisplay else "off"
        text = self.dgttranslate.text("B00_engine_retrodisplay_" + msg)
        return text

    def enter_retrowindow_menu(self):
        """Set the menu state."""
        self.state = MenuState.RETROSETTINGS_RETROWINDOW
        text = self.dgttranslate.text(self.menu_engine_retrosettings.value)
        return text

    def enter_retrospeed_menu(self):
        """Set the menu state."""
        self.state = MenuState.RETROSETTINGS_RETROSPEED
        text = self.dgttranslate.text(EngineRetroSettings.RETROSPEED.value)
        return text

    def enter_retrospeed_factor_menu(self):
        """Set the menu state."""
        l_speed = ""
        self.state = MenuState.RETROSETTINGS_RETROSPEED_FACTOR
        if self.retrospeed_list[self.menu_engine_retrospeed_idx] == "max.":
            l_speed = self.retrospeed_list[self.menu_engine_retrospeed_idx]
        else:
            l_speed = self.retrospeed_list[self.menu_engine_retrospeed_idx] + "%"
        text = self.dgttranslate.text("B00_retrospeed", l_speed)
        return text

    def enter_time_node_menu(self):
        """Set the menu state."""
        self.state = MenuState.TIME_NODE
        text = self.dgttranslate.text(self.menu_time_mode.value)
        return text

    def enter_time_node_ctrl_menu(self):
        """Set the menu state."""
        self.state = MenuState.TIME_NODE_CTRL
        text = self.dgttranslate.text("B00_tc_node", self.tc_node_list[self.menu_time_node])
        return text

    def enter_book_menu(self):
        """Set the menu state."""
        self.state = MenuState.BOOK
        text = self.dgttranslate.text(Top.BOOK.value)
        return text

    def _get_current_book_name(self):
        text = self.all_books[self.menu_book]["text"]
        text.beep = self.dgttranslate.bl(BeepLevel.BUTTON)
        return text

    def enter_book_name_menu(self):
        """Set the menu state."""
        self.state = MenuState.BOOK_NAME
        return self._get_current_book_name()

    def enter_modern_eng_menu(self):
        """Set the menu state."""
        self.state = MenuState.ENG_MODERN
        text = self.dgttranslate.text(EngineTop.MODERN_ENGINE.value)
        return text

    def enter_retro_eng_menu(self):
        """Set the menu state."""
        self.state = MenuState.ENG_RETRO
        text = self.dgttranslate.text(EngineTop.RETRO_ENGINE.value)
        return text

    def enter_fav_eng_menu(self):
        """Set the menu state."""
        self.state = MenuState.ENG_FAV
        text = self.dgttranslate.text(EngineTop.FAV_ENGINE.value)
        return text

    def _get_current_modern_engine_name(self):
        text = EngineProvider.installed_engines[self.menu_modern_engine_index]["text"]
        text.beep = self.dgttranslate.bl(BeepLevel.BUTTON)
        return text

    def _get_current_retro_engine_name(self):
        text = EngineProvider.retro_engines[self.menu_retro_engine_index]["text"]
        text.beep = self.dgttranslate.bl(BeepLevel.BUTTON)
        return text

    def _get_current_fav_engine_name(self):
        text = EngineProvider.favorite_engines[self.menu_fav_engine_index]["text"]
        text.beep = self.dgttranslate.bl(BeepLevel.BUTTON)
        return text

    def get_current_engine_name(self):
        """Get current engine name."""
        text = EngineProvider.installed_engines[self.menu_engine_index]["text"]
        text.beep = self.dgttranslate.bl(BeepLevel.BUTTON)
        return text

    def enter_eng_modern_name_menu(self):
        """Set the menu state."""
        self.state = MenuState.ENG_MODERN_NAME
        return self._get_current_modern_engine_name()

    def enter_eng_retro_name_menu(self):
        """Set the menu state."""
        self.state = MenuState.ENG_RETRO_NAME
        return self._get_current_retro_engine_name()

    def enter_eng_fav_name_menu(self):
        """Set the menu state."""
        self.state = MenuState.ENG_FAV_NAME
        return self._get_current_fav_engine_name()

    def enter_modern_eng_name_level_menu(self):
        """Set the menu state."""
        self.state = MenuState.ENG_MODERN_NAME_LEVEL
        eng = EngineProvider.installed_engines[self.menu_modern_engine_index]
        level_dict = eng["level_dict"]
        if level_dict:
            if self.menu_modern_engine_level is None or len(level_dict) <= self.menu_modern_engine_level:
                self.menu_modern_engine_level = len(level_dict) - 1
            msg = sorted(level_dict)[self.menu_modern_engine_level]
            text = self.dgttranslate.text("B00_level", msg)
        else:
            self.res_engine_index = self.menu_modern_engine_index
            self.res_engine_level = self.menu_modern_engine_level
            text = self.save_choices()
        return text

    def enter_retro_eng_name_level_menu(self):
        """Set the menu state."""
        self.state = MenuState.ENG_RETRO_NAME_LEVEL
        retro_eng = EngineProvider.retro_engines[self.menu_retro_engine_index]
        retro_level_dict = retro_eng["level_dict"]
        if retro_level_dict:
            if self.menu_retro_engine_level is None or len(retro_level_dict) <= self.menu_retro_engine_level:
                self.menu_retro_engine_level = len(retro_level_dict) - 1
            msg = sorted(retro_level_dict)[self.menu_retro_engine_level]
            text = self.dgttranslate.text("B00_level", msg)
        else:
            self.res_engine_index = self.menu_engine_index = (
                len(EngineProvider.modern_engines) + self.menu_retro_engine_index
            )
            self.res_engine_level = self.menu_retro_engine_level
            text = self.save_choices()
        return text

    def enter_fav_eng_name_level_menu(self):
        """Set the menu state."""
        self.state = MenuState.ENG_FAV_NAME_LEVEL
        fav_eng = EngineProvider.favorite_engines[self.menu_fav_engine_index]
        fav_level_dict = fav_eng["level_dict"]
        if fav_level_dict:
            if self.menu_fav_engine_level is None or len(fav_level_dict) <= self.menu_fav_engine_level:
                self.menu_fav_engine_level = len(fav_level_dict) - 1
            msg = sorted(fav_level_dict)[self.menu_fav_engine_level]
            text = self.dgttranslate.text("B00_level", msg)
        else:
            self.res_engine_index = self.menu_engine_index
            self.res_engine_level = self.menu_engine_level
            text = self.save_choices()
        return text

    def enter_engine_menu(self):
        self.state = MenuState.ENGINE
        return self.dgttranslate.text(Top.ENGINE.value)

    def enter_sys_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS
        text = self.dgttranslate.text(Top.SYSTEM.value)
        return text

    def enter_sys_power_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_POWER
        text = self.dgttranslate.text(self.menu_system.value)
        return text

    def enter_sys_power_shut_down_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_POWER_SHUT_DOWN
        text = self.dgttranslate.text(self.menu_system_power.value)
        return text

    def enter_sys_power_restart_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_POWER_RESTART
        text = self.dgttranslate.text(self.menu_system_power.value)
        return text

    def enter_sys_power_update_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_POWER_UPDATE
        text = self.dgttranslate.text(self.menu_system_power.value)
        return text

    def enter_sys_power_updt_engines_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_POWER_UPDT_ENGINES
        text = self.dgttranslate.text(self.menu_system_power.value)
        return text

    def enter_sys_power_exit_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_POWER_EXIT
        text = self.dgttranslate.text(self.menu_system_power.value)
        return text

    def enter_sys_info_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_INFO
        text = self.dgttranslate.text(self.menu_system.value)
        return text

    def enter_sys_info_vers_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_INFO_VERS
        text = self.dgttranslate.text(self.menu_system_info.value)
        return text

    def enter_sys_info_updated_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_INFO_UPDATED
        text = self.dgttranslate.text(self.menu_system_info.value)
        return text

    def enter_sys_info_git_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_INFO_GIT
        text = self.dgttranslate.text(self.menu_system_info.value)
        return text

    def enter_sys_info_ip_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_INFO_IP
        text = self.dgttranslate.text(self.menu_system_info.value)
        return text

    def enter_sys_info_battery_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_INFO_BATTERY
        text = self.dgttranslate.text(self.menu_system_info.value)
        return text

    def enter_sys_sound_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_SOUND
        text = self.dgttranslate.text(self.menu_system.value)
        return text

    def enter_sys_sound_beep_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_SOUND_BEEP
        text = self.dgttranslate.text(self.menu_system_sound.value)
        return text

    def enter_sys_lang_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_LANG
        text = self.dgttranslate.text(self.menu_system.value)
        return text

    def enter_sys_lang_name_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_LANG_NAME
        text = self.dgttranslate.text(self.menu_system_language.value)
        return text

    def enter_sys_log_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_LOG
        text = self.dgttranslate.text(self.menu_system.value)
        return text

    def enter_sys_voice_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_VOICE
        text = self.dgttranslate.text(self.menu_system.value)
        return text

    def enter_sys_voice_user_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_VOICE_USER
        text = self.dgttranslate.text(Voice.USER.value)
        return text

    def enter_sys_voice_user_mute_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_VOICE_USER_MUTE
        msg = "on" if self.menu_system_voice_user_active else "off"
        text = self.dgttranslate.text("B00_voice_" + msg)
        return text

    def enter_sys_voice_user_mute_lang_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_VOICE_USER_MUTE_LANG
        vkey = self.voices_conf.keys()[self.menu_system_voice_user_lang]
        text = self.dgttranslate.text("B00_language_" + vkey + "_menu")
        return text

    def enter_sys_voice_comp_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_VOICE_COMP
        text = self.dgttranslate.text(Voice.COMP.value)
        return text

    def enter_sys_voice_comp_mute_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_VOICE_COMP_MUTE
        msg = "on" if self.menu_system_voice_comp_active else "off"
        text = self.dgttranslate.text("B00_voice_" + msg)
        return text

    def enter_sys_voice_comp_mute_lang_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_VOICE_COMP_MUTE_LANG
        vkey = self.voices_conf.keys()[self.menu_system_voice_comp_lang]
        text = self.dgttranslate.text("B00_language_" + vkey + "_menu")
        return text

    def _get_current_speaker(self, speakers, index: int):
        speaker = speakers[list(speakers)[index]]
        text = Dgt.DISPLAY_TEXT(
            web_text="",
            large_text=speaker["large"],
            medium_text=speaker["medium"],
            small_text=speaker["small"],
        )
        text.beep = self.dgttranslate.bl(BeepLevel.BUTTON)
        text.wait = False
        text.maxtime = 0
        text.devs = {"ser", "i2c", "web"}
        return text

    def enter_sys_voice_user_mute_lang_speak_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_VOICE_USER_MUTE_LANG_SPEAK
        vkey = self.voices_conf.keys()[self.menu_system_voice_user_lang]
        self.menu_system_voice_user_speak %= len(self.voices_conf[vkey])  # in case: change from higher=>lower speakerNo
        return self._get_current_speaker(self.voices_conf[vkey], self.menu_system_voice_user_speak)

    def enter_sys_voice_comp_mute_lang_speak_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_VOICE_COMP_MUTE_LANG_SPEAK
        vkey = self.voices_conf.keys()[self.menu_system_voice_comp_lang]
        self.menu_system_voice_comp_speak %= len(self.voices_conf[vkey])  # in case: change from higher=>lower speakerNo
        return self._get_current_speaker(self.voices_conf[vkey], self.menu_system_voice_comp_speak)

    def enter_sys_voice_speed_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_VOICE_SPEED
        text = self.dgttranslate.text(Voice.SPEED.value)
        return text

    def enter_sys_voice_speed_factor_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_VOICE_SPEED_FACTOR
        text = self.dgttranslate.text("B00_voice_speed", str(self.menu_system_voice_speedfactor))
        return text

    def enter_sys_voice_volume_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_VOICE_VOLUME
        text = self.dgttranslate.text(Voice.VOLUME.value)
        return text

    def enter_sys_voice_volume_factor_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_VOICE_VOLUME_FACTOR
        text = self.dgttranslate.text("B00_voice_volume", str(self.menu_system_voice_volumefactor))
        return text

    def _set_volume_voice(self, volume_factor):
        """Set the Volume-Voice."""
        factor = str(volume_factor * 5)
        for channel in ("Headphone", "Master", "HDMI", "PCM"):
            volume_cmd = f"amixer -M sset {channel} {factor}%"
            logger.debug(volume_cmd)
            result = subprocess.run(
                volume_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                shell=True,
            )
            if result.stdout:
                logger.debug(result.stdout)
        return

    def enter_sys_disp_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_DISP
        text = self.dgttranslate.text(self.menu_system.value)
        return text

    def enter_sys_disp_clockside_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_DISP_CLOCKSIDE
        text = self.dgttranslate.text(Display.CLOCKSIDE.value)
        return text

    def enter_sys_disp_clockside_leftright_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_DISP_CLOCKSIDE_LEFTRIGHT
        msg = "left" if self.menu_system_display_clockside == "left" else "right"
        text = self.dgttranslate.text("B00_clockside_" + msg)
        return text

    def enter_sys_disp_confirm_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_DISP_CONFIRM
        text = self.dgttranslate.text(Display.CONFIRM.value)
        return text

    def enter_sys_disp_confirm_yesno_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_DISP_CONFIRM_YESNO
        msg = "off" if self.menu_system_display_confirm else "on"
        text = self.dgttranslate.text("B00_confirm_" + msg)
        return text

    def enter_sys_disp_enginename_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_DISP_ENGINENAME
        text = self.dgttranslate.text(Display.ENGINENAME.value)
        return text

    def enter_sys_disp_enginename_yesno_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_DISP_ENGINENAME_YESNO
        msg = "on" if self.menu_system_display_enginename else "off"
        text = self.dgttranslate.text("B00_enginename_" + msg)
        return text

    def enter_sys_disp_ponder_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_DISP_PONDER
        text = self.dgttranslate.text(Display.PONDER.value)
        return text

    def enter_sys_disp_ponder_interval_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_DISP_PONDER_INTERVAL
        text = self.dgttranslate.text("B00_ponder_interval", str(self.menu_system_display_ponderinterval))
        return text

    def enter_sys_disp_capital_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_DISP_CAPITAL
        text = self.dgttranslate.text(Display.CAPITAL.value)
        return text

    def enter_sys_disp_capital_yesno_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_DISP_CAPTIAL_YESNO
        msg = "on" if self.menu_system_display_capital else "off"
        text = self.dgttranslate.text("B00_capital_" + msg)
        return text

    def enter_sys_disp_notation_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_DISP_NOTATION
        text = self.dgttranslate.text(Display.NOTATION.value)
        return text

    def enter_sys_disp_notation_move_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_DISP_NOTATION_MOVE
        msg = "long" if self.menu_system_display_notation else "short"
        text = self.dgttranslate.text("B00_notation_" + msg)
        return text

    def enter_sys_eboard_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_EBOARD
        text = self.dgttranslate.text(self.menu_system.value)
        return text

    def enter_sys_eboard_type_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_EBOARD_TYPE
        text = self.dgttranslate.text(self.menu_system_eboard_type.value)
        return text

    def enter_sys_theme_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_THEME
        text = self.dgttranslate.text(self.menu_system.value)
        return text

    def enter_sys_theme_type_menu(self):
        """Set the menu state."""
        self.state = MenuState.SYS_THEME_TYPE
        text = self.dgttranslate.text(self.menu_system_theme_type.value)
        return text

    async def _fire_event(self, event: Event):
        await Observable.fire(event)
        return self.save_choices()

    async def _fire_dispatchdgt(self, text):
        await DispatchDgt.fire(text)
        return self.save_choices()

    async def _fire_timectrl(self, timectrl: TimeControl):
        time_text = self.dgttranslate.text("B10_oktime")
        event = Event.SET_TIME_CONTROL(tc_init=timectrl.get_parameters(), time_text=time_text, show_ok=True)
        return await self._fire_event(event)

    def exit_menu(self):
        """Exit the menu."""
        if self.inside_main_menu():
            self.enter_top_menu()
            if not self.get_confirm():
                return True
        return False

    def main_up(self):
        """Change the menu state after UP action == LEFT arrow button in web interface."""
        text = self.dgttranslate.text("Y00_errormenu")
        if False:  # switch-case
            pass
        elif self.state == MenuState.TOP:
            pass
        elif self.state == MenuState.MODE:
            text = self.enter_top_menu()

        elif self.state == MenuState.MODE_TYPE:
            text = self.enter_mode_menu()

        elif self.state == MenuState.POS:
            text = self.enter_top_menu()

        elif self.state == MenuState.POS_COL:
            text = self.enter_pos_menu()

        elif self.state == MenuState.POS_REV:
            text = self.enter_pos_color_menu()

        elif self.state == MenuState.POS_UCI:
            text = self.enter_pos_rev_menu()

        elif self.state == MenuState.POS_READ:
            text = self.enter_pos_uci_menu()

        elif self.state == MenuState.TIME:
            text = self.enter_top_menu()

        elif self.state == MenuState.TIME_BLITZ:
            text = self.enter_time_menu()

        elif self.state == MenuState.TIME_BLITZ_CTRL:
            text = self.enter_time_blitz_menu()

        elif self.state == MenuState.TIME_FISCH:
            text = self.enter_time_menu()

        elif self.state == MenuState.TIME_FISCH_CTRL:
            text = self.enter_time_fisch_menu()

        elif self.state == MenuState.TIME_FIXED:
            text = self.enter_time_menu()

        elif self.state == MenuState.TIME_FIXED_CTRL:
            text = self.enter_time_fixed_menu()

        elif self.state == MenuState.TIME_TOURN:
            text = self.enter_time_menu()

        elif self.state == MenuState.TIME_TOURN_CTRL:
            text = self.enter_time_tourn_menu()

        elif self.state == MenuState.TIME_DEPTH:
            text = self.enter_time_menu()

        elif self.state == MenuState.TIME_DEPTH_CTRL:
            text = self.enter_time_depth_menu()

        elif self.state == MenuState.TIME_NODE:
            text = self.enter_time_menu()

        elif self.state == MenuState.TIME_NODE_CTRL:
            text = self.enter_time_node_menu()

        elif self.state == MenuState.BOOK:
            text = self.enter_top_menu()

        elif self.state == MenuState.BOOK_NAME:
            text = self.enter_book_menu()

        elif self.state == MenuState.ENGINE:
            text = self.enter_top_menu()

        elif self.state == MenuState.ENG_MODERN:
            text = self.enter_engine_menu()

        elif self.state == MenuState.ENG_MODERN_NAME:
            text = self.enter_modern_eng_menu()

        elif self.state == MenuState.ENG_MODERN_NAME_LEVEL:
            text = self.enter_eng_modern_name_menu()

        elif self.state == MenuState.ENG_RETRO:
            text = self.enter_engine_menu()

        elif self.state == MenuState.ENG_RETRO_NAME:
            text = self.enter_retro_eng_menu()

        elif self.state == MenuState.ENG_RETRO_NAME_LEVEL:
            text = self.enter_eng_retro_name_menu()

        elif self.state == MenuState.ENG_FAV:
            text = self.enter_engine_menu()

        elif self.state == MenuState.ENG_FAV_NAME:
            text = self.enter_fav_eng_menu()

        elif self.state == MenuState.ENG_FAV_NAME_LEVEL:
            text = self.enter_eng_fav_name_menu()

        elif self.state == MenuState.RETROSETTINGS:
            text = self.enter_engine_menu()

        elif self.state == MenuState.RETROSETTINGS_RETROWINDOW:
            text = self.enter_retrosettings_menu()

        elif self.state == MenuState.RETROSETTINGS_RETROSPEED_FACTOR:
            text = self.enter_retrospeed_menu()

        elif self.state == MenuState.RETROSETTINGS_RETROSPEED:
            text = self.enter_retrosettings_menu()

        elif self.state == MenuState.RETROSETTINGS_RETROSOUND:
            text = self.enter_retrosettings_menu()

        elif self.state == MenuState.RETROSETTINGS_RETROSOUND_ONOFF:
            text = self.enter_retrosound_menu()

        elif self.state == MenuState.RETROSETTINGS_RETRODISPLAY:
            text = self.enter_retrosettings_menu()

        elif self.state == MenuState.RETROSETTINGS_RETRODISPLAY_ONOFF:
            text = self.enter_retrodisplay_menu()

        elif self.state == MenuState.RETROSETTINGS_RETROINFO:
            text = self.enter_retrosettings_menu()

        elif self.state == MenuState.RETROSETTINGS_RETROINFO_SHOW:
            text = self.enter_retroinfo_menu()

        elif self.state == MenuState.SYS:
            text = self.enter_top_menu()

        elif self.state == MenuState.SYS_POWER:
            text = self.enter_sys_menu()

        elif self.state == MenuState.SYS_POWER_SHUT_DOWN:
            text = self.enter_sys_power_menu()

        elif self.state == MenuState.SYS_POWER_RESTART:
            text = self.enter_sys_power_menu()

        elif self.state == MenuState.SYS_POWER_UPDATE:
            text = self.enter_sys_power_menu()

        elif self.state == MenuState.SYS_POWER_UPDT_ENGINES:
            text = self.enter_sys_power_menu()

        elif self.state == MenuState.SYS_POWER_EXIT:
            text = self.enter_sys_power_menu()

        elif self.state == MenuState.SYS_INFO:
            text = self.enter_sys_menu()

        elif self.state == MenuState.SYS_INFO_VERS:
            text = self.enter_sys_info_menu()

        elif self.state == MenuState.SYS_INFO_UPDATED:
            text = self.enter_sys_info_menu()

        elif self.state == MenuState.SYS_INFO_GIT:
            text = self.enter_sys_info_menu()

        elif self.state == MenuState.SYS_INFO_IP:
            text = self.enter_sys_info_menu()

        elif self.state == MenuState.SYS_INFO_BATTERY:
            text = self.enter_sys_info_menu()

        elif self.state == MenuState.SYS_SOUND:
            text = self.enter_sys_menu()

        elif self.state == MenuState.SYS_SOUND_BEEP:
            text = self.enter_sys_sound_menu()

        elif self.state == MenuState.SYS_LANG:
            text = self.enter_sys_menu()

        elif self.state == MenuState.SYS_LANG_NAME:
            text = self.enter_sys_lang_menu()

        elif self.state == MenuState.SYS_LOG:
            text = self.enter_sys_menu()

        elif self.state == MenuState.SYS_VOICE:
            text = self.enter_sys_menu()

        elif self.state == MenuState.SYS_VOICE_USER:
            text = self.enter_sys_voice_menu()

        elif self.state == MenuState.SYS_VOICE_USER_MUTE:
            text = self.enter_sys_voice_user_menu()

        elif self.state == MenuState.SYS_VOICE_USER_MUTE_LANG:
            text = self.enter_sys_voice_user_mute_menu()

        elif self.state == MenuState.SYS_VOICE_USER_MUTE_LANG_SPEAK:
            text = self.enter_sys_voice_user_mute_lang_menu()

        elif self.state == MenuState.SYS_VOICE_COMP:
            text = self.enter_sys_voice_menu()

        elif self.state == MenuState.SYS_VOICE_COMP_MUTE:
            text = self.enter_sys_voice_comp_menu()

        elif self.state == MenuState.SYS_VOICE_COMP_MUTE_LANG:
            text = self.enter_sys_voice_comp_mute_menu()

        elif self.state == MenuState.SYS_VOICE_COMP_MUTE_LANG_SPEAK:
            text = self.enter_sys_voice_comp_mute_lang_menu()

        elif self.state == MenuState.SYS_VOICE_SPEED:
            text = self.enter_sys_voice_menu()

        elif self.state == MenuState.SYS_VOICE_SPEED_FACTOR:
            text = self.enter_sys_voice_speed_menu()

        elif self.state == MenuState.SYS_VOICE_VOLUME:
            text = self.enter_sys_voice_menu()

        elif self.state == MenuState.SYS_VOICE_VOLUME_FACTOR:
            text = self.enter_sys_voice_volume_menu()

        elif self.state == MenuState.SYS_DISP:
            text = self.enter_sys_menu()

        elif self.state == MenuState.SYS_DISP_CLOCKSIDE:
            text = self.enter_sys_disp_menu()

        elif self.state == MenuState.SYS_DISP_CLOCKSIDE_LEFTRIGHT:
            text = self.enter_sys_disp_clockside_menu()

        elif self.state == MenuState.SYS_DISP_CONFIRM:
            text = self.enter_sys_disp_menu()

        elif self.state == MenuState.SYS_DISP_CONFIRM_YESNO:
            text = self.enter_sys_disp_confirm_menu()

        elif self.state == MenuState.SYS_DISP_ENGINENAME:
            text = self.enter_sys_disp_menu()

        elif self.state == MenuState.SYS_DISP_ENGINENAME_YESNO:
            text = self.enter_sys_disp_enginename_menu()

        elif self.state == MenuState.SYS_DISP_PONDER:
            text = self.enter_sys_disp_menu()

        elif self.state == MenuState.SYS_DISP_PONDER_INTERVAL:
            text = self.enter_sys_disp_ponder_menu()

        elif self.state == MenuState.SYS_DISP_CAPITAL:
            text = self.enter_sys_disp_menu()

        elif self.state == MenuState.SYS_DISP_CAPTIAL_YESNO:
            text = self.enter_sys_disp_capital_menu()

        elif self.state == MenuState.SYS_DISP_NOTATION:
            text = self.enter_sys_disp_menu()

        elif self.state == MenuState.SYS_DISP_NOTATION_MOVE:
            text = self.enter_sys_disp_notation_menu()

        elif self.state == MenuState.SYS_EBOARD:
            text = self.enter_sys_menu()

        elif self.state == MenuState.SYS_EBOARD_TYPE:
            text = self.enter_sys_eboard_menu()

        elif self.state == MenuState.SYS_THEME:
            text = self.enter_sys_menu()

        elif self.state == MenuState.SYS_THEME_TYPE:
            text = self.enter_sys_theme_menu()

        elif self.state == MenuState.PICOTUTOR:
            text = self.enter_top_menu()

        elif self.state == MenuState.PICOTUTOR_PICOWATCHER:
            text = self.enter_picotutor_menu()

        elif self.state == MenuState.PICOTUTOR_PICOWATCHER_ONOFF:
            text = self.enter_picotutor_picowatcher_menu()

        elif self.state == MenuState.PICOTUTOR_PICOCOACH:
            text = self.enter_picotutor_menu()

        elif self.state == MenuState.PICOTUTOR_PICOCOACH_ON:
            text = self.enter_picotutor_picocoach_menu()

        elif self.state == MenuState.PICOTUTOR_PICOCOACH_LIFT:
            text = self.enter_picotutor_picocoach_menu()

        elif self.state == MenuState.PICOTUTOR_PICOCOACH_OFF:
            text = self.enter_picotutor_picocoach_menu()

        elif self.state == MenuState.PICOTUTOR_PICOEXPLORER:
            text = self.enter_picotutor_menu()

        elif self.state == MenuState.PICOTUTOR_PICOEXPLORER_ONOFF:
            text = self.enter_picotutor_picoexplorer_menu()

        elif self.state == MenuState.PICOTUTOR_PICOCOMMENT:
            text = self.enter_picotutor_menu()

        elif self.state == MenuState.PICOTUTOR_PICOCOMPROB:
            text = self.enter_picotutor_menu()

        elif self.state == MenuState.PICOTUTOR_PICOCOMPROB_LIST:
            text = self.enter_com_prob_menu()

        elif self.state == MenuState.PICOTUTOR_PICOCOMMENT_OFF:
            text = self.enter_picotutor_picocomment_menu()

        elif self.state == MenuState.PICOTUTOR_PICOCOMMENT_ON_ENG:
            text = self.enter_picotutor_picocomment_menu()

        elif self.state == MenuState.PICOTUTOR_PICOCOMMENT_ON_ALL:
            text = self.enter_picotutor_picocomment_menu()

        elif self.state == MenuState.GAME:
            text = self.enter_top_menu()

        elif self.state == MenuState.GAME_GAMEEND:
            text = self.enter_game_menu()

        elif self.state == MenuState.GAME_GAMEEND_WHITE_WINS:
            text = self.enter_game_gameend_menu()

        elif self.state == MenuState.GAME_GAMEEND_BLACK_WINS:
            text = self.enter_game_gameend_menu()

        elif self.state == MenuState.GAME_GAMEEND_DRAW:
            text = self.enter_game_gameend_menu()

        elif self.state == MenuState.GAME_GAMESAVE:
            text = self.enter_game_menu()

        elif self.state == MenuState.GAME_GAMESAVE_GAME1:
            text = self.enter_game_gamesave_menu()

        elif self.state == MenuState.GAME_GAMESAVE_GAME2:
            text = self.enter_game_gamesave_menu()

        elif self.state == MenuState.GAME_GAMESAVE_GAME3:
            text = self.enter_game_gamesave_menu()

        elif self.state == MenuState.GAME_GAMEREAD:
            text = self.enter_game_menu()

        elif self.state == MenuState.GAME_GAMEREAD_GAMELAST:
            text = self.enter_game_gameread_menu()

        elif self.state == MenuState.GAME_GAMEREAD_GAME1:
            text = self.enter_game_gameread_menu()

        elif self.state == MenuState.GAME_GAMEREAD_GAME2:
            text = self.enter_game_gameread_menu()

        elif self.state == MenuState.GAME_GAMEREAD_GAME3:
            text = self.enter_game_gameread_menu()

        elif self.state == MenuState.GAME_GAMEALTMOVE:
            text = self.enter_game_menu()

        elif self.state == MenuState.GAME_GAMEALTMOVE_ONOFF:
            text = self.enter_game_altmove_menu()

        elif self.state == MenuState.GAME_GAMENEW:
            text = self.enter_game_menu()

        elif self.state == MenuState.GAME_GAMETAKEBACK:
            text = self.enter_game_menu()

        elif self.state == MenuState.GAME_GAMENEW_YESNO:
            text = self.enter_game_new_menu()

        elif self.state == MenuState.GAME_GAMECONTLAST:
            text = self.enter_game_menu()

        elif self.state == MenuState.GAME_GAMECONTLAST_ONOFF:
            text = self.enter_game_contlast_menu()

        else:  # Default
            pass
        self.current_text = text
        return text

    async def main_down(self):
        """Change the menu state after DOWN action == RIGHT arrow button in web interface."""
        text = self.dgttranslate.text("Y00_errormenu")
        if self.state == MenuState.TOP:
            if self.menu_top == Top.MODE:
                text = self.enter_mode_menu()
            if self.menu_top == Top.POSITION:
                text = self.enter_pos_menu()
            if self.menu_top == Top.TIME:
                text = self.enter_time_menu()
            if self.menu_top == Top.BOOK:
                text = self.enter_book_menu()
            if self.menu_top == Top.ENGINE:
                text = self.enter_engine_menu()
            if self.menu_top == Top.SYSTEM:
                text = self.enter_sys_menu()
            if self.menu_top == Top.PICOTUTOR:
                text = self.enter_picotutor_menu()
            if self.menu_top == Top.GAME:
                text = self.enter_game_menu()

        elif self.state == MenuState.MODE:
            text = self.enter_mode_type_menu()

        elif self.state == MenuState.MODE_TYPE:
            # maybe do action!
            if self.menu_mode == Mode.BRAIN and not self.get_engine_has_ponder():
                await DispatchDgt.fire(self.dgttranslate.text("Y10_erroreng"))
                text = Dgt.DISPLAY_TIME(force=True, wait=True, devs={"ser", "i2c", "web"})
            else:
                mode_text = self.dgttranslate.text("B10_okmode")
                event = Event.SET_INTERACTION_MODE(mode=self.menu_mode, mode_text=mode_text, show_ok=True)
                text = await self._fire_event(event)

        elif self.state == MenuState.GAME:
            if self.menu_game == Game.NEW:
                text = self.enter_game_new_menu()
            if self.menu_game == Game.TAKEBACK:
                text = self.enter_game_takeback_menu()
            if self.menu_game == Game.END:
                text = self.enter_game_gameend_menu()
            if self.menu_game == Game.SAVE:
                text = self.enter_game_gamesave_menu()
            if self.menu_game == Game.READ:
                text = self.enter_game_gameread_menu()
            if self.menu_game == Game.ALTMOVE:
                text = self.enter_game_altmove_menu()
            if self.menu_game == Game.CONTLAST:
                text = self.enter_game_contlast_menu()

        elif self.state == MenuState.GAME_GAMEEND:
            if self.menu_game_end == GameEnd.WHITE_WINS:
                text = self.enter_game_gameend_white_wins_menu()
            if self.menu_game_end == GameEnd.BLACK_WINS:
                text = self.enter_game_gameend_black_wins_menu()
            if self.menu_game_end == GameEnd.DRAW:
                text = self.enter_game_gameend_draw_menu()

        elif self.state == MenuState.GAME_GAMESAVE:
            if self.menu_game_save == GameSave.GAME1:
                text = self.enter_game_gamesave_game1_menu()
            if self.menu_game_save == GameSave.GAME2:
                text = self.enter_game_gamesave_game2_menu()
            if self.menu_game_save == GameSave.GAME3:
                text = self.enter_game_gamesave_game3_menu()

        elif self.state == MenuState.GAME_GAMEREAD:
            if self.menu_game_read == GameRead.GAMELAST:
                text = self.enter_game_gameread_gamelast_menu()
            if self.menu_game_read == GameRead.GAME1:
                text = self.enter_game_gameread_game1_menu()
            if self.menu_game_read == GameRead.GAME2:
                text = self.enter_game_gameread_game2_menu()
            if self.menu_game_read == GameRead.GAME3:
                text = self.enter_game_gameread_game3_menu()

        elif self.state == MenuState.GAME_GAMENEW:
            text = self.enter_game_new_yesno_menu()

        elif self.state == MenuState.GAME_GAMETAKEBACK:
            await self._fire_event(Event.TAKE_BACK(take_back="TAKEBACK"))
            text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_oktakeback"))

        elif self.state == MenuState.GAME_GAMENEW_YESNO:
            if self.menu_game_new:
                pos960 = 518
                await Observable.fire(Event.NEW_GAME(pos960=pos960))
            text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_okgamenew"))
            await self._fire_event(Event.PICOCOMMENT(picocomment="ok"))

        elif self.state == MenuState.GAME_GAMEALTMOVE:
            text = self.enter_game_altmove_onoff_menu()

        elif self.state == MenuState.GAME_GAMEALTMOVE_ONOFF:
            write_picochess_ini("alt-move", self.menu_game_altmove)
            self.res_game_altmove = self.menu_game_altmove
            event = Event.ALTMOVES(altmoves=self.menu_game_altmove)
            await Observable.fire(event)
            text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_okaltmove"))

        elif self.state == MenuState.GAME_GAMECONTLAST:
            text = self.enter_game_contlast_onoff_menu()

        elif self.state == MenuState.GAME_GAMECONTLAST_ONOFF:
            write_picochess_ini("continue-game", self.menu_game_contlast)
            self.res_game_contlast = self.menu_game_contlast
            event = Event.CONTLAST(contlast=self.menu_game_contlast)
            await Observable.fire(event)
            text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_okcontlast"))

        elif self.state == MenuState.GAME_GAMEEND_WHITE_WINS:
            event = Event.DRAWRESIGN(result=GameResult.WIN_WHITE)
            await Observable.fire(event)
            text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_okgameend"))

        elif self.state == MenuState.GAME_GAMEEND_BLACK_WINS:
            event = Event.DRAWRESIGN(result=GameResult.WIN_BLACK)
            await Observable.fire(event)
            text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_okgameend"))

        elif self.state == MenuState.GAME_GAMEEND_DRAW:
            event = Event.DRAWRESIGN(result=GameResult.DRAW)
            await Observable.fire(event)
            text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_okgameend"))

        elif self.state == MenuState.GAME_GAMESAVE_GAME1:
            event = Event.SAVE_GAME(pgn_filename="picochess_game_1.pgn")
            await Observable.fire(event)
            text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_oksavegame"))

        elif self.state == MenuState.GAME_GAMESAVE_GAME2:
            # raise SAVE_PGN_EVENT
            event = Event.SAVE_GAME(pgn_filename="picochess_game_2.pgn")
            await Observable.fire(event)
            text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_oksavegame"))

        elif self.state == MenuState.GAME_GAMESAVE_GAME3:
            # raise SAVE_PGN_EVENT
            event = Event.SAVE_GAME(pgn_filename="picochess_game_3.pgn")
            await Observable.fire(event)
            text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_oksavegame"))

        elif self.state == MenuState.GAME_GAMEREAD_GAMELAST:
            event = Event.READ_GAME(pgn_filename="last_game.pgn")
            await Observable.fire(event)
            text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_okreadgame"))

        elif self.state == MenuState.GAME_GAMEREAD_GAME1:
            event = Event.READ_GAME(pgn_filename="picochess_game_1.pgn")
            await Observable.fire(event)
            text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_okreadgame"))

        elif self.state == MenuState.GAME_GAMEREAD_GAME2:
            event = Event.READ_GAME(pgn_filename="picochess_game_2.pgn")
            await Observable.fire(event)
            text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_okreadgame"))

        elif self.state == MenuState.GAME_GAMEREAD_GAME3:
            event = Event.READ_GAME(pgn_filename="picochess_game_3.pgn")
            await Observable.fire(event)
            text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_okreadgame"))

        elif self.state == MenuState.PICOTUTOR:
            if self.menu_picotutor == PicoTutor.WATCHER:
                text = self.enter_picotutor_picowatcher_menu()
            if self.menu_picotutor == PicoTutor.COACH:
                text = self.enter_picotutor_picocoach_menu()
            if self.menu_picotutor == PicoTutor.EXPLORER:
                text = self.enter_picotutor_picoexplorer_menu()
            if self.menu_picotutor == PicoTutor.COMMENT:
                text = self.enter_picotutor_picocomment_menu()
            if self.menu_picotutor == PicoTutor.COM_PROB:
                text = self.enter_com_prob_menu()

        elif self.state == MenuState.PICOTUTOR_PICOWATCHER:
            text = self.enter_picotutor_picowatcher_onoff_menu()

        elif self.state == MenuState.PICOTUTOR_PICOWATCHER_ONOFF:
            write_picochess_ini("tutor-watcher", self.menu_picotutor_picowatcher)
            self.res_picotutor_picowatcher = self.menu_picotutor_picowatcher
            event = Event.PICOWATCHER(picowatcher=self.menu_picotutor_picowatcher)
            await Observable.fire(event)
            text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_okpicowatcher"))

        elif self.state == MenuState.PICOTUTOR_PICOCOACH:
            if self.menu_picotutor_picocoach == PicoCoach.COACH_OFF:
                text = self.enter_picotutor_picocoach_off_menu()
            if self.menu_picotutor_picocoach == PicoCoach.COACH_ON:
                text = self.enter_picotutor_picocoach_on_menu()
            if self.menu_picotutor_picocoach == PicoCoach.COACH_LIFT:
                text = self.enter_picotutor_picocoach_lift_menu()

        elif self.state == MenuState.PICOTUTOR_PICOCOACH_OFF:
            l_coach_state = 0
            write_picochess_ini("tutor-coach", "off")
            self.menu_picotutor_picocoach = PicoCoach.COACH_OFF
            self.res_picotutor_picocoach = PicoCoach.COACH_OFF
            event = Event.PICOCOACH(picocoach=l_coach_state)
            await Observable.fire(event)
            text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_okpicocoach"))

        elif self.state == MenuState.PICOTUTOR_PICOCOACH_ON:
            l_coach_state = 1
            if self.res_picotutor_picocoach == self.menu_picotutor_picocoach:
                l_coach_state = 2
            write_picochess_ini("tutor-coach", "on")
            self.menu_picotutor_picocoach = PicoCoach.COACH_ON
            self.res_picotutor_picocoach = PicoCoach.COACH_ON
            event = Event.PICOCOACH(picocoach=l_coach_state)
            await Observable.fire(event)
            text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_okpicocoach"))

        elif self.state == MenuState.PICOTUTOR_PICOCOACH_LIFT:
            l_coach_state = 1
            if self.res_picotutor_picocoach == self.menu_picotutor_picocoach:
                l_coach_state = 2
            write_picochess_ini("tutor-coach", "lift")
            self.menu_picotutor_picocoach = PicoCoach.COACH_LIFT
            self.res_picotutor_picocoach = PicoCoach.COACH_LIFT
            event = Event.PICOCOACH(picocoach=l_coach_state)
            await Observable.fire(event)
            text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_okpicocoach"))

        elif self.state == MenuState.PICOTUTOR_PICOEXPLORER:
            text = self.enter_picotutor_picoexplorer_onoff_menu()

        elif self.state == MenuState.PICOTUTOR_PICOEXPLORER_ONOFF:
            write_picochess_ini("tutor-explorer", self.menu_picotutor_picoexplorer)
            self.res_picotutor_picoexplorer = self.menu_picotutor_picoexplorer
            event = Event.PICOEXPLORER(picoexplorer=self.menu_picotutor_picoexplorer)
            await Observable.fire(event)
            text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_okpicoexplorer"))

        elif self.state == MenuState.PICOTUTOR_PICOCOMMENT:
            if self.menu_picotutor_picocomment == PicoComment.COM_OFF:
                text = self.enter_picotutor_picocomment_off_menu()
            if self.menu_picotutor_picocomment == PicoComment.COM_ON_ENG:
                text = self.enter_picotutor_picocomment_on_eng_menu()
            if self.menu_picotutor_picocomment == PicoComment.COM_ON_ALL:
                text = self.enter_picotutor_picocomment_on_all_menu()

        elif self.state == MenuState.PICOTUTOR_PICOCOMMENT_OFF:
            write_picochess_ini("tutor-comment", "off")
            self.res_picotutor_picocomment = PicoComment.COM_OFF
            self.menu_picotutor_picocomment = PicoComment.COM_OFF
            event = Event.PICOCOMMENT(picocomment=self.menu_picotutor_picocomment)
            await Observable.fire(event)
            text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_okpicocomment"))

        elif self.state == MenuState.PICOTUTOR_PICOCOMMENT_ON_ENG:
            write_picochess_ini("tutor-comment", "single")
            self.res_picotutor_picocomment = PicoComment.COM_ON_ENG
            self.menu_picotutor_picocomment = PicoComment.COM_ON_ENG
            event = Event.PICOCOMMENT(picocomment=self.menu_picotutor_picocomment)
            await Observable.fire(event)
            text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_okpicocomment"))

        elif self.state == MenuState.PICOTUTOR_PICOCOMMENT_ON_ALL:
            write_picochess_ini("tutor-comment", "all")
            self.res_picotutor_picocomment = PicoComment.COM_ON_ALL
            self.menu_picotutor_picocomment = PicoComment.COM_ON_ALL
            event = Event.PICOCOMMENT(picocomment=self.menu_picotutor_picocomment)
            await Observable.fire(event)
            text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_okpicocomment"))

        elif self.state == MenuState.PICOTUTOR_PICOCOMPROB:
            text = self.enter_com_problist_menu()

        elif self.state == MenuState.PICOTUTOR_PICOCOMPROB_LIST:
            self.menu_picotutor_picocomment_prob_list = self.com_prob_list[self.menu_picocomment_prob_idx]
            write_picochess_ini("comment-factor", self.menu_picotutor_picocomment_prob_list)
            self.res_picotutor_picocomment_prob = int(self.menu_picotutor_picocomment_prob_list)
            text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_okpicocomment"))
            await self._fire_event(Event.PICOCOMMENT(picocomment="comment-factor"))

        elif self.state == MenuState.POS:
            text = self.enter_pos_color_menu()

        elif self.state == MenuState.POS_COL:
            text = self.enter_pos_rev_menu()

        elif self.state == MenuState.POS_REV:
            text = self.enter_pos_uci_menu()

        elif self.state == MenuState.POS_UCI:
            text = self.enter_pos_read_menu()

        elif self.state == MenuState.POS_READ:
            fen = self.dgt_fen
            if self.flip_board != self.menu_position_reverse:
                logger.debug(
                    "flipping the board - %s infront now",
                    "B" if self.menu_position_reverse else "W",
                )
                fen = fen[::-1]
            fen += " {0} KQkq - 0 1".format("w" if self.menu_position_whitetomove else "b")
            # ask python-chess to correct the castling string
            bit_board = chess.Board(fen)
            bit_board.set_fen(bit_board.fen())
            if bit_board.is_valid():
                self.flip_board = self.menu_position_reverse
                # @todo figure out PlayMode white or black here
                self.set_position_reverse_flipboard(self.flip_board, PlayMode.USER_WHITE)
                event = Event.SETUP_POSITION(fen=bit_board.fen(), uci960=self.menu_position_uci960)
                await Observable.fire(event)
                # self._reset_moves_and_score() done in "START_NEW_GAME"
                text = self.save_choices()
            else:
                logger.debug("illegal fen %s", fen)
                await DispatchDgt.fire(self.dgttranslate.text("Y10_illegalpos"))
                text = self.dgttranslate.text("B00_scanboard")
                text.wait = True

        elif self.state == MenuState.TIME:
            if self.menu_time_mode == TimeMode.BLITZ:
                text = self.enter_time_blitz_menu()
            if self.menu_time_mode == TimeMode.FISCHER:
                text = self.enter_time_fisch_menu()
            if self.menu_time_mode == TimeMode.FIXED:
                text = self.enter_time_fixed_menu()
            if self.menu_time_mode == TimeMode.TOURN:
                text = self.enter_time_tourn_menu()
            if self.menu_time_mode == TimeMode.DEPTH:
                text = self.enter_time_depth_menu()
            if self.menu_time_mode == TimeMode.NODE:
                text = self.enter_time_node_menu()

        elif self.state == MenuState.TIME_BLITZ:
            text = self.enter_time_blitz_ctrl_menu()

        elif self.state == MenuState.TIME_BLITZ_CTRL:
            text = await self._fire_timectrl(self.tc_blitz_map[list(self.tc_blitz_map)[self.menu_time_blitz]])

        elif self.state == MenuState.TIME_FISCH:
            text = self.enter_time_fisch_ctrl_menu()

        elif self.state == MenuState.TIME_FISCH_CTRL:
            text = await self._fire_timectrl(self.tc_fisch_map[list(self.tc_fisch_map)[self.menu_time_fisch]])

        elif self.state == MenuState.TIME_FIXED:
            text = self.enter_time_fixed_ctrl_menu()

        elif self.state == MenuState.TIME_FIXED_CTRL:
            text = await self._fire_timectrl(self.tc_fixed_map[list(self.tc_fixed_map)[self.menu_time_fixed]])

        elif self.state == MenuState.TIME_TOURN:
            text = self.enter_time_tourn_ctrl_menu()

        elif self.state == MenuState.TIME_TOURN_CTRL:
            text = await self._fire_timectrl(self.tc_tournaments[self.menu_time_tourn])

        elif self.state == MenuState.TIME_DEPTH:
            text = self.enter_time_depth_ctrl_menu()

        elif self.state == MenuState.TIME_DEPTH_CTRL:
            text = await self._fire_timectrl(self.tc_depths[self.menu_time_depth])

        elif self.state == MenuState.TIME_NODE:
            text = self.enter_time_node_ctrl_menu()

        elif self.state == MenuState.TIME_NODE_CTRL:
            text = await self._fire_timectrl(self.tc_nodes[self.menu_time_node])

        elif self.state == MenuState.BOOK:
            text = self.enter_book_name_menu()

        elif self.state == MenuState.BOOK_NAME:
            book_text = self.dgttranslate.text("B10_okbook")
            event = Event.SET_OPENING_BOOK(book=self.all_books[self.menu_book], book_text=book_text, show_ok=True)
            text = await self._fire_event(event)

        elif self.state == MenuState.ENG_MODERN:
            text = self.enter_eng_modern_name_menu()

        elif self.state == MenuState.ENG_MODERN_NAME:
            # maybe do action!
            text = self.enter_modern_eng_name_level_menu()
            if not text:
                # clear old level information
                event = Event.LEVEL(options={}, level_text=self.dgttranslate.text("N07_default", ""), level_name="")
                await Observable.fire(event)
                eng = EngineProvider.modern_engines[self.menu_modern_engine_index]
                eng_text = self.dgttranslate.text("B10_okengine")
                event = Event.NEW_ENGINE(eng=eng, eng_text=eng_text, options={}, show_ok=True)
                await Observable.fire(event)
                self.engine_restart = True

        elif self.state == MenuState.ENG_MODERN_NAME_LEVEL:
            eng = EngineProvider.modern_engines[self.menu_modern_engine_index]
            logger.debug("installed engines in level: %s", str(eng))

            level_dict = eng["level_dict"]
            if level_dict:
                msg = sorted(level_dict)[self.menu_modern_engine_level]
                options = level_dict[msg]
                event = Event.LEVEL(options={}, level_text=self.dgttranslate.text("B10_level", msg), level_name=msg)
                await Observable.fire(event)
            else:
                options = {}
            eng_text = self.dgttranslate.text("B10_okengine")
            event = Event.NEW_ENGINE(eng=eng, eng_text=eng_text, options=options, show_ok=True)
            text = await self._fire_event(event)
            self.engine_restart = True
            self.res_engine_index = self.menu_engine_index = self.menu_modern_engine_index
            self.res_engine_level = self.menu_modern_engine_level

        elif self.state == MenuState.ENG_RETRO:
            text = self.enter_eng_retro_name_menu()

        elif self.state == MenuState.ENG_RETRO_NAME:
            # maybe do action!
            text = self.enter_retro_eng_name_level_menu()
            if not text:
                # clear old level information
                event = Event.LEVEL(options={}, level_text=self.dgttranslate.text("N07_default", ""), level_name="")
                await Observable.fire(event)
                retro_eng = EngineProvider.retro_engines[self.menu_retro_engine_index]
                eng_text = self.dgttranslate.text("B10_okengine")
                event = Event.NEW_ENGINE(eng=retro_eng, eng_text=eng_text, options={}, show_ok=True)
                await Observable.fire(event)
                self.engine_restart = True

        elif self.state == MenuState.ENG_RETRO_NAME_LEVEL:
            retro_eng = EngineProvider.retro_engines[self.menu_retro_engine_index]
            retro_level_dict = retro_eng["level_dict"]
            if retro_level_dict:
                msg = sorted(retro_level_dict)[self.menu_retro_engine_level]
                options = retro_level_dict[msg]
                event = Event.LEVEL(options={}, level_text=self.dgttranslate.text("B10_level", msg), level_name=msg)
                await Observable.fire(event)
            else:
                options = {}
            eng_text = self.dgttranslate.text("B10_okengine")
            event = Event.NEW_ENGINE(eng=retro_eng, eng_text=eng_text, options=options, show_ok=True)
            text = await self._fire_event(event)
            self.engine_restart = True
            self.res_engine_index = self.menu_engine_index = (
                len(EngineProvider.modern_engines) + self.menu_retro_engine_index
            )
            self.res_engine_level = self.menu_retro_engine_level

        elif self.state == MenuState.ENG_FAV:
            text = self.enter_eng_fav_name_menu()

        elif self.state == MenuState.ENG_FAV_NAME:
            # maybe do action!
            text = self.enter_fav_eng_name_level_menu()
            if not text:
                # clear old level information
                event = Event.LEVEL(options={}, level_text=self.dgttranslate.text("N07_default", ""), level_name="")
                await Observable.fire(event)
                retro_eng = EngineProvider.favorite_engines[self.menu_fav_engine_index]
                eng_text = self.dgttranslate.text("B10_okengine")
                event = Event.NEW_ENGINE(eng=retro_eng, eng_text=eng_text, options={}, show_ok=True)
                await Observable.fire(event)
                self.engine_restart = True

        elif self.state == MenuState.ENG_FAV_NAME_LEVEL:
            fav_eng = EngineProvider.favorite_engines[self.menu_fav_engine_index]
            fav_level_dict = fav_eng["level_dict"]
            if fav_level_dict:
                msg = sorted(fav_level_dict)[self.menu_fav_engine_level]
                options = fav_level_dict[msg]
                event = Event.LEVEL(options={}, level_text=self.dgttranslate.text("B10_level", msg), level_name=msg)
                await Observable.fire(event)
            else:
                options = {}
            eng_text = self.dgttranslate.text("B10_okengine")
            event = Event.NEW_ENGINE(eng=fav_eng, eng_text=eng_text, options=options, show_ok=True)
            text = await self._fire_event(event)
            self.engine_restart = True

        elif self.state == MenuState.RETROSETTINGS:
            if self.menu_engine_retrosettings == EngineRetroSettings.RETROWINDOW:
                text = self.enter_retrowindow_menu()
            if self.menu_engine_retrosettings == EngineRetroSettings.RETROSPEED:
                text = self.enter_retrospeed_menu()
            if self.menu_engine_retrosettings == EngineRetroSettings.RETROSOUND:
                text = self.enter_retrosound_menu()
            if self.menu_engine_retrosettings == EngineRetroSettings.RETRODISPLAY:
                text = self.enter_retrodisplay_menu()
            if self.menu_engine_retrosettings == EngineRetroSettings.RETROINFO:
                text = self.enter_retroinfo_menu()

        elif self.state == MenuState.RETROSETTINGS_RETROINFO:
            self.menu_engine_retrosettings = EngineRetroSettings.RETROINFO
            text = self.enter_retroinfo_show_menu()

        elif self.state == MenuState.RETROSETTINGS_RETROINFO_SHOW:
            text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_okrinfo"))
            await self._fire_event(Event.PICOCOMMENT(picocomment="ok"))

        elif self.state == MenuState.RETROSETTINGS_RETROSOUND:
            self.menu_engine_retrosettings = EngineRetroSettings.RETROSOUND
            text = self.enter_retrosound_onoff_menu()

        elif self.state == MenuState.RETROSETTINGS_RETROSOUND_ONOFF:
            self.engine_retrosound = self.engine_retrosound_onoff
            if self.engine_retrosound != self.res_engine_retrosound:
                self.res_engine_retrosound = self.engine_retrosound
                write_picochess_ini("rsound", self.engine_retrosound)
                # trigger rspeed event for rsound change (does just an engine restart)
                await self._fire_event(Event.RSPEED(rspeed=self.retrospeed_factor))
            text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_okrsound"))
            await self._fire_event(Event.PICOCOMMENT(picocomment="ok"))

        elif self.state == MenuState.RETROSETTINGS_RETROWINDOW:
            self.menu_engine_retrosettings = EngineRetroSettings.RETROWINDOW
            self.res_engine_rwindow = not self.res_engine_rwindow
            if ModeInfo.get_emulation_mode():
                cmd = get_window_command("switch_window_toggle_fullscreen")
                if self.get_engine_rdisplay():
                    write_picochess_ini("rwindow", self.res_engine_rwindow)
                    if cmd:
                        subprocess.run(
                            cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            universal_newlines=True,
                            shell=True,
                        )
            text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_ok"))
            await self._fire_event(Event.PICOCOMMENT(picocomment="ok"))

        elif self.state == MenuState.RETROSETTINGS_RETRODISPLAY:
            self.menu_engine_retrosettings = EngineRetroSettings.RETRODISPLAY
            text = self.enter_retrodisplay_onoff_menu()

        elif self.state == MenuState.RETROSETTINGS_RETRODISPLAY_ONOFF:
            self.engine_retrodisplay = self.engine_retrodisplay_onoff
            display = None
            display = os.environ.get("DISPLAY")
            if self.engine_retrodisplay and display is None:
                await DispatchDgt.fire(self.dgttranslate.text("Y10_nodesktop"))
                text = self.enter_retrosettings_menu()
                text.wait = True
            elif self.engine_retrodisplay != self.res_engine_retrodisplay:
                self.res_engine_retrodisplay = self.engine_retrodisplay
                write_picochess_ini("rdisplay", self.engine_retrodisplay)
                # trigger rspped event for rsound change (does just an engine restart)
                await self._fire_event(Event.RSPEED(rspeed=self.retrospeed_factor))

            text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_okrdisplay"))
            await self._fire_event(Event.PICOCOMMENT(picocomment="ok"))

        elif self.state == MenuState.RETROSETTINGS_RETROSPEED:
            self.menu_engine_retrosettings = EngineRetroSettings.RETROSPEED
            text = self.enter_retrospeed_factor_menu()

        elif self.state == MenuState.RETROSETTINGS_RETROSPEED_FACTOR:
            retrospeed = self.retrospeed_list[self.menu_engine_retrospeed_idx]
            tmp_speed = self.res_engine_retrospeed
            if retrospeed == "max.":
                self.retrospeed_factor = 0.0
                self.res_engine_retrospeed = self.retrospeed_factor
            else:
                self.retrospeed_factor = round(float(retrospeed) / 100, 2)
                self.res_engine_retrospeed = self.retrospeed_factor
            if tmp_speed != self.res_engine_retrospeed:
                write_picochess_ini("rspeed", self.retrospeed_factor)
                await self._fire_event(Event.RSPEED(rspeed=self.retrospeed_factor))
            text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_okrspeed"))
            await self._fire_event(Event.PICOCOMMENT(picocomment="ok"))

        elif self.state == MenuState.ENGINE:
            if self.menu_engine == EngineTop.MODERN_ENGINE:
                text = self.enter_modern_eng_menu()
            elif self.menu_engine == EngineTop.RETRO_ENGINE:
                text = self.enter_retro_eng_menu()
            elif self.menu_engine == EngineTop.RETROSETTINGS:
                text = self.enter_retrosettings_menu()
            elif self.menu_engine == EngineTop.FAV_ENGINE:
                text = self.enter_fav_eng_menu()

        elif self.state == MenuState.SYS:
            if self.menu_system == System.POWER:
                text = self.enter_sys_power_menu()
            elif self.menu_system == System.INFO:
                text = self.enter_sys_info_menu()
            elif self.menu_system == System.SOUND:
                text = self.enter_sys_sound_menu()
            elif self.menu_system == System.LANGUAGE:
                text = self.enter_sys_lang_menu()
            elif self.menu_system == System.LOGFILE:
                text = self.enter_sys_log_menu()
            elif self.menu_system == System.VOICE:
                text = self.enter_sys_voice_menu()
            elif self.menu_system == System.DISPLAY:
                text = self.enter_sys_disp_menu()
            elif self.menu_system == System.EBOARD:
                text = self.enter_sys_eboard_menu()
            elif self.menu_system == System.THEME:
                text = self.enter_sys_theme_menu()

        elif self.state == MenuState.SYS_POWER:
            if self.menu_system_power == Power.SHUT_DOWN:
                text = self.enter_sys_power_shut_down_menu()
            if self.menu_system_power == Power.RESTART:
                text = self.enter_sys_power_restart_menu()
            if self.menu_system_power == Power.UPDATE:
                text = self.enter_sys_power_update_menu()
            if self.menu_system_power == Power.UPDT_ENGINES:
                text = self.enter_sys_power_updt_engines_menu()
            if self.menu_system_power == Power.EXIT:
                text = self.enter_sys_power_exit_menu()

        elif self.state == MenuState.SYS_POWER_SHUT_DOWN:
            text = self.dgttranslate.text("B10_power_shut_down_menu")
            await self._fire_event(Event.SHUTDOWN(dev="menu"))

        elif self.state == MenuState.SYS_POWER_RESTART:
            text = self.dgttranslate.text("B10_power_restart_menu")
            await self._fire_event(Event.REBOOT(dev="menu"))

        elif self.state == MenuState.SYS_POWER_UPDATE:
            text = self.dgttranslate.text("B00_updt_picochess")
            await self._fire_event(Event.UPDATE_PICO(tag=""))
            await asyncio.sleep(1)  # let update work first
            await self._fire_event(Event.REBOOT(dev="menu"))

        elif self.state == MenuState.SYS_POWER_UPDT_ENGINES:
            text = self.dgttranslate.text("B00_power_updt_engines")
            await self._fire_event(Event.UPDATE_ENGINES())
            await asyncio.sleep(1)  # let update work first
            await self._fire_event(Event.REBOOT(dev="menu"))

        elif self.state == MenuState.SYS_POWER_EXIT:
            text = self.dgttranslate.text("B10_power_exit_menu")
            await self._fire_event(Event.EXIT(dev="menu"))

        elif self.state == MenuState.SYS_INFO:
            if self.menu_system_info == Info.VERSION:
                text = self.enter_sys_info_vers_menu()
            if self.menu_system_info == Info.UPDATED:
                text = self.enter_sys_info_updated_menu()
            if self.menu_system_info == Info.GIT:
                text = self.enter_sys_info_git_menu()
            if self.menu_system_info == Info.IPADR:
                text = self.enter_sys_info_ip_menu()
            if self.menu_system_info == Info.BATTERY:
                text = self.enter_sys_info_battery_menu()

        elif self.state == MenuState.SYS_INFO_VERS:
            text = self.dgttranslate.text("B10_picochess")
            text.rd = ClockIcons.DOT
            text.wait = False
            text = await self._fire_dispatchdgt(text)

        elif self.state == MenuState.SYS_INFO_UPDATED:
            text = self.dgttranslate.text("B10_pico_updated_status")
            text.rd = ClockIcons.DOT
            text.wait = False
            text = await self._fire_dispatchdgt(text)

        elif self.state == MenuState.SYS_INFO_GIT:
            text = self.dgttranslate.text("B10_pico_git_status")
            text.rd = ClockIcons.DOT
            text.wait = False
            text = await self._fire_dispatchdgt(text)

        elif self.state == MenuState.SYS_INFO_IP:
            if self.int_ip:
                if Rev2Info.get_web_only():
                    msg = self.int_ip
                    text = self.dgttranslate.text("N07_default", msg)
                else:
                    msg = " ".join(self.int_ip.split(".")[:2])
                    text = self.dgttranslate.text("B07_default", msg)
                    if len(msg) == 7:  # delete the " " for XL incase its "123 456"
                        text.s = msg[:3] + msg[4:]
                    await DispatchDgt.fire(text)
                    msg = " ".join(self.int_ip.split(".")[2:])
                    text = self.dgttranslate.text("N07_default", msg)
                    if len(msg) == 7:  # delete the " " for XL incase its "123 456"
                        text.s = msg[:3] + msg[4:]
                    text.wait = True
            else:
                text = self.dgttranslate.text("B10_noipadr")
            text = await self._fire_dispatchdgt(text)

        elif self.state == MenuState.SYS_INFO_BATTERY:
            text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_bat_percent", self.battery))

        elif self.state == MenuState.SYS_SOUND:
            text = self.enter_sys_sound_beep_menu()

        elif self.state == MenuState.SYS_SOUND_BEEP:
            self.dgttranslate.set_beep(self.menu_system_sound)
            write_picochess_ini("beep-config", self.dgttranslate.beep_to_config(self.menu_system_sound))
            # set system beep for picochessweb
            if self.dgttranslate.beep_to_config(self.menu_system_sound) == "sample":
                event = Event.SET_VOICE(type=Voice.BEEPER, lang="en", speaker="beeper", speed=2)
            else:
                event = Event.SET_VOICE(type=Voice.BEEPER, lang="en", speaker="mute", speed=2)

            await Observable.fire(event)
            text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_okbeep"))

        elif self.state == MenuState.SYS_LANG:
            text = self.enter_sys_lang_name_menu()

        elif self.state == MenuState.SYS_LANG_NAME:
            langs = {
                Language.EN: "en",
                Language.DE: "de",
                Language.NL: "nl",
                Language.FR: "fr",
                Language.ES: "es",
                Language.IT: "it",
            }
            language = langs[self.menu_system_language]
            self.dgttranslate.set_language(language)
            write_picochess_ini("language", language)
            await self._fire_event(Event.PICOCOMMENT(picocomment="ok"))
            text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_oklang"))

        elif self.state == MenuState.SYS_LOG:
            if self.log_file:
                await Observable.fire(Event.EMAIL_LOG())
                text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_oklogfile"))
            else:
                text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_nofunction"))
            await self._fire_event(Event.PICOCOMMENT(picocomment="ok"))

        elif self.state == MenuState.SYS_VOICE:
            if self.menu_system_voice == Voice.USER:
                text = self.enter_sys_voice_user_menu()
            if self.menu_system_voice == Voice.COMP:
                text = self.enter_sys_voice_comp_menu()
            if self.menu_system_voice == Voice.SPEED:
                text = self.enter_sys_voice_speed_menu()
            if self.menu_system_voice == Voice.VOLUME:
                text = self.enter_sys_voice_volume_menu()

        elif self.state == MenuState.SYS_VOICE_USER:
            self.menu_system_voice = Voice.USER
            text = self.enter_sys_voice_user_mute_menu()

        elif self.state == MenuState.SYS_VOICE_COMP:
            self.menu_system_voice = Voice.COMP
            text = self.enter_sys_voice_comp_mute_menu()

        elif self.state == MenuState.SYS_VOICE_USER_MUTE:
            if self.menu_system_voice_user_active:
                text = self.enter_sys_voice_user_mute_lang_menu()
            else:
                write_picochess_ini("user-voice", None)
                event = Event.SET_VOICE(type=self.menu_system_voice, lang="en", speaker="mute", speed=2)
                await Observable.fire(event)
                text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_okvoice"))

        elif self.state == MenuState.SYS_VOICE_USER_MUTE_LANG:
            text = self.enter_sys_voice_user_mute_lang_speak_menu()

        elif self.state == MenuState.SYS_VOICE_USER_MUTE_LANG_SPEAK:
            vkey = self.voices_conf.keys()[self.menu_system_voice_user_lang]
            speakers = self.voices_conf[vkey].keys()
            skey = speakers[self.menu_system_voice_user_speak]
            write_picochess_ini("user-voice", f"{vkey}:{skey}")
            event = Event.SET_VOICE(
                type=self.menu_system_voice,
                lang=vkey,
                speaker=skey,
                speed=self.menu_system_voice_speedfactor,
            )
            await Observable.fire(event)
            text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_okvoice"))

        elif self.state == MenuState.SYS_VOICE_COMP_MUTE:
            if self.menu_system_voice_comp_active:
                text = self.enter_sys_voice_comp_mute_lang_menu()
            else:
                write_picochess_ini("computer-voice", None)
                event = Event.SET_VOICE(type=self.menu_system_voice, lang="en", speaker="mute", speed=2)
                await Observable.fire(event)
                text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_okvoice"))

        elif self.state == MenuState.SYS_VOICE_COMP_MUTE_LANG:
            text = self.enter_sys_voice_comp_mute_lang_speak_menu()

        elif self.state == MenuState.SYS_VOICE_COMP_MUTE_LANG_SPEAK:
            vkey = self.voices_conf.keys()[self.menu_system_voice_comp_lang]
            speakers = self.voices_conf[vkey].keys()
            skey = speakers[self.menu_system_voice_comp_speak]
            write_picochess_ini("computer-voice", f"{vkey}:{skey}")
            event = Event.SET_VOICE(
                type=self.menu_system_voice,
                lang=vkey,
                speaker=skey,
                speed=self.menu_system_voice_speedfactor,
            )
            await Observable.fire(event)
            text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_okvoice"))

        elif self.state == MenuState.SYS_VOICE_SPEED:
            self.menu_system_voice = Voice.SPEED
            text = self.enter_sys_voice_speed_factor_menu()

        elif self.state == MenuState.SYS_VOICE_SPEED_FACTOR:
            assert self.menu_system_voice == Voice.SPEED, "menu item is not Voice.SPEED: %s" % self.menu_system_voice
            write_picochess_ini("speed-voice", self.menu_system_voice_speedfactor)
            event = Event.SET_VOICE(
                type=self.menu_system_voice,
                lang="en",
                speaker="mute",  # lang & speaker ignored
                speed=self.menu_system_voice_speedfactor,
            )
            await Observable.fire(event)
            text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_okspeed"))

        elif self.state == MenuState.SYS_VOICE_VOLUME:
            self.menu_system_voice = Voice.VOLUME
            text = self.enter_sys_voice_volume_factor_menu()

        elif self.state == MenuState.SYS_VOICE_VOLUME_FACTOR:
            assert self.menu_system_voice == Voice.VOLUME, "menu item is not Voice.VOLUME: %s" % self.menu_system_voice
            write_picochess_ini("volume-voice", str(self.menu_system_voice_volumefactor))
            self._set_volume_voice(self.menu_system_voice_volumefactor)
            event = Event.SET_VOICE(
                type=self.menu_system_voice,
                lang="en",
                speaker="mute",  # WD00
                speed=self.menu_system_voice_speedfactor,
            )  # WD00
            await Observable.fire(event)
            text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_okvolume"))

        elif self.state == MenuState.SYS_DISP:
            if self.menu_system_display == Display.PONDER:
                text = self.enter_sys_disp_ponder_menu()
            if self.menu_system_display == Display.CLOCKSIDE:
                text = self.enter_sys_disp_clockside_menu()
            if self.menu_system_display == Display.CONFIRM:
                text = self.enter_sys_disp_confirm_menu()
            if self.menu_system_display == Display.ENGINENAME:
                text = self.enter_sys_disp_enginename_menu()
            if self.menu_system_display == Display.CAPITAL:
                text = self.enter_sys_disp_capital_menu()
            if self.menu_system_display == Display.NOTATION:
                text = self.enter_sys_disp_notation_menu()

        elif self.state == MenuState.SYS_DISP_CLOCKSIDE:
            text = self.enter_sys_disp_clockside_leftright_menu()

        elif self.state == MenuState.SYS_DISP_CLOCKSIDE_LEFTRIGHT:
            ModeInfo.set_clock_side(self.menu_system_display_clockside)
            write_picochess_ini("clockside", self.menu_system_display_clockside)
            text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_okclockside"))
            await self._fire_event(Event.PICOCOMMENT(picocomment="ok"))

        elif self.state == MenuState.SYS_DISP_CONFIRM:
            text = self.enter_sys_disp_confirm_yesno_menu()

        elif self.state == MenuState.SYS_DISP_CONFIRM_YESNO:
            write_picochess_ini("disable-confirm-message", self.menu_system_display_confirm)
            text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_okconfirm"))

        elif self.state == MenuState.SYS_DISP_ENGINENAME:
            text = self.enter_sys_disp_enginename_yesno_menu()

        elif self.state == MenuState.SYS_DISP_ENGINENAME_YESNO:
            write_picochess_ini("show-engine", self.menu_system_display_enginename)
            self.res_system_display_enginename = self.menu_system_display_enginename
            event = Event.SHOW_ENGINENAME(show_enginename=self.menu_system_display_enginename)
            await Observable.fire(event)
            text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_okenginename"))

        elif self.state == MenuState.SYS_DISP_PONDER:
            text = self.enter_sys_disp_ponder_interval_menu()

        elif self.state == MenuState.SYS_DISP_PONDER_INTERVAL:
            write_picochess_ini("ponder-interval", self.menu_system_display_ponderinterval)
            await self._fire_event(Event.PICOCOMMENT(picocomment="ok"))
            text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_okponder"))

        elif self.state == MenuState.SYS_DISP_CAPITAL:
            text = self.enter_sys_disp_capital_yesno_menu()

        elif self.state == MenuState.SYS_DISP_CAPTIAL_YESNO:
            write_picochess_ini("enable-capital-letters", self.menu_system_display_capital)
            await self._fire_event(Event.PICOCOMMENT(picocomment="ok"))
            text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_okcapital"))

        elif self.state == MenuState.SYS_DISP_NOTATION:
            text = self.enter_sys_disp_notation_move_menu()

        elif self.state == MenuState.SYS_DISP_NOTATION_MOVE:
            write_picochess_ini("disable-short-notation", self.menu_system_display_notation)
            await self._fire_event(Event.PICOCOMMENT(picocomment="ok"))
            text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_oknotation"))

        elif self.state == MenuState.SYS_EBOARD:
            text = self.enter_sys_eboard_type_menu()

        elif self.state == MenuState.SYS_EBOARD_TYPE:
            eboard_type = self.menu_system_eboard_type.name.lower()
            if "noeboard" in eboard_type:
                if self.int_ip is None and not Rev2Info.get_web_only():
                    self.enter_top_menu()
                    return False
                write_picochess_ini("board-type", eboard_type)
                text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_okeboard"))
                await self._fire_event(Event.PICOCOMMENT(picocomment="ok"))
                if eboard_type != self.current_board_type:
                    # only reboot if e-board type is different from the current e-board type
                    await self._fire_event(Event.REBOOT(dev="menu"))
            else:
                write_picochess_ini("board-type", eboard_type)
                text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_okeboard"))
                await self._fire_event(Event.PICOCOMMENT(picocomment="ok"))
                if eboard_type != self.current_board_type:
                    # only reboot if e-board type is different from the current e-board type
                    await self._fire_event(Event.REBOOT(dev="menu"))

        elif self.state == MenuState.SYS_THEME:
            text = self.enter_sys_theme_type_menu()

        elif self.state == MenuState.SYS_THEME_TYPE:
            themes = {
                Theme.LIGHT: "light",
                Theme.DARK: "dark",
                Theme.TIME: "time",
                Theme.AUTO: "auto",
            }
            theme_type = themes[self.menu_system_theme_type]
            write_picochess_ini("theme", theme_type)
            text = await self._fire_dispatchdgt(self.dgttranslate.text("B10_oktheme"))
            await self._fire_event(Event.PICOCOMMENT(picocomment="ok"))
            if theme_type != self.theme_type:
                # only reboot if theme type is different from the current theme type
                await self._fire_event(Event.REBOOT(dev="menu"))

        else:  # Default
            pass
        self.current_text = text
        return text

    def main_left(self):
        """Change the menu state after LEFT action."""
        text = self.dgttranslate.text("Y00_errormenu")
        if self.state == MenuState.GAME:
            self.state = MenuState.PICOTUTOR
            self.menu_top = TopLoop.prev(self.menu_top)
            text = self.dgttranslate.text(self.menu_top.value)

        elif self.state == MenuState.GAME_GAMENEW:
            self.state = MenuState.GAME_GAMECONTLAST
            self.menu_game = GameLoop.prev(self.menu_game)
            text = self.dgttranslate.text(self.menu_game.value)

        elif self.state == MenuState.GAME_GAMENEW_YESNO:
            self.menu_game_new = not self.menu_game_new
            msg = "yes" if self.menu_game_new else "no"
            text = self.dgttranslate.text("B00_game_new_" + msg)

        elif self.state == MenuState.GAME_GAMETAKEBACK:
            self.state = MenuState.GAME_GAMENEW
            self.menu_game = GameLoop.prev(self.menu_game)
            text = self.dgttranslate.text(self.menu_game.value)

        elif self.state == MenuState.GAME_GAMEEND:
            self.state = MenuState.GAME_GAMETAKEBACK
            self.menu_game = GameLoop.prev(self.menu_game)
            text = self.dgttranslate.text(self.menu_game.value)

        elif self.state == MenuState.GAME_GAMEEND_WHITE_WINS:
            self.state = MenuState.GAME_GAMEEND_DRAW
            self.menu_game_end = GameEndLoop.prev(self.menu_game_end)
            text = self.dgttranslate.text(self.menu_game_end.value)

        elif self.state == MenuState.GAME_GAMEEND_BLACK_WINS:
            self.state = MenuState.GAME_GAMEEND_WHITE_WINS
            self.menu_game_end = GameEndLoop.prev(self.menu_game_end)
            text = self.dgttranslate.text(self.menu_game_end.value)

        elif self.state == MenuState.GAME_GAMEEND_DRAW:
            self.state = MenuState.GAME_GAMEEND_BLACK_WINS
            self.menu_game_end = GameEndLoop.prev(self.menu_game_end)
            text = self.dgttranslate.text(self.menu_game_end.value)

        elif self.state == MenuState.GAME_GAMESAVE:
            self.state = MenuState.GAME_GAMEEND
            self.menu_game = GameLoop.prev(self.menu_game)
            text = self.dgttranslate.text(self.menu_game.value)

        elif self.state == MenuState.GAME_GAMESAVE_GAME1:
            self.state = MenuState.GAME_GAMESAVE_GAME3
            self.menu_game_save = GameSaveLoop.prev(self.menu_game_save)
            text = self.dgttranslate.text(self.menu_game_save.value)

        elif self.state == MenuState.GAME_GAMESAVE_GAME2:
            self.state = MenuState.GAME_GAMESAVE_GAME1
            self.menu_game_save = GameSaveLoop.prev(self.menu_game_save)
            text = self.dgttranslate.text(self.menu_game_save.value)

        elif self.state == MenuState.GAME_GAMESAVE_GAME3:
            self.state = MenuState.GAME_GAMESAVE_GAME2
            self.menu_game_save = GameSaveLoop.prev(self.menu_game_save)
            text = self.dgttranslate.text(self.menu_game_save.value)

        elif self.state == MenuState.GAME_GAMEREAD:
            self.state = MenuState.GAME_GAMESAVE
            self.menu_game = GameLoop.prev(self.menu_game)
            text = self.dgttranslate.text(self.menu_game.value)

        elif self.state == MenuState.GAME_GAMEREAD_GAMELAST:
            self.state = MenuState.GAME_GAMEREAD_GAME3
            self.menu_game_read = GameReadLoop.prev(self.menu_game_read)
            text = self.dgttranslate.text(self.menu_game_read.value)

        elif self.state == MenuState.GAME_GAMEREAD_GAME1:
            self.state = MenuState.GAME_GAMEREAD_GAMELAST
            self.menu_game_read = GameReadLoop.prev(self.menu_game_read)
            text = self.dgttranslate.text(self.menu_game_read.value)

        elif self.state == MenuState.GAME_GAMEREAD_GAME2:
            self.state = MenuState.GAME_GAMEREAD_GAME1
            self.menu_game_read = GameReadLoop.prev(self.menu_game_read)
            text = self.dgttranslate.text(self.menu_game_read.value)

        elif self.state == MenuState.GAME_GAMEREAD_GAME3:
            self.state = MenuState.GAME_GAMEREAD_GAME2
            self.menu_game_read = GameReadLoop.prev(self.menu_game_read)
            text = self.dgttranslate.text(self.menu_game_read.value)

        elif self.state == MenuState.GAME_GAMECONTLAST:
            self.state = MenuState.GAME_GAMEALTMOVE
            self.menu_game = GameLoop.prev(self.menu_game)
            text = self.dgttranslate.text(self.menu_game.value)

        elif self.state == MenuState.GAME_GAMECONTLAST_ONOFF:
            self.menu_game_contlast = not self.menu_game_contlast
            msg = "on" if self.menu_game_contlast else "off"
            text = self.dgttranslate.text("B00_game_contlast_" + msg)

        elif self.state == MenuState.GAME_GAMEALTMOVE:
            self.state = MenuState.GAME_GAMEREAD
            self.menu_game = GameLoop.prev(self.menu_game)
            text = self.dgttranslate.text(self.menu_game.value)

        elif self.state == MenuState.GAME_GAMEALTMOVE_ONOFF:
            self.menu_game_altmove = not self.menu_game_altmove
            msg = "on" if self.menu_game_altmove else "off"
            text = self.dgttranslate.text("B00_game_altmove_" + msg)

        elif self.state == MenuState.PICOTUTOR:
            self.state = MenuState.SYS
            self.menu_top = TopLoop.prev(self.menu_top)
            text = self.dgttranslate.text(self.menu_top.value)

        elif self.state == MenuState.PICOTUTOR_PICOWATCHER:
            self.state = MenuState.PICOTUTOR_PICOCOMPROB
            self.menu_picotutor = PicoTutor.COM_PROB
            text = self.dgttranslate.text(self.menu_picotutor.value)

        elif self.state == MenuState.PICOTUTOR_PICOWATCHER_ONOFF:
            self.menu_picotutor_picowatcher = not self.menu_picotutor_picowatcher
            msg = "on" if self.menu_picotutor_picowatcher else "off"
            text = self.dgttranslate.text("B00_picowatcher_" + msg)

        elif self.state == MenuState.PICOTUTOR_PICOCOACH:
            self.state = MenuState.PICOTUTOR_PICOWATCHER
            self.menu_picotutor = PicoTutor.WATCHER
            text = self.dgttranslate.text(self.menu_picotutor.value)

        elif self.state == MenuState.PICOTUTOR_PICOCOACH_ON:
            self.state = MenuState.PICOTUTOR_PICOCOACH_OFF
            self.menu_picotutor_picocoach = PicoCoachLoop.prev(self.menu_picotutor_picocoach)
            text = self.dgttranslate.text(self.menu_picotutor_picocoach.value)

        elif self.state == MenuState.PICOTUTOR_PICOCOACH_LIFT:
            self.state = MenuState.PICOTUTOR_PICOCOACH_ON
            self.menu_picotutor_picocoach = PicoCoachLoop.prev(self.menu_picotutor_picocoach)
            text = self.dgttranslate.text(self.menu_picotutor_picocoach.value)

        elif self.state == MenuState.PICOTUTOR_PICOCOACH_OFF:
            self.state = MenuState.PICOTUTOR_PICOCOACH_LIFT
            self.menu_picotutor_picocoach = PicoCoachLoop.prev(self.menu_picotutor_picocoach)
            text = self.dgttranslate.text(self.menu_picotutor_picocoach.value)

        elif self.state == MenuState.PICOTUTOR_PICOEXPLORER:
            self.state = MenuState.PICOTUTOR_PICOCOACH
            self.menu_picotutor = PicoTutor.COACH
            text = self.dgttranslate.text(self.menu_picotutor.value)

        elif self.state == MenuState.PICOTUTOR_PICOEXPLORER_ONOFF:
            self.menu_picotutor_picoexplorer = not self.menu_picotutor_picoexplorer
            msg = "on" if self.menu_picotutor_picoexplorer else "off"
            text = self.dgttranslate.text("B00_picoexplorer_" + msg)

        elif self.state == MenuState.PICOTUTOR_PICOCOMMENT:
            self.state = MenuState.PICOTUTOR_PICOEXPLORER
            self.menu_picotutor = PicoTutor.EXPLORER
            text = self.dgttranslate.text(self.menu_picotutor.value)

        elif self.state == MenuState.PICOTUTOR_PICOCOMPROB:
            self.state = MenuState.PICOTUTOR_PICOCOMMENT
            self.menu_picotutor = PicoTutor.COMMENT
            text = self.dgttranslate.text(self.menu_picotutor.value)

        elif self.state == MenuState.PICOTUTOR_PICOCOMPROB_LIST:
            self.menu_picocomment_prob_idx = (self.menu_picocomment_prob_idx - 1) % len(self.com_prob_list)
            self.menu_picocomment_prob_list = self.com_prob_list[self.menu_picocomment_prob_idx]
            l_prob = self.menu_picocomment_prob_list + "%"
            text = self.dgttranslate.text("B00_picocom_prob_list", l_prob)

        elif self.state == MenuState.PICOTUTOR_PICOCOMMENT_OFF:
            self.state = MenuState.PICOTUTOR_PICOCOMMENT_ON_ALL
            self.menu_picotutor_picocomment = PicoCommentLoop.prev(self.menu_picotutor_picocomment)
            text = self.dgttranslate.text(self.menu_picotutor_picocomment.value)

        elif self.state == MenuState.PICOTUTOR_PICOCOMMENT_ON_ALL:
            self.state = MenuState.PICOTUTOR_PICOCOMMENT_ON_ENG
            self.menu_picotutor_picocomment = PicoCommentLoop.prev(self.menu_picotutor_picocomment)
            text = self.dgttranslate.text(self.menu_picotutor_picocomment.value)

        elif self.state == MenuState.PICOTUTOR_PICOCOMMENT_ON_ENG:
            self.state = MenuState.PICOTUTOR_PICOCOMMENT_OFF
            self.menu_picotutor_picocomment = PicoCommentLoop.prev(self.menu_picotutor_picocomment)
            text = self.dgttranslate.text(self.menu_picotutor_picocomment.value)

        elif self.state == MenuState.MODE:
            self.state = MenuState.GAME
            self.menu_top = TopLoop.prev(self.menu_top)
            text = self.dgttranslate.text(self.menu_top.value)

        elif self.state == MenuState.MODE_TYPE:
            self.menu_mode = ModeLoop.prev(self.menu_mode)
            text = self.dgttranslate.text(self.menu_mode.value)

        elif self.state == MenuState.POS:
            self.state = MenuState.MODE
            self.menu_top = TopLoop.prev(self.menu_top)
            text = self.dgttranslate.text(self.menu_top.value)

        elif self.state == MenuState.POS_COL:
            self.menu_position_whitetomove = not self.menu_position_whitetomove
            text = self.dgttranslate.text("B00_sidewhite" if self.menu_position_whitetomove else "B00_sideblack")

        elif self.state == MenuState.POS_REV:
            self.menu_position_reverse = not self.menu_position_reverse
            text = self.dgttranslate.text("B00_bw" if self.menu_position_reverse else "B00_wb")

        elif self.state == MenuState.POS_UCI:
            if self.engine_has_960:
                self.menu_position_uci960 = not self.menu_position_uci960
                text = self.dgttranslate.text("B00_960yes" if self.menu_position_uci960 else "B00_960no")
            else:
                text = self.dgttranslate.text("Y10_error960")

        elif self.state == MenuState.POS_READ:
            text = self.dgttranslate.text("B00_nofunction")

        elif self.state == MenuState.TIME:
            self.state = MenuState.POS
            self.menu_top = TopLoop.prev(self.menu_top)
            text = self.dgttranslate.text(self.menu_top.value)

        elif self.state == MenuState.TIME_BLITZ:
            self.state = MenuState.TIME_FIXED
            self.menu_time_mode = TimeModeLoop.prev(self.menu_time_mode)
            text = self.dgttranslate.text(self.menu_time_mode.value)

        elif self.state == MenuState.TIME_BLITZ_CTRL:
            self.menu_time_blitz = (self.menu_time_blitz - 1) % len(self.tc_blitz_map)
            text = self.dgttranslate.text("B00_tc_blitz", self.tc_blitz_list[self.menu_time_blitz])

        elif self.state == MenuState.TIME_FISCH:
            self.state = MenuState.TIME_BLITZ
            self.menu_time_mode = TimeModeLoop.prev(self.menu_time_mode)
            text = self.dgttranslate.text(self.menu_time_mode.value)

        elif self.state == MenuState.TIME_FISCH_CTRL:
            self.menu_time_fisch = (self.menu_time_fisch - 1) % len(self.tc_fisch_map)
            text = self.dgttranslate.text("B00_tc_fisch", self.tc_fisch_list[self.menu_time_fisch])

        elif self.state == MenuState.TIME_FIXED:
            self.state = MenuState.TIME_NODE
            self.menu_time_mode = TimeModeLoop.prev(self.menu_time_mode)
            text = self.dgttranslate.text(self.menu_time_mode.value)

        elif self.state == MenuState.TIME_FIXED_CTRL:
            self.menu_time_fixed = (self.menu_time_fixed - 1) % len(self.tc_fixed_map)
            text = self.dgttranslate.text("B00_tc_fixed", self.tc_fixed_list[self.menu_time_fixed])

        elif self.state == MenuState.TIME_TOURN:
            self.state = MenuState.TIME_FISCH
            self.menu_time_mode = TimeModeLoop.prev(self.menu_time_mode)
            text = self.dgttranslate.text(self.menu_time_mode.value)

        elif self.state == MenuState.TIME_TOURN_CTRL:
            self.menu_time_tourn = (self.menu_time_tourn - 1) % len(self.tc_tournaments)
            text = self.dgttranslate.text("B00_tc_tourn", self.tc_tourn_list[self.menu_time_tourn])

        elif self.state == MenuState.TIME_DEPTH:
            self.state = MenuState.TIME_TOURN
            self.menu_time_mode = TimeModeLoop.prev(self.menu_time_mode)
            text = self.dgttranslate.text(self.menu_time_mode.value)

        elif self.state == MenuState.TIME_DEPTH_CTRL:
            self.menu_time_depth = (self.menu_time_depth - 1) % len(self.tc_depths)
            text = self.dgttranslate.text("B00_tc_depth", self.tc_depth_list[self.menu_time_depth])

        elif self.state == MenuState.TIME_NODE:
            self.state = MenuState.TIME_DEPTH
            self.menu_time_mode = TimeModeLoop.prev(self.menu_time_mode)
            text = self.dgttranslate.text(self.menu_time_mode.value)

        elif self.state == MenuState.TIME_NODE_CTRL:
            self.menu_time_node = (self.menu_time_node - 1) % len(self.tc_nodes)
            text = self.dgttranslate.text("B00_tc_node", self.tc_node_list[self.menu_time_node])

        elif self.state == MenuState.BOOK:
            self.state = MenuState.TIME
            self.menu_top = TopLoop.prev(self.menu_top)
            text = self.dgttranslate.text(self.menu_top.value)

        elif self.state == MenuState.BOOK_NAME:
            self.menu_book = (self.menu_book - 1) % len(self.all_books)
            text = self._get_current_book_name()

        elif self.state == MenuState.ENGINE:
            self.state = MenuState.BOOK
            self.menu_top = TopLoop.prev(self.menu_top)
            text = self.dgttranslate.text(self.menu_top.value)

        elif self.state == MenuState.ENG_MODERN:
            self.state = MenuState.ENG_FAV
            self.menu_engine = EngineTopLoop.prev(self.menu_engine)
            text = self.dgttranslate.text(self.menu_engine.value)

        elif self.state == MenuState.ENG_MODERN_NAME:
            self.menu_modern_engine_index = (self.menu_modern_engine_index - 1) % len(EngineProvider.modern_engines)
            text = self._get_current_modern_engine_name()

        elif self.state == MenuState.ENG_MODERN_NAME_LEVEL:
            level_dict = EngineProvider.modern_engines[self.menu_modern_engine_index]["level_dict"]
            self.menu_modern_engine_level = (self.menu_modern_engine_level - 1) % len(level_dict)
            msg = sorted(level_dict)[self.menu_modern_engine_level]
            text = self.dgttranslate.text("B00_level", msg)

        elif self.state == MenuState.ENG_RETRO:
            self.state = MenuState.ENG_MODERN
            self.menu_engine = EngineTopLoop.prev(self.menu_engine)
            text = self.dgttranslate.text(self.menu_engine.value)

        elif self.state == MenuState.ENG_RETRO_NAME:
            self.menu_retro_engine_index = (self.menu_retro_engine_index - 1) % len(EngineProvider.retro_engines)
            text = self._get_current_retro_engine_name()

        elif self.state == MenuState.ENG_RETRO_NAME_LEVEL:
            retro_level_dict = EngineProvider.retro_engines[self.menu_retro_engine_index]["level_dict"]
            self.menu_retro_engine_level = (self.menu_retro_engine_level - 1) % len(retro_level_dict)
            msg = sorted(retro_level_dict)[self.menu_retro_engine_level]
            text = self.dgttranslate.text("B00_level", msg)

        elif self.state == MenuState.ENG_FAV:
            self.state = MenuState.RETROSETTINGS
            self.menu_engine = EngineTopLoop.prev(self.menu_engine)
            text = self.dgttranslate.text(self.menu_engine.value)

        elif self.state == MenuState.ENG_FAV_NAME:
            self.menu_fav_engine_index = (self.menu_fav_engine_index - 1) % len(EngineProvider.favorite_engines)
            text = self._get_current_fav_engine_name()

        elif self.state == MenuState.ENG_FAV_NAME_LEVEL:
            retro_level_dict = EngineProvider.favorite_engines[self.menu_fav_engine_index]["level_dict"]
            self.menu_fav_engine_level = (self.menu_fav_engine_level - 1) % len(retro_level_dict)
            msg = sorted(retro_level_dict)[self.menu_fav_engine_level]
            text = self.dgttranslate.text("B00_level", msg)

        elif self.state == MenuState.RETROSETTINGS:
            self.state = MenuState.ENG_RETRO
            self.menu_engine = EngineTopLoop.prev(self.menu_engine)
            text = self.dgttranslate.text(self.menu_engine.value)

        elif self.state == MenuState.RETROSETTINGS_RETROSOUND_ONOFF:
            self.engine_retrosound_onoff = not self.engine_retrosound_onoff
            msg = "on" if self.engine_retrosound_onoff else "off"
            text = self.dgttranslate.text("B00_engine_retrosound_" + msg)

        elif self.state == MenuState.RETROSETTINGS_RETRODISPLAY_ONOFF:
            self.engine_retrodisplay_onoff = not self.engine_retrodisplay_onoff
            msg = "on" if self.engine_retrodisplay_onoff else "off"
            text = self.dgttranslate.text("B00_engine_retrodisplay_" + msg)

        elif self.state == MenuState.RETROSETTINGS_RETROWINDOW:
            self.state = MenuState.RETROSETTINGS_RETROINFO
            self.menu_engine_retrosettings = EngineRetroSettingsLoop.prev(self.menu_engine_retrosettings)
            text = self.dgttranslate.text(self.menu_engine_retrosettings.value)

        elif self.state == MenuState.RETROSETTINGS_RETROSPEED:
            self.state = MenuState.RETROSETTINGS_RETROWINDOW
            self.menu_engine_retrosettings = EngineRetroSettingsLoop.prev(self.menu_engine_retrosettings)
            text = self.dgttranslate.text(self.menu_engine_retrosettings.value)

        elif self.state == MenuState.RETROSETTINGS_RETRODISPLAY:
            self.state = MenuState.RETROSETTINGS_RETROSOUND
            self.menu_engine_retrosettings = EngineRetroSettingsLoop.prev(self.menu_engine_retrosettings)
            text = self.dgttranslate.text(self.menu_engine_retrosettings.value)

        elif self.state == MenuState.RETROSETTINGS_RETROINFO:
            self.state = MenuState.RETROSETTINGS_RETRODISPLAY
            self.menu_engine_retrosettings = EngineRetroSettingsLoop.prev(self.menu_engine_retrosettings)
            text = self.dgttranslate.text(self.menu_engine_retrosettings.value)

        elif self.state == MenuState.RETROSETTINGS_RETROSOUND:
            self.state = MenuState.RETROSETTINGS_RETROSPEED
            self.menu_engine_retrosettings = EngineRetroSettingsLoop.prev(self.menu_engine_retrosettings)
            text = self.dgttranslate.text(self.menu_engine_retrosettings.value)

        elif self.state == MenuState.RETROSETTINGS_RETROINFO_SHOW:
            text = self.enter_retroinfo_show_menu()

        elif self.state == MenuState.RETROSETTINGS_RETROSPEED_FACTOR:
            l_speed = ""
            self.menu_engine_retrospeed_idx = (self.menu_engine_retrospeed_idx - 1) % len(self.retrospeed_list)
            if self.retrospeed_list[self.menu_engine_retrospeed_idx] == "max.":
                l_speed = self.retrospeed_list[self.menu_engine_retrospeed_idx]
            else:
                l_speed = self.retrospeed_list[self.menu_engine_retrospeed_idx] + "%"
            text = self.dgttranslate.text("B00_retrospeed", l_speed)

        elif self.state == MenuState.SYS:
            self.state = MenuState.ENGINE
            self.menu_top = TopLoop.prev(self.menu_top)
            text = self.dgttranslate.text(self.menu_top.value)

        elif self.state == MenuState.SYS_POWER:
            self.state = MenuState.SYS_THEME
            self.menu_system = SystemLoop.prev(self.menu_system)
            text = self.dgttranslate.text(self.menu_system.value)

        elif self.state == MenuState.SYS_POWER_SHUT_DOWN:
            self.state = MenuState.SYS_POWER_UPDT_ENGINES
            self.menu_system_power = PowerLoop.prev(self.menu_system_power)
            text = self.dgttranslate.text(self.menu_system_power.value)

        elif self.state == MenuState.SYS_POWER_UPDT_ENGINES:
            self.state = MenuState.SYS_POWER_UPDATE
            self.menu_system_power = PowerLoop.prev(self.menu_system_power)
            text = self.dgttranslate.text(self.menu_system_power.value)

        elif self.state == MenuState.SYS_POWER_UPDATE:
            self.state = MenuState.SYS_POWER_RESTART
            self.menu_system_power = PowerLoop.prev(self.menu_system_power)
            text = self.dgttranslate.text(self.menu_system_power.value)

        elif self.state == MenuState.SYS_POWER_RESTART:
            self.state = MenuState.SYS_POWER_EXIT
            self.menu_system_power = PowerLoop.prev(self.menu_system_power)
            text = self.dgttranslate.text(self.menu_system_power.value)

        elif self.state == MenuState.SYS_POWER_EXIT:
            self.state = MenuState.SYS_POWER_SHUT_DOWN
            self.menu_system_power = PowerLoop.prev(self.menu_system_power)
            text = self.dgttranslate.text(self.menu_system_power.value)

        elif self.state == MenuState.SYS_INFO:
            self.state = MenuState.SYS_POWER
            self.menu_system = SystemLoop.prev(self.menu_system)
            text = self.dgttranslate.text(self.menu_system.value)

        elif self.state == MenuState.SYS_INFO_VERS:
            self.state = MenuState.SYS_INFO_BATTERY
            self.menu_system_info = InfoLoop.prev(self.menu_system_info)
            text = self.dgttranslate.text(self.menu_system_info.value)

        elif self.state == MenuState.SYS_INFO_UPDATED:
            self.state = MenuState.SYS_INFO_VERS
            self.menu_system_info = InfoLoop.prev(self.menu_system_info)
            text = self.dgttranslate.text(self.menu_system_info.value)

        elif self.state == MenuState.SYS_INFO_GIT:
            self.state = MenuState.SYS_INFO_UPDATED
            self.menu_system_info = InfoLoop.prev(self.menu_system_info)
            text = self.dgttranslate.text(self.menu_system_info.value)

        elif self.state == MenuState.SYS_INFO_IP:
            self.state = MenuState.SYS_INFO_GIT
            self.menu_system_info = InfoLoop.prev(self.menu_system_info)
            text = self.dgttranslate.text(self.menu_system_info.value)

        elif self.state == MenuState.SYS_INFO_BATTERY:
            self.state = MenuState.SYS_INFO_IP
            self.menu_system_info = InfoLoop.prev(self.menu_system_info)
            text = self.dgttranslate.text(self.menu_system_info.value)

        elif self.state == MenuState.SYS_SOUND:
            self.state = MenuState.SYS_INFO
            self.menu_system = SystemLoop.prev(self.menu_system)
            text = self.dgttranslate.text(self.menu_system.value)

        elif self.state == MenuState.SYS_SOUND_BEEP:
            self.menu_system_sound = BeepLoop.prev(self.menu_system_sound)
            text = self.dgttranslate.text(self.menu_system_sound.value)

        elif self.state == MenuState.SYS_LANG:
            self.state = MenuState.SYS_SOUND
            self.menu_system = SystemLoop.prev(self.menu_system)
            text = self.dgttranslate.text(self.menu_system.value)

        elif self.state == MenuState.SYS_LANG_NAME:
            self.menu_system_language = LanguageLoop.prev(self.menu_system_language)
            text = self.dgttranslate.text(self.menu_system_language.value)

        elif self.state == MenuState.SYS_LOG:
            self.state = MenuState.SYS_LANG
            self.menu_system = SystemLoop.prev(self.menu_system)
            text = self.dgttranslate.text(self.menu_system.value)

        elif self.state == MenuState.SYS_VOICE:
            self.state = MenuState.SYS_LOG
            self.menu_system = SystemLoop.prev(self.menu_system)
            text = self.dgttranslate.text(self.menu_system.value)

        elif self.state == MenuState.SYS_VOICE_USER:
            self.state = MenuState.SYS_VOICE_COMP
            self.menu_system_voice = VoiceLoop.prev(self.menu_system_voice)
            text = self.dgttranslate.text(self.menu_system_voice.value)

        elif self.state == MenuState.SYS_VOICE_USER_MUTE:
            self.menu_system_voice_user_active = not self.menu_system_voice_user_active
            msg = "on" if self.menu_system_voice_user_active else "off"
            text = self.dgttranslate.text("B00_voice_" + msg)

        elif self.state == MenuState.SYS_VOICE_USER_MUTE_LANG:
            self.menu_system_voice_user_lang = (self.menu_system_voice_user_lang - 1) % len(self.voices_conf)
            vkey = self.voices_conf.keys()[self.menu_system_voice_user_lang]
            text = self.dgttranslate.text("B00_language_" + vkey + "_menu")  # voice using same as language

        elif self.state == MenuState.SYS_VOICE_USER_MUTE_LANG_SPEAK:
            vkey = self.voices_conf.keys()[self.menu_system_voice_user_lang]
            speakers = self.voices_conf[vkey]
            self.menu_system_voice_user_speak = (self.menu_system_voice_user_speak - 1) % len(speakers)
            text = self._get_current_speaker(speakers, self.menu_system_voice_user_speak)

        elif self.state == MenuState.SYS_VOICE_COMP:
            self.state = MenuState.SYS_VOICE_SPEED
            self.menu_system_voice = VoiceLoop.prev(self.menu_system_voice)
            text = self.dgttranslate.text(self.menu_system_voice.value)

        elif self.state == MenuState.SYS_VOICE_COMP_MUTE:
            self.menu_system_voice_comp_active = not self.menu_system_voice_comp_active
            msg = "on" if self.menu_system_voice_comp_active else "off"
            text = self.dgttranslate.text("B00_voice_" + msg)

        elif self.state == MenuState.SYS_VOICE_COMP_MUTE_LANG:
            self.menu_system_voice_comp_lang = (self.menu_system_voice_comp_lang - 1) % len(self.voices_conf)
            vkey = self.voices_conf.keys()[self.menu_system_voice_comp_lang]
            text = self.dgttranslate.text("B00_language_" + vkey + "_menu")  # voice using same as language

        elif self.state == MenuState.SYS_VOICE_COMP_MUTE_LANG_SPEAK:
            vkey = self.voices_conf.keys()[self.menu_system_voice_comp_lang]
            speakers = self.voices_conf[vkey]
            self.menu_system_voice_comp_speak = (self.menu_system_voice_comp_speak - 1) % len(speakers)
            text = self._get_current_speaker(speakers, self.menu_system_voice_comp_speak)

        elif self.state == MenuState.SYS_VOICE_SPEED:
            self.state = MenuState.SYS_VOICE_VOLUME
            self.menu_system_voice = VoiceLoop.prev(self.menu_system_voice)
            text = self.dgttranslate.text(self.menu_system_voice.value)

        elif self.state == MenuState.SYS_VOICE_SPEED_FACTOR:
            self.menu_system_voice_speedfactor = (self.menu_system_voice_speedfactor - 1) % 10
            text = self.dgttranslate.text("B00_voice_speed", str(self.menu_system_voice_speedfactor))

        elif self.state == MenuState.SYS_VOICE_VOLUME:
            self.state = MenuState.SYS_VOICE_USER
            self.menu_system_voice = VoiceLoop.prev(self.menu_system_voice)
            text = self.dgttranslate.text(self.menu_system_voice.value)

        elif self.state == MenuState.SYS_VOICE_VOLUME_FACTOR:
            self.menu_system_voice_volumefactor = (self.menu_system_voice_volumefactor - 1) % 21
            text = self.dgttranslate.text("B00_voice_volume", str(self.menu_system_voice_volumefactor))

        elif self.state == MenuState.SYS_DISP:
            self.state = MenuState.SYS_VOICE
            self.menu_system = SystemLoop.prev(self.menu_system)
            text = self.dgttranslate.text(self.menu_system.value)

        elif self.state == MenuState.SYS_DISP_CLOCKSIDE:
            self.state = MenuState.SYS_DISP_NOTATION
            self.menu_system_display = DisplayLoop.prev(self.menu_system_display)
            text = self.dgttranslate.text(self.menu_system_display.value)

        elif self.state == MenuState.SYS_DISP_CLOCKSIDE_LEFTRIGHT:
            if self.menu_system_display_clockside == "left":
                self.menu_system_display_clockside = "right"
                msg = "right"
            else:
                self.menu_system_display_clockside = "left"
                msg = "left"
            text = self.dgttranslate.text("B00_clockside_" + msg)

        elif self.state == MenuState.SYS_DISP_PONDER:
            self.state = MenuState.SYS_DISP_CLOCKSIDE
            self.menu_system_display = DisplayLoop.prev(self.menu_system_display)
            text = self.dgttranslate.text(self.menu_system_display.value)

        elif self.state == MenuState.SYS_DISP_PONDER_INTERVAL:
            self.menu_system_display_ponderinterval -= 1
            if self.menu_system_display_ponderinterval < 1:
                self.menu_system_display_ponderinterval = 8
            text = self.dgttranslate.text("B00_ponder_interval", str(self.menu_system_display_ponderinterval))

        elif self.state == MenuState.SYS_DISP_CONFIRM:
            self.state = MenuState.SYS_DISP_PONDER
            self.menu_system_display = DisplayLoop.prev(self.menu_system_display)
            text = self.dgttranslate.text(self.menu_system_display.value)

        elif self.state == MenuState.SYS_DISP_CONFIRM_YESNO:
            self.menu_system_display_confirm = not self.menu_system_display_confirm
            msg = "off" if self.menu_system_display_confirm else "on"
            text = self.dgttranslate.text("B00_confirm_" + msg)

        elif self.state == MenuState.SYS_DISP_ENGINENAME:
            self.state = MenuState.SYS_DISP_CONFIRM
            self.menu_system_display = DisplayLoop.prev(self.menu_system_display)
            text = self.dgttranslate.text(self.menu_system_display.value)

        elif self.state == MenuState.SYS_DISP_ENGINENAME_YESNO:
            self.menu_system_display_enginename = not self.menu_system_display_enginename
            msg = "on" if self.menu_system_display_enginename else "off"
            text = self.dgttranslate.text("B00_enginename_" + msg)

        elif self.state == MenuState.SYS_DISP_CAPITAL:
            self.state = MenuState.SYS_DISP_ENGINENAME
            self.menu_system_display = DisplayLoop.prev(self.menu_system_display)
            text = self.dgttranslate.text(self.menu_system_display.value)

        elif self.state == MenuState.SYS_DISP_CAPTIAL_YESNO:
            self.menu_system_display_capital = not self.menu_system_display_capital
            msg = "on" if self.menu_system_display_capital else "off"
            text = self.dgttranslate.text("B00_capital_" + msg)

        elif self.state == MenuState.SYS_DISP_NOTATION:
            self.state = MenuState.SYS_DISP_CAPITAL
            self.menu_system_display = DisplayLoop.prev(self.menu_system_display)
            text = self.dgttranslate.text(self.menu_system_display.value)

        elif self.state == MenuState.SYS_DISP_NOTATION_MOVE:
            self.menu_system_display_notation = not self.menu_system_display_notation
            msg = "long" if self.menu_system_display_notation else "short"
            text = self.dgttranslate.text("B00_notation_" + msg)

        elif self.state == MenuState.SYS_EBOARD:
            self.state = MenuState.SYS_DISP
            self.menu_system = SystemLoop.prev(self.menu_system)
            text = self.dgttranslate.text(self.menu_system.value)

        elif self.state == MenuState.SYS_EBOARD_TYPE:
            self.menu_system_eboard_type = EBoardLoop.prev(self.menu_system_eboard_type)
            text = self.dgttranslate.text(self.menu_system_eboard_type.value)

        elif self.state == MenuState.SYS_THEME:
            self.state = MenuState.SYS_EBOARD
            self.menu_system = SystemLoop.prev(self.menu_system)
            text = self.dgttranslate.text(self.menu_system.value)

        elif self.state == MenuState.SYS_THEME_TYPE:
            self.menu_system_theme_type = ThemeLoop.prev(self.menu_system_theme_type)
            text = self.dgttranslate.text(self.menu_system_theme_type.value)

        else:  # Default
            pass
        self.current_text = text
        return text

    def main_right(self):
        """Change the menu state after RIGHT action."""
        text = self.dgttranslate.text("Y00_errormenu")
        if self.state == MenuState.TOP:
            pass

        elif self.state == MenuState.GAME:
            self.state = MenuState.MODE
            self.menu_top = TopLoop.next(self.menu_top)
            text = self.dgttranslate.text(self.menu_top.value)

        elif self.state == MenuState.GAME_GAMEEND:
            self.state = MenuState.GAME_GAMESAVE
            self.menu_game = GameLoop.next(self.menu_game)
            text = self.dgttranslate.text(self.menu_game.value)

        elif self.state == MenuState.GAME_GAMEEND_WHITE_WINS:
            self.state = MenuState.GAME_GAMEEND_BLACK_WINS
            self.menu_game_end = GameEndLoop.next(self.menu_game_end)
            text = self.dgttranslate.text(self.menu_game_end.value)

        elif self.state == MenuState.GAME_GAMEEND_BLACK_WINS:
            self.state = MenuState.GAME_GAMEEND_DRAW
            self.menu_game_end = GameEndLoop.next(self.menu_game_end)
            text = self.dgttranslate.text(self.menu_game_end.value)

        elif self.state == MenuState.GAME_GAMEEND_DRAW:
            self.state = MenuState.GAME_GAMEEND_WHITE_WINS
            self.menu_game_end = GameEndLoop.next(self.menu_game_end)
            text = self.dgttranslate.text(self.menu_game_end.value)

        elif self.state == MenuState.GAME_GAMESAVE:
            self.state = MenuState.GAME_GAMEREAD
            self.menu_game = GameLoop.next(self.menu_game)
            text = self.dgttranslate.text(self.menu_game.value)

        elif self.state == MenuState.GAME_GAMESAVE_GAME1:
            self.state = MenuState.GAME_GAMESAVE_GAME2
            self.menu_game_save = GameSaveLoop.next(self.menu_game_save)
            text = self.dgttranslate.text(self.menu_game_save.value)

        elif self.state == MenuState.GAME_GAMESAVE_GAME2:
            self.state = MenuState.GAME_GAMESAVE_GAME3
            self.menu_game_save = GameSaveLoop.next(self.menu_game_save)
            text = self.dgttranslate.text(self.menu_game_save.value)

        elif self.state == MenuState.GAME_GAMESAVE_GAME3:
            self.state = MenuState.GAME_GAMESAVE_GAME1
            self.menu_game_save = GameSaveLoop.next(self.menu_game_save)
            text = self.dgttranslate.text(self.menu_game_save.value)

        elif self.state == MenuState.GAME_GAMEREAD:
            self.state = MenuState.GAME_GAMEALTMOVE
            self.menu_game = GameLoop.next(self.menu_game)
            text = self.dgttranslate.text(self.menu_game.value)

        elif self.state == MenuState.GAME_GAMEREAD_GAMELAST:
            self.state = MenuState.GAME_GAMEREAD_GAME1
            self.menu_game_read = GameReadLoop.next(self.menu_game_read)
            text = self.dgttranslate.text(self.menu_game_read.value)

        elif self.state == MenuState.GAME_GAMEREAD_GAME1:
            self.state = MenuState.GAME_GAMEREAD_GAME2
            self.menu_game_read = GameReadLoop.next(self.menu_game_read)
            text = self.dgttranslate.text(self.menu_game_read.value)

        elif self.state == MenuState.GAME_GAMEREAD_GAME2:
            self.state = MenuState.GAME_GAMEREAD_GAME3
            self.menu_game_read = GameReadLoop.next(self.menu_game_read)
            text = self.dgttranslate.text(self.menu_game_read.value)

        elif self.state == MenuState.GAME_GAMEREAD_GAME3:
            self.state = MenuState.GAME_GAMEREAD_GAMELAST
            self.menu_game_read = GameReadLoop.next(self.menu_game_read)
            text = self.dgttranslate.text(self.menu_game_read.value)

        elif self.state == MenuState.GAME_GAMECONTLAST:
            self.state = MenuState.GAME_GAMENEW
            self.menu_game = GameLoop.next(self.menu_game)
            text = self.dgttranslate.text(self.menu_game.value)

        elif self.state == MenuState.GAME_GAMENEW:
            self.state = MenuState.GAME_GAMETAKEBACK
            self.menu_game = GameLoop.next(self.menu_game)
            text = self.dgttranslate.text(self.menu_game.value)

        elif self.state == MenuState.GAME_GAMENEW_YESNO:
            self.menu_game_new = not self.menu_game_new
            msg = "yes" if self.menu_game_new else "no"
            text = self.dgttranslate.text("B00_game_new_" + msg)

        elif self.state == MenuState.GAME_GAMETAKEBACK:
            self.state = MenuState.GAME_GAMEEND
            self.menu_game = GameLoop.next(self.menu_game)
            text = self.dgttranslate.text(self.menu_game.value)

        elif self.state == MenuState.GAME_GAMEALTMOVE:
            self.state = MenuState.GAME_GAMECONTLAST
            self.menu_game = GameLoop.next(self.menu_game)
            text = self.dgttranslate.text(self.menu_game.value)

        elif self.state == MenuState.GAME_GAMEALTMOVE_ONOFF:
            self.menu_game_altmove = not self.menu_game_altmove
            msg = "on" if self.menu_game_altmove else "off"
            text = self.dgttranslate.text("B00_game_altmove_" + msg)

        elif self.state == MenuState.GAME_GAMECONTLAST_ONOFF:
            self.menu_game_contlast = not self.menu_game_contlast
            msg = "on" if self.menu_game_contlast else "off"
            text = self.dgttranslate.text("B00_game_contlast_" + msg)

        elif self.state == MenuState.PICOTUTOR:
            self.state = MenuState.GAME
            self.menu_top = TopLoop.next(self.menu_top)
            text = self.dgttranslate.text(self.menu_top.value)

        elif self.state == MenuState.PICOTUTOR_PICOWATCHER:
            self.state = MenuState.PICOTUTOR_PICOCOACH
            self.menu_picotutor = PicoTutor.COACH
            text = self.dgttranslate.text(self.menu_picotutor.value)

        elif self.state == MenuState.PICOTUTOR_PICOWATCHER_ONOFF:
            self.menu_picotutor_picowatcher = not self.menu_picotutor_picowatcher
            msg = "on" if self.menu_picotutor_picowatcher else "off"
            text = self.dgttranslate.text("B00_picowatcher_" + msg)

        elif self.state == MenuState.PICOTUTOR_PICOCOACH:
            self.state = MenuState.PICOTUTOR_PICOEXPLORER
            self.menu_picotutor = PicoTutor.EXPLORER
            text = self.dgttranslate.text(self.menu_picotutor.value)

        elif self.state == MenuState.PICOTUTOR_PICOCOACH_ON:
            self.state = MenuState.PICOTUTOR_PICOCOACH_LIFT
            self.menu_picotutor_picocoach = PicoCoachLoop.next(self.menu_picotutor_picocoach)
            text = self.dgttranslate.text(self.menu_picotutor_picocoach.value)

        elif self.state == MenuState.PICOTUTOR_PICOCOACH_LIFT:
            self.state = MenuState.PICOTUTOR_PICOCOACH_OFF
            self.menu_picotutor_picocoach = PicoCoachLoop.next(self.menu_picotutor_picocoach)
            text = self.dgttranslate.text(self.menu_picotutor_picocoach.value)

        elif self.state == MenuState.PICOTUTOR_PICOCOACH_OFF:
            self.state = MenuState.PICOTUTOR_PICOCOACH_ON
            self.menu_picotutor_picocoach = PicoCoachLoop.next(self.menu_picotutor_picocoach)
            text = self.dgttranslate.text(self.menu_picotutor_picocoach.value)

        elif self.state == MenuState.PICOTUTOR_PICOEXPLORER:
            self.state = MenuState.PICOTUTOR_PICOCOMMENT
            self.menu_picotutor = PicoTutor.COMMENT
            text = self.dgttranslate.text(self.menu_picotutor.value)

        elif self.state == MenuState.PICOTUTOR_PICOEXPLORER_ONOFF:
            self.menu_picotutor_picoexplorer = not self.menu_picotutor_picoexplorer
            msg = "on" if self.menu_picotutor_picoexplorer else "off"
            text = self.dgttranslate.text("B00_picoexplorer_" + msg)

        elif self.state == MenuState.PICOTUTOR_PICOCOMMENT:
            self.state = MenuState.PICOTUTOR_PICOCOMPROB
            self.menu_picotutor = PicoTutor.COM_PROB
            text = self.dgttranslate.text(self.menu_picotutor.value)

        elif self.state == MenuState.PICOTUTOR_PICOCOMMENT_OFF:
            self.state = MenuState.PICOTUTOR_PICOCOMMENT_ON_ENG
            self.menu_picotutor_picocomment = PicoCommentLoop.next(self.menu_picotutor_picocomment)
            text = self.dgttranslate.text(self.menu_picotutor_picocomment.value)

        elif self.state == MenuState.PICOTUTOR_PICOCOMMENT_ON_ENG:
            self.state = MenuState.PICOTUTOR_PICOCOMMENT_ON_ALL
            self.menu_picotutor_picocomment = PicoCommentLoop.next(self.menu_picotutor_picocomment)
            text = self.dgttranslate.text(self.menu_picotutor_picocomment.value)

        elif self.state == MenuState.PICOTUTOR_PICOCOMMENT_ON_ALL:
            self.state = MenuState.PICOTUTOR_PICOCOMMENT_OFF
            self.menu_picotutor_picocomment = PicoCommentLoop.next(self.menu_picotutor_picocomment)
            text = self.dgttranslate.text(self.menu_picotutor_picocomment.value)

        elif self.state == MenuState.PICOTUTOR_PICOCOMPROB:
            self.state = MenuState.PICOTUTOR_PICOWATCHER
            self.menu_picotutor = PicoTutor.WATCHER
            text = self.dgttranslate.text(self.menu_picotutor.value)

        elif self.state == MenuState.PICOTUTOR_PICOCOMPROB_LIST:
            self.menu_picocomment_prob_idx = (self.menu_picocomment_prob_idx + 1) % len(self.com_prob_list)
            self.menu_picocomment_prob_list = self.com_prob_list[self.menu_picocomment_prob_idx]
            l_prob = self.menu_picocomment_prob_list + "%"
            text = self.dgttranslate.text("B00_picocom_prob_list", l_prob)

        elif self.state == MenuState.MODE:
            self.state = MenuState.POS
            self.menu_top = TopLoop.next(self.menu_top)
            text = self.dgttranslate.text(self.menu_top.value)

        elif self.state == MenuState.MODE_TYPE:
            self.menu_mode = ModeLoop.next(self.menu_mode)
            text = self.dgttranslate.text(self.menu_mode.value)

        elif self.state == MenuState.POS:
            self.state = MenuState.TIME
            self.menu_top = TopLoop.next(self.menu_top)
            text = self.dgttranslate.text(self.menu_top.value)

        elif self.state == MenuState.POS_COL:
            self.menu_position_whitetomove = not self.menu_position_whitetomove
            text = self.dgttranslate.text("B00_sidewhite" if self.menu_position_whitetomove else "B00_sideblack")

        elif self.state == MenuState.POS_REV:
            self.menu_position_reverse = not self.menu_position_reverse
            text = self.dgttranslate.text("B00_bw" if self.menu_position_reverse else "B00_wb")

        elif self.state == MenuState.POS_UCI:
            if self.engine_has_960:
                self.menu_position_uci960 = not self.menu_position_uci960
                text = self.dgttranslate.text("B00_960yes" if self.menu_position_uci960 else "B00_960no")
            else:
                text = self.dgttranslate.text("Y10_error960")

        elif self.state == MenuState.POS_READ:
            text = self.dgttranslate.text("B10_nofunction")

        elif self.state == MenuState.TIME:
            self.state = MenuState.BOOK
            self.menu_top = TopLoop.next(self.menu_top)
            text = self.dgttranslate.text(self.menu_top.value)

        elif self.state == MenuState.TIME_BLITZ:
            self.state = MenuState.TIME_FISCH
            self.menu_time_mode = TimeModeLoop.next(self.menu_time_mode)
            text = self.dgttranslate.text(self.menu_time_mode.value)

        elif self.state == MenuState.TIME_BLITZ_CTRL:
            self.menu_time_blitz = (self.menu_time_blitz + 1) % len(self.tc_blitz_map)
            text = self.dgttranslate.text("B00_tc_blitz", self.tc_blitz_list[self.menu_time_blitz])

        elif self.state == MenuState.TIME_FISCH:
            self.state = MenuState.TIME_TOURN
            self.menu_time_mode = TimeModeLoop.next(self.menu_time_mode)
            text = self.dgttranslate.text(self.menu_time_mode.value)

        elif self.state == MenuState.TIME_FISCH_CTRL:
            self.menu_time_fisch = (self.menu_time_fisch + 1) % len(self.tc_fisch_map)
            text = self.dgttranslate.text("B00_tc_fisch", self.tc_fisch_list[self.menu_time_fisch])

        elif self.state == MenuState.TIME_FIXED:
            self.state = MenuState.TIME_BLITZ
            self.menu_time_mode = TimeModeLoop.next(self.menu_time_mode)
            text = self.dgttranslate.text(self.menu_time_mode.value)

        elif self.state == MenuState.TIME_FIXED_CTRL:
            self.menu_time_fixed = (self.menu_time_fixed + 1) % len(self.tc_fixed_map)
            text = self.dgttranslate.text("B00_tc_fixed", self.tc_fixed_list[self.menu_time_fixed])

        elif self.state == MenuState.TIME_TOURN:
            self.state = MenuState.TIME_DEPTH
            self.menu_time_mode = TimeModeLoop.next(self.menu_time_mode)
            text = self.dgttranslate.text(self.menu_time_mode.value)

        elif self.state == MenuState.TIME_TOURN_CTRL:
            self.menu_time_tourn = (self.menu_time_tourn + 1) % len(self.tc_tournaments)
            text = self.dgttranslate.text("B00_tc_tourn", self.tc_tourn_list[self.menu_time_tourn])

        elif self.state == MenuState.TIME_DEPTH:
            self.state = MenuState.TIME_NODE
            self.menu_time_mode = TimeModeLoop.next(self.menu_time_mode)
            text = self.dgttranslate.text(self.menu_time_mode.value)

        elif self.state == MenuState.TIME_DEPTH_CTRL:
            self.menu_time_depth = (self.menu_time_depth + 1) % len(self.tc_depths)
            text = self.dgttranslate.text("B00_tc_depth", self.tc_depth_list[self.menu_time_depth])

        elif self.state == MenuState.TIME_NODE:
            self.state = MenuState.TIME_FIXED
            self.menu_time_mode = TimeModeLoop.next(self.menu_time_mode)
            text = self.dgttranslate.text(self.menu_time_mode.value)

        elif self.state == MenuState.TIME_NODE_CTRL:
            self.menu_time_node = (self.menu_time_node + 1) % len(self.tc_nodes)
            text = self.dgttranslate.text("B00_tc_node", self.tc_node_list[self.menu_time_node])

        elif self.state == MenuState.BOOK:
            self.state = MenuState.ENGINE
            self.menu_top = TopLoop.next(self.menu_top)
            text = self.dgttranslate.text(self.menu_top.value)

        elif self.state == MenuState.BOOK_NAME:
            self.menu_book = (self.menu_book + 1) % len(self.all_books)
            text = self._get_current_book_name()

        elif self.state == MenuState.ENGINE:
            self.state = MenuState.SYS
            self.menu_top = TopLoop.next(self.menu_top)
            text = self.dgttranslate.text(self.menu_top.value)

        elif self.state == MenuState.ENG_MODERN:
            self.state = MenuState.ENG_RETRO
            self.menu_engine = EngineTopLoop.next(self.menu_engine)
            text = self.dgttranslate.text(self.menu_engine.value)

        elif self.state == MenuState.ENG_MODERN_NAME:
            self.menu_modern_engine_index = (self.menu_modern_engine_index + 1) % len(EngineProvider.modern_engines)
            text = self._get_current_modern_engine_name()

        elif self.state == MenuState.ENG_MODERN_NAME_LEVEL:
            level_dict = EngineProvider.modern_engines[self.menu_modern_engine_index]["level_dict"]
            self.menu_modern_engine_level = (self.menu_modern_engine_level + 1) % len(level_dict)
            msg = sorted(level_dict)[self.menu_modern_engine_level]
            text = self.dgttranslate.text("B00_level", msg)

        elif self.state == MenuState.ENG_RETRO:
            self.state = MenuState.RETROSETTINGS
            self.menu_engine = EngineTopLoop.next(self.menu_engine)
            text = self.dgttranslate.text(self.menu_engine.value)

        elif self.state == MenuState.ENG_RETRO_NAME:
            self.menu_retro_engine_index = (self.menu_retro_engine_index + 1) % len(EngineProvider.retro_engines)
            text = self._get_current_retro_engine_name()

        elif self.state == MenuState.ENG_RETRO_NAME_LEVEL:
            retro_level_dict = EngineProvider.retro_engines[self.menu_retro_engine_index]["level_dict"]
            self.menu_retro_engine_level = (self.menu_retro_engine_level + 1) % len(retro_level_dict)
            msg = sorted(retro_level_dict)[self.menu_retro_engine_level]
            text = self.dgttranslate.text("B00_level", msg)

        elif self.state == MenuState.ENG_FAV:
            self.state = MenuState.ENG_MODERN
            self.menu_engine = EngineTopLoop.next(self.menu_engine)
            text = self.dgttranslate.text(self.menu_engine.value)

        elif self.state == MenuState.ENG_FAV_NAME:
            self.menu_fav_engine_index = (self.menu_fav_engine_index + 1) % len(EngineProvider.favorite_engines)
            text = self._get_current_fav_engine_name()

        elif self.state == MenuState.ENG_FAV_NAME_LEVEL:
            retro_level_dict = EngineProvider.favorite_engines[self.menu_fav_engine_index]["level_dict"]
            self.menu_fav_engine_level = (self.menu_fav_engine_level + 1) % len(retro_level_dict)
            msg = sorted(retro_level_dict)[self.menu_fav_engine_level]
            text = self.dgttranslate.text("B00_level", msg)

        elif self.state == MenuState.RETROSETTINGS:
            self.state = MenuState.ENG_FAV
            self.menu_engine = EngineTopLoop.next(self.menu_engine)
            text = self.dgttranslate.text(self.menu_engine.value)

        elif self.state == MenuState.RETROSETTINGS_RETROSOUND:
            self.state = MenuState.RETROSETTINGS_RETRODISPLAY
            self.menu_engine_retrosettings = EngineRetroSettingsLoop.next(self.menu_engine_retrosettings)
            text = self.dgttranslate.text(self.menu_engine_retrosettings.value)

        elif self.state == MenuState.RETROSETTINGS_RETROSOUND_ONOFF:
            self.engine_retrosound_onoff = not self.engine_retrosound_onoff
            msg = "on" if self.engine_retrosound_onoff else "off"
            text = self.dgttranslate.text("B00_engine_retrosound_" + msg)

        elif self.state == MenuState.RETROSETTINGS_RETRODISPLAY:
            self.state = MenuState.RETROSETTINGS_RETROINFO
            self.menu_engine_retrosettings = EngineRetroSettingsLoop.next(self.menu_engine_retrosettings)
            text = self.dgttranslate.text(self.menu_engine_retrosettings.value)

        elif self.state == MenuState.RETROSETTINGS_RETRODISPLAY_ONOFF:
            self.engine_retrodisplay_onoff = not self.engine_retrodisplay_onoff
            msg = "on" if self.engine_retrodisplay_onoff else "off"
            text = self.dgttranslate.text("B00_engine_retrodisplay_" + msg)

        elif self.state == MenuState.RETROSETTINGS_RETROWINDOW:
            self.state = MenuState.RETROSETTINGS_RETROSPEED
            self.menu_engine_retrosettings = EngineRetroSettingsLoop.next(self.menu_engine_retrosettings)
            text = self.dgttranslate.text(self.menu_engine_retrosettings.value)

        elif self.state == MenuState.RETROSETTINGS_RETROSPEED:
            self.state = MenuState.RETROSETTINGS_RETROSOUND
            self.menu_engine_retrosettings = EngineRetroSettingsLoop.next(self.menu_engine_retrosettings)
            text = self.dgttranslate.text(self.menu_engine_retrosettings.value)

        elif self.state == MenuState.RETROSETTINGS_RETROINFO:
            self.state = MenuState.RETROSETTINGS_RETROWINDOW
            self.menu_engine_retrosettings = EngineRetroSettingsLoop.next(self.menu_engine_retrosettings)
            text = self.dgttranslate.text(self.menu_engine_retrosettings.value)

        elif self.state == MenuState.RETROSETTINGS_RETROINFO_SHOW:
            text = self.enter_retroinfo_show_menu()

        elif self.state == MenuState.RETROSETTINGS_RETROSPEED_FACTOR:
            l_speed = ""
            self.menu_engine_retrospeed_idx = (self.menu_engine_retrospeed_idx + 1) % len(self.retrospeed_list)
            if self.retrospeed_list[self.menu_engine_retrospeed_idx] == "max.":
                l_speed = self.retrospeed_list[self.menu_engine_retrospeed_idx]
            else:
                l_speed = self.retrospeed_list[self.menu_engine_retrospeed_idx] + "%"
            text = self.dgttranslate.text("B00_retrospeed", l_speed)

        elif self.state == MenuState.SYS:
            self.state = MenuState.PICOTUTOR
            self.menu_top = TopLoop.next(self.menu_top)
            text = self.dgttranslate.text(self.menu_top.value)

        elif self.state == MenuState.SYS_POWER:
            self.state = MenuState.SYS_INFO
            self.menu_system = SystemLoop.next(self.menu_system)
            text = self.dgttranslate.text(self.menu_system.value)

        elif self.state == MenuState.SYS_POWER_SHUT_DOWN:
            self.state = MenuState.SYS_POWER_EXIT
            self.menu_system_power = PowerLoop.next(self.menu_system_power)
            text = self.dgttranslate.text(self.menu_system_power.value)

        elif self.state == MenuState.SYS_POWER_RESTART:
            self.state = MenuState.SYS_POWER_UPDATE
            self.menu_system_power = PowerLoop.next(self.menu_system_power)
            text = self.dgttranslate.text(self.menu_system_power.value)

        elif self.state == MenuState.SYS_POWER_UPDATE:
            self.state = MenuState.SYS_POWER_UPDT_ENGINES
            self.menu_system_power = PowerLoop.next(self.menu_system_power)
            text = self.dgttranslate.text(self.menu_system_power.value)

        elif self.state == MenuState.SYS_POWER_UPDT_ENGINES:
            self.state = MenuState.SYS_POWER_SHUT_DOWN
            self.menu_system_power = PowerLoop.next(self.menu_system_power)
            text = self.dgttranslate.text(self.menu_system_power.value)

        elif self.state == MenuState.SYS_POWER_EXIT:
            self.state = MenuState.SYS_POWER_RESTART
            self.menu_system_power = PowerLoop.next(self.menu_system_power)
            text = self.dgttranslate.text(self.menu_system_power.value)

        elif self.state == MenuState.SYS_INFO:
            self.state = MenuState.SYS_SOUND
            self.menu_system = SystemLoop.next(self.menu_system)
            text = self.dgttranslate.text(self.menu_system.value)

        elif self.state == MenuState.SYS_INFO_VERS:
            self.state = MenuState.SYS_INFO_UPDATED
            self.menu_system_info = InfoLoop.next(self.menu_system_info)
            text = self.dgttranslate.text(self.menu_system_info.value)

        elif self.state == MenuState.SYS_INFO_UPDATED:
            self.state = MenuState.SYS_INFO_GIT
            self.menu_system_info = InfoLoop.next(self.menu_system_info)
            text = self.dgttranslate.text(self.menu_system_info.value)

        elif self.state == MenuState.SYS_INFO_GIT:
            self.state = MenuState.SYS_INFO_IP
            self.menu_system_info = InfoLoop.next(self.menu_system_info)
            text = self.dgttranslate.text(self.menu_system_info.value)

        elif self.state == MenuState.SYS_INFO_IP:
            self.state = MenuState.SYS_INFO_BATTERY
            self.menu_system_info = InfoLoop.next(self.menu_system_info)
            text = self.dgttranslate.text(self.menu_system_info.value)

        elif self.state == MenuState.SYS_INFO_BATTERY:
            self.state = MenuState.SYS_INFO_VERS
            self.menu_system_info = InfoLoop.next(self.menu_system_info)
            text = self.dgttranslate.text(self.menu_system_info.value)

        elif self.state == MenuState.SYS_SOUND:
            self.state = MenuState.SYS_LANG
            self.menu_system = SystemLoop.next(self.menu_system)
            text = self.dgttranslate.text(self.menu_system.value)

        elif self.state == MenuState.SYS_SOUND_BEEP:
            self.menu_system_sound = BeepLoop.next(self.menu_system_sound)
            text = self.dgttranslate.text(self.menu_system_sound.value)

        elif self.state == MenuState.SYS_LANG:
            self.state = MenuState.SYS_LOG
            self.menu_system = SystemLoop.next(self.menu_system)
            text = self.dgttranslate.text(self.menu_system.value)

        elif self.state == MenuState.SYS_LANG_NAME:
            self.menu_system_language = LanguageLoop.next(self.menu_system_language)
            text = self.dgttranslate.text(self.menu_system_language.value)

        elif self.state == MenuState.SYS_LOG:
            self.state = MenuState.SYS_VOICE
            self.menu_system = SystemLoop.next(self.menu_system)
            text = self.dgttranslate.text(self.menu_system.value)

        elif self.state == MenuState.SYS_VOICE:
            self.state = MenuState.SYS_DISP
            self.menu_system = SystemLoop.next(self.menu_system)
            text = self.dgttranslate.text(self.menu_system.value)

        elif self.state == MenuState.SYS_VOICE_USER:
            self.state = MenuState.SYS_VOICE_VOLUME
            self.menu_system_voice = VoiceLoop.next(self.menu_system_voice)
            text = self.dgttranslate.text(self.menu_system_voice.value)

        elif self.state == MenuState.SYS_VOICE_USER_MUTE:
            self.menu_system_voice_user_active = not self.menu_system_voice_user_active
            msg = "on" if self.menu_system_voice_user_active else "off"
            text = self.dgttranslate.text("B00_voice_" + msg)

        elif self.state == MenuState.SYS_VOICE_USER_MUTE_LANG:
            self.menu_system_voice_user_lang = (self.menu_system_voice_user_lang + 1) % len(self.voices_conf)
            vkey = self.voices_conf.keys()[self.menu_system_voice_user_lang]
            text = self.dgttranslate.text("B00_language_" + vkey + "_menu")  # voice using same as language

        elif self.state == MenuState.SYS_VOICE_USER_MUTE_LANG_SPEAK:
            vkey = self.voices_conf.keys()[self.menu_system_voice_user_lang]
            speakers = self.voices_conf[vkey]
            self.menu_system_voice_user_speak = (self.menu_system_voice_user_speak + 1) % len(speakers)
            text = self._get_current_speaker(speakers, self.menu_system_voice_user_speak)

        elif self.state == MenuState.SYS_VOICE_COMP:
            self.state = MenuState.SYS_VOICE_USER
            self.menu_system_voice = VoiceLoop.next(self.menu_system_voice)
            text = self.dgttranslate.text(self.menu_system_voice.value)

        elif self.state == MenuState.SYS_VOICE_COMP_MUTE:
            self.menu_system_voice_comp_active = not self.menu_system_voice_comp_active
            msg = "on" if self.menu_system_voice_comp_active else "off"
            text = self.dgttranslate.text("B00_voice_" + msg)

        elif self.state == MenuState.SYS_VOICE_COMP_MUTE_LANG:
            self.menu_system_voice_comp_lang = (self.menu_system_voice_comp_lang + 1) % len(self.voices_conf)
            vkey = self.voices_conf.keys()[self.menu_system_voice_comp_lang]
            text = self.dgttranslate.text("B00_language_" + vkey + "_menu")  # voice using same as language

        elif self.state == MenuState.SYS_VOICE_COMP_MUTE_LANG_SPEAK:
            vkey = self.voices_conf.keys()[self.menu_system_voice_comp_lang]
            speakers = self.voices_conf[vkey]
            self.menu_system_voice_comp_speak = (self.menu_system_voice_comp_speak + 1) % len(speakers)
            text = self._get_current_speaker(speakers, self.menu_system_voice_comp_speak)

        elif self.state == MenuState.SYS_VOICE_SPEED:
            self.state = MenuState.SYS_VOICE_COMP
            self.menu_system_voice = VoiceLoop.next(self.menu_system_voice)
            text = self.dgttranslate.text(self.menu_system_voice.value)

        elif self.state == MenuState.SYS_VOICE_SPEED_FACTOR:
            self.menu_system_voice_speedfactor = (self.menu_system_voice_speedfactor + 1) % 10
            text = self.dgttranslate.text("B00_voice_speed", str(self.menu_system_voice_speedfactor))

        elif self.state == MenuState.SYS_VOICE_VOLUME:
            self.state = MenuState.SYS_VOICE_SPEED
            self.menu_system_voice = VoiceLoop.next(self.menu_system_voice)
            text = self.dgttranslate.text(self.menu_system_voice.value)

        elif self.state == MenuState.SYS_VOICE_VOLUME_FACTOR:
            self.menu_system_voice_volumefactor = (self.menu_system_voice_volumefactor + 1) % 21
            text = self.dgttranslate.text("B00_voice_volume", str(self.menu_system_voice_volumefactor))

        elif self.state == MenuState.SYS_DISP:
            self.state = MenuState.SYS_EBOARD
            self.menu_system = SystemLoop.next(self.menu_system)
            text = self.dgttranslate.text(self.menu_system.value)

        elif self.state == MenuState.SYS_DISP_CLOCKSIDE:
            self.state = MenuState.SYS_DISP_PONDER
            self.menu_system_display = DisplayLoop.next(self.menu_system_display)
            text = self.dgttranslate.text(self.menu_system_display.value)

        elif self.state == MenuState.SYS_DISP_CLOCKSIDE_LEFTRIGHT:
            if self.menu_system_display_clockside == "left":
                self.menu_system_display_clockside = "right"
                msg = "right"
            else:
                self.menu_system_display_clockside = "left"
                msg = "left"
            text = self.dgttranslate.text("B00_clockside_" + msg)

        elif self.state == MenuState.SYS_DISP_PONDER:
            self.state = MenuState.SYS_DISP_CONFIRM
            self.menu_system_display = DisplayLoop.next(self.menu_system_display)
            text = self.dgttranslate.text(self.menu_system_display.value)

        elif self.state == MenuState.SYS_DISP_PONDER_INTERVAL:
            self.menu_system_display_ponderinterval += 1
            if self.menu_system_display_ponderinterval > 8:
                self.menu_system_display_ponderinterval = 1
            text = self.dgttranslate.text("B00_ponder_interval", str(self.menu_system_display_ponderinterval))

        elif self.state == MenuState.SYS_DISP_CONFIRM:
            self.state = MenuState.SYS_DISP_ENGINENAME
            self.menu_system_display = DisplayLoop.next(self.menu_system_display)
            text = self.dgttranslate.text(self.menu_system_display.value)

        elif self.state == MenuState.SYS_DISP_CONFIRM_YESNO:
            self.menu_system_display_confirm = not self.menu_system_display_confirm
            msg = "off" if self.menu_system_display_confirm else "on"
            text = self.dgttranslate.text("B00_confirm_" + msg)

        elif self.state == MenuState.SYS_DISP_ENGINENAME:
            self.state = MenuState.SYS_DISP_CAPITAL
            self.menu_system_display = DisplayLoop.next(self.menu_system_display)
            text = self.dgttranslate.text(self.menu_system_display.value)

        elif self.state == MenuState.SYS_DISP_ENGINENAME_YESNO:
            self.menu_system_display_enginename = not self.menu_system_display_enginename
            msg = "on" if self.menu_system_display_enginename else "off"
            text = self.dgttranslate.text("B00_enginename_" + msg)

        elif self.state == MenuState.SYS_DISP_CAPITAL:
            self.state = MenuState.SYS_DISP_NOTATION
            self.menu_system_display = DisplayLoop.next(self.menu_system_display)
            text = self.dgttranslate.text(self.menu_system_display.value)

        elif self.state == MenuState.SYS_DISP_CAPTIAL_YESNO:
            self.menu_system_display_capital = not self.menu_system_display_capital
            msg = "on" if self.menu_system_display_capital else "off"
            text = self.dgttranslate.text("B00_capital_" + msg)

        elif self.state == MenuState.SYS_DISP_NOTATION:
            self.state = MenuState.SYS_DISP_CLOCKSIDE
            self.menu_system_display = DisplayLoop.next(self.menu_system_display)
            text = self.dgttranslate.text(self.menu_system_display.value)

        elif self.state == MenuState.SYS_DISP_NOTATION_MOVE:
            self.menu_system_display_notation = not self.menu_system_display_notation
            msg = "long" if self.menu_system_display_notation else "short"
            text = self.dgttranslate.text("B00_notation_" + msg)

        elif self.state == MenuState.SYS_EBOARD:
            self.state = MenuState.SYS_THEME
            self.menu_system = SystemLoop.next(self.menu_system)
            text = self.dgttranslate.text(self.menu_system.value)

        elif self.state == MenuState.SYS_EBOARD_TYPE:
            self.menu_system_eboard_type = EBoardLoop.next(self.menu_system_eboard_type)
            text = self.dgttranslate.text(self.menu_system_eboard_type.value)

        elif self.state == MenuState.SYS_THEME:
            self.state = MenuState.SYS_POWER
            self.menu_system = SystemLoop.next(self.menu_system)
            text = self.dgttranslate.text(self.menu_system.value)

        elif self.state == MenuState.SYS_THEME_TYPE:
            self.menu_system_theme_type = ThemeLoop.next(self.menu_system_theme_type)
            text = self.dgttranslate.text(self.menu_system_theme_type.value)

        else:  # Default
            pass
        self.current_text = text
        return text

    def main_middle(self, dev):
        """Change the menu state after MIDDLE action."""

        def _exit_position():
            self.state = MenuState.POS_READ
            return self.main_down()

        if self.inside_picochess_time(dev):
            text = self.updt_middle(dev)
        else:
            text = self.dgttranslate.text("B00_nofunction")
            if False:  # switch-case
                pass
            elif self.state == MenuState.POS:
                text = _exit_position()

            elif self.state == MenuState.POS_COL:
                text = _exit_position()

            elif self.state == MenuState.POS_REV:
                text = _exit_position()

            elif self.state == MenuState.POS_UCI:
                text = _exit_position()

            elif self.state == MenuState.POS_READ:
                text = _exit_position()

            else:  # Default
                pass
        self.current_text = text
        return text

    def updt_middle(self, dev):
        """Change the menu state after MIDDLE action."""
        self.updt_devs.add(dev)
        text = self.dgttranslate.text("B00_updt_version", self.updt_tags[self.updt_version][1], devs=self.updt_devs)
        text.rd = ClockIcons.DOT
        logger.debug("enter update menu dev: %s", dev)
        self.updt_top = True
        return text

    def updt_right(self):
        """Change the menu state after RIGHT action."""
        self.updt_version = (self.updt_version + 1) % len(self.updt_tags)
        text = self.dgttranslate.text("B00_updt_version", self.updt_tags[self.updt_version][1], devs=self.updt_devs)
        text.rd = ClockIcons.DOT
        return text

    def updt_left(self):
        """Change the menu state after LEFT action."""
        self.updt_version = (self.updt_version - 1) % len(self.updt_tags)
        text = self.dgttranslate.text("B00_updt_version", self.updt_tags[self.updt_version][1], devs=self.updt_devs)
        text.rd = ClockIcons.DOT
        return text

    def updt_down(self, dev):
        """Change the menu state after DOWN action."""
        logger.debug("leave update menu dev: %s", dev)
        self.updt_top = False
        self.updt_devs.discard(dev)
        self.enter_top_menu()
        return self.updt_tags[self.updt_version][0]

    def updt_up(self, dev):
        """Change the menu state after UP action."""
        logger.debug("leave update menu dev: %s", dev)
        self.updt_top = False
        self.updt_devs.discard(dev)
        text = self.enter_top_menu()
        return text

    def inside_main_menu(self):
        """Check if currently inside the menu."""
        return self.state != MenuState.TOP

    def get_current_text(self):
        """Return the current text."""
        return self.current_text
