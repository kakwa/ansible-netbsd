# NetBSD Tiny Tiny RSS Role

This Ansible role sets up Tiny Tiny RSS (TTRSS) with PHP-FPM on NetBSD.

## Features

- **PHP**: With FPM and all required extensions for Tiny Tiny RSS (configurable version)
- **Tiny Tiny RSS**: Self-hosted RSS reader application
- **Database Integration**: PostgreSQL database connection
- **User Management**: Custom Ansible module for managing TT-RSS users
- **Security**: Hardened PHP configurations with security best practices

## Requirements

- NetBSD system
- Root or sudo access
- PostgreSQL database (use netbsd-postgresql role)

## Role Variables

### Domain Configuration
```yaml
ttrss_domain: "ttrss.example.com"
```

### Tiny Tiny RSS Configuration
```yaml
ttrss_admin_user: "admin"
ttrss_admin_password: "{{ vault_ttrss_admin_password }}"
ttrss_admin_email: "admin@example.com"
ttrss_single_user_mode: false

# Authentication for nginx htpasswd (defaults to admin user/password)
ttrss_auth_user: "{{ ttrss_admin_user }}"
ttrss_auth_password: "{{ ttrss_admin_password }}"
```

### Database Configuration
```yaml
postgresql_db_name: "ttrss"
postgresql_db_user: "ttrss"
postgresql_db_password: "{{ vault_postgresql_password }}"
postgresql_host: "localhost"
postgresql_port: 5432
```

### PHP-FPM Configuration
```yaml
php_fpm_pool: "fpm"
php_fpm_user: "fpm"
php_fpm_group: "www"
php_fpm_listen: "/var/run/php-fpm/php-fpm.sock"
php_fpm_pm_max_children: 50
php_fpm_pm_start_servers: 5
php_fpm_pm_min_spare_servers: 5
php_fpm_pm_max_spare_servers: 35
```

## Dependencies

- netbsd-postgresql (for database setup)
- netbsd-nginx (for web server)

## Example Playbook

```yaml
---
- name: Deploy Tiny Tiny RSS
  hosts: webservers
  become: true
  vars:
    ttrss_domain: "rss.example.com"
    ttrss_admin_user: "admin"
    ttrss_admin_email: "admin@example.com"
    vault_ttrss_admin_password: "secure_admin_password"
    vault_postgresql_password: "secure_db_password"
  
  roles:
    - netbsd-postgresql
    - netbsd-nginx
    - netbsd-ttrss
```

## Post-Installation Steps

1. **DNS Configuration**: Update your DNS records to point the TTRSS domain to the server
2. **Tiny Tiny RSS Setup**: Access `https://your-ttrss-domain` to complete initial setup
3. **Admin Account**: Use the configured admin credentials to log in

## Security Features

- Disabled dangerous PHP functions
- Restricted file access and permissions
- Secure PHP-FPM configuration

## Custom Modules

This role includes a custom Ansible module for managing TT-RSS users:

### ttrss_user Module

```yaml
- name: Create a TT-RSS user
  ttrss_user:
    name: myuser
    password: mypassword
    access_level: 0  # 0=user, 10=admin
    api_enabled: true
    state: present

- name: Remove a TT-RSS user
  ttrss_user:
    name: olduser
    state: absent
```

## File Structure

```
roles/netbsd-ttrss/
├── defaults/main.yml          # Default variables
├── library/
│   └── ttrss_user.py         # Custom TT-RSS user management module
├── tasks/
│   ├── main.yml              # Main task orchestration
│   └── setup_ttrss.yml       # Tiny Tiny RSS setup
├── templates/
│   ├── php-fpm-pool.conf.j2  # PHP-FPM pool configuration
│   ├── php.ini.j2            # PHP configuration
│   ├── ttrss-config.php.j2   # Tiny Tiny RSS configuration
│   └── ttrss-nginx.conf.j2   # Tiny Tiny RSS virtual host
├── handlers/main.yml          # Service restart handlers
└── README.md                 # This file
```

## License

This role is provided as-is for educational and production use.

## Author Information

Created for NetBSD Tiny Tiny RSS deployment with modern security practices.
