# NetBSD Hue Plugs Role

Installs a stdlib-only Python CLI (`/usr/pkg/bin/hue-plugs.py`) for
controlling Philips Hue smart plugs on a NetBSD host. No daemon or rc.d
service is involved -- the tool talks to the Hue bridge on demand through
the standard Hue HTTP API.

## Usage

```sh
hue-plugs.py list              # show state of all configured plugs
hue-plugs.py stop ai           # power off the plug named "ai"
hue-plugs.py start ai          # power on the plug named "ai"
hue-plugs.py restart ai        # off, wait, on (restart the device)
hue-plugs.py stop all          # power off every configured plug
hue-plugs.py autofill          # list every bridge device + room, print pasteable hue_plugs
hue-plugs.py autofill --save   # also rewrite the local config's plug list
hue-plugs.py setup --save      # discover bridge via mDNS, pair, save to config
```

The script reads a JSON config file (default `/etc/hue-plugs.conf`,
overridable with `--config` or the `HUE_PLUGS_CONFIG` environment variable).

Add `--debug` (or set `HUE_PLUGS_DEBUG=1`) to dump every raw HTTP request
and response to stderr.  This is useful when pairing or when the bridge
returns an unexpected answer.  The client key is masked in the logged URL.

## Role Variables

Variables (see `defaults/main.yml`):

| Variable | Default | Description |
| --- | --- | --- |
| `hue_plugs_enable` | `true` | Install the script and config |
| `hue_bridge_ip` | *(empty)* | **Required.** Hue bridge IP address |
| `hue_client_key` | *(empty)* | **Required.** Hue client key (paired username) |
| `hue_plugs` | `[]` | **Required.** List of `{id, name}` plug entries |
| `hue_restart_delay` | `15` | Seconds to wait between off and on during `restart` |
| `hue_config_file` | `/etc/hue-plugs.conf` | Config file path on the target |
| `hue_script_path` | `/usr/pkg/bin/hue-plugs.py` | Script install path |
| `hue_python` | `/usr/pkg/bin/python3.12` | Python interpreter (used in shebang) |
| `hue_packages` | `[python312]` | pkgsrc packages to install |

## Playbook Usage

The bridge IP and client key are secrets. They can be set from vault, or
dropped in one-line files next to the playbook (same pattern as the OVH
DNS tokens); vault values take precedence when set:

```yaml
- role: netbsd-hue-plugs
  tags: ["service", "netbsd-hue-plugs"]
  vars:
    hue_bridge_ip: "{{ vault_hue_bridge_ip | default(lookup('file', playbook_dir ~ '/hue_bridge_ip.txt') | trim, true) }}"
    hue_client_key: "{{ vault_hue_client_key | default(lookup('file', playbook_dir ~ '/hue_bridge_key.txt') | trim, true) }}"
    hue_plugs:
      - id: "1"
        name: "ai"
      - id: "2"
        name: "voron0"
```

## First-time Setup (pairing)

To discover the bridge on the local network and pair with it, run:

```sh
hue-plugs.py setup              # mDNS discovery + pair
hue-plugs.py setup --bridge-ip 192.168.0.10   # skip mDNS, use a known IP
hue-plugs.py setup --save       # also write bridge_ip + client_key to the config file
hue-plugs.py setup --debug      # dump the pairing requests/responses
```

The `setup` command works without a complete config file (it is dispatched
before `load_config`).  It sends mDNS queries for `_hue._tcp.local` over
UDP multicast (`224.0.0.251:5353`), prints the bridges it finds, and then
pairs by POSTing `{"devicetype": "hue-plugs#netbsd"}` to the
unauthenticated `/api/` endpoint.  Follow the prompt and press the link
button on the Hue bridge within 60 seconds.

After pairing, copy the printed bridge IP and client key into
`hue_bridge_ip.txt` and `hue_bridge_key.txt` next to the playbook (or into
your Ansible vault variables).

## Finding Plug IDs (autofill)

`autofill` talks to the bridge, lists every device it finds (with the room
each one lives in) and prints a ready-to-paste `hue_plugs` block for the
playbook:

```sh
hue-plugs.py autofill
```

```
discovered 3 device(s) on the bridge

HUE ID     NAME                 ROOM                 TYPE
----------------------------------------------------------------------
1          pc1                  Study                On/Off plug-in unit
6          PlugPcIA             Office               On/Off plug-in unit
9          Hue Bulb             Office               Dimmable light
```

```yaml
  hue_plugs:
    - id: "1"
      name: "pc1"
    - id: "6"
      name: "PlugPcIA"
```

Devices already present in the local config keep their (user-chosen) name;
newly discovered ones fall back to the name the bridge gave them. Add
`--save` to also write the regenerated plug list back to the config file.
`autofill` works even when the config has no plugs yet (it is the way to
populate them for the first time).
