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
from os import path
import osc.conf
osc.conf.get_config()
from osc import core as osccore
from osc import oscerr

MOM_CONFIG_PATH = "/etc/merge-o-matic"
sys.path.insert(1, MOM_CONFIG_PATH)
import momsettings
configdb = momsettings
sys.path.remove(MOM_CONFIG_PATH)
from momlib import *

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

class Distro(object):
  @staticmethod
  def all():
    ret = []
    for k in get("DISTROS").iterkeys():
      ret.append(Distro(k))
    return ret

  def __unicode__(self):
    return self.name

  def __str__(self):
    return self.__unicode__()

  def newestSources(self, dist, component):
    sources = self.getSources(dist, component)
    newest = {}
    for source in sources:
      package = source["Package"]
      if package not in newest or Version(source["Version"]) > Version(newest[package]["Version"]):
        newest[package] = source

    return [newest[x] for x in sorted(newest.keys())]

  @staticmethod
  def get(name):
    if "obs" in get("DISTROS", name):
      return OBSDistro(name)
    return DebianDistro(name)

  def __init__(self, name, parent=None):
    super(Distro, self).__init__()
    self.parent = parent
    self.name = name

  def sourcesURL(self, dist, component):
    if (dist, component) in self.config("sources_urls", default={}):
      return self.config("sources_urls")
    mirror = self.config("mirror")
    url = mirror + "/dists"
    if dist is not None:
      url += "/" + dist
    if component is not None:
      url += "/" + component
    return url + "/source/Sources.gz"

  def updatePool(self, dist, component, package=None):
    raise NotImplementedError

  def package(self, name):
    raise NotImplementedError

  def branch(self, name):
    return Distro(name, self)

  def components(self):
    return self.config("components")

  def dists(self):
    return self.config("dists")

  def packages(self, dist, component):
    raise NotImplementedError

  def config(self, *args, **kwargs):
    args = ("DISTROS", self.name) + args
    ret = get(*args, **kwargs)
    if ret is None and not (self.parent is None):
      return self.parent.config(*(args[2:]), **kwargs)
    return ret

  def sourcesFile(self, dist, component, compressed=True):
    if compressed:
      return "%s.gz"%(self.sourcesFile(dist, component, False))
    path = '/'.join((get("ROOT"), 'dists', self.name))
    if dist is not None:
      path = "%s-%s"%(path, dist)
    if component is not None:
      path = "%s/%s" % (path, component)
    return '/'.join((path, 'source', 'Sources'))

  def getSources(self, dist, component):
    """Parse a cached Sources file."""
    global SOURCES_CACHE

    filename = self.sourcesFile(dist, component)
    if filename not in SOURCES_CACHE:
        SOURCES_CACHE[filename] = ControlFile(filename, multi_para=True,
                                              signed=False)

    return SOURCES_CACHE[filename].paras

  def updateSources(self, dist, component):
    """Update a Sources file."""
    url = self.sourcesURL(dist, component)
    filename = self.sourcesFile(dist, component)

    logging.debug("Downloading %s", url)

    try:
        if not os.path.isdir(os.path.dirname(filename)):
            os.makedirs(os.path.dirname(filename))
        urllib.URLopener().retrieve(url, filename)
    except IOError:
        logging.error("Downloading %s failed", url)
        raise

    logging.info("Saved %s", tree.subdir(ROOT, filename))
    return filename

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
        source = s
        break
    return Package(self, dist, component, name, source)

  def updatePool(self, dist, component, package=None):
    mirror = self.config("mirror")
    sources = self.getSources(dist, component)
    for source in sources:
      if package != source["Package"] and not (package is None):
        continue
      sourcedir = source["Directory"]

      pooldir = self.package(dist, component, source["Package"]).poolDirectory()

      for md5sum, size, name in files(source):
          url = "%s/%s/%s" % (mirror, sourcedir, name)
          filename = "%s/%s/%s" % (ROOT, pooldir, name)

          if os.path.isfile(filename):
              if os.path.getsize(filename) == int(size):
                  logging.debug("Skipping %s, already downloaded.", filename)
                  continue

          logging.debug("Downloading %s", url)
          ensure(filename)
          try:
              urllib.URLopener().retrieve(url, filename)
          except IOError:
              logging.error("Downloading %s failed", url)
              raise
          logging.info("Saved %s", tree.subdir(ROOT, filename))

class OBSDistro(Distro):
  def __init__(self, name, parent=None):
    super(OBSDistro, self).__init__(name, parent)
    self._obsCache = {}

  def oscDirectory(self):
    return '/'.join((get("ROOT"), 'osc', self.name))

  def branchPackage(self, packageName):
    assert(not(self.parent is None))
    exists, targetprj, targetpkg, srcprj, srcpkg = \
      osccore.branch_pkg(self.config("obs", "url"), self.parent.obsProject(dist, component), \
        packageName, target_project=self.obsProject(dist, component))

  def checkout(self, dist, component, packages=[]):
    if path.isdir('/'.join((self.oscDirectory(), '.osc'))):
      return
    osccore.Project.init_project(self.config("obs", "url"), self.oscDirectory(), self.obsProject(dist, component))
    if len(packages) == 0:
      packages = self.packages(dist, component)

    for package in packages:
      logging.info("Checking out %s", package)
      if not path.isdir('/'.join((self.oscDirectory(), package, '.osc'))):
        osccore.checkout_package(self.config("obs", "url"), self.obsProject(dist, component), package, prj_dir='/'.join((self.oscDirectory(), self.obsProject(dist, component))))
        self._validateCheckout(dist, component, package)

  def _validateCheckout(self, dist, component, package):
    oscDir = '/'.join((self.oscDirectory(), self.obsProject(dist, component), package.obsName, '.osc'))
    pkg = osccore.Package(oscDir+'/../')
    files = pkg.filelist
    while True:
      needsRebuild = False
      for f in files:
        size = os.stat(oscDir+'/'+f.name).st_size
        if size == 0:
          os.unlink(oscDir+'/'+f.name)
          os.unlink(oscDir+'../'+f.name)
          needsRebuild = True
      if needsRebuild:
        logging.warn("%s wasn't checked out properly. Attempting to rebuild.", package)
        pkg = osccore.Package(oscDir+'/../', wc_check=False)
        pkg.wc_repair(self.config('obs', 'url'))
      else:
        break

  def update(self, dist, component, packages=[]):
    if len(packages) == 0:
      packages = self.packages(dist, component)
    for package in packages:
      logging.info("Updating %s", package)
      pkgDir = '/'.join((self.oscDirectory(), self.obsProject(dist, component), package.obsName))
      if not path.isdir('/'.join((pkgDir, '.osc'))):
        osccore.checkout_package(self.config("obs", "url"), self.obsProject(dist, component), package.obsName, prj_dir='/'.join((self.oscDirectory(), self.obsProject(dist, component))))
      else:
        try:
          p = osccore.Package(pkgDir)
        except oscerr.WorkingCopyInconsistent:
          logging.warn("%s is inconsistent. Attempting to repair.", pkgDir)
          p = osccore.Package(pkgDir, wc_check=False)
          p.wc_repair(self.config("obs", "url"))
        try:
          p.update()
        except oscerr.PackageFileConflict, e:
          logging.exception("%s already exists, but OBS can't recognize it.", pkgDir)
        except KeyboardInterrupt, e:
          raise e
        except:
          logging.exception("Couldn't update %s.", package)
      self._validateCheckout(dist, component, package)

  def sync(self, dist, component):
    try:
      logging.debug("Attempting checkout of %s", self)
      self.checkout(dist, component)
    except:
      pass
    logging.debug("Attempting update of %s", self)
    self.update(dist, component)

  def updateOBSCache(self, dist, component, package=None):
    ensure(os.path.expanduser("~/.mom-cache/"))
    cacheFile = os.path.expanduser("~/.mom-cache/%s"%(self.name))
    expireTime = time.time()-3600
    if os.path.isfile(cacheFile) and os.stat(cacheFile).st_mtime > expireTime and len(self._obsCache) == 0:
      logging.debug("Reusing json cache")
      cache = json.load(open(cacheFile, 'r'))
      self._obsCache = cache['data']
    finished = False
    if not dist in self._obsCache:
      self._obsCache[dist] = {}
    if not component in self._obsCache[dist]:
      self._obsCache[dist][component] = {}
    foundPackages = map(lambda x:x['obs-name'], self._obsCache[dist][component].itervalues())
    if package in foundPackages:
      return
    logging.info("Updating cache")
    obsPackageList = osccore.meta_get_packagelist(self.config("obs", "url"), self.obsProject(dist, component))
    for package in obsPackageList:
      if package in foundPackages:
        continue          
      logging.debug("Downloading metadata for %s/%s", self.obsProject(dist, component), package)
      source = None
      files = []
      filelist = []
      while True:
        try:
          filelist = osccore.meta_get_filelist(self.config("obs", "url"), self.obsProject(dist, component), package)
          break
        except KeyboardInterrupt, e:
          raise e
        except:
          continue
      for filename in filelist:
        files.append(filename)
        if filename[-4:] == ".dsc":
          tmpHandle, tmpName = tempfile.mkstemp()
          os.close(tmpHandle)
          logging.debug("Downloading %s to %s", filename, tmpName)
          while True:
            osccore.get_source_file(self.config("obs", "url"), self.obsProject(dist, component), package, filename, targetfilename=tmpName)
            if os.stat(tmpName).st_size == 0:
              logging.warn("Couldn't download %s. Retrying.", filename)
            else:
              break
          source = ControlFile(tmpName, multi_para=False, signed=True)
          os.unlink(tmpName)
      if source is None:
        logging.error("%s/%s did not have a .dsc file.", self.obsProject(dist, component), package)
      else:
        logging.debug("%s -> %s", package, source.para["Source"])
        self._obsCache[dist][component][source.para["Source"]] = {
          "name": source.para["Source"],
          "obs-name": package,
          "files": files
        }
        self._saveCache()
    self._saveCache(True)

  def _saveCache(self, finished=False):
    ensure(os.path.expanduser("~/.mom-cache/"))
    cacheFile = os.path.expanduser("~/.mom-cache/%s"%(self.name))
    fh = open(cacheFile, 'w')
    json.dump({'complete': finished, 'data': self._obsCache}, fh)
    fh.close()
    logging.debug("Flushing cache to disk")
    

  def package(self, dist, component, name):
    self.updateOBSCache(dist, component, name)
    return OBSPackage(self, dist, component, self._obsCache[dist][component][name])

  def updatePool(self, dist, component, package=None):
    """Hardlink sources checked out from osc into pool, update Sources, and clear stale symlinks"""
    self.sync(dist, component)
    def pool_copy(package):
        pooldir = "%s/%s" % (get("ROOT"), package.poolDirectory())
        obsdir = package.obsDir()
        if not os.path.isdir(pooldir):
            os.makedirs(pooldir)
        for f in package.files:
            target = "%s/%s" % (pooldir, f)
            if os.path.lexists(target):
                os.unlink(target)
            # Hardlink instead of symlink because we want to preserve files in the pool for diffs
            # even after they are removed from obs checkouts
            logging.debug("Linking %s/%s to pool %s", obsdir, f, target)
            os.link("%s/%s" % (obsdir, f), target)

    def walker(arg, dirname, filenames):
        is_pooldir = False
        for filename in filenames:
            if filename[-4:] == ".dsc" or filename == "Sources" or filename == "Sources.gz":
                is_pooldir = True
            fullname = "%s/%s" % (dirname, filename)
            if not os.path.exists(fullname):
                logging.info("Unlinking stale %s", tree.subdir(ROOT, fullname))
                os.unlink(fullname)    
    if package is None:
      for p in self.packages(dist, component):
        pool_copy(p)
    else:
        p = self.package(dist, component, package)
        pool_copy(p)

    os.path.walk("%s/pool/%s" % (ROOT, pool_name(self.name)), walker, None)

    sources_filename = self.sourcesFile(None, None)
    logging.info("Updating %s", tree.subdir(ROOT, sources_filename))
    if not os.path.isdir(os.path.dirname(sources_filename)):
        os.makedirs(os.path.dirname(sources_filename))

    # For some reason, if we try to write directly to the gzipped stream,
    # it gets corrupted at the end
    with open(self.sourcesFile(dist, component, False), "w") as f:
        shell.run(("apt-ftparchive", "sources", "%s/pool/%s" % (ROOT, pool_name(self.name))), chdir=ROOT, stdout=f)
    with open(self.sourcesFile(dist, component)) as f:
        with gzip.open(sources_filename, "wb") as gzf:
            gzf.write(f.read())

  def obsProject(self, dist, component):
    if self.parent:
      return "%s:%s"%(self.name, self.parent.obsProject(dist, component))
    return "%s:%s:%s"%(self.name, dist, component)

  def branch(self, name):
    return OBSDistro(name, self)

  def packages(self, dist, component):
    self.updateOBSCache(dist, component)
    return map(lambda x:self.package(dist, component, x), self._obsCache[dist][component].iterkeys())

  def sourcesURL(self, dist, component):
    mirror = self.config("mirror")
    url = mirror+':/'.join((self.name, dist))+':/'+component+'/'+dist+'/dists/'+dist+'/'+component+'/source/Sources.gz'
    return url

class Package(object):
  def __init__(self, distro, dist, component, name, source):
    super(Package, self).__init__()
    self.distro = distro
    self.name = name
    self.dist = dist
    self.component = component
    self.files = []
    self.source = source

  def __unicode__(self):
    return '/'.join((str(self.distro), self.dist, self.component, self.name))

  def __str__(self):
    return self.__unicode__()

  def poolDirectory(self):
    return "pool/%s/%s/%s" % (pool_name(self.distro.name), pathhash(self.name), self.name)

  def commitMerge(self):
    pass

  def version(self):
    return Version(self.source["Version"])

  def sourcesFile(self):
    return '%s/%s/Sources'%(get('ROOT'), self.poolDirectory())

  def getSources(self):
    filename = self.sourcesFile()
    sources = ControlFile(filename, multi_para=True, signed=False)
    return sources.paras

  @staticmethod
  def merge(ours, upstream, base, output_dir, force=False):
    mergedVersion = Version(upstream.version()+"co1")
    base_version = Version(re.sub("build[0-9]+$", "", base.version()))
    left_version = Version(re.sub("build[0-9]+$", "", ours.version()))
    right_version = Version(re.sub("build[0-9]+$", "", upstream.version()))
    if base_version >= left_version:
      cleanup(output_dir)
      if left_version < right_version:
        ensure("%s/%s" % (output_dir, "REPORT"))


class OBSPackage(Package):
  def __init__(self, distro, dist, component, data):
    self.files = osccore.meta_get_filelist(distro.config('obs', 'url'), distro.obsProject(dist, component), str(data['obs-name']))
    for filename in self.files:
      if filename[-4:] == ".dsc":
        tmpHandle, tmpName = tempfile.mkstemp()
        os.close(tmpHandle)
        logging.debug("Downloading %s to %s", filename, tmpName)
        while True:
          osccore.get_source_file(distro.config("obs", "url"), distro.obsProject(dist, component), str(data['obs-name']), filename, targetfilename=tmpName)
          if os.stat(tmpName).st_size == 0:
            logging.warn("Couldn't download %s. Retrying.", filename)
          else:
            break
        source = ControlFile(tmpName, multi_para=False, signed=True)
        os.unlink(tmpName)

    super(OBSPackage, self).__init__(distro, dist, component, data['name'], source)
    self.name = data['name']
    self.obsName = str(data['obs-name'])
  
  def obsDir(self):
    return '/'.join((self.distro.oscDirectory(), self.distro.obsProject(self.dist, self.component), self.obsName))

  def commit(self):
    pkg = osccore.Package(self.obsDir())
    pkg.todo = list(set(pkg.filenamelist + pkg.filenamelist_unvers + pkg.to_be_added))
    for filename in pkg.todo:
      if os.path.isdir(filename):
          continue
      # ignore foo.rXX, foo.mine for files which are in 'C' state
      if os.path.splitext(filename)[0] in pkg.in_conflict:
          continue
      state = pkg.status(filename)
      if state == '?':
          # TODO: should ignore typical backup files suffix ~ or .orig
          pkg.addfile(filename)
      elif state == '!':
          pkg.delete_file(filename)
          logging.info('D: %s', getTransActPath(os.path.join(pkg.dir, filename)))

  def submitMergeRequest(self, upstreamDistro, msg):
    osccore.create_submit_request(self.distro.config('obs', 'url'), self.distro.obsProject(self.dist, self.component), self.obsName, upstreamDistro, self.obsName, msg)

  def branch(self, projectBranch):
    branch = self.distro.branch(projectBranch)
    osccore.branch_pkg(self.distro.config('obs', 'url'), self.distro.obsProject(self.dist,self.component), self.obsName, target_project=branch.obsProject(self.dist, self.component), nodevelproject=False, msg='Branch for %s'%(str(self)), force=False, return_existing=True)
    branch.updatePool(self.dist, self.component)
    branch.updateSources(self.dist, self.component)
    return branch.package(self.dist, self.component, self.name)
