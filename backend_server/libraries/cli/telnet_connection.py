from libraries.cli import telnet_permissions as permissions
from telnetlib import Telnet
from time import sleep


class TelnetConnection:
    def __init__(self, hostname, port: str = '23', default_timeout=15):
        if type(port) is int:
            port = str(int)
        self.hostname = hostname
        self.port = port
        self.con = None
        self.permission_level = permissions.unauthenticated
        self.default_timeout = default_timeout
        self.skip_exp = False
        self.last_output = ''

    def connect(self, hostname=None, port=None):
        if hostname is None:
            hostname = self.hostname
        if port is None:
            port = self.port
        self.con = Telnet(hostname, port)

    def quit(self):
        self.get_output(exp=False)
        self.con.close()

    def extract_output(self, exp, timeout=None, tolerant=True):
        if not self.skip_exp:
            if exp is False:
                if timeout is None:
                    sleep(2)
                else:
                    sleep(timeout)
                output = self.con.read_eager().decode()
                self.last_output = output
                return self.last_output

            if timeout is None:
                timeout = self.default_timeout
            if exp is None:
                exp = self.permission_level

        expected = str.encode(exp)
        output = self.con.read_until(expected, timeout=timeout).decode()
        self.last_output = output
        if exp not in output:
            error_string = f'TELNET: Something went wrong, {exp} not found in output: "{output}"'
            if tolerant:
                print(error_string)
            else:
                assert False, error_string

        return self.last_output

    def send_command(self, command=None, exp=None, display=True, new_line=True, timeout=None, tolerant=True, exp_output=False):
        first_output = None

        if self.skip_exp:
            self.skip_exp = False
        else:
            self.extract_output(exp=exp, timeout=timeout, tolerant=tolerant)

        if command is not None:
            if new_line:
                command += '\n'
            command = str.encode(command)
            self.con.write(command)

        if exp_output is not False:
            first_output = self.last_output
            self.extract_output(exp_output, timeout=timeout, tolerant=tolerant)
            self.skip_exp = True

        if display:
            if exp_output is False:
                previously = self.last_output
            else:
                previously = first_output
            if previously != '':
                print('PREVIOUSLY:')
                print(previously)

            print(f'SENT: {command}')

            if exp_output is not False:
                print('CURRENT:')
                print(self.last_output)
        return self.last_output

    def exit(self):
        print(self.send_command('exit'))

    def confirm(self):
        return self.send_command('y', exp=')')

    def get_output(self, exp=None, timeout=30):
        self.last_output = self.send_command(command=None, exp=exp, display=True, timeout=timeout)
        self.skip_exp = exp
        return self.last_output

    @staticmethod
    def log(value, header=False):
        output = f'\n*    {value}'
        if header:
            output = f'\n*{output}\n*'
        print(output)

    def send_commands(self, commands: list, exp=None, display=True, new_line=True, timeout=5):
        if type(commands) is str:
            commands = [commands]
        output = []
        for command in commands:
            output.append(self.send_command(command, exp=exp, display=display, new_line=new_line, timeout=timeout))
        if len(output) == 1:
            return output[0]
        return output

    def validate_unauthenticated(self):
        # checks for ':' in current output.  If found, updates default exp character
        output = self.get_output(exp=permissions.unauthenticated)
        if permissions.unauthenticated in output:
            self.permission_level = permissions.unauthenticated
        else:
            assert False, f'Should not have permissions, Output was: {output}'

    def validate_login(self):
        # checks for '>' in current output.  If found, updates default exp character
        output = self.get_output(exp=permissions.authenticated)
        if permissions.authenticated in output:
            self.permission_level = permissions.authenticated
        else:
            assert False, f'Failed to authenticate.  Output for attempt: {output}'

    def validate_elevation(self):
        # checks for '#' in current output.  If found, updates default exp character
        output = self.get_output(exp=permissions.elevated)
        if permissions.elevated in output:
            self.permission_level = permissions.elevated
        else:
            assert False, f'Failed to elevate permissions.  Output for attempt: {output}'

    def validate_connect_to_client(self):
        output = self.get_output(exp=permissions.elevated)
        if 'Login incorrect' not in output and permissions.elevated in output:
            self.permission_level = permissions.elevated
        else:
            assert False, f'Failed to authenticate to client.  Output for attempt: {output}'

    def authenticate(self, password, username=None, exp=None):
        if exp is None:
            exp = permissions.unauthenticated
        if username is None:
            return self.send_command(password, exp=exp)
        return self.send_commands([username, password], exp=exp)

    def login(self, password):
        self.authenticate(password)
        self.validate_login()

    def elevate_permissions(self, password):
        self.send_commands(['enable'])
        self.authenticate(password)
        self.validate_elevation()

    def connect_to_client(self, hostname, port):
        output = self.send_command(f'telnet {hostname} {port}')
        output += self.send_command('\n', exp=':')
        return output

    def get_status(self):
        return self.send_command('get system status')

    def clear_line(self, line_no, password=''):
        raise NotImplementedError('Implemented in child classes')

    def wait_for_console_activity(self, exp: str, timeout=20):
        for attempt in range(timeout):
            if exp in self.send_command('\n', exp=False, timeout=1):
                return
        assert False, f'{exp} not found in console feed for {timeout} seconds.'

    def is_connected(self, exp=None, timeout=None, display=False):
        self.send_command('get system status', exp=exp, timeout=timeout, display=display)
        return 'Version' in self.send_command(' ', exp=exp, timeout=timeout, display=display)

    def set_output_standard(self, exp=None, timeout=None, display=False):
        self.send_commands(['config global', 'config system console', 'set output standard', 'end', 'end'], exp=exp, timeout=timeout, display=display)