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
    api_password:
        description:
            - API password for the FreshRSS user
        type: str
        no_log: true
    language:
        description:
            - Default language for the user
        type: str
        default: 'en'
    token:
        description:
            - Authentication token for the user
        type: str
        no_log: true
    purge_after_months:
        description:
            - Number of months after which to purge old articles
        type: int
    feed_min_articles_default:
        description:
            - Default minimum number of articles per feed
        type: int
    feed_ttl_default:
        description:
            - Default TTL for feeds
        type: int
    since_hours_posts_per_rss:
        description:
            - Hours since posts per RSS
        type: int
    max_posts_per_rss:
        description:
            - Maximum posts per RSS
        type: int
    no_default_feeds:
        description:
            - Do not add default feeds when creating user
        type: bool
        default: false
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
        self.cli_path = os.path.join(self.freshrss_path, 'cli')
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
        users = self.list_users()
        return username in users

    def list_users(self):
        """List all users"""
        cmd = [self.php_binary, os.path.join(self.cli_path, 'list-users.php')]
        returncode, stdout, stderr = self._run_command(cmd)
        if returncode == 0:
            # Parse the output to extract usernames
            users = []
            for line in stdout.strip().split('\n'):
                if line.strip():
                    # Remove any extra whitespace and filter out header lines
                    clean_line = line.strip()
                    if clean_line and not clean_line.startswith('FreshRSS') and not clean_line.startswith('='):
                        users.append(clean_line)
            return users
        return []

    def add_user(self, username, password, email=None, language='en', api_password=None,
                 token=None, purge_after_months=None, feed_min_articles_default=None,
                 feed_ttl_default=None, since_hours_posts_per_rss=None, max_posts_per_rss=None,
                 no_default_feeds=False, **kwargs):
        """Add a new user"""
        cmd = [self.php_binary, os.path.join(self.cli_path, 'create-user.php')]
        cmd.extend(['--user', username])

        if password:
            cmd.extend(['--password', password])
        if api_password:
            cmd.extend(['--api-password', api_password])
        if email:
            cmd.extend(['--email', email])
        if language:
            cmd.extend(['--language', language])
        if token:
            cmd.extend(['--token', token])
        if purge_after_months is not None:
            cmd.extend(['--purge-after-months', str(purge_after_months)])
        if feed_min_articles_default is not None:
            cmd.extend(['--feed-min-articles-default', str(feed_min_articles_default)])
        if feed_ttl_default is not None:
            cmd.extend(['--feed-ttl-default', str(feed_ttl_default)])
        if since_hours_posts_per_rss is not None:
            cmd.extend(['--since-hours-posts-per-rss', str(since_hours_posts_per_rss)])
        if max_posts_per_rss is not None:
            cmd.extend(['--max-posts-per-rss', str(max_posts_per_rss)])
        if no_default_feeds:
            cmd.append('--no-default-feeds')

        returncode, stdout, stderr = self._run_command(cmd)
        return returncode == 0, stdout, stderr

    def remove_user(self, username):
        """Remove a user"""
        cmd = [self.php_binary, os.path.join(self.cli_path, 'delete-user.php')]
        cmd.extend(['--user', username])
        returncode, stdout, stderr = self._run_command(cmd)
        return returncode == 0, stdout, stderr

    def update_user(self, username, password=None, email=None, language=None):
        """Update user information"""
        cmd = [self.php_binary, os.path.join(self.cli_path, 'update-user.php')]
        cmd.extend(['--user', username])

        if password:
            cmd.extend(['--password', password])
        if email:
            cmd.extend(['--email', email])
        if language:
            cmd.extend(['--language', language])

        returncode, stdout, stderr = self._run_command(cmd)
        return returncode == 0, stdout, stderr

    def get_user_info(self, username):
        """Get user information"""
        cmd = [self.php_binary, os.path.join(self.cli_path, 'user-info.php')]
        cmd.extend(['--user', username])
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
            except Exception:
                pass
        return {}


def main():
    module_args = dict(
        username=dict(type='str', required=True),
        state=dict(type='str', default='present', choices=['present', 'absent']),
        password=dict(type='str', no_log=True),
        email=dict(type='str'),
        api_password=dict(type='str', no_log=True),
        language=dict(type='str', default='en'),
        token=dict(type='str', no_log=True),
        purge_after_months=dict(type='int'),
        feed_min_articles_default=dict(type='int'),
        feed_ttl_default=dict(type='int'),
        since_hours_posts_per_rss=dict(type='int'),
        max_posts_per_rss=dict(type='int'),
        no_default_feeds=dict(type='bool', default=False),
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
    api_password = module.params['api_password']
    language = module.params['language']
    token = module.params['token']
    purge_after_months = module.params['purge_after_months']
    feed_min_articles_default = module.params['feed_min_articles_default']
    feed_ttl_default = module.params['feed_ttl_default']
    since_hours_posts_per_rss = module.params['since_hours_posts_per_rss']
    max_posts_per_rss = module.params['max_posts_per_rss']
    no_default_feeds = module.params['no_default_feeds']

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

            success, stdout, stderr = manager.add_user(
                username, password, email, language, api_password, token,
                purge_after_months, feed_min_articles_default, feed_ttl_default,
                since_hours_posts_per_rss, max_posts_per_rss, no_default_feeds
            )
            if success:
                result['changed'] = True
                result['msg'] = f"User {username} created successfully"
                result['user_exists'] = True
            else:
                module.fail_json(msg=f"Failed to create user {username}: {stderr}")
        else:
            # User exists, check if we need to update anything
            changes_needed = {}
            user_info = manager.get_user_info(username)

            # Always update password if provided (we can't check current password)
            if password:
                changes_needed['password'] = password

            # Check email
            if email and user_info.get('email', '') != email:
                changes_needed['email'] = email

            # Check language
            if language and user_info.get('language', '') != language:
                changes_needed['language'] = language

            if changes_needed:
                if module.check_mode:
                    result['changed'] = True
                    result['msg'] = f"Would update user {username}: {', '.join(changes_needed.keys())}"
                    module.exit_json(**result)

                success, stdout, stderr = manager.update_user(
                    username,
                    password=changes_needed.get('password'),
                    email=changes_needed.get('email'),
                    language=changes_needed.get('language'),
                )

                if success:
                    result['changed'] = True
                    result['msg'] = f"User {username} updated: {', '.join(changes_needed.keys())}"
                else:
                    module.fail_json(msg=f"Failed to update user {username}: {stderr}")
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
