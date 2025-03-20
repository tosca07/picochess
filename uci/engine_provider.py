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

from typing import Dict, List

from uci.read import read_engine_ini


class EngineProvider(object):
    """
    EngineProvider is a data holder for defined engines in engines.ini, retro.ini and favorites.ini.
    """

    modern_engines: List[Dict[str, str]] = []
    retro_engines: List[Dict[str, str]] = []
    favorite_engines: List[Dict[str, str]] = []
    installed_engines: List[Dict[str, str]] = []

    @classmethod
    def init(cls):
        cls.modern_engines: List[Dict[str, str]] = read_engine_ini(filename="engines.ini")
        cls.retro_engines: List[Dict[str, str]] = read_engine_ini(filename="retro.ini")
        cls.favorite_engines: List[Dict[str, str]] = read_engine_ini(filename="favorites.ini")
        # set retro/favorite engines to the list of modern engines in case retro.ini or favorites.ini is empty
        if not cls.retro_engines:
            cls.retro_engines = cls.modern_engines
        if not cls.favorite_engines:
            cls.favorite_engines = cls.modern_engines
        cls.installed_engines: List[Dict[str, str]] = cls.modern_engines + cls.retro_engines + cls.favorite_engines
