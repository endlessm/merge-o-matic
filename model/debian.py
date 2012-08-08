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
  def __init__(self, name, parent=None):
    super(DebianDistro, self).__init__(name, parent)


