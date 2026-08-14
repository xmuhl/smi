import socket, ssl, time
host = 'push2his.eastmoney.com'
CRLF = chr(13) + chr(10)
def probe(ip):
    try:
        s = socket.socket(); s.settimeout(6)
        s.connect((ip, 443))
        ctx = ssl.create_default_context()
        ss = ctx.wrap_socket(s, server_hostname=host)
        req = ('GET /api/qt/stock/kline/get?secid=1.000001&fields1=f1&fields2=f51&klt=101&fqt=0&beg=20260801&end=20260814 HTTP/1.1' + CRLF +
               'Host: ' + host + CRLF +
               'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36' + CRLF +
               'Referer: https://quote.eastmoney.com/' + CRLF +
               'Connection: close' + CRLF + CRLF)
        ss.sendall(req.encode())
        data = b''
        while True:
            c = ss.recv(4096)
            if not c: break
            data += c
        ss.close()
        ok = b'HTTP/1.1 200' in data
        print(ip, '->', 'OK' if ok else ('RESP ' + str(data[:40])), flush=True)
        return ok
    except Exception as e:
        print(ip, '-> FAIL', type(e).__name__, str(e)[:70], flush=True)
        return False

addrs = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
ips = list(dict.fromkeys(a[4][0] for a in addrs))
print('resolved:', ips, flush=True)
good = [ip for ip in ips if probe(ip)]
print('good:', good, flush=True)
