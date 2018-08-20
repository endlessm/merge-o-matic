#!/usr/bin/env python
# -*- coding: utf-8 -*-
# generate-dpatches.py - generate extracted debian patches for new packages
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

import os
import logging

import config
from model import Distro
import model.error
from momlib import *
from util import tree, run

logger = logging.getLogger('generate_dpatches')


def options(parser):
    parser.add_option("-t", "--target", type="string", metavar="TARGET",
                      default=None,
                      help="Process only this distribution target")


def main(options, args):
    logger.info('Extracting debian/patches from packages...')

    for target in config.targets(args):
        d = target.distro
        for pkg in d.packages(target.dist, target.component):
            if options.package and pkg.name not in options.package:
                continue
            if pkg.name in target.blacklist:
                logger.debug("%s is blacklisted,skipping", source['Package'])
                continue

            pvs = pkg.getPoolVersions()
            pvs.sort()
            for pv in pvs:
                try:
                    generate_dpatch(d.name, pv)
                except model.error.PackageNotFound:
                    logger.exception("Could not find %s/%s for unpacking.",
                                     pkg, version)


def generate_dpatch(distro, pv):
    """Generate the extracted patches."""
    logger.debug("%s: %s", distro, pv)

    stamp = "%s/dpatch-stamp-%s" % (pv.package.poolPath, pv.version)

    if not os.path.isfile(stamp):
        open(stamp, "w").close()

        try:
            unpack_source(pv)
        except ValueError:
            logger.exception("Could not unpack %s!", pv)
        try:
            dirname = dpatch_directory(distro, pv)
            extract_dpatches(dirname, pv)
            logger.info("Saved dpatches: %s", tree.subdir(config.get('ROOT'),
                                                          dirname))
        finally:
            cleanup_source(pv)


def extract_dpatches(dirname, pv):
    """Extract patches from debian/patches."""
    srcdir = unpack_directory(pv)
    patchdir = "%s/debian/patches" % srcdir

    if not os.path.isdir(patchdir):
        logger.debug("No debian/patches")
        return

    for patch in tree.walk(patchdir):
        if os.path.basename(patch) in ["00list", "series", "README",
                                       ".svn", "CVS", ".bzr", ".git"]:
            continue
        elif not len(patch):
            continue

        logger.debug("%s", patch)
        src_filename = "%s/%s" % (patchdir, patch)
        dest_filename = "%s/%s" % (dirname, patch)

        tree.ensure(dest_filename)
        tree.copyfile(src_filename, dest_filename)


if __name__ == "__main__":
    run(main, options, usage="%prog [DISTRO...]",
        description="generate changes and diff files for new packages")
