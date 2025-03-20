import unittest

from picotutor import PicoTutor


class TestPicotutor(unittest.TestCase):

    def test_find_longest_matching_opening_kings_pawn(self):
        tutor = PicoTutor(i_engine_path="engines/x86_64/a-stock8")
        opening_name, _, _ = tutor._find_longest_matching_opening("e4")
        self.assertEqual(opening_name, "Kings Pawn")

    def test_find_longest_matching_opening_open_game(self):
        tutor = PicoTutor(i_engine_path="engines/x86_64/a-stock8")
        opening_name, _, _ = tutor._find_longest_matching_opening("e4 e5 Nf3 Nc6")
        self.assertEqual(opening_name, "Open Game")

    def test_find_longest_matching_opening_italian_game(self):
        tutor = PicoTutor(i_engine_path="engines/x86_64/a-stock8")
        opening_name, _, _ = tutor._find_longest_matching_opening("e4 e5 Nf3 Nc6 Bc4")
        self.assertEqual(opening_name, "Italian Game")

    def test_find_longest_matching_opening_can_be_called_multiple_times(self):
        tutor = PicoTutor(i_engine_path="engines/x86_64/a-stock8")
        opening_name, _, _ = tutor._find_longest_matching_opening("e4")
        self.assertEqual(opening_name, "Kings Pawn")

        opening_name, _, _ = tutor._find_longest_matching_opening("e4 e5")
        self.assertEqual(opening_name, "Open Game")
