"""Actual CPU verification on generated patterns; no accuracy claim."""
import base64
import binascii
import hashlib
import json
import struct
import zlib
from .server import run_job

def image(pattern):
    def chunk(kind,data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',binascii.crc32(kind+data)&0xffffffff)
    rows=[]
    for y in range(64):
        pixels=bytes(0 if pattern=='black' else 255 if pattern=='white' else (x*4+y*2)%256 for x in range(64))
        rows.append(b'\0'+pixels)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',64,64,8,0,0,0,0))+chunk(b'IDAT',zlib.compress(b''.join(rows)))+chunk(b'IEND',b'')

def main():
    results=[]
    for pattern in ('black','white','gradient'):
        raw=image(pattern)
        request={'contentBase64':base64.b64encode(raw).decode(),'scanSha256':hashlib.sha256(raw).hexdigest()}
        results.append({'syntheticPattern':pattern,**run_job(request)})
    print(json.dumps(results,indent=2,allow_nan=False))

if __name__=='__main__':
    main()
