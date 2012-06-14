#!/usr/bin/env python
# -*- coding: utf-8 -*-
# commit-merges.py - commit merged packages
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

from momlib import *

def options(parser):
    parser.add_option("-d", "--distro", type="string", metavar="DISTRO",
                      default=None,
                      help="Distribution to publish")
    parser.add_option("-s", "--suite", type="string", metavar="SUITE",
                      default=None,
                      help="Suite (aka distrorelease) to publish")
    parser.add_option("-p", "--package", type="string", metavar="PACKAGE",
                      action="append",
                      help="Process only these packages")

def main(options, args):
    if options.distro:
        our_distros = [options.distro]
    else:
        our_distros = OUR_DISTROS

    if options.suite:
        our_dists = dict(zip(our_distros, [options.suite for d in our_distros]))
    else:
        our_dists = OUR_DISTS

    for our_distro in our_distros:
        for our_dist in our_dists[our_distro]:
            for component in DISTROS[our_distro]["components"]:
                for source in get_sources(our_distro, our_dist, component):
                    if options.package is not None \
                        and source["Package"] not in options.package:
                        continue
                    if not PACKAGELISTS.check_our_distro(source["Package"], our_distro):
                        continue

                    try:
                        output_dir = result_dir(source["Package"])
                        report = read_report(output_dir, our_distro, SRC_DISTROS[our_distro])
                    except ValueError:
                        continue

                    filepaths = ["%s/%s" % (report["merged_dir"], f) for f in report["merged_files"]]
                    if filepaths == []:
                        logging.warning("Empty merged file list in %s/REPORT" % output_dir)
                        continue

                    try:
                        if obs_commit_files(our_distro, report["package"], filepaths):
                            with open("%s/REPORT" % output_dir, "a") as r:
                                print >>r
                                print >>r, "Merge committed: YES"
                    except (ValueError, OSError) as e:
                        eargs = ""
                        if e.args:
                            eargs = " ".join(e.args)
                        logging.error("OBS commit for %s in %s failed: %s" % (report["package"], our_distro, eargs))
                        try:
                            with open("%s/REPORT" % output_dir, "a") as r:
                                print >>r
                                print >>r, "Merge committed: NO (failed: %s)" % eargs
                        except:
                            pass
    
if __name__ == "__main__":
    run(main, options, usage="%prog [DISTRO...]",
        description="commit merged packages to our repository")
