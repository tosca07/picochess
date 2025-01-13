#!/usr/bin/env python3

import binascii
import unittest

import eboard.ichessone.command as cmd


class TestCommand(unittest.TestCase):

    def test_set_led(self):
        position = [[0 for _ in range(8)] for _ in range(8)]
        position[2][2] = 1
        arr = cmd.set_led(position, False)
        self.assertEqual(binascii.hexlify(arr), b'454c800f0000000000000400000001ff')

    def test_set_leds_e2_e4(self):
        position = [[0 for _ in range(8)] for _ in range(8)]
        position[1][4] = 1  # e2
        position[3][4] = 1  # e4
        arr = cmd.set_led(position, False)
        self.assertEqual(binascii.hexlify(arr), b'454c800f0000000000100010000001ff')

    def test_set_led_initial_position_reversed(self):
        position = [[0 for _ in range(8)] for _ in range(8)]
        position[2][2] = 1
        arr = cmd.set_led(position, True)
        self.assertEqual(binascii.hexlify(arr), b'454c800f0000002000000000000001ff')


if __name__ == '__main__':
    unittest.main()
