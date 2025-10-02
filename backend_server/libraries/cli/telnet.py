"""
This is new version of telnet library with more efficient and simple code
"""
import telnetlib
import re
from time import sleep

from libraries.logger.test_logger import get_logger


class TelnetConnection:
    def __init__(
        self,
        host,
        port,
        timeout=15
    ):
        self.host = host
        self.port = port
        self.logger = get_logger(name=f"cli.{host}")
        self.telnet_con = None
        self.last_out = None
        self.cmd_find_status = -1
        self.default_timeout = timeout
        self._last_port = 23

    def connect(self, port=None):
        if not port:
            port = self.port
        self._last_port = port
        self.logger.info(f"Telnet to {self.host}, port = {self.port}")
        retry = 10
        error = None
        while retry > 0:
            try:
                self.telnet_con = telnetlib.Telnet(self.host, port)
                self.logger.info("Console login successful")
                return
            except ConnectionRefusedError as e:
                self.logger.error("Console connect fail, retrying..")
                error = e
                retry -= 1
                sleep(3)
        if error:
            raise error

    def disconnect(self, ext_cmd="exit"):
        if ext_cmd:
            self.send_command(ext_cmd)
        try:
            if self.telnet_con:
                self.telnet_con.close()
        except Exception as e:
            self.logger.exception("Error when disconnect", exc_info=e)
        self.telnet_con = None

    def get_output(
            self,
            exp=None,
            timeout=None,
            must_find=False,
            display=True,
            waiting=0
    ):
        try:
            if not timeout:
                timeout = self.default_timeout
            if isinstance(exp, str):
                exp = [exp]
            if not exp:
                sleep(waiting)
                out = self.telnet_con.read_very_eager()
            else:
                exp = list(map(lambda x: x.encode(), exp))
                findings, _, out = self.telnet_con.expect(exp, timeout)
                self.cmd_find_status = findings
                if exp and findings == -1:
                    msg = f"Can not find {exp}"
                    if must_find:
                        raise LookupError(msg)
                    self.logger.error(msg)
            self.last_out = out.decode()
            if self.last_out and display:
                self.logger.info(self.last_out)
            return self.last_out
        except EOFError:
            self.logger.exception("EOF for get_output")

    def output_contains(self, content):
        return content in self.last_out

    def output_match(self, regx):
        return re.match(regx, self.last_out) is not None

    def send_command(
            self,
            cmd,
            exp=None,
            timeout=None,
            must_find=False,
            newline=True,
            display=True,
            waiting=0
    ):
        if display:
            self.logger.info(f">>> SEND: {cmd}")
        cmd = cmd.encode("ascii")
        if newline:
            cmd += b"\n"
        if not self.telnet_con:
            self.connect(self._last_port)
        self.telnet_con.write(cmd)
        if not timeout:
            timeout = self.default_timeout
        self.get_output(
            exp, timeout, must_find, display=display, waiting=waiting
        )
        return self.last_out

    def send_commands(self, cmds, exp="#", display=True, waiting=0):
        if not isinstance(cmds, list):
            raise ValueError("send_commands() only accept command list")
        output = []
        for cmd in cmds:
            out = self.send_command(
                cmd, exp=exp, display=display, waiting=waiting
            )
            output.append(out)
        return output
