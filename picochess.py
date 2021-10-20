#!/usr/bin/env python3

# Copyright (C) 2013-2018 Jean-Francois Romang (jromang@posteo.de)
#                         Shivkumar Shivaji ()
#                         Jürgen Précour (LocutusOfPenguin@posteo.de)
#                         Wilhelm
#                         Dirk ("Molli")
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

############################################################################################
#-------------------------------------------------------------------------------------------
# Mollis Personal Picochess versions
#-------------------------------------------------------------------------------------------
# The following enhancements to the 0.9N version have been implemented:
#        0.  Version set to 1.0 (finally ;-)
#        1.  Voice announcements even if time < 1 minute
#        2.  Possibility to continue playing even if one player runs out of time
#        3.  Pre-Moves: Computer and user moves can be done in rapid sequence
#            (no need to wait for registration of computer move). Even the
#            own move could be played before computer move - it doesn't matter
#        4.  New flexible ponder mode: no more checks if valid moves, position can
#            be setup without any restrictions (of course it must be a legal one)
#            Makes analysis and playing differenet variants much easier
#        5.  Remote mode working again (without room handling, see menue.py)
#
#-------------------------------------------------------------------------------------------
#        6.  Version set to 2.0
#        7.  Framework for adding (more or less funny) speech comments based on
#            various events
#        8.  Rolling display of time/score/depth/hintmove in Ponder On or Normal Mode
#        9.  Continue directly after start with an interrupted game if board still shows
#            last position by reading the last games pgn file
#        10. New cool training mode with training options (with big thanks to Wilhelm!!!)
#        11. Configuration parameters for all 1.00/2.00 enhancements in picochess.ini
#        12. Various bug fixes (eg. pressing the outer buttons for quick restart
#            instead of shutdown like it was intended, calc. error in evaluation)
#            Again: big thanks to Wilhelm!
#        13. Renaming of the play modes! Now we have:
#            New mode name                                         Old mode name
#            a5 NORMAL (rolling info display off by default)       NORMAL
#            b5 PONDER ON (rolling info display on by default)     BRAIN
#            c5 MOVE HINT                                          ANALYSIS
#            d5 EVAL.SCORE                                         KIBITZ
#            e5 OBSERVE                                            OBSERVE
#            f5 ANALYSIS (flexible option on by default)           PONDER
#            g5 TRAINING (this is new in 2.00)                       -
#            h5 REMOTE (working again from 1.00 on)                REMOTE
#
#-------------------------------------------------------------------------------------------
#        14. Version set to 2.01
#        15. Added possibility to change voice volume via menu and picochess.ini
#
#-------------------------------------------------------------------------------------------
#        16. Version set to 3.0 (a really big one ;-)
#            I think most of the enhancements only make sense running on a Revelation II (or at least
#            a DGTPI with better display capabilities. Especially on a Revelation II it is really fun
#            to read game comments or the opening name etc. while this is exhausting on a DGTPI and awful
#            on a standalone DGT Clock with its 8 chars)
#            Some features (like tournament control or PicoTutor) even wouldn't correctly work on stand
#            alone clocks together with picochess because the display can not show the correct time control
#            setting.
#            Furthermore additional libraries must be installed, a bug must be fixed in the python-chess
#            code itself(!) for the tournament control option and you need additional engines for some
#            of the new feature (don't ask me where to get them or where you can get an image etc.)
#            !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
#            !!! Keep in mind: I did these enhancements in this Personal Version for my own pleasure
#            !!! in order to have fun & play with picochess on my Revelation 2 - so it might be not
#            !!! your cup of tea...
#            !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
#        17. Support for Online Engines
#             - Switch to Online Mode if online engine is choosen (engine name starts with
#               Prefix 'Online')
#             - Time control settings are taken from the online server challenge and are
#               applied automatically as current time control settings
#             - Clocks start after first white and black moves. After this the player's time already
#               starts with the annoucement of the best move and no longer when
#               the computer move has been done by the user (other than that no real sync with server
#               times has been implemented)
#             - Online decrement: In order to better "sync" picochess times with online server times
#               you can subtract X seconds after each own move from your remaining game time in
#               picochess.ini, default value is 0.9s
#             - additional online info messages (login, seeking, opponent name, game result)
#             - new online seek in case of 'start new game' event
#             - Online move is automatically played in case of white = online opponent and clock starts
#             - last move is published to online engine in case of game ending to inform the online
#               server
#             - online player names in pgn file(s) instead of engine or pico user name only
#             - Online engines won't be saved in picochess.ini as last engine
#             - picochess.ini "Online decrement" parameter can be overwritten in online uci files via parameter
#               OnlineDecrement (just add "[DEFAULT]  OnlineDecrement = X"
#             - still work in progress (don't ask me when they are ready to play...):
#               - basic FICS online engine (for this TELNET must have been installed, default!?)
#               - very basic lichess online engine (for this the BESERK package must have been installed)
#        18. (Better) support for MAME emulated chess engines
#             - requirement: new SDL libraries (probably different for BUSTER)
#                            and Q5 library must have been installed
#             - newer mame/mess versions do need BUSTER!
#             - longer startup time for mame engines necessary, voice/sound end messages from mame engine
#               last ending move is published to emulator engine in case of game end for specific engines
#             - "engine setup" message because of longer initializing phase of mame chess engines
#             - support for pico timecontrol setting in uci file settings according to mame engine levels
#               (just define the UCI parameter PicoTimeControl X Y Z in your level settings) and time is set
#               automatically after choosing a level
#             - When switching back to non mame engine time settings are reset to last setting before it has been
#               eventually changed by the uci setting (default time setting can be defined in picochess.ini
#               via parameter def-timectrl when having a mame engine as last engine after startup)
#             - automatic reset of the original time control settings after choosing a non mame/mess engine
#             - mame engine should not be saved as last used engine on a DGTPI because of possible clock problems when
#               starting mame engine directly after boot (very strange maybe a sync problem with dgtpicom lib!?)
#        19. Finally: practical support of remote engines and local engines at the same time(!)
#             - IMPORTANT! For windows server access an update of the spur and paraminko packages and a
#               modification of the spur package are necessary (ssh.py must be replaced from a different repository)
#             - name in engine.ini must start with prefix 'remote_'
#             - implemented via standard ssh connection, just add the remote login infos
#               in the corresponding parameters of picochess.ini and your remote engine in engines.ini
#               and make sure SSH server is running on your remote computer (default on MacOS)
#        20. Automatic takeback mode (only for mame engines) in case of a blunder move with active PicoTutor
#            (PicoWatcher must be switched on)
#             - Normally taking back moves when using mame engine is not possible so this is a nice feature for
#               beginners (like me ;-) who often play against mame engines.
#             - only the last blunder move can be taken back when using mame (of course this restriction is not
#               valid for other native uci engines!)
#        21. Bugfix: Set correct (old) engine (name) in case of engine error (very important for
#                    new remote/online engines which sould easily fail if server is not available)
#        22. Taking back moves: Now the next move which could be taken back is shown in display and
#            in long notation format (good for old people like me ;-)
#        23. After start up and new game events the current chosen engine is shown in the display
#            (setting in display menu & config parameter in picochess.ini)
#        24. Support for correct remaining game times for continued games from version 2 (finally!)
#        25. Synthesized voice support for moves in WebServer (unfortunately works only in desktop
#            browsers and in Android Firefox browser): Big thanks to Martin (author of the ingenious
#            TuroChamp python engine) and deletion of the non working remote room button functionality
#            Of course you can still use the remote play mode functionality (re)introduced since 2.0 and
#            the new handling of remote engines)
#        26. Replay of PGN games (semi automatic) via new engine
#            - Semi automatic replay of saved pgn games with hint move/score evaluation by an analysis engine
#              for a specific thinking period (time settings will be changed according to uci file and changed
#              back automatically)
#            - "Guess that move" game option for white or black (switch "guessing" sides by pressing the lever)
#            - Additionally this pgn replay mode can be used to train opening books when setting
#              an empty pgn file with name 'Book Test' and choosing a specific book in menu: just try and play
#              a move you think belongs to the chosen book opening (makes more sense when you create specific books
#              with a specific theme or famous player moves)
#            - Furthermore an audio comment file for the pgn file can be specified and will be automatically
#              played during the pgn game replay and can be manually started and stopped during the match
#              (I did this because I have a (german) genious radio play "Nahrungsaufnahme während der Zeitnotphase"
#               which is playing in real time during a tournament game. Now I can listen to the radio play and
#               watch the game at the same time with picochess - how cool is that!?
#            - PGN Replay engine settings won't be saved in picochess.ini as last engine 
#        27. Enhancement of supported tags in pgn file: opening eco code, pico remaining times, pico time
#            control setting
#        28. For online-, emulation- and pgn-mode: Automatically switch off opening books (setting "no book"
#            as book option)
#        29. Override pgn location from picochess.ini in case the parameter 'location' is set to
#            something different than 'auto' (you can use this if you always get a wrong auto
#            location).
#        30. Basic chess tutor functionality (even in case the choosen engine does not support
#            score & hint moves like almost all mame emulated engines) with the following 3
#            functions (disabled in Online mode)
#            a) Pico Watcher (checks your moves and returns ??, ?, !?, ?!, !, !!)
#               You can change the control limits for the evalutations in file picotutor_constants.py
#            b) Pico Coach (gives position score and move hint(s) - just lift a piece and put it back into
#               the same position)
#            c) Pico Opening Explorer (displays current opening name (alternative) independet of the
#               used opening book
#        31. Tournament time control settings:
#            Possible time control settings in picochess v3.0:
#            time = m, time = g i, time = n g i  or time = n g1 i g2
#            Examples:
#            time = ... 7   (time per move, eg. m = 7 seconds)
#                       5 0 (game time, eg. Blitz g = 5 min. and 0 seconds increment)
#                       5 3 (game time g= 5 min. plus I = 3 sec. increment)
#            Tournament time control settings: n moves in g1 minutes (plus I increment seconds) and rest
#            of the game in g2 minutes
#            time = ...
#            new:   40 5 0 (n = 40 moves in g = 5 minutes)
#            new:   40 5 3 ((n = 40 moves in g= 5 minutes with I = 3s Fischer inc.)
#            new:   40 60 0 30 (n = 40 moves in g1 = 90 minutes, I = 0 seconds increment and rest of the game in g2 = 30 minutes)
#            **************
#            * Important: *
#            **************
#            for this a python-chess bug in 22.1 version must have been fixed to support the
#            movestogo go command option correctly!
#            If you have a higher python version look there (eg. 3.7 on BUSTER)
#            (in file /usr/local/lib/python3.7/dist-packages/chess/uci.py:
#             line 949  original:   if movestogo is not None and movestogo > 0:
#                       changed to: if movestogo is not None and int(movestogo) > 0:
#             That was not so easy to figure out...)
#        32. Possibility to directly play an alternative move for the engine on the board after the engine move
#            has been displayed in NORMAL mode (like in TRAINING mode or the DGT CENTAUR chess computer)
#            (setting in menu and config para)
#        33. Menu for saving, reading and continuing a game from pgn files (yes, finally!)
#            *** IMPORTANT ***
#            In order to load and continue a saved game you will need to use the webserver in order to set up
#            the correct starting position of the game. For this you must open the webserver page BEFORE
#            you read and restore the game or if not just use the sync button!
#        34. Display of the book opening name(s) (function of the PicoTutor)
#        35. New time control setting: Support of a specific max. search depth (with a fixed
#            countdown movetime of 11:11 (unfortunately counting up the clock is not possible)
#        36. Support of written game comments like it used to be in Boris or Sargon 2.5 MGS old chess computers
#        37. Display of pgn event, players & result when loading an existing game
#        38. Enhancements of REV2 and webserver display of moves/evaluation/depth/score
#        39. Display of „new position“ message in case of analysis mode and user sets up
#            a new position instead of playing an legal move (or in case he plays an illegal
#            move which is seen as a new position)
#        40. Removed use of vorbis ogg player because of audio play conflicts with sound from
#            mame chess engines in picotalker.py and OS update problems and missing start/stop/pause
#            functions(now pygame.mixer is used instead), see <https://www.pygame.org/docs/ref/mixer.html>
#            install additional lib via: "sudo apt-get install python3-pygame"
#        50. Three new voices (one with commentary): Daniel (eng.), Boris (eng. with commentary)
#            and Gust (german). Additinal voice samples (eng./german) for the new picochess V3.0
#            feature which can be put additionally in all existing voice folders
#        51. Specific 'set pieces' sound (no voice) so you hear when something wrong with the board position
#        52. Set opponent pgn player to 'Player B' instead of engine name and user name ro 'Player A'
#            in case of 'Observe Mode'
#        53. No more searchmoves in UCI 'go' command for the engine in case normal moves (exception:
#            Alternative moves), otherwise this might cause problems with the use of internal
#            engine books etc.(thanks to Rasmus for the hint)
#        54. BugFix for Buster: Change of voice volume working again (big thanks to Wilhelm!)
#        55. New (Fischer) "simulated" median move time levels: 5s, 10s, 15s, 20s, 30s, 60s, 90s
#            (thanks to the schachcomputer.info Forum for this idea!)
#        56. New "favorite engines" options: It is nice to have all 60 and more engines installed
#            but it is a pain to select one out of these many engines...
#            => new Favorite menu to keep your main and most often used engine separately.
#               just put your favorite engines into the favorite.ini file liek you would do for the
#               main engine list in engine.ini and put it in the correct egine directory - that's it
#               *** IMPORTANT ***
#               Engines in favorite.ini must also appear in engines.ini!!!
#        57. BugFix: Continue game/load saved game and play in opposite board direction fixed
#        58. Support of engine subfolders: you can now organize your engines in subfolders
#            within the main engine folder (just specify the subfolder path in engines.ini in
#            in front of the filename eg. [MAME/mm5] where MAME is a subfolder within the armv7l
#            folder (thanks to Wilhelm for supporting the correct engine startup loading procedure!)
#        59. Fix for the strange clock times reset "bug" when playing without a clock with just a board,
#            PI and the webserver. With the voice move announcements of the webserver in V3.0 we even
#            don't have to look at the webserver screen when playing... (thanks to Marcel Swidde for
#            the fix in the picochess google groups forum)
#        60. Position correction message after the "Set pieces" error message occurs the second time:
#            assuming that you are lost and don't know where to put the piece to its correct position,
#            picochess will tell you what is wrong and how to correct (if you have your PI hooked up
#            into your WLAN you could just check the correct position with the webserver board display
#            by just pressing the Sync button of the webserver).
#            Picochess will stop the clocks and check its internal game position against the external
#            DGT board position and will display two kind of correction messages:
#            - Put w N f3 (=> put white night on f3)
#            - Clear h5 (=> remove piece from h5)
#            This will continue as long as the correct position has been set up.
#
############################################################################################

import sys
import os
import threading
import copy
import gc
import logging
from logging.handlers import RotatingFileHandler
import time
import queue
import configargparse
from platform import machine
import paramiko
import copy
import math
from typing import Set

from uci.engine import UciShell, UciEngine
from uci.read import read_engine_ini
import chess
import chess.pgn
import chess.polyglot
import chess.uci

from timecontrol import TimeControl
from utilities import get_location, update_picochess, get_opening_books, shutdown, reboot, checkout_tag
from utilities import Observable, DisplayMsg, version, evt_queue, write_picochess_ini, hms_time, RepeatedTimer
from pgn import Emailer, PgnDisplay, ModeInfo
from server import WebServer
from talker.picotalker import PicoTalkerDisplay
from dispatcher import Dispatcher

from dgt.api import Message, Event
from dgt.util import GameResult, TimeMode, Mode, PlayMode, PicoComment
from dgt.hw import DgtHw
from dgt.pi import DgtPi
from dgt.display import DgtDisplay
from dgt.board import DgtBoard
from dgt.translate import DgtTranslate
from dgt.menu import DgtMenu

from picotutor import PicoTutor ## molli
from pathlib import Path ##molli

class AlternativeMover:

    """Keep track of alternative moves."""

    def __init__(self):
        self._excludedmoves = set()

    def all(self, game: chess.Board) -> Set[chess.Move]:
        """Get all remaining legal moves from game position."""
        searchmoves = set(game.legal_moves) - self._excludedmoves
        if not searchmoves:
            self.reset()
            return set(game.legal_moves)
        return searchmoves

    def book(self, bookreader, game_copy: chess.Board):
        """Get a BookMove or None from game position."""
        try:
            choice = bookreader.weighted_choice(game_copy, self._excludedmoves)
        except IndexError:
            return None

        book_move = choice.move()
        self.exclude(book_move)
        game_copy.push(book_move)
        try:
            choice = bookreader.weighted_choice(game_copy)
            book_ponder = choice.move()
        except IndexError:
            book_ponder = None
        return chess.uci.BestMove(book_move, book_ponder)

    def check_book(self, bookreader, game_copy: chess.Board) -> bool:
        """molli: for PGN Replay/Book Test Check if BookMove exists from game position."""
        l_set = set()
        try:
            choice = bookreader.weighted_choice(game_copy, l_set)
        except IndexError:
            return False

        book_move = choice.move()

        if book_move:
            return True
        else:
            return False

    def exclude(self, move) -> None:
        """Add move to the excluded move list."""
        self._excludedmoves.add(move)

    def reset(self) -> None:
        """Reset the exclude move list."""
        self._excludedmoves.clear()

flag_startup = False
online_prefix = 'Online'
seeking_flag = False
fen_error_occured = False
position_mode = False
start_time_cmove_done = 0
reset_auto = False

def main():
    """Main function."""
    ## molli: new config params
    flag_flexible_ponder = False
    flag_premove = False
    book_in_use = ''
    max_guess_white = 0
    max_guess_black = 0
    max_guess = 0
    think_time = 0
    no_guess_white = 1
    no_guess_black = 1
    pgn_book_test = False
    flag_last_engine_pgn = False
    flag_last_engine_emu = False
    flag_last_engine_online = False
    tc_init_last = None
    take_back_locked = False
    takeback_active = False
    automatic_takeback = False
    last_move = None
    com_factor = 0
    global reset_auto
    global flag_startup
    global position_mode
    global seeking_flag
    global fen_error_occured
    global position_mode
    global start_time_cmove_done
    
    def check_ssh(host, username, password):
        l_ssh = True
        try:
            s = paramiko.SSHClient()
            s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            s.connect(host, username=username, password=password, timeout=7)
            s.close()
        except:
            l_ssh = False
        
        return(l_ssh)

    ####################################################
    # molli: PGN GAME MODE
    ####################################################
    def log_pgn():
        nonlocal max_guess_white
        nonlocal max_guess_black
        nonlocal no_guess_white
        nonlocal no_guess_black
        nonlocal max_guess
        nonlocal pgn_book_test
        
        logging.debug('molli pgn: pgn_book_test: %s', str(pgn_book_test))
        logging.debug('molli pgn: game turn: %s', game.turn)
        logging.debug('molli pgn: max_guess_white: %s', max_guess)
        logging.debug('molli pgn: max_guess_white: %s', max_guess_white)
        logging.debug('molli pgn: max_guess_black: %s', max_guess_black)
        logging.debug('molli pgn: no_guess_white: %s', no_guess_white)
        logging.debug('molli pgn: no_guess_black: %s', no_guess_black)
    
    def det_pgn_guess_tctrl():
        nonlocal max_guess_white
        nonlocal max_guess_black
        nonlocal max_guess
        nonlocal think_time
        nonlocal pgn_book_test
        max_guess_white = 0
        max_guess_black = 0

        logging.debug('molli pgn: determine pgn guess')
        
        uci_options = engine.get_pgn_options()
        
        logging.debug('molli pgn: uci_options %s', str(uci_options))
        
        if "max_guess" in uci_options:
            max_guess = int(uci_options["max_guess"])
        else:
            max_guess = 0
        
        if "think_time" in uci_options:
            think_time = int(uci_options["think_time"])
        else:
            think_time = 0
        
        if "pgn_game_file" in uci_options:
            logging.debug('molli pgn: pgn_game_file; %s', str(uci_options["pgn_game_file"]))
            if 'book_test' in str(uci_options["pgn_game_file"]):
                pgn_book_test = True
                logging.debug('molli pgn: pgn_book_test set to True')
            else:
                pgn_book_test = False
                logging.debug('molli pgn: pgn_book_test set to False')
        else:
            logging.debug('molli pgn: pgn_book_test not found => False')
            pgn_book_test = False
        
        
        max_guess_white = max_guess
        max_guess_black = 0
        
        tc_init = time_control.get_parameters()
        tc_init['mode']  = TimeMode.FIXED
        tc_init['fixed'] = think_time
        tc_init['blitz'] = 0
        tc_init['fischer'] = 0
        
        tc_init['blitz2'] = 0
        tc_init['moves_to_go'] = 0
        tc_init['depth'] = 0

        stop_clock()
        text = dgttranslate.text('N00_oktime')
        time_control.reset()
        Observable.fire(Event.SET_TIME_CONTROL(tc_init=tc_init, time_text=text, show_ok=True))
        stop_clock()
        DisplayMsg.show(Message.EXIT_MENU())
        
    def set_online_tctrl(game_time, fischer_inc):
        nonlocal time_control
        l_game_time   = 0
        l_fischer_inc = 0
        
        ## TC must be determined in newgame event (switch_online)
        
        logging.debug('molli online set_online_tctrl input %s %s', game_time, fischer_inc)
        l_game_time = int(game_time)
        l_fischer_inc = int(fischer_inc)
        ##logging.debug('molli online set_online_tctr output %s %s', game_time, fischer_inc)
        stop_clock()
        time_control.stop_internal(log=False)
        
        time_control = TimeControl()
        tc_init  = time_control.get_parameters()
        
        if l_fischer_inc == 0:
            tc_init['mode']  = TimeMode.BLITZ
            tc_init['blitz'] = l_game_time
            tc_init['fischer'] = 0
        else:
            tc_init['mode']    = TimeMode.FISCHER
            tc_init['blitz']   = l_game_time
            tc_init['fischer'] = l_fischer_inc
        
        tc_init['blitz2'] = 0
        tc_init['moves_to_go'] = 0

        lt_white = l_game_time * 60 + l_fischer_inc
        lt_black = l_game_time * 60 + l_fischer_inc
        tc_init['internal_time'] = {chess.WHITE: lt_white, chess.BLACK: lt_black}
        
        time_control = TimeControl(**tc_init)
        text = dgttranslate.text('N00_oktime')
        msg = Message.TIME_CONTROL(time_text=text, show_ok=True, tc_init=tc_init)
        DisplayMsg.show(msg)
        stop_fen_timer()
        
    def set_online_tctrl2(game_time, fischer_inc):
        nonlocal online_decrement
        nonlocal time_control
        stop_clock()
        time_control.stop_internal(log=False)
        ## molli overwrite online_decrement parameter from uci settings if defined
        try:
            uci_options = engine.get_pgn_options()
            if "OnlineDecrement" in uci_options:
                online_decrement = int(uci_options["OnlineDecrement"])
        except:
            pass
        tctrl_str = str(game_time) + ' ' + str(fischer_inc)
        logging.debug('molli: set_online_tctrl input %s', tctrl_str)
        time_control, time_text = transfer_time(tctrl_str.split(), depth=0)
        tc_init  = time_control.get_parameters()
        text = dgttranslate.text('N00_oktime')
        Observable.fire(Event.SET_TIME_CONTROL(tc_init=tc_init, time_text=text, show_ok=True))
        stop_fen_timer()
        
    def set_emulation_tctrl():
        nonlocal time_control
        logging.debug('molli: set_emulation_tctrl')
        if emulation_mode():
            pico_depth = 0
            pico_tctrl_str = ''
            
            stop_clock()
            time_control.stop_internal(log=False)
            
            uci_options = engine.get_pgn_options()
            pico_tctrl_str = ''
            
            try:
                if "PicoTimeControl" in uci_options:
                    pico_tctrl_str = str(uci_options["PicoTimeControl"])
            except:
                pico_tctrl_str = ''
            
            try:
                if "PicoDepth" in uci_options:
                    pico_depth = int(uci_options["PicoDepth"])
            except:
                pico_depth = 0

            if pico_tctrl_str:
                logging.debug('molli: set_emulation_tctrl input %s', pico_tctrl_str)
                time_control, time_text = transfer_time(pico_tctrl_str.split(), depth=pico_depth)
                tc_init  = time_control.get_parameters()
                text = dgttranslate.text('N00_oktime')
                Observable.fire(Event.SET_TIME_CONTROL(tc_init=tc_init, time_text=text, show_ok=True))
                stop_fen_timer()

    def read_pgn_info(): ## molli pgn mode must be called after each newgame event
        pgn_fen = ''
        pgn_game_name = ''
        pgn_result = ''
        pgn_problem = ''
            
        try:
            log_p = open('pgn_game_info.txt', 'r')
        except:
            log_p = ''
            logging.error('Could not read pgn_game_info file')
            return
            
        if log_p:
            lines = log_p.readlines()
            i = 0
            for line in lines:
                i += 1
                if i == 1:
                    if len(line) > 9:
                        pgn_game_name =  line[9:]
                        pgn_game_name.replace("\n", "")
                        pgn_game_name.replace("\r", "")
                elif i == 2:
                    ## game index
                    pass
                elif i == 3:
                    if len(line) > 12:
                        pgn_problem   =  line[12:]
                        pgn_problem.replace("\n", "")
                        pgn_problem.replace("\r", "")
                elif i == 4:
                    ## white
                    if len(line) > 10:
                        pgn_white   =  line[10:]
                        pgn_white.replace("\n", "")
                        pgn_white.replace("\r", "")
                        pgn_white = pgn_white
                elif i == 5:
                    ## black
                    ## white
                    if len(line) > 10:
                        pgn_black   =  line[10:]
                        pgn_black.replace("\n", "")
                        pgn_black.replace("\r", "")
                        pgn_black = pgn_black
                elif i == 6:
                    if len(line) >8:
                        pgn_fen   =  line[8:]
                        pgn_fen.replace("\n", "")
                        pgn_fen.replace("\r", "")
                elif i == 7:
                    if len(line) > 11:
                        pgn_result   =  line[11:]
                        pgn_result.replace("\n", "")
                        pgn_result.replace("\r", "")
                else:
                    pass
        else:
            pgn_fen = ''
            pgn_game_name = 'Game Error'
            pgn_problem = ''
            pgn_result = '*'
        
        log_p.close()
        l_len = len(pgn_game_name) - 1
        l_pgn_game_name = pgn_game_name[:l_len]
        pgn_game_name = l_pgn_game_name.ljust(11,' ')
        
        l_len = len(pgn_problem) - 1
        l_pgn_problem = pgn_problem[:l_len]
        pgn_pgn_problem= l_pgn_problem.ljust(11,' ')
            
        return(pgn_game_name, pgn_problem, pgn_fen, pgn_result, pgn_white, pgn_black)

    def set_fen_from_pgn(pgn_fen):
        nonlocal last_legal_fens
        nonlocal searchmoves
        nonlocal legal_fens
        nonlocal legal_fens_after_cmove # molli
        nonlocal game
        nonlocal done_move
        nonlocal done_computer_fen
        nonlocal pb_move
        nonlocal play_mode ##molli
        nonlocal game_declared
        
        bit_board = chess.Board(pgn_fen)
        bit_board.set_fen(bit_board.fen())
        logging.debug('molli PGN Fen: %s', bit_board.fen())
        if bit_board.is_valid():
            logging.debug('molli PGN fen is valid!')
            game = chess.Board(bit_board.fen())
            done_computer_fen = None
            done_move = pb_move = chess.Move.null()
            searchmoves.reset()
            game_declared = False
            legal_fens = compute_legal_fens(game.copy())
            legal_fens_after_cmove = []
            last_legal_fens = []
            if picotutor_mode():
                picotutor.reset() ##molli picotutor
                picotutor.set_position(game.fen(), i_turn = game.turn)
                if play_mode == PlayMode.USER_BLACK:
                    picotutor.set_user_color(chess.BLACK)
                else:
                    picotutor.set_user_color(chess.WHITE)
        else:
            logging.debug('molli PGN fen is invalid!')

    def picotutor_mode(): ## molli picotutor enabled?
        nonlocal flag_picotutor
        enabled = False
        
        if flag_picotutor and interaction_mode in (Mode.NORMAL, Mode.TRAINING, Mode.BRAIN) and not online_mode() and not pgn_mode() and (dgtmenu.get_picowatcher() or dgtmenu.get_picocoach() or dgtmenu.get_picoexplorer()) and picotutor != None:
            enabled = True
        else:
            enabled = False
        
        return enabled
    
    def get_comment_file():
        comment_path = engine.get_file() + '_comments_' + args.language + '.txt'
        logging.debug('molli comment file: %s', comment_path)
        comment_file = Path(comment_path)
        if comment_file.is_file():
            logging.debug('molli comment file exists')
            return comment_path
        else:
            logging.debug('molli comment file does not exist')
            return ''

    def pgn_mode():
        if 'pgn_' in engine_file:
            return(True) ## molli remote engine mode
        else:
            return(False)

    def remote_engine_mode():
        if 'remote' in engine_file:
            return(True) ## molli remote engine mode
        else:
            return(False)

    def emulation_mode():
        emulation = False
        if '(mame' in engine_name or '(mess' in engine_name:
            emulation = True ## molli emulation mode
        return(emulation)
    
    def online_mode():
        online = False
        if len(engine_name) >= 6:
            if engine_name[0:6] == online_prefix: ## molli online mode
                online = True
            else:
                online = False
        return(online)
        
    def compare_fen(fen_board_external='',fen_board_internal=''):
        ## <Piece Placement> ::= <rank8>'/'<rank7>'/'<rank6>'/'<rank5>'/'<rank4>'/'<rank3>'/'<rank2>'/'<rank1>
        ## <ranki>       ::= [<digit17>]<piece> {[<digit17>]<piece>} [<digit17>] | '8'
        ## <piece>       ::= <white Piece> | <black Piece>
        ## <digit17>     ::= '1' | '2' | '3' | '4' | '5' | '6' | '7'
        ## <white Piece> ::= 'P' | 'N' | 'B' | 'R' | 'Q' | 'K'
        ## <black Piece> ::= 'p' | 'n' | 'b' | 'r' | 'q' | 'k'

        ## eg. starting position 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR'
        ##                       'a8 b8 c8 d8... / a7 b7... / a1 b1 c1 ... h1'

        if fen_board_external == fen_board_internal or fen_board_external == '' or fen_board_internal == '':
            return('') ## no difference

        internal_board = chess.Board()
        internal_board.set_board_fen(fen_board_internal)

        external_board = chess.Board()
        external_board.set_board_fen(fen_board_external)

        ## now compare each square and return first difference
        ## and return first all fields to be cleared and then
        ## all fields where to put new/different pieces on
        ## start first with all squares to be cleared
        put_field = ''
        for square_no in range(0,63):
            if internal_board.piece_at(square_no) != external_board.piece_at(square_no):
                if internal_board.piece_at(square_no) == None:
                    return(str('clear ' + chess.square_name(square_no)))
                else:
                    put_field = str('put '+ str(internal_board.piece_at(square_no)) + ' ' + chess.square_name(square_no))
        return(put_field)

    def remote_windows():
        windows = False
        if '\\' in engine_remote_home:
            windows = True
        else:
            windows = False
        return(windows)
    
    def display_ip_info():
        nonlocal set_location
        """Fire an IP_INFO message with the IP adr."""
        location, ext_ip, int_ip = get_location()
        
        if set_location == 'auto': ##molli
            pass
        else:
            location = set_location

        info = {'location': location, 'ext_ip': ext_ip, 'int_ip': int_ip, 'version': version}
        DisplayMsg.show(Message.IP_INFO(info=info))

    ## molli: read game from pgn file
    def read_pgn_file(file_name):
        nonlocal last_legal_fens
        nonlocal searchmoves
        nonlocal legal_fens
        nonlocal legal_fens_after_cmove # molli
        nonlocal game
        nonlocal tc_init_last
        nonlocal done_move
        nonlocal done_computer_fen
        nonlocal pb_move
        nonlocal error_fen
        nonlocal play_mode ##molli
        nonlocal flag_picotutor
        nonlocal time_control
        nonlocal game_declared
        nonlocal take_back_locked
        nonlocal dgtmenu
        
        logging.debug('molli: read game from pgn file')
        
        l_filename = 'games' + os.sep + file_name
        try:
            l_file_pgn = open(l_filename)
            if not l_file_pgn:
                return
        except:
            return
        
        l_game_pgn = chess.pgn.read_game(l_file_pgn)
        l_file_pgn.close()
        
        logging.debug('molli: read game filename %s', l_filename)
        
        stop_search_and_clock()
        
        if picotutor_mode():
            picotutor.reset() ##molli picotutor
        
        game = chess.Board()
        l_move = chess.Move.null()
        
        if l_game_pgn.headers['Event']:
            DisplayMsg.show(Message.SHOW_TEXT(text_string=str(l_game_pgn.headers['Event'])))
            
        if l_game_pgn.headers['White']:
            DisplayMsg.show(Message.SHOW_TEXT(text_string=str(l_game_pgn.headers['White'])))
            
        DisplayMsg.show(Message.SHOW_TEXT(text_string='versus'))
                
        if l_game_pgn.headers['Black']:
            DisplayMsg.show(Message.SHOW_TEXT(text_string=str(l_game_pgn.headers['Black'])))
    
        if l_game_pgn.headers['Result']:
            DisplayMsg.show(Message.SHOW_TEXT(text_string=str(l_game_pgn.headers['Result'])))
    
        time.sleep(2)
        DisplayMsg.show(Message.READ_GAME)
        time.sleep(2)
        
        for l_move in l_game_pgn.main_line():
            game.push(l_move)
            valid = picotutor.push_move(l_move)

        ## take back last move in order to send it with user_move for web publishing
        if l_move:
            game.pop()
            
        engine.newgame(game.copy())
        
        ## switch temporarly picotutor off
        flag_picotutor = False

        if l_move:
            user_move(l_move, sliding=True) ## publish current position to webserver

        flag_picotutor = True ## back to on again
        
        stop_search_and_clock()
        ##engine.newgame(game.copy())
        turn = game.turn
        done_computer_fen = None
        done_move = pb_move = chess.Move.null()
        play_mode = PlayMode.USER_WHITE if turn == chess.WHITE else PlayMode.USER_BLACK
        
        #########################################################
        ## molli: eventually preset remaining game time!
        ## molli TC
        #########################################################
        
        try:
            if l_game_pgn.headers['PicoDepth']:
                l_pico_depth = int(l_game_pgn.headers['PicoDepth'])
            else:
                l_pico_depth = 0
        
            if l_game_pgn.headers['PicoTimeControl']:
                l_pico_tc = str(l_game_pgn.headers['PicoTimeControl'])
                time_control, time_text = transfer_time(l_pico_tc.split(), depth=l_pico_depth)

            if l_game_pgn.headers['PicoRemTimeW']:
                lt_white = int(l_game_pgn.headers['PicoRemTimeW'])
            else:
                lt_white = 0

            if l_game_pgn.headers['PicoRemTimeB']:
                lt_black = int(l_game_pgn.headers['PicoRemTimeB'])
            else:
                lt_black = 0
        except:
            pass
        
        tc_init       = time_control.get_parameters()
        tc_init_last  = time_control.get_parameters()

        tc_init['internal_time'] = {chess.WHITE: lt_white, chess.BLACK: lt_black}
        ##stop_clock()
        text = dgttranslate.text('N00_oktime')
        time_control.reset()

        Observable.fire(Event.SET_TIME_CONTROL(tc_init=tc_init, time_text=text, show_ok=False))
        stop_clock()
        DisplayMsg.show(Message.EXIT_MENU())

        searchmoves.reset()
        game_declared = False
        
        legal_fens = compute_legal_fens(game.copy())
        legal_fens_after_cmove = []
        last_legal_fens = []
        assert engine.is_waiting(), 'molli: read_pgn engine not waiting! thinking status: %s' % engine.is_thinking()
        engine.position(copy.deepcopy(game))
        
        ##set_wait_state(Message.START_NEW_GAME(game=game.copy(), newgame=True))
        game_end = check_game_state(game, play_mode)
        if game_end:
            play_mode = PlayMode.USER_WHITE if turn == chess.WHITE else PlayMode.USER_BLACK
            legal_fens = []
            legal_fens_after_cmove = [] # molli
            DisplayMsg.show(game_end)
        else:
            play_mode = PlayMode.USER_WHITE if turn == chess.WHITE else PlayMode.USER_BLACK
            text = play_mode.value  # type: str
            msg = Message.PLAY_MODE(play_mode=play_mode, play_mode_text=dgttranslate.text(text))
            DisplayMsg.show(msg)
            time.sleep(1)
                
        take_back_locked = True ## important otherwise problems for setting up the position

    def expired_fen_timer():
        """Handle times up for an unhandled fen string send from board."""
        nonlocal flag_flexible_ponder
        nonlocal fen_timer_running
        nonlocal last_legal_fens
        nonlocal searchmoves
        nonlocal legal_fens
        nonlocal legal_fens_after_cmove # molli
        nonlocal game
        nonlocal game_declared
        nonlocal done_move
        nonlocal done_computer_fen
        nonlocal pb_move
        nonlocal error_fen
        nonlocal play_mode ##molli
        nonlocal flag_picotutor
        nonlocal time_control
        nonlocal dgtmenu
        nonlocal engine_text
        global flag_startup ##molli
        global seeking_flag
        global fen_error_occured
        global position_mode
        fen_i = ''
        game_fen = ''

        fen_timer_running = False

        if error_fen:
            game_fen = game.board_fen()
            if (interaction_mode in (Mode.NORMAL, Mode.TRAINING, Mode.BRAIN) and game_fen!= chess.STARTING_BOARD_FEN and not online_mode() and not pgn_mode() and not emulation_mode() and error_fen != game_fen and take_back_locked == True):
                #logging.debug('Molli reversed board check before: e: %s i: %s g: %s', str(error_fen), str(fen_i), str(game_fen))
                ## check for inverse setup
                fen_i = error_fen[::-1]
                #logging.debug('Molli reversed board check after: e: %s i: %s g: %s', str(error_fen), str(fen_i), str(game_fen))
                if fen_i == game_fen:
                    logging.debug('molli: reverse the board!')
                    dgtmenu.set_position_reverse_flipboard(True)
            
            if (interaction_mode in (Mode.NORMAL, Mode.TRAINING, Mode.BRAIN) and game_fen != chess.STARTING_BOARD_FEN and flag_startup and dgtmenu.get_game_contlast() and not online_mode() and not pgn_mode() and not emulation_mode()):
                ## molli: read the pgn of last game and restore correct game status and times
                flag_startup = False
                DisplayMsg.show(Message.RESTORE_GAME())
                time.sleep(2)
                
                l_pgn_file_name = 'last_game.pgn'
                read_pgn_file(l_pgn_file_name)
                        
            elif (interaction_mode == Mode.PONDER and game_fen != chess.STARTING_BOARD_FEN and flag_flexible_ponder):
                ## molli: no error in analysis(ponder) mode => start new game with current fen
                ## and try to keep same player to play (white or black) but check
                ## if it is a legal position (otherwise switch sides or return error)
                #logging.debug('molli: Start flexible Ponder with fen: %s', error_fen)
                fen1 = error_fen
                fen2 = error_fen
                if game.turn == chess.WHITE:
                    fen1 += ' w KQkq - 0 1'
                    fen2 += ' b KQkq - 0 1'
                else:
                    fen1 += ' b KQkq - 0 1'
                    fen2 += ' w KQkq - 0 1'
                # ask python-chess to correct the castling string
                #logging.debug('Molli flexible Ponder with enhanced fen1: %s', fen1)
                bit_board = chess.Board(fen1)
                bit_board.set_fen(bit_board.fen())
                #logging.debug('Molli First Converted Bitboard Fen: %s', bit_board.fen())
                if bit_board.is_valid():
                    #logging.debug('Molli First fen ist valid!')
                    DisplayMsg.show(Message.SHOW_TEXT(text_string='NEW_POSITION'))
                    game = chess.Board(bit_board.fen())
                    stop_search_and_clock()
                    engine.newgame(game.copy())
                    done_computer_fen = None
                    done_move = pb_move = chess.Move.null()
                    searchmoves.reset()
                    game_declared = False
                    legal_fens = compute_legal_fens(game.copy())
                    legal_fens_after_cmove = []
                    last_legal_fens = []
                    assert engine.is_waiting(), 'engine not waiting! thinking status: %s' % engine.is_thinking()
                    engine.position(copy.deepcopy(game))
                    engine.ponder()
                else:
                    # ask python-chess to correct the castling string
                    bit_board = chess.Board(fen2)
                    bit_board.set_fen(bit_board.fen())
                    #logging.debug('Molli Second converted Bitboard Fen: %s', bit_board.fen())
                    if bit_board.is_valid():
                        #logging.debug('Molli Second fen ist valid!')
                        DisplayMsg.show(Message.SHOW_TEXT(text_string='NEW_POSITION'))
                        game = chess.Board(bit_board.fen())
                        stop_search_and_clock()
                        engine.newgame(game.copy())
                        done_computer_fen = None
                        done_move = pb_move = chess.Move.null()
                        searchmoves.reset()
                        game_declared = False
                        legal_fens = compute_legal_fens(game.copy())
                        legal_fens_after_cmove = []
                        last_legal_fens = []
                        assert engine.is_waiting(), 'engine not waiting! thinking status: %s' % engine.is_thinking()
                        engine.position(copy.deepcopy(game))
                        engine.ponder()
                    else:
                        #logging.debug('Molli Invalid  Fen: %s', bit_board.fen())
                        logging.info('wrong fen %s for 4 secs', error_fen)
                        DisplayMsg.show(Message.WRONG_FEN())
                        ##DisplayMsg.show(Message.EXIT_MENU())
            else:
                logging.info('wrong fen %s for 4 secs', error_fen)
                
                if online_mode():
                    ## show computer opponents move again
                    if seeking_flag:
                        DisplayMsg.show(Message.SEEKING()) ## molli
                    elif best_move_displayed:
                        DisplayMsg.show(Message.COMPUTER_MOVE(move=done_move, ponder=False, game=game.copy(), wait=False))

                fen_res = ''
                internal_fen = game.board_fen()
                external_fen = error_fen
                fen_res = compare_fen(external_fen, internal_fen)
                    
                if not position_mode and fen_res:
                    DisplayMsg.show(Message.WRONG_FEN())
                    time.sleep(2)
                if fen_error_occured and game.board_fen() and fen_res: ## != chess.STARTING_BOARD_FEN:
                    ####################################################################
                    ## molli: Picochess correction messages (not for starting position)
                    ## show incorrect square(s) and piece to put or be removed
                    ###################################################################
                    if fen_res:
                        position_mode = True
                        if not online_mode():
                            stop_clock()
                        msg = Message.POSITION_FAIL(fen_result = fen_res)
                        DisplayMsg.show(msg)
                        time.sleep(1)
                    else:
                        DisplayMsg.show(Message.EXIT_MENU())
                else:
                    DisplayMsg.show(Message.EXIT_MENU())
                        
                if interaction_mode in (Mode.NORMAL, Mode.TRAINING, Mode.BRAIN) and game_fen != chess.STARTING_BOARD_FEN and flag_startup:
                
                    if dgtmenu.get_enginename():
                        DisplayMsg.show(Message.ENGINE_NAME(engine_name=engine_text)) ## molli

                    if pgn_mode():
                        pgn_white = ''
                        pgn_black = ''
                        pgn_game_name, pgn_problem, pgn_fen, pgn_result, pgn_white, pgn_black = read_pgn_info()
                        
                        if pgn_white:
                            DisplayMsg.show(Message.SHOW_TEXT(text_string=pgn_white))
                        if pgn_black:
                            DisplayMsg.show(Message.SHOW_TEXT(text_string=pgn_black))

                        if pgn_result:
                            DisplayMsg.show(Message.SHOW_TEXT(text_string=pgn_result))

                        if 'mate in' in pgn_problem or 'Mate in' in pgn_problem:
                            set_fen_from_pgn(pgn_fen)
                            DisplayMsg.show(Message.SHOW_TEXT(text_string=pgn_problem))
                        else:
                            DisplayMsg.show(Message.SHOW_TEXT(text_string=pgn_game_name))

                else:
                    if done_computer_fen and not position_mode:
                        DisplayMsg.show(Message.EXIT_MENU())
                fen_error_occured = True ## to be reset in fen_handling
        flag_startup = False

    ###################################
    # Online mode
    ###################################
    def read_online_result(): ## molli online
        result_line = ''
        winner = ''
        
        try:
            log_u = open('online_game.txt', 'r')
        except:
            log_u = ''
            logging.error('Could not read online game file')
            return
        
        if log_u:
            i = 0
            lines = log_u.readlines()
            for line in lines:
                i += 1
                if i == 1:
                    if len(line) > 6:
                        login      =  line[6:]
                elif i == 2:
                    if len(line) > 6:
                        own_color  =  line[6]
                        own_color.replace("\n", "")
                        own_color.replace("\r", "")
                elif i == 3:
                    if len(line) > 9:
                        own_user   =  line[9:]
                        own_user.replace("\n", "")
                        own_user.replace("\r", "")
                elif i == 4:
                    if len(line) > 14:
                        opp_user   =  line[14:]
                        own_user.replace("\n", "")
                        own_user.replace("\r", "")
                elif i == 5:
                    if len(line) > 10:
                        game_time   =  line[10:]
                        game_time.replace("\n", "")
                        game_time.replace("\r", "")
                elif i == 6:
                    if len(line) > 12:
                        fischer_inc   =  line[12:]
                        fischer_inc.replace("\n", "")
                        fischer_inc.replace("\r", "")
                elif i == 7:
                    ## rem time w
                    pass
                elif i == 8:
                    ## rem time b
                    pass
                elif i == 9:
                    result_line    =  line[12:]
                elif i == 10:
                    winner         =  line[7:]
                else:
                    pass
        else:
            result_line         = ''

        log_u.close()
        logging.debug('Molli in read_result: %s', result_line)
        logging.debug('Molli in read_result: %s', winner)
        return(str(result_line), str(winner))
    
    def read_online_user_info(): ## molli online
        own_user = 'unknown'
        opp_user = 'unknown'
        login = 'failed'
        own_color = ''
        result_line = ''

        try:
            log_u = open('online_game.txt', 'r')
        except:
            log_u = ''
            logging.error('Could not read online game file')
            return
        
        if log_u:
            lines = log_u.readlines()
            i = 0
            for line in lines:
                i += 1
                if i == 1:
                    if len(line) > 6:
                        login      =  line[6:]
                elif i == 2:
                    if len(line) > 6:
                        own_color  =  line[6]
                        own_color.replace("\n", "")
                        own_color.replace("\r", "")
                        own_color.replace("]", "")
                        own_color.replace("[", "")
                elif i == 3:
                    if len(line) > 9:
                        own_user   =  line[9:]
                        own_user.replace("\n", "")
                        own_user.replace("\r", "")
                        own_user.replace("]", "")
                        own_user.replace("[", "")
                elif i == 4:
                    if len(line) > 14:
                        opp_user   =  line[14:]
                        opp_user.replace("\n", "")
                        opp_user.replace("\r", "")
                        opp_user.replace("]", "")
                        opp_user.replace("[", "")
                elif i == 5:
                    if len(line) > 10:
                        game_time   =  line[10:]
                        game_time.replace("\n", "")
                        game_time.replace("\r", "")
                        game_time.replace("]", "")
                        game_time.replace("[", "")
                elif i == 6:
                    if len(line) > 12:
                        fischer_inc   =  line[12:]
                        fischer_inc.replace("\n", "")
                        fischer_inc.replace("\r", "")
                        fischer_inc.replace("]", "")
                        fischer_inc.replace("[", "")
                elif i == 7:
                    ## rem time w
                    pass
                elif i == 8:
                    ## rem time b
                    pass
                elif i == 9:
                    result_line    =  line[12:]
                elif i == 10:
                    winner         =  line[7:]
                else:
                    pass
        else:
            result_line         = ''
            own_color           = ''
            own_user            = 'unknown'
            opp_user            = 'unknown'
            game_time           = '0'
            fischer_inc         = '0'
            login               = 'failed'
        
        log_u.close()
        logging.debug('online game_time %s fischer_inc: %s', game_time, fischer_inc)
        
        return(login, own_color, own_user, opp_user, game_time, fischer_inc)
    
    def stop_fen_timer():
        """Stop the fen timer cause another fen string been send."""
        nonlocal fen_timer_running
        nonlocal fen_timer
        if fen_timer_running:
            fen_timer.cancel()
            fen_timer.join()
            fen_timer_running = False

    def start_fen_timer():
        """Start the fen timer in case an unhandled fen string been received from board."""
        nonlocal fen_timer_running
        nonlocal fen_timer
        global position_mode
        delay = 0
        
        if position_mode:
            delay = 1 ## if a fen error already occured don't wait too long for next check
        else:
            delay = 4 ## molli: set piece error later (4 instead 3)
        fen_timer = threading.Timer(delay, expired_fen_timer)
        fen_timer.start()
        fen_timer_running = True

    def compute_legal_fens(game_copy: chess.Board):
        """
        Compute a list of legal FENs for the given game.

        :param game_copy: The game
        :return: A list of legal FENs
        """
        fens = []
        for move in game_copy.legal_moves:
            game_copy.push(move)
            fens.append(game_copy.board_fen())
            game_copy.pop()
        return fens

    def think(game: chess.Board, timec: TimeControl, msg: Message, searchlist=False):
        nonlocal automatic_takeback
        """
        Start a new search on the current game.

        If a move is found in the opening book, fire an event in a few seconds.
        """
        DisplayMsg.show(msg)
        if not online_mode() or game.fullmove_number > 1:
            start_clock()
        book_res = searchmoves.book(bookreader, game.copy())
        if (book_res and not emulation_mode() and not online_mode() and not pgn_mode()) or (book_res and (pgn_mode() and pgn_book_test)):
            Observable.fire(Event.BEST_MOVE(move=book_res.bestmove, ponder=book_res.ponder, inbook=True))
        else:
            while not engine.is_waiting():
                time.sleep(0.05)
                logging.warning('engine is still not waiting')
            uci_dict = timec.uci()
            if searchlist:
                uci_dict['searchmoves'] = searchmoves.all(game) ##molli: otherwise might lead to problems with internal books
            engine.position(copy.deepcopy(game))
            engine.go(uci_dict)
        automatic_takeback = False
        
    def mame_endgame(game: chess.Board, timec: TimeControl, msg: Message, searchlist=False):
        nonlocal automatic_takeback
        """
        Start a new search on the current game.

        If a move is found in the opening book, fire an event in a few seconds.
        """
        
        while not engine.is_waiting():
            time.sleep(0.05)
            logging.warning('engine is still not waiting')
        uci_dict = timec.uci()
        engine.position(copy.deepcopy(game))

    def analyse(game: chess.Board, msg: Message):
        """Start a new ponder search on the current game."""
        DisplayMsg.show(msg)
        engine.position(copy.deepcopy(game))
        engine.ponder()

    def observe(game: chess.Board, msg: Message):
        """Start a new ponder search on the current game."""
        analyse(game, msg)
        start_clock()

    def brain(game: chess.Board, timec: TimeControl):
        """Start a new permanent brain search on the game with pondering move made."""
        assert not done_computer_fen, 'brain() called with displayed move - fen: %s' % done_computer_fen
        if pb_move:
            game_copy = copy.deepcopy(game)
            game_copy.push(pb_move)
            logging.info('start permanent brain with pondering move [%s] fen: %s', pb_move, game_copy.fen())
            engine.position(game_copy)
            engine.brain(timec.uci())
        else:
            logging.info('ignore permanent brain cause no pondering move available')

    def stop_search_and_clock(ponder_hit=False):
        """Depending on the interaction mode stop search and clock."""
        if interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.TRAINING): 
            stop_clock()
            ##if not emulation_mode(): ## molli: not for mame to avoid picochess gets stucked
            if engine.is_waiting():
                logging.info('engine already waiting')
            else:
                if ponder_hit:
                    pass  # we send the engine.hit() lateron!
                else:
                    stop_search()
        elif interaction_mode in (Mode.REMOTE, Mode.OBSERVE):
            stop_clock()
            stop_search()
        elif interaction_mode in (Mode.ANALYSIS, Mode.KIBITZ, Mode.PONDER):
            stop_search()

    def stop_search():
        """Stop current search."""
        engine.stop()
        if not emulation_mode(): ## molli: not for mame to avoid picochess gets stucked
            while not engine.is_waiting():
                time.sleep(0.05)
                logging.warning('engine is still not waiting')

    def stop_clock():
        """Stop the clock."""
        if interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.OBSERVE, Mode.REMOTE, Mode.TRAINING): 
            time_control.stop_internal()
            if interaction_mode == Mode.TRAINING: 
                pass 
            else: 
                DisplayMsg.show(Message.CLOCK_STOP(devs={'ser', 'i2c', 'web'}))
                time.sleep(0.5)  # @todo give some time to clock to really do it. Find a better solution!
        else:
            logging.warning('wrong function call [stop]! mode: %s', interaction_mode)

    def start_clock():
        """Start the clock."""
        if interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.OBSERVE, Mode.REMOTE, Mode.TRAINING): 
            time_control.start_internal(game.turn)
            tc_init = time_control.get_parameters()
            if interaction_mode == Mode.TRAINING: 
                pass 
            else: 
                DisplayMsg.show(Message.CLOCK_START(turn=game.turn, tc_init=tc_init, devs={'ser', 'i2c', 'web'}))
                time.sleep(0.5)  # @todo give some time to clock to really do it. Find a better solution!
        else:
            logging.warning('wrong function call [start]! mode: %s', interaction_mode)
    
    def check_game_state(game: chess.Board, play_mode: PlayMode):
        nonlocal time_control
        """
        Check if the game has ended or not ; it also sends Message to Displays if the game has ended.

        :param game:
        :param play_mode:
        :return: False is the game continues, Game_Ends() Message if it has ended
        """
        result = None
        if game.is_stalemate():
            result = GameResult.STALEMATE
        if game.is_insufficient_material():
            result = GameResult.INSUFFICIENT_MATERIAL
        if game.is_seventyfive_moves():
            result = GameResult.SEVENTYFIVE_MOVES
        if game.is_fivefold_repetition():
            result = GameResult.FIVEFOLD_REPETITION
        if game.is_checkmate():
            result = GameResult.MATE

        if result is None:
            return False
        else:
            return Message.GAME_ENDS(tc_init = time_control.get_parameters(), result=result, play_mode=play_mode, game=game.copy())

    def user_move(move: chess.Move, sliding: bool):
        """Handle an user move."""
        nonlocal game
        nonlocal done_move
        nonlocal done_computer_fen
        nonlocal time_control
        nonlocal no_guess_black
        nonlocal no_guess_white
        nonlocal max_guess_black
        nonlocal max_guess_white
        nonlocal picotutor
        nonlocal take_back_locked
        nonlocal takeback_active
        nonlocal automatic_takeback
        nonlocal play_mode
        nonlocal comment_file
        nonlocal book_in_use
        nonlocal last_move
        nonlocal com_factor
        nonlocal online_decrement
        global fen_error_occured
        global position_mode

        eval_str = ''
        
        take_back_locked = False

        logging.info('user move [%s] sliding: %s', move, sliding)
        if move not in game.legal_moves:
            logging.warning('illegal move [%s]', move)
        else:
            
            if interaction_mode == Mode.BRAIN:
                ponder_hit = (move == pb_move)
                logging.info('pondering move: [%s] res: Ponder%s', pb_move, 'Hit' if ponder_hit else 'Miss')
            else:
                ponder_hit = False
            if sliding and ponder_hit:
                logging.warning('sliding detected, turn ponderhit off')
                ponder_hit = False

            stop_search_and_clock(ponder_hit=ponder_hit)
            if interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.OBSERVE, Mode.REMOTE, Mode.TRAINING) and not sliding: 
                time_control.add_time(game.turn)
                ## molli new tournament time control
                if time_control.moves_to_go_orig > 0 and game.fullmove_number == time_control.moves_to_go_orig:
                    time_control.add_game2(game.turn)
                    t_player = True
                    msg = Message.TIMECONTROL_CHECK(player=t_player, movestogo=time_control.moves_to_go_orig, time1=time_control.game_time, time2=time_control.game_time2)
                    DisplayMsg.show(msg)
                if online_mode():
                    ## molli for online pseudo time sync
                    ##online_decrement = 2.0   ## try between 1.5 and 5 if out of sync with server times
                    if online_decrement > 0:
                        time_control.sub_online_time(game.turn, online_decrement)
                   
            game_before = game.copy()
            
            done_computer_fen = None
            done_move = chess.Move.null()
            fen = game.fen()
            turn = game.turn
            game.push(move)
            eval_str = ''
            
            if picotutor_mode() and not position_mode and not takeback_active:
                l_mate = ''
                t_hint_move = chess.Move.null()
                ## set user_color ????????
                valid = picotutor.push_move(move) ##  molli: picotutor
                ## get evalutaion result and give user feedback
                if dgtmenu.get_picowatcher():
                    if valid:
                        eval_str, l_mate, l_hint = picotutor.get_user_move_eval()
                    else:
                        ## invalid move from tutor side!? Something went wrong
                        eval_str = 'ER'
                        picotutor.set_position(game.fen(), i_turn = game.turn)
                        if play_mode == PlayMode.USER_BLACK:
                            picotutor.set_user_color(chess.BLACK)
                        else:
                            picotutor.set_user_color(chess.WHITE)
                            l_mate = ''
                        eval_str = '' ## no error message
                    if eval_str != '' and last_move != move: ##molli takeback_mame
                        msg = Message.PICOTUTOR_MSG(eval_str = eval_str)
                        DisplayMsg.show(msg)
                        if '??' in eval_str:
                            time.sleep(3)
                        else:
                            time.sleep(1)
                    if l_mate:
                        n_mate = int(l_mate)
                    else:
                        n_mate = 0
                    if n_mate < 0:
                        msg_str = 'USRMATE_' + str(abs(n_mate))
                        msg = Message.PICOTUTOR_MSG(eval_str = msg_str)
                        DisplayMsg.show(msg)
                        time.sleep(1.5)
                    elif n_mate > 1:
                        n_mate = n_mate - 1
                        msg_str = 'PICMATE_' + str(abs(n_mate))
                        msg = Message.PICOTUTOR_MSG(eval_str = msg_str)
                        DisplayMsg.show(msg)
                        time.sleep(1.5)
                    ## get additional info in case of blunder
                    if eval_str == '??' and last_move != move: ##molli takeback_mame
                        t_hint_move = chess.Move.null()
                        threat_move = chess.Move.null()
                        t_mate, t_hint_move, t_pv_best_move, t_pv_user_move = picotutor.get_user_move_info()
                        ##print("Pico-Tutor Info: %s" % str(pv_user_move))
                        
                        try:
                            threat_move = t_pv_user_move[1]
                        except:
                            threat_move = chess.Move.null()
                        
                        if threat_move != chess.Move.null():
                            game_tutor = game_before.copy()
                            game_tutor.push(move)
                            san_move = game_tutor.san(threat_move)
                            game_tutor.push(t_pv_user_move[1])  ## for picotalker (last move spoken)
                            
                            tutor_str = 'THREAT' + san_move
                            msg = Message.PICOTUTOR_MSG(eval_str = tutor_str, game = game_tutor.copy())
                            DisplayMsg.show(msg)
                            time.sleep(5)
        
                        if t_hint_move.uci() != chess.Move.null():
                            game_tutor = game_before.copy()
                            san_move = game_tutor.san(t_hint_move)
                            game_tutor.push(t_hint_move)
                            tutor_str = 'HINT' + san_move
                            msg = Message.PICOTUTOR_MSG(eval_str = tutor_str, game = game_tutor.copy())
                            DisplayMsg.show(msg)
                            time.sleep(5)
            
                if game.fullmove_number < 1:
                    ModeInfo.reset_opening()
                    
            searchmoves.reset()
            if interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.TRAINING): 
                msg = Message.USER_MOVE_DONE(move=move, fen=fen, turn=turn, game=game.copy())
                game_end = check_game_state(game, play_mode)
                if game_end:
                    ## molli: for online/emulation mode we have to publish this move as well to the engine
                    if online_mode():
                        logging.info('starting think()')
                        think(game, time_control, msg)
                    elif emulation_mode():
                        logging.info('molli: starting mame_endgame()')
                        mame_endgame(game, time_control, msg)
                        DisplayMsg.show(msg)
                        DisplayMsg.show(game_end)
                        legal_fens_after_cmove = [] # molli
                    else:
                        DisplayMsg.show(msg)
                        DisplayMsg.show(game_end)
                        legal_fens_after_cmove = [] # molli
                else:
                    if interaction_mode in (Mode.NORMAL, Mode.TRAINING) or not ponder_hit: 
                        if not check_game_state(game, play_mode):
                            ## molli: automatic takeback of blunder moves for mame engines
                            if emulation_mode() and eval_str == '??' and last_move != move: 
                                ## molli: do not send move to engine
                                ## wait for take back or lever button in case of no takeback
                                takeback_active = True
                                automatic_takeback = True ## to be reset in think!
                                set_wait_state(Message.TAKE_BACK(game=game.copy()))
                            else:
                                ## send move to engine
                                logging.info('starting think()')
                                think(game, time_control, msg)
                    else:
                        logging.info('think() not started cause ponderhit')
                        DisplayMsg.show(msg)
                        start_clock()
                        engine.hit()  # finally tell the engine
                last_move = move
            elif interaction_mode == Mode.REMOTE:
                msg = Message.USER_MOVE_DONE(move=move, fen=fen, turn=turn, game=game.copy())
                game_end = check_game_state(game, play_mode)
                if game_end:
                    DisplayMsg.show(msg)
                    DisplayMsg.show(game_end)
                else:
                    observe(game, msg)
            elif interaction_mode == Mode.OBSERVE:
                msg = Message.REVIEW_MOVE_DONE(move=move, fen=fen, turn=turn, game=game.copy())
                game_end = check_game_state(game, play_mode)
                if game_end:
                    DisplayMsg.show(msg)
                    DisplayMsg.show(game_end)
                else:
                    observe(game, msg)
            else:  # interaction_mode in (Mode.ANALYSIS, Mode.KIBITZ, Mode.PONDER):
                msg = Message.REVIEW_MOVE_DONE(move=move, fen=fen, turn=turn, game=game.copy())
                game_end = check_game_state(game, play_mode)
                if game_end:
                    DisplayMsg.show(msg)
                    DisplayMsg.show(game_end)
                else:
                    analyse(game, msg)
            
            if picotutor_mode() and not position_mode and not takeback_active and not automatic_takeback:
                if dgtmenu.get_picoexplorer():
                    op_name = ''
                    op_in_book = False
                    op_eco, op_name, op_moves, op_in_book = picotutor.get_opening()
                    if op_in_book and op_name:
                        ModeInfo.set_opening(book_in_use, str(op_name), op_eco)
                        DisplayMsg.show(Message.SHOW_TEXT(text_string=op_name))
                        time.sleep(0.7)
                
                if dgtmenu.get_picocomment() != PicoComment.COM_OFF and not game_end:
                    game_comment = ''
                    game_comment = picotutor.get_game_comment(pico_comment=dgtmenu.get_picocomment(), com_factor=com_factor)
                    if game_comment:
                        DisplayMsg.show(Message.SHOW_TEXT(text_string=game_comment))
                        time.sleep(0.7)
            takeback_active = False

    def is_not_user_turn(turn):
        """Return if it is users turn (only valid in normal, brain or remote mode)."""
        assert interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.REMOTE, Mode.TRAINING), 'wrong mode: %s' % interaction_mode 
        condition1 = (play_mode == PlayMode.USER_WHITE and turn == chess.BLACK)
        condition2 = (play_mode == PlayMode.USER_BLACK and turn == chess.WHITE)
        return condition1 or condition2

    def process_fen(fen: str):
        """Process given fen like doMove, undoMove, takebackPosition, handleSliding."""
        nonlocal flag_premove
        nonlocal last_legal_fens
        nonlocal searchmoves
        nonlocal legal_fens
        nonlocal legal_fens_after_cmove # molli
        nonlocal game
        nonlocal done_move
        nonlocal done_computer_fen
        nonlocal pb_move
        nonlocal error_fen
        nonlocal play_mode
        nonlocal flag_picotutor
        nonlocal best_move_posted
        nonlocal best_move_displayed
        nonlocal book_in_use 
        nonlocal takeback_active
        nonlocal no_guess_black
        nonlocal no_guess_white
        nonlocal max_guess_black
        nonlocal max_guess_white
        nonlocal play_mode
        nonlocal time_control
        nonlocal automatic_takeback
        
        global   flag_startup
        global   fen_error_occured
        global   position_mode
        global   start_time_cmove_done

        handled_fen = True
        error_fen = None
        ## molli / WD
        legal_fens_pico = compute_legal_fens(game.copy())
        # Check for same position
        if fen == game.board_fen():
            logging.debug('Already in this fen: %s', fen)
            flag_startup = False
            ## molli: Chess tutor
            if picotutor_mode()and dgtmenu.get_picocoach() and fen != chess.STARTING_BOARD_FEN and not take_back_locked and not fen_error_occured and not position_mode and not automatic_takeback:
                if ((game.turn == chess.WHITE and play_mode == PlayMode.USER_WHITE) or (game.turn == chess.BLACK and play_mode == PlayMode.USER_BLACK)) and not(game.is_checkmate() or game.is_stalemate()):
                    stop_clock()
                    stop_fen_timer()
                    eval_str = 'ANALYSIS'
                    msg = Message.PICOTUTOR_MSG(eval_str = eval_str)
                    DisplayMsg.show(msg)
                    time.sleep(2)
                    
                    t_best_move, t_best_score, t_best_mate, t_pv_best_move, t_alt_best_moves = picotutor.get_pos_analysis()
                    
                    tutor_str = 'POS' + str(t_best_score)
                    msg = Message.PICOTUTOR_MSG(eval_str = tutor_str, score = t_best_score)
                    DisplayMsg.show(msg)
                    time.sleep(5)
                
                    if t_best_mate:
                        l_mate = int(t_best_mate)
                        if t_best_move != chess.Move.null():
                            game_tutor = game.copy()
                            san_move = game_tutor.san(t_best_move)
                            game_tutor.push(t_best_move)  ## for picotalker (last move spoken)
                            tutor_str = 'BEST' + san_move
                            msg = Message.PICOTUTOR_MSG(eval_str = tutor_str, game = game_tutor.copy())
                            DisplayMsg.show(msg)
                            time.sleep(5)
                    else:
                        l_mate = 0
                    if l_mate > 0:
                        eval_str = 'PICMATE_' + str(abs(l_mate))
                        msg = Message.PICOTUTOR_MSG(eval_str = eval_str)
                        DisplayMsg.show(msg)
                        time.sleep(5)
                    elif l_mate < 0:
                        eval_str = 'USRMATE_' + str(abs(l_mate))
                        msg = Message.PICOTUTOR_MSG(eval_str = eval_str)
                        DisplayMsg.show(msg)
                        time.sleep(5)
                    else:
                        l_max = 0
                        for alt_move in t_alt_best_moves:
                            l_max = l_max + 1
                            if l_max <= 3:
                                game_tutor = game.copy()
                                san_move = game_tutor.san(alt_move)
                                game_tutor.push(alt_move)  ## for picotalker (last move spoken)
                                
                                tutor_str = 'BEST' + san_move
                                msg = Message.PICOTUTOR_MSG(eval_str = tutor_str, game = game_tutor.copy())
                                DisplayMsg.show(msg)
                                time.sleep(5)
                            else:
                                break
    
                    start_clock()
            else:
                if position_mode:
                    ## position finally alright!
                    tutor_str = 'POSOK'
                    msg = Message.PICOTUTOR_MSG(eval_str = tutor_str, game = game.copy())
                    DisplayMsg.show(msg)
                    position_mode = False
                    time.sleep(1)
                    if not done_computer_fen:
                        start_clock()
                    DisplayMsg.show(Message.EXIT_MENU())
        
        # Check if we have to undo a previous move (sliding)
        elif fen in last_legal_fens:
            logging.info('sliding move detected')
            if interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.TRAINING): 
                if is_not_user_turn(game.turn):
                    stop_search()
                    game.pop()
                    if picotutor_mode():
                        if best_move_posted:
                            picotutor.pop_last_move() ## bestmove already sent to tutor
                            best_move_posted = False
                        picotutor.pop_last_move() ## no switch of sides
                    logging.info('user move in computer turn, reverting to: %s', game.fen())
                elif done_computer_fen:
                    done_computer_fen = None
                    done_move = chess.Move.null()
                    game.pop()
                    if picotutor_mode():
                        if best_move_posted:
                            picotutor.pop_last_move() ## bestmove already sent to tutor
                            best_move_posted = False
                        picotutor.pop_last_move() ## no switch of sides
                    logging.info('user move while computer move is displayed, reverting to: %s', game.fen())
                else:
                    handled_fen = False
                    logging.error('last_legal_fens not cleared: %s', game.fen())
            elif interaction_mode == Mode.REMOTE:
                if is_not_user_turn(game.turn):
                    game.pop()
                    if picotutor_mode():
                        if best_move_posted:
                            picotutor.pop_last_move() ## bestmove already sent to tutor
                            best_move_posted = False
                        picotutor.pop_last_move()
                    logging.info('user move in remote turn, reverting to: %s', game.fen())
                elif done_computer_fen:
                    done_computer_fen = None
                    done_move = chess.Move.null()
                    game.pop()
                    if picotutor_mode():
                        if best_move_posted:
                            picotutor.pop_last_move() ## bestmove already sent to tutor
                            best_move_posted = False
                        picotutor.pop_last_move()
                    logging.info('user move while remote move is displayed, reverting to: %s', game.fen())
                else:
                    handled_fen = False
                    logging.error('last_legal_fens not cleared: %s', game.fen())
            else:
                game.pop()
                if picotutor_mode():
                    if best_move_posted:
                        picotutor.pop_last_move() ## bestmove already sent to tutor
                        best_move_posted = False
                    picotutor.pop_last_move()
                    ## just to be sure set fen pos.
                    game_copy = copy.deepcopy(game)
                    picotutor.set_position(game_copy.fen(), i_turn = game_copy.turn)
                    if play_mode == PlayMode.USER_BLACK:
                        picotutor.set_user_color(chess.BLACK)
                    else:
                        picotutor.set_user_color(chess.WHITE)
                logging.info('wrong color move -> sliding, reverting to: %s', game.fen())
            legal_moves = list(game.legal_moves)
            move = legal_moves[last_legal_fens.index(fen)]  # type: chess.Move
            user_move(move, sliding=True)
            if interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.REMOTE, Mode.TRAINING): 
                legal_fens = []
            else:
                legal_fens = compute_legal_fens(game.copy())
    
        ## allow playing/correcting moves for pico's side in TRAINING mode:
        elif fen in legal_fens_pico and interaction_mode == Mode.TRAINING:
            legal_moves = list(game.legal_moves)
            move = legal_moves[legal_fens_pico.index(fen)]  # type: chess.Move
            
            if done_computer_fen: 
                if fen == done_computer_fen: 
                    pass 
                else: 
                    DisplayMsg.show(Message.WRONG_FEN()) # display set pieces/pico's move
                    time.sleep(3) # display set pieces again and accept new players move as pico's move
                    DisplayMsg.show(Message.ALTERNATIVE_MOVE(game=game.copy(), play_mode=play_mode))
                    time.sleep(2)
                    DisplayMsg.show(Message.COMPUTER_MOVE(move=move, ponder=False, game=game.copy(), wait=False))
                    time.sleep(2)
            logging.info('user move did a move for pico')
           
            user_move(move, sliding=False)
            last_legal_fens = legal_fens
            if interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.REMOTE, Mode.TRAINING):
                legal_fens = []
            else:
                legal_fens = compute_legal_fens(game.copy())
    
        # standard legal move
        elif fen in legal_fens:
            logging.info('standard move detected')
            # time_control.add_inc(game.turn)  # deactivated and moved to user_move() cause tc still running :-(
            legal_moves = list(game.legal_moves)
            move = legal_moves[legal_fens.index(fen)]  # type: chess.Move
            user_move(move, sliding=False)
            last_legal_fens = legal_fens
            if interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.REMOTE):
                legal_fens = []
            else:
                legal_fens = compute_legal_fens(game.copy())
    
    # molli: allow direct play of an alternative move for pico
        elif fen in legal_fens_pico and not fen in legal_fens and fen != done_computer_fen and done_computer_fen and interaction_mode in (Mode.NORMAL, Mode.BRAIN) and not online_mode() and not emulation_mode() and not pgn_mode() and dgtmenu.get_game_altmove() and not takeback_active:
            legal_moves = list(game.legal_moves)
            computer_move = done_move
            done_move = legal_moves[legal_fens_pico.index(fen)]  # type: chess.Move
            best_move_posted = False
            best_move_displayed = None
            time.sleep(3)
            DisplayMsg.show(Message.WRONG_FEN()) # display set pieces/pico's move
            time.sleep(3) ## display set pieces again and accept new players move as pico's move
            if computer_move:
                DisplayMsg.show(Message.COMPUTER_MOVE(move=computer_move, ponder=False, game=game.copy(), wait=False))
                time.sleep(3)
            DisplayMsg.show(Message.ALTERNATIVE_MOVE(game=game.copy(), play_mode=play_mode))
            time.sleep(2)
            if done_move:
                DisplayMsg.show(Message.COMPUTER_MOVE(move=done_move, ponder=False, game=game.copy(), wait=False))
                time.sleep(1.5)
            
            DisplayMsg.show(Message.COMPUTER_MOVE_DONE())
            logging.info('user did a move for pico')
            game.push(done_move)
            done_computer_fen = None
            done_move = chess.Move.null()
            game_end = check_game_state(game, play_mode)
            # time_control.add_inc(game.turn)  # deactivated and moved to user_move() cause tc still running :-(
            valid = True
            if picotutor_mode():
                picotutor.pop_last_move()
                valid = picotutor.push_move(done_move)
                if not valid:
                    eval_str = 'ER'
                    picotutor.reset() ##molli picotutor
                    picotutor.set_position(game.fen(), i_turn = game.turn)
                        
            if game_end:
                legal_fens = []
                legal_fens_after_cmove = [] # molli
                if online_mode(): ##molli
                    stop_search_and_clock()
                    stop_fen_timer()
                stop_search_and_clock()
                DisplayMsg.show(game_end)
            else:
                searchmoves.reset()
                time_control.add_time(not game.turn)
                
                ## molli new tournament time control
                if time_control.moves_to_go_orig > 0 and (game.fullmove_number - 1) == time_control.moves_to_go_orig:
                    time_control.add_game2(not game.turn)
                    t_player = False
                    msg = Message.TIMECONTROL_CHECK(player=t_player, movestogo=time_control.moves_to_go_orig, time1=time_control.game_time, time2=time_control.game_time2)
                    DisplayMsg.show(msg)
            
                start_clock()
            
                if interaction_mode == Mode.BRAIN:
                    brain(game, time_control)

        ##legal_fens_after_cmove = compute_legal_fens(game_copy) # molli
            legal_fens = compute_legal_fens(game.copy()) ## calc. new legal moves based on alt. move
            last_legal_fens = []

        # Player has done the computer or remote move on the board
        elif fen == done_computer_fen:
            logging.info('done move detected')
            assert interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.REMOTE, Mode.TRAINING), 'wrong mode: %s' % interaction_mode 
            if not pgn_mode():
                DisplayMsg.show(Message.COMPUTER_MOVE_DONE())       ##molli pgn
            
            best_move_posted = False
            game.push(done_move)
            done_computer_fen = None
            done_move = chess.Move.null()
            
            if online_mode() or emulation_mode():
            ## for online or emulation engine the user time alraedy runs with move announcement
            ## => subtract time between announcement and execution
                end_time_cmove_done = time.time()
                cmove_time = math.floor(end_time_cmove_done - start_time_cmove_done)
                if cmove_time > 0:
                    time_control.sub_online_time(game.turn, cmove_time)
                cmove_time = 0
                start_time_cmove_done = 0
            
            game_end = check_game_state(game, play_mode)
            if game_end:
                legal_fens = []
                legal_fens_after_cmove = [] # molli
                if online_mode(): ##molli time_online
                    stop_search_and_clock()
                    stop_fen_timer()
                stop_search_and_clock()
                DisplayMsg.show(game_end)
            else:
                searchmoves.reset()
                
                time_control.add_time(not game.turn)
                
                ## molli new tournament time control
                if time_control.moves_to_go_orig > 0 and (game.fullmove_number - 1) == time_control.moves_to_go_orig:
                    time_control.add_game2(not game.turn)
                    t_player = False
                    msg = Message.TIMECONTROL_CHECK(player=t_player, movestogo=time_control.moves_to_go_orig, time1=time_control.game_time, time2=time_control.game_time2)
                    DisplayMsg.show(msg)
                
                if not online_mode() or game.fullmove_number > 1:
                    start_clock()
                else:
                    DisplayMsg.show(Message.EXIT_MENU()) ## show clock
                    end_time_cmove_done = 0
            
                if interaction_mode == Mode.BRAIN:
                    brain(game, time_control)

                legal_fens = compute_legal_fens(game.copy())
                
                if pgn_mode():  ##molli pgn
                    log_pgn()
                    if game.turn == chess.WHITE:
                        if max_guess_white > 0:
                            if no_guess_white > max_guess_white:
                                last_legal_fens = []
                                get_next_pgn_move()  ##molli pgn
                        else:
                            last_legal_fens = []
                            get_next_pgn_move()  ##molli pgn
                    elif game.turn == chess.BLACK:
                        if max_guess_black > 0:
                            if no_guess_black > max_guess_black:
                                last_legal_fens = []
                                get_next_pgn_move()  ##molli pgn
                        else:
                            last_legal_fens = []
                            get_next_pgn_move()  ##molli pgn
                    
            last_legal_fens = []
            
            if game.fullmove_number < 1:
                ModeInfo.reset_opening()
            if picotutor_mode() and dgtmenu.get_picoexplorer():
                op_eco, op_name, op_moves, op_in_book = picotutor.get_opening()
                if op_in_book and op_name:
                    ModeInfo.set_opening(book_in_use, str(op_name), op_eco)
                    DisplayMsg.show(Message.SHOW_TEXT(text_string=op_name))

        # molli: Premove/fast move: Player has done the computer move and his own move in rapid sequence 
        elif fen in legal_fens_after_cmove and flag_premove and done_move != chess.Move.null(): ## and interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.TRAINING):
            logging.info('standard move after computer move detected')
            # time_control.add_inc(game.turn)  # deactivated and moved to user_move() cause tc still running :-(
            # molli: execute computer move first
            game.push(done_move)
            done_computer_fen = None
            done_move = chess.Move.null()
            best_move_posted = False
            searchmoves.reset()
           
            time_control.add_time(not game.turn)
            ## molli new tournament time control
            if time_control.moves_to_go_orig > 0 and (game.fullmove_number - 1) == time_control.moves_to_go_orig:
                time_control.add_game2(not game.turn)
                t_player = False
                msg = Message.TIMECONTROL_CHECK(player=t_player, movestogo=time_control.moves_to_go_orig, time1=time_control.game_time, time2=time_control.game_time2 )
                DisplayMsg.show(msg)
                    
            if interaction_mode == Mode.BRAIN:
                brain(game, time_control)

            last_legal_fens = []
            legal_fens_after_cmove = []
            legal_fens = compute_legal_fens(game.copy()) # molli new legal fance based on cmove
            
            # standard user move handling
            legal_moves = list(game.legal_moves)
            move = legal_moves[legal_fens.index(fen)]  # type: chess.Move
            user_move(move, sliding=False)
            last_legal_fens = legal_fens
            if interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.REMOTE, Mode.TRAINING):
                legal_fens = []
            else:
                legal_fens = compute_legal_fens(game.copy())

        # Check if this is a previous legal position and allow user to restart from this position
        else:
            if take_back_locked or online_mode() or (emulation_mode() and not automatic_takeback):
                handled_fen = False
            else:
                handled_fen = False
                game_copy = copy.deepcopy(game)
                while game_copy.move_stack:
                    game_copy.pop()
                    if game_copy.board_fen() == fen:
                        handled_fen = True
                        logging.info('current game fen      : %s', game.fen())
                        logging.info('undoing game until fen: %s', fen)
                        stop_search_and_clock()
                        while len(game_copy.move_stack) < len(game.move_stack):
                            game.pop()
                            
                            if picotutor_mode():
                                if best_move_posted:   ## molli computer move already sent to tutor!
                                    picotutor.pop_last_move()
                                    best_move_posted = False
                                picotutor.pop_last_move()
                            
                        # its a complete new pos, delete saved values
                        done_computer_fen = None
                        done_move = pb_move = chess.Move.null()
                        searchmoves.reset()
                        takeback_active = True
                        set_wait_state(Message.TAKE_BACK(game=game.copy()))  # new: force stop no matter if picochess turn
                        
                        break
        
                if pgn_mode():  ##molli pgn
                    #logging.debug('molli pgn: take back check')
                    log_pgn()
                    if max_guess_white > 0:
                        if game.turn == chess.WHITE:
                            if no_guess_white > max_guess_white:
                                get_next_pgn_move()  ##molli pgn
                    elif max_guess_black > 0:
                        if game.turn == chess.BLACK:
                            if no_guess_black > max_guess_black:
                                get_next_pgn_move()  ##molli pgn
    
        # doing issue #152
        logging.debug('fen: %s result: %s', fen, handled_fen)
        stop_fen_timer()
        if handled_fen:
            flag_startup = False
            error_fen = None
            fen_error_occured = False
            if position_mode:
                ## position finally alright!
                tutor_str = 'POSOK'
                msg = Message.PICOTUTOR_MSG(eval_str = tutor_str, game = game.copy())
                DisplayMsg.show(msg)
                position_mode = False
                time.sleep(1)
                if not done_computer_fen:
                    start_clock()
                DisplayMsg.show(Message.EXIT_MENU())
        else:
            if fen == chess.STARTING_BOARD_FEN:
                pos960 = 518
                error_fen = None
                if position_mode:
                    ## position finally alright!
                    tutor_str = 'POSOK'
                    msg = Message.PICOTUTOR_MSG(eval_str = tutor_str, game = game.copy())
                    DisplayMsg.show(msg)
                    position_mode = False
                    if not done_computer_fen:
                        start_clock()
                Observable.fire(Event.NEW_GAME(pos960=pos960))
            else:
                error_fen = fen
                start_fen_timer()

    def set_wait_state(msg: Message, start_search=True):
        nonlocal time_control
        nonlocal takeback_active
        nonlocal automatic_takeback
        global reset_auto
        """Enter engine waiting (normal mode) and maybe (by parameter) start pondering."""
        if not done_computer_fen:
            nonlocal play_mode, legal_fens, last_legal_fens
            legal_fens = compute_legal_fens(game.copy())
            last_legal_fens = []
        if interaction_mode in (Mode.NORMAL, Mode.BRAIN):  # @todo handle Mode.REMOTE too
            if done_computer_fen:
                logging.debug('best move displayed, dont search and also keep play mode: %s', play_mode)
                start_search = False
            else:
                old_mode = play_mode
                play_mode = PlayMode.USER_WHITE if game.turn == chess.WHITE else PlayMode.USER_BLACK
                if old_mode != play_mode:
                    logging.debug('new play mode: %s', play_mode)  # @todo below: for the moment send it to display too
                    text = play_mode.value  # type: str
                    if play_mode == PlayMode.USER_BLACK:
                        user_color = chess.BLACK
                    else:
                        user_color = chess.WHITE
                    if picotutor_mode():
                        picotutor.set_user_color(user_color)
                    DisplayMsg.show(Message.PLAY_MODE(play_mode=play_mode, play_mode_text=dgttranslate.text(text)))
        if start_search:
            assert engine.is_waiting(), 'engine not waiting! thinking status: %s' % engine.is_thinking()
            # Go back to analysing or observing
            if interaction_mode == Mode.BRAIN and not done_computer_fen:
                brain(game, time_control)
            if interaction_mode in (Mode.ANALYSIS, Mode.KIBITZ, Mode.PONDER, Mode.TRAINING): 
                analyse(game, msg)
                return
            if interaction_mode in (Mode.OBSERVE, Mode.REMOTE):
                # observe(game)  # dont want to autostart the clock => we are in newgame situation
                analyse(game, msg)
                return
        if not reset_auto:
            if automatic_takeback:
                stop_search_and_clock()
                reset_auto = True
            DisplayMsg.show(msg)
        else:
            automatic_takeback = False
            takeback_active = False
            reset_auto = False
        stop_fen_timer()

    def transfer_time(time_list: list, depth=0):
        """Transfer the time list to a TimeControl Object and a Text Object."""
        def _num(time_str):
            try:
                value = int(time_str)
                if value > 999:
                    value = 999
                return value
            except ValueError:
                return 1
        
        i_depth = _num(depth)
                
        if i_depth > 0: ##molli depth support
            fixed = 671
            timec = TimeControl(TimeMode.FIXED, fixed=fixed, depth=i_depth)
            textc = dgttranslate.text('B00_tc_depth', timec.get_list_text())
        elif len(time_list) == 1:
            fixed = _num(time_list[0])
            timec = TimeControl(TimeMode.FIXED, fixed=fixed)
            textc = dgttranslate.text('B00_tc_fixed', timec.get_list_text())
        elif len(time_list) == 2:
            blitz = _num(time_list[0])
            fisch = _num(time_list[1])
            if fisch == 0:
                timec = TimeControl(TimeMode.BLITZ, blitz=blitz)
                textc = dgttranslate.text('B00_tc_blitz', timec.get_list_text())
            else:
                timec = TimeControl(TimeMode.FISCHER, blitz=blitz, fischer=fisch)
                textc = dgttranslate.text('B00_tc_fisch', timec.get_list_text())
        elif len(time_list) == 3: ## molli new tournament time control
            moves_to_go = _num(time_list[0])
            blitz       = _num(time_list[1])
            blitz2      = _num(time_list[2])
            if blitz2 == 0:
                timec = TimeControl(TimeMode.BLITZ, blitz=blitz, moves_to_go=moves_to_go, blitz2=blitz2)
                textc = dgttranslate.text('B00_tc_tourn', timec.get_list_text())
            else:
                fisch = blitz2
                blitz2 = 0
                timec = TimeControl(TimeMode.FISCHER, blitz=blitz, fischer=fisch, moves_to_go=moves_to_go, blitz2=blitz2)
                textc = dgttranslate.text('B00_tc_tourn', timec.get_list_text())
        elif len(time_list) == 4: ## molli new tournament time control
            moves_to_go = _num(time_list[0])
            blitz       = _num(time_list[1])
            fisch       = _num(time_list[2])
            blitz2      = _num(time_list[3])
            if fisch == 0:
                timec = TimeControl(TimeMode.BLITZ, blitz=blitz, moves_to_go=moves_to_go, blitz2=blitz2)
                textc = dgttranslate.text('B00_tc_tourn', timec.get_list_text())
            else:
                timec = TimeControl(TimeMode.FISCHER, blitz=blitz, fischer=fisch, moves_to_go=moves_to_go, blitz2=blitz2)
                textc = dgttranslate.text('B00_tc_tourn', timec.get_list_text())
        else:
            timec = TimeControl(TimeMode.BLITZ, blitz=5)
            textc = dgttranslate.text('B00_tc_blitz', timec.get_list_text())
        return timec, textc
    
    def get_engine_level_dict(engine_level):
        """Transfer an engine level to its level_dict plus an index."""
        installed_engines = engine.get_installed_engines()
        for index in range(0, len(installed_engines)):
            eng = installed_engines[index]
            if eng['file'] == engine.get_file():
                level_list = sorted(eng['level_dict'])
                try:
                    level_index = level_list.index(engine_level)
                    return eng['level_dict'][level_list[level_index]], level_index
                except ValueError:
                    break
        return {}, None

    def engine_mode():
        ponder_mode = analyse_mode = False
        if False:  # switch-case
            pass
        elif interaction_mode in (Mode.NORMAL, Mode.REMOTE, Mode.TRAINING): 
            pass
        elif interaction_mode == Mode.BRAIN:
            ponder_mode = True
        elif interaction_mode in (Mode.ANALYSIS, Mode.KIBITZ, Mode.OBSERVE, Mode.PONDER):
            analyse_mode = True
        engine.mode(ponder=ponder_mode, analyse=analyse_mode)

    def _dgt_serial_nr():
        DisplayMsg.show(Message.DGT_SERIAL_NR(number='dont_use'))
    
    def switch_online(): ## molli
        nonlocal play_mode
        nonlocal last_legal_fens
        nonlocal legal_fens
        nonlocal legal_fens_after_cmove
        nonlocal time_control
        color = ''
        
        if online_mode():
            login, own_color, own_user, opp_user, game_time, fischer_inc = read_online_user_info()
            logging.debug('molli own_color in switch_online [%s]', own_color)
            logging.debug('molli own_user in switch_online [%s]', own_user)
            logging.debug('molli opp_user in switch_online [%s]', opp_user)
            logging.debug('molli game_time in switch_online [%s]', game_time)
            logging.debug('molli fischer_inc in switch_online [%s]', fischer_inc)

            ModeInfo.set_online_mode(mode=True)
            ModeInfo.set_online_own_user(name=own_user)
            ModeInfo.set_online_opponent(name=opp_user)
            
            if len(own_color) > 1:
                color = own_color[2]
            else:
                color = own_color
            
            logging.debug('molli switch_online start timecontrol')
            set_online_tctrl(game_time, fischer_inc) ## online rc
            time_control.reset_start_time()
            
            logging.debug('molli switch_online new_color: %s', color)
            if (color == 'b' or color == 'B') and game.turn == chess.WHITE and play_mode == PlayMode.USER_WHITE and done_move == chess.Move.null():
            ## switch to black color for user and send a 'go' to the engine
                play_mode = PlayMode.USER_BLACK
                text = play_mode.value  # type: str
                msg = Message.PLAY_MODE(play_mode=play_mode, play_mode_text=dgttranslate.text(text))
                
                stop_search_and_clock()
                
                last_legal_fens = []
                legal_fens_after_cmove = [] # molli
                legal_fens = []

                ##time_control.reset_start_time()
                think(game, time_control, msg)

        else:
            ModeInfo.set_online_mode(mode=False)

        if pgn_mode():
             ModeInfo.set_pgn_mode(mode=True)
        else:
             ModeInfo.set_pgn_mode(mode=False)

    def get_next_pgn_move():
        
        nonlocal play_mode
        nonlocal last_legal_fens
        nonlocal legal_fens
        nonlocal legal_fens_after_cmove
        nonlocal no_guess_black
        nonlocal no_guess_white
        nonlocal max_guess_black
        nonlocal max_guess_white
        nonlocal done_computer_fen
        nonlocal done_move
        nonlocal best_move_displayed
        nonlocal time_control
        
        log_pgn()
        time.sleep(0.5)
        
        if max_guess_black > 0:
            no_guess_black = 1
        elif max_guess_white > 0:
            no_guess_white = 1
        
        ##Observable.fire(Event.SWITCH_SIDES())
        if not engine.is_waiting():
            stop_search_and_clock()
                
        last_legal_fens = []
        legal_fens_after_cmove = [] # molli
        best_move_displayed = done_computer_fen
        if best_move_displayed:
            move = done_move
            done_computer_fen = None
            done_move = pb_move = chess.Move.null()
        else:
            move = chess.Move.null()  # not really needed
        
        ##text = play_mode.value  # type: str
        play_mode = PlayMode.USER_WHITE if play_mode == PlayMode.USER_BLACK else PlayMode.USER_BLACK
        msg = Message.SET_PLAYMODE(play_mode=play_mode)
        DisplayMsg.show(msg) ##molli: only set play_mode, no output message!
        msg = Message.COMPUTER_MOVE_DONE()
        
        if time_control.mode == TimeMode.FIXED:
            time_control.reset()
        
        legal_fens = []
        game_end = check_game_state(game, play_mode)
        if game_end:
            DisplayMsg.show(msg)
        else:
            cond1 = game.turn == chess.WHITE and play_mode == PlayMode.USER_BLACK
            cond2 = game.turn == chess.BLACK and play_mode == PlayMode.USER_WHITE
            if cond1 or cond2:
                time_control.reset_start_time()
                think(game, time_control, msg)
            else:
                DisplayMsg.show(msg)
                start_clock()
                legal_fens = compute_legal_fens(game.copy())

    # Enable garbage collection - needed for engne swapping as objects orphaned
    gc.enable()

    # Command line argument parsing
    parser = configargparse.ArgParser(default_config_files=[os.path.join(os.path.dirname(__file__), 'picochess.ini')])
    parser.add_argument('-e', '--engine', type=str, help="UCI engine filename/path such as 'engines/armv7l/a-stockf'",
                        default=None)
    parser.add_argument('-el', '--engine-level', type=str, help='UCI engine level', default=None)
    parser.add_argument('-er', '--engine-remote', type=str,
                        help="UCI engine filename/path such as 'engines/armv7l/a-stockf'", default=None)
    parser.add_argument('-ers', '--engine-remote-server', type=str, help='adress of the remote engine server',
                        default=None)
    parser.add_argument('-eru', '--engine-remote-user', type=str, help='username for the remote engine server')
    parser.add_argument('-erp', '--engine-remote-pass', type=str, help='password for the remote engine server')
    parser.add_argument('-erk', '--engine-remote-key', type=str, help='key file for the remote engine server')
    parser.add_argument('-erh', '--engine-remote-home', type=str, help='engine home path for the remote engine server',
                        default='')
    parser.add_argument('-d', '--dgt-port', type=str,
                        help="enable dgt board on the given serial port such as '/dev/ttyUSB0'")
    parser.add_argument('-b', '--book', type=str, help="path of book such as 'books/b-flank.bin'",
                        default='books/h-varied.bin')
    parser.add_argument('-t', '--time', type=str, default='5 0',
                        help="Time settings <FixSec> or <StMin IncSec> like '10'(move) or '5 0'(game) or '3 2'(fischer) or '40 120 60' (tournament). \
                        All values must be below 999")
    parser.add_argument('-dept', '--depth', type=int, default=0, choices=range(0, 99), help="searchdepth per move for the engine") ##molli
    parser.add_argument('-norl', '--disable-revelation-leds', action='store_true', help='disable Revelation leds')
    parser.add_argument('-l', '--log-level', choices=['notset', 'debug', 'info', 'warning', 'error', 'critical'],
                        default='warning', help='logging level')
    parser.add_argument('-lf', '--log-file', type=str, help='log to the given file')
    parser.add_argument('-pf', '--pgn-file', type=str, help='pgn file used to store the games', default='games.pgn')
    parser.add_argument('-pu', '--pgn-user', type=str, help='user name for the pgn file', default=None)
    parser.add_argument('-pe', '--pgn-elo', type=str, help='user elo for the pgn file', default='-')
    parser.add_argument('-w', '--web-server', dest='web_server_port', nargs='?', const=80, type=int, metavar='PORT',
                        help='launch web server')
    parser.add_argument('-m', '--email', type=str, help='email used to send pgn/log files', default=None)
    parser.add_argument('-ms', '--smtp-server', type=str, help='adress of email server', default=None)
    parser.add_argument('-mu', '--smtp-user', type=str, help='username for email server', default=None)
    parser.add_argument('-mp', '--smtp-pass', type=str, help='password for email server', default=None)
    parser.add_argument('-me', '--smtp-encryption', action='store_true',
                        help='use ssl encryption connection to email server')
    parser.add_argument('-mf', '--smtp-from', type=str, help='From email', default='no-reply@picochess.org')
    parser.add_argument('-mk', '--mailgun-key', type=str, help='key used to send emails via Mailgun Webservice',
                        default=None)
    parser.add_argument('-bc', '--beep-config', choices=['none', 'some', 'all'], help='sets standard beep config',
                        default='some')
    parser.add_argument('-bs', '--beep-some-level', type=int, default=0x03,
                        help='sets (some-)beep level from 0(=no beeps) to 15(=all beeps)')
    parser.add_argument('-uv', '--user-voice', type=str, help='voice for user', default=None)
    parser.add_argument('-cv', '--computer-voice', type=str, help='voice for computer', default=None)
    parser.add_argument('-sv', '--speed-voice', type=int, help='voice speech factor from 0(=90%%) to 9(=135%%)',
                        default=2, choices=range(0, 10))
    parser.add_argument('-vv', '--volume-voice', type=int, help='voice volume factor from 0(=50%%) to 10(=100%%)', default=10, choices=range(0, 11)) #WD
    parser.add_argument('-sp', '--enable-setpieces-voice', action='store_true',
                        help="speak last computer move again when 'set pieces' displayed")
    parser.add_argument('-u', '--enable-update', action='store_true', help='enable picochess updates')
    parser.add_argument('-ur', '--enable-update-reboot', action='store_true', help='reboot system after update')
    parser.add_argument('-nocm', '--disable-confirm-message', action='store_true', help='disable confirmation messages')
    parser.add_argument('-v', '--version', action='version', version='%(prog)s version {}'.format(version),
                        help='show current version', default=None)
    parser.add_argument('-pi', '--dgtpi', action='store_true', help='use the DGTPi hardware')
    parser.add_argument('-pt', '--ponder-interval', type=int, default=3, choices=range(1, 9),
                        help='how long each part of ponder display should be visible (default=3secs)')
    parser.add_argument('-lang', '--language', choices=['en', 'de', 'nl', 'fr', 'es', 'it'], default='en',
                        help='picochess language')
    parser.add_argument('-c', '--enable-console', action='store_true', help='use console interface')
    parser.add_argument('-cl', '--enable-capital-letters', action='store_true', help='clock messages in capital letters')
    parser.add_argument('-noet', '--disable-et', action='store_true', help='some clocks need this to work - deprecated')
    parser.add_argument('-ss', '--slow-slide', type=int, default=0, choices=range(0, 10),
                        help='extra wait time factor for a stable board position (sliding detect)')
    parser.add_argument('-nosn', '--disable-short-notation', action='store_true', help='disable short notation')
    ### molli
    parser.add_argument('-comf', '--comment-factor', type=int, help='comment factor from 0 to 100 for voice and written commands', default=100, choices=range(0, 100))
    parser.add_argument('-roln', '--rolling-display-normal', action='store_true', help='switch on rolling display normal mode')
    parser.add_argument('-rolp', '--rolling-display-ponder', action='store_true', help='switch on rolling display ponder mode')
    parser.add_argument('-flex', '--flexible-analysis', action='store_false', help='switch off flexible analysis mode')
    parser.add_argument('-prem', '--premove', action='store_false', help='switch off premove detection')
    parser.add_argument('-ctga', '--continue-game', action='store_true', help='continue last game after (re)start of picochess')
    parser.add_argument('-seng', '--show-engine', action='store_false', help='show engine after startup and new game')
    parser.add_argument('-teng', '--tutor-engine', type=str, default='/opt/picochess/engines/armv7l/a-stockf', help='engine used for PicoTutor analysis')
    parser.add_argument('-watc', '--tutor-watcher', action='store_true', help='Pico Watcher: atomatic move evaluation, blunder warning & move suggestion, default is off')
    parser.add_argument('-coch', '--tutor-coach', action='store_true', help='Pico Coach: move and position evaluation, move suggestion etc. on demand, default is off')
    parser.add_argument('-open', '--tutor-explorer', action='store_true', help='Pico Opening Explorrer: shows the name(s) of the opening (based on ECO file), default is off')
    parser.add_argument('-tcom', '--tutor-comment', type=str, default='off', help='show game comments based on specific engines (=single) or in general (=all). Default value is off')
    parser.add_argument('-loc', '--location', type=str, default='auto', help='determine automatically location for pgn file if set to auto, otherwise the location string which is set will be used')
    parser.add_argument('-dtcs', '--def-timectrl', type=str, default='5 0', help='default time control setting when leaving an emulation engine after startup')
    parser.add_argument('-altm', '--alt-move', action='store_true', help='Playing direct alternative move for pico: default is off')
    parser.add_argument('-odec', '--online-decrement', type=float, default=2.0, help='Seconds to be subtracted after each own online move in order to sync with server times')
    
    args, unknown = parser.parse_known_args()

    # Enable logging
    if args.log_file:
        handler = RotatingFileHandler('logs' + os.sep + args.log_file, maxBytes=1.4 * 1024 * 1024, backupCount=5)
        logging.basicConfig(level=getattr(logging, args.log_level.upper()),
                            format='%(asctime)s.%(msecs)03d %(levelname)7s %(module)10s - %(funcName)s: %(message)s',
                            datefmt="%Y-%m-%d %H:%M:%S", handlers=[handler])
    logging.getLogger('chess.engine').setLevel(logging.INFO)  # don't want to get so many python-chess uci messages

    logging.debug('#' * 20 + ' PicoChess v%s ' + '#' * 20, version)
    # log the startup parameters but hide the password fields
    a_copy = copy.copy(vars(args))
    a_copy['mailgun_key'] = a_copy['smtp_pass'] = a_copy['engine_remote_key'] = a_copy['engine_remote_pass'] = '*****'
    logging.debug('startup parameters: %s', a_copy)
    if unknown:
        logging.warning('invalid parameter given %s', unknown)

    ## molli
    flag_pgn_game_over   = False
    flag_flexible_ponder = args.flexible_analysis
    flag_premove         = args.premove
    own_user             = ''
    opp_user             = ''
    game_time            = 0
    fischer_inc          = 0
    login                = ''
    engine_text          = ''
    flag_picotutor       = True
    set_location         = args.location
    best_move_posted     = False
    online_decrement     = args.online_decrement

    logging.debug('molli: flexible_ponder %s', str(flag_flexible_ponder))
    logging.debug('molli: premove %s', str(flag_premove))

    # wire some dgt classes
    dgtboard = DgtBoard(args.dgt_port, args.disable_revelation_leds, args.dgtpi, args.disable_et, args.slow_slide)
    dgttranslate = DgtTranslate(args.beep_config, args.beep_some_level, args.language, version)
    dgtmenu = DgtMenu(args.disable_confirm_message, args.ponder_interval,
                      args.user_voice, args.computer_voice, args.speed_voice, args.enable_capital_letters,
                      args.disable_short_notation, args.log_file, args.engine_remote_server,
                      args.rolling_display_normal, args.volume_voice,
                      args.rolling_display_ponder, args.show_engine, dgttranslate) ## molli WD

    dgtdispatcher = Dispatcher(dgtmenu)
    
    tutor_engine = args.tutor_engine
    dgtmenu.set_picocoach(args.tutor_coach)
    dgtmenu.set_picowatcher(args.tutor_watcher)
    dgtmenu.set_picoexplorer(args.tutor_explorer)

    if args.tutor_comment == 'off':
        dgtmenu.set_picocomment(PicoComment.COM_OFF)
    elif args.tutor_comment == 'single':
        dgtmenu.set_picocomment(PicoComment.COM_ON_ENG)
    elif args.tutor_comment == 'all':
        dgtmenu.set_picocomment(PicoComment.COM_ON_ALL)

    dgtmenu.set_game_contlast(args.continue_game)
    dgtmenu.set_game_altmove(args.alt_move)

    logging.debug('molli: depth %s', args.depth)
    
    time_control, time_text = transfer_time(args.time.split(), depth=args.depth)
    tc_init_last  = time_control.get_parameters() ## molli for eventual restore after pgn mode
    time_text.beep = False
 
    # The class dgtDisplay fires Event (Observable) & DispatchDgt (Dispatcher)
    DgtDisplay(dgttranslate, dgtmenu, time_control).start()
    
    # Create PicoTalker for speech output
    # molli: add probability factor for game comments args.com_fact
    com_factor =  args.comment_factor
    logging.debug('molli: probability factor for game comments args.comment_factor %s', com_factor)
    com_factor =  args.comment_factor
    PicoTalkerDisplay(args.user_voice, args.computer_voice, args.speed_voice, args.enable_setpieces_voice, com_factor).start()

    # Set up the volume for the speech output according to the settings from picochess.ini#WD
    volume_factor = int(args.volume_voice)
    if volume_factor > 10:
        volume_factor = 10
        dgtmenu.set_volume_voice(volume_factor)

    # Launch web server
    if args.web_server_port:
        WebServer(args.web_server_port, dgtboard).start()
        dgtdispatcher.register('web')

    if args.enable_console:
        logging.debug('starting PicoChess in console mode')
        RepeatedTimer(1, _dgt_serial_nr).start()  # simulate the dgtboard watchdog
    else:
        # Connect to DGT board
        logging.debug('starting PicoChess in board mode')
        if args.dgtpi:
            DgtPi(dgtboard).start()
            dgtdispatcher.register('i2c')
        else:
            logging.debug('(ser) starting the board connection')
            dgtboard.run()  # a clock can only be online together with the board, so we must start it infront
        DgtHw(dgtboard).start()
        dgtdispatcher.register('ser')

    # The class Dispatcher sends DgtApi messages at the correct (delayed) time out
    dgtdispatcher.start()
    
    # Save to PGN
    emailer = Emailer(email=args.email, mailgun_key=args.mailgun_key)
    emailer.set_smtp(sserver=args.smtp_server, suser=args.smtp_user, spass=args.smtp_pass,
                     sencryption=args.smtp_encryption, sfrom=args.smtp_from)

    PgnDisplay('games' + os.sep + args.pgn_file, emailer).start()
    if args.pgn_user:
        user_name = args.pgn_user
    else:
        if args.email:
            user_name = args.email.split('@')[0]
        else:
            user_name = 'Player'

    # Update
    if args.enable_update:
        update_picochess(args.dgtpi, args.enable_update_reboot, dgttranslate)
    
    #################################################
    
    ip_info_thread = threading.Timer(12, display_ip_info)  # give RaspberyPi 10sec time to startup its network devices
    ip_info_thread.start()

    fen_timer = threading.Timer(4, expired_fen_timer)
    fen_timer_running = False
    error_fen = None
    ###########################################

    # try the given engine first and if that fails the first/second from "engines.ini" then crush
    engine_file = args.engine ## molli

    # engine_home = 'engines' + os.sep + machine() ##molli # wd
    engine_home = engine_file # wd
    engine_remote_home = args.engine_remote_home.rstrip(os.sep) ##molli
    
    engine_tries = 0
    engine = engine_name = None
    uci_remote_shell = None
    
    uci_local_shell = UciShell(hostname='', username='', key_file='', password='')

    while engine_tries < 2:
        if engine_file is None:
            eng_ini = read_engine_ini(uci_local_shell.get(), engine_home)
            engine_file = eng_ini[engine_tries]['file']
            engine_tries += 1
            
        # Gentlemen, start your engines...
        # engine_file = os.path.basename(engine_file) # wd
        # engine = UciEngine(file=engine_file, uci_shell=uci_local_shell, home=engine_home) # wd
        engine = UciEngine(file=engine_file, uci_shell=uci_local_shell) # wd
        try:
            engine_name = engine.get_name()
            break
        except AttributeError:
            logging.error('engine %s not started', engine_file)
            engine_file = None

    if engine_tries == 2:
        time.sleep(3)
        DisplayMsg.show(Message.ENGINE_FAIL())
        time.sleep(2)
        sys.exit(-1)
    
    # Startup - internal
    game = chess.Board()  # Create the current game
    fen = game.fen()
    legal_fens = compute_legal_fens(game.copy())  # Compute the legal FENs
    legal_fens_after_cmove = [] # molli: Compute the legal FENs after having done the computer move
    is_out_of_time_already = False # molli: out of time message only once
    flag_startup = True

    all_books = get_opening_books()
    try:
        book_index = [book['file'] for book in all_books].index(args.book)
    except ValueError:
        logging.warning('selected book not present, defaulting to %s', all_books[7]['file'])
        book_index = 7
    book_in_use = args.book
    bookreader = chess.polyglot.open_reader(all_books[book_index]['file'])
    searchmoves = AlternativeMover()
    interaction_mode = Mode.NORMAL
    play_mode = PlayMode.USER_WHITE  # @todo handle Mode.REMOTE too

    last_legal_fens = []
    done_computer_fen = None
    done_move = chess.Move.null()
    game_declared = False  # User declared resignation or draw
    pb_move = chess.Move.null()  # safes the best ponder move so far (for permanent brain use)

    args.engine_level = None if args.engine_level == 'None' else args.engine_level
    engine_opt, level_index = get_engine_level_dict(args.engine_level)
    engine.startup(engine_opt)

    ##engine part
    # Startup - external
    level_name = args.engine_level
    if level_name:
        level_text = dgttranslate.text('B00_level', level_name)
        level_text.beep = False
    else:
        level_text = None
        level_name = ''

    sys_info = {'version': version, 'engine_name': engine_name, 'user_name': user_name, 'user_elo': args.pgn_elo}

    DisplayMsg.show(Message.SYSTEM_INFO(info=sys_info))
    DisplayMsg.show(Message.STARTUP_INFO(info={'interaction_mode': interaction_mode, 'play_mode': play_mode,
                                     'books': all_books, 'book_index': book_index,
                                     'level_text': level_text, 'level_name': level_name,
                                     'tc_init': time_control.get_parameters(), 'time_text': time_text}))
    ## Favorites
    dgtmenu.set_favorite_engines(engine.get_installed_engines2())
                                     
    DisplayMsg.show(Message.ENGINE_STARTUP(installed_engines=engine.get_installed_engines(), file=engine.get_file(), level_index=level_index, has_960=engine.has_chess960(), has_ponder=engine.has_ponder()))
    
    ## set timecontrol restore data set for normal engines after leaving emulation mode
    pico_time = args.def_timectrl
    
    if emulation_mode():
        flag_last_engine_emu = True
        time_control_l, time_text_l = transfer_time(pico_time.split(), depth=0)
        tc_init_last = time_control_l.get_parameters()
        
    if pgn_mode():
        ModeInfo.set_pgn_mode(mode=True)
        flag_last_engine_pgn = True
        det_pgn_guess_tctrl()
    else:
        ModeInfo.set_pgn_mode(mode=False)

    DisplayMsg.show(Message.ENGINE_SETUP()) ## molli

    if online_mode():
        ModeInfo.set_online_mode(mode=True)
        set_wait_state(Message.START_NEW_GAME(game=game.copy(), newgame=True)) ## molli
    else:
        ModeInfo.set_online_mode(mode=False)
        engine.newgame(game.copy())
    ###################
    ## molli PicoTutor
    ######################
    comment_file = get_comment_file()
    picotutor = PicoTutor(i_engine_path=tutor_engine, i_comment_file=comment_file, i_lang=args.language) ## default with stockfish engine
    picotutor.set_status(dgtmenu.get_picowatcher(), dgtmenu.get_picocoach(), dgtmenu.get_picoexplorer(), dgtmenu.get_picocomment())

    if picotutor_mode():
        t_eval_str = 'ACTIVE'
        t_msg = Message.PICOTUTOR_MSG(eval_str = t_eval_str)
        DisplayMsg.show(t_msg)
        time.sleep(1)

    ModeInfo.set_game_ending(result='*') ## for save game

    dgtmenu.set_state_eng() ##molli
    text = dgtmenu.enter_eng_name_menu()
    engine_text = str(text.l)
    dgtmenu.exit_menu()
    
    # Event loop
    logging.info('evt_queue ready')
    while True:
        try:
            event = evt_queue.get()
        except queue.Empty:
            pass
        else:
            logging.debug('received event from evt_queue: %s', event)
            if False:  # switch-case
                pass
            elif isinstance(event, Event.FEN):
                process_fen(event.fen)

            elif isinstance(event, Event.KEYBOARD_MOVE):
                move = event.move
                logging.debug('keyboard move [%s]', move)
                if move not in game.legal_moves:
                    logging.warning('illegal move. fen: [%s]', game.fen())
                else:
                    game_copy = game.copy()
                    game_copy.push(move)
                    fen = game_copy.board_fen()
                    DisplayMsg.show(Message.DGT_FEN(fen=fen, raw=False))

            elif isinstance(event, Event.LEVEL):
                if event.options:
                    engine.startup(event.options, False)
                DisplayMsg.show(Message.LEVEL(level_text=event.level_text, level_name=event.level_name,
                                              do_speak=bool(event.options)))
                stop_fen_timer()

            elif isinstance(event, Event.NEW_ENGINE):
                
                old_file = engine.get_file()
                old_options = {}
                raw_options = engine.get_options()
                for name, value in raw_options.items():  # transfer Option to string by using the "default" value
                    old_options[name] = str(value.default)
                engine_fallback = False
                # Stop the old engine cleanly
                if not emulation_mode():
                    stop_search()
                # Closeout the engine process and threads

                engine_file = event.eng['file']
                help_str    = engine_file.rsplit(os.sep, 1)[1]
                remote_file = engine_remote_home + os.sep + help_str

                flag_eng = False
                flag_eng = check_ssh(args.engine_remote_server, args.engine_remote_user, args.engine_remote_pass)

                logging.debug('molli check_ssh:%s', flag_eng)
                DisplayMsg.show(Message.ENGINE_SETUP()) ## molli
                
                if remote_engine_mode(): ##molli
                    if flag_eng:
                        if not uci_remote_shell:
                            if remote_windows(): ## molli for Windows use specific shell type
                                logging.info('molli: Remote Windows Connection')
                                uci_remote_shell = UciShell(hostname=args.engine_remote_server, username=args.engine_remote_user, key_file=args.engine_remote_key, password=args.engine_remote_pass, windows=True)
                            else:
                                logging.info('molli: Remote Mac/UNIX Connection')
                                uci_remote_shell = UciShell(hostname=args.engine_remote_server, username=args.engine_remote_user, key_file=args.engine_remote_key, password=args.engine_remote_pass)
                    else:
                        time.sleep(1)
                        DisplayMsg.show(Message.ONLINE_FAILED())
                        time.sleep(1)
                        DisplayMsg.show(Message.REMOTE_FAIL())

                if engine.quit():
                    # Load the new one and send args.
                    if remote_engine_mode() and flag_eng: ##molli
                        engine = UciEngine(file=remote_file, uci_shell=uci_remote_shell)
                    else:
                        engine = UciEngine(file=engine_file, uci_shell=uci_local_shell)

                    try:
                        engine_name = engine.get_name()
                    except AttributeError:
                        # New engine failed to start, restart old engine
                        logging.error('new engine failed to start, reverting to %s', old_file)
                        engine_fallback = True
                        event.options = old_options
                        engine_file = old_file
                        help_str    = old_file.rsplit(os.sep, 1)[1]
                        remote_file = engine_remote_home + os.sep + help_str
        

                        if remote_engine_mode() and flag_eng(): ##molli
                            engine = UciEngine(file=remote_file, uci_shell=uci_remote_shell)
                        else:
                            engine = UciEngine(file=old_file, uci_shell=uci_local_shell)

                        try:
                            engine_name = engine.get_name()
                        except AttributeError:
                            # Help - old engine failed to restart. There is no engine
                            logging.error('no engines started')
                            DisplayMsg.show(Message.ENGINE_FAIL())
                            time.sleep(3)
                            sys.exit(-1)

                    # All done - rock'n'roll
                    if interaction_mode == Mode.BRAIN and not engine.has_ponder():
                        logging.debug('new engine doesnt support brain mode, reverting to %s', old_file)
                        engine_fallback = True
                        if engine.quit():
                            if remote_engine_mode() and flag_eng: ##molli
                                engine = UciEngine(file=old_file, uci_shell=uci_remote_shell)
                            else:
                                engine = UciEngine(file=old_file, uci_shell=uci_local_shell)
                            engine.startup(old_options)
                            engine.newgame(game.copy())
                            try:
                                engine_name = engine.get_name()
                            except AttributeError:
                                logging.error('no engines started')
                                DisplayMsg.show(Message.ENGINE_FAIL())
                                time.sleep(3)
                                sys.exit(-1)
                        else:
                            logging.error('engine shutdown failure')
                            DisplayMsg.show(Message.ENGINE_FAIL())

                    engine.startup(event.options)
           
                    if online_mode():
                        ##stop_search_and_clock()
                        stop_clock()
                        DisplayMsg.show(Message.ONLINE_LOGIN())
                        ## check if login successful (correct server & correct user)
                        login, own_color, own_user, opp_user, game_time, fischer_inc = read_online_user_info()
                        logging.debug('molli online login: %s', login)

                        if not 'ok' in login:
                            ## server connection failed: check settings!
                            DisplayMsg.show(Message.ONLINE_FAILED()) ##new
                            time.sleep(3)
                            engine_fallback = True
                            event.options = None
                            ##event.options = old_options
                            ##engine_file = old_file
                            old_file    = 'engines/armv7l/a-stockf'
                            help_str    = old_file.rsplit(os.sep, 1)[1]
                            remote_file = engine_remote_home + os.sep + help_str

                            if remote_engine_mode() and flag_eng: ##molli
                                engine = UciEngine(file=remote_file, uci_shell=uci_remote_shell)
                            else:
                                engine = UciEngine(file=old_file, uci_shell=uci_local_shell)
                            
                            try:
                                engine_name = engine.get_name()
                            except AttributeError:
                                # Help - old engine failed to restart. There is no engine
                                logging.error('no engines started')
                                DisplayMsg.show(Message.ENGINE_FAIL())
                                time.sleep(3)
                                sys.exit(-1)
                            engine.startup(event.options)
                        else:
                            time.sleep(2)
                            ##game.reset()
                    elif emulation_mode() or pgn_mode():
                        ## molli for emulation engine we have to reset to starting position
                        stop_search_and_clock()
                        game = chess.Board()
                        game.turn = chess.WHITE ##molli
                        play_mode = PlayMode.USER_WHITE #molli
                        engine.newgame(game.copy())
                        done_computer_fen = None
                        done_move = pb_move = chess.Move.null()
                        searchmoves.reset()
                        game_declared = False
                        legal_fens = compute_legal_fens(game.copy()) ## molli
                        last_legal_fens = [] ## molli
                        legal_fens_after_cmove = [] ## molli
                        is_out_of_time_already = False ## molli
                    else:
                        engine.newgame(game.copy())

                    engine_mode()

                    if engine_fallback:
                        msg = Message.ENGINE_FAIL()
                        ## molli: in case of engine fail, set correct old engine display settings
                        for index in range(0, len(dgtmenu.installed_engines)):
                            logging.debug('molli dgtmenu.installed_engines:%s', dgtmenu.installed_engines[index]['file'])
                            if dgtmenu.installed_engines[index]['file'] == old_file:
                                logging.debug('molli index:%s', str(index))
                                dgtmenu.set_engine_index(index)
                    else:
                        searchmoves.reset()
                        msg = Message.ENGINE_READY(eng=event.eng, engine_name=engine_name,
                                                   eng_text=event.eng_text, has_levels=engine.has_levels(),
                                                   has_960=engine.has_chess960(), has_ponder=engine.has_ponder(),
                                                   show_ok=event.show_ok)
                    # Schedule cleanup of old objects
                    gc.collect()

                    set_wait_state(msg, not engine_fallback)
                    if interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.TRAINING):   # engine isnt started/searching => stop the clock
                        stop_clock()
                    text = dgtmenu.enter_eng_name_menu()
                    engine_text = str(text.l)
                    dgtmenu.exit_menu()
                    if dgtmenu.get_enginename():
                        DisplayMsg.show(Message.ENGINE_NAME(engine_name=engine_text)) ## molli
                else:
                    logging.error('engine shutdown failure')
                    DisplayMsg.show(Message.ENGINE_FAIL())

                # here dont care if engine supports pondering, cause Mode.NORMAL from startup
                if not remote_engine_mode() and not online_mode() and not pgn_mode() and not engine_fallback: #wd
                    # dont write engine(_level) if remote/online engine or engine failure # wd
                    write_picochess_ini('engine', event.eng['file'])

                if pgn_mode():
                    if not flag_last_engine_pgn:
                        tc_init_last  = time_control.get_parameters()
                   
                    det_pgn_guess_tctrl()

                    flag_last_engine_pgn = True
                elif emulation_mode():
                    if not flag_last_engine_emu:
                        tc_init_last  = time_control.get_parameters()
                    flag_last_engine_emu = True
                else:
                    ## molli restore last saved timecontrol
                    if (flag_last_engine_pgn or flag_last_engine_emu) and not tc_init_last == None and not online_mode() and not emulation_mode() and not pgn_mode():
                        stop_clock()
                        text = dgttranslate.text('N00_oktime')
                        ##time_control.reset()
                        Observable.fire(Event.SET_TIME_CONTROL(tc_init=tc_init_last, time_text=text, show_ok=True))
                        stop_clock()
                        DisplayMsg.show(Message.EXIT_MENU())
                    flag_last_engine_pgn = False
                    flag_last_engine_emu = False
                    tc_init_last = None

                comment_file = get_comment_file() ## for picotutor game comments like Boris & Sargon
                picotutor.init_comments(comment_file)
                
                if pgn_mode() or emulation_mode():
                    ## molli: in these cases we can't continue from current position but
                    ##        have to start a new game
                    if emulation_mode():
                        set_emulation_tctrl()
                    ## prepare new game
                    if pgn_mode():
                        pgn_game_name, pgn_problem, pgn_fen, pgn_result, pgn_white, pgn_black = read_pgn_info()
                        if 'mate in' in pgn_problem or 'Mate in' in pgn_problem:
                            set_fen_from_pgn(pgn_fen)
                            play_mode = PlayMode.USER_WHITE if game.turn == chess.WHITE else PlayMode.USER_BLACK
                            text = play_mode.value  # type: str
                            msg = Message.PLAY_MODE(play_mode=play_mode, play_mode_text=dgttranslate.text(text))
                            DisplayMsg.show(msg)
                            time.sleep(1)
                    pos960 = 518
                    Observable.fire(Event.NEW_GAME(pos960=pos960))
        
                if online_mode():
                    ModeInfo.set_online_mode(mode=True)
                    logging.debug('online game fen: %s', game.fen())
                    if (not flag_last_engine_online) or (game.board_fen() == chess.STARTING_BOARD_FEN):
                        pos960 = 518
                        Observable.fire(Event.NEW_GAME(pos960=pos960))
                    flag_last_engine_online = True
                else:
                    flag_last_engine_online = False
                    ModeInfo.set_online_mode(mode=False)

                if pgn_mode():
                    ModeInfo.set_pgn_mode(mode=True)
                else:
                    ModeInfo.set_pgn_mode(mode=False)
                        
            elif isinstance(event, Event.SETUP_POSITION):
                logging.debug('setting up custom fen: %s', event.fen)
                uci960 = event.uci960
                
                if game.move_stack:
                    if not (game.is_game_over() or game_declared):
                        result = GameResult.ABORT
                        DisplayMsg.show(Message.GAME_ENDS(tc_init = time_control.get_parameters(), result=result, play_mode=play_mode, game=game.copy()))
                game = chess.Board(event.fen, uci960)
                # see new_game
                stop_search_and_clock()
                if engine.has_chess960():
                    engine.option('UCI_Chess960', uci960)
                    engine.send()

                engine.newgame(game.copy())
                done_computer_fen = None
                done_move = pb_move = chess.Move.null()
                legal_fens_after_cmove = [] # molli
                is_out_of_time_already = False #molli
                time_control.reset()
                searchmoves.reset()
                game_declared = False
                if picotutor_mode():
                    picotutor.reset() ##molli picotutor
                    picotutor.set_position(game.fen(), i_turn = game.turn)
                    if play_mode == PlayMode.USER_BLACK:
                        picotutor.set_user_color(chess.BLACK)
                    else:
                        picotutor.set_user_color(chess.WHITE)
                set_wait_state(Message.START_NEW_GAME(game=game.copy(), newgame=True))

            elif isinstance(event, Event.NEW_GAME):
                ##m molli LED Rev2 bug
                if dgtmenu.get_position_reverse_flipboard():
                    dgtboard.set_reverse(True)
                last_move_no = game.fullmove_number
                takeback_active = False
                flag_startup = False
                flag_pgn_game_over = False
                ModeInfo.set_game_ending(result='*') ## initialize game result for game saving status
                engine_name = engine.get_name() ##molli
                position_mode = False
                fen_error_occured = False
                newgame = game.move_stack or (game.chess960_pos() != event.pos960)
                
                if newgame:
                    logging.debug('starting a new game with code: %s', event.pos960)
                    uci960 = event.pos960 != 518

                    if not (game.is_game_over() or game_declared):
                       
                        if emulation_mode(): ## force abortion for mame ## molli mame enhance
                            if is_not_user_turn(game.turn):     # 01.10.2018 um die Fehlermeldung zu vermeiden getrennt
                                # clock must be stopped BEFORE the "book_move" event cause SetNRun resets the clock display
                                stop_clock()
                                best_move_posted = True
                                # @todo 8/8/R6P/1R6/7k/2B2K1p/8/8 and sliding Ra6 over a5 to a4 - handle this in correct way!!
                                game_declared = True
                                stop_fen_timer()
                                legal_fens_after_cmove = [] # molli
            
                        result = GameResult.ABORT
                        DisplayMsg.show(Message.GAME_ENDS(tc_init = time_control.get_parameters(), result=result, play_mode=play_mode, game=game.copy()))
                        time.sleep(0.3)
                    
                    game = chess.Board()
                    game.turn = chess.WHITE ##molli
                    play_mode = PlayMode.USER_WHITE #molli
                    if uci960:
                        game.set_chess960_pos(event.pos960)
                
                    stop_search_and_clock()
                
                    # see setup_position
                    if engine.has_chess960():
                        engine.option('UCI_Chess960', uci960)
                        engine.send()

                    if interaction_mode == Mode.TRAINING: 
                        engine.stop()

                    if online_mode():
                        DisplayMsg.show(Message.SEEKING()) ## molli
                        engine.stop()
                        seeking_flag = True
                        stop_fen_timer()
                        ModeInfo.set_online_mode(mode=True)
                    else:
                        ModeInfo.set_online_mode(mode=False)
                    
                    if emulation_mode():
                        ##engine.stop() ## molli mame enhance
                        DisplayMsg.show(Message.ENGINE_SETUP()) ## molli

                    engine.newgame(game.copy())
                    
                    done_computer_fen = None
                    done_move = pb_move = chess.Move.null()
                    time_control.reset()
                    best_move_posted = False
                    searchmoves.reset()
                    game_declared = False

                    if online_mode():
                        time.sleep(0.5)
                        login, own_color, own_user, opp_user, game_time, fischer_inc = read_online_user_info()
                        if 'no_user' in own_user and not login == 'ok':
                        ## user login failed check login settings!!!
                            DisplayMsg.show(Message.ONLINE_USER_FAILED())  ##new
                            time.sleep(3)
                        elif 'no_player' in opp_user:
                        ## no opponent found start new game or engine again!!!
                            DisplayMsg.show(Message.ONLINE_NO_OPPONENT()) ##new
                            time.sleep(3)
                        else:
                            DisplayMsg.show(Message.ONLINE_NAMES(own_user=own_user, opp_user=opp_user)) ## molli
                            time.sleep(3)
                        seeking_flag = False
                        best_move_displayed = None

                    legal_fens = compute_legal_fens(game.copy()) ## molli
                    last_legal_fens = [] ## molli
                    legal_fens_after_cmove = [] ## molli
                    is_out_of_time_already = False ## molli
                    if pgn_mode():
                        if max_guess > 0:
                            max_guess_white = max_guess
                            max_guess_black = 0
                        pgn_game_name, pgn_problem, pgn_fen, pgn_result, pgn_white, pgn_black = read_pgn_info()
                        if 'mate in' in pgn_problem or 'Mate in' in pgn_problem:
                            set_fen_from_pgn(pgn_fen)
                    set_wait_state(Message.START_NEW_GAME(game=game.copy(), newgame=newgame))
                    if not 'no_player' in opp_user and not 'no_user' in own_user:
                        switch_online() ##molli
                            
                else:
                    if online_mode():
                        logging.debug('starting a new game with code: %s', event.pos960)
                        uci960 = event.pos960 != 518
                        stop_clock()
                    
                        game.turn = chess.WHITE ##molli
                        play_mode = PlayMode.USER_WHITE #molli
                        if uci960:
                            game.set_chess960_pos(event.pos960)
                    
                        # see setup_position
                        stop_search_and_clock()
                        stop_fen_timer()
                        
                        if engine.has_chess960():
                            engine.option('UCI_Chess960', uci960)
                            engine.send()

                        time_control.reset()
                        searchmoves.reset()
                        
                        DisplayMsg.show(Message.SEEKING()) ## molli
                        engine.stop()
                        seeking_flag = True

                        engine.newgame(game.copy())

                        login, own_color, own_user, opp_user, game_time, fischer_inc = read_online_user_info()
                        if 'no_user' in own_user:
                        ## user login failed check login settings!!!
                            DisplayMsg.show(Message.ONLINE_USER_FAILED())  ##new
                            time.sleep(3)
                        elif 'no_player' in opp_user:
                        ## no opponent found start new game & search!!!
                            DisplayMsg.show(Message.ONLINE_NO_OPPONENT()) ##new
                            time.sleep(3)
                        else:
                            DisplayMsg.show(Message.ONLINE_NAMES(own_user=own_user, opp_user=opp_user))
                            time.sleep(1)
                        seeking_flag = False
                        best_move_displayed = None
                        done_computer_fen = None
                        done_move = pb_move = chess.Move.null()
                        legal_fens = compute_legal_fens(game.copy()) ##molli
                        last_legal_fens = []#molli
                        legal_fens_after_cmove = [] # molli
                        is_out_of_time_already = False #molli
                        game_declared = False
                        set_wait_state(Message.START_NEW_GAME(game=game.copy(), newgame=newgame))
                        if not 'no_player' in opp_user and not 'no_user' in own_user:
                            switch_online() ##molli
                    else:
                        logging.debug('no need to start a new game')
                        if pgn_mode():
                            pgn_game_name, pgn_problem, pgn_fen, pgn_result, pgn_white, pgn_black = read_pgn_info()
                            if 'mate in' in pgn_problem or 'Mate in' in pgn_problem:
                                set_fen_from_pgn(pgn_fen) ##molli
                                set_wait_state(Message.START_NEW_GAME(game=game.copy(), newgame=newgame))
                            else:
                                DisplayMsg.show(Message.START_NEW_GAME(game=game.copy(), newgame=newgame))
                        else:
                            DisplayMsg.show(Message.START_NEW_GAME(game=game.copy(), newgame=newgame))

                if picotutor_mode():
                    picotutor.reset() ## molli picotutor
                    if not flag_startup:
                        if play_mode == PlayMode.USER_BLACK:
                            picotutor.set_user_color(chess.BLACK)
                        else:
                            picotutor.set_user_color(chess.WHITE)

                if interaction_mode != Mode.REMOTE and not online_mode():
                    if dgtmenu.get_enginename():
                        time.sleep(0.7) ## give time for ABORT message
                        DisplayMsg.show(Message.ENGINE_NAME(engine_name=engine_text)) ## molli
                    if pgn_mode():
                        pgn_white = ''
                        pgn_black = ''
                        time.sleep(1)
                        pgn_game_name, pgn_problem, pgn_fen, pgn_result, pgn_white, pgn_black = read_pgn_info()
                        
                        if not pgn_white:
                            pgn_white = '????'
                        DisplayMsg.show(Message.SHOW_TEXT(text_string=pgn_white))
                        
                        DisplayMsg.show(Message.SHOW_TEXT(text_string='versus'))
                            
                        if not pgn_black:
                            pgn_black = '????'
                        DisplayMsg.show(Message.SHOW_TEXT(text_string=pgn_black))
                        
                        if pgn_result:
                            DisplayMsg.show(Message.SHOW_TEXT(text_string=pgn_result))
                        if 'mate in' in pgn_problem or 'Mate in' in pgn_problem:
                            DisplayMsg.show(Message.SHOW_TEXT(text_string=pgn_problem))
                        else:
                            DisplayMsg.show(Message.SHOW_TEXT(text_string=pgn_game_name))
                        
                        ##reset pgn guess counters
                        if last_move_no > 1:
                            no_guess_black = 1
                            no_guess_white = 1
                        else:
                            log_pgn()
                            if max_guess_white > 0:
                                if no_guess_white > max_guess_white:
                                    last_legal_fens = []
                                    get_next_pgn_move()  ##molli pgn
                        
            elif isinstance(event, Event.PAUSE_RESUME):
                if pgn_mode():
                    ##stop_clock()
                    engine.pause_pgn_audio()
                else:
                    if engine.is_thinking():
                        stop_clock()
                        engine.stop(show_best=True)
                    elif not done_computer_fen:
                        if time_control.internal_running():
                            stop_clock()
                        else:
                            start_clock()
                    else:
                        logging.debug('best move displayed, dont start/stop clock')

            elif isinstance(event, Event.ALTERNATIVE_MOVE):
                if done_computer_fen and not emulation_mode():
                    done_computer_fen = None
                    done_move = chess.Move.null()
                    if interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.TRAINING):   # @todo handle Mode.REMOTE too
                        if time_control.mode == TimeMode.FIXED:
                            time_control.reset()
                        # set computer to move - in case the user just changed the engine
                        play_mode = PlayMode.USER_WHITE if game.turn == chess.BLACK else PlayMode.USER_BLACK
                        if not check_game_state(game, play_mode):
                            if picotutor_mode():
                                picotutor.pop_last_move()
                            think(game, time_control, Message.ALTERNATIVE_MOVE(game=game.copy(), play_mode=play_mode), searchlist=True) ##molli
                    else:
                        logging.warning('wrong function call [alternative]! mode: %s', interaction_mode)

            elif isinstance(event, Event.SWITCH_SIDES):
                flag_startup = False
                DisplayMsg.show(Message.EXIT_MENU())
                
                if interaction_mode == Mode.PONDER:
                    ## molli: allow switching sides in flexble ponder mode
                    fen = game.board_fen()

                    if game.turn == chess.WHITE:
                        fen += ' b KQkq - 0 1'
                    else:
                        fen += ' w KQkq - 0 1'
                    # ask python-chess to correct the castling string
                    bit_board = chess.Board(fen)
                    bit_board.set_fen(bit_board.fen())
                    if bit_board.is_valid():
                        game = chess.Board(bit_board.fen())
                        stop_search_and_clock()
                        engine.newgame(game.copy())
                        done_computer_fen = None
                        done_move = pb_move = chess.Move.null()
                        time_control.reset() ## molli TC
                        searchmoves.reset()
                        game_declared = False
                        legal_fens = compute_legal_fens(game.copy())
                        legal_fens_after_cmove = []
                        last_legal_fens = []
                        ##assert engine.is_waiting(), 'engine not waiting! thinking status: %s' % engine.is_thinking()
                        engine.position(copy.deepcopy(game))
                        engine.ponder()
                        play_mode = PlayMode.USER_WHITE if game.turn == chess.WHITE else PlayMode.USER_BLACK
                        text = play_mode.value  # type: str
                        msg = Message.PLAY_MODE(play_mode=play_mode, play_mode_text=dgttranslate.text(text))
                        DisplayMsg.show(msg)
                    else:
                        logging.debug('illegal fen %s', fen)
                        DisplayMsg.show(Message.WRONG_FEN())
                        DisplayMsg.show(Message.EXIT_MENU())

                elif interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.TRAINING): 
                    if not engine.is_waiting():
                        stop_search_and_clock()
                    automatic_takeback = False
                    takeback_active = False
                    reset_auto = False
                    last_legal_fens = []
                    legal_fens_after_cmove = [] # molli
                    best_move_displayed = done_computer_fen
                    if best_move_displayed:
                        move = done_move
                        done_computer_fen = None
                        done_move = pb_move = chess.Move.null()
                    else:
                        move = chess.Move.null()  # not really needed

                    play_mode = PlayMode.USER_WHITE if play_mode == PlayMode.USER_BLACK else PlayMode.USER_BLACK
                    text = play_mode.value  # type: str
                    msg = Message.PLAY_MODE(play_mode=play_mode, play_mode_text=dgttranslate.text(text))

                    if time_control.mode == TimeMode.FIXED:
                        time_control.reset()

                    if picotutor_mode():
                        if play_mode == PlayMode.USER_BLACK:
                            picotutor.set_user_color(chess.BLACK)
                        else:
                            picotutor.set_user_color(chess.WHITE)
                        if best_move_posted:
                            best_move_posted = False
                            picotutor.pop_last_move()

                    legal_fens = []
                    game_end = check_game_state(game, play_mode)
                    if game_end:
                        DisplayMsg.show(msg)
                    else:
                        cond1 = game.turn == chess.WHITE and play_mode == PlayMode.USER_BLACK
                        cond2 = game.turn == chess.BLACK and play_mode == PlayMode.USER_WHITE
                        if cond1 or cond2:
                            if pgn_mode(): ## molli change pgn guessing game sides
                                if max_guess_black > 0:
                                    max_guess_white = max_guess_black
                                    max_guess_black = 0
                                elif max_guess_white > 0:
                                    max_guess_black = max_guess_white
                                    max_guess_white = 0
                                no_guess_black = 1
                                no_guess_white = 1
                            time_control.reset_start_time()
                            think(game, time_control, msg)
                        else:
                            if pgn_mode(): ## molli change pgn guessing game sides
                                if max_guess_black > 0:
                                    max_guess_white = max_guess_black
                                    max_guess_black = 0
                                elif max_guess_white > 0:
                                    max_guess_black = max_guess_white
                                    max_guess_white = 0
                                no_guess_black = 1
                                no_guess_white = 1

                            DisplayMsg.show(msg)
                            start_clock()
                            legal_fens = compute_legal_fens(game.copy())

                    if best_move_displayed:
                        DisplayMsg.show(Message.SWITCH_SIDES(game=game.copy(), move=move))

                elif interaction_mode == Mode.REMOTE:
                    if not engine.is_waiting():
                        stop_search_and_clock()

                    last_legal_fens = []
                    legal_fens_after_cmove = [] # molli
                    best_move_displayed = done_computer_fen
                    if best_move_displayed:
                        move = done_move
                        done_computer_fen = None
                        done_move = pb_move = chess.Move.null()
                    else:
                        move = chess.Move.null()  # not really needed

                    play_mode = PlayMode.USER_WHITE if play_mode == PlayMode.USER_BLACK else PlayMode.USER_BLACK
                    text = play_mode.value  # type: str
                    msg = Message.PLAY_MODE(play_mode=play_mode, play_mode_text=dgttranslate.text(text))

                    if time_control.mode == TimeMode.FIXED:
                        time_control.reset()

                    legal_fens = []
                    game_end = check_game_state(game, play_mode)
                    if game_end:
                        DisplayMsg.show(msg)
                    else:
                        cond1 = game.turn == chess.WHITE and play_mode == PlayMode.USER_BLACK
                        cond2 = game.turn == chess.BLACK and play_mode == PlayMode.USER_WHITE
                        if cond1 or cond2:
                            time_control.reset_start_time()
                            think(game, time_control, msg)
                        else:
                            DisplayMsg.show(msg)
                            start_clock()
                            legal_fens = compute_legal_fens(game.copy())

                    if best_move_displayed:
                        DisplayMsg.show(Message.SWITCH_SIDES(game=game.copy(), move=move))

            elif isinstance(event, Event.DRAWRESIGN):
                if not game_declared:  # in case user leaves kings in place while moving other pieces
                    stop_search_and_clock()
                    DisplayMsg.show(Message.GAME_ENDS(tc_init = time_control.get_parameters(), result=event.result, play_mode=play_mode, game=game.copy()))
                    game_declared = True
                    stop_fen_timer()
                    legal_fens_after_cmove = [] # molli

            elif isinstance(event, Event.REMOTE_MOVE):
                flag_startup = False
                if interaction_mode == Mode.REMOTE and is_not_user_turn(game.turn):
                    stop_search_and_clock()
                    DisplayMsg.show(Message.COMPUTER_MOVE(move=event.move, ponder=chess.Move.null(), game=game.copy(),
                                                          wait=False))
                    game_copy = game.copy()
                    game_copy.push(event.move)
                    done_computer_fen = game_copy.board_fen()
                    done_move = event.move
                    pb_move = chess.Move.null()
                    legal_fens_after_cmove = compute_legal_fens(game_copy) # molli
                else:
                    logging.warning('wrong function call [remote]! mode: %s turn: %s', interaction_mode, game.turn)

            elif isinstance(event, Event.BEST_MOVE):
                flag_startup = False ##molli
                take_back_locked = False
                best_move_posted = False
                takeback_active= False
                
                if interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.TRAINING): 
                    if is_not_user_turn(game.turn):     # 01.10.2018 um die Fehlermeldung zu vermeiden getrennt
                        # clock must be stopped BEFORE the "book_move" event cause SetNRun resets the clock display
                        stop_clock()
                        best_move_posted = True
                        # @todo 8/8/R6P/1R6/7k/2B2K1p/8/8 and sliding Ra6 over a5 to a4 - handle this in correct way!!
                        if game.is_game_over() and not online_mode():
                            logging.warning('illegal move on game_end - sliding? move: %s fen: %s', event.move, game.fen())
                        elif event.move == None:    ##online game aborted or pgn move wrong or end of pgn game
                            game_declared = True
                            stop_fen_timer()
                            legal_fens_after_cmove = [] # molli
                            game_msg = game.copy()
                            
                            if online_mode():
                                ##time.sleep(0.7) ## give some time for getting correct online result
                                winner = ''
                                result_str = ''
                                time.sleep(0.5)
                                result_str, winner = read_online_result()
                                logging.debug('molli result_str:%s', result_str)
                                logging.debug('molli winner:%s', winner)
                                gameresult_tmp = ''
                                gameresult_tmp2 = ''
                                
                                if 'Checkmate' in result_str or 'checkmate' in result_str or 'mate' in result_str:
                                    gameresult_tmp = GameResult.MATE
                                elif 'Game abort' in result_str or 'timeout' in result_str:
                                    if winner:
                                        if 'white' in winner:
                                            gameresult_tmp  = GameResult.ABORT
                                            gameresult_tmp2 = GameResult.WIN_WHITE
                                        else:
                                            gameresult_tmp  = GameResult.ABORT
                                            ameresult_tmp2 = GameResult.WIN_BLACK
                                    else:
                                        gameresult_tmp = GameResult.ABORT
                                elif result_str == 'Draw' or result_str == 'draw':
                                    gameresult_tmp = GameResult.DRAW
                                elif 'Out of time: White wins' in result_str:
                                    gameresult_tmp = GameResult.OUT_OF_TIME
                                    gameresult_tmp2 = GameResult.WIN_WHITE
                                elif 'Out of time: Black wins' in result_str:
                                    gameresult_tmp = GameResult.OUT_OF_TIME
                                    gameresult_tmp2 = GameResult.WIN_BLACK
                                elif 'Out of time' in result_str or 'outoftime' in result_str:
                                    if winner:
                                        if 'white' in winner:
                                            gameresult_tmp = GameResult.OUT_OF_TIME
                                            gameresult_tmp2 = GameResult.WIN_WHITE
                                        else:
                                            gameresult_tmp = GameResult.OUT_OF_TIME
                                            gameresult_tmp2 = GameResult.WIN_BLACK
                                    else:
                                        gameresult_tmp = GameResult.OUT_OF_TIME
                                elif 'White wins' in result_str:
                                    gameresult_tmp  = GameResult.ABORT
                                    gameresult_tmp2 = GameResult.WIN_WHITE
                                elif 'Black wins' in result_str:
                                    gameresult_tmp  = GameResult.ABORT
                                    gameresult_tmp2 = GameResult.WIN_BLACK
                                elif 'OPP. resigns' in result_str or 'resign' in result_str or 'abort' in result_str :
                                    gameresult_tmp  = GameResult.ABORT
                                    logging.debug('molli resign handling')
                                    if winner == '':
                                        logging.debug('molli winner not set')
                                        if play_mode == PlayMode.USER_BLACK:
                                            gameresult_tmp2 = GameResult.WIN_BLACK
                                        else:
                                            gameresult_tmp2 = GameResult.WIN_WHITE
                                    else:
                                        logging.debug('molli winner %s', winner)
                                        if 'white' in winner:
                                            gameresult_tmp2 = GameResult.WIN_WHITE
                                        else:
                                            gameresult_tmp2 = GameResult.WIN_BLACK
                                    
                                else:
                                    logging.debug('molli unknown result')
                                    gameresult_tmp = GameResult.ABORT
                                
                                logging.debug('molli result_tmp:%s', gameresult_tmp)
                                logging.debug('molli result_tmp2:%s', gameresult_tmp2)
                                
                                if gameresult_tmp2 != '' and not (game.is_game_over() and gameresult_tmp == GameResult.ABORT):
                                    if gameresult_tmp == GameResult.OUT_OF_TIME:
                                        DisplayMsg.show(Message.LOST_ON_TIME())
                                        time.sleep(2)
                                        DisplayMsg.show(Message.GAME_ENDS(tc_init = time_control.get_parameters(), result = gameresult_tmp2, play_mode=play_mode, game=game_msg))
                                    else:
                                        DisplayMsg.show(Message.GAME_ENDS(tc_init = time_control.get_parameters(), result = gameresult_tmp, play_mode=play_mode, game=game_msg))
                                        time.sleep(2)
                                        DisplayMsg.show(Message.GAME_ENDS(tc_init = time_control.get_parameters(), result = gameresult_tmp2, play_mode=play_mode, game=game_msg))
                                else:
                                    if gameresult_tmp  == GameResult.ABORT and gameresult_tmp2 != '':
                                        DisplayMsg.show(Message.GAME_ENDS(tc_init = time_control.get_parameters(), result = gameresult_tmp2, play_mode=play_mode, game=game_msg))
                                    else:
                                        DisplayMsg.show(Message.GAME_ENDS(tc_init = time_control.get_parameters(), result = gameresult_tmp, play_mode=play_mode, game=game_msg))
                            else:
                                
                                if pgn_mode():
                                    ## molli: check if last move of pgn game file
                                    stop_search_and_clock()
                                    log_pgn()
                                    if flag_pgn_game_over:
                                        logging.debug('molli pgn: PGN END')
                                        pgn_game_name, pgn_problem, pgn_fen, pgn_result, pgn_white, pgn_black = read_pgn_info()
                                        DisplayMsg.show(Message.PGN_GAME_END(result = pgn_result)) ## game end
                                    elif pgn_book_test: ## molli 
                                        l_game_copy = game.copy()
                                        l_game_copy.pop()
                                        l_found = searchmoves.check_book(bookreader, l_game_copy)
                                        
                                        if not l_found:
                                            DisplayMsg.show(Message.PGN_GAME_END(result = '*'))
                                        else:
                                            logging.debug('molli pgn: Wrong Move! Try Again!')
                                            ##increase pgn guess counters
                                            if max_guess_black > 0 and game.turn == chess.WHITE:
                                                no_guess_black = no_guess_black + 1
                                                if no_guess_black > max_guess_black:
                                                    DisplayMsg.show(Message.MOVE_WRONG()) # wrong move
                                                else:
                                                    DisplayMsg.show(Message.MOVE_RETRY()) # wrong move
                                            elif max_guess_white > 0 and game.turn == chess.BLACK:
                                                no_guess_white = no_guess_white + 1
                                                if no_guess_white > max_guess_white:
                                                    DisplayMsg.show(Message.MOVE_WRONG()) # wrong move
                                                else:
                                                    DisplayMsg.show(Message.MOVE_RETRY()) # wrong move
                                            else:
                                                ## user move wrong in pgn display mode only
                                                DisplayMsg.show(Message.MOVE_RETRY()) # wrong move
                                            takeback_active = True
                                            automatic_takeback = True
                                            set_wait_state(Message.TAKE_BACK(game=game.copy())) ## automatic takeback mode
                                    else:
                                        logging.debug('molli pgn: Wrong Move! Try Again!')

                                        if max_guess_black > 0 and game.turn == chess.WHITE:
                                            no_guess_black = no_guess_black + 1
                                            if no_guess_black > max_guess_black:
                                                DisplayMsg.show(Message.MOVE_WRONG()) # wrong move
                                            else:
                                                DisplayMsg.show(Message.MOVE_RETRY()) # wrong move
                                        elif max_guess_white > 0 and game.turn == chess.BLACK:
                                            no_guess_white = no_guess_white + 1
                                            if no_guess_white > max_guess_white:
                                                DisplayMsg.show(Message.MOVE_WRONG()) # wrong move
                                            else:
                                                DisplayMsg.show(Message.MOVE_RETRY()) # wrong move
                                        else:
                                            ## user move wrong in pgn display mode only
                                            DisplayMsg.show(Message.MOVE_RETRY()) # wrong move
                                        takeback_active = True
                                        automatic_takeback = True
                                        set_wait_state(Message.TAKE_BACK(game=game.copy())) ## automatic takeback mode
                                else:
                                    DisplayMsg.show(Message.GAME_ENDS(tc_init = time_control.get_parameters(), result = GameResult.ABORT, play_mode=play_mode, game=game.copy()))
                            
                            time.sleep(0.5)
                        else:
                            if event.inbook:
                                DisplayMsg.show(Message.BOOK_MOVE())
                            searchmoves.exclude(event.move)
                            
                            if online_mode() or emulation_mode():
                                start_time_cmove_done = time.time() ## time should alraedy run for the player
                            DisplayMsg.show(Message.EXIT_MENU())
                            DisplayMsg.show(Message.COMPUTER_MOVE(move=event.move, ponder=event.ponder, game=game.copy(), wait=event.inbook))
                            game_before = game.copy()
                            game_copy = game.copy()
                            game_copy.push(event.move)
                            
                            if picotutor_mode():
                                if pgn_mode(): ## molli new
                                    t_color = picotutor.get_user_color()
                                    if t_color == chess.BLACK:
                                        picotutor.set_user_color(chess.WHITE)
                                    else:
                                        picotutor.set_user_color(chess.BLACK)
                                        
                                valid = picotutor.push_move(event.move) ## molli picotutor
                                
                                if not valid:
                                    ## invalid move from tutor side!? Something went wrong
                                    eval_str = 'ER'
                                    ##msg = Message.PICOTUTOR_MSG(eval_str = eval_str)
                                    ##DisplayMsg.show(msg)
                                    picotutor.set_position(game_copy.fen(), i_turn = game_copy.turn)
                                    
                                    if play_mode == PlayMode.USER_BLACK:
                                        picotutor.set_user_color(chess.BLACK)
                                    else:
                                        picotutor.set_user_color(chess.WHITE)
                                else:
                                    if pgn_mode():
                                        l_mate = ''
                                        n_mate = 0
                                        
                            done_computer_fen = game_copy.board_fen()
                            done_move = event.move
                            
                            brain_book = interaction_mode == Mode.BRAIN and event.inbook
                            pb_move = event.ponder if event.ponder and not brain_book else chess.Move.null()
                            legal_fens_after_cmove = compute_legal_fens(game_copy) # molli
                
                            if pgn_mode():
                                ##molli pgn: reset pgn guess counters
                                if max_guess_black > 0 and not game.turn == chess.BLACK:
                                    no_guess_black = 1
                                elif max_guess_white > 0 and not game.turn == chess.WHITE:
                                    no_guess_white = 1
                    else:
                        logging.warning('wrong function call [best]! mode: %s turn: %s', interaction_mode, game.turn)
                else:
                    logging.warning('wrong function call [best]! mode: %s turn: %s', interaction_mode, game.turn)

            elif isinstance(event, Event.NEW_PV):
                if interaction_mode == Mode.BRAIN and engine.is_pondering():
                    logging.debug('in brain mode and pondering ignore pv %s', event.pv[:3])
                else:
                    # illegal moves can occur if a pv from the engine arrives at the same time as an user move
                    if game.is_legal(event.pv[0]):
                        DisplayMsg.show(Message.NEW_PV(pv=event.pv, mode=interaction_mode, game=game.copy()))
                    else:
                        logging.info('illegal move can not be displayed. move: %s fen: %s', event.pv[0], game.fen())
                        logging.info('engine status: t:%s p:%s', engine.is_thinking(), engine.is_pondering())

            elif isinstance(event, Event.NEW_SCORE):
                if interaction_mode == Mode.BRAIN and engine.is_pondering():
                    logging.debug('in brain mode and pondering, ignore score %s', event.score)
                else:
                    if event.score == 999 or event.score == -999:
                        flag_pgn_game_over = True ##molli pgn mode: signal that pgn is at end
                    else:
                        flag_pgn_game_over = False
                    
                    DisplayMsg.show(Message.NEW_SCORE(score=event.score, mate=event.mate, mode=interaction_mode,
                                                      turn=game.turn))

            elif isinstance(event, Event.NEW_DEPTH):
                if interaction_mode == Mode.BRAIN and engine.is_pondering():
                    logging.debug('in brain mode and pondering, ignore depth %s', event.depth)
                else:
                    if event.depth == 999:
                        flag_pgn_game_over = True
                    else:
                        flag_pgn_game_over = False
                    DisplayMsg.show(Message.NEW_DEPTH(depth=event.depth))

            elif isinstance(event, Event.START_SEARCH):
                DisplayMsg.show(Message.SEARCH_STARTED())

            elif isinstance(event, Event.STOP_SEARCH):
                DisplayMsg.show(Message.SEARCH_STOPPED())

            elif isinstance(event, Event.SET_INTERACTION_MODE):
                if event.mode not in (Mode.NORMAL, Mode.REMOTE, Mode.TRAINING) and done_computer_fen:  # @todo check why still needed
                    dgtmenu.set_mode(interaction_mode)  # undo the button4 stuff
                    logging.warning('mode cant be changed to a pondering mode as long as a move is displayed')
                    mode_text = dgttranslate.text('Y10_errormode')
                    msg = Message.INTERACTION_MODE(mode=interaction_mode, mode_text=mode_text, show_ok=False)
                    DisplayMsg.show(msg)
                else:
                    stop_search_and_clock()
                    interaction_mode = event.mode
                    engine_mode()
                    msg = Message.INTERACTION_MODE(mode=event.mode, mode_text=event.mode_text, show_ok=event.show_ok)
                    set_wait_state(msg)  # dont clear searchmoves here

            elif isinstance(event, Event.SET_OPENING_BOOK):
                write_picochess_ini('book', event.book['file'])
                logging.debug('changing opening book [%s]', event.book['file'])
                bookreader = chess.polyglot.open_reader(event.book['file'])
                DisplayMsg.show(Message.OPENING_BOOK(book_text=event.book_text, show_ok=event.show_ok))
                book_in_use = event.book['file']
                stop_fen_timer()

            elif isinstance(event, Event.SHOW_ENGINENAME):
                DisplayMsg.show(Message.SHOW_ENGINENAME(show_enginename=event.show_enginename))

            elif isinstance(event, Event.SAVE_GAME):
                if event.pgn_filename:
                    stop_clock()
                    DisplayMsg.show(Message.SAVE_GAME(tc_init=time_control.get_parameters(), play_mode=play_mode, game=game.copy(), pgn_filename=event.pgn_filename))

            elif isinstance(event, Event.READ_GAME):
                if event.pgn_filename:
                    DisplayMsg.show(Message.READ_GAME(pgn_filename=event.pgn_filename))
                    read_pgn_file(event.pgn_filename)
                                    
            elif isinstance(event, Event.CONTLAST):
                DisplayMsg.show(Message.CONTLAST(contlast=event.contlast))
                                
            elif isinstance(event, Event.ALTMOVES):
                DisplayMsg.show(Message.ALTMOVES(altmoves=event.altmoves))

            elif isinstance(event, Event.PICOWATCHER):
                if (dgtmenu.get_picowatcher() or dgtmenu.get_picocoach()):
                    pico_calc = True
                else:
                    pico_calc = False
                picotutor.set_status(dgtmenu.get_picowatcher(), dgtmenu.get_picocoach(), dgtmenu.get_picoexplorer(), dgtmenu.get_picocomment())
                if event.picowatcher:
                    flag_picotutor = True
                    picotutor.set_position(game.fen(), i_turn = game.turn)
                    if play_mode == PlayMode.USER_BLACK:
                        picotutor.set_user_color(chess.BLACK)
                    else:
                        picotutor.set_user_color(chess.WHITE)
                elif dgtmenu.get_picocoach():
                    flag_picotutor = True
                elif dgtmenu.get_picoexplorer():
                    flag_picotutor = True
                else:
                    flag_picotutor = False
                    if pico_calc:
                        picotutor.stop()
                DisplayMsg.show(Message.PICOWATCHER(picowatcher=event.picowatcher))

            elif isinstance(event, Event.PICOCOACH):
               
                if (dgtmenu.get_picowatcher() or dgtmenu.get_picocoach()):
                    pico_calc = True
                else:
                    pico_calc = False
        
                pico_calc = False
                picotutor.set_status(dgtmenu.get_picowatcher(), dgtmenu.get_picocoach(), dgtmenu.get_picoexplorer(), dgtmenu.get_picocomment())
                
                if event.picocoach:
                    flag_picotutor = True
                    picotutor.set_position(game.fen(), i_turn = game.turn)
                    if play_mode == PlayMode.USER_BLACK:
                        picotutor.set_user_color(chess.BLACK)
                    else:
                        picotutor.set_user_color(chess.WHITE)
                elif dgtmenu.get_picowatcher():
                    flag_picotutor = True
                elif dgtmenu.get_picoexplorer():
                    flag_picotutor = True
                else:
                    flag_picotutor = False
                    if pico_calc:
                        picotutor.stop()

                DisplayMsg.show(Message.PICOCOACH(picocoach=event.picocoach))

            elif isinstance(event, Event.PICOEXPLORER):
                if (dgtmenu.get_picowatcher() or dgtmenu.get_picocoach()):
                    pico_calc = True
                else:
                    pico_calc = False
                picotutor.set_status(dgtmenu.get_picowatcher(), dgtmenu.get_picocoach(), dgtmenu.get_picoexplorer(), dgtmenu.get_picocomment())
                if event.picoexplorer:
                    flag_picotutor = True
                else:
                    if dgtmenu.get_picowatcher() or dgtmenu.get_picocoach():
                        flag_picotutor = True
                    else:
                        flag_picotutor = False
                        if pico_calc:
                            picotutor.stop()
                DisplayMsg.show(Message.PICOEXPLORER(picoexplorer=event.picoexplorer))

            elif isinstance(event, Event.PICOCOMMENT):
                DisplayMsg.show(Message.PICOCOMMENT(picocomment=event.picocomment))

            elif isinstance(event, Event.SET_TIME_CONTROL):
                time_control.stop_internal(log=False)
                tc_init = event.tc_init
    
                time_control = TimeControl(**tc_init)
                
                ## molli not for pgn_mode!!!
                if not pgn_mode() and not online_mode():
                    if tc_init['moves_to_go'] > 0: ## molli tournament time control
                        if time_control.mode == TimeMode.BLITZ:
                            write_picochess_ini('time', '{:d} {:d} 0 {:d}'.format(tc_init['moves_to_go'], tc_init['blitz'], tc_init['blitz2']))
                        elif time_control.mode == TimeMode.FISCHER:
                            write_picochess_ini('time', '{:d} {:d} {:d} {:d}'.format(tc_init['moves_to_go'], tc_init['blitz'], tc_init['fischer'], tc_init['blitz2']))
                    elif time_control.mode == TimeMode.BLITZ:
                        write_picochess_ini('time', '{:d} 0'.format(tc_init['blitz']))
                    elif time_control.mode == TimeMode.FISCHER:
                        write_picochess_ini('time', '{:d} {:d}'.format(tc_init['blitz'], tc_init['fischer']))
                    elif time_control.mode == TimeMode.FIXED:
                        write_picochess_ini('time', '{:d}'.format(tc_init['fixed']))

                    if time_control.depth > 0:
                         write_picochess_ini('depth', '{:d}'.format(tc_init['depth']))
                    else:
                         write_picochess_ini('depth', '{:d}'.format(0))

                text = Message.TIME_CONTROL(time_text=event.time_text, show_ok=event.show_ok, tc_init=tc_init)
                DisplayMsg.show(text)
                stop_fen_timer()

            elif isinstance(event, Event.CLOCK_TIME):
                if dgtdispatcher.is_prio_device(event.dev, event.connect):  # transfer only the most prio clock's time
                    logging.debug('setting tc clock time - prio: %s w:%s b:%s', event.dev,
                                  hms_time(event.time_white), hms_time(event.time_black))
                                  
                    if time_control.mode != TimeMode.FIXED and (event.time_white == time_control.game_time and event.time_black == time_control.game_time):
                        pass
                    else:
                        moves_to_go = time_control.moves_to_go_orig - game.fullmove_number + 1
                        if moves_to_go < 0:
                            moves_to_go = 0
                        time_control.set_clock_times(white_time=event.time_white, black_time=event.time_black, moves_to_go=moves_to_go) ## molli new tournament time control

                    # find out, if we are in bullet time (<=60secs on users clock or lowest time if user side unknown)
                    time_u = event.time_white
                    time_c = event.time_black
                    if interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.TRAINING):   # @todo handle Mode.REMOTE too
                        if play_mode == PlayMode.USER_BLACK:
                            time_u, time_c = time_c, time_u
                    else:  # here, we use the lowest time
                        if time_c < time_u:
                            time_u, time_c = time_c, time_u
                    ## molli low_time = time_u <= 60 and not (time_control.mode == TimeMode.FIXED and time_control.move_time > 2)
                    low_time =  False ## molli allow the speech output even for less than 60 seconds
                    dgtboard.low_time = low_time
                    if interaction_mode == Mode.TRAINING or position_mode:
                        pass 
                    else: 
                        DisplayMsg.show(Message.CLOCK_TIME(time_white=event.time_white, time_black=event.time_black,
                                                           low_time=low_time))
                else:
                    logging.debug('ignore clock time - too low prio: %s', event.dev)
            elif isinstance(event, Event.OUT_OF_TIME):
                ## molli: allow further playing even when run out of time
                if not is_out_of_time_already and not online_mode(): ## molli in online mode the server decides
                    ##stop_search_and_clock()
                    stop_clock()
                    result = GameResult.OUT_OF_TIME
                    DisplayMsg.show(Message.GAME_ENDS(tc_init = time_control.get_parameters(), result=result, play_mode=play_mode, game=game.copy()))
                    is_out_of_time_already = True

            elif isinstance(event, Event.SHUTDOWN):
                stop_search() ## molli
                stop_clock()
                engine.quit() ## molli
                
                try:
                    if uci_remote_shell:
                        if uci_remote_shell.get():
                            try:
                               uci_remote_shell.get().__exit__(None, None, None)  # force to call __exit__ (close shell connection)
                            except:
                               pass
                except:
                    pass
                       
                result = GameResult.ABORT
                DisplayMsg.show(Message.GAME_ENDS(tc_init = time_control.get_parameters(), result=result, play_mode=play_mode, game=game.copy()))
                DisplayMsg.show(Message.SYSTEM_SHUTDOWN())
                time.sleep(5) ## molli allow more time for commentary chat
                shutdown(args.dgtpi, dev=event.dev)  # @todo make independant of remote eng

            elif isinstance(event, Event.REBOOT):
                stop_search() ## molli
                stop_clock()
                engine.quit() ## molli
                result = GameResult.ABORT
                DisplayMsg.show(Message.GAME_ENDS(tc_init = time_control.get_parameters(), result=result, play_mode=play_mode, game=game.copy()))
                DisplayMsg.show(Message.SYSTEM_REBOOT())
                time.sleep(5) ## molli allow more time for commentary chat
                reboot(args.dgtpi and uci_local_shell.get() is None, dev=event.dev)  # @todo make independant of remote eng

            elif isinstance(event, Event.EMAIL_LOG):
                email_logger = Emailer(email=args.email, mailgun_key=args.mailgun_key)
                email_logger.set_smtp(sserver=args.smtp_server, suser=args.smtp_user, spass=args.smtp_pass,
                                      sencryption=args.smtp_encryption, sfrom=args.smtp_from)
                body = 'You probably want to forward this file to a picochess developer ;-)'
                email_logger.send('Picochess LOG', body, '/opt/picochess/logs/{}'.format(args.log_file))

            elif isinstance(event, Event.SET_VOICE):
                DisplayMsg.show(Message.SET_VOICE(type=event.type, lang=event.lang, speaker=event.speaker,
                                                  speed=event.speed))

            elif isinstance(event, Event.KEYBOARD_BUTTON):
                DisplayMsg.show(Message.DGT_BUTTON(button=event.button, dev=event.dev))

            elif isinstance(event, Event.KEYBOARD_FEN):
                DisplayMsg.show(Message.DGT_FEN(fen=event.fen, raw=False))

            elif isinstance(event, Event.EXIT_MENU):
                DisplayMsg.show(Message.EXIT_MENU())

            elif isinstance(event, Event.UPDATE_PICO):
                DisplayMsg.show(Message.UPDATE_PICO())
                checkout_tag(event.tag)
                DisplayMsg.show(Message.EXIT_MENU())

            elif isinstance(event, Event.REMOTE_ROOM):
                DisplayMsg.show(Message.REMOTE_ROOM(inside=event.inside))

            else:  # Default
                logging.warning('event not handled : [%s]', event)

            evt_queue.task_done()


if __name__ == '__main__':
    main()
