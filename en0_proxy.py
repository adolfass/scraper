#!/usr/bin/env python3
"""Minimal HTTP CONNECT proxy that binds all upstream sockets to en0.

The FSA registry blocks foreign IPs, and the system default route goes through
the VPN (utunX). Chromium/Playwright cannot bind a source interface directly, so
we point Chromium at this proxy and force every upstream connection out via the
physical interface (SRC_ADDR / first en* address).

Usage:
    .venv/bin/python en0_proxy.py [port]     # default 8899
"""
import os
import select
import socket
import socketserver
import subprocess
import sys


def detect_src():
    addr = os.environ.get("SRC_ADDR")
    if addr:
        return (addr, 0)
    for iface in ("en0", "en1", "en2", "en3"):
        try:
            ip = subprocess.check_output(
                ["ipconfig", "getifaddr", iface],
                stderr=subprocess.DEVNULL, timeout=5).decode().strip()
            if ip:
                return (ip, 0)
        except Exception:
            continue
    return None


SRC = detect_src()


def pump(a, b):
    """Bidirectional copy until either side closes."""
    socks = [a, b]
    try:
        while True:
            r, _, _ = select.select(socks, [], [], 60)
            if not r:
                break
            for s in r:
                data = s.recv(65536)
                if not data:
                    return
                (b if s is a else a).sendall(data)
    except Exception:
        pass


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        line = self.rfile.readline(65536).decode("latin1").strip()
        if not line:
            return
        parts = line.split()
        if len(parts) < 3:
            return
        method, target, _ = parts

        # drain headers
        while True:
            h = self.rfile.readline(65536)
            if h in (b"\r\n", b"\n", b""):
                break

        if method.upper() == "CONNECT":
            host, _, port = target.partition(":")
            port = int(port or 443)
            try:
                up = socket.create_connection((host, port), timeout=30,
                                              source_address=SRC)
            except Exception:
                self.wfile.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
                return
            self.wfile.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            self.wfile.flush()
            pump(self.connection, up)
            up.close()
        else:
            # plain HTTP: forward the original request line + headers + body
            host = target
            path = "/"
            if target.startswith("http://"):
                host = target[len("http://"):].split("/", 1)[0]
            else:
                path = target
                host = self.headers.get("Host") if self.headers else None
            if not host:
                return
            host, _, port = host.partition(":")
            port = int(port or 80)
            try:
                up = socket.create_connection((host, port), timeout=30,
                                              source_address=SRC)
            except Exception:
                self.wfile.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
                return
            up.sendall((f"{method} {path} HTTP/1.1\r\n").encode())
            for k, v in self.headers.items():
                up.sendall(f"{k}: {v}\r\n".encode())
            up.sendall(b"\r\n")
            pump(self.connection, up)
            up.close()


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8899
    print(f"en0 proxy on 127.0.0.1:{port}  src={SRC}", flush=True)
    Server(("127.0.0.1", port), Handler).serve_forever()
