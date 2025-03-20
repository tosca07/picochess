#!/usr/bin/env python3

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

from typing import List

import unittest
from unittest.mock import call, patch

import chess  # type: ignore

from certabo.sentio import Sentio
from certabo.parser import to_square


@patch("certabo.parser.ParserCallback")
@patch("certabo.led_control.CertaboLedControl")
class TestSentio(unittest.TestCase):

    def test_leds_missing_all_pieces(self, MockedParserCallback, MockedLedControl):
        sentio = Sentio(MockedParserCallback, MockedLedControl)
        sentio.occupied_squares(self._fen_to_occupied("8/8/8/8/8/8/8/8"))
        MockedLedControl.write_led_command.assert_called_with(bytearray(b"\xff\xff\x00\x00\x00\x00\xff\xff"))

    def test_leds_missing_rook_a1(self, MockedParserCallback, MockedLedControl):
        sentio = Sentio(MockedParserCallback, MockedLedControl)
        sentio.occupied_squares(self._fen_to_occupied("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/1NBQKBNR"))
        MockedLedControl.write_led_command.assert_called_with(bytearray(b"\x00\x00\x00\x00\x00\x00\x00\x01"))

    def test_leds_missing_pawn_h2(self, MockedParserCallback, MockedLedControl):
        sentio = Sentio(MockedParserCallback, MockedLedControl)
        sentio.occupied_squares(self._fen_to_occupied("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPP1/RNBQKBNR"))
        MockedLedControl.write_led_command.assert_called_with(bytearray(b"\x00\x00\x00\x00\x00\x00\x80\x00"))

    def test_leds_combine_with_engine_move(self, MockedParserCallback, MockedLedControl):
        sentio = Sentio(MockedParserCallback, MockedLedControl)
        sentio.occupied_squares(self._fen_to_occupied("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"))
        sentio.uci_move("e2e4")
        sentio.occupied_squares(self._fen_to_occupied("rnbqkbnr/pppppppp/8/8/8/8/PPPP1PPP/RNBQKBNR"))  # pick up pawn
        MockedLedControl.write_led_command.assert_called_with(bytearray(b"\x00\x00\x00\x00\x10\x00\x10\x00"))

    def test_leds_stay_on_for_engine_move(self, MockedParserCallback, MockedLedControl):
        sentio = Sentio(MockedParserCallback, MockedLedControl)
        sentio.occupied_squares(self._fen_to_occupied("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"))
        sentio.uci_move("e2e4")
        sentio.occupied_squares(self._fen_to_occupied("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPP1/RNBQKBNR"))  # pick up pawn
        sentio.occupied_squares(self._fen_to_occupied("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"))  # put back down
        MockedLedControl.write_led_command.assert_called_with(bytearray(b"\x00\x00\x00\x00\x10\x00\x10\x00"))

    def test_leds_stay_on_for_finished_engine_move(self, MockedParserCallback, MockedLedControl):
        # LEDs will be turned off at the end by picochess itself
        sentio = Sentio(MockedParserCallback, MockedLedControl)
        sentio.occupied_squares(self._fen_to_occupied("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"))
        sentio.uci_move("e2e4")
        sentio.occupied_squares(self._fen_to_occupied("rnbqkbnr/pppppppp/8/8/8/8/PPPP1PPP/RNBQKBNR"))  # pick up e2
        sentio.occupied_squares(self._fen_to_occupied("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR"))  # put down e4
        MockedLedControl.write_led_command.assert_called_with(bytearray(b"\x00\x00\x00\x00\x10\x00\x10\x00"))

    def test_non_capture_move(self, MockedParserCallback, MockedLedControl):
        sentio = Sentio(MockedParserCallback, MockedLedControl)
        sentio.occupied_squares(self._fen_to_occupied("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"))
        sentio.occupied_squares(self._fen_to_occupied("rnbqkbnr/pppppppp/8/8/8/8/PPPP1PPP/RNBQKBNR"))  # e2 up
        sentio.occupied_squares(self._fen_to_occupied("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR"))  # e4 down
        calls = [
            call("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"),
            call("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR"),
        ]
        MockedParserCallback.board_update.assert_has_calls(calls)

    def test_capture_move(self, MockedParserCallback, MockedLedControl):
        sentio = Sentio(MockedParserCallback, MockedLedControl)
        sentio.board = chess.Board("rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 2")
        sentio.occupied_squares(self._fen_to_occupied("rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR"))
        # e4xd5
        sentio.occupied_squares(self._fen_to_occupied("rnbqkbnr/ppp1pppp/8/3p4/8/8/PPPP1PPP/RNBQKBNR"))  # e4 up
        sentio.occupied_squares(self._fen_to_occupied("rnbqkbnr/ppp1pppp/8/8/8/8/PPPP1PPP/RNBQKBNR"))  # d5 up
        sentio.occupied_squares(self._fen_to_occupied("rnbqkbnr/ppp1pppp/8/3p4/8/8/PPPP1PPP/RNBQKBNR"))  # d5 down
        calls = [
            call("rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR"),
            call("rnbqkbnr/ppp1pppp/8/3P4/8/8/PPPP1PPP/RNBQKBNR"),
        ]
        MockedParserCallback.board_update.assert_has_calls(calls)

    def test_en_passant_move_a(self, MockedParserCallback, MockedLedControl):
        sentio = Sentio(MockedParserCallback, MockedLedControl)
        sentio.board = chess.Board("rnbqkbnr/pp2pppp/8/2pP4/8/8/PPPP1PPP/RNBQKBNR w KQkq c6 0 3")
        sentio.occupied_squares(self._fen_to_occupied("rnbqkbnr/pp2pppp/8/2pP4/8/8/PPPP1PPP/RNBQKBNR"))
        # d5xc6
        sentio.occupied_squares(self._fen_to_occupied("rnbqkbnr/pp2pppp/8/2p5/8/8/PPPP1PPP/RNBQKBNR"))  # d5 up
        sentio.occupied_squares(self._fen_to_occupied("rnbqkbnr/pp2pppp/2P5/2p5/8/8/PPPP1PPP/RNBQKBNR"))  # c6 down
        sentio.occupied_squares(self._fen_to_occupied("rnbqkbnr/pp2pppp/2P5/8/8/8/PPPP1PPP/RNBQKBNR"))  # c5 up
        calls = [
            call("rnbqkbnr/pp2pppp/8/2pP4/8/8/PPPP1PPP/RNBQKBNR"),
            call("rnbqkbnr/pp2pppp/2P5/8/8/8/PPPP1PPP/RNBQKBNR"),
        ]
        MockedParserCallback.board_update.assert_has_calls(calls)

    def test_en_passant_move_b(self, MockedParserCallback, MockedLedControl):
        sentio = Sentio(MockedParserCallback, MockedLedControl)
        sentio.board = chess.Board("rnbqkbnr/pp2pppp/8/2pP4/8/8/PPPP1PPP/RNBQKBNR w KQkq c6 0 3")
        sentio.occupied_squares(self._fen_to_occupied("rnbqkbnr/pp2pppp/8/2pP4/8/8/PPPP1PPP/RNBQKBNR"))
        # d5xc6
        sentio.occupied_squares(self._fen_to_occupied("rnbqkbnr/pp2pppp/8/3P4/8/8/PPPP1PPP/RNBQKBNR"))  # c5 up
        sentio.occupied_squares(self._fen_to_occupied("rnbqkbnr/pp2pppp/8/8/8/8/PPPP1PPP/RNBQKBNR"))  # d5 up
        sentio.occupied_squares(self._fen_to_occupied("rnbqkbnr/pp2pppp/2P5/8/8/8/PPPP1PPP/RNBQKBNR"))  # c6 down
        calls = [
            call("rnbqkbnr/pp2pppp/8/2pP4/8/8/PPPP1PPP/RNBQKBNR"),
            call("rnbqkbnr/pp2pppp/2P5/8/8/8/PPPP1PPP/RNBQKBNR"),
        ]
        MockedParserCallback.board_update.assert_has_calls(calls)

    def test_en_passant_move_c(self, MockedParserCallback, MockedLedControl):
        sentio = Sentio(MockedParserCallback, MockedLedControl)
        sentio.board = chess.Board("rnbqkbnr/pp2pppp/8/2pP4/8/8/PPPP1PPP/RNBQKBNR w KQkq c6 0 3")
        sentio.occupied_squares(self._fen_to_occupied("rnbqkbnr/pp2pppp/8/2pP4/8/8/PPPP1PPP/RNBQKBNR"))
        # d5xc6
        sentio.occupied_squares(self._fen_to_occupied("rnbqkbnr/pp2pppp/8/2p5/8/8/PPPP1PPP/RNBQKBNR"))  # d5 up
        sentio.occupied_squares(self._fen_to_occupied("rnbqkbnr/pp2pppp/8/8/8/8/PPPP1PPP/RNBQKBNR"))  # c5 up
        sentio.occupied_squares(self._fen_to_occupied("rnbqkbnr/pp2pppp/2P5/8/8/8/PPPP1PPP/RNBQKBNR"))  # c6 down
        calls = [
            call("rnbqkbnr/pp2pppp/8/2pP4/8/8/PPPP1PPP/RNBQKBNR"),
            call("rnbqkbnr/pp2pppp/2P5/8/8/8/PPPP1PPP/RNBQKBNR"),
        ]
        MockedParserCallback.board_update.assert_has_calls(calls)

    def test_promotion_request(self, MockedParserCallback, MockedLedControl):
        sentio = Sentio(MockedParserCallback, MockedLedControl)
        sentio.board = chess.Board("4k3/P7/8/8/8/8/8/4K3 w - - 0 1")
        sentio.occupied_squares(self._fen_to_occupied("4k3/P7/8/8/8/8/8/4K3"))
        # a7a8=Q
        sentio.occupied_squares(self._fen_to_occupied("4k3/8/8/8/8/8/8/4K3"))  # a7 up
        sentio.occupied_squares(self._fen_to_occupied("Q3k3/8/8/8/8/8/8/4K3"))  # a8 down
        MockedParserCallback.board_update.assert_has_calls([call("4k3/P7/8/8/8/8/8/4K3")])
        MockedParserCallback.request_promotion_dialog([call(chess.Move(chess.A7, chess.A8, promotion=chess.QUEEN))])

    def test_promotion_request_with_capture(self, MockedParserCallback, MockedLedControl):
        sentio = Sentio(MockedParserCallback, MockedLedControl)
        sentio.board = chess.Board("1n2k3/P7/8/8/8/8/8/4K3 w - - 0 1")
        sentio.occupied_squares(self._fen_to_occupied("1n2k3/P7/8/8/8/8/8/4K3"))
        # a7xb8=Q
        sentio.occupied_squares(self._fen_to_occupied("4k3/P7/8/8/8/8/8/4K3"))  # b8 up
        sentio.occupied_squares(self._fen_to_occupied("4k3/8/8/8/8/8/8/4K3"))  # a7 up
        sentio.occupied_squares(self._fen_to_occupied("1Q2k3/8/8/8/8/8/8/4K3"))  # b8 down
        MockedParserCallback.board_update.assert_has_calls([call("1n2k3/P7/8/8/8/8/8/4K3")])
        MockedParserCallback.request_promotion_dialog([call(chess.Move(chess.A7, chess.B8, promotion=chess.QUEEN))])

    def test_finish_promotion_move(self, MockedParserCallback, MockedLedControl):
        sentio = Sentio(MockedParserCallback, MockedLedControl)
        sentio.board = chess.Board("1n2k3/P7/8/8/8/8/8/4K3 w - - 0 1")
        sentio.occupied_squares(self._fen_to_occupied("1n2k3/P7/8/8/8/8/8/4K3"))
        # a7xb8=Q
        sentio.occupied_squares(self._fen_to_occupied("4k3/P7/8/8/8/8/8/4K3"))  # b8 up
        sentio.occupied_squares(self._fen_to_occupied("4k3/8/8/8/8/8/8/4K3"))  # a7 up
        sentio.occupied_squares(self._fen_to_occupied("1Q2k3/8/8/8/8/8/8/4K3"))  # b8 down
        sentio.promotion_done("a7b8n")
        MockedParserCallback.board_update.assert_called_with("1N2k3/8/8/8/8/8/8/4K3")

    def test_detect_new_game(self, MockedParserCallback, MockedLedControl):
        sentio = Sentio(MockedParserCallback, MockedLedControl)
        sentio.board = chess.Board("4k3/P7/8/8/8/8/8/4K3 w - - 0 1")
        sentio.occupied_squares(self._fen_to_occupied("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"))
        calls = [call("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR")]
        MockedParserCallback.board_update.assert_has_calls(calls)
        MockedLedControl.write_led_command.assert_called_with(bytearray(b"\x00\x00\x00\x00\x00\x00\x00\x00"))

    def test_sliding_piece(self, MockedParserCallback, MockedLedControl):
        sentio = Sentio(MockedParserCallback, MockedLedControl)
        sentio.occupied_squares(self._fen_to_occupied("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"))
        sentio.occupied_squares(self._fen_to_occupied("rnbqkbnr/pppppppp/8/8/8/4P3/PPPP1PPP/RNBQKBNR"))  # e3
        sentio.occupied_squares(self._fen_to_occupied("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR"))  # e4
        calls = [
            call("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"),
            call("rnbqkbnr/pppppppp/8/8/8/4P3/PPPP1PPP/RNBQKBNR"),
            call("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR"),
        ]
        MockedParserCallback.board_update.assert_has_calls(calls)

    def test_castle(self, MockedParserCallback, MockedLedControl):
        sentio = Sentio(MockedParserCallback, MockedLedControl)
        sentio.board = chess.Board("rnbqk2r/pppp1ppp/5n2/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4")
        sentio.occupied_squares(self._fen_to_occupied("rnbqk2r/pppp1ppp/5n2/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R"))
        sentio.occupied_squares(self._fen_to_occupied("rnbqk2r/pppp1ppp/5n2/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQ3R"))  # Ke1 up
        sentio.occupied_squares(
            self._fen_to_occupied("rnbqk2r/pppp1ppp/5n2/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQ2KR")
        )  # Kg1 down
        sentio.occupied_squares(
            self._fen_to_occupied("rnbqk2r/pppp1ppp/5n2/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQ2K1")
        )  # Rh1 up
        sentio.occupied_squares(
            self._fen_to_occupied("rnbqk2r/pppp1ppp/5n2/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQ1RK1")
        )  # Rf1 down
        calls = [
            call("rnbqk2r/pppp1ppp/5n2/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R"),
            call("rnbqk2r/pppp1ppp/5n2/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQ2KR"),
            call("rnbqk2r/pppp1ppp/5n2/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQ1RK1"),
        ]
        MockedParserCallback.board_update.assert_has_calls(calls)

    def test_take_back_a(self, MockedParserCallback, MockedLedControl):
        sentio = Sentio(MockedParserCallback, MockedLedControl)
        board = chess.Board()
        board.push(chess.Move.from_uci("e2e4"))
        board.push(chess.Move.from_uci("e7e5"))
        sentio.board = board
        sentio.occupied_squares(self._fen_to_occupied("rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR"))
        # takeback e5e7
        sentio.occupied_squares(self._fen_to_occupied("rnbqkbnr/pppp1ppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR"))  # e5 up
        sentio.occupied_squares(self._fen_to_occupied("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR"))  # e7 down
        calls = [
            call("rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR"),
            call("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR"),
        ]
        MockedParserCallback.board_update.assert_has_calls(calls)

    def test_take_back_b(self, MockedParserCallback, MockedLedControl):
        sentio = Sentio(MockedParserCallback, MockedLedControl)
        board = chess.Board()
        for move in ("e2e4", "c7c5", "g1f3", "d7d6", "f1b5", "c8d7", "b5d7", "b8d7"):
            board.push(chess.Move.from_uci(move))
        sentio.board = board
        sentio.occupied_squares(self._fen_to_occupied("r2qkbnr/pp1npppp/3p4/2p5/4P3/5N2/PPPP1PPP/RNBQK2R"))
        # takeback b8d7
        sentio.occupied_squares(self._fen_to_occupied("r2qkbnr/pp2pppp/3p4/2p5/4P3/5N2/PPPP1PPP/RNBQK2R"))  # d7 up
        sentio.occupied_squares(self._fen_to_occupied("rn1qkbnr/pp2pppp/3p4/2p5/4P3/5N2/PPPP1PPP/RNBQK2R"))  # b8 down
        sentio.occupied_squares(self._fen_to_occupied("rn1qkbnr/pp1Bpppp/3p4/2p5/4P3/5N2/PPPP1PPP/RNBQK2R"))  # d7 down
        calls = [
            call("r2qkbnr/pp1npppp/3p4/2p5/4P3/5N2/PPPP1PPP/RNBQK2R"),
            call("rn1qkbnr/pp1Bpppp/3p4/2p5/4P3/5N2/PPPP1PPP/RNBQK2R"),
        ]
        MockedParserCallback.board_update.assert_has_calls(calls)
        # takeback b5d7
        sentio.occupied_squares(self._fen_to_occupied("rn1qkbnr/pp2pppp/3p4/2p5/4P3/5N2/PPPP1PPP/RNBQK2R"))  # d7 up
        sentio.occupied_squares(self._fen_to_occupied("rn1qkbnr/pp2pppp/3p4/1Bp5/4P3/5N2/PPPP1PPP/RNBQK2R"))  # b5 down
        sentio.occupied_squares(self._fen_to_occupied("rn1qkbnr/pp1bpppp/3p4/1Bp5/4P3/5N2/PPPP1PPP/RNBQK2R"))  # d7 down
        calls = [
            call("r2qkbnr/pp1npppp/3p4/2p5/4P3/5N2/PPPP1PPP/RNBQK2R"),
            call("rn1qkbnr/pp1Bpppp/3p4/2p5/4P3/5N2/PPPP1PPP/RNBQK2R"),
            call("rn1qkbnr/pp1bpppp/3p4/1Bp5/4P3/5N2/PPPP1PPP/RNBQK2R"),
        ]
        MockedParserCallback.board_update.assert_has_calls(calls)

    def _fen_to_occupied(self, board_fen: str) -> List[int]:
        board = chess.Board(board_fen + " w - - 0 1")
        squares = chess.SquareSet(board.occupied)
        result = [0] * 64
        for square in list(squares):
            result[to_square(square)] = 1
        return result


if __name__ == "__main__":
    unittest.main()
