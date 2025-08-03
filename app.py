from flask import Flask, render_template, request, send_from_directory

import tides

app = Flask(__name__)


@app.route("/")
def index():
    context = {
        "tide_type": tides.TideType,
        "hours_filter": tides.HoursFilter,
        "day_filter": tides.DayFilter,
    }
    return render_template("index.j2", **context)


@app.route("/api/tides")
def _tides():
    args = dict(request.args)
    return {"tides": tides.find_tides(**args)}
