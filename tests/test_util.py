import unittest

from dgt.util import System, SystemLoop, EBoard, EBoardLoop


class TestSystemLoop(unittest.TestCase):

    def test_next(self):
        loop = SystemLoop()
        self.assertEqual(System.SOUND, loop.next(System.INFO))
        self.assertEqual(System.EBOARD, loop.next(System.DISPLAY))
        self.assertEqual(System.THEME, loop.next(System.EBOARD))
        self.assertEqual(System.POWER, loop.next(System.THEME))
        self.assertEqual(System.INFO, loop.next(System.POWER))
        self.assertEqual("errSystNext", loop.next("invalid item"))

    def test_prev(self):
        loop = SystemLoop()
        self.assertEqual(System.THEME, loop.prev(System.POWER))
        self.assertEqual(System.EBOARD, loop.prev(System.THEME))
        self.assertEqual(System.POWER, loop.prev(System.INFO))
        self.assertEqual(System.DISPLAY, loop.prev(System.EBOARD))
        self.assertEqual(System.SOUND, loop.prev(System.LANGUAGE))
        self.assertEqual(System.INFO, loop.prev(System.SOUND))
        self.assertEqual("errSystPrev", loop.prev("invalid item"))


class TestEBoardLoop(unittest.TestCase):

    def test_next(self):
        loop = EBoardLoop()
        self.assertEqual(EBoard.DGT, loop.next(EBoard.CHESSNUT))
        self.assertEqual(EBoard.NOEBOARD, loop.next(EBoard.DGT))
        self.assertEqual(EBoard.CERTABO, loop.next(EBoard.NOEBOARD))
        self.assertEqual("errEboardNext", loop.next("invalid item"))

    def test_prev(self):
        loop = EBoardLoop()
        self.assertEqual(EBoard.CHESSNUT, loop.prev(EBoard.DGT))
        self.assertEqual(EBoard.DGT, loop.prev(EBoard.NOEBOARD))
        self.assertEqual(EBoard.NOEBOARD, loop.prev(EBoard.CERTABO))
        self.assertEqual("errEboardPrev", loop.prev("invalid item"))


if __name__ == "__main__":
    unittest.main()
