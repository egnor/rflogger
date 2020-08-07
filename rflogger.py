#!/usr/bin/env python3

import argparse
import csv
import datetime
import rfexplorer
import signal
import sys
import time


def main():
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', default='/dev/ttyUSB0')
    parser.add_argument('--baud', type=int, default=500000)
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--output_log', required=True)
    parser.add_argument('--run_seconds', type=float)
    args = parser.parse_args()

    print(f'=== Opening "{args.output_log}" ...')
    with open(args.output_log, 'w', newline='') as log_file:
        csv_writer = csv.writer(log_file)
        header_freqs = None
        finish_time = None

        print(f'=== Connecting to "{args.port}" ...')
        explorer = rfexplorer.Communicator(
            port=args.port, baud=args.baud, debug=args.debug)
        explorer.send_request_config()

        sweeps = 0
        next_status_time = datetime.datetime.min
        print(f'=== Receiving data...')
        while True:
            now = datetime.datetime.now()
            if now > next_status_time:
                next_status_time = now + datetime.timedelta(seconds=1)
                log_file.flush()
                if explorer.current_config is None:
                    print(f'{now.strftime("%m-%d %H:%M:%S")} - starting...')
                else:
                    cc = explorer.current_config
                    np = cc.sweep_points
                    f0 = 1e-6 * cc.start_freq
                    f1 = 1e-6 * (cc.start_freq + cc.freq_step * (np - 1))
                    print(f'{now.strftime("%m-%d %H:%M:%S")} - {sweeps:4d}x '
                          f'({f0:.3f}mHz - {f1:.3f}mHz / {np} points)')

            if finish_time is not None and now > finish_time:
                print(f'{now.strftime("%m-%d %H:%M:%S")} - finished run')
                break

            if not explorer.poll():
                time.sleep(0.01)
                continue

            for s in explorer.sweeps:
                freqs = list(s.frequency_dbm.keys())
                if not header_freqs:
                    header_freqs = freqs
                    csv_writer.writerow(['Timestamp'] + freqs)
                    if args.run_seconds:
                        delta = datetime.timedelta(seconds=args.run_seconds)
                        finish_time = s.datetime + delta
                        print(f'{s.datetime.strftime("%m-%d %H:%M:%S")} - ' +
                              f'run to {finish_time.strftime("%H:%M:%S")} '
                              f'({args.run_seconds:+.1f}s)')
                elif header_freqs != freqs:
                    print(f'*** Change from {header_freqs} to {freqs}')
                    sys.exit(1)

                sweeps += 1
                csv_writer.writerow([s.datetime.astimezone().isoformat()] +
                                    list(s.frequency_dbm.values()))

            explorer.sweeps = []


if __name__ == '__main__':
    main()
