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

import binascii
import unittest

import certabo.command as cmd


class TestCommand(unittest.TestCase):

    def test_set_leds_d2_d4(self):
        position = [[0 for _ in range(8)] for _ in range(8)]
        position[1][3] = 1  # d2
        position[3][3] = 1  # d4
        arr = cmd.set_leds(position, False)
        self.assertEqual(binascii.hexlify(arr), b"0000000008000800")

    def test_set_leds_e2_e4(self):
        position = [[0 for _ in range(8)] for _ in range(8)]
        position[1][4] = 1  # e2
        position[3][4] = 1  # e4
        arr = cmd.set_leds(position, False)
        self.assertEqual(binascii.hexlify(arr), b"0000000010001000")

    def test_set_leds_d2_d4_reversed(self):
        position = [[0 for _ in range(8)] for _ in range(8)]
        position[1][3] = 1  # d2
        position[3][3] = 1  # d4
        arr = cmd.set_leds(position, True)
        self.assertEqual(binascii.hexlify(arr), b"0010001000000000")


if __name__ == "__main__":
    unittest.main()
