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
from util import run
from util.tree import subdir
import xml.etree.cElementTree

def options(parser):
    parser.add_option("-t", "--target", type="string", metavar="TARGET",
                      default=None,
                      help="Distribution target to publish")
    parser.add_option("-d", "--dry-run", action="store_true", help="Don't actually fiddle with OBS, just print what would've happened.")

def main(options, args):
    logging.debug('Committing merges...')

    for target in config.targets(args):
      d = target.distro

      if not isinstance(d, OBSDistro):
        logging.debug('Skipping %r distro %r: not an OBSDistro', target, d)
        continue

      for source in d.newestSources(target.dist, target.component):
        if options.package and source['Package'] not in options.package:
          logging.debug('Skipping package %s: not selected', source['Package'])
          continue

        if source['Package'] in target.blacklist:
          logging.debug('Skipping package %s: blacklisted', source['Package'])
          continue

        try:
          output_dir = result_dir(target.name, source['Package'])
          report = read_report(output_dir)
        except ValueError:
          logging.debug('Skipping package %s: unable to read report',
                  source['Package'])
          continue

        package = d.package(target.dist, target.component, report['package'])

        if report['committed']:
          logging.debug("%s already committed, skipping!", package)
          continue

        filepaths = report['merged_files']
        if filepaths == []:
            logging.warning("Empty merged file list in %s/REPORT" % output_dir)
            continue

        if target.committable:
          logging.info("Committing changes to %s", package)
          if not options.dry_run:
            try:
              package.commit('Automatic update by Merge-O-Matic')
              pass
            except urllib2.HTTPError:
              logging.exception("Failed to commit %s", package)
        else:
          logging.debug("Branching %s", package)
          branchPkg = package.branch("home:%s:branches"%(d.obsUser))
          branch = branchPkg.distro
          branch.sync(target.dist, target.component, [branchPkg,])
          logging.info("Committing changes to %s, and submitting merge request to %s", branchPkg, package)
          if report['merged_is_right']:
            logging.debug('Copying updated upstream version %s from %r into %r',
                    package.newestVersion(),
                    srcDistro,
                    target)
            srcDistro = Distro.get(report['right_distro'])
            for upstream in target.sources:
              for src in upstream:
                srcDistro = src.distro
                try:
                  pkg = srcDistro.findPackage(package.name, searchDist=src.dist,
                      version=package.newestVersion().version)[0]
                  pfx = pkg.poolDirectory()
                  break
                except model.error.PackageNotFound:
                  pass
          else:
            logging.debug('Copying merged version from %r into %r',
                    branch, target)
            pfx = result_dir(target.name, package.name)

          for f in branchPkg.files:
            if f.endswith(".dsc"):
              oldDsc = '%s/%s'%(branchPkg.obsDir(), f)
              break
          for f in filepaths:
            if f.endswith(".dsc"):
              newDsc = '%s/%s'%(pfx, f)
              break

          #logging.debug("Running debdiff on %s and %s", oldDsc, newDsc)
          #comment = shell.get(("debdiff", oldDsc, newDsc), okstatus=(0,1))
          # FIXME: Debdiff needs implemented in OBS, as large merge descriptions break clucene.
          comment = "Merge report is available at %s"%('/'.join((config.get('MOM_URL'), subdir(config.get('ROOT'), output_dir), 'REPORT')))
          if not options.dry_run:
            filesUpdated = False
            for f in branchPkg.files:
              if f == "_link":
                continue
              try:
                logging.debug('deleting %s/%s', branchPkg.obsDir(), f)
                os.unlink('%s/%s'%(branchPkg.obsDir(), f))
                filesUpdated = True
              except OSError:
                pass
            for f in filepaths:
              if f == "_link":
                continue
              logging.debug('copying %s/%s -> %s', pfx, f, branchPkg.obsDir())
              shutil.copy2("%s/%s"%(pfx, f), branchPkg.obsDir())
              filesUpdated = True
            if filesUpdated:
              logging.debug('Submitting request to merge %r from %r into %r',
                      branchPkg, branch, target)
              try:
                branchPkg.commit('Automatic update by Merge-O-Matic')
                branchPkg.submitMergeRequest(d.obsProject(target.dist, target.component), comment)
                update_report(output_dir, True)
              except xml.etree.cElementTree.ParseError:
                logging.exception("Failed to commit %s", branchPkg)
                update_report(output_dir, False, "OBS API Error")
              except urllib2.HTTPError:
                logging.exception("Failed to commit %s", branchPkg)
                update_report(output_dir, False, "http error")
          else:
            logging.info("Not committing, due to --dry-run")

def update_report(output_dir, committed, message=None):
  with open("%s/REPORT" % output_dir, "a") as r:
    print >>r
    if committed:
      print >>r, "Merge committed: YES"
    else:
      if message is not None:
        print >>r, "Merge committed: NO (%s)"%(message)
      else:
        print >>r, "Merge committed: NO"

if __name__ == "__main__":
    run(main, options, usage="%prog [DISTRO...]",
        description="commit merged packages to our repository")
