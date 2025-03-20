import os

import unittest
from unittest.mock import patch

from dgt.menu import DgtMenu, MenuState
from dgt.translate import DgtTranslate
from dgt.util import PicoComment, EBoard
from uci.read import read_engine_ini
from uci.engine_provider import EngineProvider


class TestDgtMenu(unittest.TestCase):
    @patch("subprocess.run")
    def create_menu(self, machine_mock, _):
        machine_mock.return_value = ".." + os.sep + "tests"  # return the tests path as the platform engine path
        EngineProvider.modern_engines = read_engine_ini(filename="engines.ini")
        EngineProvider.retro_engines = read_engine_ini(filename="retro.ini")
        EngineProvider.favorite_engines = read_engine_ini(filename="favorites.ini")
        EngineProvider.installed_engines = list(
            EngineProvider.modern_engines + EngineProvider.retro_engines + EngineProvider.favorite_engines
        )

        trans = DgtTranslate("none", 0, "en", "version")
        menu = DgtMenu(
            clockside="",
            disable_confirm=False,
            ponder_interval=0,
            user_voice="",
            comp_voice="",
            speed_voice=0,
            enable_capital_letters=False,
            disable_short_move=False,
            log_file="",
            engine_server=None,
            rol_disp_norm=False,
            volume_voice=0,
            board_type=EBoard.DGT,
            theme_type="dark",
            rspeed=1.0,
            rsound=True,
            rdisplay=False,
            rwindow=False,
            rol_disp_brain=False,
            show_enginename=False,
            picocoach=False,
            picowatcher=False,
            picoexplorer=False,
            picocomment=PicoComment.COM_OFF,
            picocomment_prob=0,
            contlast=False,
            altmove=False,
            dgttranslate=trans,
        )
        return menu

    @patch("platform.machine")
    def test_engine_menu_traversal(self, machine_mock):
        menu = self.create_menu(machine_mock)
        menu.set_state_current_engine("")
        text = menu.get_current_engine_name()
        self.assertEqual("Lc0", text.large_text)
        menu.enter_top_menu()
        self.assertEqual(MenuState.TOP, menu.state)
        menu.main_down()
        # start with engine menu from top menu
        self.assertEqual(MenuState.ENGINE, menu.state)
        menu.main_right()
        self.assertEqual(MenuState.SYS, menu.state)
        menu.main_left()
        self.assertEqual(MenuState.ENGINE, menu.state)
        menu.main_left()
        self.assertEqual(MenuState.BOOK, menu.state)
        menu.main_right()
        self.assertEqual(MenuState.ENGINE, menu.state)
        menu.main_down()
        self.assertEqual(MenuState.ENG_MODERN, menu.state)
        menu.main_up()
        self.assertEqual(MenuState.ENGINE, menu.state)
        menu.main_down()
        self.assertEqual(MenuState.ENG_MODERN, menu.state)
        menu.main_right()
        self.assertEqual(MenuState.ENG_RETRO, menu.state)
        menu.main_up()
        self.assertEqual(MenuState.ENGINE, menu.state)
        menu.main_down()
        self.assertEqual(MenuState.ENG_RETRO, menu.state)
        menu.main_right()
        self.assertEqual(MenuState.RETROSETTINGS, menu.state)
        menu.main_right()
        self.assertEqual(MenuState.ENG_FAV, menu.state)
        menu.main_up()
        self.assertEqual(MenuState.ENGINE, menu.state)
        menu.main_down()
        self.assertEqual(MenuState.ENG_FAV, menu.state)
        menu.main_right()
        self.assertEqual(MenuState.ENG_MODERN, menu.state)
        menu.main_left()
        self.assertEqual(MenuState.ENG_FAV, menu.state)
        menu.main_left()
        self.assertEqual(MenuState.RETROSETTINGS, menu.state)
        menu.main_left()
        self.assertEqual(MenuState.ENG_RETRO, menu.state)
        menu.main_left()
        # modern engines
        self.assertEqual(MenuState.ENG_MODERN, menu.state)
        modern_engine_name = menu.main_down()
        self.assertEqual(MenuState.ENG_MODERN_NAME, menu.state)
        self.assertEqual("Lc0", modern_engine_name.large_text)
        modern_engine_name = menu.main_right()
        self.assertEqual("McBrain9932", modern_engine_name.large_text)
        modern_engine_name = menu.main_left()
        self.assertEqual("Lc0", modern_engine_name.large_text)
        menu.main_up()
        self.assertEqual(MenuState.ENG_MODERN, menu.state)
        menu.main_right()
        # retro engines
        self.assertEqual(MenuState.ENG_RETRO, menu.state)
        retro_engine_name = menu.main_down()
        self.assertEqual(MenuState.ENG_RETRO_NAME, menu.state)
        self.assertEqual("Mep.Academy", retro_engine_name.large_text)
        retro_engine_name = menu.main_right()
        self.assertEqual("M.Amsterdam", retro_engine_name.large_text)
        retro_engine_name = menu.main_left()
        self.assertEqual("Mep.Academy", retro_engine_name.large_text)
        menu.main_up()
        self.assertEqual(MenuState.ENG_RETRO, menu.state)
        menu.main_right()
        self.assertEqual(MenuState.RETROSETTINGS, menu.state)
        menu.main_right()
        # favorite engines
        self.assertEqual(MenuState.ENG_FAV, menu.state)
        fav_engine_name = menu.main_down()
        self.assertEqual(MenuState.ENG_FAV_NAME, menu.state)
        self.assertEqual("Lc0 v0.27.0", fav_engine_name.large_text)
        fav_engine_name = menu.main_right()
        self.assertEqual("Stockfish DD", fav_engine_name.large_text)
        fav_engine_name = menu.main_left()
        self.assertEqual("Lc0 v0.27.0", fav_engine_name.large_text)
        # level of a favorite engine
        level = menu.main_down()
        self.assertEqual(MenuState.ENG_FAV_NAME_LEVEL, menu.state)
        self.assertEqual("1 Core", level.large_text)
        level = menu.main_right()
        self.assertEqual("2 Cores", level.large_text)
        level = menu.main_left()
        self.assertEqual("1 Core", level.large_text)

        menu.main_up()
        self.assertEqual(MenuState.ENG_FAV_NAME, menu.state)
        menu.main_up()
        menu.main_right()
        modern_engine_name = menu.main_down()
        self.assertEqual(MenuState.ENG_MODERN_NAME, menu.state)
        self.assertEqual("Lc0", modern_engine_name.large_text)
        # level of a modern engine
        level = menu.main_down()
        self.assertEqual(MenuState.ENG_MODERN_NAME_LEVEL, menu.state)
        self.assertEqual("1 Core", level.large_text)
        level = menu.main_right()
        self.assertEqual("2 Cores", level.large_text)
        level = menu.main_left()
        self.assertEqual("1 Core", level.large_text)

        menu.main_up()
        self.assertEqual(MenuState.ENG_MODERN_NAME, menu.state)
        menu.main_up()
        menu.main_right()
        retro_engine_name = menu.main_down()
        self.assertEqual(MenuState.ENG_RETRO_NAME, menu.state)
        self.assertEqual("Mep.Academy", retro_engine_name.large_text)
        # level of a retro engine
        level = menu.main_down()
        self.assertEqual(MenuState.ENG_RETRO_NAME_LEVEL, menu.state)
        self.assertEqual("Level 00 - speed", level.large_text)
        level = menu.main_right()
        self.assertEqual("Level 01 - 5s move", level.large_text)
        level = menu.main_left()
        self.assertEqual("Level 00 - speed", level.large_text)

        menu.main_up()
        self.assertEqual(MenuState.ENG_RETRO_NAME, menu.state)

    @patch("platform.machine")
    def test_modern_engine_retrieval(self, machine_mock):
        menu = self.create_menu(machine_mock)
        menu.set_state_current_engine("")
        menu.enter_top_menu()
        self.assertEqual("Engine", menu.main_down().medium_text.strip())
        self.assertEqual("Modern", menu.main_down().medium_text.strip())
        menu.main_down()  # first engine 'Lc0'
        self.assertEqual("zurichess", menu.main_left().large_text)  # last engine
        self.assertEqual("level     0", menu.main_down().large_text)  # level of zurichess
        self.assertFalse(menu.main_down())  # select zurichess engine
        self.assertEqual("zurichess", menu.get_current_engine_name().large_text)

        self.assertEqual("Engine", menu.main_down().medium_text.strip())
        self.assertEqual("Modern", menu.main_down().medium_text.strip())
        self.assertEqual("zurichess", menu.main_down().large_text)  # previously selected engine

    @patch("platform.machine")
    def test_retro_engine_retrieval(self, machine_mock):
        menu = self.create_menu(machine_mock)
        menu.set_state_current_engine("")
        menu.enter_top_menu()
        self.assertEqual("Engine", menu.main_down().medium_text.strip())
        self.assertEqual("Modern", menu.main_down().medium_text.strip())
        self.assertEqual("Retro", menu.main_right().medium_text.strip())
        menu.main_down()  # first retro engine 'Mep.Academy'
        self.assertEqual("Schachzwerg", menu.main_left().large_text)  # last retro engine
        self.assertFalse(menu.main_down())  # select Schachzwerg engine
        self.assertEqual("Schachzwerg", menu.get_current_engine_name().large_text)

        self.assertEqual("Engine", menu.main_down().medium_text.strip())
        self.assertEqual("Retro", menu.main_down().medium_text.strip())
        self.assertEqual("Schachzwerg", menu.main_down().large_text)  # previously selected engine

    @patch("platform.machine")
    def test_retro_engine_level_selection(self, machine_mock):
        menu = self.create_menu(machine_mock)
        menu.set_state_current_engine("")
        menu.enter_top_menu()
        self.assertEqual("Engine", menu.main_down().medium_text.strip())
        self.assertEqual("Modern", menu.main_down().medium_text.strip())
        self.assertEqual("Retro", menu.main_right().medium_text.strip())
        menu.main_down()  # first retro engine 'Mep.Academy'
        menu.main_right()  # second retro engine
        self.assertEqual("Mep. Milano", menu.main_right().large_text)  # third retro engine
        menu.main_down()  # level selection menu
        self.assertEqual("Level 10 - 60m game", menu.main_left().large_text)  # select level for engine 'Mep. Milano',
        self.assertFalse(menu.main_down())
        self.assertEqual("Mep. Milano", menu.get_current_engine_name().large_text)

        self.assertEqual("Engine", menu.main_down().medium_text.strip())
        self.assertEqual("Retro", menu.main_down().medium_text.strip())
        self.assertEqual("Mep. Milano", menu.main_down().large_text)  # previously selected engine
        self.assertEqual("Level 10 - 60m game", menu.main_down().large_text)  # previously selected engine level

    @patch("platform.machine")
    def test_modern_engine_after_retro(self, machine_mock):
        # select modern engine
        menu = self.create_menu(machine_mock)
        menu.set_state_current_engine("")
        menu.enter_top_menu()
        self.assertEqual("Engine", menu.main_down().medium_text.strip())
        self.assertEqual("Modern", menu.main_down().medium_text.strip())
        menu.main_down()  # first engine 'Lc0'
        self.assertEqual("zurichess", menu.main_left().large_text)  # last engine
        self.assertEqual("level     0", menu.main_down().large_text)  # level of zurichess
        self.assertFalse(menu.main_down())  # select zurichess engine

        # select retro engine
        menu.enter_top_menu()
        self.assertEqual("Engine", menu.main_down().medium_text.strip())
        self.assertEqual("Modern", menu.main_down().medium_text.strip())
        self.assertEqual("Retro", menu.main_right().medium_text.strip())
        menu.main_down()  # first retro engine 'Mep.Academy'
        self.assertEqual("Schachzwerg", menu.main_left().large_text)  # last retro engine
        self.assertFalse(menu.main_down())  # select Schachzwerg engine

        # re-select modern engine
        menu.enter_top_menu()
        self.assertEqual("Engine", menu.main_down().medium_text.strip())
        self.assertEqual("Retro", menu.main_down().medium_text.strip())
        self.assertEqual("Modern", menu.main_left().medium_text.strip())
        self.assertEqual("zurichess", menu.main_down().large_text)  # previous modern engine

    @patch("platform.machine")
    def test_set_state_current_engine_modern(self, machine_mock):
        menu = self.create_menu(machine_mock)
        menu.set_state_current_engine("zurich")
        menu.enter_top_menu()
        self.assertEqual("Engine", menu.main_down().medium_text.strip())
        self.assertEqual("Modern", menu.main_down().medium_text.strip())
        self.assertEqual("zurichess", menu.main_down().large_text)

    @patch("platform.machine")
    def test_set_state_current_engine_retro(self, machine_mock):
        menu = self.create_menu(machine_mock)
        menu.set_state_current_engine("mame/milano")
        menu.enter_top_menu()
        self.assertEqual("Engine", menu.main_down().medium_text.strip())
        self.assertEqual("Retro", menu.main_down().medium_text.strip())
        self.assertEqual("Mep. Milano", menu.main_down().large_text)

    @patch("platform.machine")
    def test_set_state_current_engine_favorite(self, machine_mock):
        menu = self.create_menu(machine_mock)
        menu.set_state_current_engine("mame/milano")
        menu.enter_top_menu()
        self.assertEqual("Engine", menu.main_down().medium_text.strip())
        self.assertEqual("Retro", menu.main_down().medium_text.strip())
        self.assertEqual("Ret-Sett", menu.main_right().medium_text.strip())
        self.assertEqual("Favorite", menu.main_right().medium_text.strip())
        self.assertEqual("Mephisto Milano", menu.main_down().large_text)

    @patch("platform.machine")
    def test_engine_not_in_modern_nor_in_retro(self, machine_mock):
        menu = self.create_menu(machine_mock)
        menu.set_state_current_engine("someEngine")
        self.assertEqual(MenuState.ENG_FAV_NAME, menu.state)
        menu.enter_top_menu()
        self.assertEqual("Engine", menu.main_down().medium_text.strip())
        self.assertEqual("Favorite", menu.main_down().medium_text.strip())
        self.assertEqual("someEngine", menu.main_down().large_text)
        self.assertEqual("Stockfish 15", menu.main_right().large_text)

    @patch("platform.machine")
    def test_power_menu(self, machine_mock):
        menu = self.create_menu(machine_mock)
        menu.set_state_current_engine("mame/tascr30_king")
        menu.enter_top_menu()
        self.assertEqual("Engine", menu.main_down().medium_text.strip())
        self.assertEqual("System", menu.main_right().medium_text.strip())
        self.assertEqual("Power", menu.main_down().medium_text.strip())
        self.assertEqual("Information", menu.main_right().large_text.strip())
        self.assertEqual("Sound", menu.main_right().large_text.strip())
        self.assertEqual("Language", menu.main_right().large_text.strip())
        self.assertEqual("mailLogfile", menu.main_right().large_text.strip())
        self.assertEqual("Voice", menu.main_right().large_text.strip())
        self.assertEqual("Display", menu.main_right().large_text.strip())
        self.assertEqual("E-Board", menu.main_right().large_text.strip())
        self.assertEqual("Web-Theme", menu.main_right().large_text.strip())
        self.assertEqual("Power", menu.main_right().large_text.strip())
        self.assertEqual("Web-Theme", menu.main_left().large_text.strip())
        self.assertEqual("E-Board", menu.main_left().large_text.strip())
        self.assertEqual("Display", menu.main_left().large_text.strip())
        self.assertEqual("Voice", menu.main_left().large_text.strip())
        self.assertEqual("mailLogfile", menu.main_left().large_text.strip())
        self.assertEqual("Language", menu.main_left().large_text.strip())
        self.assertEqual("Sound", menu.main_left().large_text.strip())
        self.assertEqual("Information", menu.main_left().large_text.strip())
        self.assertEqual("Power", menu.main_left().large_text.strip())
        self.assertEqual("Shut down", menu.main_down().large_text.strip())
        self.assertEqual("Restart", menu.main_right().large_text.strip())
        self.assertEqual("Shut down", menu.main_left().large_text.strip())

    @patch("platform.machine")
    def test_node_menu(self, machine_mock):
        menu = self.create_menu(machine_mock)
        menu.set_state_current_engine("")
        text = menu.get_current_engine_name()
        self.assertEqual("Lc0", text.large_text)
        menu.enter_top_menu()
        self.assertEqual(MenuState.TOP, menu.state)
        menu.main_down()
        # start with engine menu from top menu
        menu.main_left()
        menu.main_left()
        self.assertEqual(MenuState.TIME, menu.state)
        menu.main_down()
        menu.main_left()
        menu.main_left()
        self.assertEqual(MenuState.TIME_NODE, menu.state)
        menu.main_right()
        menu.main_left()
        self.assertEqual(MenuState.TIME_NODE, menu.state)
        text = menu.main_down()
        self.assertEqual(MenuState.TIME_NODE_CTRL, menu.state)
        self.assertEqual("Nodes  1", text.large_text.strip())
        self.assertEqual("Nodes  5", menu.main_right().large_text.strip())
        self.assertEqual("Nodes  1", menu.main_left().large_text.strip())
        self.assertEqual("Nodes 500", menu.main_left().large_text.strip())
