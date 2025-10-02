from libraries.cli.users.fortigate_user import FortigateUser


class FortigateRadiusUser(FortigateUser):
    def __init__(self, name: str, raidus_server: str, is_admin: bool = False,
                 vpn_group: str = None, user_type: str = None,
                 password: str = None):
        super().__init__(name, is_admin, password, vpn_group=vpn_group)
        self.vpn_group = vpn_group
        self.radius_server = raidus_server
        self.user_type = user_type

    def __str__(self):
        return str(self.__dict__)
