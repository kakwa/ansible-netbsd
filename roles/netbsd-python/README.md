# netbsd-python

This Ansible role installs Python on NetBSD systems with configurable version support.

## Features

- **Python**: Configurable version installation (default: Python 3.12)
- **Essential packages**: Includes pip and setuptools
- **Symlinks**: Creates convenient `python` and `python3` symlinks
- **Verification**: Checks installation and displays version

## Variables

### Python Version Configuration

```yaml
python_version_major: "3"        # Major version (default: "3")
python_version_minor: "12"       # Minor version (default: "12")
```

### Package Configuration

```yaml
python_packages:                 # Core packages (automatically derived)
  - "python312"                  # Main Python package
  - "py312-pip"                  # Package installer
  - "py312-setuptools"           # Setup tools

python_extra_packages: []        # Additional packages to install
```

## Usage

### Basic Usage

```yaml
- role: netbsd-python
```

### Custom Python Version

```yaml
- role: netbsd-python
  vars:
    python_version_major: "3"
    python_version_minor: "11"
```

### With Additional Packages

```yaml
- role: netbsd-python
  vars:
    python_extra_packages:
      - "{{ python_package_prefix }}-requests"
      - "{{ python_package_prefix }}-yaml"
      - "{{ python_package_prefix }}-jinja2"
```

## Derived Variables

The role automatically creates these derived variables:

- `python_version_full`: "3.12" (full version string)
- `python_version_short`: "312" (short version for package names)
- `python_binary`: "python312" (binary name)
- `python_package_prefix`: "py312" (package prefix)
- `python_package_name`: "python312" (main package name)

## Dependencies

- `community.general.pkgin` collection for package management

## Example Playbook

```yaml
---
- name: Install Python
  hosts: all
  become: true
  vars:
    python_version_major: "3"
    python_version_minor: "12"
  roles:
    - netbsd-python
```

## Symlinks Created

- `/usr/pkg/bin/python3` → `/usr/pkg/bin/python312`
- `/usr/pkg/bin/python` → `/usr/pkg/bin/python312` (for Python 3.x)

This ensures compatibility with scripts expecting standard `python` or `python3` commands.
