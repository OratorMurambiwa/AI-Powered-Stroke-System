"""Bounded synthetic PNG subset; no decoder, ML import or file-system write."""
import binascii
import struct
import zlib
from .errors import ClinicalError

MAX_SCAN = 1048576

def validate_png(raw: bytes) -> None:
    def invalid():
        raise ClinicalError(400, 'invalid_scan_content')
    if not 1 <= len(raw) <= MAX_SCAN:
        raise ClinicalError(413, 'scan_too_large')
    if not raw.startswith(b'\x89PNG\r\n\x1a\n'):
        invalid()
    offset, chunks, compressed, header = 8, [], bytearray(), None
    while offset < len(raw):
        if offset + 12 > len(raw):
            invalid()
        length = struct.unpack('>I', raw[offset:offset+4])[0]
        kind = raw[offset+4:offset+8]
        end = offset + 12 + length
        if end > len(raw) or len(chunks) >= 128:
            invalid()
        data = raw[offset+8:end-4]
        if binascii.crc32(kind + data) & 0xffffffff != struct.unpack('>I', raw[end-4:end])[0]:
            invalid()
        if kind == b'IHDR' and not chunks and length == 13:
            header = struct.unpack('>IIBBBBB', data)
        elif kind == b'IDAT' and header and (chunks[-1] in {b'IHDR', b'IDAT'}):
            compressed.extend(data)
        elif kind == b'IEND' and not length and chunks and chunks[-1] == b'IDAT' and end == len(raw):
            pass
        else:
            invalid()  # No metadata, executable/polyglot tail, animation or external references.
        chunks.append(kind)
        offset = end
    if not header or chunks[-1] != b'IEND':
        invalid()
    width, height, depth, color, compression, filtering, interlace = header
    if not (1 <= width <= 1024 and 1 <= height <= 1024 and depth == 8 and color in {0, 2}
            and compression == filtering == interlace == 0):
        invalid()
    stride = 1 + width * (1 if color == 0 else 3)
    expected = stride * height
    try:
        decoder = zlib.decompressobj()
        pixels = decoder.decompress(compressed, expected + 1)
        if len(pixels) != expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
            invalid()
        if any(pixels[row * stride] > 4 for row in range(height)):
            invalid()
    except zlib.error:
        invalid()
