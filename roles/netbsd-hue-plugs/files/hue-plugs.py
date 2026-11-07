#!/usr/bin/env python3
"""hue-plugs.py -- control Philips Hue smart plugs over the Hue API.

A stdlib-only CLI tool (no external packages) that manages a set of
Hue smart plugs on the local network.  It reads a small JSON config
file describing the bridge, the client key and the plug names, then
issues GET/PUT requests to the Hue API to turn plugs on/off and to
list their state.

Usage:
    hue-plugs.py list
    hue-plugs.py stop <name|all>
    hue-plugs.py start <name|all>
    hue-plugs.py restart <name|all>
    hue-plugs.py warning --duration 30 <name>
    hue-plugs.py critical --duration 60 <name>
    hue-plugs.py transition <name> --on --hue H --sat S --bri B --duration D
    hue-plugs.py autofill [--save]
    hue-plugs.py setup [--bridge-ip IP] [--save]

Add --debug (or set HUE_PLUGS_DEBUG=1) to dump the raw HTTP requests and
responses to stderr.  The client key is masked in the logged URL.

Config file (JSON, default /etc/hue-plugs.conf, override with --config
or the HUE_PLUGS_CONFIG environment variable):

    {
        "bridge_ip": "192.168.0.10",
        "client_key": "abcdef1234567890abcdef1234567890",
        "restart_delay": 15,
        "plugs": [
            {"id": "1", "name": "pc1"},
            {"id": "2", "name": "pc2"}
        ]
    }

The Hue API used:
    GET  /api/<key>/lights
    GET  /api/<key>/groups
    PUT  /api/<key>/lights/<id>/state   body: {"on": true|false}
    POST /api/                          body: {}   (pairing / setup)

Bridge discovery uses a raw mDNS PTR query for _hue._tcp.local (UDP
multicast 224.0.0.251:5353), implemented with stdlib sockets only.

Exit codes:
    0  all commands succeeded
    1  one or more commands failed (details printed to stderr)
"""

from __future__ import annotations

import argparse
import json
import math
import os
import select
import socket
import struct
import sys
import time
import urllib.error
import urllib.request

DEFAULT_CONFIG = "/etc/hue-plugs.conf"
TIMEOUT = 5  # seconds per HTTP request
PAIR_DEVICETYPE = "hue-plugs#netbsd"  # required by the Hue pairing API

# Alert animation timing: one full colour cycle takes ALERT_HUE_PERIOD
# seconds, one full brightness cycle takes ALERT_BRI_PERIOD seconds,
# and one request is issued every ALERT_STEP seconds.
ALERT_HUE_PERIOD = 2.0
ALERT_BRI_PERIOD = 1.5
ALERT_STEP = 0.25

DEBUG = False


def debug(msg: str) -> None:
    """Print *msg* to stderr when debug mode is enabled."""
    if DEBUG:
        print(msg, file=sys.stderr, flush=True)


class HuePlugsError(Exception):
    """Raised when the Hue bridge is unreachable or returns an error."""


def load_config(path: str, require_plugs: bool = True) -> dict:
    """Load and validate the JSON config file.

    When *require_plugs* is False (used by ``autofill``), the ``plugs`` key
    may be absent or empty -- autofill regenerates it from the bridge.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            cfg = json.load(fh)
    except FileNotFoundError:
        raise HuePlugsError(f"config file not found: {path}")
    except json.JSONDecodeError as exc:
        raise HuePlugsError(f"invalid JSON in {path}: {exc}")

    for field in ("bridge_ip", "client_key"):
        if field not in cfg:
            raise HuePlugsError(f"missing key in config: {field!r}")

    if require_plugs:
        if "plugs" not in cfg:
            raise HuePlugsError("missing key in config: 'plugs'")
        if not isinstance(cfg["plugs"], list) or not cfg["plugs"]:
            raise HuePlugsError("'plugs' must be a non-empty list")
        for plug in cfg["plugs"]:
            if "id" not in plug or "name" not in plug:
                raise HuePlugsError(
                    f"each plug needs 'id' and 'name': {plug!r}"
                )

    cfg.setdefault("restart_delay", 15)
    return cfg


def api_request(bridge_ip: str, client_key: str, method: str,
                path: str, body: dict | None = None) -> dict:
    """Issue an HTTP request to the Hue bridge and return parsed JSON.

    *client_key* may be empty for unauthenticated endpoints (e.g. the
    pairing endpoint at /api/).  In debug mode the raw request and the raw
    response (including the body of HTTP error responses) are dumped to
    stderr; the client key is masked in the logged URL.
    """
    if client_key:
        url = f"http://{bridge_ip}/api/{client_key}{path}"
        shown_url = f"http://{bridge_ip}/api/<client-key>{path}"
    else:
        url = f"http://{bridge_ip}/api{path}"
        shown_url = url
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, method=method,
                                 headers=headers)
    debug(f">>> {method} {shown_url}")
    if headers:
        debug(f">>> headers: {headers}")
    if data is not None:
        debug(f">>> body: {data.decode('utf-8')}")

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
            debug(f"<<< {resp.status} {resp.reason}")
            debug(f"<<< headers: {dict(resp.headers)}")
            debug(f"<<< body: {raw.decode('utf-8', errors='replace')}")
            try:
                return json.loads(raw)
            except json.JSONDecodeError as exc:
                raise HuePlugsError(
                    f"invalid JSON from bridge {bridge_ip} "
                    f"{method} {path}: {exc}"
                ) from exc
    except urllib.error.HTTPError as exc:
        err_body = exc.read()
        debug(f"<<< {exc.code} {exc.reason}")
        debug(f"<<< headers: {dict(exc.headers)}")
        debug(f"<<< body: {err_body.decode('utf-8', errors='replace')}")
        raise HuePlugsError(
            f"HTTP {exc.code} from bridge {bridge_ip} {method} {path}"
        ) from exc
    except urllib.error.URLError as exc:
        debug(f"!!! connection failed: {exc.reason}")
        raise HuePlugsError(
            f"cannot reach Hue bridge at {bridge_ip}: {exc.reason}"
        ) from exc


def _dns_read_name(data: bytes, offset: int) -> tuple:
    """Read a DNS name from *data* at *offset*, following compression
    pointers.  Returns (name, offset_after_name)."""
    labels = []
    next_offset = None
    jumps = 0
    while True:
        if jumps > 20:
            raise ValueError("DNS name compression loop")
        if offset >= len(data):
            raise ValueError("DNS name extends past end of packet")
        length = data[offset]
        if length == 0:
            if next_offset is None:
                next_offset = offset + 1
            break
        if (length & 0xC0) == 0xC0:
            if next_offset is None:
                next_offset = offset + 2
            if offset + 1 >= len(data):
                raise ValueError("truncated DNS compression pointer")
            pointer = ((length & 0x3F) << 8) | data[offset + 1]
            offset = pointer
            jumps += 1
            continue
        if offset + 1 + length > len(data):
            raise ValueError("truncated DNS label")
        labels.append(
            data[offset + 1:offset + 1 + length].decode("ascii",
                                                        errors="replace")
        )
        offset += 1 + length
    return ".".join(labels), next_offset if next_offset is not None else offset


def _build_mdns_query(service_type: str) -> bytes:
    """Build a raw mDNS PTR query packet for *service_type*."""
    header = struct.pack("!HHHHHH", 0, 0, 1, 0, 0, 0)
    qname = b""
    for label in service_type.rstrip(".").split("."):
        encoded = label.encode("ascii")
        if len(encoded) > 63:
            raise ValueError(f"DNS label too long: {label!r}")
        qname += bytes([len(encoded)]) + encoded
    qname += b"\x00"
    # QTYPE PTR (12), QCLASS IN (1)
    return header + qname + struct.pack("!HH", 12, 1)


def _parse_mdns_response(data: bytes) -> list:
    """Parse an mDNS response, returning a list of (hostname, ipv4) tuples
    taken from A records."""
    if len(data) < 12:
        return []
    # DNS header: ID(0-1) FLAGS(2-3) QDCOUNT(4-5) ANCOUNT(6-7) NSCOUNT(8-9) ARCOUNT(10-11)
    qdcount = struct.unpack("!H", data[4:6])[0]
    ancount = struct.unpack("!H", data[6:8])[0]
    ncount = struct.unpack("!H", data[8:10])[0]
    arcount = struct.unpack("!H", data[10:12])[0]

    offset = 12
    try:
        for _ in range(qdcount):
            _, offset = _dns_read_name(data, offset)
            offset += 4  # QTYPE + QCLASS
        results = []
        for _ in range(ancount + ncount + arcount):
            name, offset = _dns_read_name(data, offset)
            if offset + 10 > len(data):
                break
            rtype, _rclass, _ttl, rdlength = struct.unpack(
                "!HHIH", data[offset:offset + 10])
            offset += 10
            if offset + rdlength > len(data):
                break
            rdata = data[offset:offset + rdlength]
            offset += rdlength
            if rtype == 1 and rdlength == 4:
                results.append((name, socket.inet_ntoa(rdata)))
        return results
    except (ValueError, IndexError, struct.error):
        return []


def mdns_discover(timeout: float = 3.0) -> list:
    """Discover Hue bridges on the local network via mDNS.

    Queries _hue._tcp.local and collects A records.  Returns a list of
    (ip, name) tuples, empty when nothing is found.  Requires multicast
    to work on the default interface; falls back silently (returns [])
    if the socket cannot be set up.
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except (AttributeError, OSError):
            pass
        try:
            sock.bind(("", 5353))
        except OSError:
            sock.bind(("", 0))
        mreq = struct.pack("4s4s", socket.inet_aton("224.0.0.251"),
                           socket.inet_aton("0.0.0.0"))
        try:
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                            mreq)
        except OSError:
            pass
    except OSError:
        return []

    query = _build_mdns_query("_hue._tcp.local")
    found = {}
    try:
        # mDNS spec: send 3 queries spaced 0.25-250 ms apart; use 0.5 s
        for i in range(3):
            try:
                sock.sendto(query, ("224.0.0.251", 5353))
            except OSError:
                break
            if i < 2:
                time.sleep(0.5)

        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                ready, _, _ = select.select([sock], [], [],
                                            max(0.1, deadline - time.time()))
            except (OSError, ValueError):
                break
            if not ready:
                continue
            try:
                data, _addr = sock.recvfrom(65535)
            except OSError:
                break
            for name, ip in _parse_mdns_response(data):
                if name.endswith("._hue._tcp.local"):
                    name = name[: -len("._hue._tcp.local")]
                found.setdefault(ip, name)
    finally:
        sock.close()

    return list(found.items())


def get_lights(cfg: dict) -> list:
    """Return the list of all lights from the bridge."""
    raw = api_request(cfg["bridge_ip"], cfg["client_key"],
                      "GET", "/lights")
    # Response is a dict keyed by light ID
    lights = []
    for light_id, state in raw.items():
        lights.append({
            "id": light_id,
            "name": state.get("name", light_id),
            "on": state.get("state", {}).get("on", False),
            "type": state.get("type", "unknown"),
        })
    return lights


def get_groups(cfg: dict) -> list:
    """Return the bridge's groups (rooms, zones, lights) from ``GET /groups``.

    Each entry is ``{id, name, type, device_ids}``.  Rooms and zones are the
    useful ones: they tell you which room a given device sits in, which is
    handy when naming plugs.  Returns an empty list when the bridge does not
    expose groups (some firmware) so callers can degrade gracefully.
    """
    try:
        raw = api_request(cfg["bridge_ip"], cfg["client_key"],
                          "GET", "/groups")
    except HuePlugsError:
        return []
    groups = []
    for gid, gstate in raw.items():
        # Firmware-dependent key for member lights: newer firmware
        # exposes "lights" (a list of light id strings), older ones
        # "device_ids".  Accept both.
        ids = gstate.get("lights", gstate.get("device_ids", []))
        groups.append({
            "id": gid,
            "name": gstate.get("name", gid),
            "type": gstate.get("type", "unknown"),
            "device_ids": [str(d) for d in ids],
        })
    return groups


def rooms_by_light_id(groups: list) -> dict:
    """Map each light id to the room it belongs to.

    Only groups of type ``room`` (and, failing that, ``zone``) are used.  A
    light that appears in several rooms is reported as ``"a / b"``.  Lights in
    no room map to ``""``.
    """
    # Firmware-dependent type casing: newer firmware reports "Room"/
    # "Zone", older ones lowercase "room"/"zone".
    room_ids = [g for g in groups if g["type"].lower() == "room"]
    if not room_ids:
        room_ids = [g for g in groups if g["type"].lower() == "zone"]
    result = {}
    for g in room_ids:
        for dev in g["device_ids"]:
            result.setdefault(dev, []).append(g["name"])
    return {k: " / ".join(v) for k, v in result.items()}


def set_plug_on(cfg: dict, plug_id: str, on: bool) -> bool:
    """Set a single plug to on/off.  Returns True on success."""
    body = {"on": on}
    api_request(cfg["bridge_ip"], cfg["client_key"],
                "PUT", f"/lights/{plug_id}/state", body=body)
    return True


def _get_light_state(cfg: dict, light_id: str) -> dict:
    """Return the current state dict of a single light."""
    raw = api_request(cfg["bridge_ip"], cfg["client_key"],
                      "GET", f"/lights/{light_id}")
    if isinstance(raw, dict):
        # Firmware-dependent response shape: some bridges return the
        # light object directly ("state" at the top level), others a
        # dict keyed by light id.
        if "state" in raw:
            return raw["state"]
        if light_id in raw:
            return raw[light_id].get("state", {})
    if isinstance(raw, list):
        for entry in raw:
            err = entry.get("error") if isinstance(entry, dict) else None
            if err:
                raise HuePlugsError(
                    f"bridge error for light {light_id}: "
                    f"{err.get('description', 'unknown')}"
                )
    raise HuePlugsError(f"unexpected response for light {light_id}")


def _restore_light_state(cfg: dict, light_id: str, saved: dict) -> None:
    """Restore a light to its previously captured state."""
    body: dict = {}
    if not saved.get("on", False):
        body["on"] = False
    else:
        body["on"] = True
        if saved.get("bri") is not None:
            body["bri"] = saved["bri"]
        if saved.get("hue") is not None and saved.get("sat") is not None:
            body["hue"] = saved["hue"]
            body["sat"] = saved["sat"]
        elif saved.get("ct") is not None:
            body["ct"] = saved["ct"]
    api_request(cfg["bridge_ip"], cfg["client_key"],
                "PUT", f"/lights/{light_id}/state", body=body)


def _get_group_action(cfg: dict, group_id: str) -> dict:
    """Return the current action dict of a group from the bridge."""
    raw = api_request(cfg["bridge_ip"], cfg["client_key"],
                      "GET", f"/groups/{group_id}")
    if isinstance(raw, dict) and "action" in raw:
        return raw["action"]
    if isinstance(raw, list):
        for entry in raw:
            err = entry.get("error") if isinstance(entry, dict) else None
            if err:
                raise HuePlugsError(
                    f"bridge error for group {group_id}: "
                    f"{err.get('description', 'unknown')}"
                )
    raise HuePlugsError(f"unexpected response for group {group_id}")


def _restore_group_action(cfg: dict, group_id: str, saved: dict) -> None:
    """Restore a group's action to its previously captured state."""
    body: dict = {}
    if not saved.get("on", False):
        body["on"] = False
    else:
        body["on"] = True
        if saved.get("bri") is not None:
            body["bri"] = saved["bri"]
        if saved.get("hue") is not None and saved.get("sat") is not None:
            body["hue"] = saved["hue"]
            body["sat"] = saved["sat"]
        elif saved.get("ct") is not None:
            body["ct"] = saved["ct"]
    api_request(cfg["bridge_ip"], cfg["client_key"],
                "PUT", f"/groups/{group_id}/action", body=body)


def _animate(cfg: dict, kind: str, target_id: str,
             duration: int, hue_a: int, hue_b: int,
             sat: int, bri_lo: int, bri_hi: int, label: str) -> None:
    """Run the colour animation loop for *duration* seconds.

    *kind* is "light" or "group".  Hue oscillates between *hue_a* and
    *hue_b* with a full cycle every ALERT_HUE_PERIOD seconds; brightness
    oscillates between *bri_lo* and *bri_hi* with a full cycle every
    ALERT_BRI_PERIOD seconds.  *sat* is fixed.  Both waves are driven
    from the wall clock so the motion stays periodic no matter how long
    the alert runs.
    """
    # Capture state before animating
    if kind == "light":
        saved = _get_light_state(cfg, target_id)
    else:
        saved = _get_group_action(cfg, target_id)

    # Ensure the light/group is on with full sat
    base_body = {"on": True, "sat": sat}
    try:
        start = time.monotonic()
        while True:
            now = time.monotonic()
            elapsed = now - start
            if elapsed >= duration:
                break
            # Full sine cycles (-1..1) mapped to 0..1, independent
            # periods for colour and brightness.
            hue_frac = 0.5 + 0.5 * math.sin(
                2.0 * math.pi * elapsed / ALERT_HUE_PERIOD)
            bri_frac = 0.5 + 0.5 * math.sin(
                2.0 * math.pi * elapsed / ALERT_BRI_PERIOD)
            hue = int(hue_a + (hue_b - hue_a) * hue_frac)
            bri = int(bri_lo + (bri_hi - bri_lo) * bri_frac)
            body = {**base_body, "hue": hue, "bri": bri,
                    "transitiontime": 10}  # 100 ms transition
            if kind == "light":
                api_request(cfg["bridge_ip"], cfg["client_key"],
                            "PUT", f"/lights/{target_id}/state", body=body)
            else:
                api_request(cfg["bridge_ip"], cfg["client_key"],
                            "PUT", f"/groups/{target_id}/action", body=body)
            # Sleep until the next step (accounts for request time).
            next_t = start + (int(elapsed / ALERT_STEP) + 1) * ALERT_STEP
            time.sleep(max(0.05, next_t - time.monotonic()))
    finally:
        # Always restore previous state, even on error
        if kind == "light":
            _restore_light_state(cfg, target_id, saved)
        else:
            _restore_group_action(cfg, target_id, saved)
        print(f"  restored previous state for {label}")


def resolve_targets(cfg: dict, name: str) -> list:
    """Resolve a user-supplied name ('all' or a plug name) to plug dicts.

    Returns a list of plug dicts from the config.
    """
    if name == "all":
        return cfg["plugs"]
    matches = [p for p in cfg["plugs"] if p["name"] == name]
    if not matches:
        known = ", ".join(p["name"] for p in cfg["plugs"])
        raise HuePlugsError(
            f"unknown plug name {name!r}. Known: {known}"
        )
    return matches


def resolve_alert_target(cfg: dict, name: str) -> tuple:
    """Resolve *name* to (kind, target_id, label) for alert commands.

    Matches first against configured plug names, then against group/room
    names from the bridge.  Returns:
        ("light", plug_id, plug_name)  or
        ("group", group_id, group_name)
    """
    # Try plug names first
    for plug in cfg.get("plugs", []):
        if plug["name"] == name:
            return ("light", str(plug["id"]), plug["name"])

    # Try group/room names from the bridge
    groups = get_groups(cfg)
    for g in groups:
        if g["name"] == name:
            return ("group", g["id"], g["name"])

    # Not found -- give a helpful error
    plug_names = ", ".join(p["name"] for p in cfg.get("plugs", []))
    group_names = ", ".join(g["name"] for g in groups)
    raise HuePlugsError(
        f"unknown target {name!r}.\n"
        f"  plugs:  {plug_names or '(none)'}\n"
        f"  groups: {group_names or '(none)'}"
    )


def cmd_alert(cfg: dict, args: argparse.Namespace, severity: str) -> int:
    """Run a warning or critical alert animation on a target.

    *severity* is "warning" or "critical".
    """
    kind, target_id, label = resolve_alert_target(cfg, args.name)
    duration = args.duration

    if severity == "warning":
        # Orange, oscillating slightly toward yellow.  The Hue scale
        # 0-65535 maps to 0-360 deg: orange ~5000 (27 deg), a slightly
        # yellower orange ~7000 (38 deg).
        hue_a, hue_b = 5000, 7000
        bri_lo, bri_hi = 80, 254
        sat = 200
        desc = f"warning ({duration}s, orange→yellow-orange)"
    else:
        # Purple -> Red.  Purple ~49152 (270 deg); red is the top of
        # the scale, 65535 (360 deg), so the oscillation sweeps through
        # magenta rather than the long way round the colour wheel.
        hue_a, hue_b = 49152, 65535
        bri_lo, bri_hi = 100, 254
        sat = 230
        desc = f"critical ({duration}s, purple→red)"

    print(f"  {desc} on {label} ({kind} {target_id})")
    _animate(cfg, kind, target_id, duration,
             hue_a, hue_b, sat, bri_lo, bri_hi, label)
    return 0


def cmd_list(cfg: dict) -> int:
    """Print the state of all configured plugs."""
    lights = get_lights(cfg)
    light_by_id = {l["id"]: l for l in lights}

    print(f"{'NAME':<20} {'HUE ID':<10} {'STATE':<8} {'ON':<6} {'TYPE'}")
    print("-" * 58)
    for plug in cfg["plugs"]:
        pid = str(plug["id"])
        light = light_by_id.get(pid)
        if light is None:
            print(f"{plug['name']:<20} {pid:<10} {'MISSING':<8} {'?':<6} "
                  f"not found on bridge")
            continue
        state = "ON" if light["on"] else "OFF"
        print(f"{plug['name']:<20} {pid:<10} {state:<8} "
              f"{'yes' if light['on'] else 'no':<6} {light['type']}")
    return 0


def cmd_stop(cfg: dict, name: str) -> int:
    """Turn off the named plug(s)."""
    targets = resolve_targets(cfg, name)
    failed = 0
    for plug in targets:
        try:
            set_plug_on(cfg, str(plug["id"]), on=False)
            print(f"  off   {plug['name']} (id {plug['id']})")
        except HuePlugsError as exc:
            print(f"  ERROR {plug['name']}: {exc}", file=sys.stderr)
            failed += 1
    return 1 if failed else 0


def cmd_start(cfg: dict, name: str) -> int:
    """Turn on the named plug(s)."""
    targets = resolve_targets(cfg, name)
    failed = 0
    for plug in targets:
        try:
            set_plug_on(cfg, str(plug["id"]), on=True)
            print(f"  on    {plug['name']} (id {plug['id']})")
        except HuePlugsError as exc:
            print(f"  ERROR {plug['name']}: {exc}", file=sys.stderr)
            failed += 1
    return 1 if failed else 0


def cmd_restart(cfg: dict, name: str) -> int:
    """Restart the named plug(s): off, wait, on."""
    targets = resolve_targets(cfg, name)
    delay = int(cfg.get("restart_delay", 15))
    failed = 0

    # Phase 1: turn everything off
    for plug in targets:
        try:
            set_plug_on(cfg, str(plug["id"]), on=False)
            print(f"  off   {plug['name']} (id {plug['id']})")
        except HuePlugsError as exc:
            print(f"  ERROR {plug['name']}: {exc}", file=sys.stderr)
            failed += 1

    if failed:
        return 1

    print(f"  waiting {delay}s ...")
    time.sleep(delay)

    # Phase 2: turn everything back on
    for plug in targets:
        try:
            set_plug_on(cfg, str(plug["id"]), on=True)
            print(f"  on    {plug['name']} (id {plug['id']})")
        except HuePlugsError as exc:
            print(f"  ERROR {plug['name']}: {exc}", file=sys.stderr)
            failed += 1

    return 1 if failed else 0


def cmd_autofill(cfg: dict, args: argparse.Namespace) -> int:
    """Discover every light on the bridge and emit a ready-to-paste
    ``hue_plugs`` list.

    Devices already present in the config keep their (user-chosen) name;
    newly discovered devices are added under the name the bridge gave
    them.  The printed YAML block is meant to be pasted into the Ansible
    playbook's ``hue_plugs`` variable; with --save the regenerated list is
    also written back to the local config file.
    """
    lights = get_lights(cfg)
    rooms = rooms_by_light_id(get_groups(cfg))
    existing_names = {str(p["id"]): p["name"]
                      for p in cfg.get("plugs", []) or []}

    rows = []
    for light in lights:
        lid = str(light["id"])
        rows.append({
            "id": lid,
            "name": existing_names.get(lid, light["name"]),
            "type": light["type"],
            "room": rooms.get(lid, ""),
        })

    def sort_key(row):
        return (0, int(row["id"])) if row["id"].isdigit() else (1, row["id"])
    rows.sort(key=sort_key)

    print(f"discovered {len(rows)} device(s) on the bridge\n")
    print(f"{'HUE ID':<10} {'NAME':<20} {'ROOM':<20} TYPE")
    print("-" * 70)
    for row in rows:
        room = row["room"] if row["room"] else "-"
        print(f"{row['id']:<10} {row['name']:<20} {room:<20} {row['type']}")

    print("\npaste this into your Ansible playbook:")
    print("  hue_plugs:")
    for row in rows:
        print(f'    - id: "{row["id"]}"')
        print(f'      name: "{row["name"]}"')

    if args.save:
        cfg["plugs"] = [{"id": row["id"], "name": row["name"]}
                        for row in rows]
        with open(args.config, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=4)
            fh.write("\n")
        print(f"\nsaved {len(rows)} plug(s) to {args.config}")

    return 0


def cmd_setup(args: argparse.Namespace) -> int:
    """Discover the bridge (mDNS or --bridge-ip) and pair with it.

    Pairs by POSTing to the unauthenticated /api/ endpoint: the first
    call reports "press the link button", and once the button has been
    pressed a subsequent call returns the client key ("username").
    """
    bridge_ip = args.bridge_ip

    if not bridge_ip:
        print("Searching for a Hue bridge via mDNS ...")
        found = mdns_discover()
        if not found:
            print("no Hue bridge found on the network", file=sys.stderr)
            print("run again with --bridge-ip <ip> to pair manually",
                  file=sys.stderr)
            return 1
        for ip, name in found:
            print(f"  found: {ip} ({name})")
        if len(found) == 1:
            bridge_ip = found[0][0]
        else:
            choice = input("which bridge? [1]: ").strip() or "1"
            try:
                bridge_ip = found[int(choice) - 1][0]
            except (ValueError, IndexError):
                print("invalid choice", file=sys.stderr)
                return 1

    print(f"\npairing with bridge at {bridge_ip}")
    print("Press the link button on the Hue bridge now.")
    print("Waiting up to 60 s ...")

    username = None
    deadline = time.time() + 60
    body = {"devicetype": PAIR_DEVICETYPE}
    while time.time() < deadline and not username:
        try:
            raw = api_request(bridge_ip, "", "POST", "/", body=body)
        except HuePlugsError as exc:
            debug(f"pairing request failed: {exc}")
            raw = None
        if isinstance(raw, list):
            for entry in raw:
                if not isinstance(entry, dict):
                    continue
                if "success" in entry:
                    username = entry["success"].get("username")
                    break
                err = entry.get("error")
                if not isinstance(err, dict):
                    continue
                etype = err.get("type")
                description = err.get("description", "unknown error")
                if etype == 101:
                    # Link button not pressed yet -- keep polling.
                    continue
                if etype == 120:
                    print("bridge has too many registered clients",
                          file=sys.stderr)
                    print("delete one in the Hue app, then retry",
                          file=sys.stderr)
                    return 1
                print(f"pairing failed: {description} "
                      f"(error type {etype})", file=sys.stderr)
                return 1
        if not username:
            time.sleep(2)

    if not username:
        print("pairing timed out -- make sure the link button was pressed",
              file=sys.stderr)
        return 1

    print(f"\npaired. client key: {username}")
    print(f"bridge ip:      {bridge_ip}")

    if args.save:
        try:
            with open(args.config, encoding="utf-8") as fh:
                cfg = json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            cfg = {}
        cfg["bridge_ip"] = bridge_ip
        cfg["client_key"] = username
        cfg.setdefault("restart_delay", 15)
        cfg.setdefault("plugs", [])
        with open(args.config, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=4)
            fh.write("\n")
        print(f"saved to {args.config}")

    print("\nfor the Ansible vault:")
    print(f'  vault_hue_bridge_ip: "{bridge_ip}"')
    print(f'  vault_hue_client_key: "{username}"')
    return 0


def build_parser() -> argparse.ArgumentParser:
    # Defined on both the main parser and every subparser so that --debug
    # works before or after the command.  SUPPRESS avoids one parser
    # clobbering the value set by the other.
    debug_opt = argparse.ArgumentParser(add_help=False)
    debug_opt.add_argument(
        "--debug",
        action="store_true",
        default=argparse.SUPPRESS,
        help="dump raw HTTP requests and responses to stderr",
    )

    parser = argparse.ArgumentParser(
        prog="hue-plugs.py",
        description="Control Philips Hue smart plugs over the Hue API.",
        parents=[debug_opt],
    )
    parser.add_argument(
        "--config",
        default=os.environ.get("HUE_PLUGS_CONFIG", DEFAULT_CONFIG),
        help=f"Path to JSON config file (default: {DEFAULT_CONFIG})",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="show state of all configured plugs",
                   parents=[debug_opt])

    for cmd in ("stop", "start", "restart"):
        p = sub.add_parser(cmd, help=f"{cmd} a plug or all plugs",
                           parents=[debug_opt])
        p.add_argument(
            "name",
            help="plug name (e.g. 'pc1') or 'all'",
        )

    p = sub.add_parser(
        "autofill",
        help="list all bridge lights and print a pasteable hue_plugs list",
        parents=[debug_opt],
    )
    p.add_argument(
        "--save",
        action="store_true",
        help="also write the discovered plugs back to the config file",
    )

    for cmd, default_dur, desc in (
        ("warning", 30, "animate yellow→orange alert on a light or room"),
        ("critical", 60, "animate orange→red alert on a light or room"),
    ):
        p = sub.add_parser(cmd, help=desc, parents=[debug_opt])
        p.add_argument(
            "--duration",
            type=int,
            default=default_dur,
            help=f"alert duration in seconds (default: {default_dur})",
        )
        p.add_argument(
            "name",
            help="plug name or room/group name",
        )

    p = sub.add_parser(
        "setup",
        help="discover the bridge (mDNS) and pair (press link button)",
        parents=[debug_opt],
    )
    p.add_argument(
        "--bridge-ip",
        default=None,
        help="bridge IP; skip mDNS discovery",
    )
    p.add_argument(
        "--save",
        action="store_true",
        help="write bridge_ip and client_key into the config file",
    )
    return parser


def main(argv: list | None = None) -> int:
    global DEBUG

    parser = build_parser()
    args = parser.parse_args(argv)

    env_debug = os.environ.get("HUE_PLUGS_DEBUG", "").strip().lower()
    DEBUG = (bool(getattr(args, "debug", False))
             or env_debug in ("1", "true", "yes", "on"))

    # setup works without a complete config file
    if args.command == "setup":
        return cmd_setup(args)

    # autofill regenerates the plug list, so an empty/missing one is fine
    require_plugs = args.command != "autofill"

    try:
        cfg = load_config(args.config, require_plugs=require_plugs)
    except HuePlugsError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 1

    try:
        if args.command == "list":
            return cmd_list(cfg)
        if args.command == "stop":
            return cmd_stop(cfg, args.name)
        if args.command == "start":
            return cmd_start(cfg, args.name)
        if args.command == "restart":
            return cmd_restart(cfg, args.name)
        if args.command == "warning":
            return cmd_alert(cfg, args, "warning")
        if args.command == "critical":
            return cmd_alert(cfg, args, "critical")
        if args.command == "autofill":
            return cmd_autofill(cfg, args)
    except HuePlugsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
