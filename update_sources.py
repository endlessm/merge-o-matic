#!/usr/bin/env python
# -*- coding: utf-8 -*-
# update-sources.py - update the Sources files in a distribution's pool
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

import sys
import os

from model import Distro
import config
import model.error
import logging
from util import run

def main(options, args):
    upstreamSources = []
    packages = []
    for target in config.targets(args):
      logging.info("Updating sources for %s", target)
      d = target.distro
      d.updateSources(target.dist, target.component)
      for upstreamList in target.sources:
        for source in upstreamList:
          if source not in upstreamSources:
            for component in source.distro.components():
              logging.info("Updating upstream sources for %s/%s", source, component)
              source.distro.updateSources(source.dist, component)
            upstreamSources.append(source)
      for package in target.distro.packages(target.dist, target.component):
        if options.package and package.name not in options.package:
          continue
        packages.append(package)

        for upstreamList in target.sources:
          for source in upstreamList:
            try:
              upstreamPkgs = source.distro.findPackage(package.name, searchDist=source.dist)
              for upstreamPkg in upstreamPkgs:
                if upstreamPkg.package not in packages:
                  packages.append(upstreamPkg.package)
            except model.error.PackageNotFound:
              logging.debug("%s not found in %s, skipping.", package, source)
              pass

    logging.info("%d packages considered for updating", len(packages))
    for pkg in packages:
      logging.info("Updating %s", pkg)
      pkg.updatePool()
      pkg.updatePoolSource()
      logging.info("Updated %s to %s", pkg, pkg.newestVersion())

if __name__ == "__main__":
    run(main, usage="%prog [DISTRO...]",
        description="update the Sources file in a distribution's pool")
