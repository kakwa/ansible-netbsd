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
- **netbsd-nginx**:
  - Nginx web server with SSL support
  - Static site hosting
  - Reverse proxy configuration with authentication
- **netbsd-postgresql**: PostgreSQL database server
- **netbsd-freshrss**: FreshRSS feed reader

Don't hesitate to tweak it to your needs.

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

By default, the main playbook will auto-generate passwords & secret and store in `*.password.txt` files:

```bash
ls *.password.txt

cat *.password.txt
```

Values can be overriden, or you could setup [ansible-vault](https://docs.ansible.com/ansible/latest/vault_guide/index.html) to more cleanly manage them.
