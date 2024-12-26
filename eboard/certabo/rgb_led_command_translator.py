class RgbLedCommandTranslator:
    BOARD_SIZE = 8
    LEDS_PER_ROW = 9
    TOTAL_LEDS = 81
    COLORS_PER_LED = 3
    BRIGHTNESS = 0x40

    def __init__(self):
        pass

    def translate(self, command: bytearray) -> bytearray:
        result = [0] * (self.TOTAL_LEDS * self.COLORS_PER_LED)
        # Process each bit of the command
        for byteIndex in range(len(command)):
            currentByte = command[byteIndex]
            for bitIndex in range(8):
                if currentByte & (1 << bitIndex):
                    self._set_color_for_square(result, byteIndex * 8 + bitIndex, 0, 0, self.BRIGHTNESS)
        return self._add_start_end_bytes(result)

    def _set_color_for_square(self, ledValues, squareIndex, r, g, b):
        row = 7 - squareIndex // self.BOARD_SIZE
        col = 7 - squareIndex % self.BOARD_SIZE
        # Determine the indices of the LEDs for the given square
        baseIndex = (row * self.LEDS_PER_ROW + col) * self.COLORS_PER_LED
        ledIndices = [baseIndex, baseIndex + self.COLORS_PER_LED, baseIndex + self.LEDS_PER_ROW * self.COLORS_PER_LED,
                      baseIndex + self.LEDS_PER_ROW * self.COLORS_PER_LED + self.COLORS_PER_LED]
        # Set color for the four LEDs of the specified square
        for i in ledIndices:
            ledValues[i] = r
            ledValues[i + 1] = g
            ledValues[i + 2] = b

    def _add_start_end_bytes(self, ledValues) -> bytearray:
        result = [0] * (len(ledValues) + 4)
        result[0] = 255
        result[1] = 85
        result[2:2 + len(ledValues)] = ledValues
        result[-2] = 13
        result[-1] = 10
        return bytearray(result)
