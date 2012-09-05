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
from model import Distro


def options(parser):
    parser.add_option("-p", "--package", type="string", metavar="PACKAGE",
                      action="append",
                      help="Process only these packages")

def main(options, args):
    # Update target distribution sources and calculate the list of packages we are
    # interested in (no need to download the entire Ubuntu archive...)
    for target in config.targets(args):
      target.distro.updatePool(target.dist, target.component)
      for package in target.distro.packages():
        package.updatePoolSources()
        for upstreamList in target.sources:
          for source in upstreamList:
            for component in source.distro.components():
              source.distro.updatePool(source.dist, component)
      packages = target.
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
        updated_sources.add((our_distro, our_dist, our_component))
        sources.extend(d.getSources(our_dist, our_component))
        for pkg in sources:
          if options.package and pkg['Package'] not in options.package:
            continue
          for sourceName in DISTRO_TARGETS[target]['sources']:
            for source in DISTRO_SOURCES[sourceName]:
              distname = source["dist"]
              sourceDistro = Distro.get(source["distro"])
              PACKAGELISTS.add_if_needed(target, sourceName, pkg['Package'])
              for component in sourceDistro.components():
                sourceDistro.updatePool(distname, component, pkg['Package'])
                sourceDistro.package(pkg['Package'], distname, component).updatePoolSource()
        PACKAGELISTS.save_if_modified(target)

if __name__ == "__main__":
    run(main, options, usage="%prog [DISTRO...]",
        description="update a distribution's pool")
