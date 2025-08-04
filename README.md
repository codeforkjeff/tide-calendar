
# tide-calender

Display a tide calendar for Seattle and other select places.

It's running here: https://tides.codefork.com

## How to Run

```
docker build -t tide-calendar .
docker run -d --restart always -p 127.0.0.1:8000:8000 -v "$(pwd)/cache:/opt/tide-calendar/cache" tide-calendar
```

## TODO

- handle arbitrary places
- localize dates in JS to place, not the browser's time zone

## References

Washington Department of Fish and Wildlife publishes a chart that's similar to what this project does:
https://wdfw.wa.gov/sites/default/files/fishing/shellfishing/WDFWBestClamOysterHarvestTides.pdf
