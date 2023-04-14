import os
import os.path as op
import sys
import numpy as np
import scipy.interpolate as spi
import json
import requests
import datetime as dt
import pytz
import math

import secr
import plotter

one_day = dt.timedelta(days = 1)
one_hour = dt.timedelta(hours = 1)

root = op.join(sys.path[0], '..')
cached_data_file = op.join(root, 'cached_response.json')

# Returns a list of timestamps, one per hour, covering the interval
def parse_duration(s):
    d, p = s.split('/P')
    d = dt.datetime.fromisoformat(d)
    # d should be UTC
    if 'T' in p:
        pd, ph = p.split('T')
        assert ph[-1] == 'H'
        hours = int(ph[:-1])
    else:
        pd = p
        hours = 0
    if len(pd) > 0:
        assert pd[-1] == 'D'
        hours += 24 * int(pd[:-1])
    assert hours >= 1
    assert hours <= 24 * 30

    ts = []
    for i in range(hours):
        ts.append(int(((d + (i * one_hour)).timestamp()) + 0.5))
    return ts

class Location:
    # url_base = 'https://api.darksky.net/forecast/{}/{},{}'
    # options = {
            # 'units' : 'si',
            # 'extend' : 'hourly',
            # 'exclude' : 'minutely,daily,flags,alerts'
            # }
    # options = {
                # 'units' : 'si'
            # }
    # options = {}
    # url_base = 'https://api.weather.gov/gridpoints/{}/{},{}/forecast/hourly'
    # url_base = 'https://api.weather.gov/gridpoints/{}/{},{}'

    def __init__(self, name, localtime):
        self.name = name
        # self.grid_id = grid_id
        # self.grid_x = grid_x
        # self.grid_y = grid_y
        self.localtime = localtime
        # self.url = self.url_base.format(secret.apikey, self.lat, self.lon)
        # self.url = self.url_base.format(self.grid_id, self.grid_x, self.grid_y)
        self.history_dir = op.join(root, self.name, 'history')
        self.full_history_dir = op.join(root, self.name, 'history_full')

    def request_data(self):
        response = requests.get(secr.weather_url)
        if response.status_code == requests.codes.ok:
            j = response.json()

            return WeatherData.from_raw_json(j)

loc = Location(secr.location_name, secr.localtime)

def get_now():
    return dt.datetime.now(tz = pytz.utc)

class WeatherData:
    def __init__(self):
        self.raw = None
        self.current = None
        self.series = {}

    def from_darksky_response(j):
        wd = WeatherData()
        wd.raw = j
        if 'currently' in j:
            wd.set_current(DataPoint(j['currently']))
        if 'hourly' in j:
            if 'data' in j['hourly']:
                for d in j['hourly']['data']:
                    wd.add_data_point(DataPoint(d))
        return wd

    def from_raw_json(j):
        wd = WeatherData()
        wd.raw = j
        wd.current = j['current_weather']

        wd.series['time'] = np.array(j['hourly']['time'], dtype = int)
        for name in ['temperature_2m', 'precipitation_probability', 'precipitation']:
            wd.series[name] = np.array(j['hourly'][name], dtype = float)

        for i, t in enumerate(wd.series['time']):
            if t > wd.current['time']:
                pre = wd.series['precipitation'][i]
                wd.current['precipitation'] = pre
                if pre > 0.01:
                    wd.current['precipitation_probability'] = 100
                else:
                    wd.current['precipitation_probability'] = 0
                break

        return wd

        # j = j.get('properties', {})
        # # C, %, mm / hour
        # properties = ['temperature', 'probabilityOfPrecipitation', 'quantitativePrecipitation']
        # # t -> prop -> value
        # abbr = {}
        # for p in properties:
            # for v in j[p]['values']:
                # ts = parse_duration(v['validTime'])
                # value = v['value']
                # for t in ts:
                    # if not (t in abbr):
                        # abbr[t] = {}
                    # abbr[t][p] = value
# 
        # wd.raw_abbr = abbr
# 
        # for t in abbr:
            # wd.add_data_point(DataPoint(t, abbr[t]))
        # wd.set_current(wd.data[wd.times()[0]])

    # def from_shorter_json(j):
        # wd = WeatherData()
        # wd.raw = None
        # wd.raw_abbr = j
        # for t in j:
            # wd.add_data_point(DataPoint(t, j[t]))
        # wd.set_current(wd.data[wd.times()[0]])
# 
        # return wd

    def from_cache():
        with open(cached_data_file, 'r') as f:
            return WeatherData.from_raw_json(json.load(f))

    def save_in_cache(self):
        if self.raw is not None:
            with open(cached_data_file, 'w') as f:
                json.dump(self.raw, f, indent = 2)

            fn = op.join(loc.full_history_dir, str(self.current['time']))
            with open(fn, 'w') as f:
                json.dump(self.raw, f)

            fn = op.join(loc.history_dir, str(self.current['time']))
            with open(fn, 'w') as f:
                json.dump(self.current, f)

    def load_history(self):
        return None

        now = get_now()
        thresh = (now - 2 * one_day).timestamp()

        for fn in os.listdir(loc.history_dir):
            t = 0
            try:
                t = int(fn)
            except:
                continue

            if t > thresh:
                with open(op.join(loc.history_dir, fn), 'r') as f:
                    j = json.load(f)
                    self.add_data_point(DataPoint.from_json(j))

    def make_plot(self, filename, fahrenheit = False, legend = True):
        dt_now = get_now()
        dt_now_local = dt_now.astimezone(loc.localtime)
        dt_today = dt_now_local.replace(hour = 0, minute = 0, second = 0, microsecond = 0)
        today = dt_today.timestamp()

        days_of_week = ['M', 'T', 'W', '\u00DE', 'F', 'S', 'U']

        #### Process data ####

        # Given a timestamp, return days after the most recent midnight
        def to_day(t):
            return (t - today) / one_day.total_seconds()
            # if type(t) is int:
                # t = dt.datetime.fromtimestamp(t, tz = pytz.utc)
            # return (t - dt_today).total_seconds() / one_day.total_seconds()

        ts = self.series['time']
        temp = self.series['temperature_2m']
        rain_prob = self.series['precipitation_probability']
        rain_rate = self.series['precipitation']
        day = to_day(ts)

        if fahrenheit:
            temp = temp * (9 / 5) + 32

        day_smooth = np.linspace(np.min(day), np.max(day), 2000)
        temp_smooth = spi.PchipInterpolator(day, temp)(day_smooth)
        rain_prob_smooth = spi.PchipInterpolator(day, rain_prob)(day_smooth)

        day_low = -1
        day_high = 7
        if dt_now_local.hour < 20:
            day_zoom = 0
        else:
            day_zoom = 1

        temp_low = float(np.min(temp)) - 5
        temp_high = float(np.max(temp)) + 5

        if temp_low > ((temp_low // 10) * 10) + 8.8:
            temp_low = ((temp_low // 10) * 10) + 8.8

        tens = [10 * i for i in range(math.floor(temp_low / 10), math.floor(temp_high / 10) + 1)]

        # Returns all intervals in which the forecast rain is above the specified threshold
        # int_thresh is in mm / hour
        # prob_thresh is in [0, 1]
        def intervals_above(rate_thresh, prob_thresh):
            intervals = []
            start = None
            for i, t in enumerate(day):
                if rain_rate[i] > rate_thresh and rain_prob[i] > prob_thresh:
                    if start is None:
                        start = t
                else:
                    if start is not None:
                        intervals.append((start, t))
                        start = None

            if start is not None:
                intervals.append((start, day[-1] + (1 / 24)))

            return intervals

        r1 = intervals_above(0.3, 0.1)
        r2 = intervals_above(1, 0.1)
        r3 = intervals_above(2, 0.1)
        r4 = intervals_above(3, 0.1)

        cur_temp = self.current['temperature']
        if fahrenheit:
            cur_temp = cur_temp * (9 / 5) + 32
        dt_updated = dt.datetime.fromtimestamp(self.current['time'], tz = pytz.utc).astimezone(loc.localtime)

        ### Plot ####

        p = plotter.Plotter()
        p.set_x_transform(p.mk_transform_2lin(-1, day_zoom, day_zoom + 1, 7, 0.5))
        p.set_y_transform(p.mk_transform_lin(temp_low, temp_high))

        for i in range(day_low, day_high, 1):
            dt_day = dt_today + i * one_day
            if i == day_low:
                ls = ' '
            else:
                ls = '--'
            w = days_of_week[dt_day.weekday()]
            p.vline(to_day(dt_day.timestamp()), linestyle = ls)(w, fontsize = 12)

        p.vline(day_zoom + 0.25, linestyle = ':', color = 'grey')('6am', fontsize = 8)
        p.vline(day_zoom + 0.5 , linestyle = ':', color = 'grey')('noon', fontsize = 8)
        p.vline(day_zoom + 0.75, linestyle = ':', color = 'grey')('6pm', fontsize = 8)
        p.vline(to_day(self.current['time']), linestyle = '-', linewidth = 1, color = 'blue')

        for t in tens:
            p.hline(t, linestyle = '-')(str(t), fontsize = 12)
            for i in [2, 4, 6, 8]:
                if t + i > temp_high:
                    break
                p.hline(t + i, linestyle = ':', color = 'grey', x = [day_zoom, day_zoom + 1])

        p.plot(day_smooth, temp_smooth, color = 'red', linewidth = 2, zorder = 5)

        if legend:
            l_temp = '{:.1f}'.format(cur_temp)
            l_asof = 'as of {}.{:02d}'.format((dt_updated.hour + 11 ) % 12 + 1, dt_updated.minute)
            if dt_updated.hour < 12:
                l_asof += 'am'
            else:
                l_asof += 'pm'
            p.legend([l_temp, l_asof], [36, 10])

        p.set_y_transform(p.mk_transform_lin(-1, 9))

        for a, b in r1 + r2 + r3 + r4:
            p.box(a, b, 0, 1, color = 'blue', alpha = 0.2)

        for a, b in r1:
            idx = ((day_smooth >= a) & (day_smooth <= b))
            p.plot(day_smooth[idx], rain_prob_smooth[idx], color = 'black', linewidth = 1, zorder = 4)

        p.save(filename)

def main():
    args = sys.argv
    if len(args) == 1:
        data = loc.request_data()
        data.save_in_cache()
    elif len(args) == 2 and args[1] == 'cached':
        data = WeatherData.from_cache()
    else:
        print("Didn't understand arguments", args)
        return

    # data.load_history()
    data.make_plot(filename = op.join(root, loc.name, 'forecast.png'))
    data.make_plot(filename = op.join(root, loc.name, 'forecast_f.png'), fahrenheit = True)

if __name__ == "__main__":
    main()
