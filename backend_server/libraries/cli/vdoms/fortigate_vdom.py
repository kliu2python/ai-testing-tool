

class FortigateVdom:
    def __init__(self, name: str):
        self.name = None
        self.base_name = name

    def __str__(self):
        return str(self.__dict__)

    def get_vdom_name(self, ip):
        ip_add = ip.split('.', 2)[-1].replace('.', '_')
        self.name = f"{ip_add}_{self.base_name}"
