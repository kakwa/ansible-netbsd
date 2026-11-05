# ansible-netbsd

Roles for my netbsd server.

## Bootstrap

Before running the Ansible playbooks, you'll need to set up the NetBSD system with some basic prerequisites:


```bash
# Install pkgin
pkg_add https://cdn.NetBSD.org/pub/pkgsrc/packages/NetBSD/`uname -m`/`uname -r`/All/pkgin

# Install sudo and Python
pkgin update
pkgin install sudo python312  # or your preferred Python version

# Add your user to the wheel group to allow sudo access:
LOGIN_USER="your_user_login"
# As root:
usermod -G wheel $LOGIN_USER
```

After completing these steps, you should be able to run the Ansible playbooks against your NetBSD system.

## Customization

The `netbsd.yml` file is an example playbook that you should copy and customize for your needs:

```bash
# Copy example playbook
cp netbsd.yml netbsd-myserver.yml

# Customize it
vim netbsd-myserver.yml
```

By default, the playbook includes the following roles:

- **os-release**: Sets up OS release file
- **netbsd-pkgin**: Configures pkgin package manager
- **netbsd-pkgsrc**: Sets up pkgsrc build system
- **netbsd-misc-packages**: Installs various utility packages
- **netbsd-mdns**: Sets up mDNS/Bonjour service discovery
- **netbsd-ai-waker** (optional): On-demand Wake-on-LAN for `ai.local`, exposed to nginx as an `auth_request` endpoint
- **netbsd-nginx**:
  - Nginx web server with SSL support
  - Static site hosting
  - Reverse proxy configuration with authentication
- **netbsd-postgresql**: PostgreSQL database server
- **netbsd-freshrss**: FreshRSS feed reader

Don't hesitate to tweak it to your needs.

## Wake-on-LAN (`netbsd-ai-waker`)

The optional `netbsd-ai-waker` role lets nginx wake the AI host (`ai.local`)
on demand instead of leaving it powered on. It installs a small stdlib-only
Python HTTP service (`/usr/pkg/bin/ai-waker.py`, `ai_waker` rc.d script) bound
to `127.0.0.1:8099`.

Enable it on a reverse proxy entry:

```yaml
- name: "ai"
  domain: "ai.kakwalab.ovh"
  upstream: "https://ai.local/"
  wake_enabled: true
```

With `wake_enabled: true`, the generated vhost adds `auth_request /_ai_wake;`
before `proxy_pass`. nginx calls the waker for every request:

- if `ai.local:443` already accepts connections, the check returns immediately
  and the request is proxied normally;
- otherwise the waker sends a Wake-on-LAN magic packet (broadcast UDP/9 plus a
  unicast copy to `ai_waker_target_ip`) and waits up to `ai_waker_wake_timeout`
  seconds for the host to answer before nginx continues.

Variables (see `roles/netbsd-ai-waker/defaults/main.yml`):

| Variable | Default | Description |
| --- | --- | --- |
| `ai_waker_enable` | `true` | Install/enable the service |
| `ai_waker_target_mac` | *(empty)* | **Required.** MAC of the NIC to wake |
| `ai_waker_target_host` | `ai.local` | Target hostname |
| `ai_waker_target_ip` | `192.168.1.20` | Target IP used for the reachability check |
| `ai_waker_check_port` | `443` | TCP port used to detect the host is up |
| `ai_waker_broadcast` | `255.255.255.255` | Magic packet destination |
| `ai_waker_wol_port` | `9` | Magic packet UDP port |
| `ai_waker_wake_timeout` | `90` | Seconds to wait for the host to wake |
| `ai_waker_wake_poll_interval` | `2` | Poll interval while waking |
| `ai_waker_listen_addr` | `127.0.0.1` | Local listen address |
| `ai_waker_listen_port` | `8099` | Local listen port |

The role refuses to run if the MAC is missing. Set it in the playbook, e.g.:

```yaml
- role: netbsd-ai-waker
  vars:
    ai_waker_target_mac: "{{ vault_ai_wol_mac }}"
```

The wake endpoint can be tuned from the `netbsd-nginx` defaults with
`nginx_ai_waker_url` (default `http://127.0.0.1:8099/wake`) and
`nginx_ai_waker_timeout` (default `120` seconds).

## Usage

Once the bootstrap setup is complete, you can run the Ansible playbook against your NetBSD server:

```bash
# Set your server details
SERVER_IP="192.168.0.100"
LOGIN_USER="your_username"

# Run the playbook
ansible-playbook -i $SERVER_IP, -u $LOGIN_USER netbsd.yml
```

Where:
- `SERVER_IP` is the IP address of your NetBSD server
- `LOGIN_USER` is the username to connect with (should be the same user you added to the wheel group)
- The comma after the IP address is important - it tells Ansible to treat this as an inventory list

You can also create an inventory file instead of using the inline format:

```bash
# Create inventory file
echo "$SERVER_IP" > inventory

# Run playbook with inventory file
ansible-playbook -i inventory -u $LOGIN_USER netbsd.yml
```

## Secrets

By default, the main playbook will auto-generate passwords & secrets and store them in `*.password.txt` / `*.apikey.txt` files:

```bash
ls *.password.txt *.apikey.txt

cat *.password.txt *.apikey.txt
```

Values can be overriden, or you could setup [ansible-vault](https://docs.ansible.com/ansible/latest/vault_guide/index.html) to more cleanly manage them.
