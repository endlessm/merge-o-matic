#!/usr/bin/env python
# -*- coding: utf-8 -*-
# produce-merges.py - produce merged packages
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

from __future__ import with_statement

import os
import re
import time
import logging
import subprocess
import tempfile

import config
from deb.controlfile import ControlFile
from deb.version import Version
from generate_patches import generate_patch
from merge_report import (MergeResult, MergeReport, read_report, write_report)
from model.base import (PackageVersion, Package, UpdateInfo)
import model.error
from momlib import *
from momversion import VERSION
from util import tree, shell, run
from util.debtreemerger import DebTreeMerger

logger = logging.getLogger('produce_merges')


class NoBase(Exception):
    pass


def options(parser):
    parser.add_option("-D", "--source-distro", type="string", metavar="DISTRO",
                      default=None,
                      help="Source distribution")
    parser.add_option("-S", "--source-suite", type="string", metavar="SUITE",
                      default=None,
                      help="Source suite (aka distrorelease)")

    parser.add_option("-t", "--target", type="string", metavar="TARGET",
                      default=None,
                      help="Distribution target to use")

    parser.add_option("-V", "--version", type="string", metavar="VER",
                      help="Version to obtain from destination")

    parser.add_option("-X", "--exclude", type="string", metavar="FILENAME",
                      action="append",
                      help="Exclude packages listed in this file")
    parser.add_option("-I", "--include", type="string", metavar="FILENAME",
                      action="append",
                      help="Only process packages listed in this file")


# Handle the merge of a specific package, returning the new merge report,
# or None if there was already a merge report that is still valid.
def handle_package(options, output_dir, target, pkg, our_version):
    update_info = UpdateInfo(pkg)

    if update_info.version is None:
        logger.error('UpdateInfo version %s does not match our version %s"',
                     update_info.version, our_version)
        report = MergeReport(left=our_version)
        report.target = target.name
        report.result = MergeResult.FAILED
        report.message = 'Could not find update info for version %s' % \
            our_version
        return report

    if update_info.upstream_version is None \
            or our_version.version >= update_info.upstream_version:
        logger.debug("No updated upstream version available for %s",
                     our_version)
        cleanup(output_dir)
        report = MergeReport(left=our_version)
        report.target = target.name
        report.result = MergeResult.KEEP_OURS
        report.merged_version = our_version.version
        return report

    if update_info.base_version is None:
        logger.info("No base version available for %s", our_version)
        cleanup(output_dir)
        report = MergeReport(left=our_version)
        report.target = target.name
        report.result = MergeResult.NO_BASE
        return report

    upstream = target.findSourcePackage(pkg.name, update_info.upstream_version)
    if not upstream:
        logger.error('Could not find upstream version %s in pool',
                     update_info.upstream_version)
        cleanup(output_dir)
        report = MergeReport(left=our_version)
        report.target = target.name
        report.result = MergeResult.FAILED
        report.message = 'Could not find upstream version %s in pool' % \
            update_info.upstream_version
        return report

    upstream = upstream[0]
    base = None
    pool_versions = target.getAllPoolVersions(pkg.name)
    for pv in pool_versions:
        if pv.version == update_info.base_version:
            base = pv

    if base is None:
        logger.error('Could not find base version %s in pool',
                     update_info.base_version)
        cleanup(output_dir)
        report = MergeReport(left=our_version)
        report.target = target.name
        report.result = MergeResult.FAILED
        report.message = 'Could not find base version %s in pool' % \
            update_info.base_version
        return report

    try:
        report = read_report(output_dir)
        # See if sync_upstream_packages already set
        if not options.force and \
                pkg.name in target.sync_upstream_packages and \
                Version(report['right_version']) == upstream.version and \
                Version(report['left_version']) == our_version.version and \
                Version(report['merged_version']) == upstream.version and \
                report['result'] == MergeResult.SYNC_THEIRS:
            logger.info("sync to upstream for %s [ours=%s, theirs=%s] "
                        "already produced, skipping run", pkg,
                        our_version.version, upstream.version)
            return None
        elif (not options.force and
              Version(report['right_version']) == upstream.version and
              Version(report['left_version']) == our_version.version and
              # we'll retry the merge if there was an unexpected
              # failure, a missing base or an unknown result last time
              report['result'] in (MergeResult.KEEP_OURS,
                                   MergeResult.SYNC_THEIRS, MergeResult.MERGED,
                                   MergeResult.CONFLICTS)):
            logger.info("merge for %s [ours=%s, theirs=%s] already produced, "
                        "skipping run",
                        pkg, our_version.version, upstream.version)
            return None
    except (AttributeError, ValueError, KeyError):
        pass

    if pkg.name in target.sync_upstream_packages:
        logger.info("Syncing to %s per sync_upstream_packages", upstream)
        cleanup(output_dir)
        report = MergeReport(left=our_version, right=upstream)
        report.target = target.name
        report.result = MergeResult.SYNC_THEIRS
        report.merged_version = upstream.version
        report.message = "Using version in upstream distro per " \
            "sync_upstream_packages configuration"
        return report

    logger.info("local: %s, upstream: %s", our_version, upstream)

    try:
        return produce_merge(target, base, our_version, upstream, output_dir)
    except ValueError as e:
        logger.exception("Could not produce merge, "
                         "perhaps %s changed components upstream?", pkg)
        report = MergeReport(left=our_version, right=upstream)
        report.target = target.name
        report.result = MergeResult.FAILED
        report.message = 'Could not produce merge: %s' % e
        return report


def main(options, args):
    logger.info('Producing merges...')

    excludes = []
    if options.exclude is not None:
        for filename in options.exclude:
            logger.info('excluding packages from %s', filename)
            excludes.extend(read_package_list(filename))

    includes = []
    if options.include is not None:
        for filename in options.include:
            logger.info('including packages from %s', filename)
            includes.extend(read_package_list(filename))

    # For each package in the destination distribution, locate the latest in
    # the source distribution; calculate the base from the destination and
    # produce a merge combining both sets of changes
    for target in config.targets(args):
        logger.info('considering target %s', target)
        our_dist = target.dist
        our_component = target.component
        d = target.distro
        for pkg in d.packages(target.dist, target.component):
            if options.package is not None and pkg.name not in options.package:
                continue
            if len(includes) and pkg.name not in includes:
                logger.info('skipping package %s: not in include list',
                            pkg.name)
                continue
            if len(excludes) and pkg.name in excludes:
                logger.info('skipping package %s: in exclude list', pkg.name)
                continue
            if pkg.name in target.blacklist:
                logger.info("%s is blacklisted, skipping", pkg.name)
                continue
            logger.info('considering package %s', pkg.name)
            if options.version:
                our_version = PackageVersion(pkg, Version(options.version))
                logger.debug('our version: %s (from command line)',
                             our_version)
            else:
                our_version = pkg.newestVersion()
                logger.debug('our version: %s', our_version)

            output_dir = result_dir(target.name, pkg.name)
            try:
                report = handle_package(options, output_dir, target, pkg,
                                        our_version)
                if report is not None:
                    report.write_report(output_dir)
            except Exception:
                logging.exception('Failed handling merge for %s', pkg)


def is_build_metadata_changed(left_source, right_source):
    """Return true if the two sources have different build-time metadata."""
    for field in ["Binary", "Architecture", "Build-Depends",
                  "Build-Depends-Indep", "Build-Conflicts",
                  "Build-Conflicts-Indep"]:
        if field in left_source and field not in right_source:
            return True
        if field not in left_source and field in right_source:
            return True
        if field in left_source and field in right_source \
                and left_source[field] != right_source[field]:
            return True

    return False


def add_changelog(package, merged_version, left_distro, left_dist,
                  right_distro, right_dist, merged_dir):
    """Add a changelog entry to the package."""
    changelog_file = "%s/debian/changelog" % merged_dir

    with open(changelog_file) as changelog:
        with open(changelog_file + ".new", "w") as new_changelog:
            print >>new_changelog, ("%s (%s) UNRELEASED; urgency=low"
                                    % (package, merged_version))
            print >>new_changelog
            print >>new_changelog, "  * Merge from %s %s." % (
                right_distro.title(), right_dist)
            print >>new_changelog
            print >>new_changelog, (" -- %s <%s>  " % (
                config.get('MOM_NAME'),
                config.get('MOM_EMAIL'))
                    + time.strftime("%a, %d %b %Y %H:%M:%S %z"))
            print >>new_changelog
            for line in changelog:
                print >>new_changelog, line.rstrip("\r\n")

    os.rename(changelog_file + ".new", changelog_file)


def copy_in(output_dir, pkgver):
    """Make a copy of the source files."""

    pkg = pkgver.package

    for md5sum, size, name in files(pkgver.getDscContents()):
        src = "%s/%s" % (pkg.poolPath, name)
        dest = "%s/%s" % (output_dir, name)
        if os.path.isfile(dest):
            os.unlink(dest)
        try:
            logger.debug("%s -> %s", src, dest)
            os.link(src, dest)
        except OSError, e:
            logger.exception("File not found: %s", src)

    patch = patch_file(pkg.distro, pkgver)
    if os.path.isfile(patch):
        output = "%s/%s" % (output_dir, os.path.basename(patch))
        if not os.path.exists(output):
            os.link(patch, output)
        return os.path.basename(patch)
    else:
        return None


def create_tarball(package, version, output_dir, merged_dir):
    """Create a tarball of a merge with conflicts."""
    filename = "%s/%s_%s.src.tar.gz" % (output_dir, package,
                                        version.without_epoch)
    contained = "%s-%s" % (package, version.without_epoch)

    tree.ensure("%s/tmp/" % config.get('ROOT'))
    parent = tempfile.mkdtemp(dir="%s/tmp/" % config.get('ROOT'))
    try:
        tree.copytree(merged_dir, "%s/%s" % (parent, contained))

        debian_rules = "%s/%s/debian/rules" % (parent, contained)
        if os.path.isfile(debian_rules):
            os.chmod(debian_rules, os.stat(debian_rules).st_mode | 0111)

        shell.run(("tar", "czf", filename, contained), chdir=parent)

        logger.info("Created %s", tree.subdir(config.get('ROOT'), filename))
        return os.path.basename(filename)
    finally:
        tree.remove(parent)


def create_source(package, version, since, output_dir, merged_dir):
    """Create a source package without conflicts."""
    contained = "%s-%s" % (package, version.upstream)
    dsc_filename = "%s_%s.dsc" % (package, version.without_epoch)

    tree.ensure("%s/tmp/" % config.get('ROOT'))
    parent = tempfile.mkdtemp(dir="%s/tmp/" % config.get('ROOT'))
    try:
        tree.copytree(merged_dir, "%s/%s" % (parent, contained))

        match = '%s_%s.orig(-\w+)?.tar.(gz|bz2|xz)$' \
                % (re.escape(package), re.escape(version.upstream))
        for filename in os.listdir(output_dir):
            if re.match(match, filename) is None:
                continue
            path = os.path.join(output_dir, filename)
            if os.path.isfile(path):
                os.link(path,
                        "%s/%s" % (parent, filename))

        cmd = ("dpkg-source",)
        if version.revision is not None and since.upstream != version.upstream:
            cmd += ("-sa",)
        cmd += ("-b", contained)

        try:
            dpkg_source_output = subprocess.check_output(
                cmd, cwd=parent, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError, e:
            logger.warning("dpkg-source failed with code %d:\n%s\n",
                           e.returncode, e.output)
            # for the message in the JSON report, just take the last line
            # and hope it's relevant...
            lastline = re.sub(r'.*\n', '', e.output.rstrip('\n'),
                              flags=re.DOTALL)
            return (MergeResult.FAILED,
                    "unable to build merged source package: "
                    "dpkg-source failed with %d (%s)" % (e.returncode,
                                                         lastline),
                    create_tarball(package, version, output_dir, merged_dir))
        else:
            logger.debug("dpkg-source succeeded:\n%s\n", dpkg_source_output)

        if os.path.isfile("%s/%s" % (parent, dsc_filename)):
            logger.info("Created dpkg-source %s", dsc_filename)
            for name in os.listdir(parent):
                src = "%s/%s" % (parent, name)
                dest = "%s/%s" % (output_dir, name)
                if os.path.isfile(src) and not os.path.isfile(dest):
                    os.link(src, dest)

            return (MergeResult.MERGED, None, os.path.basename(dsc_filename))
        else:
            message = ("dpkg-source did not produce expected filename %s" %
                       tree.subdir(config.get('ROOT'), dsc_filename))
            logger.warning("%s", message)
            return (MergeResult.FAILED,
                    "unable to build merged source package (%s)" % message,
                    create_tarball(package, version, output_dir, merged_dir))
    finally:
        tree.remove(parent)


def create_patch(version, filename, merged_dir, basis, basis_dir):
    """Create the merged patch."""

    parent = tempfile.mkdtemp()
    try:
        tree.copytree(merged_dir, "%s/%s" % (parent, version))
        tree.copytree(basis_dir, "%s/%s" % (parent, basis.version))

        with open(filename, "w") as diff:
            shell.run(("diff", "-pruN",
                       str(basis.version), str(version)),
                      chdir=parent, stdout=diff, okstatus=(0, 1, 2))
            logger.info("Created %s",
                        tree.subdir(config.get('ROOT'), filename))

        return os.path.basename(filename)
    finally:
        tree.remove(parent)


def read_package_list(filename):
    """Read a list of packages from the given file."""
    packages = []

    with open(filename) as list_file:
        for line in list_file:
            if line.startswith("#"):
                continue

            package = line.strip()
            if len(package):
                packages.append(package)

    return packages


def save_changelog(output_dir, cl_versions, pv, bases, limit=None):
    fh = None
    name = None
    n = 0

    for (v, text) in cl_versions:
        n += 1

        if v in bases:
            break

        if limit is not None and n > limit:
            break

        if fh is None:
            name = '%s_changelog.txt' % pv.version
            path = '%s/%s' % (output_dir, name)
            tree.ensure(path)
            fh = open(path, 'w')

        fh.write(text + '\n')

    if fh is not None:
        fh.close()

    return name


def produce_merge(target, base, left, upstream, output_dir):
    left_dir = unpack_source(left)
    upstream_dir = unpack_source(upstream)
    base_dir = unpack_source(base)

    report = MergeReport(left=left, right=upstream)
    report.target = target.name
    report.mom_version = str(VERSION)
    report.merge_date = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

    cleanup(output_dir)

    downstream_versions = read_changelog(left_dir + '/debian/changelog')
    upstream_versions = read_changelog(upstream_dir + '/debian/changelog')

    report.left_changelog = save_changelog(output_dir, downstream_versions,
                                           left, [base.version])

    # If the base is a common ancestor, log everything from the ancestor
    # to the current version. Otherwise just log the first entry.
    limit = 1
    for upstream_version, text in upstream_versions:
        if upstream_version == base.version:
            limit = None
            break
    report.right_changelog = save_changelog(output_dir, upstream_versions,
                                            upstream, [base.version], limit)

    report.set_base(base)
    logger.info('base version: %s', base.version)

    generate_patch(base, left.package.distro, left, slipped=False, force=False,
                   unpacked=True)
    generate_patch(base, upstream.package.distro, upstream, slipped=False,
                   force=False, unpacked=True)

    report.merged_version = Version(str(upstream.version) +
                                    config.get('LOCAL_SUFFIX') + '1')

    if base >= upstream:
        logger.info("Nothing to be done: %s >= %s", base, upstream)
        report.result = MergeResult.KEEP_OURS
        report.merged_version = left.version
        report.write_report(output_dir)
        return report

    # Careful: MergeReport.merged_dir is the output directory for the .dsc or
    # tarball, whereas our local variable merged_dir (below) is a temporary
    # directory containing unpacked source code. Don't mix them up.
    report.merged_dir = output_dir

    if base.version == left.version:
        logger.info("Syncing %s to %s", left, upstream)
        if not os.path.isdir(output_dir):
                os.makedirs(output_dir)

        report.result = MergeResult.SYNC_THEIRS
        report.build_metadata_changed = False
        report.right_patch = copy_in(output_dir, upstream)
        report.merged_version = upstream.version
        report.merged_patch = report.right_patch
        report.merged_files = report.right_files

        write_report(report, left=left, base=base, right=upstream,
                     src_file=None,
                     # this is MergeReport.merged_dir...
                     output_dir=output_dir,
                     # ... and for a SYNC_THEIRS merge, we don't need to look
                     # at the unpacked source code
                     merged_dir=None)
        return report

    merged_dir = work_dir(left.package.name, report.merged_version)

    logger.info("Merging %s..%s onto %s", upstream, base, left)

    try:
        merger = DebTreeMerger(left_dir, left.package.name,
                               left.getDscContents()['Format'],
                               left.package.distro.name,
                               upstream_dir, upstream.package.name,
                               upstream.getDscContents()['Format'],
                               upstream.package.distro.name,
                               base_dir, merged_dir)
        merger.run()
    except Exception as e:
        cleanup(merged_dir)
        logger.exception("Could not merge %s, probably bad files?", left)
        report.result = MergeResult.FAILED
        report.message = '%s: %s' % (e.__class__.__name__, e)
        report.write_report(output_dir)
        return report

    report.notes.extend(merger.notes)

    if len(merger.conflicts) == 0 and merger.total_changes_made == 1 \
            and len(merger.modified_files) == 1 \
            and 'debian/changelog' in merger.modified_files:
        # Sync to upstream if the only remaining change is in the changelog
        logger.info("Syncing %s to %s since only changes are in changelog",
                    left, upstream)
        if not os.path.isdir(output_dir):
            os.makedirs(output_dir)

        report.result = MergeResult.SYNC_THEIRS
        report.build_metadata_changed = False
        report.right_patch = copy_in(output_dir, upstream)
        report.merged_version = upstream.version
        report.merged_patch = report.right_patch
        report.merged_files = report.right_files
        report.notes.append('Synced to upstream version because the '
                            'changelog was the only modified file')

        write_report(report, left=left, base=base, right=upstream,
                     src_file=None,
                     # this is MergeReport.merged_dir...
                     output_dir=output_dir,
                     # ... and for a SYNC_THEIRS merge, we don't need to
                     # look at the unpacked source code
                     merged_dir=None)

        cleanup(merged_dir)
        cleanup_source(upstream)
        cleanup_source(base)
        cleanup_source(left)

        return report

    if 'debian/changelog' not in merger.conflicts:
        try:
            add_changelog(left.package.name, report.merged_version,
                          left.package.distro.name, left.package.dist,
                          upstream.package.distro.name, upstream.package.dist,
                          merged_dir)
        except IOError as e:
            logger.exception("Could not update changelog for %s!", left)
            report.result = MergeResult.FAILED
            report.message = 'Could not update changelog: %s' % e
            report.write_report(output_dir)
            return report

    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)
    copy_in(output_dir, base)
    report.left_patch = copy_in(output_dir, left)
    report.right_patch = copy_in(output_dir, upstream)
    report.build_metadata_changed = False
    report.merged_dir = output_dir

    if len(merger.conflicts):
        src_file = create_tarball(left.package.name, report.merged_version,
                                  output_dir, merged_dir)
        report.result = MergeResult.CONFLICTS
        report.conflicts = sorted(merger.conflicts)
        report.merge_failure_tarball = src_file
        report.merged_dir = None
    else:
        result, message, src_file = create_source(
            left.package.name, report.merged_version, left.version,
            output_dir, merged_dir)
        report.result = result

        if result == MergeResult.MERGED:
            assert src_file.endswith('.dsc'), src_file
            dsc = ControlFile("%s/%s" % (output_dir, src_file),
                              signed=True).para
            report.build_metadata_changed = is_build_metadata_changed(
                left.getDscContents(), dsc)
            report.merged_files = [src_file] + [f[2] for f in files(dsc)]
            report.merged_patch = create_patch(
                report.merged_version,
                "%s/%s_%s_from-theirs.patch" % (output_dir, left.package.name,
                                                report.merged_version),
                merged_dir, upstream, upstream_dir)
            report.proposed_patch = create_patch(
                report.merged_version,
                "%s/%s_%s_from-ours.patch" % (output_dir, left.package.name,
                                              report.merged_version),
                merged_dir, left, left_dir)
        else:
            report.result = result
            report.message = message
            report.merged_dir = ""
            report.merge_failure_tarball = src_file

    write_report(report, left, base, upstream, src_file=src_file,
                 output_dir=output_dir, merged_dir=merged_dir)
    logger.info("Wrote output to %s", src_file)
    cleanup(merged_dir)
    cleanup_source(upstream)
    cleanup_source(base)
    cleanup_source(left)
    return report


if __name__ == "__main__":
    run(main, options, usage="%prog",
        description="produce merged packages")
