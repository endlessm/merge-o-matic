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

def main(options, args):
    logger.info('Trying to download missing base versions for 3-way merge...')

    for target in config.targets(args):
      distro = target.distro
      for pkg in distro.packages(target.dist, target.component):
        if options.package is not None and pkg.name not in options.package:
          continue

        base = pkg.newestVersion().version.base()
        nearest = target.findNearestVersion(pkg.newestVersion())
        if nearest.version == base:
          # already have the base
          continue

        logger.debug("Attempting to fetch missing base %s for %s",
                     base, pkg.newestVersion())
        poolDir = pkg.poolDirectory()
        tmpdir = mkdtemp()

        try:
          rc = subprocess.call(['debsnap', '-d', tmpdir, '-f', '-v', pkg.name,
                                str(base)])
          if rc != 0:
            logger.warning("debsnap failed with code %d", rc)
            continue

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
