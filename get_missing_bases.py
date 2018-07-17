#!/usr/bin/env python
# -*- coding: utf-8 -*-
# get_missing_bases.py - download missing base versions to make a 3-way
# merge possible
#
# Copyright © 2012 Collabora Ltd.
# Author: Alexandre Rostovtsev <alexandre.rostovtsev@collabora.com>.
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
import urllib
from momlib import *
from config import *
from model import Distro, Package
import model.error
from util import tree, run
import config
import subprocess
from tempfile import mkdtemp
from urlparse import urljoin
import json
import urllib2

logger = logging.getLogger('update_sources')

BASE_URL = 'http://snapshot.debian.org'

def options(parser):
    parser.add_option("-t", "--target", type="string", metavar="TARGET",
                      default=None,
                      help="Distribution target to fetch for")
    parser.add_option("-D", "--source-distro", type="string", metavar="DISTRO",
                      default=None,
                      help="Source distribution")
    parser.add_option("-S", "--source-suite", type="string", metavar="SUITE",
                      default=None,
                      help="Source suite (aka distrorelease)")

def package_version_present_in_sources(target, pkg, base):
    for pv in target.findSourcePackage(pkg.name, base):
      for pool_pv in pv.package.getPoolVersions():
        if pool_pv.version == base:
          return True
    return False

def get_file_hash_from_fileinfo(data, filename):
  for filehash, files in data['fileinfo'].iteritems():
    for fileinfo in files:
      if fileinfo['name'] == filename:
        return filehash
  return None

def download_file(url, output_path):
    try:
      fd = urllib2.urlopen(url)
      with open(output_path, 'w') as output:
        output.write(fd.read())
      return True
    except urllib2.HTTPError, e:
      logger.exception('Failed to download %s', url)
      return False

def fetch_from_snapshot(package_name, version, output_dir):
    url = '%s/mr/package/%s/%s/srcfiles?fileinfo=1' % \
          (BASE_URL, package_name, version)
    try:
      fd = urllib2.urlopen(url)
      data = json.load(fd)
    except urllib2.HTTPError, e:
      logger.exception('Failed to download %s', url)
      return False

    dsc_name = '%s_%s.dsc' % (package_name, version)
    dsc_hash = get_file_hash_from_fileinfo(data, dsc_name)
    dsc_path = os.path.join(output_dir, dsc_name)

    url = '%s/file/%s' % (BASE_URL, dsc_hash)
    if not download_file(url, dsc_path):
      return False

    dsc_data = ControlFile(dsc_path, multi_para=False, signed=True).para
    for filehash, size, filename in files(dsc_data):
      snapshot_hash = get_file_hash_from_fileinfo(data, filename)
      url = '%s/file/%s' % (BASE_URL, snapshot_hash)
      path = os.path.join(output_dir, filename)
      if not download_file(url, path):
        return False

    return True


def main(options, args):
    logger.info('Trying to download missing base versions for 3-way merge...')

    for target in config.targets(args):
      distro = target.distro
      for pkg in distro.packages(target.dist, target.component):
        if options.package is not None and pkg.name not in options.package:
          continue

        base = pkg.newestVersion().version.base()

        # See if the base version is already in the target distro
        try:
            target.distro.findPackage(pkg.name, searchDist=target.dist,
                                      version=base)
            # already have the base
            continue
        except model.error.PackageNotFound:
            pass

        # Now look for the base version in the source distros
        if package_version_present_in_sources(target, pkg, base):
            continue

        logger.debug("Attempting to fetch missing base %s for %s",
                     base, pkg.newestVersion())

        tmpdir = mkdtemp()
        if not fetch_from_snapshot(pkg.name, str(base), tmpdir):
          shutil.rmtree(tmpdir)
          continue

        # For lack of a better place, we save the missing base version under
        # the very last source distro in the list.
        source_list = target.getSourceLists(pkg.name)[-1]
        source = source_list[-1]
        component = source.distro.components()[-1]
        logger.debug("Saving it into last source %s component %s",
                     source.distro, component)
        source_pkg = Package(source.distro, source.dist, component, pkg.name)
        poolDir = source_pkg.poolPath

        if not os.path.exists(poolDir):
          os.makedirs(poolDir)

        for filename in os.listdir(tmpdir):
          if not os.path.exists(os.path.join(poolDir, filename)):
            shutil.move(os.path.join(tmpdir, filename), poolDir)

        shutil.rmtree(tmpdir)

if __name__ == "__main__":
    run(main, options, usage="%prog]",
        description="download missing base versions to make 3-way merge possible")
