# NetBSD FreshRSS Role

This Ansible role sets up FreshRSS with PHP-FPM on NetBSD.

## How to update freshrss pkgsrc

On the NetBSD target:
```
cd /usr/pkgsrc/overlay/php-freshrss
make clean
make makesum
make install
make print-PLIST > PLIST
make replace
```

Copy of the files:
```
export NETBSD_HOST=sun.kakwalab.ovh

scp $NETBSD_HOST:/usr/pkgsrc/overlay/php-freshrss/\* ./files/php-freshrss.pkgsrc/
```

## Role Variables

```yaml
freshrss_domain: "rss.example.com"
freshrss_admin_user: "admin"
freshrss_admin_password: "{{ vault_freshrss_admin_password }}"
freshrss_admin_email: "admin@example.com"
freshrss_auth_user: "{{ freshrss_admin_user }}"
freshrss_auth_password: "{{ freshrss_admin_password }}"
freshrss_db_name: "freshrss"
freshrss_db_user: "freshrss"
freshrss_db_password: "{{ vault_postgresql_password }}"
freshrss_db_host: "localhost"
freshrss_db_port: 5432
freshrss_title: "FreshRSS"
freshrss_default_user: "{{ freshrss_admin_user }}"
freshrss_language: "en"
freshrss_timezone: "UTC"
freshrss_theme: "Origine"
freshrss_allow_anonymous: false
freshrss_allow_anonymous_refresh: false
freshrss_auth_type: "form"
freshrss_limits_cache_duration: 800
freshrss_limits_timeout: 20
freshrss_limits_cookie_duration: 2592000
```

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
