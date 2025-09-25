# Copyright: (c) 2025, Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: ttrss_user
short_description: Manage Tiny Tiny RSS users
description:
    - Add, remove, or modify Tiny Tiny RSS users using the update.php command-line interface
    - Supports user creation, deletion, password changes, and access level modifications
version_added: "1.0.0"
author:
    - "Ansible Project"
options:
    name:
        description:
            - Username for the TT-RSS user
        required: true
        type: str
    state:
        description:
            - Whether the user should exist or not
        choices: ['present', 'absent']
        default: 'present'
        type: str
    password:
        description:
            - Password for the TT-RSS user
            - Required when state=present for new users
        type: str
        no_log: true
    access_level:
        description:
            - Access level for the user (0=user, 10=admin)
        type: int
        default: 0
        choices: [0, 10]
    api_enabled:
        description:
            - Whether API access should be enabled for the user
        type: bool
        default: false
    php_binary:
        description:
            - Path to the PHP binary to use
        type: str
        default: '/usr/pkg/bin/php83'
    ttrss_path:
        description:
            - Path to the TT-RSS installation
        type: str
        default: '/usr/pkg/share/tt-rss'
    become_user:
        description:
            - User to become when running commands
        type: str
requirements:
    - PHP command line interface
    - TT-RSS installation with update.php
notes:
    - This module uses the TT-RSS update.php command-line interface
    - The module requires appropriate permissions to execute PHP and access TT-RSS files
'''

EXAMPLES = r'''
- name: Create a TT-RSS user
  ttrss_user:
    name: myuser
    password: mypassword
    access_level: 0
    api_enabled: true
    state: present

- name: Create a TT-RSS admin user
  ttrss_user:
    name: admin
    password: adminpassword
    access_level: 10
    state: present

- name: Remove a TT-RSS user
  ttrss_user:
    name: olduser
    state: absent

- name: Change user password
  ttrss_user:
    name: myuser
    password: newpassword
    state: present
'''

RETURN = r'''
changed:
    description: Whether the user was modified
    type: bool
    returned: always
msg:
    description: Message describing what happened
    type: str
    returned: always
user_exists:
    description: Whether the user exists after the operation
    type: bool
    returned: always
'''

import os
import subprocess
from ansible.module_utils.basic import AnsibleModule


class TtRssUserManager:
    def __init__(self, module):
        self.module = module
        self.php_binary = module.params['php_binary']
        self.ttrss_path = module.params['ttrss_path']
        self.update_script = os.path.join(self.ttrss_path, 'update.php')
        self.become_user = module.params.get('become_user')

    def _run_command(self, cmd):
        """Run a command with optional user switching"""
        if self.become_user:
            cmd = ['sudo', '-u', self.become_user] + cmd
        
        try:
            result = subprocess.run(
                cmd,
                cwd=self.ttrss_path,
                capture_output=True,
                text=True,
                check=False
            )
            return result.returncode, result.stdout, result.stderr
        except Exception as e:
            return 1, "", str(e)

    def user_exists(self, username):
        """Check if a user exists"""
        cmd = [self.php_binary, self.update_script, '--user-exists', username]
        returncode, stdout, stderr = self._run_command(cmd)
        return returncode == 0

    def list_users(self):
        """List all users"""
        cmd = [self.php_binary, self.update_script, '--user-list']
        returncode, stdout, stderr = self._run_command(cmd)
        if returncode == 0:
            return stdout.strip().split('\n') if stdout.strip() else []
        return []

    def add_user(self, username, password, access_level=0):
        """Add a new user"""
        user_spec = f"{username}:{password}:{access_level}"
        cmd = [self.php_binary, self.update_script, '--user-add', user_spec]
        returncode, stdout, stderr = self._run_command(cmd)
        return returncode == 0, stdout, stderr

    def remove_user(self, username):
        """Remove a user"""
        cmd = [self.php_binary, self.update_script, '--user-remove', username]
        returncode, stdout, stderr = self._run_command(cmd)
        return returncode == 0, stdout, stderr

    def set_password(self, username, password):
        """Set user password"""
        user_pass = f"{username}:{password}"
        cmd = [self.php_binary, self.update_script, '--user-set-password', user_pass]
        returncode, stdout, stderr = self._run_command(cmd)
        return returncode == 0, stdout, stderr

    def check_password(self, username, password):
        """Check if user has the specified password"""
        user_pass = f"{username}:{password}"
        cmd = [self.php_binary, self.update_script, '--user-check-password', user_pass]
        returncode, stdout, stderr = self._run_command(cmd)
        return returncode == 0

    def set_access_level(self, username, access_level):
        """Set user access level"""
        user_level = f"{username}:{access_level}"
        cmd = [self.php_binary, self.update_script, '--user-set-access-level', user_level]
        returncode, stdout, stderr = self._run_command(cmd)
        return returncode == 0, stdout, stderr

    def set_api_access(self, username, enabled):
        """Enable/disable API access for user"""
        api_setting = f"{username}:{'1' if enabled else '0'}"
        cmd = [self.php_binary, self.update_script, '--user-enable-api', api_setting]
        returncode, stdout, stderr = self._run_command(cmd)
        return returncode == 0, stdout, stderr


def main():
    module_args = dict(
        name=dict(type='str', required=True),
        state=dict(type='str', default='present', choices=['present', 'absent']),
        password=dict(type='str', no_log=True),
        access_level=dict(type='int', default=0, choices=[0, 10]),
        api_enabled=dict(type='bool', default=False),
        php_binary=dict(type='str', default='/usr/pkg/bin/php83'),
        ttrss_path=dict(type='str', default='/usr/pkg/share/tt-rss'),
        become_user=dict(type='str', required=False)
    )

    result = dict(
        changed=False,
        msg='',
        user_exists=False
    )

    module = AnsibleModule(
        argument_spec=module_args,
        supports_check_mode=True,
        required_if=[
            ('state', 'present', ['password'], False)
        ]
    )

    manager = TtRssUserManager(module)
    name = module.params['name']
    state = module.params['state']
    password = module.params['password']
    access_level = module.params['access_level']
    api_enabled = module.params['api_enabled']

    # Check if user exists
    user_exists = manager.user_exists(name)
    result['user_exists'] = user_exists

    if state == 'present':
        if not user_exists:
            # Create new user
            if not password:
                module.fail_json(msg="Password is required when creating a new user")
            
            if module.check_mode:
                result['changed'] = True
                result['msg'] = f"Would create user {name}"
                module.exit_json(**result)

            success, stdout, stderr = manager.add_user(name, password, access_level)
            if success:
                result['changed'] = True
                result['msg'] = f"User {name} created successfully"
                result['user_exists'] = True
                
                # Set API access if requested
                if api_enabled:
                    api_success, _, _ = manager.set_api_access(name, True)
                    if api_success:
                        result['msg'] += " with API access enabled"
                    else:
                        result['msg'] += " but failed to enable API access"
            else:
                module.fail_json(msg=f"Failed to create user {name}: {stderr}")
        else:
            # User exists, check if we need to update anything
            changes_made = []
            
            if password:
                # Check if password needs updating
                if not manager.check_password(name, password):
                    if not module.check_mode:
                        success, stdout, stderr = manager.set_password(name, password)
                        if success:
                            changes_made.append("password updated")
                        else:
                            module.fail_json(msg=f"Failed to update password for user {name}: {stderr}")
                    else:
                        changes_made.append("password would be updated")

            # Set access level (we'll always try to set it to ensure consistency)
            if not module.check_mode:
                success, stdout, stderr = manager.set_access_level(name, access_level)
                if success and f"access level {access_level}" not in stdout:
                    changes_made.append(f"access level set to {access_level}")

            # Set API access
            if not module.check_mode:
                success, stdout, stderr = manager.set_api_access(name, api_enabled)
                if success:
                    api_status = "enabled" if api_enabled else "disabled"
                    changes_made.append(f"API access {api_status}")

            if changes_made:
                result['changed'] = True
                result['msg'] = f"User {name} updated: {', '.join(changes_made)}"
            else:
                result['msg'] = f"User {name} already exists with correct configuration"

    elif state == 'absent':
        if user_exists:
            if module.check_mode:
                result['changed'] = True
                result['msg'] = f"Would remove user {name}"
                module.exit_json(**result)

            success, stdout, stderr = manager.remove_user(name)
            if success:
                result['changed'] = True
                result['msg'] = f"User {name} removed successfully"
                result['user_exists'] = False
            else:
                module.fail_json(msg=f"Failed to remove user {name}: {stderr}")
        else:
            result['msg'] = f"User {name} does not exist"

    module.exit_json(**result)


if __name__ == '__main__':
    main()
