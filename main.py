#!/usr/bin/env python
# -*- coding: utf-8 -*-
# main.py - main executable for a daily Merge-o-Matic run
#
# Copyright © 2012 Collabora Ltd.
# Author: Alexandre Rostovtsev <alexandre.rostovtsev@collabora.com>.
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
import os
import os.path
import shutil
import sys

from momversion import VERSION
from util import run
import config
import update_sources
import get_missing_bases
import generate_diffs
import generate_dpatches
import publish_patches
import produce_merges
import commit_merges
import notify_action_needed
import stats
import stats_graphs
import merge_status
import expire_pool

def options(parser):
    parser.add_option("-f", "--force", action="store_true",
                      help="Force creation of patches and merges")
    parser.add_option("-t", "--target", type="string", metavar="TARGET",
                      help="Process only this distribution target")
    parser.add_option("-d", "--dry-run", action="store_true", help="Don't actually fiddle with OBS, just print what would've happened.")

logger = logging.getLogger('main')

def main(options, args):
    logger.info('starting Merge-o-Matic version %s', VERSION)
    logger.debug('options: %r', options)
    logger.debug('args: %r', args)

    ROOT = config.get('ROOT')
    lockdir = "%s/.lock" % ROOT
    codedir = os.path.abspath(os.path.dirname(__file__))
    unpackeddir = "%s/unpacked" % ROOT

    # Some modules assume we're already here
    os.chdir(ROOT)

    # Default options values referenced in various *.main() functions
    options.exclude = None
    options.include = None
    options.version = None
    options.source_distro = None
    options.source_suite = None
    try:
        os.umask(002)
        try:
            logger.debug('Locking %r', lockdir)
            os.makedirs(lockdir)
        except:
            raise Exception("LOCKED (another one running?)")

        try:
            if not os.path.isdir('%s/merges' % ROOT):
                os.makedirs("%s/merges" % ROOT)
            shutil.copy2("%s/addcomment.py" % codedir, "%s/merges/addcomment.py" % ROOT)
        except:
            logger.exception('Unable to copy addcomment.py into %s/merges:',
                    ROOT)

        # Update the Sources files against new packages that have been downloaded
        update_sources.main(options, args)

        try:
            # Try to download missing base versions from the source distro pool
            get_missing_bases.main(options, args)
        except:
            logger.exception('Failed to get missing bases:')

        # Generate changes, diffs and patches
        generate_diffs.main(options, args)
        generate_dpatches.main(options, args)

        # Publish the patches
        publish_patches.main(options, args)

        # Run the merge tool
        produce_merges.main(options, args)

        # Commit committable changes to OBS
        commit_merges.main(options, args)
        notify_action_needed.main(options, args)

        # Produce pretty reports
        stats.main(options, args)
        stats_graphs.main(options, args)
        merge_status.main(options, args)

        # Expire any old packages from the pool
        expire_pool.main(options, args)

        # ?! untidy
        try:
            for entry in os.listdir(unpackeddir):
                p = "%s/%s" % (unpackeddir, entry)
                logger.debug('Removing unpacked directory %s', p)
                shutil.rmtree(p)
        except Exception as e:
            logger.debug('Cancelling removal of unpacked directories: %r', e)

    finally:
        try:
            logger.debug('Unlocking %r', lockdir)
            os.rmdir(lockdir)
        except Exception as e:
            logger.debug('Failed to unlock %r: %r', lockdir, e)

if __name__ == "__main__":
    run(main, options, usage="%prog",
        description="main merge-o-matic executable")
