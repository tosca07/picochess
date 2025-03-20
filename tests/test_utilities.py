import unittest

from utilities import get_engine_mame_par


class TestUtilities(unittest.TestCase):

    def test_engine_mame_par(self):
        self.assertEqual("-speed 1.0 -sound none", get_engine_mame_par(1.0))
        self.assertEqual("-speed 2.01", get_engine_mame_par(2.01, True))
        self.assertEqual("-speed 30 -sound none", get_engine_mame_par(0.009))
        self.assertEqual("-speed 30", get_engine_mame_par(0.009, True))


if __name__ == "__main__":
    unittest.main()
