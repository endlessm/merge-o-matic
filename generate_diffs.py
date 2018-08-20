#!/usr/bin/env python
# -*- coding: utf-8 -*-
# generate-diffs.py - generate changes and diff files for new packages
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
from momlib import *
from model.base import (Distro, PackageVersion)
from util import tree, run

logger = logging.getLogger('generate_diffs')


def options(parser):
    parser.add_option("-t", "--target", type="string", metavar="TARGET",
                      default=None,
                      help="Process only this distribution target")


def main(options, args):
    logger.info('Comparing current and previous versions in source distros...')

    # For latest version of each package in the given distributions, iterate
    # the pool in order and generate a diff from the previous version and a
    # changes file
    for target in config.targets(args):
        d = target.distro
        for pkg in d.packages(target.dist, target.component):
            if options.package and pkg.name not in options.package:
                continue
            if pkg.name in target.blacklist:
                logger.debug("%s is blacklisted, skipping", source['Package'])
                continue

            pvs = pkg.getPoolVersions()
            pvs.sort()

            last = None
            try:
                for pv in pvs:
                    try:
                        generate_diff(last, pv)
                    except model.error.PackageNotFound:
                        logger.exception("Could not find a package to diff "
                                         "against.")
                    except ValueError:
                        logger.exception("Could not find a .dsc file, "
                                         "perhaps it moved components?")
                    finally:
                        if last is not None:
                            cleanup_source(pv)
                    last = pv
            finally:
                if last is not None:
                    cleanup_source(pv)


def generate_diff(last, this):
    """Generate the differences."""

    changes_filename = changes_file(this.package.distro, this)
    if last is None:
        return
    if not os.path.isfile(changes_filename) \
            and not os.path.isfile(changes_filename + ".bz2"):
        try:
            unpack_source(this)
        except ValueError:
            logger.exception("Couldn't unpack %s.", this)
            return
        try:
            save_changes_file(changes_filename, this, last)
            logger.info("Saved changes file: %s",
                        tree.subdir(config.get('ROOT'), changes_filename))
        except (ValueError, OSError):
            logger.error("dpkg-genchanges for %s failed",
                         tree.subdir(config.get('ROOT'), changes_filename))

    logger.debug("Producing diff from %s to %s", this, last)
    diff_filename = diff_file(this.package.distro.name, this)
    if not os.path.isfile(diff_filename) \
            and not os.path.isfile(diff_filename + ".bz2"):
        unpack_source(this)
        unpack_source(last)
        save_patch_file(diff_filename, last, this)
        save_basis(diff_filename, last.version)
        logger.info("Saved diff file: %s", tree.subdir(config.get('ROOT'),
                                                       diff_filename))


if __name__ == "__main__":
    run(main, options, usage="%prog [DISTRO...]",
        description="generate changes and diff files for new packages")
