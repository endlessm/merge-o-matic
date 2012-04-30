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

from momlib import *
import update_pool
import update_sources
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
    parser.add_option("-p", "--package", type="string", metavar="PACKAGE",
                      action="append",
                      help="Process only this package")
                      
def main(options, args):
    lockdir = "%s/.lock" % ROOT
    codedir = os.path.dirname(__file__)
    unpackeddir = "%s/unpacked" % ROOT

    # Default options values referenced in various *.main() functions
    options.component = None
    options.distro = None
    options.suite = None
    options.exclude = None
    options.include = None
    options.version = None
    options.source_distro = None
    options.source_suite = None
    options.dest_distro = None
    options.dest_suite = None
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

        try:
            # Download new packages
            update_pool.main(options, args)

            # Update the Sources files against new packages that have been downloaded
            update_sources.main(options, args)
        except:
            sys.excepthook(sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])

        # Generate changes, diffs and patches
        generate_diffs.main(options, args)
        generate_patches.main(options, args)
        generate_dpatches.main(options, args)

        # Publish the patches
        publish_patches.main(options, args)
        syndicate.main(options, args)
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
        for entry in os.listdir(unpackeddir):
            shutil.rmtree("%s/entry" % unpackeddir)
        
    finally:
        try:
            os.rmdir(lockdir)
        except:
            pass

if __name__ == "__main__":
    run(main, options, usage="%prog",
        description="main merge-o-matic executable")
