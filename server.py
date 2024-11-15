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

import datetime
import threading
import logging
from collections import OrderedDict
from typing import Optional, Set

import chess  # type: ignore
import chess.pgn as pgn  # type: ignore

import tornado.web  # type: ignore
import tornado.wsgi  # type: ignore
from tornado.ioloop import IOLoop  # type: ignore
from tornado.websocket import WebSocketHandler  # type: ignore

from utilities import Observable, DisplayMsg, hms_time, AsyncRepeatingTimer
from web.picoweb import picoweb as pw

from dgt.api import Dgt, Event, Message
from dgt.util import PlayMode, Mode, ClockSide, GameResult
from dgt.iface import DgtIface
from eboard.eboard import EBoard
from pgn import ModeInfo
import asyncio
from constants import FLOAT_MSG_WAIT
import queue

# This needs to be reworked to be session based (probably by token)
# Otherwise multiple clients behind a NAT can all play as the 'player'
client_ips = []


logger = logging.getLogger(__name__)


def read_pgn_info():
    info = {}
    try:
        with open("/opt/picochess/engines/aarch64/extra/pgn_game_info.txt") as info_file:
            for line in info_file:
                name, value = line.partition("=")[::2]
                info[name.strip()] = value.strip()
        return info
    except (OSError, KeyError):
        logger.error("Could not read pgn_game_info file")
        info["PGN_GAME"] = "Game Error"
        info["PGN_PROBLEM"] = ""
        info["PGN_FEN"] = ""
        info["PGN_RESULT"] = "*"
        info["PGN_White"] = ""
        info["PGN_Black"] = ""
        info["PGN_White_ELO"] = ""
        info["PGN_Black_ELO"] = ""
        return info


class ServerRequestHandler(tornado.web.RequestHandler):
    def initialize(self, shared=None):
        self.shared = shared

    def data_received(self, chunk):
        pass


class ChannelHandler(ServerRequestHandler):
    def process_console_command(self, raw):
        cmd = raw.lower()

        try:
            # Here starts the simulation of a dgt-board!
            # Let the user send events like the board would do
            if cmd.startswith("fen:"):
                fen = raw.split(":")[1].strip()
                # dgt board only sends the basic fen => be sure it's same no matter what fen the user entered
                fen = fen.split(" ")[0]
                bit_board = chess.Board()  # valid the fen
                bit_board.set_board_fen(fen)
                Observable.fire(Event.KEYBOARD_FEN(fen=fen))
            # end simulation code
            elif cmd.startswith("go"):
                if "last_dgt_move_msg" in self.shared:
                    fen = self.shared["last_dgt_move_msg"]["fen"].split(" ")[0]
                    Observable.fire(Event.KEYBOARD_FEN(fen=fen))
            else:
                # Event.KEYBOARD_MOVE tranfers "move" to "fen" and then continues with "Message.DGT_FEN"
                move = chess.Move.from_uci(cmd)
                Observable.fire(Event.KEYBOARD_MOVE(move=move))
        except (ValueError, IndexError):
            logger.warning("Invalid user input [%s]", raw)

    def post(self):
        action = self.get_argument("action")

        if action == "broadcast":
            fen = self.get_argument("fen")
            pgn_str = self.get_argument("pgn")
            result = {
                "event": "Broadcast",
                "msg": "Position from Spectators!",
                "pgn": pgn_str,
                "fen": fen,
            }
            EventHandler.write_to_clients(result)
        elif action == "move":
            move = chess.Move.from_uci(
                self.get_argument("source")
                + self.get_argument("target")
                + self.get_argument("promotion")
            )
            Observable.fire(Event.REMOTE_MOVE(move=move, fen=self.get_argument("fen")))
        elif action == "promotion":
            move = chess.Move.from_uci(
                self.get_argument("source")
                + self.get_argument("target")
                + self.get_argument("promotion")
            )
            Observable.fire(Event.PROMOTION(move=move, fen=self.get_argument("fen")))
        elif action == "clockbutton":
            Observable.fire(Event.KEYBOARD_BUTTON(button=self.get_argument("button"), dev="web"))
        elif action == "room":
            inside = self.get_argument("room") == "inside"
            Observable.fire(Event.REMOTE_ROOM(inside=inside))
        elif action == "command":
            self.process_console_command(self.get_argument("command"))


class EventHandler(WebSocketHandler):
    """ Started by /event HTTP call - Clients are WebDisplay and WebVr classes """
    clients: Set[WebSocketHandler] = set()

    def initialize(self, shared=None):
        self.shared = shared

    def on_message(self, message):
        logger.debug("WebSocket message " + message)
        pass

    def data_received(self, chunk):
        pass

    def real_ip(self):
        x_real_ip = self.request.headers.get("X-Real-IP")
        real_ip = x_real_ip if x_real_ip else self.request.remote_ip
        return real_ip

    def open(self):
        EventHandler.clients.add(self)
        client_ips.append(self.real_ip())

    def on_close(self):
        EventHandler.clients.remove(self)
        client_ips.remove(self.real_ip())

    @classmethod
    def write_to_clients(cls, msg):
        """ This is the main event loop message producer for WebDisplay and WebVR """
        for client in cls.clients:
            client.write_message(msg)


class DGTHandler(ServerRequestHandler):
    def get(self, *args, **kwargs):
        action = self.get_argument("action")
        if action == "get_last_move":
            if "last_dgt_move_msg" in self.shared:
                self.write(self.shared["last_dgt_move_msg"])


class InfoHandler(ServerRequestHandler):
    def get(self, *args, **kwargs):
        action = self.get_argument("action")
        if action == "get_system_info":
            if "system_info" in self.shared:
                self.write(self.shared["system_info"])
        if action == "get_ip_info":
            if "ip_info" in self.shared:
                self.write(self.shared["ip_info"])
        if action == "get_headers":
            if "headers" in self.shared:
                self.write(dict(self.shared["headers"]))
        if action == "get_clock_text":
            if "clock_text" in self.shared:
                self.write(self.shared["clock_text"])


class ChessBoardHandler(ServerRequestHandler):
    def initialize(self, theme="dark"):
        self.theme = theme

    def get(self):
        self.render("web/picoweb/templates/clock.html", theme=self.theme)


class HelpHandler(ServerRequestHandler):
    def initialize(self, theme="dark"):
        self.theme = theme

    def get(self):
        self.render("web/picoweb/templates/help.html", theme=self.theme)


class WebServer(threading.Thread):
    def __init__(self, port: int, dgtboard: EBoard, theme: str):
        super(WebServer, self).__init__()
        self.shared: dict = {}
        self.port = port
        self.dgtboard = dgtboard
        self.theme = theme
        self.io_loop = None


    def make_app(self) -> tornado.web.Application:
        """ define web pages and their handlers """
        wsgi_app = tornado.wsgi.WSGIContainer(pw)
        return tornado.web.Application(
            [
                (r"/", ChessBoardHandler, dict(theme=self.theme)),
                (r"/event", EventHandler, dict(shared=self.shared)),
                (r"/dgt", DGTHandler, dict(shared=self.shared)),
                (r"/info", InfoHandler, dict(shared=self.shared)),
                (r"/help", HelpHandler, dict(theme=self.theme)),
                (r"/channel", ChannelHandler, dict(shared=self.shared)),
                (r".*", tornado.web.FallbackHandler, {"fallback": wsgi_app}),
            ]
        )


    async def start_server(self):
        """ start web server from thread start run"""
        app = self.make_app()
        app.listen(self.port)
        # moved starting WebDisplayt and WebVr here so that they are in same thread io_loop
        self.io_loop = tornado.ioloop.IOLoop.current()
        logger.info("web server starting - initializing message queues")
        WebDisplay(self.shared, self.io_loop).start()
        WebVr(self.shared, self.dgtboard, self.io_loop).start()
        logger.info("message queues ready - web server ready")
        await asyncio.Event().wait()


    def run(self):
        """Call by threading.Thread start() function."""
        asyncio.run(self.start_server())


class WebVr(DgtIface):
    """Handle the web (clock) communication."""

    def __init__(self, shared, dgtboard: EBoard, io_loop: tornado.ioloop.IOLoop):
        super(WebVr, self).__init__(dgtboard)
        self.shared = shared
        # virtual_timer is a web clock updater, loop is started in parent
        self.virtual_timer = AsyncRepeatingTimer(1, self._runclock, self.loop)
        self.io_loop = io_loop  # this is Tornados event loop for callbacks
        self.enable_dgtpi = dgtboard.is_pi
        sub = 2 if dgtboard.is_pi else 0
        DisplayMsg.show(Message.DGT_CLOCK_VERSION(main=2, sub=sub, dev="web", text=None))
        self.clock_show_time = True

        # keep the last time to find out errorous DGT_MSG_BWTIME messages (error: current time > last time)
        self.r_time = 3600 * 10  # max value cause 10h cant be reached by clock
        self.l_time = 3600 * 10  # max value cause 10h cant be reached by clock

    def _create_clock_text(self):
        if "clock_text" not in self.shared:
            self.shared["clock_text"] = {}

    async def _runclock(self):
        """ callback from AsyncRepeatingTimer once every second """
        # this is probably only to show a running web clock
        # the real clock measurement timecontrol is not here?
        if self.side_running == ClockSide.LEFT:
            time_left = self.l_time - 1
            if time_left <= 0:
                logger.info("negative/zero time left: %s", time_left)
                self.virtual_timer.stop()
                time_left = 0
            self.l_time = time_left
        if self.side_running == ClockSide.RIGHT:
            time_right = self.r_time - 1
            if time_right <= 0:
                logger.info("negative/zero time right: %s", time_right)
                self.virtual_timer.stop()
                time_right = 0
            self.r_time = time_right
        #logger.debug(
        #    "(web) clock new time received l:%s r:%s", hms_time(self.l_time), hms_time(self.r_time)
        #)
        DisplayMsg.show(
            Message.DGT_CLOCK_TIME(
                time_left=self.l_time, time_right=self.r_time, connect=True, dev="web"
            )
        )
        self._display_time(self.l_time, self.r_time)

    def _display_time(self, time_left: int, time_right: int):
        if time_left >= 3600 * 10 or time_right >= 3600 * 10:
            logger.debug("time values not set - abort function")
        elif self.clock_show_time:
            l_hms = hms_time(time_left)
            r_hms = hms_time(time_right)
            if ModeInfo.get_clock_side() == "left":
                text_l = "{}:{:02d}.{:02d}".format(l_hms[0], l_hms[1], l_hms[2])
                text_r = "{}:{:02d}.{:02d}".format(r_hms[0], r_hms[1], r_hms[2])
                icon_d = (
                    "fa-caret-right" if self.side_running == ClockSide.RIGHT else "fa-caret-left"
                )
            else:
                text_r = "{}:{:02d}.{:02d}".format(l_hms[0], l_hms[1], l_hms[2])
                text_l = "{}:{:02d}.{:02d}".format(r_hms[0], r_hms[1], r_hms[2])
                icon_d = (
                    "fa-caret-right" if self.side_running == ClockSide.LEFT else "fa-caret-left"
                )
            if self.side_running == ClockSide.NONE:
                icon_d = "fa-sort"
            text = text_l + '&nbsp;<i class="fa ' + icon_d + '"></i>&nbsp;' + text_r
            self._create_clock_text()
            self.shared["clock_text"] = text
            result = {"event": "Clock", "msg": text}
            EventHandler.write_to_clients(result)

    def display_move_on_clock(self, message):
        """Display a move on the web clock."""
        is_new_rev2 = self.dgtboard.is_revelation and self.dgtboard.enable_revelation_pi
        if self.enable_dgt3000 or is_new_rev2 or self.enable_dgtpi:
            bit_board, text = self.get_san(message, not self.enable_dgtpi)
            points = "..." if message.side == ClockSide.RIGHT else "."
            if self.enable_dgtpi:
                text = "{:3d}{:s}{:s}".format(bit_board.fullmove_number, points, text)
            else:
                text = "{:2d}{:s}{:s}".format(bit_board.fullmove_number % 100, points, text)
        else:
            text = message.move.uci()
            if message.side == ClockSide.RIGHT:
                text = text[:2].rjust(3) + text[2:].rjust(3)
            else:
                text = text[:2].ljust(3) + text[2:].ljust(3)
        if self.get_name() not in message.devs:
            logger.debug("ignored %s - devs: %s", text, message.devs)
            return True
        self.clock_show_time = False
        self._create_clock_text()
        logger.debug("[%s]", text)
        self.shared["clock_text"] = text
        result = {"event": "Clock", "msg": text}
        EventHandler.write_to_clients(result)
        return True

    def display_text_on_clock(self, message: Dgt.DISPLAY_TEXT):
        """Display a text on the web clock."""
        if message.web_text != "":
            text = message.web_text
        else:
            text = message.large_text
        if self.get_name() not in message.devs:
            logger.debug("ignored %s - devs: %s", text, message.devs)
            return True
        self.clock_show_time = False
        self._create_clock_text()
        logger.debug("[%s]", text)
        self.shared["clock_text"] = text
        result = {"event": "Clock", "msg": text}
        EventHandler.write_to_clients(result)
        return True

    def display_time_on_clock(self, message):
        """Display the time on the web clock."""
        if self.get_name() not in message.devs:
            logger.debug("ignored endText - devs: %s", message.devs)
            return True
        if self.side_running != ClockSide.NONE or message.force:
            self.clock_show_time = True
            self._display_time(self.l_time, self.r_time)
        else:
            logger.debug("(web) clock isnt running - no need for endText")
        return True

    def stop_clock(self, devs: set):
        """Stop the time on the web clock."""
        if self.get_name() not in devs:
            logger.debug("ignored stopClock - devs: %s", devs)
            return True
        if self.virtual_timer.is_running():
            self.virtual_timer.stop()
        return self._resume_clock(ClockSide.NONE)

    def _resume_clock(self, side: ClockSide):
        self.side_running = side
        return True

    def start_clock(self, side: ClockSide, devs: set):
        """Start the time on the web clock."""
        if self.get_name() not in devs:
            logger.debug("ignored startClock - devs: %s", devs)
            return True
        if self.virtual_timer.is_running():
            self.virtual_timer.stop()
        if side != ClockSide.NONE:
            self.virtual_timer.start()
        self._resume_clock(side)
        self.clock_show_time = True
        self._display_time(self.l_time, self.r_time)
        return True

    def set_clock(self, time_left: int, time_right: int, devs: set):
        """Start the time on the web clock."""
        if self.get_name() not in devs:
            logger.debug("ignored setClock - devs: %s", devs)
            return True
        self.l_time = time_left
        self.r_time = time_right
        return True

    def light_squares_on_revelation(self, uci_move):
        """Light the rev2 squares."""
        result = {"event": "Light", "move": uci_move}
        EventHandler.write_to_clients(result)
        return True

    def light_square_on_revelation(self, square):
        """Light the rev2 square."""
        uci_move = square + square
        result = {"event": "Light", "move": uci_move}
        EventHandler.write_to_clients(result)
        return True

    def clear_light_on_revelation(self):
        """Clear all leds from rev2."""
        result = {"event": "Clear"}
        EventHandler.write_to_clients(result)
        return True

    def promotion_done(self, move):
        pass

    def get_name(self):
        """Return name."""
        return "web"

    def _create_task(self, msg):
        # put callback to be executed by Tornado main event loop
        self.io_loop.add_callback(callback=lambda: self._process_message(msg))


class WebDisplay(DisplayMsg, threading.Thread):
    level_text_sav = ""
    level_name_sav = ""
    engine_elo_sav = ""
    result_sav = ""
    engine_name = "Picochess"

    def __init__(self, shared: dict, io_loop: tornado.ioloop.IOLoop):
        super(WebDisplay, self).__init__()
        self.shared = shared
        self.io_loop = io_loop  # Tornado webserver loop for callbacks
        self.loop = asyncio.new_event_loop()  # thread needs loop
        self._task = None  # task for message consumer
        self.starttime = datetime.datetime.now().strftime("%H:%M:%S")

    def _create_game_info(self):
        if "game_info" not in self.shared:
            self.shared["game_info"] = {}

    def _create_system_info(self):
        if "system_info" not in self.shared:
            self.shared["system_info"] = {}

    def _create_headers(self):
        if "headers" not in self.shared:
            self.shared["headers"] = OrderedDict()

    def _build_game_header(self, pgn_game: chess.pgn.Game):
        if WebDisplay.result_sav:
            pgn_game.headers["Result"] = WebDisplay.result_sav
        pgn_game.headers["Event"] = "PicoChess game"
        pgn_game.headers["Site"] = "picochess.org"
        pgn_game.headers["Date"] = datetime.datetime.today().strftime("%Y.%m.%d")
        pgn_game.headers["Round"] = "?"
        pgn_game.headers["White"] = "?"
        pgn_game.headers["Black"] = "?"

        user_name = "User"

        user_elo = "-"
        comp_elo = 2500
        rspeed = 1
        retro_speed = 100
        retro_speed_str = ""

        if "system_info" in self.shared:
            if "user_name" in self.shared["system_info"]:
                user_name = self.shared["system_info"]["user_name"]
            if "engine_name" in self.shared["system_info"]:
                WebDisplay.engine_name = self.shared["system_info"]["engine_name"]
            if "rspeed" in self.shared["system_info"]:
                rspeed = self.shared["system_info"]["rspeed"]
                retro_speed = int(100 * round(float(rspeed), 2))
                if ModeInfo.get_emulation_mode():
                    retro_speed_str = " (" + str(retro_speed) + "%" + ")"
                    if retro_speed < 20:
                        retro_speed_str = " (full speed)"
                else:
                    retro_speed_str = ""
            if "user_elo" in self.shared["system_info"]:
                user_elo = self.shared["system_info"]["user_elo"]
            if "engine_elo" in self.shared["system_info"]:
                comp_elo = self.shared["system_info"]["engine_elo"]

        if "game_info" in self.shared:
            if "level_text" in self.shared["game_info"]:
                text: Dgt.DISPLAY_TEXT = self.shared["game_info"]["level_text"]
                engine_level = " ({0})".format(text.large_text)
                if text.large_text == "" or text.large_text == " ":
                    engine_level = ""
            else:
                engine_level = ""
            if "level_name" in self.shared["game_info"]:
                level_name = self.shared["game_info"]["level_name"]
                if level_name.startswith("Elo@"):
                    comp_elo = int(level_name[4:])
                    engine_level = ""
            if "play_mode" in self.shared["game_info"]:
                if self.shared["game_info"]["play_mode"] == PlayMode.USER_WHITE:
                    pgn_game.headers["White"] = user_name
                    pgn_game.headers["Black"] = (
                        WebDisplay.engine_name + engine_level + retro_speed_str
                    )
                    pgn_game.headers["WhiteElo"] = str(user_elo)
                    pgn_game.headers["BlackElo"] = str(comp_elo)
                else:
                    pgn_game.headers["White"] = (
                        WebDisplay.engine_name + engine_level + retro_speed_str
                    )
                    pgn_game.headers["Black"] = user_name
                    pgn_game.headers["WhiteElo"] = str(comp_elo)
                    pgn_game.headers["BlackElo"] = str(user_elo)
            if "PGN Replay" in WebDisplay.engine_name:
                info = {}
                info = read_pgn_info()
                pgn_game.headers["Event"] = WebDisplay.engine_name + engine_level
                pgn_game.headers["Date"] = datetime.datetime.today().strftime("%Y.%m.%d")
                pgn_game.headers["Site"] = "picochess.org"
                pgn_game.headers["Round"] = ""
                pgn_game.headers["White"] = info["PGN_White"]
                pgn_game.headers["Black"] = info["PGN_Black"]
                if "PGN_White_ELO" in info and "PGN_Black_ELO" in info:
                    pgn_game.headers["WhiteElo"] = str(info["PGN_White_ELO"])
                    pgn_game.headers["BlackElo"] = str(info["PGN_Black_ELO"])
                else:
                    pgn_game.headers["WhiteElo"] = "?"
                    pgn_game.headers["BlackElo"] = "?"

        if "ip_info" in self.shared:
            if "location" in self.shared["ip_info"]:
                pgn_game.headers["Site"] = self.shared["ip_info"]["location"]

        pgn_game.headers["Time"] = self.starttime

    def task(self, message):
        """ Message task consumer for WebDisplay messages """
        def _oldstyle_fen(game: chess.Board):
            builder = []
            builder.append(game.board_fen())
            builder.append("w" if game.turn == chess.WHITE else "b")
            builder.append(game.castling_xfen())
            builder.append(chess.SQUARE_NAMES[game.ep_square] if game.ep_square else "-")
            builder.append(str(game.halfmove_clock))
            builder.append(str(game.fullmove_number))
            return " ".join(builder)

        def _build_headers():
            self._create_headers()
            pgn_game = pgn.Game()
            self._build_game_header(pgn_game)
            self.shared["headers"].update(pgn_game.headers)

        def _send_headers():
            EventHandler.write_to_clients(
                {"event": "Header", "headers": dict(self.shared["headers"])}
            )

        def _send_title():
            if "ip_info" in self.shared:
                EventHandler.write_to_clients(
                    {"event": "Title", "ip_info": self.shared["ip_info"]}
                )

        def _transfer(game: chess.Board):
            pgn_game = pgn.Game().from_board(game)
            self._build_game_header(pgn_game)
            self.shared["headers"] = pgn_game.headers
            return pgn_game.accept(
                pgn.StringExporter(headers=True, comments=False, variations=False)
            )

        def peek_uci(game: chess.Board):
            """Return last move in uci format."""
            try:
                return game.peek().uci()
            except IndexError:
                return chess.Move.null().uci()

        if False:  # switch-case
            pass
        elif isinstance(message, Message.START_NEW_GAME):
            WebDisplay.result_sav = ""
            self.starttime = datetime.datetime.now().strftime("%H:%M:%S")
            pgn_str = _transfer(message.game)
            fen = message.game.fen()
            result = {
                "pgn": pgn_str,
                "fen": fen,
                "event": "Game",
                "move": "0000",
                "play": "newgame",
            }
            self.shared["last_dgt_move_msg"] = result
            EventHandler.write_to_clients(result)
            _build_headers()
            _send_headers()
            _send_title()

        elif isinstance(message, Message.IP_INFO):
            self.shared["ip_info"] = message.info
            _build_headers()
            _send_headers()
            _send_title()

        elif isinstance(message, Message.SYSTEM_INFO):
            self._create_system_info()
            self.shared["system_info"].update(message.info)
            if "engine_name" in self.shared["system_info"]:
                WebDisplay.engine_name = self.shared["system_info"]["engine_name"]
                self.shared["system_info"]["old_engine"] = self.shared["system_info"][
                    "engine_name"
                ]
            if "rspeed" in self.shared["system_info"]:
                self.shared["system_info"]["rspeed_orig"] = self.shared["system_info"]["rspeed"]
            if "user_name" in self.shared["system_info"]:
                self.shared["system_info"]["user_name_orig"] = self.shared["system_info"][
                    "user_name"
                ]
            _build_headers()
            _send_headers()

        elif isinstance(message, Message.ENGINE_STARTUP):
            for index in range(0, len(message.installed_engines)):
                eng = message.installed_engines[index]
                if eng["file"] == message.file:
                    self.shared["system_info"]["engine_elo"] = eng["elo"]
                    break
            _build_headers()
            _send_headers()

        elif isinstance(message, Message.ENGINE_READY):
            self._create_system_info()
            WebDisplay.engine_name = message.engine_name
            self.shared["system_info"]["old_engine"] = self.shared["system_info"][
                "engine_name"
            ] = message.engine_name
            self.shared["system_info"]["engine_elo"] = message.eng["elo"]
            if not message.has_levels:
                if "level_text" in self.shared["game_info"]:
                    del self.shared["game_info"]["level_text"]
                if "level_name" in self.shared["game_info"]:
                    del self.shared["game_info"]["level_name"]
            _build_headers()
            _send_headers()

        elif isinstance(message, Message.STARTUP_INFO):
            self.shared["game_info"] = message.info.copy()
            # change book_index to book_text
            books = message.info["books"]
            book_index = message.info["book_index"]
            self.shared["game_info"]["book_text"] = books[book_index]["text"]
            del self.shared["game_info"]["book_index"]

            if message.info["level_text"] is None:
                del self.shared["game_info"]["level_text"]
            if message.info["level_name"] is None:
                del self.shared["game_info"]["level_name"]

        elif isinstance(message, Message.OPENING_BOOK):
            self._create_game_info()
            self.shared["game_info"]["book_text"] = message.book_text

        elif isinstance(message, Message.INTERACTION_MODE):
            self._create_game_info()
            self.shared["game_info"]["interaction_mode"] = message.mode
            if self.shared["game_info"]["interaction_mode"] == Mode.REMOTE:
                self.shared["system_info"]["engine_name"] = "Remote Player"
                if self.shared["system_info"]["engine_elo"] != "":
                    WebDisplay.engine_elo_sav = self.shared["system_info"]["engine_elo"]
                self.shared["system_info"]["engine_elo"] = "?"
                if self.shared["game_info"]["level_text"] != "":
                    WebDisplay.level_text_sav = self.shared["game_info"]["level_text"]
                if self.shared["game_info"]["level_name"] != "":
                    WebDisplay.level_name_sav = self.shared["game_info"]["level_name"]
                del self.shared["game_info"]["level_text"]
                del self.shared["game_info"]["level_name"]

            elif self.shared["game_info"]["interaction_mode"] == Mode.OBSERVE:
                self.shared["system_info"]["engine_name"] = "Player B"
                self.shared["system_info"]["user_name"] = "Player A"
                if self.shared["system_info"]["engine_elo"] != "":
                    WebDisplay.engine_elo_sav = self.shared["system_info"]["engine_elo"]
                self.shared["system_info"]["engine_elo"] = "?"
                if self.shared["game_info"]["level_text"] != "":
                    WebDisplay.level_text_sav = self.shared["game_info"]["level_text"]
                if self.shared["game_info"]["level_name"] != "":
                    WebDisplay.level_name_sav = self.shared["game_info"]["level_name"]
                del self.shared["game_info"]["level_text"]
                del self.shared["game_info"]["level_name"]
            else:
                self.shared["system_info"]["engine_name"] = self.shared["system_info"][
                    "old_engine"
                ]
                self.shared["system_info"]["user_name"] = self.shared["system_info"][
                    "user_name_orig"
                ]
                if WebDisplay.engine_elo_sav != "":
                    self.shared["system_info"]["engine_elo"] = WebDisplay.engine_elo_sav
                if WebDisplay.level_text_sav != "":
                    self.shared["game_info"]["level_text"] = WebDisplay.level_text_sav
                if WebDisplay.level_name_sav != "":
                    self.shared["game_info"]["level_name"] = WebDisplay.level_name_sav

            _build_headers()
            _send_headers()

        elif isinstance(message, Message.PLAY_MODE):
            if "PGN Replay" not in WebDisplay.engine_name:
                self._create_game_info()
                self.shared["game_info"]["play_mode"] = message.play_mode
                _build_headers()
                _send_headers()

        elif isinstance(message, Message.TIME_CONTROL):
            self._create_game_info()
            self.shared["game_info"]["time_text"] = message.time_text
            self.shared["game_info"]["tc_init"] = message.tc_init

        elif isinstance(message, Message.LEVEL):
            self._create_game_info()
            self.shared["game_info"]["level_text"] = message.level_text
            self.shared["game_info"]["level_name"] = message.level_name
            _build_headers()
            _send_headers()

        elif isinstance(message, Message.DGT_NO_CLOCK_ERROR):
            # result = {'event': 'Status', 'msg': 'Error clock'}
            # EventHandler.write_to_clients(result)
            pass

        elif isinstance(message, Message.DGT_CLOCK_VERSION):
            if message.dev == "ser":
                attached = "serial"
            elif message.dev == "i2c":
                attached = "i2c-pi"
            else:
                attached = "server"
            result = {"event": "Status", "msg": "Ok clock " + attached}
            EventHandler.write_to_clients(result)

        elif isinstance(message, Message.COMPUTER_MOVE):
            game_copy = message.game.copy()
            game_copy.push(message.move)
            pgn_str = _transfer(game_copy)
            fen = _oldstyle_fen(game_copy)
            mov = message.move.uci()
            result = {"pgn": pgn_str, "fen": fen, "event": "Fen", "move": mov, "play": "computer"}
            self.shared["last_dgt_move_msg"] = result  # not send => keep it for COMPUTER_MOVE_DONE

        elif isinstance(message, Message.COMPUTER_MOVE_DONE):
            WebDisplay.result_sav = ""
            result = self.shared["last_dgt_move_msg"]
            EventHandler.write_to_clients(result)

        elif isinstance(message, Message.USER_MOVE_DONE):
            WebDisplay.result_sav = ""
            pgn_str = _transfer(message.game)
            fen = _oldstyle_fen(message.game)
            mov = message.move.uci()
            result = {"pgn": pgn_str, "fen": fen, "event": "Fen", "move": mov, "play": "user"}
            self.shared["last_dgt_move_msg"] = result
            EventHandler.write_to_clients(result)

        elif isinstance(message, Message.REVIEW_MOVE_DONE):
            pgn_str = _transfer(message.game)
            fen = _oldstyle_fen(message.game)
            mov = message.move.uci()
            result = {"pgn": pgn_str, "fen": fen, "event": "Fen", "move": mov, "play": "review"}
            self.shared["last_dgt_move_msg"] = result
            EventHandler.write_to_clients(result)

        elif isinstance(message, Message.ALTERNATIVE_MOVE):
            pgn_str = _transfer(message.game)
            fen = _oldstyle_fen(message.game)
            mov = peek_uci(message.game)
            result = {"pgn": pgn_str, "fen": fen, "event": "Fen", "move": mov, "play": "reload"}
            self.shared["last_dgt_move_msg"] = result
            EventHandler.write_to_clients(result)

        elif isinstance(message, Message.SWITCH_SIDES):
            pgn_str = _transfer(message.game)
            fen = _oldstyle_fen(message.game)
            mov = message.move.uci()
            result = {"pgn": pgn_str, "fen": fen, "event": "Fen", "move": mov, "play": "reload"}
            self.shared["last_dgt_move_msg"] = result
            EventHandler.write_to_clients(result)

        elif isinstance(message, Message.TAKE_BACK):
            pgn_str = _transfer(message.game)
            fen = _oldstyle_fen(message.game)
            mov = peek_uci(message.game)
            result = {"pgn": pgn_str, "fen": fen, "event": "Fen", "move": mov, "play": "reload"}
            self.shared["last_dgt_move_msg"] = result
            EventHandler.write_to_clients(result)

        elif isinstance(message, Message.PROMOTION_DIALOG):
            result = {"event": "PromotionDlg", "move": message.move}
            EventHandler.write_to_clients(result)

        elif isinstance(message, Message.GAME_ENDS):
            if message.result == GameResult.DRAW:
                WebDisplay.result_sav = "1/2-1/2"
            elif message.result in (GameResult.WIN_WHITE, GameResult.WIN_BLACK):
                WebDisplay.result_sav = "1-0" if message.result == GameResult.WIN_WHITE else "0-1"
            elif message.result == GameResult.OUT_OF_TIME:
                if message.game.turn == chess.WHITE:
                    WebDisplay.result_sav = "0-1"
                else:
                    WebDisplay.result_sav = "1-0"
            else:
                WebDisplay.result_sav = ""
            if WebDisplay.result_sav != "":
                _build_headers()
                _send_headers()
        else:  # Default
            pass

    def _create_task(self, msg):
        # put callback to be executed by Tornado main event loop
        self.io_loop.add_callback(callback=lambda: self.task(msg))


    def run(self):
        """Call by threading.Thread start() function."""
        asyncio.set_event_loop(self.loop)
        self._task = self.loop.create_task(self.message_to_task())
        self.loop.run_forever()


    async def message_to_task(self):
        """ Message task consumer for WebDisplay messages """
        logger.info("msg_queue ready")
        while True:
            # Check if we have something to display
            try:
                message = self.msg_queue.get_nowait()
                self._create_task(message)
            except queue.Empty:
                await asyncio.sleep(FLOAT_MSG_WAIT)
