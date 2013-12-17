#!/usr/bin/env python
# -*- coding: utf-8 -*-
# expire-pool.py - expires packages from all pools
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

import logging

from momlib import *
from util import tree, run
from merge_report import read_report
from model import Distro


def main(options, args):
    if len(args):
        distros = args
    else:
        distros = get_pool_distros()

    # Run through our default distribution and use that for the base
    # package names.  Expire from all distributions.
    for target in DISTRO_TARGETS.keys():
        our_distro, our_dist, our_component = get_target_distro_dist_component(target)
        d = Distro.get(our_distro)
        for source in d.getSources(our_dist, our_component):
            if options.package and source['Package'] not in options.package:
                continue

            try:
                output_dir = result_dir(target, source['Package'])
                report = read_report(output_dir)
                base = report["base_version"]
            except ValueError:
                logging.debug('Skipping package %s: unable to read merge report',
                        source['Package'])
                continue

            if base is None:
                # If there's no suitable base for merges, we don't
                # automatically expire any versions.
                logging.debug('Skipping package %s: no base version found',
                        source['Package'])
                continue

            logging.debug("%s %s", source["Package"], source["Version"])
            logging.debug("base is %s", base)

            for distro in distros:
                if DISTROS[distro]["expire"]:
                    for component in DISTROS[distro]['components']:
                      expire_pool_sources(distro, component, source["Package"], base)


def expire_pool_sources(distro, component, package, base):
    """Remove sources older than the given base.

    If the base doesn't exist, then the newest source that is older is also
    kept.
    """
    pooldir = pool_directory(distro, component, package)
    try:
        sources = get_pool_sources(distro, package)
    except IOError:
        return

    # Find sources older than the base, record the filenames of newer ones
    bases = []
    base_found = False
    keep = []
    for source in sources:
        if base > source["Version"]:
            bases.append(source)
        else:
            if base == source["Version"]:
                base_found = True
                logging.info("Leaving %s %s %s (is base)", distro, package,
                             source["Version"])
            else:
                logging.info("Leaving %s %s %s (is newer)", distro, package,
                             source["Version"])

            keep.append(source)

    # If the base wasn't found, we want the newest source below that
    if not base_found and len(bases):
        version_sort(bases)
        source = bases.pop()
        logging.info("Leaving %s %s %s (is newest before base)",
                     distro, package, source["Version"])

        keep.append(source)

    # Identify filenames we don't want to delete
    keep_files = []
    for source in keep:
        if has_files(source):
            for md5sum, size, name in files(source):
                keep_files.append(name)

    # Expire the older packages
    need_update = False
    for source in bases:
        logging.info("Expiring %s %s %s", distro, package, source["Version"])

        for md5sum, size, name in files(source):
            if name in keep_files:
                logging.debug("Not removing %s/%s", pooldir, name)
                continue

            tree.remove("%s/%s/%s" % (ROOT, pooldir, name))
            logging.debug("Removed %s/%s", pooldir, name)
            need_update = True


if __name__ == "__main__":
    run(main, usage="%prog [DISTRO...]",
        description="expires packages from all pools")
