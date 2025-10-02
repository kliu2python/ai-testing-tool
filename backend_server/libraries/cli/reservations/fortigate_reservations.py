from singleton_decorator import singleton

from ai-testint-tool.libraries.cli.reservations.reservations_base import _ReservationsBase
from ai-testint-tool.libraries.cli.reservations.fortigate import Fortigate


@singleton
class FortigateReservations(_ReservationsBase):
    def reserve(self, ip, username, password, **kwargs):
        self._reserve(ip, username, password, Fortigate, **kwargs)
