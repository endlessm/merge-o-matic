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

configdb = None

SOURCES_CACHE = {}

def loadConfig(data):
  global configdb
  configdb = data

def get(*args, **kwargs):
  if configdb is None and 'MOM_TEST' not in os.environ:
    MOM_CONFIG_PATH = "/etc/merge-o-matic"
    sys.path.insert(1, MOM_CONFIG_PATH)
    import momsettings
    loadConfig(momsettings)
    sys.path.remove(MOM_CONFIG_PATH)

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

class Blacklist(object):
  def __init__(self, files=[], contents=[]):
    super(Blacklist, self).__init__()
    self._list = []
    files.append('/'.join((get("ROOT"), 'blacklist.txt')))
    for filename in files:
      try:
        with open(filename, 'r') as f:
          for line in f:
            self._list.append(line.strip())
      except IOError:
        pass
    self._list += contents

  def __contains__(self, key):
    return key in self._list

  def __add__(self, other):
    ret = Blacklist(contents=self._list)
    ret._list += other._list
    return ret

class Source(object):
  """A source of reference packages from which to merge. For instance,
  a Debian derivative might have a Source representing Debian wheezy,
  and a Source representing Debian wheezy-updates.
  """

  def __init__(self, distro, dist):
    """Constructor.

    @param distro the name of a distribution, e.g. "debian", "ubuntu"
    @param dist a release codename, e.g. "wheezy", "wheezy-updates", "precise"
    """
    assert isinstance(distro, str), distro
    assert dist is None or isinstance(dist, str), dist

    super(Source, self).__init__()
    self._distro = model.Distro.get(distro)
    self._dist = dist

  @property
  def distro(self):
    """The Distro object, e.g. Distro.get("debian") or Distro.get("ubuntu")."""
    return self._distro

  @property
  def dist(self):
    """The release codename, e.g. "wheezy" or "precise"."""
    return self._dist

  def __str__(self):
    return repr(self)

  def __repr__(self):
    return "Source(%s, %s)"%(self._distro, self._dist)

  def __eq__(self, other):
    return self._distro == other._distro and self._dist == other._dist

class SourceList(object):
  """A named collection of one or more Source objects."""

  def __init__(self, name):
    """Constructor.

    @param name a source of packages: one of the keys in DISTRO_SOURCES,
      e.g. "wheezy+updates"
    """
    assert isinstance(name, str), name
    assert name in get('DISTRO_SOURCES'), name

    super(SourceList, self).__init__()
    self._name = name
    self._sources = map(lambda x:Source(x['distro'], x['dist']), get('DISTRO_SOURCES', self._name))

  @property
  def name(self):
    """The name of this object, e.g. "wheezy-updates". It can be used
    as a key in DISTRO_SOURCES.
    """
    return self._name

  def __iter__(self):
    return self._sources.__iter__()

  def __getitem__(self, i):
    return self._sources[i]

  def __str__(self):
    return repr(self)

  def __repr__(self):
    return repr(self._sources)

  def findPackage(self, name, version=None):
    for s in self._sources:
      try:
        return s.distro.findPackage(name, searchDist=s.dist, version=version)
      except model.error.PackageNotFound:
        continue
    raise model.error.PackageNotFound, name

class Target(object):
  """One of the components of a derived distribution, into which packages
  are to be merged.

  This corresponds to a (distribution, release codename, component) tuple;
  for instance, if merging Debian into Ubuntu, one of the possible
  Target objects is (ubuntu, precise, universe).
  """

  def __init__(self, name):
    """Constructor.

    @param name the short name of the target, such as precise-universe;
    a key from DISTRO_TARGETS in the configuration file
    """
    assert isinstance(name, str), name
    assert name in get('DISTRO_TARGETS'), name

    super(Target, self).__init__()
    self._name = name
    self._blacklist = None
    self._sync_upstream = None

  @property
  def blacklist(self):
    """Return a Blacklist object based on blacklist-NAME.txt."""
    if self._blacklist is None:
      files = ['/'.join((get("ROOT"), 'blacklist-%s.txt'%(self.name))),]
      self._blacklist = Blacklist(files=files)
    return self._blacklist

  def config(self, *args, **kwargs):
    """Return the configuration item given by the args, kwargs parameters.
    """
    args = (self._name,)+args
    return get('DISTRO_TARGETS', *args, **kwargs)

  @property
  def distro(self):
    """Return the Distro for our "distro" configuration item."""
    return model.Distro.get(self.config('distro'))

  @property
  def dist(self):
    """Return the release codename, such as "wheezy" or "precise"."""
    return self.config('dist')

  @property
  def component(self):
    """Return the component (archive area), such as "main", "contrib"
    or "universe".
    """
    return self.config('component')

  @property
  def sources(self):
    """Return a list of SourceList containing each Source that is merged into
    this target.
    """
    return map(SourceList, self.config('sources', default=[]))

  @property
  def unstable_sources(self):
    """Return a list of SourceList containing each Source that is merged into
    this target.
    """
    return map(SourceList, self.config('unstable_sources', default=[]))


  @property
  def sync_upstream_packages(self):
    """Return a set of package names that should be synced to the upstream
    distro without merging changes.
    """
    if self._sync_upstream is None:
      self._sync_upstream = set(self.config('sync_upstream_packages',
                                            default=[]))
    return self._sync_upstream

  def getAllSourceLists(self):
    """Return the union of self.sources and all possible results of
    self.getSourceLists.
    """
    ret = set(self.config('sources', default=[]) + self.config('unstable_sources', default=[]))

    for (p, s) in self.config('sources_per_package', default={}).iteritems():
      if isinstance(s, str):
        ret.add(s)
      else:
        ret.update(s)

    return map(SourceList, ret)

  def getSourceLists(self, packageName=None, include_unstable=True):
    """Return a list of SourceList containing each Source that is merged into
    the given package in this target. For instance, this is useful
    if you want to take most packages from Debian stable, but some
    subset of packages from backports, testing or unstable; or
    most packages from unstable, but some from experimental.
    """
    unstable = self.unstable_sources if include_unstable else []

    if packageName is None:
      return self.sources + unstable

    spp = self.config('sources_per_package', default={})
    ret = spp.get(packageName, None)

    if ret is None:
      return self.sources + unstable
    elif isinstance(ret, str):
      return [SourceList(ret)]
    else:
      return map(SourceList, ret)

  def packageHasSpecificSource(self, packageName):
    spp = self.config('sources_per_package', default={})
    return spp.get(packageName, None) is not None

  @property
  def committable(self):
    """Return True if we can commit directly to this component's
    OBS project."""
    return self.config('commit', default=False)

  @property
  def name(self):
    """Return the short name of the distribution, such as
    "precise-universe". This is a key from DISTRO_TARGETS in the
    configuration file.
    """
    return self._name

  def __str__(self):
    return repr(self)

  def __repr__(self):
    return "Target(%s)"%(self._name)

  def findSourcePackage(self, package_name, version=None):
    """Look for a source package in our source lists. Return all matches
    from all sources.
    """
    ret = []
    for srclist in self.getSourceLists(package_name):
      try:
        ret.extend(srclist.findPackage(package_name, version))
      except model.error.PackageNotFound:
        pass
    return ret

  def findNearestVersion(self, version):
    assert(isinstance(version, model.PackageVersion))
    base = version.version.base()
    sources = []
    for pkg in self.findSourcePackage(version.package.name):
      for v in pkg.package.poolDirectory().getVersions():
        pv = model.PackageVersion(pkg.package, v)
        if pv not in sources:
          sources.append(pv)

    for v in version.package.poolDirectory().getVersions():
      pv = model.PackageVersion(version.package, v)
      if pv not in sources:
        sources.append(pv)
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
    pooldir = pkg.getCurrentSources()[0]['Directory']
    name = "%s_%s.dsc" % (pkg.name, version)
    url = "%s/%s/%s" % (mirror, pooldir, name)
    ourPoolDir = pkg.poolDirectory()
    outfile = "%s/%s" % (ourPoolDir.path, name)
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
      outfile = "%s/%s" % (ourPoolDir.path, name)
      self._getFile(url, outfile, size)
    ourPoolDir.updateSources()
    return True
  
  def fetchMissingVersion(self, package, version):
    for srclist in self.getSourceLists(package.name):
      for src in srclist:
        try:
          for pkg in src.distro.findPackage(package.name, searchDist=src.dist,
                  version=version):
            if self._tryFetch(pkg.package, version):
              return
        except model.error.PackageNotFound:
          logging.debug('%s/%s not found in %r', package.name, version,
                  src)
          continue
        except IOError, e:
          logging.exception("Could not download %s_%s", package.name, version)
          continue

def targets(names=[]):
  """If names is non-empty, return a Target for each entry, or raise an
  exception.

  If names is empty, return a Target for each target configured in
  DISTRO_TARGETS.
  """
  if len(names) == 0:
    names = get('DISTRO_TARGETS').keys()
  else:
    for n in names:
      if n not in get('DISTRO_TARGETS').keys():
        raise Exception, "%s is not a target name."%(n)
  return map(Target, names)
