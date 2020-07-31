import collections
import datetime
import re
import serial
import time


Setup = collections.namedtuple(
    'Setup', 'main_model expansion_model firmware_version',
    defaults=(None,) * 3)

Config = collections.namedtuple(
    'Config',
    'start_freq freq_step amp_top amp_bottom sweep_points '
    'exp_module_active current_mode min_freq max_freq max_span rbw '
    'amp_offset calculator_mode',
    defaults=(None,) * 13)

Sweep = collections.namedtuple('Sweep', 'datetime frequency_dbm')


OK_BAUDS = [500000, 1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200]
GOOD_BAUDS = [500000, 2400]

class Communicator:
    def __init__(self, port, baud=500000, debug=False):
        self._debug = debug
        self._buffer = bytes()

        self.serial_number = None
        self.current_setup = None
        self.current_config = None
        self.screen_data = None
        self.tracking_status = None
        self.sweeps = []

        try:
            self._serial = serial.Serial(
                port=port, baudrate=baud, timeout=0.0, write_timeout=0.1)
            self._serial.reset_input_buffer()
        except OSError:
            raise OSError(f'Error opening {port}')

    def send_request_config(self):
        self._send_command('C0')

    def send_request_shutdown(self):
        self._send_command('S')

    def send_request_hold(self):
        self._send_command('CH')

    def send_request_reboot(self):
        self._send_command('r')

    def send_change_baudrate(self, baud):
        self._send_command(f'c{OK_BAUDS.index(baud)}')
        self._serial.baudrate = baud

    def send_lcd_enable(self, enable):
        self._send_command(f'L{"1" if enable else "0"}')

    def send_dump_screen_enable(self, enable):
        self._send_command(f'D{"1" if enable else "0"}')

    def send_request_sn(self):
        self._send_command('Cn')

    def _send_command(self, text):
        dprint = print if self._debug else lambda *x, **k: None
        data = text.encode('ascii')
        if len(data) + 2 >= 255:
            raise ValueError(f'RFE command too long "{text}"')
        data = b'#' + bytes([len(data) + 2]) + data + b'\r\n'
        self._serial.write(data)
        dprint(f'==> {data}')

    def poll(self):
        try:
            data = self._serial.read(self._serial.in_waiting)
        except OSError: 
            raise OSError(f'Error reading {self._serial.name}')

        if not data:
            return False
        else:
            old_buffer = self._buffer
            self._buffer += data
            self._consume_buffer()
            return (self._buffer != old_buffer)

    # TODO: Handle "DSP"?
    _header_re = re.compile(
        b'(\\$C...|\\$D|\\$q.|\\$Q..|\\$[Ss].|\\$z..|#.*?\r\n)')

    def _consume_buffer(self):
        dprint = print if self._debug else lambda *x, **k: None
        m = self._header_re.search(self._buffer)
        if not m:
            return

        if m.start() > 0:
            dprint(f'*** Skipped RFE data {self._buffer[0:m.start()]}')
            self._buffer = self._buffer[m.start():]
            return

        data = m.group(1)
        after = self._buffer[m.end():]
        if data.startswith(b'$D'):
            body = self._take_body(after, 128 * 8)
            if body:
                self.screen_data = body
                dprint('<== screen dump')

        elif data.startswith(b'$S'):
            body = self._take_body(after, data[2])
            self._maybe_add_sweep(body)

        elif data.startswith(b'$s'):
            body = self._take_body(after, (data[2] or 256) * 16)
            self._maybe_add_sweep(body)

        elif data.startswith(b'$z'):
            body = self._take_body(after, data[2] * 256 + data[3])
            self._maybe_add_sweep(body)

        elif data.startswith(b'#'):
            text = data[1:].strip().decode('ascii', errors='replace')
            self._buffer = after
            if text.startswith('Sn'):
                self.serial_number = text[2:]
                dprint(f'<== S/N {self.serial_number}')
            elif text.startswith('C2-M:'):
                self.current_setup = Setup(*text[5:].split(',', 2))
                dprint(f'<== {self.current_setup}')
            elif text.startswith('C2-F:'):
                try:
                    config = Config(*[int(p) for p in text[5:].split(',', 12)])
                except ValueError:
                    dprint(f'*** Bad RFE config "{text}"')
                self.current_config = config._replace(
                    start_freq=config.start_freq * 1000,
                    min_freq=config.min_freq * 1000,
                    max_freq=config.max_freq * 1000,
                    max_span=config.max_span * 1000,
                    rbw=config.rbw * 1000 if config.rbw else None)
                dprint(f'<== {self.current_config}')
            elif text.startswith('K'):
                if text[1:] in ('0', '1'):
                    self.tracking_status = bool(int(text))
                    dprint(f'<== tracking status {self.tracking_status}')
                else:
                    dprint(f'*** Bad RFE tracking status "{text}"')
            else:
                dprint(f'*** Unknown RFE text "{text}"')

        else:
            raise AssertionError(f'Matched but unhandled RFE data {data}')


    def _take_body(self, next, size):
        dprint = print if self._debug else lambda *x, **k: None
        if len(next) <= size + 2:
            return None  # Not enough data yet.
        elif next[size:size + 2] != b'\r\n':
            dprint(f'*** Unterminated RFE data {self._buffer}')
            self._buffer = next
            return None  # Assume data is bogus.
        else:
            self._buffer = next[size + 2:]  # After b'\r\n'.
            return next[:size]


    def _maybe_add_sweep(self, data):
        dprint = print if self._debug else lambda *x, **k: None
        cc = self.current_config
        if data is None or cc is None:
            return

        points = cc.sweep_points
        if len(data) != points:
            dprint(f'*** RFE sweep size={len(data)} != config={points}')
            return

        self.sweeps.append(Sweep(
            datetime=datetime.datetime.now(),
            frequency_dbm=dict(zip(
                (cc.start_freq + cc.freq_step * p for p in range(points)),
                (cc.amp_offset - 0.5 * b for b in data)))))

        dprint(f'<== {self.sweeps[-1]}')
