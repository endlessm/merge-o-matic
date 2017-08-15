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
from model import Distro
from model.base import PoolDirectory
import model.error
from util import tree, run
import config
import subprocess
from tempfile import mkdtemp

logger = logging.getLogger('update_sources')

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
    for sl in target.getSourceLists(pkg.name):
        for source in sl:
            for component in source.distro.components():
                pooldir = PoolDirectory(source.distro, component,
                                        pkg.name)

                if base in pooldir.getVersions():
                    return True
    return False

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

        # For lack of a better place, we save the missing base version under
        # the very last source distro in the list.
        source_list = target.getSourceLists(pkg.name)[-1]
        source = source_list[-1]
        component = source.distro.components()[-1]
        logger.debug("Saving it into last source %s component %s",
                     source.distro, component)
        poolDir = PoolDirectory(source.distro, component, pkg.name)

        tmpdir = mkdtemp()
        try:
          rc = subprocess.call(['debsnap', '-d', tmpdir, '-f', '-v', pkg.name,
                                str(base)])
          if rc != 0:
            logger.warning("debsnap failed with code %d", rc)
            continue

          if not os.path.exists(poolDir.path):
              os.makedirs(poolDir.path)

          updated = False
          for filename in os.listdir(tmpdir):
            if not os.path.exists(os.path.join(poolDir.path, filename)):
              shutil.move(os.path.join(tmpdir, filename), poolDir.path)
              updated = True
        finally:
          shutil.rmtree(tmpdir)
        
        if updated:
          poolDir.updateSources()
        

if __name__ == "__main__":
    run(main, options, usage="%prog]",
        description="download missing base versions to make 3-way merge possible")
