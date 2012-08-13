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
import config
from model import Distro, OBSDistro
import urllib2

def options(parser):
    parser.add_option("-t", "--target", type="string", metavar="TARGET",
                      default=None,
                      help="Distribution target to publish")
    parser.add_option("-p", "--package", type="string", metavar="PACKAGE",
                      action="append",
                      help="Process only these packages")
    parser.add_option("-d", "--dry-run", action="store_true", help="Don't actually fiddle with OBS, just print what would've happened.")

def main(options, args):
    if options.target:
        targets = [options.target]
    else:
        targets = filter(lambda target: "obs" in DISTROS[DISTRO_TARGETS[target]["distro"]], DISTRO_TARGETS)

    for target in targets:
        our_distro, our_dist, our_component = get_target_distro_dist_component(target)
        d = Distro.get(our_distro)
        if not isinstance(d, OBSDistro):
            continue
        for source in d.newestSources(our_dist, our_component):
            if options.package is not None \
                and source["Package"] not in options.package:
                continue
            if not PACKAGELISTS.check_target(target, None, source["Package"]):
                continue

            try:
                output_dir = result_dir(target, source["Package"])
                report = read_report(output_dir)
            except ValueError:
                continue

            package = d.package(our_dist, our_component, report['package'])
            filepaths = report['merged_files']
            if filepaths == []:
                logging.warning("Empty merged file list in %s/REPORT" % output_dir)
                continue

            if config.get("DISTRO_TARGETS", target, "commit", default=False):
              logging.info("Committing changes to %s", package)
              if not options.dry_run:
                try:
                  #package.commit('Automatic update by Merge-O-Matic')
                  pass
                except urllib2.HTTPError:
                  logging.exception("Failed to commit %s", package)
            else:
              logging.debug("Branching %s", package)
              branchPkg = package.branch("home:%s:branches:%s"%(d.obsUser, d.name))
              branch = branchPkg.distro
              branch.sync(our_dist, our_component, [branchPkg,])
              logging.info("Committing changes to %s, and submitting merge request to %s", branchPkg, package)
              if report['merged_is_right']:
                srcDistro = Distro.get(report['right_distro'])
                for upstream in DISTRO_TARGETS[target]['sources']:
                  for src in DISTRO_SOURCES[upstream]:
                    srcDistro = Distro.get(src['distro'])
                    for component in srcDistro.components():
                      try:
                        pkg = srcDistro.package(src['dist'], component, package.name)
                        pfx = pkg.poolDirectory()
                        break
                      except:
                        pass
              else:
                pfx = result_dir(target, package.name)

              for f in branchPkg.files:
                if f.endswith(".dsc"):
                  oldDsc = '%s/%s'%(branchPkg.obsDir(), f)
                  break
              for f in filepaths:
                if f.endswith(".dsc"):
                  newDsc = '%s/%s'%(pfx, f)
                  break

              logging.debug("Running debdiff on %s and %s", oldDsc, newDsc)
              diff = shell.get(("debdiff", oldDsc, newDsc))
              for f in branchPkg.files:
                if f == "_link":
                  continue
                try:
                  os.unlink('%s/%s'%(branchPkg.obsDir(), f))
                except OSError:
                  pass
              for f in filepaths:
                if f == "_link":
                  continue
                shutil.copy2("%s/%s"%(pfx, f), branchPkg.obsDir())
              if not options.dry_run:
                try:
                  branchPkg.commit('Automatic update by Merge-O-Matic')
                  #branchPkg.submitMergeRequest(d.obsProject(our_dist, our_component), diff)
                except urllib2.HTTPError:
                  logging.exception("Failed to commit %s", branchPkg)

if __name__ == "__main__":
    run(main, options, usage="%prog [DISTRO...]",
        description="commit merged packages to our repository")
