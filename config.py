#!/usr/bin/env python
# -*- coding: utf-8 -*-
# config.py - configuration API
#
# Copyright © 2012 Collabora
# Author: Trever Fischer <tdfischer@fedoraproject.org>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of version 3 of the GNU General Public License as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import sys
import logging
from os import path
import osc.conf
osc.conf.get_config()
from osc import core as osc

MOM_CONFIG_PATH = "/etc/merge-o-matic"
sys.path.insert(1, MOM_CONFIG_PATH)
import momsettings
configdb = momsettings
sys.path.remove(MOM_CONFIG_PATH)

def loadConfig(data):
  global configdb
  configdb = data

def get(*args, **kwargs):
  def _get(item, *args, **kwargs):
    global configdb
    if len(args) == 0:
      return item
    if hasattr(item, args[0]):
      return _get(getattr(item, args[0]), *(args[1:]), **kwargs)
    if hasattr(item, "__iter__"):
      if args[0] in item:
        return _get(item[args[0]], *(args[1:]), **kwargs)
    return kwargs.setdefault("default", None)
  return _get(configdb, *args, **kwargs)

class Distro(object):
  @staticmethod
  def all():
    ret = []
    for k in get("DISTROS").iterkeys():
      ret.append(Distro(k))
    return ret

  def __init__(self, name, parent=None):
    self.parent = parent
    self.name = name

  def config(self, *args, **kwargs):
    args = ("DISTROS", self.name) + args
    ret = get(*args, **kwargs)
    if ret is None and not (self.parent is None):
      return self.parent.config(*(args[2:]), **kwargs)
    return ret

  def oscDirectory(self):
    return '/'.join((get("ROOT"), 'osc', self.name))

  def osc(self):
    return OSCProject(self)

  def obsProject(self):
    if self.parent:
      return "%s:%s"%(self.name, self.parent.obsProject())
    return self.config("obs", "project", default=self.name)

  def branch(self, name):
    return Distro(name, self)

class OSCProject(object):
  def __init__(self, distro):
    self.distro = distro

  def packages(self):
    return osc.meta_get_packagelist(self.distro.config("obs", "url"), self.distro.obsProject())

  def branchPackage(self, packageName):
    assert(not(self.distro.parent is None))
    exists, targetprj, targetpkg, srcprj, srcpkg = \
      osc.branch_pkg(self.distro.config("obs", "url"), self.distro.parent.obsProject(), \
        packageName, target_project=self.distro.obsProject())

  def checkout(self, packages=[]):
    if path.isdir('/'.join((self.distro.oscDirectory(), '.osc'))):
      return
    osc.Project.init_project(self.distro.config("obs", "url"), self.distro.oscDirectory(), self.distro.obsProject())
    if len(packages) == 0:
      packages = self.packages()

    for package in packages:
      logging.info("Checking out %s", package)
      if not path.isdir('/'.join((self.distro.oscDirectory(), package, '.osc'))):
        osc.checkout_package(self.distro.config("obs", "url"), self.distro.obsProject(), package, prj_dir='/'.join((self.distro.oscDirectory(), self.distro.obsProject())))

  def update(self, packages=[]):
    if len(packages) == 0:
      packages = self.packages()
    for package in packages:
      logging.info("Updating %s", package)
      pkgDir = '/'.join((self.distro.oscDirectory(), self.distro.obsProject(), package))
      if not path.isdir('/'.join((pkgDir, '.osc'))):
        osc.checkout_package(self.distro.config("obs", "url"), self.distro.obsProject(), package, prj_dir='/'.join((self.distro.oscDirectory(), self.distro.obsProject())))
      else:
        p = osc.Package(pkgDir)
        p.update()

  def sync(self):
    try:
      self.checkout()
    except:
      self.update()
