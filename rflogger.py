#!/usr/bin/env python3

import argparse
import csv
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
    parser.add_argument('--out_file', required=True)
    args = parser.parse_args()

    print(f'=== Opening "{args.out_file}" ...')
    with open(args.out_file, 'w', newline='') as out_file:
        csv_writer = csv.writer(out_file)
        header_freqs = None

        print(f'=== Connecting to "{args.port}" ...')
        explorer = rfexplorer.Communicator(
            port=args.port, baud=args.baud, debug=args.debug)
        explorer.send_request_config()

        sweeps = 0
        last_status_time = 0
        print(f'=== Receiving data...')
        while True:
            now = time.time()
            if now > last_status_time + 1:
                last_status_time = now
                out_file.flush()
                if explorer.current_config is None:
                    print(f'{time.strftime("%m-%d %H:%M:%S")} - starting...')
                else:
                    cc = explorer.current_config
                    np = cc.sweep_points
                    f0 = 1e-6 * cc.start_freq
                    f1 = 1e-6 * (cc.start_freq + cc.freq_step * (np - 1))
                    print(f'{time.strftime("%m-%d %H:%M:%S")} - {sweeps:4d}x '
                          f'({f0:.3f}mHz - {f1:.3f}mHz / {np} points)')

            if not explorer.poll():
                time.sleep(0.01)
                continue

            for s in explorer.sweeps:
                freqs = list(s.frequency_dbm.keys())
                if not header_freqs:
                    csv_writer.writerow(['Timestamp'] + freqs)
                    header_freqs = freqs
                elif header_freqs != freqs:
                    print(f'*** Change from {header_freqs} to {freqs}')
                    sys.exit(1)

                sweeps += 1
                csv_writer.writerow([s.datetime.astimezone().isoformat()] +
                                    list(s.frequency_dbm.values()))

            explorer.sweeps = []


if __name__ == '__main__':
    main()
