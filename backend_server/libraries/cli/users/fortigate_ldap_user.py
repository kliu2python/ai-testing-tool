from libraries.cli.users.fortigate_user import FortigateUser
from libraries.cli.ldap_server import ldapServer


class FortigateLdapUser(FortigateUser):
    def __init__(self, name: str, ldap_server: ldapServer, password: str = None,
                 vpn_group: str = None, is_admin: bool = False,
                 remote_group: str = None, unique_id: str = None):
        super().__init__(name, is_admin, password, vpn_group=vpn_group)
        self.ldap_server = ldap_server
        self.name = f"{name}-{unique_id}"
        self.remote_group = remote_group

    def __str__(self):
        return str(self.__dict__)
