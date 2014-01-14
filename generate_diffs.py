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

from momlib import *
from util import tree, run
from model import Distro
import config


def options(parser):
    parser.add_option("-t", "--target", type="string", metavar="TARGET",
                      default=None,
                      help="Process only this distribution target")

logger = logging.getLogger('generate_diffs')

def main(options, args):
    logger.info('Comparing current and previous versions in source distros...')

    # For latest version of each package in the given distributions, iterate the pool in order
    # and generate a diff from the previous version and a changes file
    for target in config.targets(args):
      d = target.distro
      for source in d.newestSources(target.dist, target.component):
        if options.package and source['Package'] not in options.package:
          continue
        if source['Package'] in target.blacklist:
          logger.debug("%s is blacklisted, skipping", source['Package'])
          continue
        try:
          pkg = d.package(target.dist, target.component, source['Package'])
        except model.error.PackageNotFound, e:
          logger.exception("Spooky stuff going on with %s.", d)
          continue
        sources = pkg.getSources()
        version_sort(sources)

        last = None
        try:
          for version in pkg.versions():
            try:
              generate_diff(last, version)
            except model.error.PackageNotFound:
              logger.exception("Could not find a package to diff against.")
            except ValueError:
              logger.exception("Could not find a .dsc file, perhaps it moved components?")
            finally:
              if last is not None:
                cleanup_source(last.getSources())
            last = version
        finally:
          if last is not None:
            cleanup_source(last.getSources())


def generate_diff(last, this):
    """Generate the differences."""

    changes_filename = changes_file(this.package.distro, this.getSources())
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
            save_changes_file(changes_filename, this.getSources(),
                last.getSources())
            logger.info("Saved changes file: %s",
                          tree.subdir(ROOT, changes_filename))
        except (ValueError, OSError):
            logger.error("dpkg-genchanges for %s failed",
                          tree.subdir(ROOT, changes_filename))

    logger.debug("Producing diff from %s to %s", this, last)
    diff_filename = diff_file(this.package.distro.name, this.getSources())
    if not os.path.isfile(diff_filename) \
            and not os.path.isfile(diff_filename + ".bz2"):
        unpack_source(this)
        unpack_source(last)
        save_patch_file(diff_filename, last.getSources(), this.getSources())
        save_basis(diff_filename, last.getSources()["Version"])
        logger.info("Saved diff file: %s", tree.subdir(ROOT, diff_filename))


if __name__ == "__main__":
    run(main, options, usage="%prog [DISTRO...]",
        description="generate changes and diff files for new packages")
