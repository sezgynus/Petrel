#!/usr/bin/env python3
"""Capture the real curses Kconfig UI in a private PTY (Linux/CI only).

No installed environment is imported and no configuration is applied or saved.
The terminal emulator interprets menuconfig output; Pillow only paints its cells.
"""
import errno
import os
from pathlib import Path
import pty
import select
import signal
import struct
import sys
import tempfile
import time
import fcntl
import termios

import pyte
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
MENUS = ('connections-power', 'encoder-presets', 'buzzer-pwm', 'virtual-buzzer',
         'maintenance-counters', 'display-tools', 'auxiliary-uart', 'nfc', 'apply-options')
COLS, ROWS = 110, 32
PALETTE = dict(black='#101820', red='#d75f5f', green='#5faf87', brown='#af875f',
               blue='#264b70', magenta='#af87af', cyan='#63b7c7', white='#d7dfe7')


def capture(index=None):
    with tempfile.TemporaryDirectory(prefix='petrel-kconfig-') as directory:
        pid, fd = pty.fork()
        if pid == 0:
            fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack('HHHH', ROWS, COLS, 0, 0))
            os.environ.update(TERM='xterm-256color', LANG='C.UTF-8',
                              KCONFIG_CONFIG='example.config', srctree=str(ROOT))
            os.chdir(directory)
            os.execv(sys.executable, [sys.executable, '-c',
                "import kconfiglib, menuconfig; menuconfig.menuconfig(kconfiglib.Kconfig())"])
        screen = pyte.Screen(COLS, ROWS)
        stream = pyte.Stream(screen)
        def drain():
            deadline = time.monotonic() + 5
            received = False
            while time.monotonic() < deadline:
                readable, _, _ = select.select([fd], [], [], .25)
                if not readable:
                    if received:
                        return
                    continue
                try:
                    data = os.read(fd, 65536)
                except OSError as error:
                    if error.errno == errno.EIO:
                        raise RuntimeError('menuconfig exited before capture') from error
                    raise
                if not data:
                    raise RuntimeError('Empty menuconfig capture')
                stream.feed(data.decode('utf-8', errors='replace'))
                received = True
            if not received:
                raise RuntimeError('menuconfig did not draw')
        try:
            drain()
            if index is not None:
                for _ in range(index):
                    os.write(fd, b'\x1bOB')
                    drain()
                os.write(fd, b'\n')
                drain()
            text = '\n'.join(screen.display)
            if 'Petrel' not in text or (index is None and 'NFC' not in text):
                raise RuntimeError('Incomplete menuconfig screen')
            if index is not None:
                expected = ('Connections and power', 'Encoder and presets', 'Buzzer hardware PWM',
                            'Klipper virtual buzzer', 'Maintenance usage counters', 'Display tools',
                            'DWIN auxiliary UART', 'NFC', 'Apply options')[index]
                # Title text must occur, including in the actual submenu breadcrumb.
                if expected not in text or '--->' in next((x for x in screen.display if expected in x), ''):
                    raise RuntimeError('Did not enter submenu: ' + expected)
            return screen
        finally:
            os.kill(pid, signal.SIGTERM)
            os.close(fd)
            os.waitpid(pid, 0)


def render(screen, target):
    font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf', 14)
    cw, ch, margin = 9, 18, 12
    image = Image.new('RGB', (COLS*cw+2*margin, ROWS*ch+2*margin), '#101820')
    draw = ImageDraw.Draw(image)
    def color(value, fallback):
        return PALETTE.get(value, '#' + value if len(value) == 6 else fallback)
    for y in range(ROWS):
        for x in range(COLS):
            cell = screen.buffer[y][x]
            fg, bg = color(cell.fg, '#d7dfe7'), color(cell.bg, '#101820')
            if cell.reverse:
                fg, bg = bg, fg
            left, top = margin+x*cw, margin+y*ch
            draw.rectangle((left, top, left+cw-1, top+ch-1), fill=bg)
            draw.text((left, top), cell.data, font=font, fill=fg)
    image.save(target, optimize=True)


def main():
    target = ROOT / 'docs/assets/configuration'
    target.mkdir(parents=True, exist_ok=True)
    # Render to a staging directory so a failed capture never publishes a subset.
    with tempfile.TemporaryDirectory(prefix='petrel-config-images-') as directory:
        stage = Path(directory)
        for name, index in [('main-menu', None), *[(name, i) for i, name in enumerate(MENUS)]]:
            render(capture(index), stage / (name + '.png'))
        for path in stage.glob('*.png'):
            (target/path.name).write_bytes(path.read_bytes())
    print('Captured real Kconfig main menu and nine submenus; no settings applied.')


if __name__ == '__main__':
    main()
