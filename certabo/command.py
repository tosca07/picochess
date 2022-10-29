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


def set_leds(pos, is_reversed: bool):
    """
    Set LEDs according to `position`.
    :param pos: `position` array, field != 0 indicates a LED that should be on
    :param is_reversed: whether the colors on the board are reversed
    """
    leds = bytearray(8)
    for y in range(8):
        for x in range(8):
            if pos[y][x] != 0:
                square = (7 - y) * 8 + (7 - x)
                if is_reversed:
                    square = 63 - square
                _set_bit(leds, square, 1)
    return leds


def _set_bit(data: bytearray, pos: int, val: int):
    pos_byte = int(pos / 8)
    posBit = pos % 8
    oldByte = data[pos_byte]
    oldByte = (((0xFF7F >> posBit) & oldByte) & 0x00FF)
    newByte = ((val << (8 - (posBit + 1))) | oldByte)
    data[pos_byte] = newByte


def set_leds_off():
    return b'\x00\x00\x00\x00\x00\x00\x00\x00'


def set_leds_calibrate():
    return b'\xff\xff\x08\x00\x00\x08\xff\xff'
