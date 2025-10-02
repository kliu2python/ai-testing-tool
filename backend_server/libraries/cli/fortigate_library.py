from json import loads
from re import search, findall
from typing import List, Union

from libraries.api.taas.pool import Pool
from libraries.cli.commands import Commands
from libraries.cli.ldap_server import ldapServer
from libraries.cli.ssh_connection import SSHConnection
from libraries.cli.users.fac_user import FacUser
from libraries.cli.users.fortigate_ldap_user import FortigateLdapUser
from libraries.cli.users.fortigate_user import FortigateUser
from libraries.logger.test_logger import get_logger
from libraries.selenium.session_data import SessionData
from suites.fortigate.suites.fortitoken.resources import auth_2fa
from suites.fortinet_one.suites.token.libraries.users import Users
from suites.fortinet_one.suites.token.libraries.vdoms import Vdoms
from suites.fortinet_one.suites.token.resources.variables import VPN_GROUPS

logger = get_logger()


class FortigateBase(SSHConnection, Commands):
    def __init__(
            self,
            session_data=None,
            dns=None,
            email_un=None,
            fortigate_ip=None,
            fortigate_un=None,
            fortigate_pw=None,
            alternate_ip=None,
            timeout=30,
            display=False
    ):
        if session_data is None:
            session_data = SessionData()
        self.session_data = session_data

        self.alternate_ip = alternate_ip

        if dns is None:
            dns = session_data.dns
            if dns is None:
                dns = ["96.45.45.45", "96.45.46.46"]
        self.dns = dns

        if email_un is None:
            email_un = session_data.email_un
        self.email = email_un

        if fortigate_ip is None:
            fortigate_ip = session_data.fortigate_ip
        self.fortigate_ip = fortigate_ip

        if fortigate_un is None:
            fortigate_un = session_data.fortigate_un
        self.fortigate_un = fortigate_un

        if fortigate_pw is None:
            fortigate_pw = session_data.fortigate_pw
        self.fortigate_pw = fortigate_pw

        if session_data.default_timeout is not None:
            timeout = session_data.default_timeout

        SSHConnection.__init__(
            self,
            self.fortigate_ip,
            self.fortigate_un,
            self.fortigate_pw,
            timeout=timeout,
            display=display
        )
        self.users = Users(self.fortigate_ip)
        self.vdoms = Vdoms(self.fortigate_ip)
        self.pool = Pool(self.fortigate_ip)

    class CLIMapping:
        def __init__(self, value, pattern, name):
            self._value = value
            self.pattern = pattern
            self.name = name

        @property
        def value(self):
            return self._value

        @value.setter
        def value(self, new_value):
            if type(self._value) in {list, set}:
                self._value.append(new_value)
            else:
                self._value = new_value

    # TODO rebuild using CLI Mapping?
    @staticmethod
    def extract_name(line):
        return findall(r'(?<=").*(?=")', line)[0]

    @staticmethod
    def include_mutli_vdom(commands: list, mulit_vdom=True, vdom_name='root'):
        if mulit_vdom:
            commands = ['config vdom', f'edit {vdom_name}'] + commands
        return commands

    @staticmethod
    def extract_json(s: str) -> dict:
        if isinstance(s, list):
            s = '\n'.join(s)
        return loads(search(r'{.*\}', s).group())

    @staticmethod
    def ssh_str(ip: str, mode: str = 'centos') -> str:
        return f'execute ssh {mode}@{ip}'

    @staticmethod
    def parse_values_from_lines(lines, cli_mappings):
        # creates dictionary mapping of supplied cli_mappings
        lines = [x.strip() for x in lines]
        lines.sort()
        cli_mappings.sort(key=lambda x: x.pattern)

        i = 0
        j = 0

        while i < len(lines) and j < len(cli_mappings):
            # if current line matches current cli_value
            if cli_mappings[j].pattern in lines[i]:
                # set cli_property value to line value
                cli_mappings[j].value = lines[i].split()[-1]
                if type(cli_mappings[j].value) not in {list, set}:
                    j += 1
                i += 1
            # increment the pointer for the alphabetically smaller string
            elif sorted([lines[i], cli_mappings[j].pattern])[0] == lines[i]:
                i += 1
            else:
                j += 1
        results = {x.name: x.value for x in cli_mappings}

        if len(results) == 1:
            return list(results.values())[0]
        return results

    def end(self, multi_vdom, ignore_error=False):
        end_count = 1 + int(multi_vdom)
        return self.send_commands(['end'] * end_count,
                                  ignore_error=ignore_error)

    def execute_cmd(self, timeout, display, ignore_error=False):
        ret = self.send_commands(
            self.commands, timeout=timeout,
            display=display, ignore_error=ignore_error
        )
        self.reset_commands()
        return ret

    def create_user(
            self, new_user: FortigateUser, email=None,
            password=1234, timeout=15, two_factor='fortitoken-cloud',
            multi_vdom=True, display=True, vdom_name='root',
            sms_phone=None, fortitoken=None, ignore_error=False
    ):
        if new_user.is_admin:
            commands = [
                'config system admin',
                f'edit "{new_user.name}"',
                'set accprofile "super_admin"',
                'set vdom "root"',
                f'set password {password}',
            ]
            if multi_vdom:
                commands = ['config global'] + commands
        else:
            commands = [
                'config user local',
                f'edit {new_user.name}',
            ]
            if hasattr(new_user, "ldap_server"):
                auth_setting = [
                    'set type ldap',
                    f'set ldap-server {new_user.ldap_server}'
                ]
            elif hasattr(new_user, "radius_server"):
                if new_user.radius_server is not None:
                    auth_setting = [
                        'set type radius',
                        f'set radius-server {new_user.radius_server}'
                    ]
            else:
                auth_setting = [
                    'set type password',
                    f'set passwd {password}',
                ]
            commands.extend(auth_setting)
            if multi_vdom:
                commands = ['config vdom', f'edit {vdom_name}'] + commands
        if email is None:
            email = self.session_data.email_un
        if two_factor:
            commands.extend([f'set two-factor {two_factor}'])
        if fortitoken:
            commands.extend([f'set fortitoken {fortitoken}'])
        if sms_phone:
            commands.extend([f'set sms-phone {sms_phone}'])
        if email:
            commands.extend([f'set email-to {email}'])
        results = self.send_commands(commands, timeout=timeout, display=display,
                                     ignore_error=ignore_error)
        results.append(self.end(multi_vdom, ignore_error=ignore_error))
        if 'Failed' in results[-1][1] or 'Unable' in results[-1][1]:
            return None
        if new_user.vpn_group is not None:
            results.append(
                self.modify_users_in_vpn(new_user, multi_vdom, vdom_name))
        return new_user.name

    def _purge(self, commands):
        self.send_commands(commands)
        self.send_command('purge')
        self.send_command('y', exp='n)', exp_output='#')

    def get_user_groups(self, multi_vdom=True, vdom_name='root'):

        def construct_groupings(results):
            groupings = {}
            current_group = None
            for r in results:
                if 'edit' in r:
                    current_group = self.extract_name(r)
                    groupings[current_group] = []
                elif 'set' in r:
                    new_user = FortigateUser(self.extract_name(r))
                    groupings[current_group].append(new_user)
            return groupings

        commands = [
            'config user group',
            'show',
        ]
        commands = self.include_mutli_vdom(commands, multi_vdom, vdom_name)
        results = self.send_commands(commands)
        results = results[4].split('\n')
        self.end(multi_vdom)
        return construct_groupings(results)

    def purge_user_groups(self, multi_vdom=True, vdom_name='root'):
        commands = [
            'config user groups'
        ]
        commands = self.include_mutli_vdom(commands, multi_vdom, vdom_name)
        self._purge(commands)
        self.end(multi_vdom)

    def purge_users(self, multi_vdom=True, vdom_name='root'):
        commands = [
            'config user local'
        ]
        commands = self.include_mutli_vdom(commands, multi_vdom, vdom_name)
        self._purge(commands)
        self.end(multi_vdom)

    def modify_users_in_vpn(
            self,
            user: Union[
                List[FortigateUser], FortigateUser, FacUser,
                List[FacUser]] = None,
            multi_vdom=True,
            vdom_name='root',
            delete=False
    ):
        """
        Example of commands:

        config vdom
        edit root
        config user groups
        set member <name>
        end
        end
        """
        commands = [
            'config user group'
        ]
        vpn_names = [user.vpn_group] if user else VPN_GROUPS
        for vpn_name in vpn_names:
            commands += [
                f'edit {vpn_name}',
            ]
            if delete:
                commands.append('unset member')
            else:
                if isinstance(user, FacUser) and hasattr(user, "fac_name"):
                    name = user.fac_name
                else:
                    name = user.name
                commands.append(f'append member {name}')
            commands.append('next')
        commands = self.include_mutli_vdom(commands, multi_vdom, vdom_name)
        results = self.send_commands(commands)
        results.append(self.end(multi_vdom))
        return results

    def delete_user(
            self, user: FortigateUser, multi_vdom=True, vdom_name='root',
            timeout=15, display=True, ignore_error=False
    ):
        if user.is_admin:
            commands = [
                'config system admin',
                f'delete "{user.name}"'
            ]
            if multi_vdom:
                commands = ['config global'] + commands
        else:
            commands = [
                'config user local',
                f'delete {user.name}'
            ]
            if multi_vdom:
                commands = ['config vdom', f'edit {vdom_name}'] + commands
        commands.extend([
            'end',
            'end'
        ])
        return self.send_commands(commands, timeout=timeout,
                                  display=display, ignore_error=ignore_error)

    def delete_mfa(
            self, user: FortigateUser, multi_vdom=True, vdom_name='root',
            timeout=15, display=True, ignore_error=False
    ):
        if user.is_admin:
            commands = [
                'config system admin',
                f'edit "{user.name}"',
                'unset two-factor'
            ]
            if multi_vdom:
                commands = ['config global'] + commands
        else:
            commands = [
                'config user local',
                f'edit "{user.name}"',
                'unset two-factor'
            ]
            if multi_vdom:
                commands = ['config vdom', f'edit {vdom_name}'] + commands
        commands.extend([
            'end',
            'end'
        ])
        return self.send_commands(commands, timeout=timeout,
                                  display=display, ignore_error=ignore_error)

    def ping(self, ip, alternate=False):
        commands = []
        if isinstance(ip, FortigateBase):
            if alternate:
                ip = ip.alternate_ip
                commands = [
                    f'execute ping-options source {self.alternate_ip}',
                ]
            else:
                ip = ip.hostname
        commands.append(f'execute ping {ip}')
        ping_results = ''.join(self.send_commands(commands))
        return bool(search('[^0] packets received', ping_results))

    def set_dns(self, dns=None):
        if dns or self.dns:
            dns = dns if dns else self.dns
            if isinstance(dns, list):
                dns1 = dns[0]
                dns2 = dns[1]
            else:
                dns1 = dns
                dns2 = dns
            commands = [
                'config global',
                'config system dns',
                f'set primary {dns1}',
                f'set secondary {dns2}',
                'set protocol cleartext'
            ]
            commands.extend(['end', 'end'])
            return self.send_commands(commands)

    def sync(self):
        commands = [
            'config global',
            'execute fortitoken-cloud sync',
            'end'
        ]
        return self.send_commands(commands)

    def validate_sync(self, create=0, modify=0, delete=0):
        self.set_dns()
        json = self.extract_json(self.sync())
        if json['status'] == 'complete':
            json = json['msg']
        else:
            assert False, f'Something went wrong, please see json body:\n{json}'

        created = json['create']['success']
        modified = json['modify']['success']
        deleted = json['delete']['success']
        assert created == (create, f'Sync count: Created did not match. Found'
                                   f' {created}, expected {create}')
        assert modified == (modify, f'Sync count: Created did not match. '
                                    f'Found {modified}, expected {modify}')
        assert deleted == (delete, f'Sync count: Created did not match. Found'
                                   f' {deleted}, expected {delete}')

        assert json['create']['failure'] == json['modify']['failure'] == \
               json['delete'][
                   'failure'] == 0, 'Sync failure reported'
        return json

    def set_management_vdom(self, vdom='root'):
        commands = [
            'config global',
            'config system global',
            f'set management-vdom {vdom}',
            'end',
            'end'
        ]
        self.send_commands(commands)

    def get_version(self):
        results = self.send_command('get system status | grep Version:',
                                    exp_output=None).split()
        return ' '.join(results[8:-2])

    def get_sn(self):
        results = self.send_command('get system status | grep Serial-Number:',
                                    exp_output=None).split()
        logger.info(f"The result is {results}")
        return results[7]

    def set_global_vdom_mode(self, vdom_mode):
        commands = [
            'config system global',
            f'set vdom-mode {vdom_mode}',
            'end',
            'y'
        ]
        self.send_commands(commands)

    def create_vdom(self, vdom_name, check_exist=False):
        if check_exist:
            commands = [
                'config global',
                'diag sys vd list | grep name'
            ]
            res = self.send_commands(commands)
            for name in res:
                if name.split(" ") in [f'name={vdom_name}/{vdom_name}']:
                    commands = [
                        'end',
                        'config vdom',
                        f'delete {vdom_name}'
                    ]
                    self.send_commands(commands)
        commands = [
            'config vdom',
            f'edit {vdom_name}',
            'end'
        ]
        self.send_commands(commands)

    def assign_interface(self, interface_name, vdom_name):
        commands = [
            'config global',
            'config system interface',
            f'edit {interface_name}',
            f'set vdom {vdom_name}',
            'set mode dhcp',
            'set allowaccess ping https ssh snmp http telnet fgfm radius-acct'
            ' probe-response fabric ftm',
            'end',
            'end'
        ]
        self.send_commands(commands)

    def unassign_interface(self, interface_name):
        commands = [
            'config global',
            'config system interface',
            f'edit {interface_name}',
            'set vdom root',
            'set mode static',
            'set ip 0.0.0.0/0',
            'end',
            'end'
        ]
        self.send_commands(commands)

    def delete_vdom(self, vdom_name):
        commands = [
            'config vdom',
            f'delete {vdom_name}',
            'end'
        ]
        self.send_commands(commands)

    def update(self):
        commands = [
            'config global',
            'execute fortitoken-cloud update',
            'end'
        ]
        return self.send_commands(commands, display=True)

    def set_ldap_server(self, ldap_server: ldapServer, vdom="root"):
        commands = [
            'config vdom',
            f'edit {vdom}',
            'config user ldap',
            f'edit {ldap_server.name}',
            f'set server {ldap_server.ip}',
            f'set cnid {ldap_server.cnid}',
            f'set type {ldap_server.type}',
            f'set dn {ldap_server.dn}',
            f'set username {ldap_server.username}',
            f'set password {ldap_server.password}',
            'end',
            'end'
        ]
        return self.send_commands(commands, display=True)

    def create_ldap_user(
            self, new_user: FortigateLdapUser, email, timeout=15,
            two_factor='fortitoken-cloud',
            multi_vdom=True, display=True, vdom_name='root'
    ):
        commands = [
            'config user local',
            f'edit {new_user.name}',
            'set type ldap',
            f'set ldap {new_user.ldap_server.name}',
            f'set two-factor {two_factor}',
            f'set email-to {email}',
            'end'
        ]
        if multi_vdom:
            commands = ['config vdom', f'edit {vdom_name}'] + commands
            commands.extend(["end"])
        return self.send_commands(commands, timeout=timeout, display=display)

    def set_ldap_group(self, remote_group, ldap_server, timeout=15,
                       multi_vdom=True, display=True, vdom_name='root'):
        commands = [
            'config user group',
            f'edit {remote_group}',
            f'set member {ldap_server}',
            'end'
        ]
        if multi_vdom:
            commands = ['config vdom', f'edit {vdom_name}'] + commands
            commands.extend(["end"])
        return self.send_commands(commands, timeout=timeout, display=display)

    def create_ldap_admin(
            self, new_user: FortigateLdapUser, email,
            password=1234, timeout=15, two_factor='fortitoken-cloud',
            multi_vdom=True, display=True, vdom_name='root'
    ):
        commands = [
            'config system admin',
            f'edit "{new_user.name}"',
            'set remote-auth enable',
            'set accprofile "super_admin"',
            f'set vdom {vdom_name}',
            f'set remote-group {new_user.remote_group}',
            f'set password {password}',
            f'set two-factor {two_factor}',
            f'set email-to {email}',
            'end',
        ]
        if multi_vdom:
            commands = ['config global'] + commands
            commands.extend(['end'])
        return self.send_commands(commands, timeout=timeout, display=display)

    def set_fgt_admin_timeout(self, timeout_val=480):
        set_timeout_commands = [
            'config system global',
            f'set admintimeout {timeout_val}',
            'end',
        ]
        self.send_commands(set_timeout_commands, exp='#')

    def get_fgt_log_display(self):
        self.send_command('exe log display', exp='#')
        return self.get_output()

    def fgt_log_delete(self):
        self.send_command('exe log delete', exp='#')

    def set_fgt_group_id_ha(self, group_id_ha):
        set_group_id_ha = [
            'config sys ha',
            f'set group-id {group_id_ha}',
            'end'
        ]
        self.send_commands(set_group_id_ha, exp='#')

    def show_fgt_sys_ha(self):
        self.send_command('show sys ha', exp='#')

    def unset_group_id_ha(self):
        unset_group_id_ha = [
            'config sys ha',
            'unset group-id',
            'end'
        ]
        self.send_commands(unset_group_id_ha, exp='#')

    def set_fgt_group_name_ha(self, group_name_ha):
        set_group_name_ha = [
            'config sys ha',
            f'set group-name {group_name_ha}',
            'end'
        ]
        self.send_commands(set_group_name_ha, exp='#')

    def unset_group_name_HA(self):
        unset_group_name_ha = [
            'config sys ha',
            'unset group-name',
            'end'
        ]
        self.send_commands(unset_group_name_ha, exp='#')

    def set_mode_ha(self, ha_mode):
        set_mode_ha = [
            'config sys ha',
            f'set mode {ha_mode}',
            'end'
        ]
        self.send_commands(set_mode_ha, exp='#')

    def set_pw_ha(self, ha_pw):
        set_pw_ha = [
            'config sys ha',
            f'set password {ha_pw}',
            'end'
        ]
        self.send_commands(set_pw_ha, exp='#')

    def set_ha_hbdev(self, hbdev1, hbdev2):
        set_ha_hbdev = [
            'config sys ha'
            f'set hbdev {hbdev1} 100 {hbdev2} 50'
            'end'
        ]
        self.send_commands(set_ha_hbdev, exp='#')

    def set_ha_sync_config_enable(self):
        set_ha_sync_enable = [
            'config sys ha',
            'set sync-config enable',
            'end'
        ]
        self.send_commands(set_ha_sync_enable, exp='#')

    def set_ha_sync_config_disable(self):
        set_ha_sync_disable = [
            'config sys ha',
            'set sync-config disable',
            'end'
        ]
        self.send_commands(set_ha_sync_disable, exp='#')

    def set_ha_encryption_enable(self):
        set_ha_enc_enable = [
            'config sys ha',
            'set encryption enable',
            'end'
        ]
        self.send_commands(set_ha_enc_enable, exp='#')

    def set_ha_encryption_disable(self):
        set_ha_enc_disable = [
            'config sys ha',
            'set encryption disable',
            'end'
        ]
        self.send_commands(set_ha_enc_disable, exp='#')

    def set_ha_auth_enable(self):
        set_ha_auth_enable = [
            'config sys ha',
            'set authentication enable',
            'end'
        ]
        self.send_commands(set_ha_auth_enable, exp='#')

    def set_ha_auth_disable(self):
        set_ha_auth_disable = [
            'config sys ha',
            'set authentication disable',
            'end'
        ]
        self.send_commands(set_ha_auth_disable, exp='#')

    def set_ha_session_pickup_enable(self):
        set_ha_session_pickup_enable = [
            'config sys ha',
            'set session-pickup enable',
            'end'
        ]
        self.send_commands(set_ha_session_pickup_enable, exp='#')

    def set_ha_session_pickup_disable(self):
        set_ha_session_pickup_disable = [
            'config sys ha',
            'set session-pickup disable',
            'end'
        ]
        self.send_commands(set_ha_session_pickup_disable, exp='#')

    def set_ha_link_failed_signal_enable(self):
        set_ha_link_failed_signal_enable = [
            'config sys ha',
            'set link-failed-signal enable',
            'end'
        ]
        self.send_commands(set_ha_link_failed_signal_enable, exp='#')

    def set_ha_link_failed_signal_disable(self):
        set_ha_link_failed_signal_disable = [
            'config sys ha',
            'set link-failed-signal disable',
            'end'
        ]
        self.send_commands(set_ha_link_failed_signal_disable, exp='#')

    def set_ha_override_enable(self):
        set_ha_override_enable = [
            'config sys ha',
            'set override enable',
            'end'
        ]
        self.send_commands(set_ha_override_enable, exp='#')

    def set_ha_override_disable(self):
        set_ha_override_disable = [
            'config sys ha',
            'set override disable',
            'end'
        ]
        self.send_commands(set_ha_override_disable, exp='#')

    def set_ha_priority_out_of_range(self):
        set_ha_priority_out_of_range = [
            'config sys ha',
            'set priority 256',
            'end'
        ]
        self.send_commands(set_ha_priority_out_of_range, exp='#')

    def set_ha_priority(self):
        set_ha_priority = [
            'config sys ha',
            f'set priority 255',
            'end'
        ]
        self.send_commands(set_ha_priority, exp='#')

    def set_ipsec_phase1_interface_fgt_proposal(self, fgt_a_b, interface_name,
                                                remote_gw, psksecret, set_mode):
        set_ipsec_phase1_interface = [
            'config vpn_group ipsec phase1-interface',
            f'edit {fgt_a_b}',
            f'set interface {interface_name}',
            f'set remote-gw {remote_gw}',
            f'set psksecret {psksecret}',
            f'set mode {set_mode}',
            'end'
        ]
        self.send_commands(set_ipsec_phase1_interface, exp='#')

    def set_ipsec_phase1_interface_fgt(self, fgt_a_b, interface_name, proposal,
                                       remote_gw, psksecret,
                                       ipsec_dhgrp, dhgrp_status=False,
                                       set_mode='main'):
        if not proposal:
            if not dhgrp_status:
                set_ipsec_phase1_interface = [
                    'config vpn_group ipsec phase1-interface',
                    f'edit {fgt_a_b}',
                    f'set interface {interface_name}',
                    f'set remote-gw {remote_gw}',
                    f'set psksecret {psksecret}',
                    f'set mode {set_mode}',
                    'end'
                ]
            else:
                set_ipsec_phase1_interface = [
                    'config vpn_group ipsec phase1-interface',
                    f'edit {fgt_a_b}',
                    f'set interface {interface_name}',
                    f'set remote-gw {remote_gw}',
                    f'set dhgrp {ipsec_dhgrp}',
                    f'set psksecret {psksecret}',
                    f'set mode {set_mode}',
                    'end'
                ]
            self.send_commands(set_ipsec_phase1_interface, exp='#')

        else:
            if not dhgrp_status:
                set_ipsec_phase1_interface = [
                    'config vpn_group ipsec phase1-interface',
                    f'edit {fgt_a_b}',
                    f'set interface {interface_name}',
                    f'set proposal {proposal}',
                    f'set remote-gw {remote_gw}',
                    f'set psksecret {psksecret}',
                    f'set mode {set_mode}',
                    'end'
                ]
            else:
                set_ipsec_phase1_interface = [
                    'config vpn_group ipsec phase1-interface',
                    f'edit {fgt_a_b}',
                    f'set interface {interface_name}',
                    f'set proposal {proposal}',
                    f'set dhgrp {ipsec_dhgrp}',
                    f'set remote-gw {remote_gw}',
                    f'set psksecret {psksecret}',
                    f'set mode {set_mode}',
                    'end'
                ]

            self.send_commands(set_ipsec_phase1_interface, exp='#')

    def set_ipsec_phase2_interface_fgt(self, fgt_a_b, phase1name, proposal,
                                       src_subnet, dst_subnet):
        set_ipsec_phase2_interface = [
            'config vpn_group ipsec phase2-interface',
            f'edit {fgt_a_b}',
            f'set phase1name {phase1name} ',
            f'set proposal {proposal}',
            f'set src-subnet {src_subnet}',
            f'set dst-subnet {dst_subnet} ',
            'end'
        ]
        self.send_commands(set_ipsec_phase2_interface, exp='#')

    def set_router_static_remote_network(self, static_number: str, dst: str,
                                         device: str):
        set_router_static = [
            'config router static',
            f'edit {static_number}',
            f'set dst {dst}',
            f'set device {device}',
            'end'
        ]
        self.send_commands(set_router_static, exp='#')

    def set_router_static(self, static_number: str, dst: str, device: str,
                          gateway: str = None):
        set_router_static = [
            'config router static',
            f'edit {static_number}',
            f'set dst {dst}',
            f'set device {device}',
            f'set gateway {gateway}',
            'end'
        ]
        self.send_commands(set_router_static, exp='#')

    def set_firewall_policy(self, firewall_number, srcintf, dstintf,
                            srcaddr='all', dstaddr='all', action='accept',
                            schedule='always', service='ALL', nat='disable'):
        set_firewall_policy = [
            'config firewall policy',
            f'edit {firewall_number}',
            f'set srcintf {srcintf}',
            f'set dstintf {dstintf}',
            f'set srcaddr {srcaddr}',
            f'set dstaddr {dstaddr}',
            f'set action {action}',
            f'set schedule {schedule}',
            f'set service {service}',
            f'set nat {nat}',
            'end'
        ]
        self.send_commands(set_firewall_policy, exp='#')

    def unset_virtual_switch_interface_internal(self, virtual_switch_interface,
                                                ipsec_hosta_interface,
                                                ipsec_interface1,
                                                ipsec_interface2,
                                                ipsec_interface3,
                                                ipsec_interface4,
                                                ipsec_hostb_interface):
        unset_interface = [
            'config system virtual-switch',
            f'edit {virtual_switch_interface}',
            'config port',
            f'delete {ipsec_hosta_interface}',
            f'delete {ipsec_interface1}',
            f'delete {ipsec_interface2}',
            f'delete {ipsec_interface3}',
            f'delete {ipsec_interface4}',
            f'delete {ipsec_hostb_interface}',
            'y',
            'end',
            'end'
        ]
        self.send_commands(unset_interface, exp='#')

    def unset_virtual_switch_interface_fortilink(self):
        unset_interface = [
            'config system virtual-switch',
            'edit fortilink',
            'config port',
            'delete b',
            'end',
            'end'
        ]
        self.send_commands(unset_interface, exp='#')

    # TODO: FORTILINK To Set Interface
    # def set_interface_vdom(self, internal1='internal1',
    # internal_hosta='internal4', vdom_1='VD_IPSEC_1',
    # internal2='internal2', internal3='internal3',
    # vdom_2='VD_IPSEC_2', internal4='internal5',
    # b='b', vdom_3='VD_IPSEC_3'):
    def set_interface_vdom(self, internal1='internal1',
                           internal_hosta='internal4', vdom_1='VD_IPSEC_1',
                           internal2='internal2', internal3='internal3',
                           vdom_2='VD_IPSEC_2', internal4='internal5',
                           vdom_3='VD_IPSEC_3',
                           internal_hostb='ipsec_hostb_interface'):
        interface_vdom = [
            'config vdom',
            'edit root',
            'config system interface',
            f'edit {internal1}',
            f'set vdom {vdom_1}',
            'set ip 192.168.10.1 255.255.255.0',
            'set allowaccess ping https ssh snmp http telnet',
            'next',
            f'edit {internal2}',
            f'set vdom {vdom_2}',
            'set ip 192.168.10.2 255.255.255.0',
            'set allowaccess ping https ssh snmp http telnet',
            'next',
            f'edit {internal3}',
            f'set vdom {vdom_2}',
            'set ip 192.168.30.2 255.255.255.0',
            'set allowaccess ping https ssh snmp http telnet',
            'next',
            f'edit {internal_hosta}',
            f'set vdom {vdom_1}',
            'set ip 192.168.1.1 255.255.255.0',
            'set allowaccess ping https ssh snmp http telnet',
            'next',
            f'edit {internal4}',
            f'set vdom {vdom_3}',
            'set ip 192.168.30.1 255.255.255.0',
            'set allowaccess ping https ssh snmp http telnet',
            'next',
            f'edit {internal_hostb}',
            f'set vdom {vdom_3}',
            'set ip 192.168.3.1 255.255.255.0',
            'set allowaccess ping https ssh snmp http telnet',
            'next',
            'end',
            'end'
        ]
        self.send_commands(interface_vdom, exp='#')

    def disconnect_admin_session(self, admin_list):
        commands = [
            'config global',
            'execute disconnect-admin-session ?',
        ]
        output = self.send_commands(commands)
        cmd = []
        for admin in admin_list:
            for session in output[2].split("\n")[4::2]:
                if admin.name in session:
                    logger.info(f"Trying to logout {admin.name}")
                    session_id = output[2].split("\n")[4::2].index(session)
                    cmd.append(
                        f'execute disconnect-admin-session {session_id}'
                    )
                    break
        cmd.append('end')
        self.send_commands(cmd)
