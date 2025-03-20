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


def set_led(pos, is_reversed: bool):
    """
    Set LEDs according to `position`.
    :param pos: `position` array, field != 0 indicates a led that should be on
    :param is_reversed: whether the colors on the board are reversed
    """
    leds = bytearray(8)
    for y in range(8):
        for x in range(8):
            if pos[y][x] != 0:
                square = (7 - y) * 8 + 7 - x
                if is_reversed:
                    square = 63 - square
                _set_bit(leds, square, 1)

    prefix = bytearray(5)
    prefix[0] = 0x45
    prefix[1] = 0x4C
    prefix[2] = 0x80  # 50% brightness, red level
    prefix[3] = 0x0F  # blue level, green level
    prefix[4] = 0x00  # indicators of row 9
    postfix = bytearray(3)
    postfix[0] = 0x00  # indicators of row 0
    postfix[1] = 0x01  # no flash, clear previous
    postfix[2] = 0xFF  # permanent
    return prefix + leds + postfix


def _set_bit(data: bytearray, pos: int, val: int):
    posByte = int(pos / 8)
    posBit = pos % 8
    oldByte = data[posByte]
    oldByte = ((0xFF7F >> posBit) & oldByte) & 0x00FF
    newByte = (val << (8 - (posBit + 1))) | oldByte
    data[posByte] = newByte


def set_led_off():
    return b"\x45\x4c\x00\x0f\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01\xff"


def request_battery_status():
    return b"\x52\x42"


def request_board():
    return b"\x52\x50"


def request_board_updates():
    return b"\x43\x50\x49\x52\x51"
