#!/usr/bin/env python
# -*- coding: utf-8 -*-
# publish-patches.py - publish patches for the given distribution
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

logger = logging.getLogger('publish_patches')

def options(parser):
    parser.add_option("-t", "--target", type="string", metavar="TARGET",
                      default=None,
                      help="Distribution target to publish patches for")

def main(options, args):
    logger.info('Comparing target packages with source distros...')

    if options.target:
        targets = [options.target]
    else:
        targets = config.get('DISTRO_TARGETS').keys()

    # Write to a new list
    list_filename = patch_list_file()
    tree.ensure(list_filename)
    list_file = open(list_filename + ".new", "w")
    try:
        # For latest version of each package in the distribution, check for a patch for the
        # current version; publish if it exists, clean up if not
        for target in targets:
            our_distro, our_dist, our_component = get_target_distro_dist_component(target)
            d = Distro.get(our_distro)
            for pv in d.newestPackageVersions(our_dist, our_component):
                if options.package and pv.package.name not in options.package:
                    continue

                if not PackageLists().check_target(target, None,
                                                   pv.package.name):
                    continue

                # Publish slipped patches in preference to true-base ones
                slip_filename = patch_file(our_distro, pv, True)
                filename = patch_file(our_distro, pv, False)

                if os.path.isfile(slip_filename):
                    publish_patch(our_distro, pv, slip_filename, list_file)
                elif os.path.isfile(filename):
                    publish_patch(our_distro, pv, filename, list_file)
                else:
                    unpublish_patch(our_distro, pv)
    finally:
        list_file.close()

    # Move the new list over the old one
    os.rename(list_filename + ".new", list_filename)


def publish_patch(distro, pv, filename, list_file):
    """Publish the latest version of the patch for all to see."""
    publish_filename = published_file(distro, pv)

    tree.ensure(publish_filename)
    if os.path.isfile(publish_filename):
        os.unlink(publish_filename)
    os.link(filename, publish_filename)

    logger.info("Published %s", tree.subdir(config.get('ROOT'),
                                            publish_filename))
    print >>list_file, "%s %s" % (pv.package,
                                  tree.subdir("%s/published" % config.get('ROOT'),
                                              publish_filename))

    # Remove older patches
    for junk in os.listdir(os.path.dirname(publish_filename)):
        junkpath = "%s/%s" % (os.path.dirname(publish_filename), junk)
        if os.path.isfile(junkpath) \
                and junk != os.path.basename(publish_filename):
            os.unlink(junkpath)

    # Publish extracted patches
    output = "%s/extracted" % os.path.dirname(publish_filename)
    if os.path.isdir(output):
        tree.remove(output)

    dpatch_dir = dpatch_directory(distro, pv)
    if os.path.isdir(dpatch_dir):
        for dpatch in tree.walk(dpatch_dir):
            if not len(dpatch):
                continue

            src_filename = "%s/%s" % (dpatch_dir, dpatch)
            dest_filename = "%s/%s" % (output, dpatch)

            logger.info("Published %s", tree.subdir(config.get('ROOT'),
                                                    dest_filename))
            tree.ensure(dest_filename)
            tree.copyfile(src_filename, dest_filename)

def unpublish_patch(distro, pv):
    """Remove any published patch."""
    publish_dir = os.path.dirname(published_file(distro, pv))
    cleanup(publish_dir)


if __name__ == "__main__":
    run(main, options, usage="%prog",
        description="publish patches for the given distribution")
