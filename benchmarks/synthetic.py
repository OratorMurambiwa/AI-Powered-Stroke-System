"""Nonmedical generated PNG workload, not labeled evaluation data."""
import binascii,struct,zlib

def image(pattern):
    if pattern not in {'black','white','gradient'}:raise ValueError('unknown synthetic pattern')
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',binascii.crc32(kind+data)&0xffffffff)
    rows=[]
    for y in range(64):
        pixels=bytes(0 if pattern=='black' else 255 if pattern=='white' else (x*4+y*2)%256 for x in range(64))
        rows.append(b'\0'+pixels)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',64,64,8,0,0,0,0))+chunk(b'IDAT',zlib.compress(b''.join(rows)))+chunk(b'IEND',b'')
