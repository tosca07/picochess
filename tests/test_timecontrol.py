import unittest

from timecontrol import TimeControl, TimeMode


class TestTimeControl(unittest.TestCase):

    def test_uci_returns_int_for_movestogo(self):
        tc = TimeControl(mode=TimeMode.BLITZ, moves_to_go=20)
        tc.set_clock_times(5, 5, 10)
        self.assertEqual(10, tc.uci()["movestogo"])
