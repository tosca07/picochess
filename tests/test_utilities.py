import unittest

from utilities import get_engine_rspeed_par


class TestUtilities(unittest.TestCase):

    def test_engine_rspeed_par(self):
        self.assertEqual('-speed 1.0', get_engine_rspeed_par(1.0))
        self.assertEqual('-speed 2.01', get_engine_rspeed_par(2.01))
        self.assertEqual('-nothrottle', get_engine_rspeed_par(0.009))


if __name__ == '__main__':
    unittest.main()
