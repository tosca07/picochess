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
from geopy.geocoders import Nominatim  # type: ignore
from geopy.exc import GeopyError  # type: ignore
from astral import LocationInfo  # type: ignore
from astral.sun import sun  # type: ignore
import astral.geocoder  # type: ignore

import utilities


def calc_theme(theme_in: str, location_setting: str) -> str:
    theme_out = theme_in
    if theme_in == "auto":
        location = utilities.get_location()[0] if location_setting == "auto" else location_setting
        try:
            location_info = astral.geocoder.lookup(location, astral.geocoder.database())
        except KeyError:
            location_info = _location_info_from_location(location)
        if location_info is not None:
            try:
                theme_out = _theme_from_location_info(location_info)
            except (KeyError, ValueError):
                theme_out = _theme_according_to_current_time()
        else:
            theme_out = _theme_according_to_current_time()
    elif theme_in == "time":
        theme_out = _theme_according_to_current_time()
    return theme_out


def _theme_according_to_current_time() -> str:
    # check if before or after 9am/5pm
    now = datetime.datetime.now()
    year = now.year
    month = now.month
    day = now.day
    sunset = datetime.datetime(year, month, day, 17)
    sunrise = datetime.datetime(year, month, day, 9)
    return _theme_for_time(now, sunrise, sunset)


def _theme_from_location_info(location_info) -> str:
    local_timezone = location_info.tzinfo
    local_time = datetime.datetime.now(local_timezone)
    sun_info = sun(location_info.observer, tzinfo=local_timezone)
    return _theme_for_time(local_time, sun_info["sunrise"], sun_info["sunset"])


def _theme_for_time(current_time: datetime.datetime, sunrise: datetime.datetime, sunset: datetime.datetime) -> str:
    if sunrise < current_time < sunset:
        theme = "light"
    else:
        theme = "dark"
    return theme


def _location_info_from_location(location: str):
    location_info = None
    geolocator = Nominatim(user_agent="Picochess")
    try:
        loc = geolocator.geocode(location)
    except GeopyError:
        loc = None
    if loc is not None:
        location_info = LocationInfo(
            location,
            "",
            datetime.datetime.now().astimezone(datetime.timezone.utc).tzname(),
            loc.latitude,
            loc.longitude,
        )
    return location_info
