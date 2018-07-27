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

import logging
import urllib2
import xml.etree.cElementTree

from momlib import *
import config
from deb.version import Version
from merge_report import (read_report, MergeResult)
from model import Distro, OBSDistro
from util import run
from util.tree import subdir

logger = logging.getLogger('commit_merges')

def options(parser):
    parser.add_option("-t", "--target", type="string", metavar="TARGET",
                      default=None,
                      help="Distribution target to publish")
    parser.add_option("-d", "--dry-run", action="store_true", help="Don't actually fiddle with OBS, just print what would've happened.")
    parser.add_option("-f", "--force", action="store_true",
                      help="Force creation of commits")

def main(options, args):
    logger.debug('Committing merges...')

    for target in config.targets(args):
      d = target.distro

      if not isinstance(d, OBSDistro):
        logger.debug('Skipping %r distro %r: not an OBSDistro', target, d)
        continue

      for package in d.packages(target.dist, target.component):
        if options.package and package.name not in options.package:
          logger.debug('Skipping package %s: not selected', package.name)
          continue

        if package.name in target.blacklist:
          logger.debug('Skipping package %s: blacklisted', package.name)
          continue

        try:
          output_dir = result_dir(target.name, package.name)
          report = read_report(output_dir)
        except ValueError:
          logger.debug('Skipping package %s: unable to read report',
                       package.name)
          continue

        if report['committed']:
          if options.force:
            logger.info("Forcing commit of %s", package)
          else:
            logger.debug("%s already committed, skipping!", package)
            continue

        if report['result'] not in (MergeResult.MERGED,
                MergeResult.SYNC_THEIRS):
            logger.debug("%s has nothing to commit: result=%s",
                    package, report['result'])
            continue

        filepaths = report['merged_files']
        if filepaths == []:
            logger.warning("Empty merged file list in %s/REPORT" % output_dir)
            continue

        if 'MOM_TEST' in os.environ:
          continue

        if target.committable:
          # we can commit directly to the target distribution
          # FIXME: is this still a supported configuration? I wouldn't
          # want to commit automated merges without some sort of manual
          # check on the debdiff...
          logger.info("Committing changes to %s", package)
          if not options.dry_run:
            try:
              package.commit('Automatic update by Merge-O-Matic')
            except urllib2.HTTPError as e:
              logger.exception('Failed to commit %s: HTTP error %s at <%s>:',
                  package, e.code, e.geturl())
              update_report(report, output_dir, False,
                  "HTTP error %s" % e.code)
            except Exception as e:
              logger.exception('Failed to commit %s:', package)
              # deliberately rather vague, as below
              update_report(report, output_dir, False,
                  "%s" % e.__class__.__name__)
            else:
              update_report(report, output_dir, True,
                      committed_to=d.obsProject(target.dist, target.component))
          continue

        # else we need to branch it and commit to the branch
        try:
          logger.debug("Branching %s", package)

          branchPkg = package.branch("home:%s:branches"%(d.obsUser))

          branch = branchPkg.distro
          branch.sync(target.dist, target.component, [branchPkg,])
          logger.info("Committing changes to %s, and submitting merge request to %s", branchPkg, package)
          if report['result'] == MergeResult.SYNC_THEIRS:
            srcDistro = Distro.get(report['right_distro'])

            version = Version(report['right_version'])

            logger.debug('Copying updated upstream version %s from %r into %r',
                    version,
                    srcDistro,
                    target)
            for upstream in target.getSourceLists(package.name):
              for src in upstream:
                srcDistro = src.distro
                try:
                  pkg = srcDistro.findPackage(package.name, searchDist=src.dist,
                      version=version)[0]
                  pfx = pkg.poolPath
                  break
                except model.error.PackageNotFound:
                  pass
          else:
            logger.debug('Copying merged version from %r into %r',
                    branch, target)
            pfx = result_dir(target.name, package.name)

          # this might raise an error
          obsFiles = branchPkg.getOBSFiles()

          # Get the linked target files since the checkout is expanded
          # and may contain them
          linkedFiles = package.getOBSFiles()

          for f in obsFiles:
            if f.endswith(".dsc"):
              oldDsc = '%s/%s'%(branchPkg.obsDir(), f)
              break
          for f in filepaths:
            if f.endswith(".dsc"):
              newDsc = '%s/%s'%(pfx, f)
              break

          #logger.debug("Running debdiff on %s and %s", oldDsc, newDsc)
          #comment = shell.get(("debdiff", oldDsc, newDsc), okstatus=(0,1))
          # FIXME: Debdiff needs implemented in OBS, as large merge descriptions break clucene.
          comment = ''
          if report['result'] == MergeResult.SYNC_THEIRS:
            comment += 'Sync to '
          elif report['result'] == MergeResult.MERGED:
            comment += 'Merge with '
          comment += 'version %s from %s %s' %(report['right_version'],
                                               report['right_distro'],
                                               report['right_suite'])
          comment += "\n\nMerge report is available at %s"%('/'.join((config.get('MOM_URL'), subdir(config.get('ROOT'), output_dir), 'REPORT.html')))

          if report['notes']:
            comment += '\n\nMerge notes:'
            for note in report['notes']:
              comment += '\n - %s' % note

          # The newlines seem to cause create_submit_request to send
          # UTF-32 over the wire, which OBS promptly chokes on. Encode
          # the message to UTF-8 first.
          comment = comment.encode('utf-8')
          if not options.dry_run:
            filesUpdated = False
            for f in obsFiles + linkedFiles:
              if f == "_link":
                continue
              try:
                logger.debug('deleting %s/%s', branchPkg.obsDir(), f)
                os.unlink('%s/%s'%(branchPkg.obsDir(), f))
                filesUpdated = True
              except OSError:
                pass
            for f in filepaths:
              if f == "_link":
                continue
              logger.debug('copying %s/%s -> %s', pfx, f, branchPkg.obsDir())
              shutil.copy2("%s/%s"%(pfx, f), branchPkg.obsDir())
              filesUpdated = True
            if filesUpdated:
              logger.debug('Submitting request to merge %r from %r into %r',
                      branchPkg, branch, target)
              try:
                branchPkg.commit('Automatic update by Merge-O-Matic')
                obs_project = d.obsProject(target.dist, target.component)
                reqid = branchPkg.submitMergeRequest(obs_project, comment)
                update_report(report, output_dir, True,
                        committed_to=obs_project,
                        request_url=branchPkg.webMergeRequest(reqid))
              except xml.etree.cElementTree.ParseError:
                logger.exception("Failed to commit %s", branchPkg)
                update_report(report, output_dir, False, "OBS API Error")
              except urllib2.HTTPError as e:
                logger.exception("Failed to commit %s: HTTP error %s at <%s>:",
                    branchPkg, e.code, e.geturl())
                update_report(report, output_dir, False,
                    "HTTP error %s" % e.code)
              except Exception as e:
                logger.exception("Failed to commit %s", branchPkg)
                # deliberately being a bit vague here in case the exact
                # exception leaks internal info
                update_report(report, output_dir, False,
                    "%s" % e.__class__.__name__)
          else:
            logger.info("Not committing, due to --dry-run")

        except urllib2.HTTPError as e:
          logger.exception('Failed to branch %s: HTTP error %s at <%s>:',
              package, e.code, e.geturl())
          update_report(report, output_dir, False,
              "Failed to branch: HTTP error %s" % e.code)

        except Exception as e:
          logger.exception('Failed to branch %s:', package)
          # deliberately being a bit vague here in case the exact
          # exception leaks internal info
          update_report(report, output_dir, False,
              "Failed to branch: %s" % e.__class__.__name__)

def update_report(report, output_dir, committed, message=None,
        request_url=None, committed_to=None):
  report.committed = committed
  report.commit_detail = message
  report.obs_request_url = request_url
  report.committed_to = committed_to
  report.write_report(output_dir)

  with open("%s/REPORT" % output_dir, "a") as r:
    print >>r
    if committed:
      print >>r, "Merge committed: YES"
      if request_url is not None:
        print >>r, "OBS merge request: %s" % request_url
    else:
      if message is not None:
        print >>r, "Merge committed: NO (%s)"%(message)
      else:
        print >>r, "Merge committed: NO"

if __name__ == "__main__":
    run(main, options, usage="%prog [DISTRO...]",
        description="commit merged packages to our repository")
