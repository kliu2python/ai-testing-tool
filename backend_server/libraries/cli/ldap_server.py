class ldapServer:
    def __init__(self, name: str, ip: str, username: str, password: str, dn: str,
                 cnid: str = 'uid', type: str = "regular"):
        self.name = name
        self.ip = ip
        self.username = username
        self.password = password
        self.dn = dn
        self.cnid = cnid
        self.type = type

    def __str__(self):
        return str(self.__dict__)