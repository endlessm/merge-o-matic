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

import model.error


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

    parser.add_option("-p", "--package", type="string", metavar="PACKAGE",
                      action="append",
                      help="Process only these packages")

def main(options, args):
    if options.target:
        targets = [options.target]
    else:
        targets = DISTRO_TARGETS.keys()

    # For latest version of each package in the destination distribution, locate the latest in
    # the source distribution; calculate the base from the destination
    for target in targets:
        our_distro, our_dist, our_component = get_target_distro_dist_component(target)
        stats = {}
        stats["total"] = 0
        stats["local"] = 0
        stats["unmodified"] = 0
        stats["needs-sync"] = 0
        stats["needs-merge"] = 0
        stats["repackaged"] = 0
        stats["modified"] = 0

        d = Distro.get(our_distro)
        for our_source in d.newestSources(our_dist, our_component):
            if options.package is not None \
                and our_source["Package"] not in options.package:
                continue

            package = our_source["Package"]
            our_version = Version(our_source["Version"])
            logging.debug("%s: %s is %s", package, our_distro, our_version)

            stats["total"] += 1

            if not PACKAGELISTS.check_target(target, None, our_source["Package"]):
                logging.debug("%s: blacklisted or not whitelisted", package)
                stats["local"] += 1
                continue

            try:
                if options.source_distro is None:
                    (src_source, src_version, src_pool_source, src_distro, src_dist) \
                                = PACKAGELISTS.find_in_source_distros(target, package)
                else:
                    src_distro = options.source_distro
                    src_dist = options.source_suite
                    (src_source, src_version, src_pool_source) \
                                = get_same_source(src_distro, src_dist, package)

                logging.debug("%s: %s is %s", package, src_distro, src_version)
            except model.error.PackageNotFound:
                logging.debug("%s: locally packaged", package)
                stats["local"] += 1
                continue

            base = get_base(our_source)

            if our_version == src_version:
                logging.debug("%s: unmodified", package)
                stats["unmodified"] += 1
            elif base > src_version:
                logging.debug("%s: locally repackaged", package)
                stats["repackaged"] += 1
            elif our_version == base:
                logging.debug("%s: needs sync", package)
                stats["needs-sync"] += 1
            elif our_version < src_version:
                logging.debug("%s: needs merge", package)
                stats["needs-merge"] += 1
            elif "-0co" in str(our_version):
                logging.debug("%s: locally repackaged", package)
                stats["repackaged"] += 1
            else:
                logging.debug("%s: modified", package)
                stats["modified"] += 1

        write_stats(target, stats)

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
