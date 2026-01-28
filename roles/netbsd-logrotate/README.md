# NetBSD Logrotate Role

This Ansible role installs and configures logrotate on NetBSD systems for managing log file rotation.

## Features

- Installs logrotate from pkgsrc
- Configures global logrotate settings
- Supports multiple logrotate configurations
- Sets up daily cron job for automatic log rotation
- Flexible configuration per service/application

## Requirements

- NetBSD system with pkgin configured
- Ansible 2.9 or higher

## Role Variables

### Default Variables

```yaml
# Logrotate package
logrotate_package: "logrotate"

# Global logrotate configuration
logrotate_global_config:
  - "weekly"
  - "rotate 4"
  - "create"
  - "compress"
  - "delaycompress"
  - "notifempty"
  - "missingok"

# Logrotate configurations (empty by default)
logrotate_configs: []
```

### Configuration Format

Each entry in `logrotate_configs` should have:

- `name`: Unique identifier for the config file
- `paths`: List of log file paths to rotate
- `options`: List of logrotate options
- `postrotate`: (Optional) Script to run after rotation
- `prerotate`: (Optional) Script to run before rotation

## Example Usage

### Basic Playbook

```yaml
- hosts: servers
  roles:
    - netbsd-logrotate
```

### With Custom Configuration

```yaml
- hosts: servers
  roles:
    - role: netbsd-logrotate
      logrotate_configs:
        - name: myapp
          paths:
            - /var/log/myapp/*.log
          options:
            - daily
            - rotate 30
            - compress
            - delaycompress
            - notifempty
            - missingok
          postrotate: |
            /etc/rc.d/myapp reload
```

### Nginx Example

```yaml
- hosts: webservers
  roles:
    - role: netbsd-logrotate
      logrotate_configs:
        - name: nginx
          paths:
            - /var/log/nginx/*.log
          options:
            - daily
            - rotate 14
            - compress
            - delaycompress
            - notifempty
            - missingok
            - sharedscripts
          postrotate: |
            if [ -f /var/run/nginx.pid ]; then
              kill -USR1 $(cat /var/run/nginx.pid)
            fi
```

## Common Logrotate Options

- `daily`, `weekly`, `monthly`: Rotation frequency
- `rotate N`: Keep N rotated logs
- `compress`: Compress rotated logs with gzip
- `delaycompress`: Delay compression until next rotation
- `notifempty`: Don't rotate empty logs
- `missingok`: Don't error if log file is missing
- `sharedscripts`: Run scripts only once for all logs
- `create MODE OWNER GROUP`: Create new log file after rotation
- `size SIZE`: Rotate when log reaches SIZE (e.g., 100M)
- `maxage N`: Remove rotated logs older than N days

## Files Created

- `/usr/pkg/etc/logrotate.conf`: Main logrotate configuration
- `/usr/pkg/etc/logrotate.d/`: Directory for individual configurations
- Cron job: Daily execution at 2:00 AM

## Tags

- `logrotate-base`: Installation and base configuration
- `logrotate-config`: Individual logrotate rule configuration

## License

Same as the parent ansible-netbsd project
