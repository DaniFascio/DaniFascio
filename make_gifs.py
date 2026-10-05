"""Export the camera power-on / power-off clips (Gengar waking up / going to sleep) as GIFs.

Pure standard library: draws the same 192x128 black-and-white scene as camera.html,
scales it up and writes animated GIFs with a small LZW encoder.

    python3 make_gifs.py            -> gifs/gengar-wake.gif, gifs/gengar-sleep.gif
"""
import math
import os
import struct

GW, GH = 192, 128
SCALE = 3
FPS = 20
DUR = 2.0
BAYER = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]


def clamp(v, a, b):
    return max(a, min(b, v))


def lerp(a, b, k):
    return a + (b - a) * k


def ease_in_out(k):
    return 4 * k * k * k if k < 0.5 else 1 - (-2 * k + 2) ** 3 / 2


def ease_out_back(k):
    c1 = 1.5
    c3 = c1 + 1
    return 1 + c3 * (k - 1) ** 3 + c1 * (k - 1) ** 2


class Canvas:
    """Single-channel buffer: 1.0 is paper white, 0.0 is ink black."""

    def __init__(self):
        self.buf = [1.0] * (GW * GH)

    def px(self, x, y, v, a=1.0):
        x, y = math.floor(x), math.floor(y)
        if x < 0 or y < 0 or x >= GW or y >= GH:
            return
        o = y * GW + x
        self.buf[o] = self.buf[o] * (1 - a) + v * a

    def rect(self, x, y, w, h, v):
        for j in range(y, y + h):
            for i in range(x, x + w):
                self.px(i, j, v)

    def box(self, x, y, w, h):
        self.rect(x, y, w, h, 0)
        self.rect(x + 2, y + 2, w - 4, h - 4, 1)

    def disc(self, cx, cy, r, v):
        for j in range(math.floor(cy - r), math.floor(cy + r) + 1):
            for i in range(math.floor(cx - r), math.floor(cx + r) + 1):
                if (i + 0.5 - cx) ** 2 + (j + 0.5 - cy) ** 2 <= r * r:
                    self.px(i, j, v)


GLYPH = {
    'G': ['.###.', '#....', '#.###', '#...#', '.###.'], 'O': ['.###.', '#...#', '#...#', '#...#', '.###.'],
    'D': ['####.', '#...#', '#...#', '#...#', '####.'], 'M': ['#...#', '##.##', '#.#.#', '#...#', '#...#'],
    'R': ['####.', '#...#', '####.', '#..#.', '#...#'], 'N': ['#...#', '##..#', '#.#.#', '#..##', '#...#'],
    'I': ['#####', '..#..', '..#..', '..#..', '#####'], 'H': ['#...#', '#...#', '#####', '#...#', '#...#'],
    'T': ['#####', '..#..', '..#..', '..#..', '..#..'], '!': ['..#..', '..#..', '..#..', '.....', '..#..'],
    '.': ['.....', '.....', '.....', '.....', '..#..'], 'Z': ['#####', '...#.', '..#..', '.#...', '#####'],
    ' ': ['.....'] * 5,
}


def text(cv, s, x, y, v, a=1.0, size=2):
    for n, ch in enumerate(s):
        g = GLYPH[ch]
        for j in range(5):
            for i in range(5):
                if g[j][i] == '#':
                    for dy in range(size):
                        for dx in range(size):
                            cv.px(x + (n * 6 + i) * size + dx, y + j * size + dy, v, a)


GG_W, GG_H, GS = 56, 48, 1.25


def tri_in(px, py, a, b, c):
    def s(p1, p2, p3):
        return (p1[0] - p3[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p3[1])
    d1, d2, d3 = s((px, py), a, b), s((px, py), b, c), s((px, py), c, a)
    return not ((d1 < 0 or d2 < 0 or d3 < 0) and (d1 > 0 or d2 > 0 or d3 > 0))


def gg_inside(px, py, arms_up):
    if px < 0 or py < 0 or px >= GG_W or py >= GG_H:
        return False
    m = 56 - px if px > 28 else px

    def el(cx, cy, rx, ry):
        return ((px - cx) / rx) ** 2 + ((py - cy) / ry) ** 2 <= 1
    if el(28, 32, 22, 20) or el(28, 40, 24, 12):
        return True
    if tri_in(m, py, (0, 0), (7, 24), (20, 13)):
        return True
    if tri_in(m, py, (3, 27), (8, 21), (9, 33)) or tri_in(m, py, (5, 37), (8, 32), (10, 41)):
        return True
    if (tri_in(px, py, (22, 4), (18, 14), (26, 12)) or tri_in(px, py, (29, 1), (25, 13), (34, 12))
            or tri_in(px, py, (36, 6), (32, 13), (40, 15))):
        return True
    if arms_up:
        return tri_in(m, py, (0, 8), (8, 30), (14, 22))
    return tri_in(m, py, (0, 46), (7, 33), (13, 41))


def gg_color(px, py, eyes, mouth, arms):
    """-1 transparent, 0 ink, 1 paper."""
    if not gg_inside(px, py, arms):
        return -1
    mx = 56 - px if px > 28 else px
    if eyes == 'open':
        if tri_in(mx, py, (11, 16), (25.5, 26), (14, 28)):
            return 0 if (abs(mx - 21.5) < 0.8 and 22.5 < py < 26) else 1
    elif 13 <= mx <= 24.5 and abs(py - (24.5 + 2 * math.sin(math.pi * (mx - 13) / 11))) < 0.85:
        return 1
    if mouth == 'grin':
        u = (px - 28) / 17
        if abs(u) <= 1:
            top, bot = 32 - 3 * u * u, 32 + 9 * (1 - u * u)
            if top <= py <= bot:
                tooth = any(abs(px - t) < 0.55 for t in (16, 20, 24, 28, 32, 36, 40))
                return 0 if (tooth and top + 1.5 < py < bot - 0.5) else 1
    elif mouth == 'yawn':
        d = ((px - 28) / 6) ** 2 + ((py - 36) / 7) ** 2
        if 0.55 <= d <= 1:
            return 1
    else:
        u = (px - 28) / 9
        if abs(u) <= 1 and abs(py - (34.5 + 3 * (1 - u * u))) < 0.85:
            return 1
    return 0


def draw_gengar(cv, gx, gy, eyes, mouth, arms):
    for y in range(math.ceil(GG_H * GS)):
        for x in range(math.ceil(GG_W * GS)):
            v = gg_color((x + 0.5) / GS, (y + 0.5) / GS, eyes, mouth, arms)
            if v >= 0:
                cv.px(gx + x, gy + y, v)


def state(kind, k):
    def sm(v):
        v = clamp(v, 0, 1)
        return v * v * (3 - 2 * v)
    if kind == 'wake':
        return {
            'inv': 1 - sm((k - 0.34) / 0.16),
            'eyes': 'closed' if (k < 0.42 or 0.48 < k < 0.52) else 'open',
            'gy': lerp(37, 18, ease_out_back(clamp((k - 0.52) / 0.18, 0, 1))),
            'arms': 0.7 < k < 0.88, 'mouth': 'smile' if k < 0.66 else 'grin',
            'bang': 0.52 < k < 0.68, 'zzz': 1 - clamp((k - 0.25) / 0.1, 0, 1),
            'banner': 'GOOD MORNING!' if k > 0.72 else '',
        }
    return {
        'inv': sm((k - 0.6) / 0.15),
        'mouth': 'grin' if k < 0.15 else ('yawn' if k < 0.42 else 'smile'),
        'arms': 0.15 < k < 0.4,
        'gy': lerp(18, 37, ease_in_out(clamp((k - 0.42) / 0.24, 0, 1))),
        'eyes': 'open' if k < 0.55 else 'closed', 'bang': False,
        'zzz': clamp((k - 0.72) / 0.1, 0, 1),
        'banner': 'GOOD NIGHT...' if k > 0.62 else '',
    }


def render(kind, k, tau):
    st = state(kind, k)
    gx, gy = 30, math.floor(st['gy'] + 0.5)
    cv = Canvas()
    cv.rect(8, 106, 176, 1, 0)
    cv.rect(22, 48, 10, 58, 0)
    cv.disc(27, 48, 5, 0)
    cv.rect(156, 66, 8, 40, 0)
    cv.disc(160, 66, 4, 0)
    cv.box(32, 76, 124, 12)
    cv.rect(32, 88, 124, 6, 0)
    cv.rect(36, 94, 4, 12, 0)
    cv.rect(148, 94, 4, 12, 0)
    cv.box(36, 62, 34, 14)
    draw_gengar(cv, gx, gy, st['eyes'], st['mouth'], st['arms'])
    cv.box(32, 70, 124, 28)
    cv.rect(34, 75, 120, 1, 0)
    cv.rect(70, 84, 1, 12, 0)
    cv.rect(104, 82, 1, 14, 0)
    cv.rect(134, 86, 1, 10, 0)
    if st['zzz'] > 0:
        for i in range(3):
            ph = (tau * 0.7 + i / 3) % 1
            text(cv, 'Z', gx + 62 + ph * 20, gy + 8 - ph * 26, 0, st['zzz'] * math.sin(ph * math.pi))
    if st['bang']:
        text(cv, '!', gx + 32, gy - 14, 0)
    if st['banner']:
        s = st['banner']
        text(cv, s, (GW - (len(s) * 6 - 1) * 2) // 2, 6, 0)
    if st['inv'] > 0:
        for y in range(GH):
            for x in range(GW):
                if (BAYER[y & 3][x & 3] + 0.5) / 16 < st['inv']:
                    cv.buf[y * GW + x] = 1 - cv.buf[y * GW + x]
    return [int(clamp(round(v * 255), 0, 255)) for v in cv.buf]


# ---------- GIF writer ----------
def lzw(data, min_size):
    clear, eoi = 1 << min_size, (1 << min_size) + 1
    out = bytearray()
    st = {'buf': 0, 'len': 0, 'size': min_size + 1}

    def emit(code):
        st['buf'] |= code << st['len']
        st['len'] += st['size']
        while st['len'] >= 8:
            out.append(st['buf'] & 255)
            st['buf'] >>= 8
            st['len'] -= 8

    def reset():
        st['size'] = min_size + 1
        return {bytes([i]): i for i in range(clear)}, eoi + 1

    table, nxt = reset()
    emit(clear)
    w = b''
    for b in data:
        wc = w + bytes([b])
        if wc in table:
            w = wc
            continue
        emit(table[w])
        if nxt == 4096:
            emit(clear)
            table, nxt = reset()
        else:
            table[wc] = nxt
            nxt += 1
            if nxt > (1 << st['size']) and st['size'] < 12:
                st['size'] += 1
        w = bytes([b])
    if w:
        emit(table[w])
    emit(eoi)
    if st['len']:
        out.append(st['buf'] & 255)
    return bytes(out)


def write_gif(path, frames, delay_cs):
    w, h = GW * SCALE, GH * SCALE
    out = bytearray(b'GIF89a' + struct.pack('<HHBBB', w, h, 0, 0, 0))
    out += b'\x21\xff\x0bNETSCAPE2.0\x03\x01\x00\x00\x00'
    for grey in frames:
        palette = sorted(set(grey))
        index = {v: i for i, v in enumerate(palette)}
        bits = max(1, (len(palette) - 1).bit_length())
        size = 1 << bits
        big = bytearray()
        for y in range(GH):
            row = bytearray()
            for x in range(GW):
                row += bytes([index[grey[y * GW + x]]]) * SCALE
            big += bytes(row) * SCALE
        out += b'\x21\xf9\x04\x04' + struct.pack('<H', delay_cs) + b'\x00\x00'
        out += b'\x2c' + struct.pack('<HHHH', 0, 0, w, h) + bytes([0x80 | (bits - 1)])
        for v in palette + [0] * (size - len(palette)):
            out += bytes([v, v, v])
        min_size = max(2, bits)
        data = lzw(bytes(big), min_size)
        out += bytes([min_size])
        for i in range(0, len(data), 255):
            chunk = data[i:i + 255]
            out += bytes([len(chunk)]) + chunk
        out += b'\x00'
    out += b'\x3b'
    with open(path, 'wb') as f:
        f.write(out)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(os.path.join(here, 'gifs'), exist_ok=True)
    n = int(DUR * FPS)
    for kind, name in (('wake', 'gengar-wake.gif'), ('sleep', 'gengar-sleep.gif')):
        frames = [render(kind, i / (n - 1), i / FPS) for i in range(n)]
        write_gif(os.path.join(here, 'gifs', name), frames, 100 // FPS)
        print('wrote gifs/' + name)


if __name__ == '__main__':
    main()
