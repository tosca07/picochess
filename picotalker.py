# Copyright (C) 2013-2018 Jean-Francois Romang (jromang@posteo.de)
#                         Shivkumar Shivaji ()
#                         Jürgen Précour (LocutusOfPenguin@posteo.de)
#
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

# This version uses sox. It does not use pygame or ogg123 -RR
# To install sox use:
# sudo apt install sox

###########################################################################
# Molli: Added new framework for voice comments based on different events
#        (to be activated via pico voice menue and additional audio files)
###########################################################################

from typing import Optional
import threading
import logging
import subprocess
import queue
from pathlib import Path
from shutil import which
from random import randint
import os
import time

import chess  # type: ignore
from utilities import DisplayMsg
from dgt.api import Message
from dgt.util import GameResult, PlayMode, Voice, EBoard


class PicoTalker(object):

    """Handle the human speaking of events."""

    def __init__(self, localisation_id_voice, speed_factor: float):
        self.voice_path = None
        self.speed_factor = 1.0
        self.set_speed_factor(speed_factor)
        self.sound = None
        try:
            (localisation_id, voice_name) = localisation_id_voice.split(':')
            voice_path = 'talker/voices/' + localisation_id + '/' + voice_name
            if Path(voice_path).exists():
                self.voice_path = voice_path
            else:
                logging.warning('voice path [%s] doesnt exist', voice_path)
        except ValueError:
            logging.warning('not valid voice parameter')

    def set_speed_factor(self, speed_factor: float):
        """Set the speed voice factor."""
        self.speed_factor = speed_factor if which('play') else 1.0  # check for "sox" package

    def talk(self, sounds):
        """Speak out the sound part by using sox play."""
        if not self.voice_path:
            logging.debug('picotalker turned off')
            return False

        vpath = self.voice_path
        result = False
        for part in sounds:
            voice_file = vpath + '/' + part
            if Path(voice_file).is_file():
                command = ['play', voice_file, 'tempo', str(self.speed_factor)]
                try:  # use blocking call
                    subprocess.call(command, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    result = True
                except OSError as os_exc:
                    logging.warning('OSError: %s => turn voice OFF', os_exc)
                    self.voice_path = None
                    return False
            else:
                logging.warning('voice file not found %s', voice_file)
        return result


class PicoTalkerDisplay(DisplayMsg, threading.Thread):

    """Listen on messages for talking."""

    USER = 'user'
    COMPUTER = 'computer'
    SYSTEM = 'system'
    BEEPER = 'beeper'

    c_taken = False
    c_castle = False
    c_knight = False
    c_rook = False
    c_king = False
    c_bishop = False
    c_pawn = False
    c_queen = False
    c_check = False
    c_mate = False
    c_stalemate = False
    c_draw = False

    # add voice comment-factor
    def __init__(self, user_voice: str, computer_voice: str, speed_factor: int, setpieces_voice: bool,
                 comment_factor: int, beep: bool, eboard_type: EBoard):
        """
        Initialize a PicoTalkerDisplay with voices for the user and/or computer players.

        :param user_voice: The voice to use for the user (eg. en:al).
        :param computer_voice: The voice to use for the computer (eg. en:christina).
        """
        super(PicoTalkerDisplay, self).__init__()
        self.user_picotalker = None
        self.computer_picotalker: Optional[PicoTalker] = None
        self.beeper_picotalker = None
        self.eboard_type = eboard_type
        self.speed_factor = (90 + (speed_factor % 10) * 5) / 100  # used by sox
        self.play_mode = PlayMode.USER_WHITE
        self.low_time = False
        self.play_game = None  # saves the game after a computer move - used for "setpieces" to speak the move again
        self.setpieces_voice = setpieces_voice
        self.c_no_beforecmove = 0
        self.c_no_beforeumove = 0
        self.c_no_cmove = 0
        self.c_no_umove = 0
        self.c_no_poem = 0
        self.c_no_chat = 0
        self.c_no_newgame = 0
        self.c_no_rmove = 0
        self.c_no_uwin = 0
        self.c_no_uloose = 0
        self.c_no_ublack = 0
        self.c_no_uwhite = 0
        self.c_no_start = 0
        self.c_no_name = 0
        self.c_no_shutdown = 0
        self.c_no_takeback = 0
        self.c_no_taken = 0
        self.c_no_check = 0
        self.c_no_mate = 0
        self.c_no_stalemate = 0
        self.c_no_draw = 0
        self.c_no_castle = 0
        self.c_no_king = 0
        self.c_no_queen = 0
        self.c_no_rook = 0
        self.c_no_bishop = 0
        self.c_no_knight = 0
        self.c_no_pawn = 0

        self.c_comment_factor = comment_factor
        self.beep_on = beep

        if user_voice:
            logging.debug('creating user voice: [%s]', str(user_voice))
            self.set_user(PicoTalker(user_voice, self.speed_factor))
        if computer_voice:
            logging.debug('creating computer voice: [%s]', str(computer_voice))
            self.set_computer(PicoTalker(computer_voice, self.speed_factor))
        if beep:
            beeper_sound = 'en:beeper'
            logging.debug('creating beeper sound: [%s]', str(beeper_sound))
            self.set_beeper(PicoTalker(beeper_sound, self.speed_factor))

    def calc_no_group_comments(self, filestring: str):
        """
        molli: Calculate number of generic filestring files in voice folder
        """
        c_group_no = 0

        if self.computer_picotalker is not None:
            path = self.computer_picotalker.voice_path
            for file in os.listdir(path):
                if file.startswith(filestring):
                    c_group_no += 1

        return c_group_no

    def set_computer(self, picotalker):
        """Set the computer talker."""
        self.computer_picotalker = picotalker
        """molli: set correct number and assign it to voice group comment variables"""
        self.c_no_beforecmove = self.calc_no_group_comments('f_beforecmove')
        self.c_no_beforeumove = self.calc_no_group_comments('f_beforeumove')
        self.c_no_cmove = self.calc_no_group_comments('f_cmove')
        self.c_no_umove = self.calc_no_group_comments('f_umove')
        self.c_no_poem = self.calc_no_group_comments('f_poem')
        self.c_no_chat = self.calc_no_group_comments('f_chat')
        self.c_no_newgame = self.calc_no_group_comments('f_newgame')
        self.c_no_rmove = self.calc_no_group_comments('f_rmove')
        self.c_no_uwin = self.calc_no_group_comments('f_uwin')
        self.c_no_uloose = self.calc_no_group_comments('f_uloose')
        self.c_no_ublack = self.calc_no_group_comments('f_ublack')
        self.c_no_uwhite = self.calc_no_group_comments('f_uwhite')
        self.c_no_start = self.calc_no_group_comments('f_start')
        self.c_no_name = self.calc_no_group_comments('f_name')
        self.c_no_shutdown = self.calc_no_group_comments('f_shutdown')
        self.c_no_takeback = self.calc_no_group_comments('f_takeback')
        self.c_no_taken = self.calc_no_group_comments('f_taken')
        self.c_no_check = self.calc_no_group_comments('f_check')
        self.c_no_mate = self.calc_no_group_comments('f_mate')
        self.c_no_stalemate = self.calc_no_group_comments('f_stalemate')
        self.c_no_draw = self.calc_no_group_comments('f_draw')
        self.c_no_castle = self.calc_no_group_comments('f_castle')
        self.c_no_king = self.calc_no_group_comments('f_king')
        self.c_no_queen = self.calc_no_group_comments('f_queen')
        self.c_no_rook = self.calc_no_group_comments('f_rook')
        self.c_no_bishop = self.calc_no_group_comments('f_bishop')
        self.c_no_knight = self.calc_no_group_comments('f_knight')
        self.c_no_pawn = self.calc_no_group_comments('f_pawn')

    def set_user(self, picotalker):
        """Set the user talker."""
        self.user_picotalker = picotalker

    def set_beeper(self, picotalker):
        """Set the beeper talker."""
        self.beeper_picotalker = picotalker

    def set_factor(self, speed_factor):
        """Set speech factor."""
        if self.computer_picotalker:
            self.computer_picotalker.set_speed_factor(speed_factor)
        if self.user_picotalker:
            self.user_picotalker.set_speed_factor(speed_factor)
        if self.beeper_picotalker:
            self.beeper_picotalker.set_speed_factor(speed_factor)

    def talk(self, sounds, dev=SYSTEM):
        if self.low_time:
            return
        if False:  # switch-case
            pass
        elif dev == self.USER:
            if self.user_picotalker:
                self.user_picotalker.talk(sounds)
        elif dev == self.COMPUTER:
            if self.computer_picotalker:
                self.computer_picotalker.talk(sounds)
        elif dev == self.BEEPER:
            if self.beeper_picotalker:
                self.beeper_picotalker.talk(sounds)
        elif dev == self.SYSTEM:
            if self.computer_picotalker:
                self.computer_picotalker.talk(sounds)
                return
            if self.user_picotalker:
                self.user_picotalker.talk(sounds)

    def get_total_cgroup(self, c_group: str):
        # molli: define number of possible comments in differrent event groups
        #        together with a probability factor one can control how
        #        often a group comment will be spoken
        c_number = 0
        c_prob = 0
        if c_group == 'beforeumove':
            c_prob = 10
            c_number = self.c_no_beforeumove
        elif c_group == 'beforecmove':
            c_prob = 10
            c_number = self.c_no_beforecmove
        elif c_group == 'cmove':
            c_prob = 20
            c_number = self.c_no_cmove
        elif c_group == 'umove':
            c_prob = 20
            c_number = self.c_no_umove
        elif c_group == 'poem':
            c_prob = 20
            c_number = self.c_no_poem
        elif c_group == 'chat':
            c_prob = 20
            c_number = self.c_no_chat
        elif c_group == 'newgame':
            c_prob = 100
            c_number = self.c_no_newgame
        elif c_group == 'rmove':
            c_prob = 20
            c_number = self.c_no_rmove
        elif c_group == 'uwin':
            c_prob = 100
            c_number = self.c_no_uwin
        elif c_group == 'uloose':
            c_prob = 100
            c_number = self.c_no_uloose
        elif c_group == 'ublack':
            c_prob = 70
            c_number = self.c_no_ublack
        elif c_group == 'uwhite':
            c_prob = 70
            c_number = self.c_no_uwhite
        elif c_group == 'start':
            c_prob = 100
            c_number = self.c_no_start
        elif c_group == 'name':
            c_prob = 100
            c_number = self.c_no_name
        elif c_group == 'shutdown':
            c_prob = 100
            c_number = self.c_no_shutdown
        elif c_group == 'takeback':
            c_prob = 100
            c_number = self.c_no_takeback
        elif c_group == 'taken':
            c_prob = 50
            c_number = self.c_no_taken
        elif c_group == 'check':
            c_prob = 50
            c_number = self.c_no_check
        elif c_group == 'mate':
            c_prob = 100
            c_number = self.c_no_mate
        elif c_group == 'stalemate':
            c_prob = 100
            c_number = self.c_no_stalemate
        elif c_group == 'draw':
            c_prob = 100
            c_number = self.c_no_draw
        elif c_group == 'castle':
            c_prob = 50
            c_number = self.c_no_castle
        elif c_group == 'king':
            c_prob = 50
            c_number = self.c_no_king
        elif c_group == 'queen':
            c_prob = 50
            c_number = self.c_no_queen
        elif c_group == 'rook':
            c_prob = 50
            c_number = self.c_no_rook
        elif c_group == 'bishop':
            c_prob = 50
            c_number = self.c_no_bishop
        elif c_group == 'knight':
            c_prob = 50
            c_number = self.c_no_knight
        elif c_group == 'pawn':
            c_prob = 50
            c_number = self.c_no_pawn
        else:
            c_prob = 0
            c_number = 0

        return c_number, c_prob

    def calc_comment(self, c_group):
        # molli: define number of possible comments in differrent event groups
        #        together with a probability factor one can control how
        #        often a group comment will be spoken
        talkfile = ''
        c_rand_str = ''
        c_rand = 0
        c_number = 0
        c_prob = 0
        c_total = 0

        # get total numbers of possible comments for this event group in dependence of
        # selected comment speech and lanuage

        c_total, c_prob = self.get_total_cgroup(c_group)

        if c_prob == 0:
            return talkfile
        # consider probability factor from picochess.ini
        if c_group == 'start' or c_group == 'name' or c_group == 'shutdown':
            # don't use factor for these events
            c_prob = c_prob
        else:
            c_prob = round(c_prob * (self.c_comment_factor / 100))

        c_number = round(c_total * (100 / c_prob))

        if c_number > 1:
            c_rand = randint(1, c_number)
        else:
            c_rand = c_number

        c_rand_str = str(c_rand)

        if c_rand == 0:
            talkfile = ''
        elif c_rand <= c_total:
            talkfile = 'f_' + c_group + c_rand_str + '.ogg'
        else:
            talkfile = ''

        return talkfile

    def comment(self, c_group):
        # molli: define number of possible comments in differrent event groups
        #        together with a probability factor one can control how
        #        often a group comment will be spoke
        talkfile = ''

        # get total numbers of possible comments for this event group in dependence of
        # selected comment speech and lanuage

        talkfile = self.calc_comment(c_group)

        if talkfile != '':
            self.talk([talkfile])

    def move_comment(self):
        talkfile = ''

        if PicoTalkerDisplay.c_taken:
            talkfile = self.calc_comment('taken')
        elif PicoTalkerDisplay.c_bishop:
            talkfile = self.calc_comment('bishop')
        elif PicoTalkerDisplay.c_queen:
            talkfile = self.calc_comment('queen')
        elif PicoTalkerDisplay.c_knight:
            talkfile = self.calc_comment('knight')
        elif PicoTalkerDisplay.c_rook:
            talkfile = self.calc_comment('rook')
        elif PicoTalkerDisplay.c_king:
            talkfile = self.calc_comment('king')
        elif PicoTalkerDisplay.c_castle:
            talkfile = self.calc_comment('castle')
        elif PicoTalkerDisplay.c_pawn:
            talkfile = self.calc_comment('pawn')
        else:
            # pawn piesces are not spoken
            # (no flag is set) => but we comment them!
            talkfile = self.calc_comment('pawn')

        if talkfile != '':
            self.talk([talkfile])

        if PicoTalkerDisplay.c_mate:
            talkfile = ''
        elif PicoTalkerDisplay.c_stalemate:
            talkfile = ''
        elif PicoTalkerDisplay.c_draw:
            talkfile = ''
        elif PicoTalkerDisplay.c_check:
            talkfile = self.calc_comment('check')
        else:
            talkfile = ''

        if talkfile != '':
            self.talk([talkfile])

    def say_squarepiece(self, fen_result):
        logging.debug('molli: talker fen_result = %s', fen_result)

        piece_parts = {
            'K': 't_king.ogg',
            'B': 't_bishop.ogg',
            'N': 't_knight.ogg',
            'R': 't_rook.ogg',
            'Q': 't_queen.ogg',
            'P': 't_pawn.ogg',
        }

        square_parts = {
            'a': 't_a.ogg',
            'b': 't_b.ogg',
            'c': 't_c.ogg',
            'd': 't_d.ogg',
            'e': 't_e.ogg',
            'f': 't_f.ogg',
            'g': 't_g.ogg',
            'h': 't_h.ogg',
            '1': 't_1.ogg',
            '2': 't_2.ogg',
            '3': 't_3.ogg',
            '4': 't_4.ogg',
            '5': 't_5.ogg',
            '6': 't_6.ogg',
            '7': 't_7.ogg',
            '8': 't_8.ogg'
        }

        sound_file = ''
        voice_parts = []
        rank = fen_result[-2]
        file = fen_result[-1]
        square_str = rank
        square_str = square_str + ' ' + file

        logging.debug('molli: talker square = %s', square_str)

        if len(fen_result) > 2:

            piece = fen_result[0]
            if piece.islower():
                voice_parts += ['black.ogg']
                piece = piece.upper()
            else:
                voice_parts += ['white.ogg']

            logging.debug('molli: talker piece = %s', piece)

            try:
                sound_file = piece_parts[piece]
            except KeyError:
                sound_file = ''
            if sound_file:
                voice_parts += [sound_file]

            voice_parts += ['on.ogg']

            for part in square_str:
                try:
                    sound_file = square_parts[part]
                except KeyError:
                    sound_file = ''
                if sound_file:
                    voice_parts += [sound_file]
        else:
            for part in square_str:
                try:
                    sound_file = square_parts[part]
                except KeyError:
                    sound_file = ''
                if sound_file:
                    voice_parts += [sound_file]

        logging.debug('molli: talker voice_parts = %s', voice_parts)
        return voice_parts

    def run(self):
        """Start listening for Messages on our queue and generate speech as appropriate."""

        previous_move = chess.Move.null()  # Ignore repeated broadcasts of a move
        last_pos_dir = ''
        logging.info('msg_queue ready')
        while True:
            try:
                # Check if we have something to say
                message = self.msg_queue.get()

                if False:  # switch-case
                    pass
                elif isinstance(message, Message.ENGINE_FAIL):
                    logging.debug('announcing ENGINE_FAIL')
                    self.talk(['error.ogg'])

                elif isinstance(message, Message.START_NEW_GAME):
                    last_pos_dir = ''
                    if message.newgame:
                        logging.debug('announcing START_NEW_GAME')
                        self.talk(['new_game.ogg'], self.BEEPER)
                        self.talk(['newgame.ogg'])
                        self.play_game = None
                        self.comment('newgame')
                        self.comment('uwhite')
                        previous_move = chess.Move.null()

                elif isinstance(message, Message.COMPUTER_MOVE):
                    logging.debug('molli: before announcing COMPUTER_MOVE [%s]', message.move)
                    if message.move and message.game:
                        game_copy = message.game.copy()
                        if game_copy.board_fen() == chess.STARTING_BOARD_FEN:
                            previous_move = chess.Move.null()
                        if message.move != previous_move:
                            logging.debug('announcing COMPUTER_MOVE [%s]', message.move)
                            game_copy.push(message.move)
                            self.talk(['computer_move.ogg'], self.BEEPER)
                            if self.eboard_type == EBoard.NOEBOARD:
                                self.talk(['player_move.ogg'], self.BEEPER)
                            self.comment('beforecmove')
                            self.talk(self.say_last_move(game_copy), self.COMPUTER)
                            self.move_comment()
                            self.comment('cmove')
                            previous_move = message.move
                            self.play_game = game_copy

                elif isinstance(message, Message.COMPUTER_MOVE_DONE):
                    self.play_game = None
                    if self.eboard_type != EBoard.NOEBOARD:
                        self.talk(['player_move.ogg'], self.BEEPER)
                    self.comment('chat')

                elif isinstance(message, Message.USER_MOVE_DONE):
                    if message.move and message.game and message.move != previous_move:
                        logging.debug('announcing USER_MOVE_DONE [%s]', message.move)
                        self.talk(['player_move.ogg'], self.BEEPER)
                        self.comment('beforeumove')
                        self.talk(self.say_last_move(message.game), self.USER)
                        previous_move = message.move
                        self.play_game = None
                        self.comment('umove')
                        self.comment('poem')

                elif isinstance(message, Message.REVIEW_MOVE_DONE):
                    if message.move and message.game and message.move != previous_move:
                        logging.debug('announcing REVIEW_MOVE_DONE [%s]', message.move)
                        self.talk(['player_move.ogg'], self.BEEPER)
                        self.talk(self.say_last_move(message.game), self.USER)
                        previous_move = message.move
                        self.play_game = None  # @todo why thats not set in dgtdisplay?

                elif isinstance(message, Message.GAME_ENDS):
                    previous_move = chess.Move.null()
                    last_pos_dir = ''
                    if message.result == GameResult.OUT_OF_TIME:
                        logging.debug('announcing GAME_ENDS/TIME_CONTROL')
                        wins = 'whitewins.ogg' if message.game.turn == chess.BLACK else 'blackwins.ogg'
                        self.talk(['timelost.ogg', wins])
                        if wins == 'whitewins.ogg':
                            if self.play_mode == PlayMode.USER_WHITE:
                                self.comment('uwin')
                            else:
                                self.comment('uloose')
                        else:
                            if self.play_mode == PlayMode.USER_BLACK:
                                self.comment('uwin')
                            else:
                                self.comment('uloose')
                    elif message.result == GameResult.INSUFFICIENT_MATERIAL:
                        logging.debug('announcing GAME_ENDS/INSUFFICIENT_MATERIAL')
                        self.talk(['material.ogg', 'draw.ogg'])
                        self.comment('draw')
                    elif message.result == GameResult.MATE:
                        logging.debug('announcing GAME_ENDS/MATE')
                        self.comment('mate')
                        if message.game.turn == chess.BLACK:
                            # white wins
                            if self.play_mode == PlayMode.USER_WHITE:
                                self.talk(['checkmate.ogg'])
                                self.talk(['whitewins.ogg'])
                                self.comment('uwin')
                            else:
                                self.comment('uloose')
                        else:
                            # black wins
                            if self.play_mode == PlayMode.USER_BLACK:
                                self.talk(['checkmate.ogg'])
                                self.talk(['blackwins.ogg'])
                                self.comment('uwin')
                            else:
                                self.comment('uloose')
                    elif message.result == GameResult.STALEMATE:
                        logging.debug('announcing GAME_ENDS/STALEMATE')
                        self.talk(['stalemate.ogg'])
                        self.comment('stalemate')
                    elif message.result == GameResult.ABORT:
                        logging.debug('announcing GAME_ENDS/ABORT')
                        self.talk(['abort.ogg'])
                    elif message.result == GameResult.DRAW:
                        logging.debug('announcing GAME_ENDS/DRAW')
                        self.talk(['draw.ogg'])
                        self.comment('draw')
                    elif message.result == GameResult.WIN_WHITE:
                        logging.debug('announcing GAME_ENDS/WHITE_WIN')
                        self.talk(['whitewins.ogg'])
                        if self.play_mode == PlayMode.USER_WHITE:
                            self.comment('uwin')
                        else:
                            self.comment('uloose')
                    elif message.result == GameResult.WIN_BLACK:
                        logging.debug('announcing GAME_ENDS/BLACK_WIN')
                        self.talk(['blackwins.ogg'])
                        if self.play_mode == PlayMode.USER_BLACK:
                            self.comment('uwin')
                        else:
                            self.comment('uloose')
                    elif message.result == GameResult.FIVEFOLD_REPETITION:
                        logging.debug('announcing GAME_ENDS/FIVEFOLD_REPETITION')
                        self.talk(['repetition.ogg', 'draw.ogg'])
                        self.comment('draw')
                    self.talk(['bell.ogg'], self.BEEPER)

                elif isinstance(message, Message.TAKE_BACK):
                    logging.debug('announcing TAKE_BACK')
                    self.talk(['takeback.ogg'])
                    self.play_game = None
                    previous_move = chess.Move.null()
                    self.comment('takeback')

                elif isinstance(message, Message.TIME_CONTROL):
                    logging.debug('announcing TIME_CONTROL')
                    self.talk(['confirm.ogg'], self.BEEPER)
                    self.talk(['oktime.ogg'])

                elif isinstance(message, Message.INTERACTION_MODE):
                    logging.debug('announcing INTERACTION_MODE')
                    self.talk(['okmode.ogg'])

                elif isinstance(message, Message.LEVEL):
                    if message.do_speak:
                        logging.debug('announcing LEVEL')
                        self.talk(['oklevel.ogg'])
                    else:
                        logging.debug('dont announce LEVEL cause its also an engine message')

                elif isinstance(message, Message.OPENING_BOOK):
                    logging.debug('announcing OPENING_BOOK')
                    self.talk(['okbook.ogg'])

                elif isinstance(message, Message.ENGINE_READY):
                    logging.debug('announcing ENGINE_READY')
                    self.talk(['confirm.ogg'], self.BEEPER)
                    self.talk(['okengine.ogg'])

                elif isinstance(message, Message.PLAY_MODE):
                    logging.debug('announcing PLAY_MODE')
                    self.play_mode = message.play_mode
                    userplay = 'userblack.ogg' if message.play_mode == PlayMode.USER_BLACK else 'userwhite.ogg'
                    self.talk([userplay])
                    if message.play_mode == PlayMode.USER_BLACK:
                        self.comment('ublack')
                    else:
                        self.comment('uwhite')

                elif isinstance(message, Message.STARTUP_INFO):
                    self.play_mode = message.info['play_mode']
                    logging.debug('announcing PICOCHESS')
                    self.talk(['picoChess.ogg'], self.BEEPER)
                    self.talk(['picoChess.ogg'])
                    previous_move = chess.Move.null()
                    last_pos_dir = ''
                    self.comment('start')
                    self.comment('name')

                elif isinstance(message, Message.CLOCK_TIME):
                    self.low_time = message.low_time
                    if self.low_time:
                        logging.debug('time too low, disable voice - w: %i, b: %i', message.time_white,
                                      message.time_black)

                elif isinstance(message, Message.ALTERNATIVE_MOVE):
                    self.play_mode = message.play_mode
                    self.play_game = None
                    self.talk(['alternative_move.ogg'])

                elif isinstance(message, Message.SYSTEM_SHUTDOWN):
                    logging.debug('announcing SHUTDOWN')
                    self.talk(['goodbye.ogg'])
                    self.comment('shutdown')

                elif isinstance(message, Message.SYSTEM_REBOOT):
                    logging.debug('announcing REBOOT')
                    self.talk(['pleasewait.ogg'])
                    self.comment('shutdown')
                    time.sleep(3)

                elif isinstance(message, Message.MOVE_RETRY):
                    logging.debug('announcing MOVE_RETRY')
                    self.talk(['retry_move.ogg'])

                elif isinstance(message, Message.MOVE_WRONG):
                    logging.debug('announcing MOVE_WRONG')
                    self.talk(['wrong_move.ogg'])

                elif isinstance(message, Message.ONLINE_LOGIN):
                    logging.debug('announcing ONLINE_LOGIN')
                    self.talk(['online_login.ogg'])

                elif isinstance(message, Message.SEEKING):
                    logging.debug('announcing SEEKING')
                    self.talk(['seeking.ogg'])

                elif isinstance(message, Message.ONLINE_NAMES):
                    logging.debug('announcing ONLINE_NAMES')
                    self.talk(['opponent_found.ogg'])

                elif isinstance(message, Message.RESTORE_GAME):
                    logging.debug('announcing RESTORE_GAME')
                    self.talk(['last_game_restored.ogg'])

                elif isinstance(message, Message.ENGINE_SETUP):
                    logging.debug('announcing ENGINE_SETUP')
                    self.talk(['engine_setup.ogg'])

                elif isinstance(message, Message.ONLINE_FAILED):
                    self.talk(['server_error.ogg'])

                elif isinstance(message, Message.ONLINE_USER_FAILED):
                    self.talk(['login_error.ogg'])

                elif isinstance(message, Message.ONLINE_NO_OPPONENT):
                    self.talk(['no_opponent.ogg'])

                elif isinstance(message, Message.LOST_ON_TIME):
                    self.talk(['timelost.ogg'])

                elif isinstance(message, Message.POSITION_FAIL):
                    logging.debug('molli: talker orig. fen_result = %s', message.fen_result)
                    if last_pos_dir != message.fen_result:
                        last_pos_dir = message.fen_result
                        if 'clear' in message.fen_result:
                            fen_str = message.fen_result[-2:]
                            self.talk(['remove.ogg'])
                            self.talk(self.say_squarepiece(fen_str))
                        elif 'put' in message.fen_result:
                            fen_str = message.fen_result[-4:]
                            self.talk(['put.ogg'])
                            self.talk(self.say_squarepiece(fen_str))
                        else:
                            pass

                elif isinstance(message, Message.PICOTUTOR_MSG):
                    if '??' == message.eval_str:
                        self.talk(['picotutor.ogg'], self.BEEPER)
                        self.talk(['picotutor_notify.ogg'])
                        self.talk(['verybadmove.ogg'])
                    elif '?' == message.eval_str:
                        self.talk(['picotutor_notify.ogg'])
                        self.talk(['badmove.ogg'])
                    elif '!?' == message.eval_str:
                        self.talk(['picotutor_notify.ogg'])
                        self.talk(['interestingmove.ogg'])
                    elif '!!' == message.eval_str:
                        self.talk(['picotutor_notify.ogg'])
                        self.talk(['verygoodmove.ogg'])
                    elif '!' == message.eval_str:
                        self.talk(['picotutor_notify.ogg'])
                        self.talk(['goodmove.ogg'])
                    elif '?!' == message.eval_str:
                        self.talk(['picotutor_notify.ogg'])
                        self.talk(['dubiousmove.ogg'])
                    elif 'ER' == message.eval_str:
                        self.talk(['picotutor_notify.ogg'])
                        self.talk(['error.ogg'])
                    elif 'ACTIVE' in message.eval_str:
                        self.talk(['picotutor_notify.ogg'])
                        self.talk(['picotutor_enabled.ogg'])
                    elif 'ANALYSIS' in message.eval_str:
                        self.talk(['picotutor_notify.ogg'])
                        self.talk(['picotutor_analysis.ogg'])
                    elif 'HINT' in message.eval_str:
                        self.talk(['picotutor_hintmove.ogg'])
                        self.talk(self.say_tutor_move(message.game))
                    elif 'THREAT' in message.eval_str:
                        self.talk(['picotutor_threatmove.ogg'])
                        self.talk(self.say_tutor_move(message.game))
                    elif 'POSOK' in message.eval_str:
                        last_pos_dir = ''
                        self.talk(['confirm.ogg'], self.BEEPER)
                        self.talk(['ok.ogg'])
                    elif 'POS' in message.eval_str:
                        score = message.score
                        if abs(score) <= 1:
                            self.talk(['picotutor_equal_position.ogg'])
                        elif score > 3:
                            self.talk(['picotutor_verygood_position.ogg'])
                        elif score > 1 and score < 3:
                            self.talk(['picotutor_good_position.ogg'])
                        elif score < -3:
                            self.talk(['picotutor_verybad_position.ogg'])
                        elif score > -3 and score < -1:
                            self.talk(['picotutor_bad_position.ogg'])
                    elif 'BEST' in message.eval_str:
                        self.talk(['picotutor_best_move.ogg'])
                        self.talk(self.say_tutor_move(message.game))
                    elif 'PICMATE' in message.eval_str:
                        logging.debug('molli in picotutortalker: %s', message.eval_str)
                        self.talk(['picotutor_pico_mate.ogg'])
                        list_str = message.eval_str
                        list_mate = list_str.split('_')
                        logging.debug('molli in picotutortalker: %s', list_mate[0])
                        logging.debug('molli in picotutortalker: %s', list_mate[1])

                        talk_mate = 't_' + list_mate[1] + '.ogg'
                        logging.debug('talk_mate = %s', talk_mate)
                        self.talk([talk_mate])
                    elif 'USRMATE' in message.eval_str:
                        logging.debug('molli in picotutortalker: %s', message.eval_str)
                        self.talk(['picotutor_player_mate.ogg'])
                        list_str = message.eval_str
                        list_mate = list_str.split('_')
                        logging.debug('molli in picotutortalker: %s', list_mate[0])
                        logging.debug('molli in picotutortalker: %s', list_mate[1])

                        talk_mate = 't_' + list_mate[1] + '.ogg'
                        logging.debug('talk_mate = %s', talk_mate)
                        self.talk([talk_mate])

                elif isinstance(message, Message.PGN_GAME_END):  # for pgn replay
                    logging.debug('announcing PGN GAME END')
                    previous_move = chess.Move.null()
                    self.talk(['pgn_game_end.ogg'])
                    if '1-0' in message.result:
                        self.talk(['whitewins.ogg'])
                    elif '0-1' in message.result:
                        self.talk(['blackwins.ogg'])
                    elif '0.5-0.5' in message.result or '1/2-1/2' in message.result:
                        self.talk(['draw.ogg'])
                    elif '*' in message.result:
                        self.talk(['game_result_unknown.ogg'])
                    else:
                        # default
                        self.talk(['game_result_unknown.ogg'])

                elif isinstance(message, Message.TIMECONTROL_CHECK):
                    logging.debug('timecontrol check')
                    self.talk(['picotutor_notify.ogg'])
                    if message.player:
                        self.talk(['timecontrol_check_player.ogg'])
                    else:
                        self.talk(['timecontrol_check_opp.ogg'])

                elif isinstance(message, Message.SHOW_ENGINENAME):
                    if message.show_enginename:
                        self.talk(['show_enginename_on.ogg'])
                    else:
                        self.talk(['show_enginename_off.ogg'])

                elif isinstance(message, Message.SHOW_TEXT):
                    if message.text_string == 'NEW_POSITION':
                        self.talk(['set_pieces_sound.ogg'], self.BEEPER)
                        if not self.beep_on:
                            self.talk(['set_pieces_sound.ogg'])

                elif isinstance(message, Message.PICOWATCHER):
                    if message.picowatcher:
                        self.talk(['picowatcher_enabled.ogg'])
                    else:
                        self.talk(['picowatcher_disabled.ogg'])
                    self.talk(['picotutor_ok.ogg'])

                elif isinstance(message, Message.PICOCOACH):
                    if message.picocoach:
                        self.talk(['picocoach_enabled.ogg'])
                    else:
                        self.talk(['picocoach_disabled.ogg'])
                    self.talk(['picotutor_ok.ogg'])

                elif isinstance(message, Message.PICOEXPLORER):
                    if message.picoexplorer:
                        self.talk(['picoexplorer_enabled.ogg'])
                    else:
                        self.talk(['picoexplorer_disabled.ogg'])
                    self.talk(['picotutor_ok.ogg'])

                elif isinstance(message, Message.PICOCOMMENT):
                    self.talk(['ok.ogg'])

                elif isinstance(message, Message.SAVE_GAME):
                    self.talk(['save_game.ogg'])

                elif isinstance(message, Message.READ_GAME):
                    self.talk(['read_game.ogg'])

                elif isinstance(message, Message.CONTLAST):
                    if message.contlast:
                        self.talk(['contlast_game_on.ogg'])
                    else:
                        self.talk(['contlast_game_off.ogg'])

                elif isinstance(message, Message.ALTMOVES):
                    if message.altmoves:
                        self.talk(['altmoves_on.ogg'])
                    else:
                        self.talk(['altmoves_off.ogg'])

                elif isinstance(message, Message.SET_VOICE):
                    self.speed_factor = (90 + (message.speed % 10) * 5) / 100
                    localisation_id_voice = message.lang + ':' + message.speaker
                    if message.type == Voice.USER:
                        self.set_user(PicoTalker(localisation_id_voice, self.speed_factor))
                    if message.type == Voice.COMP:
                        self.set_computer(PicoTalker(localisation_id_voice, self.speed_factor))
                    if message.type == Voice.SPEED:
                        self.set_factor(self.speed_factor)
                    if message.type == Voice.BEEPER:
                        self.set_beeper(PicoTalker(localisation_id_voice, self.speed_factor))
                        if message.speaker == 'mute':
                            self.beep_on = False
                        else:
                            self.beep_on = True
                    self.talk(['confirm.ogg'], self.BEEPER)
                    self.talk(['ok.ogg'])

                elif isinstance(message, Message.WRONG_FEN):
                    self.talk(['set_pieces_sound.ogg'], self.BEEPER)
                    if self.setpieces_voice:
                        self.talk(['setpieces.ogg'])
                    else:
                        if not self.beep_on:
                            self.talk(['set_pieces_sound.ogg'])
                    if self.play_game:
                        self.talk(self.say_last_move(self.play_game), self.COMPUTER)

                elif isinstance(message, Message.DGT_BUTTON):
                    self.talk(['button_click.ogg'], self.BEEPER)
                else:  # Default
                    pass
            except queue.Empty:
                pass

    @staticmethod
    def say_last_move(game: chess.Board):
        """Take a chess.BitBoard instance and speaks the last move from it."""

        PicoTalkerDisplay.c_taken = False
        PicoTalkerDisplay.c_castle = False
        PicoTalkerDisplay.c_knight = False
        PicoTalkerDisplay.c_rook = False
        PicoTalkerDisplay.c_king = False
        PicoTalkerDisplay.c_bishop = False
        PicoTalkerDisplay.c_pawn = False
        PicoTalkerDisplay.c_queen = False
        PicoTalkerDisplay.c_check = False
        PicoTalkerDisplay.c_mate = False
        PicoTalkerDisplay.c_stalemate = False
        PicoTalkerDisplay.c_draw = False

        move_parts = {
            'K': 'king.ogg',
            'B': 'bishop.ogg',
            'N': 'knight.ogg',
            'R': 'rook.ogg',
            'Q': 'queen.ogg',
            'P': 'pawn.ogg',
            '+': '',
            '#': '',
            'x': 'takes.ogg',
            '=': 'promote.ogg',
            'a': 'a.ogg',
            'b': 'b.ogg',
            'c': 'c.ogg',
            'd': 'd.ogg',
            'e': 'e.ogg',
            'f': 'f.ogg',
            'g': 'g.ogg',
            'h': 'h.ogg',
            '1': '1.ogg',
            '2': '2.ogg',
            '3': '3.ogg',
            '4': '4.ogg',
            '5': '5.ogg',
            '6': '6.ogg',
            '7': '7.ogg',
            '8': '8.ogg'
        }

        bit_board = game.copy()
        move = bit_board.pop()
        san_move = bit_board.san(move)
        voice_parts = []
        if san_move.startswith('O-O-O'):
            voice_parts += ['castlequeenside.ogg']
            PicoTalkerDisplay.c_castle = True
        elif san_move.startswith('O-O'):
            voice_parts += ['castlekingside.ogg']
            PicoTalkerDisplay.c_castle = True
        else:
            for part in san_move:
                try:
                    sound_file = move_parts[part]
                except KeyError:
                    logging.warning('unknown char found in san: [%s : %s]', san_move, part)
                    sound_file = ''
                if sound_file:
                    voice_parts += [sound_file]
                    if sound_file == 'takes.ogg':
                        PicoTalkerDisplay.c_taken = True
                    elif sound_file == 'knight.ogg':
                        PicoTalkerDisplay.c_knight = True
                    elif sound_file == 'king.ogg':
                        PicoTalkerDisplay. c_king = True
                    elif sound_file == 'rook.ogg':
                        PicoTalkerDisplay.c_rook = True
                    elif sound_file == 'pawn.ogg':
                        PicoTalkerDisplay.c_pawn = True
                    elif sound_file == 'bishop.ogg':
                        PicoTalkerDisplay.c_bishop = True
                    elif sound_file == 'queen.ogg':
                        PicoTalkerDisplay.c_queen = True

        if game.is_game_over():
            if game.is_checkmate():
                wins = 'whitewins.ogg' if game.turn == chess.BLACK else 'blackwins.ogg'
                voice_parts += ['checkmate.ogg', wins]
                PicoTalkerDisplay.c_mate = True
            elif game.is_stalemate():
                voice_parts += ['stalemate.ogg']
                PicoTalkerDisplay.c_stalemate = True
            else:
                PicoTalkerDisplay.c_draw = True
                if game.is_seventyfive_moves():
                    voice_parts += ['75moves.ogg', 'draw.ogg']
                elif game.is_insufficient_material():
                    voice_parts += ['material.ogg', 'draw.ogg']
                elif game.is_fivefold_repetition():
                    voice_parts += ['repetition.ogg', 'draw.ogg']
                else:
                    voice_parts += ['draw.ogg']
        elif game.is_check():
            voice_parts += ['check.ogg']
            PicoTalkerDisplay.c_check = True

        if bit_board.is_en_passant(move):
            voice_parts += ['enpassant.ogg']

        return voice_parts

    @staticmethod
    def say_tutor_move(game: chess.Board):
        """Take a chess.BitBoard instance and speaks the last move from it."""
        move_parts = {
            'K': 't_king.ogg',
            'B': 't_bishop.ogg',
            'N': 't_knight.ogg',
            'R': 't_rook.ogg',
            'Q': 't_queen.ogg',
            'P': 't_pawn.ogg',
            '+': '',
            '#': '',
            'x': 't_takes.ogg',
            '=': 't_promote.ogg',
            'a': 't_a.ogg',
            'b': 't_b.ogg',
            'c': 't_c.ogg',
            'd': 't_d.ogg',
            'e': 't_e.ogg',
            'f': 't_f.ogg',
            'g': 't_g.ogg',
            'h': 't_h.ogg',
            '1': 't_1.ogg',
            '2': 't_2.ogg',
            '3': 't_3.ogg',
            '4': 't_4.ogg',
            '5': 't_5.ogg',
            '6': 't_6.ogg',
            '7': 't_7.ogg',
            '8': 't_8.ogg'
        }

        bit_board = game.copy()
        move = bit_board.pop()
        san_move = bit_board.san(move)
        voice_parts = []

        if san_move.startswith('O-O-O'):
            voice_parts += ['t_castlequeenside.ogg']
        elif san_move.startswith('O-O'):
            voice_parts += ['t_castlekingside.ogg']
            PicoTalkerDisplay.c_castle = True
        else:
            for part in san_move:
                try:
                    sound_file = move_parts[part]
                except KeyError:
                    logging.warning('unknown char found in san: [%s : %s]', san_move, part)
                    sound_file = ''
                if sound_file:
                    voice_parts += [sound_file]

        if game.is_check():
            voice_parts += ['t_check.ogg']

        if bit_board.is_en_passant(move):
            voice_parts += ['t_enpassant.ogg']

        return voice_parts
