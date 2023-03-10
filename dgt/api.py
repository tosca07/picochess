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


class BaseClass(object):

    """Used for creating event, message, dgt classes."""

    def __init__(self, classtype):
        self._type = classtype

    def __repr__(self):
        return self._type

    def __hash__(self):
        return hash(str(self.__class__) + ": " + str(self.__dict__))


def ClassFactory(name, argnames, BaseClass=BaseClass):
    """Class factory for generating."""
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            # here, the argnames variable is the one passed to the ClassFactory call
            if key not in argnames:
                raise TypeError("argument {} not valid for {}".format(key, self.__class__.__name__))
            setattr(self, key, value)
        BaseClass.__init__(self, name)

    newclass = type(name, (BaseClass,), {"__init__": __init__})
    return newclass


class EventApi():

    """The api for the events."""

    # User events
    FEN = 'EVT_FEN'  # User has moved one or more pieces, and we have a new fen position
    LEVEL = 'EVT_LEVEL'  # User sets engine level
    NEW_GAME = 'EVT_NEW_GAME'  # User starts a new game
    DRAWRESIGN = 'EVT_DRAWRESIGN'  # User declares a resignation or draw
    KEYBOARD_MOVE = 'EVT_KEYBOARD_MOVE'  # Keyboard sends a move (to be transfered to a fen)
    REMOTE_MOVE = 'EVT_REMOTE_MOVE'  # Remote player move
    PROMOTION = 'EVT_PROMOTION'  # Promotion piece selected
    SET_OPENING_BOOK = 'EVT_SET_OPENING_BOOK'  # User chooses an opening book
    NEW_ENGINE = 'EVT_NEW_ENGINE'  # Change engine
    SET_INTERACTION_MODE = 'EVT_SET_INTERACTION_MODE'  # Change interaction mode
    SETUP_POSITION = 'EVT_SETUP_POSITION'  # Setup custom position
    PAUSE_RESUME = 'EVT_PAUSE_RESUME'  # Stops search or halt/resume running clock
    SWITCH_SIDES = 'EVT_SWITCH_SIDES'  # Switch the side
    SET_TIME_CONTROL = 'EVT_SET_TIME_CONTROL'  # User sets time control
    SHUTDOWN = 'EVT_SHUTDOWN'  # User wants to shutdown the machine
    REBOOT = 'EVT_REBOOT'  # User wants to reboot the machine
    ALTERNATIVE_MOVE = 'EVT_ALTERNATIVE_MOVE'  # User wants engine to recalculate the position
    EMAIL_LOG = 'EVT_EMAIL_LOG'  # User want to send the log file by eMail
    SET_VOICE = 'EVT_SET_VOICE'  # User sets a new voice
    SHOW_ENGINENAME = 'EVT_SHOW_ENGINENAME'  # show enginename
    PICOWATCHER = 'EVT_PICOWATCHER'  # picowatcher on/off
    PICOCOACH = 'EVT_PICOCOACH'  # picocoach on/off
    PICOEXPLORER = 'EVT_PICOEXPLORER'  # picoexplorer on/off
    PICOCOMMENT = 'EVT_PICOCOMMENT'  # pico written game comments on/off/all
    RSPEED = 'EVT_RSPEED'
    TAKE_BACK = 'EVT_TAKE_BACK'
    READ_GAME = 'EVT_READ_GAME'
    SAVE_GAME = 'EVT_SAVE_GAME'
    CONTLAST = 'EVT_CONTLAST'
    ALTMOVES = 'EVT_ALTMOVES'

    # Keyboard events
    KEYBOARD_BUTTON = 'EVT_KEYBOARD_BUTTON'  # User pressed a button at the virtual clock
    KEYBOARD_FEN = 'EVT_KEYBOARD_FEN'  # Virtual board sends a fen
    # Engine events
    BEST_MOVE = 'EVT_BEST_MOVE'  # Engine has found a move
    NEW_PV = 'EVT_NEW_PV'  # Engine sends a new principal variation
    NEW_SCORE = 'EVT_NEW_SCORE'  # Engine sends a new score
    NEW_DEPTH = 'EVT_NEW_DEPTH'  # Engine sends a new depth
    START_SEARCH = 'EVT_START_SEARCH'  # Engine starts the search
    STOP_SEARCH = 'EVT_STOP_SEARCH'  # Engine stops the search
    # Timecontrol events
    OUT_OF_TIME = 'EVT_OUT_OF_TIME'  # Clock flag fallen
    CLOCK_TIME = 'EVT_CLOCK_TIME'  # Clock sends its time
    # Special events
    EXIT_MENU = 'EVT_EXIT_MENU'  # User exists the menu
    UPDATE_PICO = 'EVT_UPDATE'  # User wants to upgrade/downgrade picochess
    REMOTE_ROOM = 'EVT_REMOTE_ROOM'  # User enters/leaves the remote room


class MessageApi():

    """The api for message."""

    # Messages to display devices
    COMPUTER_MOVE = 'MSG_COMPUTER_MOVE'  # Show computer move
    BOOK_MOVE = 'MSG_BOOK_MOVE'  # Show book move
    NEW_PV = 'MSG_NEW_PV'  # Show the new Principal Variation
    REVIEW_MOVE_DONE = 'MSG_REVIEW_MOVE_DONE'  # Player is reviewing a game (analysis, kibitz or observe modes)
    ENGINE_READY = 'MSG_ENGINE_READY'
    ENGINE_STARTUP = 'MSG_ENGINE_STARTUP'  # first time a new engine is ready
    ENGINE_FAIL = 'MSG_ENGINE_FAIL'  # Engine startup fails
    REMOTE_FAIL = 'MSG_REMOTE_FAIL'  # Remote Engine startup fails molli
    LEVEL = 'MSG_LEVEL'  # User sets engine level
    TIME_CONTROL = 'MSG_TIME_CONTROL'  # New Timecontrol
    OPENING_BOOK = 'MSG_OPENING_BOOK'  # User chooses an opening book
    PROMOTION_DIALOG = 'MSG_PROMOTION_DIALOG'  # Request promotion dialog on web display
    PROMOTION_DONE = 'MSG_PROMOTION_DONE'  # User has selected piece for promotion

    DGT_BUTTON = 'MSG_DGT_BUTTON'  # Clock button pressed
    DGT_FEN = 'MSG_DGT_FEN'  # DGT Board sends a fen
    DGT_CLOCK_VERSION = 'MSG_DGT_CLOCK_VERSION'  # DGT Board sends the clock version
    DGT_CLOCK_TIME = 'MSG_DGT_CLOCK_TIME'  # DGT Clock time message
    DGT_SERIAL_NR = 'MSG_DGT_SERIAL_NR'  # DGT Clock serial_nr (used for watchdog only)
    DGT_JACK_CONNECTED_ERROR = 'MSG_DGT_JACK_CONNECTED_ERROR'  # User connected fully|partly the clock via jack
    DGT_NO_CLOCK_ERROR = 'MSG_DGT_NO_CLOCK_ERROR'  # User hasnt connected a clock
    DGT_NO_EBOARD_ERROR = 'MSG_DGT_NO_EBOARD_ERROR'  # User hasnt connected an E-Board
    DGT_EBOARD_VERSION = 'MSG_DGT_EBOARD_VERSION'  # Startup Message after a successful connection to an E-Board

    INTERACTION_MODE = 'MSG_INTERACTON_MODE'  # Interaction mode
    PLAY_MODE = 'MSG_PLAY_MODE'  # Play mode
    SET_PLAYMODE = 'MSG_SET_PLAYMODE'
    START_NEW_GAME = 'MSG_START_NEW_GAME'  # User starts a new game
    COMPUTER_MOVE_DONE = 'MSG_COMPUTER_MOVE_DONE'  # User has done the computer move on board
    SEARCH_STARTED = 'MSG_SEARCH_STARTED'  # Engine has started to search

    SEARCH_STOPPED = 'MSG_SEARCH_STOPPED'  # Engine has stopped the search
    TAKE_BACK = 'MSG_TACK_BACK'  # User takes back move(s)
    CLOCK_START = 'MSG_CLOCK_START'  # Say to run autonomous clock, contains time_control
    CLOCK_STOP = 'MSG_CLOCK_STOP'  # Stops the clock
    CLOCK_TIME = 'MSG_CLOCK_TIME'  # Send the prio clock time
    USER_MOVE_DONE = 'MSG_USER_MOVE_DONE'  # Player has done a move on board
    GAME_ENDS = 'MSG_GAME_ENDS'  # The current game has ended, contains a 'result' (GameResult) and list of 'moves'

    SYSTEM_INFO = 'MSG_SYSTEM_INFO'  # Information about picochess such as version etc
    STARTUP_INFO = 'MSG_STARTUP_INFO'  # Information about the startup options
    IP_INFO = 'MSG_IP_INFO'  # Information about the IP adr
    NEW_SCORE = 'MSG_NEW_SCORE'  # Shows a new score
    NEW_DEPTH = 'MSG_NEW_DEPTH'  # Shows a new depth
    ALTERNATIVE_MOVE = 'MSG_ALTERNATIVE_MOVE'  # User wants another move to be calculated
    SWITCH_SIDES = 'MSG_SWITCH_SIDES'  # Forget the engines move, and let it be user's turn
    SYSTEM_SHUTDOWN = 'MSG_SYSTEM_SHUTDOWN'  # Sends a Shutdown
    SYSTEM_REBOOT = 'MSG_SYSTEM_REBOOT'  # Sends a Reboot
    SET_VOICE = 'MSG_SET_VOICE'  # User chooses a new voice
    SHOW_ENGINENAME = 'MSG_SHOW_ENGINENAME'
    PICOWATCHER = 'MSG_PICOWATCHER'  # picowatcher on/off
    PICOCOACH = 'MSG_PICOCOACH'  # picocoach on/off
    PICOEXPLORER = 'MSG_PICOEXPLORER'  # picoexplorer on/off
    PICOCOMMENT = 'MSG_PICOCOMMENT'  # picoexplorer on/off
    RSPEED = 'MSG_RSPEED'
    READ_GAME = 'MSG_READ_GAME'  # read game
    SAVE_GAME = 'MSG_SAVE_GAME'  # save game
    CONTLAST = 'MSG_CONTLAST'   # continue last game
    ALTMOVES = 'MSG_ALTMOVES'   # direct play alternative pico moves

    EXIT_MENU = 'MSG_EXIT_MENU'  # User exits the menu
    WRONG_FEN = 'MSG_WRONG_FEN'  # User sends a wrong placement of pieces (timed)
    BATTERY = 'MSG_BATTERY'  # percent of BT battery
    UPDATE_PICO = 'MSG_UPDATE'  # User wants to update picochess
    SEEKING = 'MSG_SEEKING'  # molli: seek for online player
    PGN_GAME_END = 'MSG_PGN_GAME_END'
    ENGINE_SETUP = 'MSG_ENGINE_SETUP'
    MOVE_RETRY = 'MSG_MOVE_RETRY'
    MOVE_WRONG = 'MSG_MOVE_WRONG'
    RESTORE_GAME = 'MSG_RESTORE_GAME'
    ENGINE_NAME = 'MSG_ENGINE_NAME'
    SHOW_TEXT = 'MSG_SHOW_TEXT'
    ONLINE_NAMES = 'MSG_ONLINE_NAMES'
    ONLINE_LOGIN = 'MSG_ONLINE_LOGIN'
    ONLINE_USER_FAILED = 'MSG_ONLINE_USER_FAILED'
    ONLINE_NO_OPPONENT = 'MSG_ONLINE_NO_OPPONENT'
    ONLINE_FAILED = 'MSG_ONLINE_FAILED'
    LOST_ON_TIME = 'MSG_LOST_ON_TIME'
    SET_NOBOOK = 'MSG_SET_NOBOOK'
    PICOTUTOR_MSG = 'MSG_PICOTUTOR_MSG'
    POSITION_FAIL = 'MSG_POSITION_FAIL'
    TIMECONTROL_CHECK = 'MSG_TIMECONTROL_CHECK'
    REMOTE_ROOM = 'MSG_REMOTE_ROOM'  # User enters/leaves a remote room


class DgtApi():

    """The api for the dgt."""

    # Commands to the DgtHw/DgtPi/DgtVr
    DISPLAY_MOVE = 'DGT_DISPLAY_MOVE'
    DISPLAY_TEXT = 'DGT_DISPLAY_TEXT'
    DISPLAY_TIME = 'DGT_DISPLAY_TIME'
    LIGHT_CLEAR = 'DGT_LIGHT_CLEAR'
    LIGHT_SQUARES = 'DGT_LIGHT_SQUARES'
    LIGHT_SQUARE = 'DGT_LIGHT_SQUARE'
    CLOCK_SET = 'DGT_CLOCK_SET'
    CLOCK_START = 'DGT_CLOCK_START'
    CLOCK_STOP = 'DGT_CLOCK_STOP'
    CLOCK_VERSION = 'DGT_CLOCK_VERSION'
    SERIALNR = 'DGT_SERIALNR'
    PROMOTION_DONE = 'DGT_PROMOTION_DONE'


class Dgt():

    """Used to define tasks for the communication towards the dgt hardware."""

    DISPLAY_MOVE = ClassFactory(DgtApi.DISPLAY_MOVE, ['move', 'fen', 'uci960', 'side', 'lang', 'capital', 'long', 'beep', 'maxtime', 'devs', 'wait', 'ld', 'rd'])
    DISPLAY_TEXT = ClassFactory(DgtApi.DISPLAY_TEXT, ['web_text', 'large_text', 'medium_text', 'small_text', 'beep', 'maxtime', 'devs', 'wait', 'ld', 'rd'])
    DISPLAY_TIME = ClassFactory(DgtApi.DISPLAY_TIME, ['wait', 'force', 'devs'])
    LIGHT_CLEAR = ClassFactory(DgtApi.LIGHT_CLEAR, ['devs'])
    LIGHT_SQUARES = ClassFactory(DgtApi.LIGHT_SQUARES, ['uci_move', 'devs'])
    LIGHT_SQUARE = ClassFactory(DgtApi.LIGHT_SQUARE, ['square', 'devs'])
    CLOCK_SET = ClassFactory(DgtApi.CLOCK_SET, ['time_left', 'time_right', 'devs'])
    CLOCK_START = ClassFactory(DgtApi.CLOCK_START, ['side', 'devs', 'wait'])
    CLOCK_STOP = ClassFactory(DgtApi.CLOCK_STOP, ['devs', 'wait'])
    CLOCK_VERSION = ClassFactory(DgtApi.CLOCK_VERSION, ['main', 'sub', 'devs'])
    PROMOTION_DONE = ClassFactory(DgtApi.PROMOTION_DONE, ['uci_move', 'devs'])


class Message():

    """General class for transmitting messages between several parts of picochess."""

    # Messages to display devices
    COMPUTER_MOVE = ClassFactory(MessageApi.COMPUTER_MOVE, ['move', 'ponder', 'game', 'wait'])
    BOOK_MOVE = ClassFactory(MessageApi.BOOK_MOVE, [])
    NEW_PV = ClassFactory(MessageApi.NEW_PV, ['pv', 'mode', 'game'])
    REVIEW_MOVE_DONE = ClassFactory(MessageApi.REVIEW_MOVE_DONE, ['move', 'fen', 'turn', 'game'])
    ENGINE_READY = ClassFactory(MessageApi.ENGINE_READY, ['eng', 'eng_text', 'engine_name', 'has_levels', 'has_960', 'has_ponder', 'show_ok'])
    ENGINE_STARTUP = ClassFactory(MessageApi.ENGINE_STARTUP, ['installed_engines', 'file', 'level_index', 'has_960', 'has_ponder'])
    ENGINE_FAIL = ClassFactory(MessageApi.ENGINE_FAIL, [])
    REMOTE_FAIL = ClassFactory(MessageApi.REMOTE_FAIL, [])
    LEVEL = ClassFactory(MessageApi.LEVEL, ['level_text', 'level_name', 'do_speak'])
    TIME_CONTROL = ClassFactory(MessageApi.TIME_CONTROL, ['time_text', 'show_ok', 'tc_init'])
    OPENING_BOOK = ClassFactory(MessageApi.OPENING_BOOK, ['book_text', 'show_ok'])
    PROMOTION_DIALOG = ClassFactory(MessageApi.PROMOTION_DIALOG, ['move'])

    DGT_BUTTON = ClassFactory(MessageApi.DGT_BUTTON, ['button', 'dev'])
    DGT_FEN = ClassFactory(MessageApi.DGT_FEN, ['fen', 'raw'])
    DGT_CLOCK_VERSION = ClassFactory(MessageApi.DGT_CLOCK_VERSION, ['main', 'sub', 'dev', 'text'])
    DGT_CLOCK_TIME = ClassFactory(MessageApi.DGT_CLOCK_TIME, ['time_left', 'time_right', 'connect', 'dev'])
    DGT_SERIAL_NR = ClassFactory(MessageApi.DGT_SERIAL_NR, ['number'])
    DGT_JACK_CONNECTED_ERROR = ClassFactory(MessageApi.DGT_JACK_CONNECTED_ERROR, [])
    DGT_NO_CLOCK_ERROR = ClassFactory(MessageApi.DGT_NO_CLOCK_ERROR, ['text'])
    DGT_NO_EBOARD_ERROR = ClassFactory(MessageApi.DGT_NO_EBOARD_ERROR, ['text'])
    DGT_EBOARD_VERSION = ClassFactory(MessageApi.DGT_EBOARD_VERSION, ['text', 'channel'])

    INTERACTION_MODE = ClassFactory(MessageApi.INTERACTION_MODE, ['mode', 'mode_text', 'show_ok'])
    PLAY_MODE = ClassFactory(MessageApi.PLAY_MODE, ['play_mode', 'play_mode_text'])
    SET_PLAYMODE = ClassFactory(MessageApi.SET_PLAYMODE, ['play_mode'])
    START_NEW_GAME = ClassFactory(MessageApi.START_NEW_GAME, ['game', 'newgame'])
    COMPUTER_MOVE_DONE = ClassFactory(MessageApi.COMPUTER_MOVE_DONE, [])
    SEARCH_STARTED = ClassFactory(MessageApi.SEARCH_STARTED, [])
    SEARCH_STOPPED = ClassFactory(MessageApi.SEARCH_STOPPED, [])
    TAKE_BACK = ClassFactory(MessageApi.TAKE_BACK, ['game'])
    CLOCK_START = ClassFactory(MessageApi.CLOCK_START, ['turn', 'tc_init', 'devs'])
    CLOCK_STOP = ClassFactory(MessageApi.CLOCK_STOP, ['devs'])
    CLOCK_TIME = ClassFactory(MessageApi.CLOCK_TIME, ['time_white', 'time_black', 'low_time'])
    USER_MOVE_DONE = ClassFactory(MessageApi.USER_MOVE_DONE, ['move', 'fen', 'turn', 'game'])
    GAME_ENDS = ClassFactory(MessageApi.GAME_ENDS, ['tc_init', 'result', 'play_mode', 'game'])

    SYSTEM_INFO = ClassFactory(MessageApi.SYSTEM_INFO, ['info'])
    STARTUP_INFO = ClassFactory(MessageApi.STARTUP_INFO, ['info'])
    IP_INFO = ClassFactory(MessageApi.IP_INFO, ['info'])
    NEW_SCORE = ClassFactory(MessageApi.NEW_SCORE, ['score', 'mate', 'mode', 'turn'])
    NEW_DEPTH = ClassFactory(MessageApi.NEW_DEPTH, ['depth'])
    ALTERNATIVE_MOVE = ClassFactory(MessageApi.ALTERNATIVE_MOVE, ['game', 'play_mode'])
    SWITCH_SIDES = ClassFactory(MessageApi.SWITCH_SIDES, ['game', 'move'])
    SYSTEM_SHUTDOWN = ClassFactory(MessageApi.SYSTEM_SHUTDOWN, [])
    SYSTEM_REBOOT = ClassFactory(MessageApi.SYSTEM_REBOOT, [])
    SET_VOICE = ClassFactory(MessageApi.SET_VOICE, ['type', 'lang', 'speaker', 'speed'])
    SHOW_ENGINENAME = ClassFactory(MessageApi.SHOW_ENGINENAME, ['show_enginename'])
    PICOWATCHER = ClassFactory(MessageApi.PICOWATCHER, ['picowatcher'])
    PICOCOACH = ClassFactory(MessageApi.PICOCOACH, ['picocoach'])
    PICOEXPLORER = ClassFactory(MessageApi.PICOEXPLORER, ['picoexplorer'])
    PICOCOMMENT = ClassFactory(MessageApi.PICOCOMMENT, ['picocomment'])
    RSPEED = ClassFactory(MessageApi.RSPEED, ['rspeed'])
    READ_GAME = ClassFactory(MessageApi.READ_GAME, ['pgn_filename'])
    SAVE_GAME = ClassFactory(MessageApi.SAVE_GAME, ['tc_init', 'play_mode', 'game', 'pgn_filename'])
    CONTLAST = ClassFactory(MessageApi.CONTLAST, ['contlast'])
    ALTMOVES = ClassFactory(MessageApi.ALTMOVES, ['altmoves'])

    EXIT_MENU = ClassFactory(MessageApi.EXIT_MENU, [])
    WRONG_FEN = ClassFactory(MessageApi.WRONG_FEN, [])
    BATTERY = ClassFactory(MessageApi.BATTERY, ['percent'])
    UPDATE_PICO = ClassFactory(MessageApi.UPDATE_PICO, [])
    REMOTE_ROOM = ClassFactory(MessageApi.REMOTE_ROOM, ['inside'])
    SEEKING = ClassFactory(MessageApi.SEEKING, [])
    PGN_GAME_END = ClassFactory(MessageApi.PGN_GAME_END, ['result'])
    ENGINE_SETUP = ClassFactory(MessageApi.ENGINE_SETUP, [])
    MOVE_RETRY = ClassFactory(MessageApi.MOVE_RETRY, [])
    MOVE_WRONG = ClassFactory(MessageApi.MOVE_WRONG, [])
    RESTORE_GAME = ClassFactory(MessageApi.RESTORE_GAME, [])
    ENGINE_NAME = ClassFactory(MessageApi.ENGINE_NAME, ['engine_name'])
    SHOW_TEXT = ClassFactory(MessageApi.SHOW_TEXT, ['text_string'])
    ONLINE_NAMES = ClassFactory(MessageApi.ONLINE_NAMES, ['own_user', 'opp_user'])
    ONLINE_LOGIN = ClassFactory(MessageApi.ONLINE_LOGIN, [])
    ONLINE_NO_OPPONENT = ClassFactory(MessageApi.ONLINE_NO_OPPONENT, [])
    ONLINE_USER_FAILED = ClassFactory(MessageApi.ONLINE_USER_FAILED, [])
    ONLINE_FAILED = ClassFactory(MessageApi.ONLINE_FAILED, [])
    LOST_ON_TIME = ClassFactory(MessageApi.LOST_ON_TIME, [])
    SET_NOBOOK = ClassFactory(MessageApi.SET_NOBOOK, ['book_index'])
    PICOTUTOR_MSG = ClassFactory(MessageApi.PICOTUTOR_MSG, ['eval_str', 'game', 'score'])
    POSITION_FAIL = ClassFactory(MessageApi.POSITION_FAIL, ['fen_result'])
    TIMECONTROL_CHECK = ClassFactory(MessageApi.TIMECONTROL_CHECK, ['player', 'movestogo', 'time1', 'time2'])
    PROMOTION_DONE = ClassFactory(MessageApi.PROMOTION_DONE, ['move'])


class Event():

    """Event used to send towards picochess."""

    # User events
    FEN = ClassFactory(EventApi.FEN, ['fen'])
    LEVEL = ClassFactory(EventApi.LEVEL, ['options', 'level_text', 'level_name'])
    NEW_GAME = ClassFactory(EventApi.NEW_GAME, ['pos960'])
    DRAWRESIGN = ClassFactory(EventApi.DRAWRESIGN, ['result'])
    KEYBOARD_MOVE = ClassFactory(EventApi.KEYBOARD_MOVE, ['move'])
    REMOTE_MOVE = ClassFactory(EventApi.REMOTE_MOVE, ['move', 'fen'])
    PROMOTION = ClassFactory(EventApi.PROMOTION, ['move', 'fen'])
    SET_OPENING_BOOK = ClassFactory(EventApi.SET_OPENING_BOOK, ['book', 'book_text', 'show_ok'])
    NEW_ENGINE = ClassFactory(EventApi.NEW_ENGINE, ['eng', 'eng_text', 'options', 'show_ok'])
    SET_INTERACTION_MODE = ClassFactory(EventApi.SET_INTERACTION_MODE, ['mode', 'mode_text', 'show_ok'])
    SETUP_POSITION = ClassFactory(EventApi.SETUP_POSITION, ['fen', 'uci960'])
    PAUSE_RESUME = ClassFactory(EventApi.PAUSE_RESUME, [])
    SWITCH_SIDES = ClassFactory(EventApi.SWITCH_SIDES, [])
    SET_TIME_CONTROL = ClassFactory(EventApi.SET_TIME_CONTROL, ['tc_init', 'time_text', 'show_ok'])
    SHUTDOWN = ClassFactory(EventApi.SHUTDOWN, ['dev'])
    REBOOT = ClassFactory(EventApi.REBOOT, ['dev'])
    ALTERNATIVE_MOVE = ClassFactory(EventApi.ALTERNATIVE_MOVE, [])
    EMAIL_LOG = ClassFactory(EventApi.EMAIL_LOG, [])
    SET_VOICE = ClassFactory(EventApi.SET_VOICE, ['type', 'lang', 'speaker', 'speed'])
    SHOW_ENGINENAME = ClassFactory(EventApi.SHOW_ENGINENAME, ['show_enginename'])
    PICOWATCHER = ClassFactory(EventApi.PICOWATCHER, ['picowatcher'])
    PICOCOACH = ClassFactory(EventApi.PICOCOACH, ['picocoach'])
    PICOEXPLORER = ClassFactory(EventApi.PICOEXPLORER, ['picoexplorer'])
    PICOCOMMENT = ClassFactory(EventApi.PICOCOMMENT, ['picocomment'])
    TAKE_BACK = ClassFactory(EventApi.TAKE_BACK, ['take_back'])
    RSPEED = ClassFactory(EventApi.RSPEED, ['rspeed'])
    READ_GAME = ClassFactory(EventApi.READ_GAME, ['pgn_filename'])
    SAVE_GAME = ClassFactory(EventApi.SAVE_GAME, ['pgn_filename'])
    CONTLAST = ClassFactory(EventApi.CONTLAST, ['contlast'])
    ALTMOVES = ClassFactory(EventApi.ALTMOVES, ['altmoves'])
    # Keyboard events
    KEYBOARD_BUTTON = ClassFactory(EventApi.KEYBOARD_BUTTON, ['button', 'dev'])
    KEYBOARD_FEN = ClassFactory(EventApi.KEYBOARD_FEN, ['fen'])
    # Engine events
    BEST_MOVE = ClassFactory(EventApi.BEST_MOVE, ['move', 'ponder', 'inbook'])
    NEW_PV = ClassFactory(EventApi.NEW_PV, ['pv'])
    NEW_SCORE = ClassFactory(EventApi.NEW_SCORE, ['score', 'mate'])
    NEW_DEPTH = ClassFactory(EventApi.NEW_DEPTH, ['depth'])
    START_SEARCH = ClassFactory(EventApi.START_SEARCH, [])
    STOP_SEARCH = ClassFactory(EventApi.STOP_SEARCH, [])
    # Timecontrol events
    OUT_OF_TIME = ClassFactory(EventApi.OUT_OF_TIME, ['color'])
    CLOCK_TIME = ClassFactory(EventApi.CLOCK_TIME, ['time_white', 'time_black', 'connect', 'dev'])
    # special events
    EXIT_MENU = ClassFactory(EventApi.EXIT_MENU, [])
    UPDATE_PICO = ClassFactory(EventApi.UPDATE_PICO, ['tag'])
    REMOTE_ROOM = ClassFactory(EventApi.REMOTE_ROOM, ['inside'])
