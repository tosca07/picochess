import chess  # type: ignore
import mock
import unittest

from picochess import AlternativeMover, read_pgn_info, read_online_result, read_online_user_info


class TestAlternativeMover(unittest.TestCase):

    def setUp(self):
        self.testee = AlternativeMover()
        self.game = chess.Board()
        self.e2e4 = chess.Move.from_uci("e2e4")

    def test_alternative_move_tracking(self):
        moves = self.testee.all(self.game)

        self.assertEqual(moves, set(self.game.legal_moves))

    def test_exclude_moves(self):
        self.testee.exclude(self.e2e4)
        moves = self.testee.all(self.game)

        self.assertTrue(self.e2e4 not in moves)

    def test_reset(self):
        self.testee.exclude(self.e2e4)
        moves = self.testee.all(self.game)

        self.assertTrue(self.e2e4 not in moves)

        self.testee.reset()
        moves = self.testee.all(self.game)

        self.assertTrue(self.e2e4 in moves)

    def test_all_excluded_moves(self):
        only_move_fen = "k7/8/2K5/8/8/8/8/1Q6 b - - 0 1"
        self.testee.exclude(chess.Move.from_uci("a8a7"))
        moves = self.testee.all(chess.Board(only_move_fen))

        self.assertTrue(chess.Move.from_uci("a8a7") in moves)

    def test_book_no_moves(self):
        bookreader = mock.create_autospec(chess.polyglot.MemoryMappedReader)
        bookreader.weighted_choice.side_effect = IndexError()
        move = self.testee.book(bookreader, self.game)

        self.assertEqual(move, None)

    def test_book_1_move_in_book(self):
        bookreader = mock.create_autospec(chess.polyglot.MemoryMappedReader)
        book_move = chess.polyglot.Entry(1, 796, 0, 1)
        bookreader.weighted_choice.side_effect = [book_move, IndexError()]
        move = self.testee.book(bookreader, self.game)

        self.assertEqual(move, chess.engine.BestMove(self.e2e4, None))

    def test_book_2_moves_in_book(self):
        bookreader = mock.create_autospec(chess.polyglot.MemoryMappedReader)
        book_move = chess.polyglot.Entry(1, 796, 0, 1)
        book_move_2 = chess.polyglot.Entry(1, 1804, 0, 1)
        e4e2 = chess.Move.from_uci("e4e2")
        bookreader.weighted_choice.side_effect = [book_move, book_move_2]
        move = self.testee.book(bookreader, self.game)

        self.assertEqual(move, chess.engine.BestMove(self.e2e4, e4e2))

    def test_book_exclude_side_effect(self):
        bookreader = mock.create_autospec(chess.polyglot.MemoryMappedReader)
        book_move = chess.polyglot.Entry(1, 796, 0, 1)
        bookreader.weighted_choice.side_effect = [book_move, IndexError()]
        self.testee.book(bookreader, self.game)

        moves = self.testee.all(self.game)

        self.assertTrue(self.e2e4 not in moves)

    def test_book_game_side_effect(self):
        bookreader = mock.create_autospec(chess.polyglot.MemoryMappedReader)
        book_move = chess.polyglot.Entry(1, 796, 0, 1)
        bookreader.weighted_choice.side_effect = [book_move, IndexError()]
        self.testee.book(bookreader, self.game)

        self.assertEqual(self.game.pop(), self.e2e4)

    def test_check_book_no_moves(self):
        bookreader = mock.create_autospec(chess.polyglot.MemoryMappedReader)
        bookreader.weighted_choice.side_effect = IndexError()

        self.assertFalse(self.testee.check_book(bookreader, self.game))

    def test_check_book_found_move(self):
        bookreader = mock.create_autospec(chess.polyglot.MemoryMappedReader)
        book_move = chess.polyglot.Entry(1, 796, 0, 1)
        bookreader.weighted_choice.side_effect = [book_move]

        self.assertTrue(self.testee.check_book(bookreader, self.game))

    def test_check_book_found_null_move(self):
        bookreader = mock.create_autospec(chess.polyglot.MemoryMappedReader)
        book_move = chess.polyglot.Entry(1, 0, 0, 1)
        bookreader.weighted_choice.side_effect = [book_move]

        self.assertFalse(self.testee.check_book(bookreader, self.game))


class TestReadPGNInfo(unittest.TestCase):
    def test_read_pgn_info(self):
        game_name, problem, fen, result, white, black = read_pgn_info()
        self.assertEqual("Kasparov 25 board Simul", game_name.strip())
        self.assertEqual("", problem.strip())
        self.assertEqual("", fen.strip())
        self.assertEqual("1/2-1/2", result.strip())
        self.assertEqual("Kasparov", white.strip())
        self.assertEqual("Lloyds Bank: Munro, Clarke, Cooper, Drew", black.strip())


class TestReadOnlineGame(unittest.TestCase):
    def test_read_online_result(self):
        result, winner = read_online_result()
        self.assertEqual(result, "unknown")
        self.assertEqual(winner, "")

    def test_read_online_user_info(self):
        login, own_color, own_user, opp_user, game_time, fisher_inc = read_online_user_info()
        self.assertEqual(login, "ok")
        self.assertEqual(own_color, "W")
        self.assertEqual(own_user, "GuestBLQS")
        self.assertEqual(opp_user, "levoll")
        self.assertEqual(game_time, 5)
        self.assertEqual(fisher_inc, 0)
