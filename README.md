## µPing (MicroPing) for MicroPython

An asynchronous single packet ping lib, tested on both micropython ESP32/ESP32S2/UNIX port and CPython3.9. Since it's asynchronous, measured delay may not be precise, depending on other async tasks' responsiveness. This lib is updated for checking connectivity without blocking.

Here mainly used for implementing an seperate connectivity maintenance task for a [stripped-down version of mqtt_as](https://github.com/zcattacz/mqtt_as) which has connectivity and wifi managing code dropped. Connectivity issue can be actively verified by pinging gateway and dns, besides checking `mqtt._has_connected` flag or `wlan.isconnected()`. 

For test on CPython, add a [micropython shim](https://github.com/zcattacz/mqtt_as/blob/main/micropython.py), or delete the `@native` decorator.

Run with default settings
```python
async def multi_ping(addr, count=3, interval=1):
    #ping.quiet = True
    print(f"ping {addr}")
    #calling with host_addr will reset icmp_seq to 1.
    await pingsvc.ping(addr)
    for i in (0, count-1):
        t = time.time()
        #calling without host will increase icmp_seq by 1.
        await pingsvc.ping()
        td = interval-(time.time()-t)
        if td > 0:
            await asyncio.sleep(td)

import uping
pingsvc = uping.Ping()
asyncio.run(multi_ping("example.org"))
```
```
64 bytes from 93.184.216.34: seq=0 ttl=54 time=106.261 ms
64 bytes from 93.184.216.34: seq=1 ttl=54 time=106.221 ms
64 bytes from 93.184.216.34: seq=2 ttl=54 time=106.421 ms
64 bytes from 93.184.216.34: seq=3 ttl=54 time=107.521 ms
```
---
### Arguments:
Optional
- HOST     (default:"127.0.0.1", FQDN or IP address)
- SOURCE   (default: None, ip address)
- SIZE     (default: 64, bytes)
- TIMEOUT  (default: 5000, ms)
- quiet    (default: False, bool)
---

### Class methods

#### ping(host="")
> Ping with just a one packet. 
> - when called with host address, seq num is reset to 1
> - when called without host, seq num is incremented sequencially.
> Returns sequense number(int), round-trip time (ms, float), ttl(int)<br>
> e.g. (5, 106.521, 54)

All credit goes to the orginal author.
