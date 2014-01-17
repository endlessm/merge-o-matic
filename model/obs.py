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

logger = logging.getLogger('model.obs')

class OBSDistro(Distro):
  """A distro with OBS integration."""

  def __repr__(self):
    return '<%s "%s" ("%s")>' % (self.__class__.__name__, self.name,
            self.obsProject('*', '*'))

  def __init__(self, name, parent=None):
    super(OBSDistro, self).__init__(name, parent)

  @property
  def obsUser(self):
    """Return the username with which to log in to the OBS instance.

    The merge-o-matic administrator is currently expected to set this up
    by running something like 'sudo -H -u mom -- osc -A ${url} ls'
    and entering the username and password interactively.
    """
    return osc.conf.get_apiurl_usr(self.config("obs", "url"))

  def oscDirectory(self):
    """Return the absolute path to the working area used to check out
    packages in this distro.
    """
    return '/'.join((config.get("ROOT"), 'osc', self.name))

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
        logger.warn("%s wasn't checked out properly. Attempting to rebuild.", package)
        pkg = osccore.Package(oscDir+'/../', wc_check=False)
        pkg.wc_repair(self.config('obs', 'url'))
      else:
        break

  def sync(self, dist, component, packages=[]):
    """
    Check out and/or update each package into osc/PROJECT/NAME.

    @param dist a release codename like "precise"
    @param component a component (archive area) like "universe"
    @param packages a list of OBSPackage, or the empty list to act on
    all known packages
    """
    if len(packages) == 0:
      packages = self.packages(dist, component)
    for package in packages:
      logger.info("Checking out/updating %s", package)
      apiurl = self.config("obs", "url")
      project = self.obsProject(dist, component)
      prjDir = '/'.join((self.oscDirectory(), project))
      pkgDir = '/'.join((prjDir, package.obsName))

      if path.isdir(pkgDir + '/.osc'):
        logger.debug("updating %s in %s (.osc found)", package, pkgDir)
        try:
          p = osccore.Package(pkgDir)
        except oscerr.WorkingCopyInconsistent:
          logger.warn("%s is inconsistent. Attempting to repair.", pkgDir)
          p = osccore.Package(pkgDir, wc_check=False)
          p.wc_repair(apiurl)

        try:
          p.update()
        except KeyboardInterrupt, e:
          raise e
        except:
          logger.warning("Couldn't update %s.", package, exc_info=True)
          logger.info('Deleting %s and starting again...', pkgDir)
          tree.rmtree(pkgDir)
        else:
          # no exception from update() => no need to redo the checkout
          continue
      else:
        logger.debug("checking out %s into %s (.osc not found)", package, pkgDir)

      # If .../.osc didn't exist, or if it existed but we decided it wasn't
      # recoverable, check the package out
      osccore.checkout_package(apiurl, project, package.obsName, prj_dir=prjDir)

      # Perform a sanity check
      self._validateCheckout(dist, component, package)

  def package(self, dist, component, name):
    try:
      for s in self.getSources(dist, component):
        if s['Package'] == name:
          return OBSPackage(self, dist, component, name)
      raise error.PackageNotFound(name, dist, component)
    except KeyError:
      raise error.PackageNotFound(name, dist, component)

  def getPackageFiles(self, dist, component, obsPkg):
    return osccore.meta_get_filelist(self.config("obs", "url"),
        self.obsProject(dist, component), obsPkg)

  def obsProject(self, dist, component):
    """
    Return the OBS project for the given release and component
    in the form "prefix:release:component", e.g. "debian:wheezy:main"
    or "home:myuser:branches:ubuntu:precise:universe".

    The prefix defaults to self.name, but can be overridden via
    DISTROS[self.name]["obs"]["project"].

    @param dist a release codename like "precise"
    @param component a component (archive area) like "universe"
    """
    if self.parent:
      return "%s:%s"%(self.name, self.parent.obsProject(dist, component))
    return "%s:%s:%s" % (self.config("obs", "project", default=self.name),
            dist, component)

  def branch(self, name):
    """Return a new OBSDistro that is a branch of this one.

    @param name a prefix like home:myuser:branches, which will be prepended to
    this OBSDistro's name
    """
    return OBSDistro(name, self)

  def mirrorURL(self, dist, component):
    mirror = self.config("mirror")
    return mirror

class OBSPackage(Package):
  def __init__(self, distro, dist, component, name):
    super(OBSPackage, self).__init__(distro, dist, component, name)

  @property
  def obsName(self):
    """Return the name of this package in OBS. This is currently assumed
    to be the same as its Debian package name.
    """
    # self.name sometimes ends up as a unicode object, which confuses urllib2
    return str(self.name)

  def getOBSFiles(self):
    """Return the filenames of this package's .dsc file and
    related source files in OBS.
    """
    return self.distro.getPackageFiles(self.dist, self.component, self.obsName)

  def obsDir(self):
    """Return the directory into which this package will be checked out."""
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
          logger.info('D: %s', os.path.join(pkg.dir, filename))
    pkg.commit(message)

  def submitMergeRequest(self, upstreamDistro, msg):
    reqs = osccore.get_request_list(self.distro.config('obs', 'url'),
        self.distro.obsProject(self.dist, self.component), self.obsName,
        req_type='submit', req_state=['new', 'review'])
    user = self.distro.obsUser
    oldreqs = [ i for i in reqs if i.state.who == user ]
    result = osccore.create_submit_request(self.distro.config('obs', 'url'), self.distro.obsProject(self.dist, self.component), self.obsName, upstreamDistro, self.obsName, msg)
    for req in oldreqs:
      osccore.change_request_state(self.distro.config('obs', 'url'), req.reqid,
          'superseded', 'superseded by %s' % result, result)
    return result

  def webMergeRequest(self, reqid):
    url = self.distro.config('obs', 'web')

    if url is None:
      url = self.distro.config('obs', 'url')

    return '%s/request/show/%s' % (url, reqid)

  def branch(self, projectBranch):
    branch = self.distro.branch(projectBranch)
    logger.info('Branching %r/%s as %r/%s', self.distro, self.name,
        branch, self.name)

    obsURL = self.distro.config('obs', 'url')
    obsProject = self.distro.obsProject(self.dist,self.component)
    targetProject = branch.obsProject(self.dist, self.component)

    logger.debug('- OBS URL: %r', obsURL)
    logger.debug('- Source OBS project: %r', obsProject)
    logger.debug('- Source OBS package: %r', self.obsName)
    logger.debug('- Target OBS project: %r', targetProject)
    logger.debug('- Message: %r', 'Branch for %s' % (str(self)))

    result = osccore.branch_pkg(obsURL, obsProject, self.obsName,
      target_project=targetProject, nodevelproject=False,
      msg='Branch for %s'%(str(self)), force=False, return_existing=True)

    if result[0]:
      logger.debug('Branched package already exists')
    else:
      logger.debug('Branched package was created')

    if (result[1] != targetProject or
        result[2] != self.obsName or
        result[3] not in (None, obsProject) or
        result[4] not in (None, self.obsName)):
      logger.warning("Unexpected result from branch_pkg:")
      logger.warning("- expected source project: %r or None", obsProject)
      logger.warning("- result's source project: %r", result[3])
      logger.warning("- expected source package: %r or None", self.obsName)
      logger.warning("- result's source package: %r", result[4])
      logger.warning("- expected target project: %r", targetProject)
      logger.warning("- result's target project: %r", result[1])
      logger.warning("- expected target package: %r", self.obsName)
      logger.warning("- result's target package: %r", result[2])

    return branch.package(self.dist, self.component, self.name)

