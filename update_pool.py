#!/usr/bin/env python
# -*- coding: utf-8 -*-
# update-pool.py - update a distribution's pool
#
# Copyright © 2008 Canonical Ltd.
# Author: Scott James Remnant <scott@ubuntu.com>.
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

from __future__ import with_statement

import os
import gzip
import urllib
import logging
import tempfile
from contextlib import closing

from momlib import *
from util import tree
from config import Distro


def options(parser):
    parser.add_option("-p", "--package", type="string", metavar="PACKAGE",
                      action="append",
                      help="Process only these packages")

def main(options, args):
    if len(args):
        distros = args
    else:
        distros = get_pool_distros()

    # Update target distribution sources and calculate the list of packages we are
    # interested in (no need to download the entire Ubuntu archive...)
    updated_sources = set()
    for target in DISTRO_TARGETS:
        our_distro = DISTRO_TARGETS[target]["distro"]
        our_dist = DISTRO_TARGETS[target]["dist"]
        our_component = DISTRO_TARGETS[target]["component"]
        if our_distro not in distros:
            continue
        d = Distro.get(our_distro)
        sources = []
        logging.info("Updating %s/%s/%s", d.name, our_dist, our_component)
        d.updatePool(our_dist, our_component)
        d.updateSources(our_dist, our_component)
        updated_sources.add((our_distro, our_dist, our_component))
        sources.extend(d.getSources(our_dist, our_component))
        for sourceName in DISTRO_TARGETS[target]['sources']:
          for source in DISTRO_SOURCES[sourceName]:
            distname = source["dist"]
            sourceDistro = Distro.get(source["distro"])
            for component in sourceDistro.components():
              sourceDistro.updateSources(distname, component)
              totalPackages = len(d.packages(our_dist, our_component))
              upstreamPackages = len(sourceDistro.packages(distname, component))
              packageSavings = len(sourceDistro.packages(distname, component)) - len(d.packages(our_dist, our_component))
              logging.info("Downloading %d/%d packages", totalPackages, upstreamPackages)
              finishedPackages = 0
              for pkg in d.packages(our_dist, our_component):
                logging.info("%d/%d: Updating %s in upstream %s pool", finishedPackages, totalPackages, pkg.name, sourceDistro)
                finishedPackages += 1
                sourceDistro.updatePool(distname, component, pkg.name)

if __name__ == "__main__":
    run(main, options, usage="%prog [DISTRO...]",
        description="update a distribution's pool")
