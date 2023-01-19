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
    modern_engines: List[Dict[str, str]] = read_engine_ini(filename='engines.ini')
    retro_engines: List[Dict[str, str]] = read_engine_ini(filename='retro.ini')
    favorite_engines: List[Dict[str, str]] = read_engine_ini(filename='favorites.ini')
    installed_engines: List[Dict[str, str]] = modern_engines + retro_engines + favorite_engines
    # set retro/favorite engines to the list of modern engines in case retro.ini or favorites.ini is empty
    if not retro_engines:
        retro_engines = modern_engines
    if not favorite_engines:
        favorite_engines = modern_engines
