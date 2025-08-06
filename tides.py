from contextlib import contextmanager
import csv
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import auto, StrEnum
import os.path
from typing import Dict, List
import urllib.request

from bs4 import BeautifulSoup
from bs4.element import Tag
import pytz

ONE_HOUR = 60 * 60
TZ_LOS_ANGELES = pytz.timezone("America/Los_Angeles")
TZ_NEW_YORK = pytz.timezone("America/New_York")
DATE_FORMAT = "%Y/%m/%d"
CACHE_DIR = "cache"


class Place(StrEnum):
    # to find stations, see https://tidesandcurrents.noaa.gov/map/index.html

    SEATTLE = "seattle", "Seattle, WA", 9447130, 47.6, -122.32, TZ_LOS_ANGELES
    CANNON_BEACH = (
        "cannon_beach",
        "Cannon Beach, OR",
        9437585,
        45.89177,
        -123.96153,
        TZ_LOS_ANGELES,
    )
    PROVINCETOWN = (
        "provincetown",
        "Provincetown, MA",
        8446121,
        42.0521329,
        -70.1927079,
        TZ_NEW_YORK,
    )

    def __new__(cls, value, label, station_id, latitude, longitude, tz):
        member = str.__new__(cls, value)
        member._value_ = value
        member.label = label
        member.station_id = station_id
        member.latitude = latitude
        member.longitude = longitude
        member.tz = tz
        return member


class TideType(StrEnum):
    LOW = auto()
    HIGH = auto()

    @classmethod
    def _missing_(cls, value):
        mapped = None
        if value == "L":
            mapped = "low"
        elif value == "H":
            mapped = "high"
        if mapped:
            return cls(mapped)
        return None


class DayFilter(StrEnum):
    ANY = auto()
    WEEKDAY = auto()
    WEEKEND = auto()


class HoursFilter(StrEnum):
    DAY = auto()
    DAY_1 = auto()
    NIGHT = auto()


@dataclass
class Daylight:
    sunrise: int
    sunset: int


@dataclass
class Tide:
    date: str
    tide_type: TideType
    # timestamp
    tide: int
    prediction: float
    daylight: Daylight


def get_tides(place: Place, year: int) -> List[List[str]]:
    """
    Fetches tide data from NOAA for a given year
    """
    # stnid is the monitoring station id (9447130 = Seattle)
    url = f"https://tidesandcurrents.noaa.gov/cgi-bin/predictiondownload.cgi?&stnid={place.station_id}&threshold=&thresholdDirection=greaterThan&bdate={year}&timezone=LST/LDT&datum=MLLW&clock=24hour&type=txt&annual=true"

    cached_file = f"{CACHE_DIR}/{year}_{place.station_id}_tides.txt"
    if not os.path.exists(cached_file):
        with urllib.request.urlopen(url) as f:
            with open(cached_file, "w") as output:
                output.write(f.read().decode("utf-8"))

    with open(cached_file, "r") as f:
        # skip first section including blank line that follows it
        while len(f.readline().strip()) > 0:
            pass

        # skip header
        f.readline()

        # can't use a DictReader, delimiters in the header row are messed up
        reader = csv.reader(f, delimiter="\t")

        return [row for row in reader]


def parse_table(table: Tag, year: int, tz):
    """
    Parse HTML table containing sunrise or sunset times

    Parameters:
    table (Tag): BeautifulSoup tag for HTML table
    year (int): the data's year
    """
    times = {}
    day_of_month = None
    for row in table.find_all("tr"):
        for idx, cell in enumerate(row.find_all("td")):
            text = (cell.string or "").strip()
            if text:
                if idx == 0:
                    day_of_month = int(text)
                else:
                    hour, minute = text.split(":")
                    dt_obj = tz.localize(
                        datetime(year, idx, day_of_month, int(hour), int(minute))
                    )
                    times[dt_obj.strftime(DATE_FORMAT)] = dt_obj
    return times


def get_daylight(place: Place, year: int) -> Dict[str, Daylight]:
    """
    Fetches daylight information from NOAA
    """
    url = f"https://gml.noaa.gov/grad/solcalc/table.php?lat={place.latitude}&lon={place.longitude}&year={year}"

    cached_file = f"{CACHE_DIR}/{year}_{place.value}_daylight.html"
    if not os.path.exists(cached_file):
        with urllib.request.urlopen(url) as f:
            with open(cached_file, "w") as output:
                output.write(f.read().decode("utf-8"))

    times = {}

    with open(cached_file, "r") as f:
        soup = BeautifulSoup(f.read(), features="html.parser")

        tables = soup.find_all("table")
        sunrise = parse_table(tables[0], year, place.tz)
        sunset = parse_table(tables[1], year, place.tz)

        for date in sunrise.keys():
            times[date] = Daylight(
                int(sunrise[date].timestamp()), int(sunset[date].timestamp())
            )

    return times


def find_tides(
    place: str | Place = Place.SEATTLE,
    year: str | int = None,
    tide_type: str | TideType = TideType.LOW,
    prediction_limit: str | float = 0.0,
    day_filter: str | DayFilter = DayFilter.ANY,
    hours_filter: str | HoursFilter = HoursFilter.DAY,
) -> Dict:
    """
    Return a list of filtered tides based on passed-in arguments.
    """

    if isinstance(place, str):
        place = Place(place)

    if isinstance(tide_type, str):
        tide_type = TideType(tide_type)

    if isinstance(prediction_limit, str):
        prediction_limit = float(prediction_limit)

    if isinstance(day_filter, str):
        day_filter = DayFilter(day_filter)

    if isinstance(hours_filter, str):
        hours_filter = HoursFilter(hours_filter)

    def filter_tide_type(value):
        return tide_type.value[0].lower() == value

    def filter_day(date: datetime):
        match (day_filter):
            case DayFilter.ANY:
                return True
            case DayFilter.WEEKDAY:
                return date.weekday() <= 4
            case DayFilter.WEEKEND:
                return date.weekday() >= 5

    def filter_hours(date: datetime, daylight_obj: Daylight):
        date_ts = date.timestamp()
        match (hours_filter):
            case HoursFilter.DAY:
                return (
                    date_ts >= daylight_obj.sunrise and date_ts <= daylight_obj.sunset
                )
            case HoursFilter.DAY_1:
                return date_ts >= (daylight_obj.sunrise - ONE_HOUR) and date_ts <= (
                    daylight_obj.sunset + ONE_HOUR
                )
            case HoursFilter.NIGHT:
                return date_ts < daylight_obj.sunrise or date_ts > daylight_obj.sunset

    if isinstance(year, str):
        year = int(year)
    elif not year:
        year = place.tz.localize(datetime.now()).year

    daylight = get_daylight(place, year)

    tides = []

    for row in get_tides(place, year):
        (date, dow, time, pred_, _, _, _, _, hl) = row
        pred = float(pred_)
        year, month, day_of_month = [int(part) for part in date.split("/")]
        hour, minute = [int(part) for part in time.split(":")]

        # sanity check parsing
        assert hl in ["H", "L"]

        dt_obj = place.tz.localize(datetime(year, month, day_of_month, hour, minute))
        daylight_obj = daylight[date]

        if (
            filter_tide_type(hl.lower())
            and (pred < prediction_limit)
            and filter_day(dt_obj)
            and filter_hours(dt_obj, daylight_obj)
        ):
            tides.append(
                Tide(
                    dt_obj.strftime(DATE_FORMAT),
                    TideType(hl),
                    int(dt_obj.timestamp()),
                    pred,
                    daylight_obj,
                )
            )

    return {"tides": tides, "tz": place.tz.zone}


if __name__ == "__main__":
    for tide in find_tides()["tides"]:
        print(tide)
