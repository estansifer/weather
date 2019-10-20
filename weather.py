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

import secret
import plotter

one_day = dt.timedelta(days = 1)

root = op.join(sys.path[0], '..')
cached_data_file = op.join(root, 'cached_response.json')

class Location:
    url_base = 'https://api.darksky.net/forecast/{}/{},{}'
    options = {
            'units' : 'si',
            'extend' : 'hourly',
            'exclude' : 'minutely,daily,flags,alerts'
            }

    def __init__(self, name, lat, lon, localtime):
        self.name = name
        self.lat = lat
        self.lon = lon
        self.localtime = localtime
        self.url = self.url_base.format(secret.apikey, self.lat, self.lon)
        self.history_dir = op.join(root, self.name, 'history')
        self.full_history_dir = op.join(root, self.name, 'history_full')

    def request_data():
        response = requests.get(self.url, params = self.options)
        if response.status_code == requests.codes.ok:
            j = response.json()

            t = j.get('currently', {}).get('time')
            if type(t) is int:
                with open(op.join(self.history_dir, str(t)), 'w') as f:
                    json.dump(j['currently'], f)

            return WeatherData.from_darksky_response(response.json())

loc = Location(secret.location_name, secret.lat, secret.lon, secret.localtime)

def get_now():
    return dt.datetime.now(tz = pytz.utc)

class DataPoint:
    def __init__(self, j):
        self.temp = j.get('temperature')
        self.app_temp = j.get('apparentTemperature')
        self.precip_prob = j.get('precipProbability', 0)
        self.precip_int = j.get('precipIntensity', 0)
        self.humidity = j.get('humidity')

        self.time = dt.datetime.fromtimestamp(j['time'], tz = pytz.utc)

class WeatherData:
    def __init__(self):
        self.raw = None
        self.current = None
        self.data = {}

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

    def from_cache():
        with open(cached_data_file, 'r') as f:
            return WeatherData.from_darksky_response(json.load(f))

    def save_in_cache(self):
        if self.raw is not None:
            with open(cached_data_file, 'w') as f:
                json.dump(self.raw, f, indent = 2)
            fn = op.join(loc.full_history_dir, str(self.raw['currently']['time']))
            with open(fn, 'w') as f:
                json.dump(self.raw, f)

    def load_history(self):
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
                    self.add_data_point(DataPoint(j))

    def set_current(self, current):
        self.current = current
        self.add_data_point(current)

    def add_data_point(self, d):
        self.data[d.time] = d

    def times(self):
        return sorted(self.data.keys())

    def make_plot(self, filename, fahrenheit = False, legend = True):
        now = get_now()
        now_local = now.astimezone(loc.localtime)
        today = now_local.replace(hour = 0, minute = 0, second = 0, microsecond = 0)

        days_of_week = ['M', 'T', 'W', '\u00DE', 'F', 'S', 'U']

        #### Process data ####

        # Given a datetime object, return days after the most recent midnight
        def to_day(t):
            return (t - today).total_seconds() / one_day.total_seconds()

        day = []
        temp = []
        rain_prob = []
        for key in self.times():
            day.append(to_day(key))
            temp.append(self.data[key].temp)
            rain_prob.append(self.data[key].precip_prob)
        day = np.array(day)
        temp = np.array(temp)
        rain_prob = np.array(rain_prob)

        if fahrenheit:
            temp = temp * (9 / 5) + 32

        day_smooth = np.linspace(np.min(day), np.max(day), 2000)
        temp_smooth = spi.PchipInterpolator(day, temp)(day_smooth)
        rain_prob_smooth = spi.PchipInterpolator(day, rain_prob)(day_smooth)

        day_low = -1
        day_high = 7
        if now_local.hour < 20:
            day_zoom = 0
        else:
            day_zoom = 1

        midnights = [today + i * one_day for i in range(day_low, day_high, 1)]

        temp_low = float(np.min(temp)) - 5
        temp_high = float(np.max(temp)) + 5

        if temp_low > ((temp_low // 10) * 10) + 8.8:
            temp_low = ((temp_low // 10) * 10) + 8.8

        tens = [10 * i for i in range(math.floor(temp_low / 10), math.floor(temp_high / 10) + 1)]

        # Returns all intervals in which the forecast rain is above the specified threshold
        # int_thresh is in mm / hour
        # prob_thresh is in [0, 1]
        def intervals_above(int_thresh, prob_thresh):
            intervals = []
            start = None
            for key in self.times():
                d = self.data[key]
                if d.precip_int > int_thresh and d.precip_prob > prob_thresh:
                    if start is None:
                        start = to_day(key)
                else:
                    if start is not None:
                        intervals.append((start, to_day(key)))
                        start = None

            if start is not None:
                intervals.append((start, to_day(self.times()[-1]) + (1 / 24)))

            return intervals

        r1 = intervals_above(0.3, 0.1)
        r2 = intervals_above(1, 0.1)
        r3 = intervals_above(2, 0.1)
        r4 = intervals_above(3, 0.1)

        cur_temp = self.current.temp
        if fahrenheit:
            cur_temp = cur_temp * (9 / 5) + 32
        updated = self.current.time.astimezone(loc.localtime)

        ### Plot ####

        p = plotter.Plotter()
        p.set_x_transform(p.mk_transform_2lin(-1, day_zoom, day_zoom + 1, 7, 0.5))
        p.set_y_transform(p.mk_transform_lin(temp_low, temp_high))

        for i in range(len(midnights)):
            if i == 0:
                ls = ' '
            else:
                ls = '--'
            w = days_of_week[midnights[i].weekday()]
            p.vline(to_day(midnights[i]), linestyle = ls)(w, fontsize = 12)

        p.vline(day_zoom + 0.25, linestyle = ':', color = 'grey')('6am', fontsize = 8)
        p.vline(day_zoom + 0.5 , linestyle = ':', color = 'grey')('noon', fontsize = 8)
        p.vline(day_zoom + 0.75, linestyle = ':', color = 'grey')('6pm', fontsize = 8)
        p.vline(to_day(updated), linestyle = '-', linewidth = 1, color = 'blue')

        for t in tens:
            p.hline(t, linestyle = '-')(str(t), fontsize = 12)
            for i in [2, 4, 6, 8]:
                if t + i > temp_high:
                    break
                p.hline(t + i, linestyle = ':', color = 'grey', x = [day_zoom, day_zoom + 1])

        p.plot(day_smooth, temp_smooth, color = 'red', linewidth = 2, zorder = 5)

        if legend:
            l_temp = '{:.1f}'.format(cur_temp)
            l_asof = 'as of {}.{:02d}'.format((updated.hour + 11 ) % 12 + 1, updated.minute)
            if updated.hour < 12:
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

    data.load_history()
    data.make_plot(filename = op.join(root, loc.name + '.png'))
    data.make_plot(filename = op.join(root, loc.name + '_f.png'), fahrenheit = True)

if __name__ == "__main__":
    main()
