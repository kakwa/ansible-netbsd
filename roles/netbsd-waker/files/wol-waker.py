#!/usr/pkg/bin/python3.12
"""waker: on-demand Wake-on-LAN helper for a target host.

Small HTTP service consumed by nginx through an ``auth_request``
subrequest. A request to ``/wake`` returns immediately when the target TCP
port is already accepting connections. Otherwise a magic packet is sent and
the request blocks until the target answers or the wake timeout expires.

Only the Python standard library is used, so no extra pkgsrc packages are
required beyond the interpreter.
"""

import argparse
import os
import signal
import socket
import sys
import syslog
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_PID_FILE = "/var/run/waker.pid"

_shutdown = threading.Event()
_use_syslog = False


def log(message, level=syslog.LOG_INFO):
    """Log to syslog in daemon mode, otherwise to stdout."""
    if _use_syslog:
        syslog.syslog(level, message)
    else:
        print(message, flush=True)


def parse_mac(mac):
    """Return the six raw bytes of a MAC address."""
    raw = mac.replace(":", "").replace("-", "").replace(".", "")
    if len(raw) != 12:
        raise ValueError("invalid MAC address: %r" % mac)
    try:
        return bytes.fromhex(raw)
    except ValueError:
        raise ValueError("invalid MAC address: %r" % mac)


def magic_packet(mac):
    """Build the standard 102-byte Wake-on-LAN magic packet."""
    mac_bytes = parse_mac(mac)
    return b"\xff" * 6 + mac_bytes * 16


def is_up(host, port, timeout=2.0):
    """Return True when a TCP connection to host:port succeeds."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def send_magic_packet(mac, broadcast, wol_port, target_ip=None, repeat=3):
    """Send the magic packet to the broadcast address (and target IP)."""
    packet = magic_packet(mac)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        for attempt in range(repeat):
            sock.sendto(packet, (broadcast, wol_port))
            if target_ip:
                try:
                    sock.sendto(packet, (target_ip, wol_port))
                except OSError:
                    pass
            if attempt + 1 < repeat:
                time.sleep(0.2)
    finally:
        sock.close()


def wait_until_up(host, port, timeout, poll_interval, retry=None,
                  retry_interval=0.0):
    """Poll host:port until it answers or timeout expires.

    ``retry`` is called every ``retry_interval`` seconds while waiting. It is
    used to resend the magic packet: a packet that arrives while the target is
    still entering suspend can be consumed as a pending wakeup, after which the
    kernel aborts the freeze and immediately re-enters suspend.
    """
    start = time.monotonic()
    deadline = start + timeout
    next_retry = start + retry_interval if retry and retry_interval > 0 else None
    while True:
        if is_up(host, port):
            return True
        now = time.monotonic()
        if now >= deadline:
            break
        if next_retry is not None and now >= next_retry:
            retry()
            next_retry = now + retry_interval
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(poll_interval, remaining))
    return is_up(host, port)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "waker/1.0"

    def log_message(self, fmt, *args):
        # nginx calls this endpoint on every proxied request, so keep the
        # access log quiet. Wake events are logged explicitly in _handle().
        return

    def do_GET(self):
        self._handle()

    def do_POST(self):
        self._handle()

    def do_HEAD(self):
        self._handle(head=True)

    def _reply(self, code, body, head=False):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if not head:
            self.wfile.write(data)

    def _handle(self, head=False):
        path = self.path.split("?", 1)[0]
        client = self.client_address[0] if self.client_address else "-"
        original_uri = self.headers.get("X-Original-URI") or "-"
        real_ip = self.headers.get("X-Real-IP") or "-"
        # Log every request so we can confirm nginx is reaching this endpoint
        # through its auth_request subrequest, and from which vhost/client.
        log(
            "request %s %s from %s (x-original-uri=%s x-real-ip=%s)"
            % (self.command, self.path, client, original_uri, real_ip)
        )

        if path == "/health":
            self._reply(200, "ok\n", head=head)
            return
        if path not in ("/wake", "/_wake", "/"):
            log("unknown path %s" % path, syslog.LOG_DEBUG)
            self._reply(404, "not found\n", head=head)
            return

        cfg = self.server.config
        check_host = cfg.target_ip or cfg.target_host

        # Do not gate on self.command: nginx issues auth_request subrequests
        # as GET even when the original request was a POST, so a "post-only"
        # check would skip every wake. Static PWA assets are served by
        # nginx directly and never reach this endpoint.
        if is_up(check_host, cfg.check_port):
            log(
                "target %s already up (check %s:%s)"
                % (cfg.target_host, check_host, cfg.check_port),
                syslog.LOG_DEBUG,
            )
            self._reply(200, "already up\n", head=head)
            return

        log(
            "target %s down (check %s:%s), sending magic packet"
            % (cfg.target_host, check_host, cfg.check_port)
        )
        try:
            send_magic_packet(
                cfg.mac, cfg.broadcast, cfg.wol_port, cfg.target_ip
            )
        except (OSError, ValueError) as exc:
            log("failed to send magic packet: %s" % exc, syslog.LOG_ERR)
            self._reply(500, "failed to send magic packet: %s\n" % exc, head=head)
            return

        def resend():
            log(
                "target %s still down, resending magic packet"
                % cfg.target_host,
                syslog.LOG_DEBUG,
            )
            try:
                send_magic_packet(
                    cfg.mac, cfg.broadcast, cfg.wol_port, cfg.target_ip
                )
            except (OSError, ValueError) as exc:
                log("failed to resend magic packet: %s" % exc, syslog.LOG_ERR)

        if wait_until_up(
            check_host,
            cfg.check_port,
            cfg.wake_timeout,
            cfg.poll_interval,
            retry=resend,
            retry_interval=cfg.wol_retry_interval,
        ):
            log("target %s is up" % cfg.target_host)
            self._reply(200, "awake\n", head=head)
        else:
            log(
                "target %s did not come up within %ss"
                % (cfg.target_host, cfg.wake_timeout),
                syslog.LOG_ERR,
            )
            self._reply(504, "wake timeout\n", head=head)


class WakeServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, handler, config):
        self.config = config
        super().__init__(address, handler)


def write_pid_file(path):
    with open(path, "w") as handle:
        handle.write("%d\n" % os.getpid())


def remove_pid_file(path):
    try:
        if os.path.exists(path):
            os.unlink(path)
    except OSError:
        pass


def daemonize():
    """Detach from the controlling terminal (double fork)."""
    if os.fork() > 0:
        os._exit(0)
    os.setsid()
    if os.fork() > 0:
        os._exit(0)
    os.chdir("/")
    os.umask(0o022)
    sys.stdout.flush()
    sys.stderr.flush()
    devnull = os.open(os.devnull, os.O_RDWR)
    os.dup2(devnull, 0)
    os.dup2(devnull, 1)
    os.dup2(devnull, 2)
    if devnull > 2:
        os.close(devnull)


def build_parser():
    parser = argparse.ArgumentParser(description="Wake-on-LAN helper")
    parser.add_argument("--daemon", action="store_true", help="run in background")
    parser.add_argument("--pid-file", default=DEFAULT_PID_FILE)
    parser.add_argument("--listen-addr", default="127.0.0.1")
    parser.add_argument("--listen-port", type=int, default=8099)
    parser.add_argument("--target-host", default="target.local")
    parser.add_argument("--target-ip", default="")
    parser.add_argument("--mac", default="", help="target MAC address")
    parser.add_argument("--check-port", type=int, default=443)
    parser.add_argument("--broadcast", default="255.255.255.255")
    parser.add_argument("--wol-port", type=int, default=9)
    parser.add_argument("--wake-timeout", type=float, default=90)
    parser.add_argument("--poll-interval", type=float, default=2)
    parser.add_argument(
        "--wol-retry-interval",
        type=float,
        default=5.0,
        help="resend the magic packet this often while waiting (0 disables)",
    )
    return parser


def main():
    global _use_syslog

    parser = build_parser()
    cfg = parser.parse_args()

    try:
        parse_mac(cfg.mac)
    except ValueError as exc:
        parser.error(str(exc))

    if cfg.daemon:
        daemonize()
        _use_syslog = True
        syslog.openlog("waker")

    def handle_signal(signum, _frame):
        log("received signal %d, shutting down" % signum)
        _shutdown.set()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    server = WakeServer((cfg.listen_addr, cfg.listen_port), Handler, cfg)
    if cfg.pid_file:
        write_pid_file(cfg.pid_file)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    log(
        "listening on %s:%d (target %s, MAC %s)"
        % (cfg.listen_addr, cfg.listen_port, cfg.target_host, cfg.mac)
    )

    try:
        while not _shutdown.wait(1.0):
            pass
    finally:
        server.shutdown()
        server.server_close()
        if cfg.pid_file:
            remove_pid_file(cfg.pid_file)
        log("stopped")

    return 0


if __name__ == "__main__":
    sys.exit(main())
