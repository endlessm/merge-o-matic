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
import tempfile
import json
import time
import urllib
import model
import re
import model.error
from deb.version import Version
from os import path
import os
from deb.source import ControlFile
from util import files, tree

MOM_CONFIG_PATH = "/etc/merge-o-matic"
sys.path.insert(1, MOM_CONFIG_PATH)
import momsettings
configdb = momsettings
sys.path.remove(MOM_CONFIG_PATH)

SOURCES_CACHE = {}

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

class Source(object):
  def __init__(self, distro, dist):
    super(Source, self).__init__()
    self._distro = model.Distro.get(distro)
    self._dist = dist

  @property
  def distro(self):
    return self._distro

  @property
  def dist(self):
    return self._dist

  def __str__(self):
    return repr(self)

  def __repr__(self):
    return "Source(%s, %s)"%(self._distro, self._dist)

  def __eq__(self, other):
    return self._distro == other._distro and self._dist == other._dist

class SourceList(object):
  def __init__(self, name):
    super(SourceList, self).__init__()
    self._name = name
    self._sources = map(lambda x:Source(x['distro'], x['dist']), get('DISTRO_SOURCES', self._name))

  @property
  def name(self):
    return self._name

  def __iter__(self):
    return self._sources.__iter__()

  def __getitem__(self, i):
    return self._sources[i]

  def __str__(self):
    return repr(self)

  def __repr__(self):
    return repr(self._sources)

  def findPackage(self, name):
    for s in self._sources:
      try:
        return s.distro.findPackage(name, searchDist=s.dist)
      except model.error.PackageNotFound:
        continue
    raise model.error.PackageNotFound, name

class Target(object):
  def __init__(self, name):
    super(Target, self).__init__()
    self._name = name

  def config(self, *args, **kwargs):
    args = (self._name,)+args
    return get('DISTRO_TARGETS', *args, **kwargs)

  @property
  def distro(self):
    return model.Distro.get(self.config('distro'))

  @property
  def dist(self):
    return self.config('dist')

  @property
  def component(self):
    return self.config('component')

  @property
  def sources(self):
    return map(SourceList, self.config('sources', default=[]))

  @property
  def committable(self):
    return self.config('commit', default=False)

  @property
  def name(self):
    return self._name

  def __str__(self):
    return repr(self)

  def __repr__(self):
    return "Target(%s)"%(self._name)

  def findNearestVersion(self, version):
    assert(isinstance(version, model.PackageVersion))
    base = version.version.base()
    sources = []
    for srclist in self.sources:
      for src in srclist:
        try:
          for pkg in  src.distro.findPackage(version.package.name,
              searchDist=src.dist):
            for v in pkg.package.versions():
              if v not in sources:
                sources.append(v)
        except model.error.PackageNotFound:
          pass
    for v in version.package.versions():
      if v not in sources:
        sources.append(v)
    bases = []
    for source in sources:
      if base == source.version:
        return source
      elif base <= Version(re.sub("build[0-9]+$", "", str(source.version))) and source not in bases:
        bases.append(source)
    bases.append(version)
    bases.sort()
    return bases[0]

  def _getFile(self, url, filename, size=None):
    if os.path.isfile(filename):
        if size is None or os.path.getsize(filename) == int(size):
            return

    logging.debug("Downloading %s", url)
    tree.ensure(filename)
    try:
        urllib.URLopener().retrieve(url, filename)
    except IOError as e:
        logging.error("Downloading %s failed: %s", url, e.args)
        raise
    logging.info("Saved %s", filename)

  def _tryFetch(self, pkg, version):
    mirror = pkg.distro.mirrorURL(pkg.dist, pkg.component)
    pooldir = pkg.getPoolSources()[0]['Directory']
    name = "%s_%s.dsc" % (pkg.name, version)
    url = "%s/%s/%s" % (mirror, pooldir, name)
    outfile = "%s/%s" % (pkg.poolDirectory(), name)
    logging.debug("Downloading %s to %s", url, outfile)
    try:
      self._getFile(url, outfile)
    except IOError:
      logging.debug("Could not download %s.", url)
      return False
    source = ControlFile()
    try:
      source.open(outfile, signed=True, multi_para=True)
    except:
      pass
    for md5sum, size, name in files(source.paras[0]):
      url = "%s/%s/%s" % (mirror, pooldir, name)
      outfile = "%s/%s" % (pkg.poolDirectory(), name)
      self._getFile(url, outfile, size)
    return True
  
  def fetchMissingVersion(self, package, version):
    for srclist in self.sources:
      for src in srclist:
        try:
          for pkg in src.distro.findPackage(package.name):
            if self._tryFetch(pkg.package, version):
              pkg.package.updatePoolSource()
              return
        except IOError, e:
          logging.exception("Could not download %s_%s", pkg, version)
          continue

def targets(names=[]):
  if len(names) == 0:
    names = get('DISTRO_TARGETS').keys()
  return map(Target, names)
