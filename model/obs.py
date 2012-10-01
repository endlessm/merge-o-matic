import osc.conf
osc.conf.get_config()
from osc import core as osccore
from osc import oscerr

from model.base import Distro, Package
from util import tree, shell
import os
import tempfile
import gzip
import json
import time
import urllib
from os import path
import logging
import error
import config

from deb.controlfile import ControlFile
from deb.version import Version


class OBSDistro(Distro):
  masterCache = {}
  obsLists = {}
  def __init__(self, name, parent=None):
    super(OBSDistro, self).__init__(name, parent)
    self._obsCache = {}

  @property
  def obsUser(self):
    return osc.conf.get_apiurl_usr(self.config("obs", "url"))

  def oscDirectory(self):
    return '/'.join((config.get("ROOT"), 'osc', self.name))

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
          os.unlink(oscDir+'/../'+f.name)
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

  def sync(self, dist, component, packages=[]):
    try:
      logging.debug("Attempting checkout of %s/%s", self, packages)
      self.checkout(dist, component, packages)
    except:
      pass
    logging.debug("Attempting update of %s/%s", self, packages)
    self.update(dist, component, packages)

  def updateOBSCache(self, dist, component, package=None):
    tree.ensure(os.path.expanduser("~/.mom-cache/"))
    cacheFile = os.path.expanduser("~/.mom-cache/%s"%(self.name))
    expireTime = time.time()-3600

    if self.name in OBSDistro.masterCache and len(self._obsCache) == 0:
      self._obsCache = OBSDistro.masterCache[self.name]

    if os.path.isfile(cacheFile) and os.stat(cacheFile).st_mtime > expireTime and len(self._obsCache) == 0:
      try:
        cache = json.load(open(cacheFile, 'r'))
        self._obsCache = cache['data']
        OBSDistro.masterCache[self.name] = self._obsCache
      except ValueError:
        logging.warning("Cache is corrupted. Rebuilding from scratch.")
    finished = False
    if not dist in self._obsCache:
      self._obsCache[dist] = {}
    if not component in self._obsCache[dist]:
      self._obsCache[dist][component] = {}
    if package in self._obsCache[dist][component] or (len(self._obsCache[dist][component]) > 0 and package is None):
      return

    logging.debug("Updating cache for %s/%s", self.obsProject(dist, component), package)
    unknownPackages = []
    if not self.obsProject(dist, component) in OBSDistro.obsLists:
      OBSDistro.obsLists[self.obsProject(dist, component)] = osccore.meta_get_packagelist(self.config("obs", "url"), self.obsProject(dist, component))
    obsPackageList = OBSDistro.obsLists[self.obsProject(dist, component)]
    foundPackages = map(lambda x:x['obs-name'], self._obsCache[dist][component].itervalues())
    for pkg in obsPackageList:
      if pkg not in foundPackages:
        unknownPackages.append(pkg)

    modified = False
    for obsPkg in unknownPackages:
      if package in foundPackages:
        continue
      logging.debug("Downloading metadata for %s/%s", self.obsProject(dist, component), obsPkg)
      source = None
      files = []
      filelist = []
      while True:
        try:
          filelist = osccore.meta_get_filelist(self.config("obs", "url"), self.obsProject(dist, component), obsPkg)
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
            osccore.get_source_file(self.config("obs", "url"), self.obsProject(dist, component), obsPkg, filename, targetfilename=tmpName)
            if os.stat(tmpName).st_size == 0:
              logging.warn("Couldn't download %s. Retrying.", filename)
            else:
              break
          source = ControlFile(tmpName, multi_para=False, signed=True)
          os.unlink(tmpName)
      if source is None:
        logging.error("%s/%s did not have a .dsc file.", self.obsProject(dist, component), obsPkg)
      else:
        logging.debug("%s -> %s", obsPkg, source.para["Source"])
        self._obsCache[dist][component][source.para["Source"]] = {
          "name": source.para["Source"],
          "obs-name": obsPkg,
          "files": files,
          "version": source.para['Version']
        }
        self._saveCache()

  def _saveCache(self):
    logging.debug("Flushing cache to disk")
    tree.ensure(os.path.expanduser("~/.mom-cache/"))
    cacheFile = os.path.expanduser("~/.mom-cache/%s"%(self.name))
    tmpCache = cacheFile+"~"
    fh = open(tmpCache, 'w')
    json.dump({'complete': True, 'data': self._obsCache}, fh)
    fh.close()
    os.rename(tmpCache, cacheFile)
    OBSDistro.masterCache[self.name] = self._obsCache

  def package(self, dist, component, name):
    try:
      for s in self.getSources(dist, component):
        if s['Package'] == name:
          return OBSPackage(self, dist, component, name)
      raise error.PackageNotFound(name, dist, component)
    except KeyError:
      raise error.PackageNotFound(name, dist, component)

  def obsProject(self, dist, component):
    if self.parent:
      return "%s:%s"%(self.name, self.parent.obsProject(dist, component))
    return "%s:%s:%s"%(self.name, dist, component)

  def branch(self, name):
    return OBSDistro(name, self)

  def mirrorURL(self, dist, component):
    mirror = self.config("mirror")
    url = mirror+'/'+':/'.join((self.name, dist))+':/'+component+'/'+dist
    return url

class OBSPackage(Package):
  def __init__(self, distro, dist, component, name):
    super(OBSPackage, self).__init__(distro, dist, component, name)

  @property
  def obsName(self):
    self._updateOBSCache()
    return self._obsName

  @property
  def files(self):
    self._updateOBSCache()
    return self._files

  def _updateOBSCache(self):
    self.distro.updateOBSCache(self.dist, self.component, self.name)
    self._obsName = self.distro._obsCache[self.dist][self.component][self.name]['obs-name']
    self._files = self.distro._obsCache[self.dist][self.component][self.name]['files']
  
  def obsDir(self):
    return '/'.join((self.distro.oscDirectory(), self.distro.obsProject(self.dist, self.component), self.obsName))

  def commit(self, message):
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
          logging.info('D: %s', os.path.join(pkg.dir, filename))
    pkg.commit(message)
    del self.distro._obsCache[self.dist][self.component][self.name]

  def submitMergeRequest(self, upstreamDistro, msg):
    osccore.create_submit_request(self.distro.config('obs', 'url'), self.distro.obsProject(self.dist, self.component), self.obsName, upstreamDistro, self.obsName, msg)

  def branch(self, projectBranch):
    branch = self.distro.branch(projectBranch)
    osccore.branch_pkg(self.distro.config('obs', 'url'), self.distro.obsProject(self.dist,self.component), self.obsName, target_project=branch.obsProject(self.dist, self.component), nodevelproject=False, msg='Branch for %s'%(str(self)), force=False, return_existing=True)
    if branch.obsProject(self.dist, self.component) in OBSDistro.obsLists:
      del OBSDistro.obsLists[branch.obsProject(self.dist, self.component)]
    return branch.package(self.dist, self.component, self.name)

