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

from typing import Optional
import logging
import configparser
import spur  # type: ignore
import paramiko

from subprocess import DEVNULL
from dgt.api import Event
from utilities import Observable
import chess.uci  # type: ignore
from chess import Board  # type: ignore
from uci.informer import Informer
from uci.rating import Rating, Result
from utilities import write_picochess_ini


class UciShell(object):

    """Handle the uci engine shell."""

    def __init__(self, hostname=None, username=None, key_file=None, password=None, windows=False):
        super(UciShell, self).__init__()
        if hostname:
            logging.info('connecting to [%s]', hostname)
            if key_file:
                if windows:
                    self.shell = spur.SshShell(hostname=hostname, username=username, private_key_file=key_file,
                                               missing_host_key=paramiko.AutoAddPolicy(), shell_type=spur.ssh.ShellTypes.windows)
                else:
                    self.shell = spur.SshShell(hostname=hostname, username=username, private_key_file=key_file,
                                               missing_host_key=paramiko.AutoAddPolicy())
            else:
                if windows:
                    self.shell = spur.SshShell(hostname=hostname, username=username, password=password,
                                               missing_host_key=paramiko.AutoAddPolicy(), shell_type=spur.ssh.ShellTypes.windows)
                else:
                    self.shell = spur.SshShell(hostname=hostname, username=username, password=password,
                                               missing_host_key=paramiko.AutoAddPolicy())
        else:
            self.shell = None

    def get(self):
        return self.shell


class UciEngine(object):

    """Handle the uci engine communication."""

    def __init__(self, file: str, uci_shell: UciShell, mame_par: str):
        super(UciEngine, self).__init__()
        logging.info('mame parameters=' + mame_par)
        try:
            self.is_adaptive = False
            self.is_mame = False
            self.engine_rating = -1
            self.uci_elo_eval_fn = None  # saved UCI_Elo eval function
            self.shell = uci_shell.get()
            logging.info('file ' + file)
            if '/mame/' in file:
                self.is_mame = True
                mfile = [file, mame_par]
                logging.info(mfile)
            else:
                mfile = [file]
                logging.info(mfile)
            if self.shell:
                self.engine = chess.uci.spur_spawn_engine(self.shell, mfile)
            else:
                self.engine = chess.uci.popen_engine(mfile, stderr=DEVNULL)

            self.file = file
            if self.engine:
                handler = Informer()
                self.engine.info_handlers.append(handler)
                self.engine.uci()
            else:
                logging.error('engine executable [%s] not found', file)
            self.options: dict = {}
            self.future = None
            self.show_best = True

            self.res = None
            self.level_support = False
        except OSError:
            logging.exception('OS error in starting engine')
        except TypeError:
            logging.exception('engine executable not found')

    def get_name(self):
        """Get engine name."""
        return self.engine.name

    def get_options(self):
        """Get engine options."""
        return self.engine.options

    def get_pgn_options(self):
        """Get options."""
        return self.options

    def option(self, name, value):
        """Set OptionName with value."""
        self.options[name] = value

    def send(self):
        """Send options to engine."""
        self.engine.setoption(self.options)

    def has_levels(self):
        """Return engine level support."""
        has_lv = self.has_skill_level() or self.has_handicap_level() or self.has_limit_strength() or self.has_strength()
        return self.level_support or has_lv

    def has_skill_level(self):
        """Return engine skill level support."""
        return 'Skill Level' in self.engine.options

    def has_handicap_level(self):
        """Return engine handicap level support."""
        return 'Handicap Level' in self.engine.options

    def has_limit_strength(self):
        """Return engine limit strength support."""
        return 'UCI_LimitStrength' in self.engine.options

    def has_strength(self):
        """Return engine strength support."""
        return 'Strength' in self.engine.options

    def has_chess960(self):
        """Return chess960 support."""
        return 'UCI_Chess960' in self.engine.options

    def has_ponder(self):
        """Return ponder support."""
        return 'Ponder' in self.engine.options

    def get_file(self):
        """Get File."""
        return self.file

    def position(self, game: Board):
        """Set position."""
        self.engine.position(game)

    def quit(self):
        """Quit engine."""
        if self.engine.quit():  # Ask nicely
            if self.engine.terminate():  # If you won't go nicely....
                if self.engine.kill():  # Right that does it!
                    return False
        return True

    def uci(self):
        """Send start uci command."""
        self.engine.uci()

    def stop(self, show_best=False):
        """Stop engine."""
        logging.info('show_best old: %s new: %s', self.show_best, show_best)
        self.show_best = show_best
        if self.is_waiting():
            logging.info('engine already stopped')
            return self.res
        try:
            self.engine.stop()
        except chess.uci.EngineTerminatedException:
            logging.error('Engine terminated')  # @todo find out, why this can happen!
        return self.future.result()

    def pause_pgn_audio(self):
        """Stop engine."""
        logging.info('pause audio old')
        try:
            self.engine.uci()
        except chess.uci.EngineTerminatedException:
            logging.error('Engine terminated')  # @todo find out, why this can happen!

    def go(self, time_dict: dict):
        """Go engine."""
        self.show_best = True
        time_dict['async_callback'] = self.callback
        logging.debug('molli: timedict: %s', str(time_dict))
        # Observable.fire(Event.START_SEARCH())
        self.future = self.engine.go(**time_dict)
        return self.future

    def go_emu(self):
        """Go engine."""
        logging.debug('molli: go_emu')
        self.future = self.engine.go(async_callback=self.callback)

    def ponder(self):
        """Ponder engine."""
        self.show_best = False

        # Observable.fire(Event.START_SEARCH())
        self.future = self.engine.go(ponder=True, infinite=True, async_callback=self.callback)
        return self.future

    def brain(self, time_dict: dict):
        """Permanent brain."""
        self.show_best = True
        time_dict['ponder'] = True
        time_dict['async_callback'] = self.callback3

        # Observable.fire(Event.START_SEARCH())
        self.future = self.engine.go(**time_dict)
        return self.future

    def hit(self):
        """Send a ponder hit."""
        logging.info('show_best: %s', self.show_best)
        self.engine.ponderhit()
        self.show_best = True

    def callback(self, command):
        """Callback function."""
        try:
            self.res = command.result()
        except chess.uci.EngineTerminatedException:
            logging.error('Engine terminated')  # @todo find out, why this can happen!
            self.show_best = False
        logging.info('res: %s', self.res)
        # Observable.fire(Event.STOP_SEARCH())
        if self.show_best and self.res:
            Observable.fire(Event.BEST_MOVE(move=self.res.bestmove, ponder=self.res.ponder, inbook=False))
        else:
            logging.info('event best_move not fired')

    def callback3(self, command):
        """Callback function."""
        try:
            self.res = command.result()
        except chess.uci.EngineTerminatedException:
            logging.error('Engine terminated')  # @todo find out, why this can happen!
            self.show_best = False
        logging.info('res: %s', self.res)
        # Observable.fire(Event.STOP_SEARCH())
        if self.show_best and self.res:
            Observable.fire(Event.BEST_MOVE(move=self.res.bestmove, ponder=self.res.ponder, inbook=False))
        else:
            logging.info('event best_move not fired')

    def is_thinking(self):
        """Engine thinking."""
        return not self.engine.idle and not self.engine.pondering

    def is_pondering(self):
        """Engine pondering."""
        return not self.engine.idle and self.engine.pondering

    def is_waiting(self):
        """Engine waiting."""
        return self.engine.idle

    def newgame(self, game: Board):
        """Engine sometimes need this to setup internal values."""
        self.engine.ucinewgame()
        self.engine.position(game)

    def mode(self, ponder: bool, analyse: bool):
        """Set engine mode."""
        self.engine.setoption({'Ponder': ponder, 'UCI_AnalyseMode': analyse})

    def startup(self, options: dict, rating: Optional[Rating] = None):
        """Startup engine."""
        parser = configparser.ConfigParser()

        if not options:
            if self.shell is None:
                success = bool(parser.read(self.get_file() + '.uci'))
            else:
                try:
                    with self.shell.open(self.get_file() + '.uci', 'r') as file:
                        parser.read_file(file)
                    success = True
                except FileNotFoundError:
                    success = False
            if success:
                options = dict(parser[parser.sections().pop()])

        self.level_support = bool(options)

        self.options = options.copy()
        self._engine_rating(rating)
        logging.debug('setting engine with options %s', self.options)
        self.send()

        logging.debug('Loaded engine [%s]', self.get_name())
        logging.debug('Supported options [%s]', self.get_options())

    def _engine_rating(self, rating: Optional[Rating] = None):
        """
        Set engine_rating; replace UCI_Elo 'auto' value with rating.
        Delete UCI_Elo from the options if no rating is given.
        """
        if 'UCI_Elo' in self.options:
            uci_elo_option = self.options['UCI_Elo'].strip()
            if uci_elo_option.lower() == 'auto' and rating is not None:
                self._set_rating(self._round_engine_rating(int(rating.rating)))
            elif uci_elo_option.isnumeric():
                self.engine_rating = int(uci_elo_option)
            elif 'auto' in uci_elo_option and rating is not None:
                uci_elo_with_rating = uci_elo_option.replace('auto', str(int(rating.rating)))
                try:
                    evaluated = eval(uci_elo_with_rating)
                    if str(evaluated).isnumeric():
                        self._set_rating(int(evaluated))
                        self.uci_elo_eval_fn = uci_elo_option  # save evaluation function for updating engine ELO later
                    else:
                        del self.options['UCI_Elo']
                except Exception as e:  # noqa - catch all exceptions for eval()
                    print(f'invalid option set for UCI_Elo={uci_elo_with_rating}, exception={e}')
                    logging.error(f'invalid option set for UCI_Elo={uci_elo_with_rating}, exception={e}')
                    del self.options['UCI_Elo']
            else:
                del self.options['UCI_Elo']

    def _set_rating(self, value: int):
        self.engine_rating = value
        self.options['UCI_Elo'] = str(int(self.engine_rating))
        self.is_adaptive = True

    def _round_engine_rating(self, value: int) -> int:
        """ Round the value up to the next 50, minimum=500 """
        return max(500, int(value / 50 + 1) * 50)

    def update_rating(self, rating: Rating, result: Result) -> Rating:
        """ Send the new ELO value to the engine and save the ELO and rating deviation """
        if not self.is_adaptive or result is None or self.engine_rating < 0:
            return rating
        new_rating = rating.rate(Rating(self.engine_rating, 0), result)
        if self.uci_elo_eval_fn is not None:
            # evaluation function instead of auto?
            self.engine_rating = eval(self.uci_elo_eval_fn.replace('auto', str(int(new_rating.rating))))
        else:
            self.engine_rating = self._round_engine_rating(int(new_rating.rating))
        self._save_rating(new_rating)
        self.option('UCI_Elo', str(self.engine_rating))
        self.send()
        return new_rating

    def _save_rating(self, new_rating: Rating):
        write_picochess_ini('pgn-elo', max(500, int(new_rating.rating)))
        write_picochess_ini('rating-deviation', int(new_rating.rating_deviation))
