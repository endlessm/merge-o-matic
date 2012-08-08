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

  def packages(self, dist, component):
    sources = self.getSources(dist, component)
    return map(lambda x:self.package(dist, component, x["Package"]), sources)

  def package(self, dist, component, name):
    source = None
    for s in self.getSources(dist, component):
      if s['Package'] == name:
        return Package(self, dist, component, name, Version(s['Version']))
    raise error.PackageNotFound(dist, component, name)

