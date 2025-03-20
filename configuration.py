import configargparse  # type: ignore
import os

from utilities import version


class Configuration:
    def __init__(self):
        # Command line argument parsing
        self.parser = configargparse.ArgParser(
            default_config_files=[
                os.path.join(os.path.dirname(__file__), "picochess.ini"),
            ]
        )
        self.parser.add_argument(
            "-e",
            "--engine",
            type=str,
            help="UCI engine filename/path such as 'engines/aarch64/a-stockf'",
            default=None,
        )
        self.parser.add_argument("-el", "--engine-level", type=str, help="UCI engine level", default=None)
        self.parser.add_argument(
            "-er",
            "--engine-remote",
            type=str,
            help="UCI engine filename/path such as 'engines/aarch64/a-stockf'",
            default=None,
        )
        self.parser.add_argument(
            "-ers",
            "--engine-remote-server",
            type=str,
            help="address of the remote engine server",
            default=None,
        )
        self.parser.add_argument("-eru", "--engine-remote-user", type=str, help="username for the remote engine server")
        self.parser.add_argument("-erp", "--engine-remote-pass", type=str, help="password for the remote engine server")
        self.parser.add_argument("-erk", "--engine-remote-key", type=str, help="key file for the remote engine server")
        self.parser.add_argument(
            "-erh",
            "--engine-remote-home",
            type=str,
            help="engine home path for the remote engine server",
            default="",
        )
        self.parser.add_argument(
            "-d",
            "--dgt-port",
            type=str,
            help="enable dgt board on the given serial port such as '/dev/ttyUSB0'",
        )
        self.parser.add_argument(
            "-b",
            "--book",
            type=str,
            help="path of book such as 'books/b-flank.bin'",
            default="books/h-varied.bin",
        )
        self.parser.add_argument(
            "-t",
            "--time",
            type=str,
            default="5 0",
            help="Time settings <FixSec> or <StMin IncSec> like '10'(move) or '5 0'(game) or '3 2'(fischer) or '40 120 60' (tournament). \
                            All values must be below 999",
        )
        self.parser.add_argument(
            "-dept",
            "--depth",
            type=int,
            default=0,
            choices=range(0, 99),
            help="searchdepth per move for the engine",
        )
        self.parser.add_argument(
            "-node",
            "--node",
            type=int,
            default=0,
            choices=range(0, 99),
            help="search nodes per move for the engine",
        )
        self.parser.add_argument(
            "-norl", "--disable-revelation-leds", action="store_true", help="disable Revelation leds"
        )
        self.parser.add_argument(
            "-l",
            "--log-level",
            choices=["notset", "debug", "info", "warning", "error", "critical"],
            default="warning",
            help="logging level",
        )
        self.parser.add_argument("-lf", "--log-file", type=str, help="log to the given file")
        self.parser.add_argument(
            "-pf", "--pgn-file", type=str, help="pgn file used to store the games", default="games.pgn"
        )
        self.parser.add_argument("-pu", "--pgn-user", type=str, help="user name for the pgn file", default=None)
        self.parser.add_argument(
            "-pe",
            "--pgn-elo",
            type=str,
            help="user elo for the pgn file, also used for auto-adjusting the elo",
            default="-",
        )
        self.parser.add_argument(
            "-w",
            "--web-server",
            dest="web_server_port",
            nargs="?",
            const=80,
            type=int,
            metavar="PORT",
            help="launch web server",
        )
        self.parser.add_argument("-m", "--email", type=str, help="email used to send pgn/log files", default=None)
        self.parser.add_argument("-ms", "--smtp-server", type=str, help="address of email server", default=None)
        self.parser.add_argument("-mu", "--smtp-user", type=str, help="username for email server", default=None)
        self.parser.add_argument("-mp", "--smtp-pass", type=str, help="password for email server", default=None)
        self.parser.add_argument(
            "-me",
            "--smtp-encryption",
            action="store_true",
            help="use ssl encryption connection to email server",
        )
        self.parser.add_argument(
            "-mt",
            "--smtp-starttls",
            action="store_true",
            help="use starttls encryption connection to email server",
        )
        self.parser.add_argument("-mr", "--smtp-port", type=int, help="port for email server", default=21)
        self.parser.add_argument("-mf", "--smtp-from", type=str, help="From email", default="no-reply@picochess.org")
        self.parser.add_argument(
            "-mk",
            "--mailgun-key",
            type=str,
            help="key used to send emails via Mailgun Webservice",
            default=None,
        )
        self.parser.add_argument(
            "-bc",
            "--beep-config",
            choices=["none", "some", "all", "sample"],
            help="sets standard beep config",
            default="some",
        )
        self.parser.add_argument(
            "-bs",
            "--beep-some-level",
            type=int,
            default=0x03,
            help="sets (some-)beep level from 0(=no beeps) to 15(=all beeps)",
        )
        self.parser.add_argument("-uv", "--user-voice", type=str, help="voice for user", default=None)
        self.parser.add_argument("-cv", "--computer-voice", type=str, help="voice for computer", default=None)
        self.parser.add_argument(
            "-sv",
            "--speed-voice",
            type=int,
            help="voice speech factor from 0(=90%%) to 9(=135%%)",
            default=2,
            choices=range(0, 10),
        )
        self.parser.add_argument(
            "-vv",
            "--volume-voice",
            type=int,
            help="voice volume factor from 0(=muted) to 20(=100%%)",
            default=14,
            choices=range(0, 21),
        )
        self.parser.add_argument(
            "-sp",
            "--enable-setpieces-voice",
            action="store_true",
            help="speak last computer move again when 'set pieces' displayed",
        )
        self.parser.add_argument("-u", "--enable-update", action="store_true", help="enable picochess updates")
        self.parser.add_argument(
            "-ur", "--enable-update-reboot", action="store_true", help="reboot system after update"
        )
        self.parser.add_argument(
            "-nocm",
            "--disable-confirm-message",
            action="store_true",
            help="disable confirmation messages",
        )
        self.parser.add_argument(
            "-v",
            "--version",
            action="version",
            version="%(prog)s version {}".format(version),
            help="show current version",
            default=None,
        )
        self.parser.add_argument("-pi", "--dgtpi", action="store_true", help="use the DGTPi hardware")
        self.parser.add_argument(
            "-csd",
            "--clockside",
            choices=["left", "right"],
            default="left",
            help="side on which you put your DGTPI/DGT3000",
        )
        self.parser.add_argument(
            "-pt",
            "--ponder-interval",
            type=int,
            default=3,
            choices=range(1, 9),
            help="how long each part of ponder display should be visible (default=3secs)",
        )
        self.parser.add_argument(
            "-lang",
            "--language",
            choices=["en", "de", "nl", "fr", "es", "it"],
            default="en",
            help="picochess language",
        )
        self.parser.add_argument("-c", "--enable-console", action="store_true", help="use console interface")
        self.parser.add_argument(
            "-cl",
            "--enable-capital-letters",
            action="store_true",
            help="clock messages in capital letters",
        )
        self.parser.add_argument(
            "-noet",
            "--disable-et",
            action="store_true",
            help="some clocks need this to work - deprecated",
        )
        self.parser.add_argument(
            "-ss",
            "--slow-slide",
            type=int,
            default=0,
            choices=range(0, 10),
            help="extra wait time factor for a stable board position (sliding detect)",
        )
        self.parser.add_argument(
            "-nosn", "--disable-short-notation", action="store_true", help="disable short notation"
        )
        self.parser.add_argument(
            "-comf",
            "--comment-factor",
            type=int,
            help="comment factor from 0 to 100 for voice and written commands",
            default=100,
            choices=range(0, 101),
        )
        self.parser.add_argument(
            "-roln",
            "--rolling-display-normal",
            action="store_true",
            help="switch on rolling display normal mode",
        )
        self.parser.add_argument(
            "-rolp",
            "--rolling-display-ponder",
            action="store_true",
            help="switch on rolling display ponder mode",
        )
        self.parser.add_argument(
            "-flex",
            "--flexible-analysis",
            action="store_false",
            help="switch off flexible analysis mode",
        )
        self.parser.add_argument("-prem", "--premove", action="store_false", help="switch off premove detection")
        self.parser.add_argument(
            "-ctga",
            "--continue-game",
            action="store_true",
            help="continue last game after (re)start of picochess",
        )
        self.parser.add_argument(
            "-seng",
            "--show-engine",
            action="store_false",
            help="show engine after startup and new game",
        )
        self.parser.add_argument(
            "-teng",
            "--tutor-engine",
            type=str,
            default="/opt/picochess/engines/aarch64/a-stockf",
            help="engine used for PicoTutor analysis",
        )
        self.parser.add_argument(
            "-watc",
            "--tutor-watcher",
            action="store_true",
            help="Pico Watcher: atomatic move evaluation, blunder warning & move suggestion, default is off",
        )
        self.parser.add_argument(
            "-coch",
            "--tutor-coach",
            choices=["on", "off", "lift"],
            default="off",
            help="Pico Coach: move and position evaluation, move suggestion etc. on demand, default is off, when selecting lift you can trigger the coach by lifting and putting back a piece",
        )
        self.parser.add_argument(
            "-coan",
            "--coach-analyser",
            action="store_true",
            help="Pico Watcher: use tutor-coach as an analyser instead of the engine you are playing against",
        )
        self.parser.add_argument(
            "-open",
            "--tutor-explorer",
            action="store_true",
            help="Pico Opening Explorer: shows the name(s) of the opening (based on ECO file), default is off",
        )
        self.parser.add_argument(
            "-tcom",
            "--tutor-comment",
            type=str,
            default="off",
            help="show game comments based on specific engines (=single) or in general (=all). Default value is off",
        )
        self.parser.add_argument(
            "-loc",
            "--location",
            type=str,
            default="auto",
            help="determine automatically location for pgn file if set to auto, otherwise the location string which is set will be used",
        )
        self.parser.add_argument(
            "-dtcs",
            "--def-timectrl",
            type=str,
            default="5 0",
            help="default time control setting when leaving an emulation engine after startup",
        )
        self.parser.add_argument(
            "-altm",
            "--alt-move",
            action="store_true",
            help="Playing direct alternative move for pico: default is off",
        )
        self.parser.add_argument(
            "-odec",
            "--online-decrement",
            type=float,
            default=2.0,
            help="Seconds to be subtracted after each own online move in order to sync with server times",
        )
        self.parser.add_argument(
            "-board",
            "--board-type",
            type=str,
            default="dgt",
            help='Type of e-board: "dgt", "certabo", "chesslink", "chessnut", "ichessone" or "noeboard" (for basic web-play only), default is "dgt"',
        )
        self.parser.add_argument(
            "-theme",
            "--theme",
            type=str,
            default="dark",
            help='Web theme, "light", "dark" , "time", "auto" or blank, default is "dark", leave blank for another light theme, "time" for a change according to a fixed time or "auto" for a sunrise/sunset dependent theme setting',
        )
        self.parser.add_argument(
            "-rspeed",
            "--rspeed",
            type=str,
            default="1.0",
            help="RetroSpeed factor for mame eingines, 0.0 for fullspeed, 1.0 for original speed, 0.5 for half of the original speed or any other value from 0.0 to 7.0",
        )
        self.parser.add_argument(
            "-ratdev",
            "--rating-deviation",
            type=str,
            help="Player rating deviation for automatic adjustment of ELO",
            default=350,
        )
        self.parser.add_argument(
            "-rsound",
            "--rsound",
            action="store_true",
            help="en/disable retro engine sound (default is off)",
        )
        self.parser.add_argument(
            "-rwind",
            "--rwindow",
            action="store_true",
            help="en/disable window mode for retro display (default is on, disabling means fullscreen)",
        )
        self.parser.add_argument(
            "-rdisp",
            "--rdisplay",
            action="store_true",
            help="en/disable retro engine artwork display (default is false)",
        )

        self._args, self.unknown = self.parser.parse_known_args()
