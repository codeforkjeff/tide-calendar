import csv
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import auto, StrEnum
import os.path
import re
from typing import Any, Dict, List
import urllib.request

from bs4 import BeautifulSoup
from bs4.element import Tag
import pytz

ONE_HOUR = 60 * 60
DATE_FORMAT = "%Y/%m/%d"
CACHE_DIR = "cache"
CURRENT_YEAR = datetime.now().year


@dataclass
class Station:
    name: str
    state: str
    nos_id: str
    nws_id: str
    latitude: Decimal
    longitude: Decimal


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
    ANYTIME = auto()


@dataclass
class Daylight:
    sunrise: int
    sunset: int


@dataclass
class DaylightInfo:
    daylight: Dict[str, Daylight]
    tz: Any


@dataclass
class Tide:
    date: str
    tide_type: TideType
    # timestamp
    tide: int
    prediction: float
    daylight: Daylight


def retrieve_url_and_cache(url: str, path: str):
    """
    if path doesn't exist, fetches the url and writes the response to path.
    """
    if not os.path.exists(path):
        with urllib.request.urlopen(url) as f:
            with open(path, "w") as output:
                contents = f.read().decode("utf-8")
                output.write(contents)


def get_tides(station: Station, year: int) -> List[List[str]]:
    """
    Fetches tide data from NOAA for a given year
    """
    # stnid is the monitoring station id (9447130 = Seattle)
    url = f"https://tidesandcurrents.noaa.gov/cgi-bin/predictiondownload.cgi?&stnid={station.nos_id}&threshold=&thresholdDirection=greaterThan&bdate={year}&timezone=LST/LDT&datum=MLLW&clock=24hour&type=txt&annual=true"

    cached_file = f"{CACHE_DIR}/{year}_{station.nos_id}_tides.txt"
    retrieve_url_and_cache(url, cached_file)

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


def get_daylight(station: Station, year: int) -> DaylightInfo:
    """
    Fetches daylight information from NOAA
    """
    url = f"https://gml.noaa.gov/grad/solcalc/table.php?lat={station.latitude}&lon={station.longitude}&year={year}"

    def format(lat_or_lng):
        return str(lat_or_lng).replace(".", "_").replace("-", "neg")

    lat_lng = f"{format(station.latitude)}_{format(station.longitude)}"

    cached_file = f"{CACHE_DIR}/{year}_{lat_lng}_daylight.html"
    retrieve_url_and_cache(url, cached_file)

    times = {}

    with open(cached_file, "r") as f:
        soup = BeautifulSoup(f.read(), features="html.parser")

        tz_element = soup.find_all(
            lambda tag: "Time Zone Offset" in (tag.string or "")
        )[0]
        tz_str = re.findall(r"Time Zone Offset: ([\w/]+)", tz_element.string)[0]
        tz = pytz.timezone(tz_str)

        tables = soup.find_all("table")
        sunrise = parse_table(tables[0], year, tz)
        sunset = parse_table(tables[1], year, tz)

        for date in sunrise.keys():
            times[date] = Daylight(
                int(sunrise[date].timestamp()), int(sunset[date].timestamp())
            )

    return DaylightInfo(times, tz)


def get_stations() -> List[Station]:
    url = f"https://access.co-ops.nos.noaa.gov/nwsproducts.html"

    cached_file = f"{CACHE_DIR}/stations.html"
    retrieve_url_and_cache(url, cached_file)

    stations = []

    with open(cached_file, "r") as f:
        soup = BeautifulSoup(f.read(), features="html.parser")
        tables = soup.css.select("#NWSTable")
        rows = tables[0].find_all("tr")
        for row in rows:
            cols = row.find_all("td")
            if len(cols) == 6:
                nos_id, nws_id, latitude, longitude, state, station_name = [
                    e.string.strip() for e in row.find_all("td")
                ]
                stations.append(
                    Station(
                        name=station_name,
                        state=state,
                        nos_id=nos_id,
                        nws_id=nws_id,
                        latitude=Decimal(latitude),
                        longitude=Decimal(longitude),
                    )
                )

    stations = sorted(stations, key=lambda station: f"{station.state}, {station.name}")

    return stations


def find_tides(
    station: str | Station = "9447130",
    year: str | int = CURRENT_YEAR,
    tide_type: str | TideType = TideType.LOW,
    prediction_limit: str | float = 0.0,
    day_filter: str | DayFilter = DayFilter.ANY,
    hours_filter: str | HoursFilter = HoursFilter.DAY,
) -> Dict:
    """
    Return a list of filtered tides based on passed-in arguments.
    """
    stations = get_stations()

    if isinstance(station, str):
        station = [s for s in stations if s.nos_id == station][0]

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
            case HoursFilter.ANYTIME:
                return True

    if isinstance(year, str):
        year = int(year)

    daylight_info = get_daylight(station, year)
    tz = daylight_info.tz

    tides = []

    for row in get_tides(station, year):
        (date, dow, time, pred_, _, _, _, _, hl) = row
        pred = float(pred_)
        year, month, day_of_month = [int(part) for part in date.split("/")]
        hour, minute = [int(part) for part in time.split(":")]

        # sanity check parsing
        assert hl in ["H", "L"]

        dt_obj = tz.localize(datetime(year, month, day_of_month, hour, minute))
        daylight_obj = daylight_info.daylight[date]

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

    return {"tides": tides, "tz": tz.zone}


if __name__ == "__main__":
    # for tide in find_tides()["tides"]:
    #     print(tide)
    print(get_stations())
