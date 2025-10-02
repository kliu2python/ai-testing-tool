from libraries.cli.users.fortigate_user import FortigateUser


class UserCollection:
    def __init__(self, host_ip):
        self.host_ip = host_ip

    def __setattr__(self, key, value):
        if isinstance(value, FortigateUser):
            value.add_hostname_ip(self.host_ip)
        self.__dict__[key] = value
