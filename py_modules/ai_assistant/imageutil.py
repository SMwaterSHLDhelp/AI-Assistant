"""PNG decode and baseline JPEG encode using the standard library only.

Gamescope writes PNG screenshots. Providers want a JPEG around 1280px so the
request stays small. Pillow and ffmpeg are not required on the Deck.
"""

from __future__ import annotations

import math
import zlib

MAX_EDGE = 1280
MAX_BYTES = 1_500_000
_MAX_DIMENSION = 8000

_ZZ = [
    0, 1, 8, 16, 9, 2, 3, 10,
    17, 24, 32, 25, 18, 11, 4, 5,
    12, 19, 26, 33, 40, 48, 41, 34,
    27, 20, 13, 6, 7, 14, 21, 28,
    35, 42, 49, 56, 57, 50, 43, 36,
    29, 22, 15, 23, 30, 37, 44, 51,
    58, 59, 52, 45, 38, 31, 39, 46,
    53, 60, 61, 54, 47, 55, 62, 63,
]

_LUMA_Q = [
    16, 11, 10, 16, 24, 40, 51, 61,
    12, 12, 14, 19, 26, 58, 60, 55,
    14, 13, 16, 24, 40, 57, 69, 56,
    14, 17, 22, 29, 51, 87, 80, 62,
    18, 22, 37, 56, 68, 109, 103, 77,
    24, 35, 55, 64, 81, 104, 113, 92,
    49, 64, 78, 87, 103, 121, 120, 101,
    72, 92, 95, 98, 112, 100, 103, 99,
]
_CHROMA_Q = [
    17, 18, 24, 47, 99, 99, 99, 99,
    18, 21, 26, 66, 99, 99, 99, 99,
    24, 26, 56, 99, 99, 99, 99, 99,
    47, 66, 99, 99, 99, 99, 99, 99,
    99, 99, 99, 99, 99, 99, 99, 99,
    99, 99, 99, 99, 99, 99, 99, 99,
    99, 99, 99, 99, 99, 99, 99, 99,
    99, 99, 99, 99, 99, 99, 99, 99,
]

_DC_LUMA_COUNTS = [0, 1, 5, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0]
_DC_CHROMA_COUNTS = [0, 3, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0]
_DC_SYMBOLS = list(range(12))
_AC_LUMA_COUNTS = [0, 2, 1, 3, 3, 2, 4, 3, 5, 5, 4, 4, 0, 0, 1, 0x7D]
_AC_CHROMA_COUNTS = [0, 2, 1, 2, 4, 4, 3, 4, 7, 5, 4, 4, 0, 1, 2, 0x77]
_AC_LUMA_SYMBOLS = bytes.fromhex(
    "01020300041105122131410613516107227114328191a1082342b1c11552d1f02433627282090a161718191a25262728292a3435363738393a434445464748494a535455565758595a636465666768696a737475767778797a838485868788898a92939495969798999aa2a3a4a5a6a7a8a9aab2b3b4b5b6b7b8b9bac2c3c4c5c6c7c8c9cad2d3d4d5d6d7d8d9dae1e2e3e4e5e6e7e8e9eaf1f2f3f4f5f6f7f8f9fa"
)
_AC_CHROMA_SYMBOLS = bytes.fromhex(
    "000102031104052131061241510761711322328108144291a1b1c109233352f0156272d10a162434e125f11718191a262728292a35363738393a434445464748494a535455565758595a636465666768696a737475767778797a82838485868788898a92939495969798999aa2a3a4a5a6a7a8a9aab2b3b4b5b6b7b8b9bac2c3c4c5c6c7c8c9cad2d3d4d5d6d7d8d9dae2e3e4e5e6e7e8e9eaf2f3f4f5f6f7f8f9fa"
)

_COS = [[math.cos((2 * x + 1) * u * math.pi / 16.0) for u in range(8)] for x in range(8)]
_SCALE = [1.0 / math.sqrt(2.0) if u == 0 else 1.0 for u in range(8)]


def _check_tables() -> None:
    pairs = (
        (_DC_LUMA_COUNTS, _DC_SYMBOLS, "dc luma"),
        (_DC_CHROMA_COUNTS, _DC_SYMBOLS, "dc chroma"),
        (_AC_LUMA_COUNTS, _AC_LUMA_SYMBOLS, "ac luma"),
        (_AC_CHROMA_COUNTS, _AC_CHROMA_SYMBOLS, "ac chroma"),
    )
    for counts, symbols, name in pairs:
        if sum(counts) != len(symbols):
            raise RuntimeError(f"JPEG {name} table does not match its symbol list")
    if len(_ZZ) != 64 or len(set(_ZZ)) != 64:
        raise RuntimeError("JPEG zigzag table is incomplete")


_check_tables()


def encode_png(rgb: bytes, width: int, height: int) -> bytes:
    """8-bit RGB PNG. Used by tests and by anything that already has raw pixels."""
    if width < 1 or height < 1 or len(rgb) != width * height * 3:
        raise ValueError("RGB size does not match the image")

    def chunk(tag: bytes, payload: bytes) -> bytes:
        crc = zlib.crc32(tag + payload) & 0xFFFFFFFF
        return len(payload).to_bytes(4, "big") + tag + payload + crc.to_bytes(4, "big")

    raw = bytearray()
    stride = width * 3
    for y in range(height):
        raw.append(0)
        start = y * stride
        raw.extend(rgb[start : start + stride])
    ihdr = width.to_bytes(4, "big") + height.to_bytes(4, "big") + bytes((8, 2, 0, 0, 0))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(b"IEND", b"")


def decode_png(data: bytes) -> tuple[bytes, int, int]:
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Screenshot was not a PNG")
    pos = 8
    width = height = bit_depth = color_type = None
    interlace = 0
    idat = bytearray()
    while pos + 8 <= len(data):
        length = int.from_bytes(data[pos : pos + 4], "big")
        tag = data[pos + 4 : pos + 8]
        end = pos + 8 + length
        if end + 4 > len(data):
            raise ValueError("PNG chunk is truncated")
        payload = data[pos + 8 : end]
        pos = end + 4
        if tag == b"IHDR":
            width = int.from_bytes(payload[0:4], "big")
            height = int.from_bytes(payload[4:8], "big")
            bit_depth = payload[8]
            color_type = payload[9]
            interlace = payload[12]
        elif tag == b"IDAT":
            idat.extend(payload)
        elif tag == b"IEND":
            break
    if not width or not height or not idat or bit_depth is None or color_type is None:
        raise ValueError("PNG is missing image data")
    if width > _MAX_DIMENSION or height > _MAX_DIMENSION:
        raise ValueError("Screenshot is too large")
    if interlace:
        raise ValueError("Interlaced PNGs are not supported")
    if bit_depth != 8:
        raise ValueError("Only 8-bit PNGs are supported")
    channels = {0: 1, 2: 3, 4: 2, 6: 4}.get(color_type)
    if channels is None:
        raise ValueError("Unsupported PNG color")
    raw = zlib.decompress(bytes(idat))
    stride = width * channels
    if len(raw) < height * (stride + 1):
        raise ValueError("PNG data is truncated")
    prev = bytearray(stride)
    rgb = bytearray(width * height * 3)
    offset = 0
    dest = 0
    for _ in range(height):
        filter_type = raw[offset]
        offset += 1
        scan = bytearray(raw[offset : offset + stride])
        offset += stride
        recon = _unfilter(filter_type, scan, prev, channels)
        prev = recon
        if channels == 3:
            rgb[dest : dest + stride] = recon
            dest += stride
            continue
        step = 4 if channels == 4 else channels
        for index in range(0, stride, step):
            value = recon[index]
            if channels == 1:
                pixel = (value, value, value)
            elif channels == 2:
                pixel = (value, value, value)
            else:
                pixel = (recon[index], recon[index + 1], recon[index + 2])
            rgb[dest : dest + 3] = bytes(pixel)
            dest += 3
    return bytes(rgb), width, height


def _unfilter(filter_type: int, scan: bytearray, prev: bytearray, channels: int) -> bytearray:
    out = bytearray(len(scan))
    if filter_type == 0:
        return scan
    for index, value in enumerate(scan):
        left = out[index - channels] if index >= channels else 0
        up = prev[index]
        up_left = prev[index - channels] if index >= channels else 0
        if filter_type == 1:
            predictor = left
        elif filter_type == 2:
            predictor = up
        elif filter_type == 3:
            predictor = (left + up) // 2
        elif filter_type == 4:
            predictor = _paeth(left, up, up_left)
        else:
            raise ValueError("Unsupported PNG filter")
        out[index] = (value + predictor) & 0xFF
    return out


def _paeth(left: int, up: int, up_left: int) -> int:
    estimate = left + up - up_left
    left_distance = abs(estimate - left)
    up_distance = abs(estimate - up)
    diagonal = abs(estimate - up_left)
    if left_distance <= up_distance and left_distance <= diagonal:
        return left
    if up_distance <= diagonal:
        return up
    return up_left


def fit_rgb(rgb: bytes, width: int, height: int, max_edge: int) -> tuple[bytes, int, int]:
    longest = max(width, height)
    if longest <= max_edge:
        return rgb, width, height
    scale = max_edge / longest
    new_width = max(1, int(round(width * scale)))
    new_height = max(1, int(round(height * scale)))
    fitted = bytearray(new_width * new_height * 3)
    for y in range(new_height):
        y0 = (y * height) // new_height
        y1 = max(y0 + 1, ((y + 1) * height) // new_height)
        for x in range(new_width):
            x0 = (x * width) // new_width
            x1 = max(x0 + 1, ((x + 1) * width) // new_width)
            total = [0, 0, 0]
            count = 0
            for yy in range(y0, y1):
                row = yy * width
                for xx in range(x0, x1):
                    index = (row + xx) * 3
                    total[0] += rgb[index]
                    total[1] += rgb[index + 1]
                    total[2] += rgb[index + 2]
                    count += 1
            dest = (y * new_width + x) * 3
            fitted[dest] = total[0] // count
            fitted[dest + 1] = total[1] // count
            fitted[dest + 2] = total[2] // count
    return bytes(fitted), new_width, new_height


def jpeg_size(data: bytes) -> tuple[int, int] | None:
    if not data.startswith(b"\xff\xd8"):
        return None
    pos = 2
    limit = len(data)
    while pos + 4 < limit:
        if data[pos] != 0xFF:
            pos += 1
            continue
        while pos < limit and data[pos] == 0xFF:
            pos += 1
        if pos >= limit:
            break
        marker = data[pos]
        pos += 1
        if marker in {0x01, 0xD8} or 0xD0 <= marker <= 0xD7:
            continue
        if pos + 2 > limit:
            break
        length = int.from_bytes(data[pos : pos + 2], "big")
        if marker in {0xC0, 0xC1, 0xC2}:
            if pos + 7 > limit:
                return None
            height = int.from_bytes(data[pos + 3 : pos + 5], "big")
            width = int.from_bytes(data[pos + 5 : pos + 7], "big")
            return width, height
        if marker == 0xD9:
            break
        pos += length
    return None


def to_jpeg(data: bytes, *, max_edge: int = MAX_EDGE, max_bytes: int = MAX_BYTES) -> bytes:
    """Return a JPEG whose long edge is about ``max_edge`` and whose size stays under ``max_bytes``."""
    if data.startswith(b"\xff\xd8"):
        size = jpeg_size(data)
        if size is None:
            raise ValueError("Could not read that JPEG screenshot")
        if max(size) <= max_edge and len(data) <= max_bytes:
            return data
        raise ValueError(
            "That JPEG screenshot is larger than 1280px. A Gamescope PNG capture is resized before it is sent."
        )
    rgb, width, height = decode_png(data)
    encoded = b""
    for edge, quality in ((max_edge, 70), (max_edge, 50), (min(max_edge, 960), 45), (min(max_edge, 640), 35)):
        fitted, fitted_width, fitted_height = fit_rgb(rgb, width, height, edge)
        encoded = encode_jpeg(fitted, fitted_width, fitted_height, quality)
        if len(encoded) <= max_bytes:
            return encoded
    raise ValueError("Could not shrink the screenshot enough to send")


def encode_jpeg(rgb: bytes, width: int, height: int, quality: int = 70) -> bytes:
    if width < 1 or height < 1 or len(rgb) != width * height * 3:
        raise ValueError("RGB size does not match the image")
    if width > _MAX_DIMENSION or height > _MAX_DIMENSION:
        raise ValueError("Screenshot is too large")
    luma_q, chroma_q = _scaled_quant(_LUMA_Q, quality), _scaled_quant(_CHROMA_Q, quality)
    tables = (luma_q, chroma_q, chroma_q)
    dc_codes = (_codes(_DC_LUMA_COUNTS, _DC_SYMBOLS), _codes(_DC_CHROMA_COUNTS, _DC_SYMBOLS))
    ac_codes = (_codes(_AC_LUMA_COUNTS, list(_AC_LUMA_SYMBOLS)), _codes(_AC_CHROMA_COUNTS, list(_AC_CHROMA_SYMBOLS)))
    dc_choice = (dc_codes[0], dc_codes[1], dc_codes[1])
    ac_choice = (ac_codes[0], ac_codes[1], ac_codes[1])
    writer = _BitWriter()
    previous = [0, 0, 0]
    padded_width = (width + 7) // 8 * 8
    padded_height = (height + 7) // 8 * 8
    for block_y in range(0, padded_height, 8):
        for block_x in range(0, padded_width, 8):
            planes = _planes(rgb, width, height, block_x, block_y)
            for component in range(3):
                quantized = _quantize(_dct(planes[component]), tables[component])
                zigzag = [quantized[pos] for pos in _ZZ]
                _write_block(writer, zigzag, previous[component], dc_choice[component], ac_choice[component])
                previous[component] = zigzag[0]
    writer.flush()
    header = bytearray(b"\xff\xd8")
    header += b"\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    header += _dqt(0, luma_q)
    header += _dqt(1, chroma_q)
    header += _sof(width, height)
    header += _dht(0x00, _DC_LUMA_COUNTS, _DC_SYMBOLS)
    header += _dht(0x01, _DC_CHROMA_COUNTS, _DC_SYMBOLS)
    header += _dht(0x10, _AC_LUMA_COUNTS, _AC_LUMA_SYMBOLS)
    header += _dht(0x11, _AC_CHROMA_COUNTS, _AC_CHROMA_SYMBOLS)
    header += _sos()
    header += writer.data
    header += b"\xff\xd9"
    return bytes(header)


def _scaled_quant(table: list[int], quality: int) -> list[int]:
    quality = max(1, min(100, int(quality)))
    factor = 5000 // quality if quality < 50 else 200 - quality * 2
    return [max(1, min(255, (value * factor + 50) // 100)) for value in table]


def _codes(counts: list[int], symbols: list[int]) -> dict[int, tuple[int, int]]:
    codes: dict[int, tuple[int, int]] = {}
    code = 0
    index = 0
    for length, count in enumerate(counts, start=1):
        for _ in range(count):
            codes[symbols[index]] = (code, length)
            index += 1
            code += 1
        code <<= 1
    return codes


def _dqt(table_id: int, natural: list[int]) -> bytes:
    zigzag = bytes(natural[pos] for pos in _ZZ)
    body = bytes((table_id,)) + zigzag
    return b"\xff\xdb" + (len(body) + 2).to_bytes(2, "big") + body


def _sof(width: int, height: int) -> bytes:
    body = bytearray((8,))
    body += height.to_bytes(2, "big")
    body += width.to_bytes(2, "big")
    body.append(3)
    body += bytes((1, 0x11, 0, 2, 0x11, 1, 3, 0x11, 1))
    return b"\xff\xc0" + (len(body) + 2).to_bytes(2, "big") + bytes(body)


def _dht(class_id: int, counts: list[int], symbols: bytes | list[int]) -> bytes:
    body = bytes((class_id, *counts)) + bytes(symbols)
    return b"\xff\xc4" + (len(body) + 2).to_bytes(2, "big") + body


def _sos() -> bytes:
    body = bytes((3, 1, 0x00, 2, 0x11, 3, 0x11, 0, 63, 0))
    return b"\xff\xda" + (len(body) + 2).to_bytes(2, "big") + body


def _planes(rgb: bytes, width: int, height: int, origin_x: int, origin_y: int) -> tuple[list[float], list[float], list[float]]:
    luma = [0.0] * 64
    blue = [0.0] * 64
    red = [0.0] * 64
    for y in range(8):
        sample_y = min(height - 1, origin_y + y)
        row = sample_y * width
        for x in range(8):
            sample_x = min(width - 1, origin_x + x)
            index = (row + sample_x) * 3
            red_value = rgb[index]
            green_value = rgb[index + 1]
            blue_value = rgb[index + 2]
            slot = y * 8 + x
            luma[slot] = (0.299 * red_value + 0.587 * green_value + 0.114 * blue_value) - 128.0
            blue[slot] = (-0.168736 * red_value - 0.331264 * green_value + 0.5 * blue_value)
            red[slot] = (0.5 * red_value - 0.418688 * green_value - 0.081312 * blue_value)
    return luma, blue, red


def _dct(block: list[float]) -> list[float]:
    temp = [0.0] * 64
    for y in range(8):
        row = y * 8
        for u in range(8):
            total = 0.0
            for x in range(8):
                total += block[row + x] * _COS[x][u]
            temp[row + u] = total * _SCALE[u]
    out = [0.0] * 64
    for u in range(8):
        for v in range(8):
            total = 0.0
            for y in range(8):
                total += temp[y * 8 + u] * _COS[y][v]
            out[v * 8 + u] = total * _SCALE[v] * 0.25
    return out


def _quantize(coeffs: list[float], table: list[int]) -> list[int]:
    out = [0] * 64
    for index, coeff in enumerate(coeffs):
        divisor = table[index]
        out[index] = int(coeff / divisor + (0.5 if coeff >= 0 else -0.5))
    return out


def _write_block(
    writer: _BitWriter,
    zigzag: list[int],
    previous_dc: int,
    dc_codes: dict[int, tuple[int, int]],
    ac_codes: dict[int, tuple[int, int]],
) -> None:
    _write_coeff(writer, zigzag[0] - previous_dc, dc_codes)
    run = 0
    for value in zigzag[1:]:
        if value == 0:
            run += 1
            continue
        while run > 15:
            bits, length = ac_codes[0xF0]
            writer.write(bits, length)
            run -= 16
        symbol = (run << 4) | (abs(value).bit_length())
        bits, length = ac_codes[symbol]
        writer.write(bits, length)
        _write_magnitude(writer, value)
        run = 0
    if run:
        bits, length = ac_codes[0x00]
        writer.write(bits, length)


def _write_coeff(writer: _BitWriter, value: int, codes: dict[int, tuple[int, int]]) -> None:
    category = 0 if value == 0 else abs(value).bit_length()
    bits, length = codes[category]
    writer.write(bits, length)
    if category:
        _write_magnitude(writer, value)


def _write_magnitude(writer: _BitWriter, value: int) -> None:
    category = abs(value).bit_length()
    magnitude = value if value > 0 else value + (1 << category) - 1
    writer.write(magnitude, category)


class _BitWriter:
    def __init__(self) -> None:
        self.data = bytearray()
        self._acc = 0
        self._n = 0

    def write(self, value: int, length: int) -> None:
        if length <= 0:
            return
        self._acc = (self._acc << length) | (value & ((1 << length) - 1))
        self._n += length
        while self._n >= 8:
            self._n -= 8
            byte = (self._acc >> self._n) & 0xFF
            self.data.append(byte)
            if byte == 0xFF:
                self.data.append(0x00)

    def flush(self) -> None:
        if self._n:
            self.write((1 << (8 - self._n)) - 1, 8 - self._n)
