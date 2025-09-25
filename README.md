# ansible-netbsd
roles for my netbsd server

## Bootstrap Setup

Before running the Ansible playbooks, you'll need to set up the NetBSD system with some basic prerequisites:

### 1. Install pkgin

```bash
pkg_add https://cdn.NetBSD.org/pub/pkgsrc/packages/NetBSD/`uname -m`/`uname -r`/All/pkgin
```

### 2. Install sudo and Python

```bash
pkgin update
pkgin install sudo python312  # or your preferred Python version
```

### 3. Add user to wheel group

Add your user to the wheel group to allow sudo access:

```bash
LOGIN_USER="your_user_login"

# As root:
usermod -G wheel $LOGIN_USER
```

After completing these steps, you should be able to run the Ansible playbooks against your NetBSD system.

## Setup

Before using the playbooks, initialize the git submodules:

```bash
git submodule update --init
```

## Customization

The `netbsd.yml` file is an example playbook that you should copy and customize for your needs:

```bash
cp netbsd.yml my-server.yml
```

Then edit `my-server.yml` to customize:
- Domain names (replace `example.com` with your actual domains)
- IP addresses and ports for reverse proxies
- Static site configurations
- Database names and users

### What the playbook installs

The playbook includes the following roles and components by default:

- **os-release**: Sets up OS release information
- **netbsd-pkgin**: Configures pkgin package manager
- **netbsd-pkgsrc**: Sets up pkgsrc build system
- **vim**: Installs and configures Vim editor
- **zsh**: Installs and configures Zsh shell
- **netbsd-misc-packages**: Installs various utility packages
- **netbsd-mdns**: Sets up mDNS/Bonjour service discovery
- **netbsd-nginx**:
  - Nginx web server with SSL support
  - Static site hosting
  - Reverse proxy configuration with authentication
- **netbsd-postgresql**: PostgreSQL database server
- **netbsd-ttrss**: Tiny Tiny RSS feed reader

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

## Configuration

Some roles require password files to be present. Create these files in the project root directory:

```bash
# Create password files with your desired passwords
echo "your_proxy_password" > proxy.password.txt
echo "your_ttrss_db_password" > ttrss_db.password.txt

# Verify the files were created correctly
cat proxy.password.txt
cat ttrss_db.password.txt
```

These files should contain the respective passwords in plain text and will be used by the playbooks for authentication and database setup.

**Note:** If these password files are not present, the playbooks will automatically generate files and respective passwords for you.
