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
    parser.add_option("-t", "--target", type="string", metavar="TARGET",
                      default=None,
                      help="Distribution target to publish")
    parser.add_option("-p", "--package", type="string", metavar="PACKAGE",
                      action="append",
                      help="Process only these packages")

def main(options, args):
    if options.target:
        targets = [options.target]
    else:
        targets = filter(lambda target: "obs" in DISTROS[DISTRO_TARGETS[target]["distro"]], DISTRO_TARGETS)

    for target in targets:
        our_distro, our_dist, our_component = get_target_distro_dist_component(target)
        for source in get_newest_sources(our_distro, our_dist, our_component):
            if options.package is not None \
                and source["Package"] not in options.package:
                continue
            if not PACKAGELISTS.check_target(target, None, source["Package"]):
                continue

            try:
                output_dir = result_dir(source["Package"])
                report = read_report(output_dir)
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
                    eargs = " ".join([str(x) for x in e.args])
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
