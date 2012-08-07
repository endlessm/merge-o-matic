import config
from util import tree
import os
from os import path
import logging
import urllib

class Distro(object):
  @staticmethod
  def all():
    ret = []
    for k in config.get("DISTROS").iterkeys():
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
    if "obs" in config.get("DISTROS", name):
      return model.obs.OBSDistro(name)
    return model.debian.DebianDistro(name)

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
    ret = config.get(*args, **kwargs)
    if ret is None and not (self.parent is None):
      return self.parent.config(*(args[2:]), **kwargs)
    return ret

  def sourcesFile(self, dist, component, compressed=True):
    if compressed:
      return "%s.gz"%(self.sourcesFile(dist, component, False))
    path = '/'.join((config.get("ROOT"), 'dists', self.name))
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
    with gzip.open(self.sourcesFile(dist, component)) as gzf:
        with open(self.sourcesFile(dist, component, False), "wb") as f:
            f.write(gzf.read())

  def poolName(self, component):
    return "%s/%s"%(self.config('pool', default=self.name), component)

class Package(object):
  def __init__(self, distro, dist, component, name, version):
    super(Package, self).__init__()
    self.distro = distro
    self.name = name
    self.dist = dist
    self.component = component
    self.files = []
    self.version = version

  def __unicode__(self):
    return '/'.join((str(self.distro), self.dist, self.component, self.name))

  def __str__(self):
    return self.__unicode__()

  def poolDirectory(self):
    return "pool/%s/%s/%s" % (self.distro.poolName(self.component), pathhash(self.name), self.name)

  def commitMerge(self):
    pass

  def version(self):
    return self.version
    return Version(self.source["Version"])

  def sourcesFile(self):
    return '%s/%s/Sources'%(config.get('ROOT'), self.poolDirectory())

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
        tree.ensure("%s/%s" % (output_dir, "REPORT"))

  def updatePoolSource(self):
    pooldir = self.poolDirectory()
    filename = self.sourcesFile()

    logging.info("Updating %s", filename)
    with open(filename, "w") as sources:
        shell.run(("apt-ftparchive", "sources", pooldir), chdir=config.get('ROOT'),
                  stdout=sources)

import model.debian
import model.obs
