from model.base import Distro, Package
from util import tree
import logging
import os
from os import path
import urllib
import error
from deb.version import Version
import config

class DebianDistro(Distro):
  """An ordinary Debian derivative, with no OBS integration."""

  def __init__(self, name, parent=None):
    super(DebianDistro, self).__init__(name, parent)


