# Original copyright:
#
# MIT License
#
# Copyright (c) 2018 Dominik Schlösser
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""
Helper functions for the Chess Link protocol for character-based odd-parity and
message-block-parity.

The chess link protocol sends ASCII messages. Each ASCII character gets an additional
odd-parity-bit. Each block of ASCII+odd-parity bytes gets an additional block parity.

Details of the Chess Link protocol are documented in
`magic-board.md <https://github.com/domschl/python-mchess/blob/master/mchess/magic-board.md>`_.
"""

import logging

protocol_replies = {"v": 7, "s": 67, "l": 3, "x": 3, "w": 7, "r": 7}


logger = logging.getLogger(__name__)


def add_odd_par(b):
    """
    The chess link protocol is 7-Bit ASCII. This adds an odd-parity-bit to an ASCII char

    :param b: an ASCII character (0..127)
    :returns: a byte (0..255) with odd parity in most significant bit.
    """
    byte = ord(b) & 127
    par = 1
    for _ in range(7):
        bit = byte & 1
        byte = byte >> 1
        par = par ^ bit
    if par == 1:
        byte = ord(b) | 128
    else:
        byte = ord(b) & 127
    return byte


def hexd(digit):
    """
    Returns a hex digit '0'..'F' for an integer 0..15

    :param digit: integer 0..15
    :returns: an ASCII hex character '0'..'F'
    """
    if digit < 10:
        return chr(ord("0") + digit)
    else:
        return chr(ord("A") - 10 + digit)


def hex2(num):
    """
    Convert integer to 2-digit hex string. Most numeric parameters and the block CRC
    are encoded as such 2-digit hex-string.

    :param num: uint_8 integer 0..255
    :returns: Returns a 2-digit hex code '00'..'FF'
    """
    d1 = num // 16
    d2 = num % 16
    s = hexd(d1) + hexd(d2)
    return s


def check_block_crc(msg):
    """
    Chess link messages consist of 7-bit-ASCII characters with odd parity. At the end of each
    message, an additional block-parity is added. Valid chess link messages must have correct odd
    parity for each character and a valid block parity at the end.

    :param msg: a byte array with the message.
    :returns: True, if the last two bytes of msg contain a correct CRC, False otherwise.
    """
    if len(msg) > 2:
        gpar = 0
        for b in msg[:-2]:
            gpar = gpar ^ ord(b)
        if msg[-2] + msg[-1] != hex2(gpar):
            logger.warning(f"CRC error rep={msg} CRCs: {ord(msg[-2])}!={hex2(gpar)}")
            return False
        else:
            return True
    else:
        logger.warning(f"Message {msg} too short for CRC check")
        return False


def add_block_crc(msg):
    """Add block parity at the end of the message

    :param msg: a message byte array (each byte must have already been encoded with odd parity).
                This function adds two bytes of block CRC at the end of the message.
    :param msg: byte array with a message (incl. odd-parity bits set already)
    :return: two byte longer message that includes 2 CRC bytes.
    """
    gpar = 0
    for b in msg:
        gpar = gpar ^ ord(b)
    msg = msg + hex2(gpar)
    return msg
