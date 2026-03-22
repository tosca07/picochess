import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import chess

from dgt.api import Event
from dgt.display import DgtDisplay
from dgt.util import Mode, PlayMode, TimeMode
from timecontrol import TimeControl


class DummyTranslate:
    language = "en"
    capital = False
    notation = False

    def text(self, *_args, **_kwargs):
        return SimpleNamespace(
            large_text="",
            medium_text="",
            small_text="",
            web_text="",
            wait=False,
            beep=None,
            maxtime=0,
        )

    def bl(self, *_args, **_kwargs):
        return None


class DummyMenu:
    def __init__(self):
        self.tc_fixed_map = {}
        self.tc_blitz_map = {}
        self.tc_fisch_map = {}
        self.all_books = []
        self.installed_engines = []
        self.remote_engine = False
        self._dgt_fen = ""
        self._flip_board = False
        self._engine_has_960 = False
        self._engine_rdisplay = False
        self._mode = Mode.PONDER

    def set_position_reverse_flipboard(self, flip_board, _play_mode):
        self._flip_board = flip_board

    def get_flip_board(self):
        return self._flip_board

    def get_dgt_fen(self):
        return self._dgt_fen

    def set_dgt_fen(self, fen):
        self._dgt_fen = fen

    def get_engine_has_960(self):
        return self._engine_has_960

    def get_engine_rdisplay(self):
        return self._engine_rdisplay

    def get_mode(self):
        return self._mode


class TestDgtDisplayStartPositionRouting(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        loop = asyncio.new_event_loop()
        self.addCleanup(loop.close)
        self.menu = DummyMenu()
        self.display = DgtDisplay(
            dgttranslate=DummyTranslate(),
            dgtmenu=self.menu,
            time_control=TimeControl(mode=TimeMode.FIXED, fixed=0),
            loop=loop,
        )
        self.display.play_mode = PlayMode.USER_WHITE

    @patch("dgt.display.Observable.fire", new_callable=AsyncMock)
    async def test_standard_start_position_routes_through_fen_for_takeback(self, observable_fire):
        self.display.last_pos_start = False
        self.display._current_game_has_moves = True
        self.display._current_game_start_pos960 = 518

        await self.display._process_fen(chess.STARTING_BOARD_FEN, raw=False)

        event = observable_fire.await_args.args[0]
        self.assertIsInstance(event, Event.FEN)
        self.assertEqual(chess.STARTING_BOARD_FEN, event.fen)

    @patch("dgt.display.Observable.fire", new_callable=AsyncMock)
    async def test_different_chess960_start_still_triggers_new_game(self, observable_fire):
        self.menu._engine_has_960 = True
        self.display.last_pos_start = False
        self.display._current_game_has_moves = True
        self.display._current_game_start_pos960 = 518
        chess960_fen = chess.Board.from_chess960_pos(0).board_fen()

        await self.display._process_fen(chess960_fen, raw=False)

        event = observable_fire.await_args.args[0]
        self.assertIsInstance(event, Event.NEW_GAME)
        self.assertEqual(0, event.pos960)

    @patch("dgt.display.Observable.fire", new_callable=AsyncMock)
    async def test_start_position_without_move_history_still_triggers_new_game(self, observable_fire):
        self.display.last_pos_start = False
        self.display._current_game_has_moves = False
        self.display._current_game_start_pos960 = 518

        await self.display._process_fen(chess.STARTING_BOARD_FEN, raw=False)

        event = observable_fire.await_args.args[0]
        self.assertIsInstance(event, Event.NEW_GAME)
        self.assertEqual(518, event.pos960)
