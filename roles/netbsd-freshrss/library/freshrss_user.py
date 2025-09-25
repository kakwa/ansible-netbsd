# Copyright: (c) 2025, Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: freshrss_user
short_description: Manage FreshRSS users
description:
    - Add, remove, or modify FreshRSS users using the CLI interface
    - Supports user creation, deletion, password changes, and email modifications
version_added: "1.0.0"
author:
    - "Ansible Project"
options:
    username:
        description:
            - Username for the FreshRSS user
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
            - Password for the FreshRSS user
            - Required when state=present for new users
        type: str
        no_log: true
    email:
        description:
            - Email address for the FreshRSS user
        type: str
    language:
        description:
            - Default language for the user
        type: str
        default: 'en'
    timezone:
        description:
            - Default timezone for the user
        type: str
        default: 'UTC'
    php_binary:
        description:
            - Path to the PHP binary to use
        type: str
        default: '/usr/pkg/bin/php83'
    freshrss_path:
        description:
            - Path to the FreshRSS installation
        type: str
        default: '/usr/pkg/share/freshrss'
    become_user:
        description:
            - User to become when running commands
        type: str
requirements:
    - PHP command line interface
    - FreshRSS installation with CLI tools
notes:
    - This module uses the FreshRSS command-line interface
    - The module requires appropriate permissions to execute PHP and access FreshRSS files
'''

EXAMPLES = r'''
- name: Create a FreshRSS user
  freshrss_user:
    username: myuser
    password: mypassword
    email: myuser@example.com
    state: present

- name: Create a FreshRSS admin user
  freshrss_user:
    username: admin
    password: adminpassword
    email: admin@example.com
    state: present

- name: Remove a FreshRSS user
  freshrss_user:
    username: olduser
    state: absent

- name: Change user password
  freshrss_user:
    username: myuser
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
import json
from ansible.module_utils.basic import AnsibleModule


class FreshRssUserManager:
    def __init__(self, module):
        self.module = module
        self.php_binary = module.params['php_binary']
        self.freshrss_path = module.params['freshrss_path']
        self.cli_script = os.path.join(self.freshrss_path, 'cli', 'user.php')
        self.become_user = module.params.get('become_user')

    def _run_command(self, cmd):
        """Run a command with optional user switching"""
        if self.become_user:
            cmd = ['sudo', '-u', self.become_user] + cmd
        
        try:
            result = subprocess.run(
                cmd,
                cwd=self.freshrss_path,
                capture_output=True,
                text=True,
                check=False
            )
            return result.returncode, result.stdout, result.stderr
        except Exception as e:
            return 1, "", str(e)

    def user_exists(self, username):
        """Check if a user exists"""
        cmd = [self.php_binary, self.cli_script, '--user', username, '--list']
        returncode, stdout, stderr = self._run_command(cmd)
        return returncode == 0 and username in stdout

    def list_users(self):
        """List all users"""
        cmd = [self.php_binary, self.cli_script, '--list']
        returncode, stdout, stderr = self._run_command(cmd)
        if returncode == 0:
            # Parse the output to extract usernames
            users = []
            for line in stdout.split('\n'):
                if line.strip() and not line.startswith('FreshRSS'):
                    users.append(line.strip())
            return users
        return []

    def add_user(self, username, password, email=None, language='en', timezone='UTC'):
        """Add a new user"""
        cmd = [self.php_binary, self.cli_script, '--user', username, '--add']
        if password:
            cmd.extend(['--password', password])
        if email:
            cmd.extend(['--email', email])
        cmd.extend(['--language', language, '--timezone', timezone])
        
        returncode, stdout, stderr = self._run_command(cmd)
        return returncode == 0, stdout, stderr

    def remove_user(self, username):
        """Remove a user"""
        cmd = [self.php_binary, self.cli_script, '--user', username, '--delete']
        returncode, stdout, stderr = self._run_command(cmd)
        return returncode == 0, stdout, stderr

    def set_password(self, username, password):
        """Set user password"""
        cmd = [self.php_binary, self.cli_script, '--user', username, '--password', password]
        returncode, stdout, stderr = self._run_command(cmd)
        return returncode == 0, stdout, stderr

    def set_email(self, username, email):
        """Set user email"""
        cmd = [self.php_binary, self.cli_script, '--user', username, '--email', email]
        returncode, stdout, stderr = self._run_command(cmd)
        return returncode == 0, stdout, stderr

    def get_user_info(self, username):
        """Get user information"""
        cmd = [self.php_binary, self.cli_script, '--user', username, '--get']
        returncode, stdout, stderr = self._run_command(cmd)
        if returncode == 0:
            try:
                # Parse user info from output
                info = {}
                for line in stdout.split('\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        info[key.strip().lower()] = value.strip()
                return info
            except:
                pass
        return {}


def main():
    module_args = dict(
        username=dict(type='str', required=True),
        state=dict(type='str', default='present', choices=['present', 'absent']),
        password=dict(type='str', no_log=True),
        email=dict(type='str'),
        language=dict(type='str', default='en'),
        timezone=dict(type='str', default='UTC'),
        php_binary=dict(type='str', default='/usr/pkg/bin/php83'),
        freshrss_path=dict(type='str', default='/usr/pkg/share/freshrss'),
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

    manager = FreshRssUserManager(module)
    username = module.params['username']
    state = module.params['state']
    password = module.params['password']
    email = module.params['email']
    language = module.params['language']
    timezone = module.params['timezone']

    # Check if user exists
    user_exists = manager.user_exists(username)
    result['user_exists'] = user_exists

    if state == 'present':
        if not user_exists:
            # Create new user
            if not password:
                module.fail_json(msg="Password is required when creating a new user")
            
            if module.check_mode:
                result['changed'] = True
                result['msg'] = f"Would create user {username}"
                module.exit_json(**result)

            success, stdout, stderr = manager.add_user(username, password, email, language, timezone)
            if success:
                result['changed'] = True
                result['msg'] = f"User {username} created successfully"
                result['user_exists'] = True
            else:
                module.fail_json(msg=f"Failed to create user {username}: {stderr}")
        else:
            # User exists, check if we need to update anything
            changes_made = []
            user_info = manager.get_user_info(username)
            
            if password:
                # Always try to set password for consistency
                if not module.check_mode:
                    success, stdout, stderr = manager.set_password(username, password)
                    if success:
                        changes_made.append("password updated")
                    else:
                        module.fail_json(msg=f"Failed to update password for user {username}: {stderr}")
                else:
                    changes_made.append("password would be updated")

            if email and user_info.get('email', '') != email:
                if not module.check_mode:
                    success, stdout, stderr = manager.set_email(username, email)
                    if success:
                        changes_made.append("email updated")
                    else:
                        module.fail_json(msg=f"Failed to update email for user {username}: {stderr}")
                else:
                    changes_made.append("email would be updated")

            if changes_made:
                result['changed'] = True
                result['msg'] = f"User {username} updated: {', '.join(changes_made)}"
            else:
                result['msg'] = f"User {username} already exists with correct configuration"

    elif state == 'absent':
        if user_exists:
            if module.check_mode:
                result['changed'] = True
                result['msg'] = f"Would remove user {username}"
                module.exit_json(**result)

            success, stdout, stderr = manager.remove_user(username)
            if success:
                result['changed'] = True
                result['msg'] = f"User {username} removed successfully"
                result['user_exists'] = False
            else:
                module.fail_json(msg=f"Failed to remove user {username}: {stderr}")
        else:
            result['msg'] = f"User {username} does not exist"

    module.exit_json(**result)


if __name__ == '__main__':
    main()
