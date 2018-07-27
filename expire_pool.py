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

import errno
import logging

from momlib import *
from util import tree, run
from merge_report import (read_report, MergeResult)
from model.base import Distro

logger = logging.getLogger('expire_pool')

def main(options, args):
    if len(args):
        distros = [Distro.get(a) for a in args]
    else:
        distros = Distro.all()

    # Run through our default distribution and use that for the base
    # package names.  Expire from all distributions.
    for target in config.targets(args):
        d = target.distro
        for pkg in d.packages(target.dist, target.component):
            if options.package and pkg.name not in options.package:
                continue

            try:
                output_dir = result_dir(target, pkg.name)
                report = read_report(output_dir)
                base = report["base_version"]
            except ValueError:
                logger.debug('Skipping package %s: unable to read merge report',
                        pkg.name)
                continue

            if report['result'] not in (MergeResult.SYNC_THEIRS,
                    MergeResult.KEEP_OURS, MergeResult.MERGED,
                    MergeResult.CONFLICTS):
                logger.debug('Skipping expiry for package %s: result=%s',
                        pkg.name, report['result'])
                continue

            if base is None:
                # If there's no suitable base for merges, we don't
                # automatically expire any versions.
                logger.debug('Skipping expiry for package %s: '
                        'no base version found (result=%s)',
                        pkg.name, report['result'])
                continue

            base = Version(base)
            logger.debug("%s base is %s", pkg.name, base)

            for distro in distros:
                if distro.shouldExpire():
                    for component in distro.components():
                      distro_pkg = distro.package(target.dist, component, pkg.name)
                      expire_pool_sources(distro_pkg, base)


def expire_pool_sources(pkg, base):
    """Remove sources older than the given base.

    If the base doesn't exist, then the newest source that is older is also
    kept.
    """
    pooldir = pkg.poolPath

    # Find sources older than the base, record the filenames of newer ones
    bases = []
    base_found = False
    keep = []
    for pv in pkg.getPoolVersions():
        if base > pv:
            bases.append(pv)
        else:
            if base == pv.version():
                base_found = True
                logger.info("Leaving %s %s (is base)", distro, pv)
            else:
                logger.info("Leaving %s %s (is newer)", distro, pv)

            keep.append(pv)

    # If the base wasn't found, we want the newest source below that
    if not base_found and len(bases):
        version_sort(bases)
        pv = bases.pop()
        logger.info("Leaving %s %s (is newest before base)",
                     distro, pv)

        keep.append(pv)

    # Identify filenames we don't want to delete
    keep_files = []
    for pv in keep:
        if has_files(pv):
            for md5sum, size, name in files(pv):
                keep_files.append(name)

    # Expire the older packages
    need_update = False
    for pv in bases:
        logger.info("Expiring %s %s", distro, pv)

        for md5sum, size, name in files(pv):
            if name in keep_files:
                logger.debug("Not removing %s/%s", pooldir, name)
                continue

            tree.remove("%s/%s" % (pooldir, name))
            logger.debug("Removed %s/%s", pooldir, name)
            need_update = True


if __name__ == "__main__":
    run(main, usage="%prog [DISTRO...]",
        description="expires packages from all pools")
