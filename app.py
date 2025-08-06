from flask import Flask, render_template, request

import tides

app = Flask(__name__)


@app.route("/")
def index():
    selected = {
        **{
            "station": request.args.get("station", "9447130"),
            "year": request.args.get("year", str(tides.CURRENT_YEAR)),
            "tide_type": request.args.get("tide_type", tides.TideType.LOW.value),
            "prediction_limit": request.args.get("prediction_limit", "0.0"),
            "day_filter": request.args.get("day_filter", tides.DayFilter.ANY.value),
            "hours_filter": request.args.get(
                "hours_filter", tides.HoursFilter.DAY.value
            ),
        },
        **request.args,
    }

    context = {
        "stations": tides.get_stations(),
        "tide_type": tides.TideType,
        "hours_filter": tides.HoursFilter,
        "day_filter": tides.DayFilter,
        "selected": selected,
    }
    return render_template("index.j2", **context)


@app.route("/api/tides")
def _tides():
    args = dict(request.args)
    return tides.find_tides(**args)
