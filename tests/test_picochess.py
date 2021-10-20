import chess
import unittest

from picochess import AlternativeMover

class TestAlternativeMover(unittest.TestCase):

    def setUp(self):
        self.testee = AlternativeMover()
        self.game = chess.Board()

    def test_alternative_move_tracking(self):
        moves = self.testee.all(self.game)

        self.assertEqual(moves, set(self.game.legal_moves))


    def test_exclude_moves(self):
        self.testee.exclude(chess.Move.from_uci('e2e4'))
        moves = self.testee.all(self.game)

        self.assertTrue(chess.Move.from_uci('e2e4') not in moves)


    def test_reset(self):
        self.testee.exclude(chess.Move.from_uci('e2e4'))
        moves = self.testee.all(self.game)

        self.assertTrue(chess.Move.from_uci('e2e4') not in moves)

        self.testee.reset()
        moves = self.testee.all(self.game)

        self.assertTrue(chess.Move.from_uci('e2e4') in moves)


    def test_all_excluded_moves(self):
        only_move_fen = 'k7/8/2K5/8/8/8/8/1Q6 b - - 0 1'
        self.testee.exclude(chess.Move.from_uci('a8a7'))
        moves = self.testee.all(chess.Board(only_move_fen))

        self.assertTrue(chess.Move.from_uci('a8a7') in moves)
