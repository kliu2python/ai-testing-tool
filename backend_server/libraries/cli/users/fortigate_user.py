class FortigateUser:
    def __init__(self, name: str, is_admin: bool = False, password: str = None,
                 vpn_group: str = None, token_name: str = None,
                 token_type: str = 'ftk'):
        self.name = self.base_name = name
        self.password = password
        self.is_admin = is_admin
        self.ignored_values = {'base_name', 'password'}
        self.vpn_group = vpn_group
        self.token_name = token_name
        self.token_type = token_type
    # TODO: update once users can exist in multiple vdoms

    def __eq__(self, other):
        def _get_filtered_values(obj):
            d = obj.__dict__
            return [d[value] for value in d if value not in self.ignored_values]

        if isinstance(other, FortigateUser):
            return _get_filtered_values(self) == _get_filtered_values(other)
        return False

    def __str__(self):
        return str(self.__dict__)

    def add_hostname_ip(self, ip):
        self.name = f'{self.base_name}-{ip.split(".")[-1]}'
