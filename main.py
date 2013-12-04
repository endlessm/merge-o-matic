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

import os
import os.path
import shutil
import sys

from util import run
import config
import update_sources
import get_missing_bases
import generate_diffs
import generate_patches
import generate_dpatches
import publish_patches
import syndicate
import produce_merges
import commit_merges
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
                      
def main(options, args):
    lockdir = "%s/.lock" % config.get('ROOT')
    codedir = os.path.dirname(__file__)
    unpackeddir = "%s/unpacked" % config.get('ROOT')

    # Some modules assume we're already here
    os.chdir(config.get('ROOT'))

    # Default options values referenced in various *.main() functions
    options.exclude = None
    options.include = None
    options.version = None
    options.source_distro = None
    options.source_suite = None
    try:
        os.umask(002)
        try:
            os.makedirs(lockdir)
        except:
            raise Exception("LOCKED (another one running?)")

        try:
            os.makedirs("%s/merges" % ROOT)
            shutil.copy2("%s/addcomment.py" % codedir, "%s/merges/addcomment.py" % ROOT)
        except:
            pass

        # Update the Sources files against new packages that have been downloaded
        update_sources.main(options, args)

        try:
            # Try to download missing base versions from the source distro pool
            get_missing_bases.main(options, args)
        except:
            sys.excepthook(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])

        # Generate changes, diffs and patches
        generate_diffs.main(options, args)
        generate_patches.main(options, args)
        generate_dpatches.main(options, args)

        # Publish the patches
        publish_patches.main(options, args)
        # syndicate.main(options, args)
        # mail_bugs.main(options, args)

        # Run the merge tool
        produce_merges.main(options, args)

        # Commit committable changes to OBS
        commit_merges.main(options, args)

        # Produce pretty reports
        stats.main(options, args)
        stats_graphs.main(options, args)
        merge_status.main(options, args)
        # manual_status.main(options, args)

        # Expire any old packages from the pool
        expire_pool.main(options, args)

        # ?! untidy
        try:
            for entry in os.listdir(unpackeddir):
                shutil.rmtree("%s/%s" % (unpackeddir, entry))
        except:
            pass
        
    finally:
        try:
            os.rmdir(lockdir)
        except:
            pass

if __name__ == "__main__":
    run(main, options, usage="%prog",
        description="main merge-o-matic executable")
