# µPing (MicroPing) for MicroPython (Unix version)
# License: MIT
# copyright (c) 2020 coffee-it

# recommendations from
# https://forum.micropython.org/viewtopic.php?t=5287

# µPing (MicroPing) for MicroPython
# copyright (c) 2018 Shawwwn <shawwwn1@gmail.com>
# License: MIT

# Internet Checksum Algorithm
# Author: Olav Morken
# https://github.com/olavmrk/python-ping/blob/master/ping.py
# @data: bytes
try:
    import uctypes # esp32 doesn't have ctypes
except:
    import ctypes as uctypes
import select as uselect
import socket as usocket
import struct as ustruct
import random as urandom
import micropython
import gc
from sys import implementation as impl
if impl.name == "micropython":
    import uasyncio as asyncio
    import time as utime
else:
    import asyncio
    utime = micropython.patch_time()

from errno import EINPROGRESS
urandom.seed(utime.ticks_us())

class Ping():
    """
    Create the ping calculating object exemplar
    """
    def __init__(self, HOST, SOURCE=None, COUNT=4, INTERVAL=1000, SIZE=64, TIMEOUT=5000, quiet=False):
        self.HOST     = HOST
        self.COUNT    = COUNT
        self.TIMEOUT  = TIMEOUT
        self.INTERVAL = INTERVAL
        self.SIZE     = SIZE
        self.SOURCE   = SOURCE
        self.quiet    = quiet

        # prepare packet
        assert SIZE >= 16, "pkt size too small"
        self._PKT = bytearray(b'Q'*SIZE)
        if impl.name == "micropython":
            self.PKT_DESC = {
                "type": uctypes.UINT8 | 0,
                "code": uctypes.UINT8 | 1,
                "checksum": uctypes.UINT16 | 2,
                "id": uctypes.UINT16 | 4,
                "seq": uctypes.INT16 | 6,
                "timestamp": uctypes.UINT64 | 8,
            } # packet header descriptor
            h = uctypes.ustruct(uctypes.addressof(self._PKT), self.PKT_DESC, uctypes.BIG_ENDIAN)
        else:
            class PktDesc(uctypes.BigEndianStructure):
                _pack_ = 1
                _fields_ = [
                    ("type", uctypes.c_uint8),
                    ("code", uctypes.c_uint8),
                    ("checksum", uctypes.c_uint16),
                    ("id", uctypes.c_uint16),
                    ("seq", uctypes.c_int16),
                    ("timestamp", uctypes.c_uint64)
                ]
            self.PKT_DESC =PktDesc
            h = self.PKT_DESC.from_buffer(self._PKT)
        h.type = 8 # ICMP_ECHO_REQUEST
        h.code = 0
        h.checksum = 0
        h.id = urandom.getrandbits(16)
        h.seq = 1
        self.h = h

        self.sock = None
        self.DEST_IP = self._connect_to_host(HOST)

        # [ COUNTERS ]
        self.seq_num = 1 # Next sequence number
        self.transmitted = 0
        self.received = 0
        self.seqs = None

    def sock_connect(self, addr):
        #close old socket
        if self.sock and self.sock.fileno() > 0:
            try:
                #print("closing opened socket:", self.sock.fileno())
                self.sock.close()
                gc.collect()
            except:
                pass

        # init socket
        #print("creating socket for", addr)
        self.sock = usocket.socket(usocket.AF_INET, usocket.SOCK_RAW, 1)
        if self.SOURCE:
            src_addr = usocket.getaddrinfo(self.SOURCE, 1)[0][-1] # ip address
            self.sock.bind(src_addr)
        self.sock.setblocking(False)

        poller = uselect.poll()
        poller.register(self.sock, uselect.POLLIN | uselect.POLLOUT)

        #if not self.quiet: print("print:sock connecting to %s", addr)
        try:
            self.sock.connect(addr)
        except OSError as e:
            if e.errno != EINPROGRESS:
                raise e

        #if not self.quiet: print("print:sock polling for connect open")
        res = poller.poll(self.TIMEOUT)
        #print("c2u", res)
        poller.unregister(self.sock)
        #print("c2ud", res)
        if not res:
            #print("c2e", res)
            self.sock.close()
            raise OSError('Socket Connect Timeout')
        
        if self.sock.fileno() < 0:
            raise OSError('Socket Connect Failed, RST?')
        #if not self.quiet: print("ping:", res, self.sock.fileno())

        # Socket connected
        self.sock.settimeout(self.TIMEOUT/1000)

    def _connect_to_host(self, HOST):
        if self.is_valid_ip(HOST):
            addresses = [[(HOST,1)]]
            #self.sock.connect((HOST,1))
            #return HOST
        else:
            addresses = usocket.getaddrinfo(HOST, 1) # [0][-1] # list of ip addresses
        assert addresses, "Can not take the IP address of host"
        for addr in addresses:
            try:
                self.sock_connect(addr[-1])
                return addr[-1][0] #usocket.inet_ntop(usocket.AF_INET, addr[-1][0])
            except Exception as ex:
                print("_connect_to_host:", ex.args, type(ex))
                try:
                    self.sock.close()
                except:
                    pass
                continue
        raise Exception("Can not take the IP address of host")

    @micropython.native
    def is_valid_ip(self, HOST):
        digits = HOST.split(".")
        if len(digits) == 4:
            for d in digits:
                try:
                    if int(d) > 255:
                        return False
                except:
                    return False
            return True

    async def ping(self, host=""):
        if host != "":
            gc.collect()
            try:
                self.DEST_IP = self._connect_to_host(host)
                # [ Start over ]
                self.seq_num = 1
                self.seqs = [1]
                self.transmitted = 0
                self.received = 0
            except:
                print("ping: failed to connect to host", self.DEST_IP)
                pass
        """
        Send ping manually.
        Returns sequense number(int), round-trip time (ms, float), ttl
        """
        if not self.seqs:
            self.seqs = []
            self.seqs.append(self.seq_num)
        seq, t_elasped, ttl = None, None, None

        # header
        h = self.h
        h.checksum = 0
        h.seq = self.seq_num
        h.timestamp = utime.ticks_us()
        h.checksum = self.checksum(self._PKT)

        try:
            # send packet
            if self.sock.send(self._PKT) == self.SIZE:
                self.transmitted += 1
            else:
                self.seqs.remove(self.seq_num)
            self.seq_num += 1

            # recv packet
            while 1:
                resp = self.sock.recv(self.SIZE + 20) # ICMP header and payload + IP header
                resp_mv = memoryview(resp)
                if impl.name == "micropython":
                    h2 = uctypes.struct(uctypes.addressof(resp_mv[20:]), self.PKT_DESC, uctypes.BIG_ENDIAN)
                else:
                    h2 = self.PKT_DESC.from_buffer_copy(resp_mv[20:])
                seq = h2.seq
                if h2.type==0 and h2.id==h.id and (seq in self.seqs): # 0: ICMP_ECHO_REPLY
                    t_elasped = (utime.ticks_us()-h2.timestamp) / 1000
                    self.seqs.remove(seq)
                    if h2.checksum == self.checksum(resp[24:]): # except IP header and a part of ICMP header (type, code, checksum)
                        ttl = ustruct.unpack('!B', resp_mv[8:9])[0] # time-to-live
                        self.received += 1
                        if not self.quiet: print("%u bytes from %s: icmp_seq=%u, ttl=%u, time=%f ms" % (len(resp[12:]), self.DEST_IP, seq, ttl, t_elasped))
                        break
                    else:
                        if not self.quiet: print("Payload checksum doesnt match")
                        t_elasped = None
                        break
                await asyncio.sleep(0)

        except Exception as identifier:
            import errno
            if identifier.args[0] in [errno.ETIMEDOUT, "timed out"]: #EPIPE broken pipe:
                print("ping: Connection closed unexpectedly")
                pass
            elif identifier.args[0] == errno.EHOSTUNREACH: #EPIPE broken pipe:
                print("ping: Host unreachable")
                pass
            elif identifier.args[0] == errno.EBADF:
                print("ping: Bad file descriptor.")
                pass
            elif identifier.args[0] == errno.EPERM: # PermissionError
                print("ping: Permission denied, check setcap/iptables")
                pass
            else:
                print("ping: unknown exception:", identifier.args, type(identifier))
                raise identifier
        return (seq, t_elasped, ttl)

    @micropython.native
    def checksum(self, data):
        if len(data) & 0x1: # Odd number of bytes
            data += b'\0'
        cs = 0
        for pos in range(0, len(data), 2):
            b1 = data[pos]
            b2 = data[pos + 1]
            cs += (b1 << 8) + b2
        while cs >= 0x10000:
            cs = (cs & 0xffff) + (cs >> 16)
        cs = ~cs & 0xffff
        return cs

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.close()

    def close(self):
        self.sock.close()
if __name__ == "__main__":
    import wifi
    wifi.reset()
    print("waiting for wifi")
    wifi.connect()
    icfg = wifi.sta.ifconfig()
    print(icfg)
    gw = icfg[2]
    ##gw = "qq.com"
    print("ping:", gw)
    ping = Ping(gw, COUNT=3); ping.start()
    ping = Ping("bing.com", COUNT=3); ping.start()
    ping = Ping(gw, COUNT=3); ping.start()
    ping.ping("bing.com")
    ping.ping(gw)
