"""Generated PNG shape/color parity across dependency candidates; no labels/accuracy."""
import base64,binascii,hashlib,json,struct,zlib
from inference_worker.server import run_job

def main():
    results=[]
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',binascii.crc32(kind+data)&0xffffffff)
    for width,height in [(64,64),(320,240),(512,512),(1024,256)]:
        for channels,color in [(1,0),(3,2)]:
            rows=[b'\0'+bytes((x*3+y*7+c*53)%256 for x in range(width) for c in range(channels)) for y in range(height)]
            raw=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,color,0,0,0))+chunk(b'IDAT',zlib.compress(b''.join(rows)))+chunk(b'IEND',b'')
            result=run_job({'contentBase64':base64.b64encode(raw).decode(),'scanSha256':hashlib.sha256(raw).hexdigest()})
            results.append({'width':width,'height':height,'channels':channels,**{k:v for k,v in result.items() if k!='durationMs'}})
    print(json.dumps({'schemaVersion':1,'syntheticOnly':True,'results':results},indent=2))
if __name__=='__main__':main()
