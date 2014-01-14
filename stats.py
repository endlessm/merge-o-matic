#!/usr/bin/env python
# -*- coding: utf-8 -*-
# stats.py - collect difference stats
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

import time
import logging

from momlib import *
from deb.version import Version
from model import Distro
from util import run
import config

import model.error

logger = logging.getLogger('stats')

def options(parser):
    parser.add_option("-D", "--source-distro", type="string", metavar="DISTRO",
                      default=None,
                      help="Source distribution")
    parser.add_option("-S", "--source-suite", type="string", metavar="SUITE",
                      default=None,
                      help="Source suite (aka distrorelease)")

    parser.add_option("-t", "--target", type="string", metavar="TARGET",
                      default=None,
                      help="Distribution target to generate stats for")

def main(options, args):
    # For latest version of each package in the destination distribution, locate the latest in
    # the source distribution; calculate the base from the destination
    if options.package:
      logger.info("Skipping stats since -p was specified.")
      return

    logger.info('Collecting stats...')

    for target in config.targets(args):
      stats = {}
      stats["total"] = 0
      stats["local"] = 0
      stats["unmodified"] = 0
      stats["needs-sync"] = 0
      stats["needs-merge"] = 0
      stats["repackaged"] = 0
      stats["modified"] = 0
      for pkg in target.distro.packages(target.dist, target.component):
        stats['total'] += 1

        upstream = None
        for srclist in target.getSourceLists(pkg.name):
          for src in srclist:
            try:
              for possible in src.distro.findPackage(pkg.name,
                      searchDist=src.dist):
                if upstream is None or possible > upstream:
                  upstream = possible
            except model.error.PackageNotFound:
              pass

        our_version = pkg.newestVersion()
        logger.debug("%s: %s, upstream: %s", target.distro,
            our_version, upstream)
        if upstream is None:
          logger.debug("%s: locally packaged", pkg)
          stats["local"] += 1
          continue

        base = target.findNearestVersion(our_version)

        if our_version.version == upstream.version:
          logger.debug("%s: unmodified", pkg)
          stats["unmodified"] += 1
        elif base > upstream:
          logger.debug("%s: locally repackaged", pkg)
          stats["repackaged"] += 1
        elif our_version.version == base.version:
          logger.debug("%s: needs sync", pkg)
          stats["needs-sync"] += 1
        elif our_version.version < upstream.version:
          logger.debug("%s: needs merge", pkg)
          stats["needs-merge"] += 1
        elif "-0co" in str(our_version.version):
          logger.debug("%s: locally repackaged", pkg)
          stats["repackaged"] += 1
        else:
          logger.debug("%s: modified", pkg)
          stats["modified"] += 1

      write_stats(target.name, stats)

def write_stats(target, stats):
    """Write out the collected stats."""
    stats_file = "%s/stats.txt" % ROOT
    with open(stats_file, "a") as stf:
        stamp = time.strftime("%Y-%m-%d %H:%M", time.gmtime())
        text = " ".join("%s=%d" % (k, v) for k,v in stats.items())
        print >>stf, "%s %s %s" % (stamp, target, text)

if __name__ == "__main__":
    run(main, options, usage="%prog",
        description="collect difference stats")
