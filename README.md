
# tide-calender

Display a daylight low tide calendar for NOAA's National Ocean Service stations.

It's running here: https://tides.codefork.com

## How to Run

```
docker build -t tide-calendar .
docker run -d --restart always -p 127.0.0.1:8000:8000 -v "$(pwd)/cache:/opt/tide-calendar/cache" tide-calendar
```

## References

Washington Department of Fish and Wildlife publishes a chart that's similar to what this project does:
https://wdfw.wa.gov/sites/default/files/fishing/shellfishing/WDFWBestClamOysterHarvestTides.pdf
