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

import base64
import datetime
import logging
import os
import mimetypes
import asyncio

from email import encoders
from email.mime.multipart import MIMEMultipart
from email.mime.audio import MIMEAudio
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.text import MIMEText
from typing import Optional
from smtplib import SMTP_SSL as SMTP
from smtplib import SMTP
from ssl import create_default_context

import requests
import chess  # type: ignore
import chess.pgn  # type: ignore
import dgt.util

from timecontrol import TimeControl
from utilities import DisplayMsg
from dgt.api import Dgt, Message
from dgt.util import PlayMode, Mode, TimeMode
from picotutor import PicoTutor

logger = logging.getLogger(__name__)


# molli: support for player names from online game
class ModeInfo:
    online_mode = False
    pgn_mode = False
    emulation_mode = False
    opening_name = ""
    opening_eco = ""
    online_opponent = ""
    online_own_user = ""
    end_result = "*"
    book_in_use = ""
    retro_engine_features = " /"
    clock_side = "left"
    flipped_board = False
    eboard_type = dgt.util.EBoard.DGT

    @classmethod
    def set_opening(cls, book_in_use, op_name, op_eco):
        ModeInfo.opening_name = op_name
        ModeInfo.opening_eco = op_eco
        ModeInfo.book_in_use = book_in_use
        ModeInfo.opening_name = ModeInfo.opening_name.strip()
        ModeInfo.opening_name.replace("\n", "")
        ModeInfo.opening_name.replace("\r", "")
        ModeInfo.opening_name.replace("\t", "")
        ModeInfo.opening_name.replace("[", "")
        ModeInfo.opening_name.replace("]", "")
        ModeInfo.opening_name.replace("(", "")
        ModeInfo.opening_name.replace(")", "")
        ModeInfo.opening_name = ModeInfo.opening_name.strip()
        ModeInfo.opening_eco.replace("\n", "")
        ModeInfo.opening_eco.replace("\r", "")
        ModeInfo.opening_eco.replace("\t", "")
        ModeInfo.opening_eco.replace("[", "")
        ModeInfo.opening_eco.replace("]", "")
        ModeInfo.opening_eco.replace("(", "")
        ModeInfo.opening_eco.replace(")", "")

    @classmethod
    def reset_opening(cls):
        ModeInfo.opening_name = ""
        ModeInfo.opening_eco = ""
        ModeInfo.book_in_use = ""

    @classmethod
    def set_game_ending(cls, result):
        logger.debug("Save game result %s", result)
        ModeInfo.end_result = result

    @classmethod
    def get_retro_features(cls):
        return ModeInfo.retro_engine_features

    @classmethod
    def get_game_ending(cls):
        return ModeInfo.end_result

    @classmethod
    def set_online_mode(cls, mode):
        ModeInfo.online_mode = mode
        if mode:
            ModeInfo.pgn_mode = False
            ModeInfo.emulation_mode = False

    @classmethod
    def get_online_mode(cls):
        return ModeInfo.online_mode

    @classmethod
    def set_clock_side(cls, side):
        ModeInfo.clock_side = side

    @classmethod
    def get_clock_side(cls):
        return ModeInfo.clock_side

    @classmethod
    def set_flipped_board(cls, flipped):
        ModeInfo.flipped_board = flipped

    @classmethod
    def get_flipped_board(cls):
        return ModeInfo.flipped_board

    @classmethod
    def set_eboard_type(cls, type):
        ModeInfo.eboard_type = type

    @classmethod
    def get_eboard_type(cls):
        return ModeInfo.eboard_type

    @classmethod
    def set_emulation_mode(cls, mode):
        ModeInfo.emulation_mode = mode
        if mode:
            ModeInfo.online_mode = False
            ModeInfo.pgn_mode = False

    @classmethod
    def get_emulation_mode(cls):
        return ModeInfo.emulation_mode

    @classmethod
    def set_pgn_mode(cls, mode):
        ModeInfo.pgn_mode = mode
        if mode:
            ModeInfo.online_mode = False
            ModeInfo.emulation_mode = False

    @classmethod
    def get_pgn_mode(cls):
        return ModeInfo.pgn_mode

    @classmethod
    def set_online_opponent(cls, name):
        ModeInfo.online_opponent = name
        ModeInfo.online_opponent.replace("[", "")
        ModeInfo.online_opponent.replace("]", "")
        ModeInfo.online_opponent.replace("(", "")
        ModeInfo.online_opponent.replace(")", "")
        ModeInfo.online_opponent.replace("\n", "")
        ModeInfo.online_opponent.replace("\r", "")
        ModeInfo.online_opponent.replace("\t", "")

    @classmethod
    def get_online_opponent(cls):
        return ModeInfo.online_opponent

    @classmethod
    def set_online_own_user(cls, name):
        ModeInfo.online_own_user = name
        ModeInfo.online_own_user.replace("[", "")
        ModeInfo.online_own_user.replace("]", "")
        ModeInfo.online_own_user.replace("(", "")
        ModeInfo.online_own_user.replace(")", "")
        ModeInfo.online_own_user.replace("\n", "")
        ModeInfo.online_own_user.replace("\r", "")
        ModeInfo.online_own_user.replace("\t", "")

    @classmethod
    def get_online_own_user(cls):
        if ModeInfo.online_own_user != "":
            pass
        else:
            ModeInfo.online_own_user = cls.get_online_own_user()
        return ModeInfo.online_own_user


class Emailer(object):
    """Handle eMail with subject, body and an attached file."""

    def __init__(self, email=None, mailgun_key=None):
        if email:  # check if email address is provided by picochess.ini
            self.email = email
        else:
            self.email = False
        self.smtp_server = None
        self.smtp_encryption = None
        self.smtp_user = None
        self.smtp_pass = None
        self.smtp_from = None
        self.smtp_port = None
        self.smtp_starttls = None

        if email and mailgun_key:
            self.mailgun_key = base64.b64decode(str.encode(mailgun_key)).decode("utf-8")
        else:
            self.mailgun_key = False

    def _use_smtp(self, subject, body, path):
        # if self.smtp_server is not provided than don't try to send email via smtp service
        logger.debug("SMTP Mail delivery: Started")
        # change to smtp based mail delivery
        # depending on encrypted mail delivery, we need to import the right lib
        if self.smtp_encryption:
            # lib with ssl encryption
            logger.debug("SMTP Mail delivery: Import SSL SMTP Lib")
        elif self.smtp_starttls:
            logger.debug("SMTP Mail delivery: Import SSL SMTP Lib (with STARTTLS)")
        else:
            # lib without encryption (SMTP-port 21)
            logger.debug("SMTP Mail delivery: Import standard SMTP Lib (no SSL encryption)")
        conn = False
        try:
            outer = MIMEMultipart()
            outer["Subject"] = subject  # put subject to mail
            outer["From"] = "Your PicoChess computer <{}>".format(self.smtp_from)
            outer["To"] = self.email
            outer.attach(MIMEText(body, "plain"))  # pack the pgn to Email body

            ctype, encoding = mimetypes.guess_type(path)
            if ctype is None or encoding is not None:
                ctype = "application/octet-stream"
            maintype, subtype = ctype.split("/", 1)
            if maintype == "text":
                with open(path) as fpath:
                    msg = MIMEText(fpath.read(), _subtype=subtype)
            elif maintype == "image":
                with open(path, "rb") as fpath:
                    msg = MIMEImage(fpath.read(), _subtype=subtype)
            elif maintype == "audio":
                with open(path, "rb") as fpath:
                    msg = MIMEAudio(fpath.read(), _subtype=subtype)
            else:
                with open(path, "rb") as fpath:
                    msg = MIMEBase(maintype, subtype)
                    msg.set_payload(fpath.read())
                encoders.encode_base64(msg)
            msg.add_header("Content-Disposition", "attachment", filename=os.path.basename(path))
            outer.attach(msg)

            if self.smtp_starttls:

                # handle starttls smtp server connections
                logger.debug(
                    "SMTP Mail delivery: trying to connect to " + self.smtp_server + " via port " + str(self.smtp_port)
                )
                context = create_default_context()
                conn = SMTP(self.smtp_server, self.smtp_port)
                conn.set_debuglevel(1)
                # conn.ehlo()  # Can be omitted
                conn.starttls(context=context)
                # conn.ehlo()  # Can be omitted
                logger.debug("SMTP Username, password: " + self.smtp_user + ", " + "XXXXXXX")

            else:

                logger.debug("SMTP Mail delivery: trying to connect to " + self.smtp_server)
                conn = SMTP(self.smtp_server)  # contact smtp server
                conn.set_debuglevel(False)  # no debug info from smtp lib

            if self.smtp_user is not None and self.smtp_pass is not None:
                logger.debug("SMTP Mail delivery: trying to log to SMTP Server")
                conn.login(self.smtp_user, self.smtp_pass)  # login at smtp server

            logger.debug("SMTP Mail delivery: trying to send email")
            conn.sendmail(self.smtp_from, self.email, outer.as_string())
            logger.debug("SMTP Mail delivery: successfuly delivered message to SMTP server")
        except Exception as smtp_exc:
            logger.error("SMTP Mail delivery: Failed")
            logger.error("SMTP Mail delivery: " + str(smtp_exc))
        finally:
            if conn:
                conn.close()
            logger.debug("SMTP Mail delivery: Ended")

    def _use_mailgun(self, subject, body):
        out = requests.post(
            "https://api.mailgun.net/v3/picochess.org/messages",
            auth=("api", self.mailgun_key),
            data={
                "from": "Your PicoChess computer <no-reply@picochess.org>",
                "to": self.email,
                "subject": subject,
                "text": body,
            },
        )
        logger.debug(out)

    def set_smtp(self, sserver=None, sencryption=None, suser=None, spass=None, sfrom=None, sport=None, sstarttls=None):
        """Store information for SMTP based mail delivery."""
        self.smtp_server = sserver
        self.smtp_encryption = sencryption
        self.smtp_user = suser
        self.smtp_pass = spass
        self.smtp_from = sfrom
        self.smtp_port = sport
        self.smtp_starttls = sstarttls

    def send(self, subject: str, body: str, path: str):
        """Send the email out."""
        if self.email:  # check if email address to send the pgn to is provided
            if self.mailgun_key:  # check if we have mailgun-key available to send the pgn successful
                self._use_mailgun(subject=subject, body=body)
            if self.smtp_server:  # check if smtp server address provided
                self._use_smtp(subject=subject, body=body, path=path)


class PgnDisplay(DisplayMsg):
    """Deal with DisplayMessages related to pgn."""

    def __init__(self, file_name: str, emailer: Emailer, shared: dict, loop: asyncio.AbstractEventLoop):
        super(PgnDisplay, self).__init__(loop)
        self.file_name = file_name
        self.last_file_name = "games" + os.sep + "last_game.pgn"
        self.emailer = emailer

        self.engine_name = "?"
        self.old_engine = "?"
        self.user_name = "?"
        self.user_name_orig = "?"
        self.rspeed = "1.0"
        self.location = "?"
        self.level_text: Optional[Dgt.DISPLAY_TEXT] = None
        self.level_name = ""
        self.old_level_name = ""
        self.old_level_text = None
        self.old_engine_elo = "-"
        self.user_elo = "-"
        self.engine_elo = "-"
        self.mode = ""
        self.startime = datetime.datetime.now().strftime("%H:%M:%S")
        self.last_saved_game = None
        self.picotutor: PicoTutor | None = None
        self.shared = shared  # shared headers needed in generate_pgn_from_message

    def set_picotutor(self, picotutor: PicoTutor):
        """Assign a reference to the picotutor object."""
        self.picotutor = picotutor

    def _pgn_game_from_message(self, message) -> chess.pgn.Game:
        """common routine for pgn creators to create a savable game
        wraps the two _generate_pgn_from... functions"""
        # if message.mode in (Mode.NORMAL, Mode.BRAIN, Mode.TRAINING):
        # same as main eng_plays()
        pgn_game: chess.pgn.Game = self._generate_pgn_from_message(message)
        # else:
        # in analysis try to preserve original headers as we have not played
        # pgn_game: chess.pgn.Game = self._generate_pgn_from_existing_headers(message)
        return pgn_game

    def _generate_pgn_from_existing_headers(self, message) -> chess.pgn.Game:
        """create a pgn.game and fill it with existing headers"""
        pgn_game = chess.pgn.Game().from_board(message.game)
        pgn_game.headers.update(self.shared["headers"])  # overwrite with existing headers
        return pgn_game

    def _generate_pgn_from_message(self, message) -> chess.pgn.Game:
        """create a pgn.game and fill it with headers from a played game"""
        pgn_game = chess.pgn.Game().from_board(message.game)

        # Headers
        if ModeInfo.get_online_mode():
            pgn_game.headers["Event"] = "PicoChess" + self.engine_name
        else:
            pgn_game.headers["Event"] = "PicoChess Game"

        pgn_game.headers["Site"] = self.location
        pgn_game.headers["Date"] = datetime.date.today().strftime("%Y.%m.%d")
        pgn_game.headers["Time"] = self.startime

        logger.debug("molli: pgn save result = %s", ModeInfo.get_game_ending())
        if pgn_game.headers["Result"] == "*":
            pgn_game.headers["Result"] = ModeInfo.get_game_ending()

        if not self.level_text:
            engine_level = ""
        else:
            engine_level = " ({})".format(self.level_text.large_text)

        if self.level_name.startswith("Elo@"):
            comp_elo = self.level_name[4:]
            engine_level = ""
        else:
            comp_elo = self.engine_elo

        if ModeInfo.get_online_mode():
            help1 = ModeInfo.get_online_opponent()
            help2 = "(Opp.)"
            logger.debug("Opp name %s", ModeInfo.get_online_opponent())
            logger.debug("Own User %s", ModeInfo.get_online_opponent())
            if help1[:5] == "Guest":
                engine_name = "Opp.(Guest)"
            else:
                engine_name = ModeInfo.get_online_opponent()[:-1] + help2

            help = ModeInfo.get_online_own_user()
            if help[:5] == "Guest":
                help2 = self.user_name
                user_name = help2 + "(Guest)"
            else:
                help2 = "(" + self.user_name + ")"
                user_name = ModeInfo.get_online_own_user()[:-1] + help2
                user_name.replace("\n", "")
                user_name = str(user_name)

            logger.debug("Play Mode %s", message.play_mode)
            if message.play_mode == PlayMode.USER_WHITE:
                pgn_game.headers["White"] = user_name
                pgn_game.headers["Black"] = engine_name
                pgn_game.headers["WhiteElo"] = str(self.user_elo)
                pgn_game.headers["BlackElo"] = str(comp_elo)
            if message.play_mode == PlayMode.USER_BLACK:
                pgn_game.headers["White"] = engine_name
                pgn_game.headers["Black"] = user_name
                pgn_game.headers["WhiteElo"] = str(comp_elo)
                pgn_game.headers["BlackElo"] = str(self.user_elo)
        else:
            if message.play_mode == PlayMode.USER_WHITE:
                pgn_game.headers["White"] = self.user_name
                pgn_game.headers["Black"] = self.engine_name + engine_level
                pgn_game.headers["WhiteElo"] = str(self.user_elo)
                pgn_game.headers["BlackElo"] = str(comp_elo)
            if message.play_mode == PlayMode.USER_BLACK:
                pgn_game.headers["White"] = self.engine_name + engine_level
                pgn_game.headers["Black"] = self.user_name
                pgn_game.headers["WhiteElo"] = str(comp_elo)
                pgn_game.headers["BlackElo"] = str(self.user_elo)

        # game time related tags for picochess
        l_tc_init = message.tc_init
        l_timectrl = TimeControl(**l_tc_init)

        if l_timectrl.depth > 0:
            pgn_game.headers["PicoDepth"] = str(l_timectrl.depth)
        if l_timectrl.node > 0:
            pgn_game.headers["PicoNode"] = str(l_timectrl.node)
        if ModeInfo.get_emulation_mode():
            rspeed_str = str(round(float(self.rspeed), 2))
            pgn_game.headers["PicoRSpeed"] = rspeed_str

        # Timecontrol
        if l_timectrl.mode == TimeMode.FIXED:
            l_timecontrol = str(l_timectrl.move_time)
        elif l_timectrl.mode == TimeMode.BLITZ:
            l_timecontrol = str(l_timectrl.game_time) + " " + "0"
        elif l_timectrl.mode == TimeMode.FISCHER:
            l_timecontrol = str(l_timectrl.game_time) + " " + str(l_timectrl.fisch_inc)

        if l_timectrl.moves_to_go_orig > 0:
            if l_timectrl.fisch_inc > 0:
                l_timecontrol = (
                    str(l_timectrl.moves_to_go_orig)
                    + " "
                    + str(l_timectrl.game_time)
                    + " "
                    + str(l_timectrl.fisch_inc)
                    + " "
                    + str(l_timectrl.game_time2)
                )
            else:
                l_timecontrol = (
                    str(l_timectrl.moves_to_go_orig)
                    + " "
                    + str(l_timectrl.game_time)
                    + " 0 "
                    + str(l_timectrl.game_time2)
                )

        # remaining game times
        l_int_time = l_tc_init["internal_time"]
        l_rem_time_w = str(int(l_int_time[chess.WHITE]))
        l_rem_time_b = str(int(l_int_time[chess.BLACK]))

        pgn_game.headers["PicoTimeControl"] = l_timecontrol
        pgn_game.headers["PicoRemTimeW"] = l_rem_time_w
        pgn_game.headers["PicoRemTimeB"] = l_rem_time_b

        # book opening information
        if ModeInfo.book_in_use:
            pgn_game.headers["PicoOpeningBook"] = ModeInfo.book_in_use
        if ModeInfo.opening_name:
            pgn_game.headers["Opening"] = ModeInfo.opening_name
            pgn_game.headers["ECO"] = ModeInfo.opening_eco

        return pgn_game

    def get_node_at_halfmove_nr(self, game: chess.Board, halfmove_nr: int) -> Optional[chess.pgn.GameNode]:
        """get the node halfmove_nr (ply) in the game tree - 0 is like 1. e4"""
        nodes = list(game.mainline())
        if halfmove_nr - 1 < len(nodes):
            return nodes[halfmove_nr - 1]  # first halfmove index zero
        else:
            return None

    def add_picotutor_evaluation(self, game: chess.Board):
        """add picotutor evaluations to the game"""
        # see if we have an evaluation in picotutor
        if self.picotutor:
            eval_moves = self.picotutor.get_eval_moves()
            for (halfmove_nr, user_move, turn), value in eval_moves.items():
                # key=(ply halfmove number, move)
                node = self.get_node_at_halfmove_nr(game, halfmove_nr)
                if node:  # game has this ply node
                    pgn_move = node.move
                    if pgn_move == user_move and node.turn() == turn:  # checksum
                        nag = value["nag"]  # $N symbol for !!, ! etc
                        if nag != chess.pgn.NAG_NULL:
                            node.nags.add(nag)
                        node.comment = self._get_picotutor_eval_comments(nag, value)
                    else:
                        logger.debug("skipped move %s-%s picotutor eval mismatch", pgn_move.uci(), user_move.uci())

    def _get_picotutor_eval_comments(self, nag: int, value: dict) -> str:
        """get comments found in picotutor evaluations value dict"""
        if nag != chess.pgn.NAG_NULL:
            comment = PicoTutor.nag_to_symbol(nag)  # back to !!, ! etc
        else:
            # special case inaccuracy - its not a nag, but CPL > INACCURACY_TH
            # its the only case where there is a No-NULL evaluation
            if "best_move" in value:
                comment = "Best: " + value["best_move"]
            else:
                comment = "Inaccuracy "  # should never happen, fallback
        if "mate" in value:
            comment += " Mate in: " + str(value["mate"])
        else:
            if "score" in value:
                comment += " Score: " + str(value["score"])
        if "CPL" in value:
            comment += " CPL: " + str(value["CPL"])
        if "deep_low_diff" in value:
            comment += " DS: " + str(value.get("deep_low_diff"))
        if nag in (chess.pgn.NAG_BLUNDER, chess.pgn.NAG_MISTAKE, chess.pgn.NAG_DUBIOUS_MOVE):
            if "best_move" in value:
                comment += " Best: " + value["best_move"]
        return comment

    def _save_and_email_pgn(self, message):
        """when game ends the pgn file is saved and emailed"""
        logger.debug("Saving game to [%s]", self.file_name)
        pgn_game = self._pgn_game_from_message(message)
        pgn_game_last = pgn_game

        # If we already saved the exact same game, do not
        # save it again, and do not send an email
        logger.debug(
            "Comparing current game to last save game:\nCurrent Game: %s\nLast Saved Game: %s",
            pgn_game,
            self.last_saved_game,
        )
        if str(pgn_game) == str(self.last_saved_game):
            logger.debug("Current game is the same as last saved gamed, skipping")
            return
        self.last_saved_game = pgn_game

        # add picotutor stored evaluations before saving game
        self.add_picotutor_evaluation(pgn_game)

        # Save to last game file
        with open(self.last_file_name, "w") as last_file:
            last_exporter = chess.pgn.FileExporter(last_file)
            pgn_game_last.accept(last_exporter)

        # Append to all games file
        with open(self.file_name, "a") as file:
            exporter = chess.pgn.FileExporter(file)
            pgn_game.accept(exporter)

        self.emailer.send("Game PGN", str(pgn_game), self.file_name)

    def _save_pgn(self, message):
        l_file_name = "games" + os.sep + message.pgn_filename
        logger.debug("Saving PGN game to [%s]", l_file_name)
        pgn_game = self._pgn_game_from_message(message)

        # add picotutor stored evaluations before saving game
        self.add_picotutor_evaluation(pgn_game)

        with open(l_file_name, "w") as file:
            exporter = chess.pgn.FileExporter(file)
            pgn_game.accept(exporter)

        logger.debug("molli: save pgn finished")

    async def _process_message(self, message):
        await asyncio.sleep(0.1)  # reduce priority for PGN
        if False:  # switch-case
            pass

        elif isinstance(message, Message.SYSTEM_INFO):
            if "engine_name" in message.info:
                self.engine_name = message.info["engine_name"]
                ModeInfo.retro_engine_features = " /"
                if "(pos+info)" in self.engine_name:
                    ModeInfo.retro_engine_features = " pos + info"
                    self.engine_name = self.engine_name.replace("(pos+info)", "")
                if "(pos)" in self.engine_name:
                    ModeInfo.retro_engine_features = " position"
                    self.engine_name = self.engine_name.replace("(pos)", "")
                if "(info)" in self.engine_name:
                    ModeInfo.retro_engine_features = " information"
                    self.engine_name = self.engine_name.replace("(info)", "")
                    self.old_engine = self.engine_name
                    self.old_level_name = self.level_name
                    self.old_level_text = self.level_text
                    self.old_engine_elo = self.engine_elo
            if "user_name" in message.info:
                self.user_name = message.info["user_name"]
                self.user_name_orig = message.info["user_name"]
            if "user_elo" in message.info:
                self.user_elo = message.info["user_elo"]
            if "engine_elo" in message.info:
                self.engine_elo = message.info["engine_elo"]
            if "rspeed" in message.info:
                self.rspeed = message.info["rspeed"]

        elif isinstance(message, Message.IP_INFO):
            self.location = message.info["location"]

        elif isinstance(message, Message.STARTUP_INFO):
            self.level_text = message.info["level_text"]
            self.level_name = message.info["level_name"]
            self.old_level_name = self.level_name
            self.old_level_text = self.level_text
            self.old_engine_elo = self.engine_elo
            if "engine_elo" in message.info:
                self.engine_elo = message.info["engine_elo"]

        elif isinstance(message, Message.LEVEL):
            self.level_text = message.level_text
            self.level_name = message.level_name
            self.old_level_name = self.level_name
            self.old_level_text = self.level_text
            self.old_engine_elo = self.engine_elo

        elif isinstance(message, Message.INTERACTION_MODE):
            self.mode = message.mode
            if message.mode == Mode.REMOTE:
                self.old_engine = self.engine_name
                self.engine_name = "Remote Player"
                self.level_text = None
                self.level_name = ""
            elif message.mode == Mode.OBSERVE:
                self.old_engine = self.engine_name
                self.engine_name = "Player B"
                self.user_name = "Player A"
                self.level_text = None
                self.level_name = ""
            else:
                self.engine_name = self.old_engine
                self.level_name = self.old_level_name
                self.level_text = self.old_level_text
                self.engine_elo = self.old_engine_elo
                self.user_name = self.user_name_orig

        elif isinstance(message, Message.ENGINE_STARTUP):
            for index in range(0, len(message.installed_engines)):
                eng = message.installed_engines[index]
                if eng["file"] == message.file:
                    self.engine_elo = eng["elo"]
                    break

        elif isinstance(message, Message.ENGINE_READY):
            self.engine_name = message.engine_name
            ModeInfo.retro_engine_features = " /"
            if "(pos+info)" in self.engine_name:
                ModeInfo.retro_engine_features = " pos + info"
                self.engine_name = self.engine_name.replace("(pos+info)", "")
            if "(pos)" in self.engine_name:
                ModeInfo.retro_engine_features = " position"
                self.engine_name = self.engine_name.replace("(pos)", "")
            if "(info)" in self.engine_name:
                ModeInfo.retro_engine_features = " information"
                self.engine_name = self.engine_name.replace("(info)", "")

            self.old_engine = self.engine_name
            self.engine_elo = message.eng["elo"]
            if not message.has_levels:
                self.level_text = None
                self.level_name = ""

            self.old_level_name = self.level_name
            self.old_level_text = self.level_text
            self.old_engine_elo = self.engine_elo

        elif isinstance(message, Message.GAME_ENDS):
            if message.game.move_stack and not ModeInfo.get_pgn_mode() and self.mode != Mode.PONDER:
                # we do not have pgn_filename in GAME_ENDS as we have in SAVE_GAME message
                self._save_and_email_pgn(message)

        elif isinstance(message, Message.START_NEW_GAME):
            if "(pos+info)" in self.engine_name:
                ModeInfo.retro_engine_features = " pos + info"
                self.engine_name = self.engine_name.replace("(pos+info)", "")
            if "(pos)" in self.engine_name:
                ModeInfo.retro_engine_features = " position"
                self.engine_name = self.engine_name.replace("(pos)", "")
            if "(info)" in self.engine_name:
                ModeInfo.retro_engine_features = " information"
                self.engine_name = self.engine_name.replace("(info)", "")
            self.startime = datetime.datetime.now().strftime("%H:%M:%S")

        elif isinstance(message, Message.SAVE_GAME):
            logger.debug("molli: save game message pgn dispatch")
            if message.game.move_stack:
                self._save_pgn(message)  # needs pgn_filename from SAVE_GAME message
                # if we _save_and_email_pgn() here the side effect is that
                # it stores unfinished games in games.pgn

        else:
            await asyncio.sleep(0.05)  # balancing message queues

    async def message_consumer(self):
        """PGN message consumer"""
        logger.info("msg_queue ready")
        while True:
            # Check if we have something to display
            message = await self.msg_queue.get()
            if (
                not isinstance(message, Message.DGT_SERIAL_NR)
                and not isinstance(message, Message.DGT_CLOCK_TIME)
                and not isinstance(message, Message.CLOCK_TIME)
            ):
                logger.debug("received message from msg_queue: %s", message)
            asyncio.create_task(self._process_message(message))
            self.msg_queue.task_done()
