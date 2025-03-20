import chess  # type: ignore[import]
import datetime
import unittest

from dgt.util import PlayMode
from pgn import PgnDisplay

EMPTY_GAME = """[Event "PicoChess Game"]
[Site "?"]
[Date "{0}"]
[Round "?"]
[White "?"]
[Black "?"]
[Result "*"]
[BlackElo "-"]
[PicoRemTimeB "0"]
[PicoRemTimeW "0"]
[PicoTimeControl "0"]
[Time "{1}"]
[WhiteElo "-"]

*"""


class FakeMessage:
    def __init__(self, game, play_mode):
        self.game = game
        self.play_mode = play_mode
        self.tc_init = {"internal_time": {chess.WHITE: 0, chess.BLACK: 0}}


class TestPgnDisplay(unittest.TestCase):
    def setUp(self):
        self.testee = PgnDisplay("test", None)

    def test_generate_pgn(self):
        game = chess.Board()
        msg = FakeMessage(game, PlayMode.USER_WHITE)

        pgn = self.testee._generate_pgn_from_message(msg)
        empty_game = EMPTY_GAME.format(datetime.date.today().strftime("%Y.%m.%d"), self.testee.startime)

        self.assertEqual(str(pgn), empty_game)
