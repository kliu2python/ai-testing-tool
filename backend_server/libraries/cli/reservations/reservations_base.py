# Reservations are intended to be singleton classes to aid in network based test parameterization
class _ReservationsBase:
    def __init__(self):
        self.connections = []
        self.ip_adds = set()
        self.instantiated = False

    def _reserve(self, ip, username, password, connection, **kwargs):
        if ip not in self.ip_adds:
            self.ip_adds.add(ip)
            new_connection = connection(ip, username, password)
            new_connection.__dict__.update(kwargs)
            self.connections.append(new_connection)
            self.instantiated = True

    def __str__(self):
        return self.ip_adds

    def __iter__(self):
        for conn in self.connections:
            yield conn
