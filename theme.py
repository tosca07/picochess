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
import timezonefinder  # type: ignore
import pytz
from geopy.geocoders import Nominatim  # type: ignore
from astral import LocationInfo  # type: ignore
from astral.sun import sun  # type: ignore
import astral.geocoder  # type: ignore

import utilities


def calc_theme(theme_in: str) -> str:
    theme_out = theme_in
    if theme_in == 'auto':
        location, _, _ = utilities.get_location()
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
    datetime_now = datetime.datetime.now()
    local_time = _local_time(datetime_now, location_info)
    sun_info = sun(location_info.observer, date=datetime_now, tzinfo=location_info.timezone)
    return _theme_for_time(local_time, sun_info['sunrise'], sun_info['sunset'])


def _theme_for_time(current_time: datetime.datetime, sunrise: datetime.datetime, sunset: datetime.datetime) -> str:
    if sunrise < current_time < sunset:
        theme = 'light'
    else:
        theme = 'dark'
    return theme


def _local_time(datetime_now: datetime.datetime, location_info) -> datetime.datetime:
    tz_loc = pytz.timezone(location_info.timezone)
    return tz_loc.localize(datetime_now)


def _location_info_from_location(location: str):
    location_info = None
    geolocator = Nominatim(user_agent='Picochess')
    loc = geolocator.geocode(location)
    if loc is not None:
        tf = timezonefinder.TimezoneFinder()
        timezone_str = tf.certain_timezone_at(lat=loc.latitude, lng=loc.longitude)
        if timezone_str is not None:
            location_info = LocationInfo(location, '', timezone_str, loc.latitude, loc.longitude)
    return location_info
