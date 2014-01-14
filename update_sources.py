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

import osc.core

from deb.version import Version
from model import Distro
from model.obs import OBSDistro
import config
import model.error
import logging
from util import run

logger = logging.getLogger('update_sources')

def main(options, args):
    logger.info('Updating source packages in target and source distros...')

    upstreamSources = []
    packages = []
    for target in config.targets(args):
      logger.info("Updating sources for %s", target)
      d = target.distro
      d.updateSources(target.dist, target.component)

      pairs = []
      for stanza in d.getSources(target.dist, target.component):
        pairs.append((stanza.get('Package'), Version(stanza.get('Version'))))
      logger.debug('Packages in %s:', target)
      for pair in sorted(pairs):
        logger.debug('- %s/%s', pair[0], pair[1])

      for upstreamList in target.getAllSourceLists():
        for source in upstreamList:
          if source not in upstreamSources:
            for component in source.distro.components():
              logger.info("Updating upstream sources for %s/%s", source, component)
              source.distro.updateSources(source.dist, component)

              pairs = []
              for stanza in source.distro.getSources(source.dist, component):
                pairs.append((stanza.get('Package'),
                    Version(stanza.get('Version'))))
              logger.debug('Packages in %s/%s:', source, component)
              for pair in sorted(pairs):
                logger.debug('- %s/%s', pair[0], pair[1])

            upstreamSources.append(source)

      package_names = set()
      for package in target.distro.packages(target.dist, target.component):
        package_names.add(package.name)
        if options.package and package.name not in options.package:
          continue
        packages.append(package)

        for upstreamList in target.getSourceLists(package.name):
          for source in upstreamList:
            try:
              upstreamPkgs = source.distro.findPackage(package.name, searchDist=source.dist)
              for upstreamPkg in upstreamPkgs:
                if upstreamPkg.package not in packages:
                  packages.append(upstreamPkg.package)
            except model.error.PackageNotFound:
              logger.debug("%s not found in %s, skipping.", package, source)
              pass

      if isinstance(d, OBSDistro):
        try:
          project = d.obsProject(target.dist, target.component)
          logger.debug('Checking packages in %s', project)
          obs_packages = set(
              osc.core.meta_get_packagelist(d.config('obs', 'url'),
                project))
          for p in package_names:
            if p not in obs_packages:
              logger.warning('Debian source package "%s" does not seem '
                  'to correspond to an OBS package. Please rename the OBS '
                  'package to match "Source" in the .dsc file', p)
        except:
          logger.warning('Unable to check packages in %s', project,
              exc_info=1)

    logger.info("%d packages considered for updating", len(packages))
    for pkg in packages:
      # updatePool and updatePoolSource ignore the suite (distribution)
      # and work on the pool directory directly, so don't put the
      # suite in the log messages: it's misleading.
      #
      # FIXME: if we track two suites, say raring and saucy, we could
      # have both ubuntu/raring/main/hello and ubuntu/saucy/main/hello
      # in @packages, resulting in us updating the ubuntu/*/main/hello
      # pool directory twice. For the moment, we just live with it.
      logger.info("Updating %s/*/%s/%s", pkg.distro, pkg.component,
          pkg.name)
      pkg.updatePool()
      pkg.updatePoolSource()
      logger.info("Available versions of %s/*/%s/%s:",
          pkg.distro, pkg.component, pkg.name)
      for pv in sorted(pkg.poolVersions()):
        logger.info('- %s', pv.version)

if __name__ == "__main__":
    run(main, usage="%prog [DISTRO...]",
        description="update the Sources file in a distribution's pool")
