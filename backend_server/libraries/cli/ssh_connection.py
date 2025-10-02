import socket

import paramiko
from paramiko_expect import SSHClientInteraction
from time import sleep

from libraries.logger.test_logger import get_logger
from libraries.parallelization import parallel_decorator

logger = get_logger()


class CommandParseError(Exception):
    pass


class CommandFailedError(Exception):
    pass


class CommandUnknownActionError(Exception):
    pass


class SSHConnection:
    def __init__(self, hostname, username, password, timeout=30, display=True):
        self.hostname = hostname
        self.username = username
        self.password = password
        self.logger = get_logger(name=f"cli.{hostname}")
        self.timeout = timeout
        self.display = display
        self.disconnected = True
        self.skip_exp = None
        self.con = None

    def connect(self):
        client = paramiko.SSHClient()
        # Set SSH key parameters to auto accept unknown hosts
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=self.hostname,
            username=self.username,
            password=self.password
        )
        self.con = SSHClientInteraction(
            client,
            timeout=self.timeout,
            display=self.display,
            tty_height=1000,
            newline=''
        )
        self.skip_exp = False
        self.disconnected = False

    def extract_output(self, exp, timeout=None):
        if not self.skip_exp:
            if exp is False:
                if timeout is None:
                    sleep(2)
                    exp = '.*'
                else:
                    sleep(timeout)
            elif exp is None:
                exp = r'.*#.*'

            self.con.expect(exp, timeout=timeout, default_match_prefix='.*')
        return self.con.current_output

    def send_command(
            self,
            command=None,
            exp: str = None,
            display=False,
            new_line=True,
            timeout=None,
            exp_output=False,
            ignore_error=False
    ):
        if 'config global' in command or 'config vdom' in command:
            self.back_to_root()
        if self.disconnected:
            self.connect()
        first_output = None

        if self.skip_exp:
            self.skip_exp = False
        else:
            self.extract_output(exp=exp, timeout=timeout)

        if command is not None:
            if new_line:
                command += '\r'
            self.con.send(command)

        if exp_output is not False:
            first_output = self.con.current_output
            self.extract_output(exp_output, timeout=timeout)
            self.skip_exp = True

        if display:
            self.logger.info('PREVIOUSLY:')

            if exp_output is False:
                self.logger.info(self.con.current_output)
            else:
                self.logger.info(first_output)

            self.logger.info(f'SENT: {command}')

            if exp_output is not False:
                self.logger.info('CURRENT:')
                self.logger.info(self.con.current_output)

        curr_output = self.con.current_output
        self.logger.info(f"Last Command: {command}")
        if not ignore_error:
            if 'command parse error' in curr_output.lower():
                raise CommandParseError(curr_output)
            if "command fail" in curr_output.lower():
                raise CommandFailedError(curr_output)
            if "unknown action" in curr_output.lower():
                raise CommandUnknownActionError(curr_output)

        return curr_output

    def send_commands(
            self,
            commands: list,
            exp=None,
            display=True,
            timeout=None,
            new_line=True,
            ignore_error=False
    ):
        if isinstance(commands, str):
            commands = [commands]
        output = []
        cmd_len = len(commands)
        for i, command in enumerate(commands):
            if command in ["y", "n"]:
                last_new_line = True
                last_is_yn = True
            else:
                last_is_yn = False
                last_new_line = new_line
            if (
                    i + 1 < cmd_len
                    and commands[i + 1] in ["y", "n"]
                    and not last_is_yn
            ):
                out = self.send_command(
                    command,
                    exp,
                    display=display,
                    timeout=30,
                    new_line=last_new_line,
                    ignore_error=ignore_error,
                    exp_output=r"n\)"
                )
            else:
                out = self.send_command(
                    command,
                    exp,
                    display=display,
                    timeout=timeout,
                    new_line=last_new_line,
                    ignore_error=ignore_error
                )
            output.append(out)
        if new_line:
            output.append(
                self.send_command(
                    " ",
                    exp,
                    display=display,
                    timeout=timeout,
                    ignore_error=ignore_error
                )
            )

        if len(output) == 1:
            return output[0]
        return output

    def back_to_root(self):
        out = self.send_command("")
        is_root = False
        while not is_root:
            if "(" in out:
                if "Interim" not in out:
                    self.send_command(
                        "end"
                    )
                else:
                    break
            else:
                break
            out = self.send_command("")
        logger.info("Already back to root level")

    @parallel_decorator
    def send_commands_parallel(
            self, commands: list,
            exp=None,
            display=True,
            timeout=None,
            new_line=True
    ):
        return self.send_commands(
            commands, exp, display, timeout, new_line
        )

    def get_output(self):
        return self.con.current_output

    def quit(self):
        self.disconnected = True
        if self.con:
            self.get_output()
            self.con.close()

    @staticmethod
    def is_in_output(value, output):
        for line in output:
            if value in line:
                return True
        return False


class SshNoneInteractiveConnection:
    def __init__(self, host, username, password, timeout=2):
        self.host = host
        self.username = username
        self.password = password
        self.timeout = timeout

        self.client = None
        self.disconnected = True
        self.connect()

    def connect(self):
        self.client = paramiko.SSHClient()
        self.client.load_system_host_keys()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.client.connect(hostname=self.host, username=self.username,
                            password=self.password)
        self.disconnected = False

    def _send_commands(self, cmds):
        channel = self.client.invoke_shell()
        channel.settimeout(self.timeout)
        for cmd in cmds:
            channel.send(f"{cmd}\n")

        buffer = ""
        run = True
        while run:
            try:
                data = channel.recv(4096)
                data = data.decode("utf-8")
                if data:
                    buffer += data
            except socket.timeout:
                run = False
        channel.close()
        return buffer

    def send_command(self, cmd):
        return self.send_commands([cmd])

    def quit(self):
        self.client.close()
        self.disconnected = False

    def send_commands(self, cmds):
        retry = 5
        while retry > 0:
            try:
                return self._send_commands(cmds)
            except Exception as e:
                retry -= 1
                if retry <= 0:
                    raise e
                self.quit()
                self.connect()
