import unittest
import chess
from picotutor import PicoTutor



class TestHalfMoves(unittest.TestCase):

    def test_halfmove_to_fullmove_unknown_start(self):
        self.assertEqual(PicoTutor.halfmove_to_fullmove(0), (0, chess.WHITE, False))
        self.assertEqual(PicoTutor.halfmove_to_fullmove(1), (0, chess.BLACK, False))
        self.assertEqual(PicoTutor.halfmove_to_fullmove(2), (1, chess.WHITE, False))
        self.assertEqual(PicoTutor.halfmove_to_fullmove(3), (1, chess.BLACK, False))
        self.assertEqual(PicoTutor.halfmove_to_fullmove(4), (2, chess.WHITE, False))
        self.assertEqual(PicoTutor.halfmove_to_fullmove(5), (2, chess.BLACK, False))
        self.assertEqual(PicoTutor.halfmove_to_fullmove(6), (3, chess.WHITE, False))
        self.assertEqual(PicoTutor.halfmove_to_fullmove(7), (3, chess.BLACK, False))

    def test_halfmove_to_fullmove_normal_start(self):
        self.assertEqual(PicoTutor.halfmove_to_fullmove(0, chess.WHITE), (0, chess.WHITE, False))
        self.assertEqual(PicoTutor.halfmove_to_fullmove(1, chess.BLACK), (0, chess.BLACK, False))
        self.assertEqual(PicoTutor.halfmove_to_fullmove(2, chess.WHITE), (1, chess.WHITE, False))
        self.assertEqual(PicoTutor.halfmove_to_fullmove(3, chess.BLACK), (1, chess.BLACK, False))
        self.assertEqual(PicoTutor.halfmove_to_fullmove(4, chess.WHITE), (2, chess.WHITE, False))
        self.assertEqual(PicoTutor.halfmove_to_fullmove(5, chess.BLACK), (2, chess.BLACK, False))
        self.assertEqual(PicoTutor.halfmove_to_fullmove(6, chess.WHITE), (3, chess.WHITE, False))
        self.assertEqual(PicoTutor.halfmove_to_fullmove(7, chess.BLACK), (3, chess.BLACK, False))

    def test_halfmove_to_fullmove_black_first(self):
        self.assertEqual(PicoTutor.halfmove_to_fullmove(0, chess.BLACK), (0, chess.BLACK, True))
        self.assertEqual(PicoTutor.halfmove_to_fullmove(1, chess.WHITE), (1, chess.WHITE, True))
        self.assertEqual(PicoTutor.halfmove_to_fullmove(2, chess.BLACK), (1, chess.BLACK, True))
        self.assertEqual(PicoTutor.halfmove_to_fullmove(3, chess.WHITE), (2, chess.WHITE, True))
        self.assertEqual(PicoTutor.halfmove_to_fullmove(4, chess.BLACK), (2, chess.BLACK, True))
        self.assertEqual(PicoTutor.halfmove_to_fullmove(5, chess.WHITE), (3, chess.WHITE, True))
        self.assertEqual(PicoTutor.halfmove_to_fullmove(6, chess.BLACK), (3, chess.BLACK, True))
        self.assertEqual(PicoTutor.halfmove_to_fullmove(7, chess.WHITE), (4, chess.WHITE, True))

    def test_fullmove_to_halfmove_unknown_start(self):
        self.assertEqual(PicoTutor.fullmove_to_halfmove(0, chess.WHITE), 0)
        self.assertEqual(PicoTutor.fullmove_to_halfmove(0, chess.BLACK), 1)
        self.assertEqual(PicoTutor.fullmove_to_halfmove(1, chess.WHITE), 2)
        self.assertEqual(PicoTutor.fullmove_to_halfmove(1, chess.BLACK), 3)
        self.assertEqual(PicoTutor.fullmove_to_halfmove(2, chess.WHITE), 4)
        self.assertEqual(PicoTutor.fullmove_to_halfmove(2, chess.BLACK), 5)
        self.assertEqual(PicoTutor.fullmove_to_halfmove(3, chess.WHITE), 6)
        self.assertEqual(PicoTutor.fullmove_to_halfmove(3, chess.BLACK), 7)

    def test_fullmove_to_halfmove_normal_start(self):
        self.assertEqual(PicoTutor.fullmove_to_halfmove(0, chess.WHITE, first_move_black=False), 0)
        self.assertEqual(PicoTutor.fullmove_to_halfmove(0, chess.BLACK, first_move_black=False), 1)
        self.assertEqual(PicoTutor.fullmove_to_halfmove(1, chess.WHITE, first_move_black=False), 2)
        self.assertEqual(PicoTutor.fullmove_to_halfmove(1, chess.BLACK, first_move_black=False), 3)
        self.assertEqual(PicoTutor.fullmove_to_halfmove(2, chess.WHITE, first_move_black=False), 4)
        self.assertEqual(PicoTutor.fullmove_to_halfmove(2, chess.BLACK, first_move_black=False), 5)
        self.assertEqual(PicoTutor.fullmove_to_halfmove(3, chess.WHITE, first_move_black=False), 6)
        self.assertEqual(PicoTutor.fullmove_to_halfmove(3, chess.BLACK, first_move_black=False), 7)

    def test_fullmove_to_halfmove_black_first(self):
        self.assertEqual(PicoTutor.fullmove_to_halfmove(0, chess.BLACK, first_move_black=True), 0)
        self.assertEqual(PicoTutor.fullmove_to_halfmove(1, chess.WHITE, first_move_black=True), 1)
        self.assertEqual(PicoTutor.fullmove_to_halfmove(1, chess.BLACK, first_move_black=True), 2)
        self.assertEqual(PicoTutor.fullmove_to_halfmove(2, chess.WHITE, first_move_black=True), 3)
        self.assertEqual(PicoTutor.fullmove_to_halfmove(2, chess.BLACK, first_move_black=True), 4)
        self.assertEqual(PicoTutor.fullmove_to_halfmove(3, chess.WHITE, first_move_black=True), 5)
        self.assertEqual(PicoTutor.fullmove_to_halfmove(3, chess.BLACK, first_move_black=True), 6)
        self.assertEqual(PicoTutor.fullmove_to_halfmove(4, chess.WHITE, first_move_black=True), 7)

    def test_round_trip_consistency(self):
        for halfmove in range(0, 20):
            for known_turn in [chess.WHITE, chess.BLACK]:
                fullmove, turn, first_move_black = PicoTutor.halfmove_to_fullmove(halfmove, known_turn)
                reconverted = PicoTutor.fullmove_to_halfmove(fullmove, turn, first_move_black)
                self.assertEqual(reconverted, halfmove,
                                 f"Mismatch: halfmove={halfmove}, known_turn={known_turn}, got={reconverted}")

if __name__ == '__main__':
    unittest.main()
