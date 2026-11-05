# NetBSD waker Role

The optional `netbsd-waker` role lets nginx wake a target host on demand
instead of leaving it powered on. It installs a small stdlib-only Python HTTP
service (`/usr/pkg/bin/wol-waker.py`, `waker` rc.d script) bound to
`127.0.0.1:8099`.

## Usage

Enable it on a reverse proxy entry:

```yaml
- name: "wol"
  domain: "wol.example.com"
  upstream: "https://target.local/"
  wake_enabled: true
```

With `wake_enabled: true`, the generated vhost adds `auth_request /_wake;`
before `proxy_pass`. nginx calls the waker for every request:

- if the target host already accepts connections, the check returns immediately
  and the request is proxied normally;
- otherwise the waker sends a Wake-on-LAN magic packet (broadcast UDP/9 plus a
  unicast copy to `waker_target_ip`) and waits up to `waker_wake_timeout`
  seconds for the host to answer before nginx continues.

## Role Variables

Variables (see `defaults/main.yml`):

| Variable | Default | Description |
| --- | --- | --- |
| `waker_enable` | `true` | Install/enable the service |
| `waker_target_mac` | *(empty)* | **Required.** MAC of the NIC to wake |
| `waker_target_host` | `target.local` | Target hostname |
| `waker_target_ip` | `192.168.1.20` | Target IP used for the reachability check |
| `waker_check_port` | `443` | TCP port used to detect the host is up |
| `waker_broadcast` | `255.255.255.255` | Magic packet destination |
| `waker_wol_port` | `9` | Magic packet UDP port |
| `waker_wake_timeout` | `90` | Seconds to wait for the host to wake |
| `waker_wake_poll_interval` | `2` | Poll interval while waking |
| `waker_listen_addr` | `127.0.0.1` | Local listen address |
| `waker_listen_port` | `8099` | Local listen port |

The role refuses to run if the MAC is missing. Set it in the playbook, e.g.:

```yaml
- role: netbsd-waker
  vars:
    waker_target_mac: "{{ vault_wol_mac }}"
```

## nginx Integration

The wake endpoint can be tuned from the `netbsd-nginx` defaults with
`nginx_waker_url` (default `http://127.0.0.1:8099/wake`) and
`nginx_waker_timeout` (default `120` seconds).
