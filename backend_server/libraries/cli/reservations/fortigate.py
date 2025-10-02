from libraries.cli.fortigate_library import FortigateBase


class Fortigate:
    def __init__(self, ip, username, password):
        super().__init__()
        self.ip = ip
        self.username = username
        self.password = password
        self.version = self._get_fgt_version()

    def _get_fgt_version(self):
        if self.ip not in ["disabled"]:
            return FortigateBase(
                fortigate_ip=self.ip,
                fortigate_un=self.username,
                fortigate_pw=self.password
            ).get_version()
        else:
            return "default"
