from libraries.cli.vdoms.fortigate_vdom import FortigateVdom


class VdomCollection:
    def __init__(self, host_ip):
        self.host_ip = host_ip

    def __setattr__(self, key, value):
        if isinstance(value, FortigateVdom):
            value.get_vdom_name(self.host_ip)
        self.__dict__[key] = value
