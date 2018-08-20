from model.base import Distro


class DebianDistro(Distro):
    """An ordinary Debian derivative, with no OBS integration."""

    def __init__(self, name, parent=None):
        super(DebianDistro, self).__init__(name, parent)
