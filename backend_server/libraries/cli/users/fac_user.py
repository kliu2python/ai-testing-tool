from libraries.cli.users.fortigate_user import FortigateUser


class FacUser(FortigateUser):
    def __init__(self, name, password, user_type=None, vpn_group=None,
                 is_admin=False, fac_name=True, pin_value: str = None,
                 pin_length: str = None, fac_ip=None, admin_user: str = None,
                 fac_api_key: str = None, token_name=None, token_type=None):
        super().__init__(name, is_admin, password, vpn_group,
                         token_name=token_name, token_type=token_type)
        self.user_type = user_type
        self.pin_length = pin_length
        self.pin_value = pin_value
        self.fac_ip = fac_ip
        self.admin_user = admin_user
        self.fac_api_key = fac_api_key
        self.name = name
        if fac_name:
            self.fac_name = f"{fac_ip}-{self.user_type}"
