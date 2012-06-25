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
from util import tree


def options(parser):
    parser.add_option("-t", "--target", type="string", metavar="TARGET",
                      default=None,
                      help="Distribution target to publish patches for")

def main(options, args):
    if options.target:
        targets = [options.target]
    else:
        targets = DISTRO_TARGETS.keys()

    # Write to a new list
    list_filename = patch_list_file()
    ensure(list_filename)
    list_file = open(list_filename + ".new", "w")
    try:
        # For latest version of each package in the distribution, check for a patch for the
        # current version; publish if it exists, clean up if not
        for target in targets:
            our_distro, our_dist, our_component = get_target_distro_dist_component(target)
            for source in get_newest_sources(our_distro, our_dist, our_component):
                package = source["Package"]

                if not PACKAGELISTS.check_target(target, None, source["Package"]):
                    continue

                # Publish slipped patches in preference to true-base ones
                slip_filename = patch_file(our_distro, source, True)
                filename = patch_file(our_distro, source, False)

                if os.path.isfile(slip_filename):
                    publish_patch(our_distro, source, slip_filename, list_file)
                elif os.path.isfile(filename):
                    publish_patch(our_distro, source, filename, list_file)
                else:
                    unpublish_patch(our_distro, source)
    finally:
        list_file.close()

    # Move the new list over the old one
    os.rename(list_filename + ".new", list_filename)


def publish_patch(distro, source, filename, list_file):
    """Publish the latest version of the patch for all to see."""
    publish_filename = published_file(distro, source)

    ensure(publish_filename)
    if os.path.isfile(publish_filename):
        os.unlink(publish_filename)
    os.link(filename, publish_filename)

    logging.info("Published %s", tree.subdir(ROOT, publish_filename))
    print >>list_file, "%s %s" % (source["Package"],
                                  tree.subdir("%s/published" % ROOT,
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

    dpatch_dir = dpatch_directory(distro, source)
    if os.path.isdir(dpatch_dir):
        for dpatch in tree.walk(dpatch_dir):
            if not len(dpatch):
                continue

            src_filename = "%s/%s" % (dpatch_dir, dpatch)
            dest_filename = "%s/%s" % (output, dpatch)

            logging.info("Published %s", tree.subdir(ROOT, dest_filename))
            ensure(dest_filename)
            tree.copyfile(src_filename, dest_filename)

def unpublish_patch(distro, source):
    """Remove any published patch."""
    publish_dir = os.path.dirname(published_file(distro, source))
    cleanup(publish_dir)


if __name__ == "__main__":
    run(main, options, usage="%prog",
        description="publish patches for the given distribution")
