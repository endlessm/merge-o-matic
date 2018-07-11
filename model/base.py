import config
from glob import glob
from util import tree, pathhash, shell
import os
from os import path
import logging
import urllib
from deb.controlfile import ControlFile
from deb.version import Version
import gzip

import error

logger = logging.getLogger('model.base')

class Distro(object):
  """Base class for distributions corresponding to the keys of DISTROS,
  such as "debian" or "ubuntu", and for temporary distribution branches.
  """
  SOURCES_CACHE = {}

  @staticmethod
  def all():
    """Return a list of Distro objects representing distributions.
    These correspond to the keys of DISTROS in the configuration file."""
    ret = []
    for k in config.get("DISTROS").iterkeys():
      ret.append(Distro.get(k))
    return ret

  def __unicode__(self):
    return self.name

  def __eq__(self, other):
    return self.name == other.name

  def __str__(self):
    return self.__unicode__()

  def __repr__(self):
    return '<%s "%s">' % (self.__class__.__name__, self.name)

  def newestPackageVersions(self, dist, component):
    sources = self.getSources(dist, component)
    newest = {}
    for source in sources:
      package = source["Package"]
      version = Version(source['Version'])
      if package not in newest or version > newest[package]:
        newest[package] = version

    ret = []
    for name in sorted(newest.keys()):
      pkg = Package(self, dist, component, name)
      ret.append(PackageVersion(pkg, newest[name]))

    return ret

  @staticmethod
  def get(name):
    """Return the Distro with the given name, e.g. "debian",
    which should be one of the keys of DISTROS.
    """
    if "obs" in config.get("DISTROS", name):
      return model.obs.OBSDistro(name)
    return model.debian.DebianDistro(name)

  def __init__(self, name, parent=None):
    """Constructor.

    @param name the distro's name, e.g. "debian" for a distribution listed
    in DISTROS, or "home:myuser:branches" for a branch
    @param parent the Distro from which this was branched, or None if it
    is listed in DISTROS
    """
    super(Distro, self).__init__()
    self.parent = parent
    self.name = name

  def sourcesURL(self, dist, component):
    """Return the absolute URL to Sources.gz for the given release
    and component in this distribution. If it is not configured
    specially in sources_urls, the mirror is assumed to follow the
    standard apt layout (MIRROR/dists/RELEASE/COMPONENT/source/Sources.gz).
    """
    if (dist, component) in self.config("sources_urls", default={}):
      return self.config("sources_urls")[(dist, component)]
    mirror = self.mirrorURL(dist, component)
    url = mirror + "/dists"
    if dist is not None:
      url += "/" + dist
    if component is not None:
      url += "/" + component
    return url + "/source/Sources.gz"

  def mirrorURL(self, dist, component):
    """Return the absolute URL of the top of the mirror for the given
    release and component in this distribution.
    """
    return self.config("mirror")

  def updatePool(self, dist, component, package=None):
    """Populate the 'pool' directory by downloading Debian source packages
    from the given release and component.

    :param str dist: a release codename such as "wheezy" or "precise"
    :param str component: a component (archive area) such as "main" or "contrib"
    :param package: a source package name, or None to download all of them
    :type package: str or None
    :return: True if anything actually changed, False otherwise
    :rtype: bool
    """
    if package is None:
      logger.debug('Downloading all packages from %s/%s/%s into %s pool',
          self, dist, component, self)
    else:
      logger.debug('Downloading package "%s" from %s/%s/%s into %s pool',
          package, self, dist, component, self)

    mirror = self.mirrorURL(dist, component)
    sources = self.getSources(dist, component)

    changed = False

    for source in sources:
      if package != source["Package"] and not (package is None):
        continue
      sourcedir = source["Directory"]

      pkg = self.package(dist, component, source['Package'])
      for md5sum, size, name in files(source):
          url = "%s/%s/%s" % (mirror, sourcedir, name)
          filename = "%s/%s" % (pkg.poolPath, name)

          if os.path.isfile(filename):
              if os.path.getsize(filename) == int(size):
                  logger.debug("Skipping %s, already downloaded.", filename)
                  continue

          logger.debug("Downloading %s", url)
          changed = True
          tree.ensure(filename)
          try:
              urllib.URLopener().retrieve(url, filename)
          except IOError:
              logger.error("Downloading %s failed", url)
              raise
          logger.debug("Saved %s", tree.subdir(config.get('ROOT'), filename))

    return changed

  def findPackage(self, name, searchDist=None, searchComponent=None, version=None):
    """Return a list of the available versions of the given package
    as PackageVersion objects. Raise PackageNotFound if there are no
    such versions.

    The returned versions are in no particular order.

    @param name the name of a source package
    @param searchDist if not None, only search in this release codename,
    such as "precise"
    @param searchComponent if not None, only search in this component
    (archive area), such as "universe"
    @version if not None, only consider versions matching this Version
    """
    if searchDist is None:
      dists = self.dists()
    else:
      dists = [searchDist,]
    if searchComponent is None:
      components = self.components()
    else:
      components = [searchComponent,]
    ret = []
    for dist in dists:
      for component in components:
        try:
          pkg = self.package(dist, component, name)
        except error.PackageNotFound:
          continue
        for v in pkg.currentVersions():
          if version and v.version != version:
            continue
          ret.append(v)
    if len(ret) == 0:
      raise error.PackageNotFound(name, searchDist, searchComponent)
    return ret

  def package(self, dist, component, name):
    """Return a Package for the given (release, component, source package)
    tuple, or raise PackageNotFound.

    @param dist a release codename like "precise"
    @param component a component (archive area) like "universe"
    @param name the name of a source package
    """
    source = None
    for s in self.getSources(dist, component):
      if s['Package'] == name:
        return Package(self, dist, component, name)
    raise error.PackageNotFound(name, dist, component)

  def branch(self, name):
    """Return a Distro with self as its parent."""
    return Distro(name, self)

  def components(self):
    """Return a list of components (archive areas) in each of this
    distro's releases, e.g. ["main", "contrib", "non-free"] for Debian
    or ["main", "restricted", "universe", "multiverse"] for Ubuntu.
    """
    return self.config("components")

  def dists(self):
    """Return a list of release codenames in this distro, e.g.
    ["wheezy", "jessie", "unstable"].
    """
    return self.config("dists")

  def packages(self, dist, component):
    """Return a Package for each source package in (dist, component).

    @param dist a release codename like "precise", or None if this
    distro does not have release subdirectories
    @param component a component (archive area) like "universe", or None if
    this distro does not have release subdirectories
    """
    sources = self.getSources(dist, component)
    ret = map(lambda x:self.package(dist, component, x["Package"]), sources)
    # Multiple versions of a package could exist in the sources.
    # De-duplicate the returned list.
    return list(set(ret))

  def config(self, *args, **kwargs):
    args = ("DISTROS", self.name) + args
    ret = config.get(*args, **kwargs)
    if ret is None and not (self.parent is None):
      return self.parent.config(*(args[2:]), **kwargs)
    return ret

  def sourcesFile(self, dist, component, compressed=True):
    """Return the absolute filename of the cached Sources file.

    @param dist a release codename like "precise", or None if this
    distro does not have release subdirectories
    @param component a component (archive area) like "universe", or None if
    this distro does not have release subdirectories
    @param compressed if True, return the path to Sources.gz
    """
    if self.parent:
      return self.parent.sourcesFile(dist, component, compressed)
    if compressed:
      return "%s.gz"%(self.sourcesFile(dist, component, False))
    path = '/'.join((config.get("ROOT"), 'dists', self.name))
    if dist is not None:
      path = "%s-%s"%(path, dist)
    if component is not None:
      path = "%s/%s" % (path, component)
    return '/'.join((path, 'source', 'Sources'))

  def getSources(self, dist, component):
    """Parse a cached Sources file. Return its stanzas, each representing
    a source package, as dictionaries of the form { "Field": "value" }.
    """

    filename = self.sourcesFile(dist, component)
    if filename not in Distro.SOURCES_CACHE:
        Distro.SOURCES_CACHE[filename] = ControlFile(filename, multi_para=True,
                                              signed=False)

    return Distro.SOURCES_CACHE[filename].paras

  def updateSources(self, dist, component):
    """Update a Sources file."""
    url = self.sourcesURL(dist, component)
    filename = self.sourcesFile(dist, component)

    logger.debug("Downloading %s", url)

    try:
        if not os.path.isdir(os.path.dirname(filename)):
            os.makedirs(os.path.dirname(filename))
        urllib.URLopener().retrieve(url, filename)
    except IOError:
        logger.error("Downloading %s failed", url)
        raise

    logger.debug("Saved %s", tree.subdir(config.get('ROOT'), filename))
    with gzip.open(self.sourcesFile(dist, component)) as gzf:
        with open(self.sourcesFile(dist, component, False), "wb") as f:
            f.write(gzf.read())

  def getPoolPath(self, component):
    """Return the absolute path to the pool for a given component
    source packages for the given component.
    """
    return "%s/pool/%s/%s" % (config.get('ROOT'), self.config('pool', default=self.name), component)

  def shouldExpire(self):
    return self.config('expire', default=False)

class Package(object):
  """A Debian source package in a distribution."""

  def __init__(self, distro, dist, component, name):
    """Constructor.

    @param distro a Distro
    @param dist a release codename like "precise", or None if this
    distro does not have release subdirectories
    @param component a component (archive area) like "universe", or None if
    this distro does not have release subdirectories
    @param name the name of the source package
    """
    super(Package, self).__init__()
    assert(isinstance(distro, Distro))
    self.distro = distro
    self.name = name
    self.dist = dist
    self.component = component

  def __eq__(self, other):
    return self.distro == other.distro and self.name == other.name and self.dist == other.dist and self.component == other.component

  def __unicode__(self):
    return '/'.join((str(self.distro), self.dist, self.component, self.name))

  def __str__(self):
    return self.__unicode__()

  def __repr__(self):
    return self.__unicode__()

  @property
  def poolPath(self):
    """Return something like 'pool/debian/main/libf/libfoo'"""
    return "%s/%s/%s" % (self.distro.getPoolPath(self.component),
        pathhash(self.name), self.name)

  def commitMerge(self):
    pass

  def getCurrentSources(self):
    """Return a list of Sources stanzas (dictionaries of the form
    { "Field": "value" }) describing versions of this package
    available in (self.distro, self.dist, self.component), with
    the oldest version first.
    """
    sources = self.distro.getSources(self.dist, self.component)
    matches = []
    for source in sources:
      if source['Package'] == self.name:
        matches.append(source)
    matches.sort(key=lambda x:Version(x['Version']))
    return matches

  @staticmethod
  def merge(ours, upstream, base, output_dir, force=False):
    """Merge PackageVersion instances @ours (left) and @upstream (right) using
    the common ancestor PackageVersion @base, placing the result in
    @output_dir.
    """
    mergedVersion = Version(upstream.version()+"co1")
    base_version = Version(re.sub("build[0-9]+$", "", base.version()))
    left_version = Version(re.sub("build[0-9]+$", "", ours.version()))
    right_version = Version(re.sub("build[0-9]+$", "", upstream.version()))
    if base_version >= left_version:
      cleanup(output_dir)
      if left_version < right_version:
        tree.ensure("%s/%s" % (output_dir, "REPORT"))

  def updatePool(self):
    """Download all available versions of this package from
    (self.distro, self.dist, self.component) into the pool.

    :return: True if the pool changed
    :rtype: bool
    """
    return self.distro.updatePool(self.dist, self.component, self.name)

  def getPoolVersions(self):
    """Return all available versions of this package in the pool as
    PackageVersion objects. They are in no particular order.
    """
    versions = []
    for f in glob(self.poolPath + '/*.dsc'):
      dsc = ControlFile(f, multi_para=False, signed=True).para
      versions.append(PackageVersion(self, Version(dsc['Version'])))
    return versions

  def currentVersions(self):
    """Return all available versions of this package in self.distro.
    They are in no particular order.
    """
    versions = []
    for s in self.distro.getSources(self.dist, self.component):
      if s['Package'] == self.name:
        versions.append(PackageVersion(self, Version(s['Version'])))
    return versions

  def newestVersion(self):
    """Return the newest version of this package in self.distro.
    """
    versions = self.currentVersions()
    newest = versions[0]
    for v in versions:
      if v > newest:
        newest = v
    return newest

class PackageVersion(object):
  """A pair (Package, Version)."""

  def __init__(self, package, version):
    self.package = package
    self.version = version

  def __eq__(self, other):
    return self.package == other.package and self.version == other.version

  def __cmp__(self, other):
    return self.version.__cmp__(other.version)

  def __str__(self):
    return self.__unicode__()

  def __repr__(self):
    return self.__unicode__()

  def __unicode__(self):
    return "%s-%s"%(self.package, self.version)

  @property
  def dscFilename(self):
      return "%s_%s.dsc" % (self.package.name, self.version.without_epoch)

  @property
  def dscPath(self):
      """Return path to the .dsc file in the pool"""
      return self.package.poolPath + '/' + self.dscFilename

  def getDscContents(self):
      return ControlFile(self.dscPath, multi_para=False, signed=True).para

def files(source):
    """Return (md5sum, size, name) for each file.

    @param source a stanza from Sources, as a dictionary in the form
    {"Field": "value"}
    """
    files = source["Files"].strip("\n").split("\n")
    return [ f.split(None, 2) for f in files ]

import model.debian
import model.obs
