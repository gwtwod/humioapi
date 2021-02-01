"""
Original source: https://gist.github.com/florimondmanca/d56764d78d748eb9f73165da388e546e

An HTTPCore transport that uses urllib3 as the HTTP networking backend. (This was initially shipped with HTTPX.)

When used with HTTPX, this transport makes it easier to transition from Requests to HTTPX by keeping the same underlying HTTP networking layer.

Compatible with: HTTPX 0.15.x, 0.16.x (i.e. HTTPCore 0.11.x and HTTPCore 0.12.x).

Note: not all urllib3 pool manager options are supported here — feel free to adapt this gist to your specific needs.
"""

#MIT License
#
#Copyright (c) 2020 Florimond Manca
#
#Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
#
#The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
#
#THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#

import socket
import ssl
from typing import Dict, Iterator, List, Optional, Tuple

import httpcore
import urllib3


class URLLib3ByteStream(httpcore.SyncByteStream):
    def __init__(self, response: urllib3.HTTPResponse) -> None:
        self._response = response

    def __iter__(self) -> Iterator[bytes]:
        try:
            for chunk in self._response.stream(4096, decode_content=False):
                yield chunk
        except socket.error as exc:
            raise httpcore.NetworkError(exc)

    def close(self) -> None:
        self._response.release_conn()


class URLLib3Transport(httpcore.SyncHTTPTransport):
    def __init__(
        self,
        *,
        ssl_context: ssl.SSLContext = None,
        pool_connections: int = 10,
        pool_maxsize: int = 10,
        pool_block: bool = False,
    ) -> None:
        self._pool = urllib3.PoolManager(
            ssl_context=ssl_context,
            num_pools=pool_connections,
            maxsize=pool_maxsize,
            block=pool_block,
        )

    def request(
        self,
        method: bytes,
        url: Tuple[bytes, bytes, Optional[int], bytes],
        headers: List[Tuple[bytes, bytes]] = None,
        stream: httpcore.SyncByteStream = None,
        ext: dict = None,
    ) -> Tuple[int, List[Tuple[bytes, bytes]], httpcore.SyncByteStream, dict]:
        headers = [] if headers is None else headers
        stream = httpcore.PlainByteStream(b"") if stream is None else stream
        ext = {} if ext is None else ext
        timeout: Dict[str, float] = ext["timeout"]

        urllib3_timeout = urllib3.util.Timeout(
            connect=timeout.get("connect"), read=timeout.get("read")
        )

        chunked = False
        content_length = 0
        for header_key, header_value in headers:
            header_key = header_key.lower()
            if header_key == b"transfer-encoding":
                chunked = header_value == b"chunked"
            if header_key == b"content-length":
                content_length = int(header_value.decode("ascii"))
        body = stream if chunked or content_length else None

        scheme, host, port, path = url
        default_port = {b"http": 80, "https": 443}.get(scheme)
        if port is None or port == default_port:
            url_str = "%s://%s%s" % (
                scheme.decode("ascii"),
                host.decode("ascii"),
                path.decode("ascii"),
            )
        else:
            url_str = "%s://%s:%d%s" % (
                scheme.decode("ascii"),
                host.decode("ascii"),
                port,
                path.decode("ascii"),
            )

        try:
            response = self._pool.urlopen(
                method=method.decode(),
                url=url_str,
                headers={
                    key.decode("ascii"): value.decode("ascii") for key, value in headers
                },
                body=body,
                redirect=False,
                assert_same_host=False,
                retries=0,
                preload_content=False,
                chunked=chunked,
                timeout=urllib3_timeout,
                pool_timeout=timeout.get("pool"),
            )
        except (urllib3.exceptions.SSLError, socket.error) as exc:
            raise httpcore.NetworkError(exc)

        status_code = response.status
        reason_phrase = response.reason
        headers = list(response.headers.items())
        stream = URLLib3ByteStream(response)
        ext = {"reason": reason_phrase, "http_version": "HTTP/1.1"}

        return (status_code, headers, stream, ext)

    def close(self) -> None:
        self._pool.clear()


class URLLib3ProxyTransport(URLLib3Transport):
    def __init__(
        self,
        *,
        proxy_url: str,
        proxy_headers: dict = None,
        ssl_context: ssl.SSLContext = None,
        pool_connections: int = 10,
        pool_maxsize: int = 10,
        pool_block: bool = False,
    ) -> None:
        self._pool = urllib3.ProxyManager(
            proxy_url=proxy_url,
            proxy_headers=proxy_headers,
            ssl_context=ssl_context,
            num_pools=pool_connections,
            maxsize=pool_maxsize,
            block=pool_block,
        )

