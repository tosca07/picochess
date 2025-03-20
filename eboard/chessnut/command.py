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
                square = (7 - y) * 8 + x
                if is_reversed:
                    square = 63 - square
                _set_bit(leds, square, 1)

    prefix = bytearray(2)
    prefix[0] = 0x0A
    prefix[1] = 0x08
    return prefix + leds


def _set_bit(data: bytearray, pos: int, val: int):
    posByte = int(pos / 8)
    posBit = pos % 8
    oldByte = data[posByte]
    oldByte = ((0xFF7F >> posBit) & oldByte) & 0x00FF
    newByte = (val << (8 - (posBit + 1))) | oldByte
    data[posByte] = newByte


def set_led_off():
    return b"\x0a\x08\x00\x00\x00\x00\x00\x00\x00\x00"


def request_realtime_mode():
    return b"\x21\x01\x00"


def request_battery_status():
    return b"\x29\x01\x00"
