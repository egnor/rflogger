#!/usr/bin/env python3

import argparse
import collections
import datetime
import signal
import sys

import matplotlib.cm
import matplotlib.dates
import matplotlib.figure
import matplotlib.ticker
import pandas


signal.signal(signal.SIGINT, signal.SIG_DFL)
parser = argparse.ArgumentParser()
parser.add_argument('--input_log', required=True)
parser.add_argument('--save_slice')
parser.add_argument('--out_file')
parser.add_argument('--width', type=int, default=8)
parser.add_argument('--height', type=int, default=16)
parser.add_argument('--dpi', type=int, default=100)
parser.add_argument(
    '--start', type=pandas.Timestamp, default=pandas.Timestamp(2000, 1, 1))
parser.add_argument(
    '--end', type=pandas.Timestamp, default=pandas.Timestamp(2100, 1, 1))
parser.add_argument(
    '--duration', type=pandas.Timedelta, default=pandas.Timedelta(weeks=10400))

args = parser.parse_args()
local_tz = datetime.datetime.now().astimezone().tzinfo
start_time = args.start.tz_localize(local_tz)
end_time = start_time + min(args.duration, args.end - args.start)

print(f'Opening "{args.input_log}" ...')
reader = pandas.read_csv(
    args.input_log, index_col='Timestamp', parse_dates=True,
    infer_datetime_format=True, dtype=float,
    chunksize=10000)

slice_chunks = []
for chunk in reader:
    if chunk.index[-1] < start_time:
        print(f'Skip {chunk.index[0]} - {chunk.index[-1]}')
        continue

    if chunk.index[0] >= end_time:
        print(f'Done {chunk.index[0]} - {chunk.index[-1]} ...')
        break

    slice = chunk.loc[start_time:end_time]
    if len(slice):
        print(f'Load {slice.index[0]} - {slice.index[-1]}')
        slice_chunks.append(slice)

data = pandas.concat(slice_chunks)
if args.save_slice:
    print(f'Writing "{args.save_slice}" ...')
    data.to_csv(args.save_slice)

print('Generating plot...')
figure = matplotlib.figure.Figure(
    figsize=(args.width, args.height), tight_layout=True)

axes = figure.add_subplot()

axes.set_xlabel('MHz')
mhz = data.columns.to_series().astype(int) / 1e6
mhz_step = (mhz[-1] - mhz[0]) / max(1, len(mhz) - 1)
mhz_corners = (mhz - mhz_step / 2).append(mhz[-1:] + mhz_step / 2)

axes.set_ylabel('Timestamp')
axes.invert_yaxis()
stamp = data.index.to_series()
stamp_step = (stamp[-1] - stamp[0]) / max(1, len(stamp) - 1)
stamp_corners = (stamp - stamp_step / 2).append(stamp[-1:] + stamp_step / 2)

m = axes.pcolormesh(
    mhz_corners, stamp_corners, data.to_numpy(),
    vmin=-90, vmax=-20, cmap=matplotlib.cm.hot)
figure.colorbar(m, ax=axes, label='dBm', use_gridspec=True, fraction=0.05)

out_file = args.out_file or (
    (args.save_slice or args.input_log).replace('.csv', '') + '.png')
print(f'Writing "{out_file}" ...')
figure.savefig(out_file, dpi=args.dpi)
