# NetBSD FreshRSS Role

This Ansible role sets up FreshRSS with PHP-FPM on NetBSD.

## Features

- **PHP**: With FPM and all required extensions for FreshRSS (configurable version)
- **FreshRSS**: Self-hosted RSS feed aggregator
- **Database Integration**: PostgreSQL database connection (MySQL and SQLite also supported)
- **User Management**: Custom Ansible module for managing FreshRSS users
- **Security**: Hardened PHP configurations with security best practices
- **Multi-user Support**: Full multi-user capability with admin controls
- **API Access**: RESTful API for external integrations

## Requirements

- NetBSD system
- Root or sudo access
- PostgreSQL database (use netbsd-postgresql role)

## Role Variables

### Domain Configuration
```yaml
freshrss_domain: "rss.example.com"
```

### FreshRSS Configuration
```yaml
freshrss_admin_user: "admin"
freshrss_admin_password: "{{ vault_freshrss_admin_password }}"
freshrss_admin_email: "admin@example.com"

# Authentication for nginx htpasswd (defaults to admin user/password)
freshrss_auth_user: "{{ freshrss_admin_user }}"
freshrss_auth_password: "{{ freshrss_admin_password }}"
```

### Database Configuration
```yaml
freshrss_db_name: "freshrss"
freshrss_db_user: "freshrss"
freshrss_db_password: "{{ vault_postgresql_password }}"
freshrss_db_host: "localhost"
freshrss_db_port: 5432
```

### Application Settings
```yaml
freshrss_title: "FreshRSS"
freshrss_default_user: "{{ freshrss_admin_user }}"
freshrss_language: "en"
freshrss_timezone: "UTC"
freshrss_theme: "Origine"
```

### Security Settings
```yaml
freshrss_allow_anonymous: false
freshrss_allow_anonymous_refresh: false
freshrss_auth_type: "form"
```

### Performance Settings
```yaml
freshrss_limits_cache_duration: 800
freshrss_limits_timeout: 20
freshrss_limits_cookie_duration: 2592000
```

### Extensions
```yaml
freshrss_extensions_enabled: []
```

## Dependencies

- netbsd-postgresql (for database setup)
- netbsd-nginx (for web server)

## Example Playbook

```yaml
---
- name: Deploy FreshRSS
  hosts: webservers
  become: true
  vars:
    freshrss_domain: "rss.example.com"
    freshrss_admin_user: "admin"
    freshrss_admin_email: "admin@example.com"
    vault_freshrss_admin_password: "secure_admin_password"
    vault_postgresql_password: "secure_db_password"
  
  roles:
    - netbsd-postgresql
    - netbsd-nginx
    - netbsd-freshrss
```

## Post-Installation Steps

1. **DNS Configuration**: Update your DNS records to point the FreshRSS domain to the server
2. **FreshRSS Setup**: Access `https://your-freshrss-domain` to complete initial setup
3. **Admin Account**: Use the configured admin credentials to log in
4. **Feed Updates**: Automatic feed updates are configured via cron (every 10 minutes)

## Security Features

- Disabled dangerous PHP functions
- Restricted file access and permissions
- Secure PHP-FPM configuration
- HTTP Basic Authentication via nginx
- SSL/TLS encryption (Let's Encrypt or self-signed)

## Custom Modules

This role includes a custom Ansible module for managing FreshRSS users:

### freshrss_user Module

```yaml
- name: Create a FreshRSS user
  freshrss_user:
    username: myuser
    password: mypassword
    email: myuser@example.com
    language: en
    timezone: UTC
    state: present

- name: Remove a FreshRSS user
  freshrss_user:
    username: olduser
    state: absent
```

## API Access

FreshRSS provides several API options:

1. **Google Reader API**: Compatible with mobile apps
2. **Fever API**: Compatible with Fever-compatible clients
3. **Native API**: Full FreshRSS functionality

API endpoints are available at:
- `https://your-domain/api/greader.php` (Google Reader API)
- `https://your-domain/api/fever.php` (Fever API)

## File Structure

```
roles/netbsd-freshrss/
├── defaults/main.yml                    # Default variables
├── files/
│   └── php-freshrss.pkgsrc/            # NetBSD package files
│       ├── Makefile                     # Package build configuration
│       ├── DESCR                        # Package description
│       ├── PLIST                        # Package file list
│       ├── distinfo                     # Package checksums
│       ├── options.mk                   # Package options
│       ├── MESSAGE                      # Post-install message
│       └── INSTALL                      # Post-install script
├── library/
│   └── freshrss_user.py                # Custom FreshRSS user management module
├── tasks/
│   └── main.yml                         # Main task orchestration
├── templates/
│   ├── freshrss-config.php.j2          # FreshRSS configuration
│   ├── freshrss-user-config.php.j2     # Default user configuration
│   └── freshrss-nginx.conf.j2          # FreshRSS virtual host
├── handlers/main.yml                    # Service restart handlers
└── README.md                           # This file
```

## Troubleshooting

### Common Issues

1. **Permission Errors**: Ensure the web server user has write access to data directories
2. **Database Connection**: Verify database credentials and connectivity
3. **Feed Updates**: Check cron logs in `/var/log/freshrss/cron.log`
4. **PHP Errors**: Check FreshRSS logs and nginx error logs

### Log Locations

- FreshRSS logs: `/var/log/freshrss/`
- Nginx access log: `/var/log/nginx/freshrss_access.log`
- Nginx error log: `/var/log/nginx/freshrss_error.log`
- Cron log: `/var/log/freshrss/cron.log`

### CLI Tools

FreshRSS includes several CLI tools for administration:

```bash
# List users
${php_binary} /usr/pkg/share/freshrss/cli/list-users.php

# Create user
${php_binary} /usr/pkg/share/freshrss/cli/create-user.php --user newuser

# Import OPML
${php_binary} /usr/pkg/share/freshrss/cli/import-opml.php --user username --filename feeds.opml

# Update feeds for specific user
${php_binary} /usr/pkg/share/freshrss/cli/actualize-user.php --user username
```

## Differences from TT-RSS

FreshRSS differs from Tiny Tiny RSS in several ways:

1. **Licensing**: FreshRSS uses AGPL v3, TT-RSS uses GPL v2
2. **Architecture**: FreshRSS has a more modular design
3. **User Interface**: More modern and responsive interface
4. **Installation**: Simpler installation and configuration process
5. **Extensions**: Different extension system and available extensions
6. **API**: Multiple API compatibility options

## License

This role is provided as-is for educational and production use.

## Author Information

Created for NetBSD FreshRSS deployment with modern security practices, inspired by the netbsd-ttrss role.
