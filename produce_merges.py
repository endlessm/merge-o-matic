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

from stat import *

from momlib import *
from deb.controlfile import ControlFile
from deb.version import Version
from generate_patches import generate_patch
from util import tree, shell, run
from merge_report import (MergeResult, MergeReport, read_report, write_report)
from model.base import (PackageVersion, Package)
from momversion import VERSION
import config
import model.error

# Regular expression for top of debian/changelog
CL_RE = re.compile(r'^(\w[-+0-9a-z.]*) \(([^\(\) \t]+)\)((\s+[-0-9a-z]+)+)\;',
                   re.IGNORECASE)

logger = logging.getLogger('produce_merges')

class NoBase(Exception):
    pass

def find_upstream(target, pkg, our_version):
  upstream = None

  for srclist in target.getSourceLists(pkg.name, include_unstable=False):
    for src in srclist:
      logger.debug('considering source %s', src)
      try:
        for possible in src.distro.findPackage(pkg.name, searchDist=src.dist):
          logger.debug('- contains version %s', possible)
          if upstream is None or possible > upstream:
            logger.debug('  - that version is the best yet seen')
            upstream = possible
      except model.error.PackageNotFound:
        pass

  # There are two situations in which we will look in unstable distros
  # for a better version:
  try_unstable = False

  # 1. If our version is newer than the stable upstream version, we
  #    assume that our version was sourced from unstable, so let's
  #    check for an update there.
  #    However we must use the base version for the comparison here,
  #    otherwise we would consider our version 1.0-1endless1 newer
  #    than the stable 1.0-1 and look in unstable for an update.
  if upstream is not None and our_version >= upstream:
    our_base_version = our_version.version.base()
    logger.info("our version %s >= their version %s, checking base version %s", our_version, upstream, our_base_version)
    if our_base_version > upstream.version:
      logger.info("base version still newer than their version, checking in unstable")
      try_unstable = True

  # 2. If we didn't find any upstream version at all, it's possible
  #    that it's a brand new package where our version was imported
  #    from unstable, so let's see if we can find a better version
  #    there.
  if upstream is None:
    try_unstable = True

  # However, if this package has been assigned a specific source,
  # we'll honour that.
  if target.packageHasSpecificSource(pkg.name):
    try_unstable = False

  if try_unstable:
    for srclist in target.unstable_sources:
      for src in srclist:
        logger.debug('considering unstable source %s', src)
        try:
          for possible in src.distro.findPackage(pkg.name,
                      searchDist=src.dist):
            logger.debug('- contains version %s', possible)
            if upstream is None or possible > upstream:
              logger.debug('  - that version is the best yet seen')
              upstream = possible
        except model.error.PackageNotFound:
          pass

  return upstream

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
            logger.debug('skipping package %s: not the selected package',
                         pkg.name)
            continue
          if len(includes) and pkg.name not in includes:
            logger.info('skipping package %s: not in include list', pkg.name)
            continue
          if len(excludes) and pkg.name in excludes:
            logger.info('skipping package %s: in exclude list', pkg.name)
            continue
          if pkg.name in target.blacklist:
            logger.info("%s is blacklisted, skipping", pkg.name)
            continue
          logger.info('considering package %s', pkg.name)
          if options.version:
            our_version = Version(options.version)
            logger.debug('our version: %s (from command line)', our_version)
          else:
            our_version = pkg.newestVersion()
            logger.debug('our version: %s', our_version)

          output_dir = result_dir(target.name, pkg.name)

          upstream = find_upstream(target, pkg, our_version)
          if upstream is None:
            logger.info("%s not available upstream, skipping", our_version)
            cleanup(output_dir)
            report = MergeReport(left=our_version)
            report.target = target.name
            report.result = MergeResult.KEEP_OURS
            report.merged_version = our_version.version
            report.write_report(output_dir)
            continue

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
                continue
            elif (not options.force and
                    Version(report['right_version']) == upstream.version and
                    Version(report['left_version']) == our_version.version and
                    # we'll retry the merge if there was an unexpected
                    # failure, a missing base or an unknown result last time
                    report['result'] in (MergeResult.KEEP_OURS,
                        MergeResult.SYNC_THEIRS, MergeResult.MERGED,
                        MergeResult.CONFLICTS)):
              logger.info("merge for %s [ours=%s, theirs=%s] already produced, skipping run", pkg, our_version.version, upstream.version)
              continue
          except (AttributeError, ValueError, KeyError):
            pass

          if our_version >= upstream:
            logger.info("our version %s >= their version %s, skipping",
                    our_version, upstream)
            cleanup(output_dir)
            report = MergeReport(left=our_version, right=upstream)
            report.target = target.name
            report.result = MergeResult.KEEP_OURS
            report.merged_version = our_version.version
            report.write_report(output_dir)
            continue
          elif our_version < upstream and \
               pkg.name in target.sync_upstream_packages:
            logger.info("Syncing to %s per sync_upstream_packages", upstream)
            cleanup(output_dir)
            report = MergeReport(left=our_version, right=upstream)
            report.target = target.name
            report.result = MergeResult.SYNC_THEIRS
            report.merged_version = upstream.version
            report.message = "Using version in upstream distro per " \
                             "sync_upstream_packages configuration"
            report.write_report(output_dir)
            continue

          logger.info("local: %s, upstream: %s", our_version, upstream)

          try:
            produce_merge(target, our_version, upstream, output_dir)
          except ValueError as e:
            logger.exception("Could not produce merge, perhaps %s changed components upstream?", pkg)
            report = MergeReport(left=our_version, right=upstream)
            report.target = target.name
            report.result = MergeResult.FAILED
            report.message = 'Could not produce merge: %s' % e
            report.write_report(output_dir)
            continue

def is_build_metadata_changed(left_source, right_source):
    """Return true if the two sources have different build-time metadata."""
    for field in ["Binary", "Architecture", "Build-Depends", "Build-Depends-Indep", "Build-Conflicts", "Build-Conflicts-Indep"]:
        if field in left_source and field not in right_source:
            return True
        if field not in left_source and field in right_source:
            return True
        if field in left_source and field in right_source and left_source[field] != right_source[field]:
            return True

    return False

class MergeData(object):
  def __init__(self):
    ### Changes made relative to the right version
    self.added_files = set()
    self.removed_files = set()
    self.modified_files = set()

    ### Unsolved problems

    # Files that generated conflicts when merging
    self.conflicts = set()

  @property
  def total_modifications(self):
    """Total number of modifications made relative to the right version"""
    return len(self.added_files) + len(self.removed_files) + \
           len(self.modified_files)

def do_merge(left_dir, left_name, left_format, left_distro, base_dir,
             right_dir, right_name, right_format, right_distro, merged_dir):
    """Do the heavy lifting of comparing and merging."""
    logger.debug("Producing merge in %s", merged_dir)
    result = MergeData()
    po_files = []

    both_formats_quilt = left_format == right_format == "3.0 (quilt)"
    if both_formats_quilt:
        logger.debug("Only merging debian directory since both "
                     "formats 3.0 (quilt)")

    # Look for files in the base and merge them if they're in both new
    # files (removed files get removed)
    for filename in tree.walk(base_dir):
        # If both packages are 3.0 (quilt), ignore everything except the
        # debian directory
        if both_formats_quilt and not tree.under("debian", filename):
            continue

        if tree.under(".pc", filename):
            # Not interested in merging quilt metadata
            continue

        base_stat = os.lstat("%s/%s" % (base_dir, filename))

        try:
            left_stat = os.lstat("%s/%s" % (left_dir, filename))
        except OSError:
            left_stat = None

        try:
            right_stat = os.lstat("%s/%s" % (right_dir, filename))
        except OSError:
            right_stat = None

        if left_stat is None and right_stat is None:
            # Removed on both sides
            pass

        elif left_stat is None:
            logger.debug("removed from %s: %s", left_distro, filename)
            if not same_file(base_stat, base_dir, right_stat, right_dir,
                             filename):
                # Changed on RHS
                result.conflicts.add(filename)
            else:
                result.removed_files.add(filename)

        elif right_stat is None:
            # Removed on RHS only
            logger.debug("removed from %s: %s", right_distro, filename)
            if not same_file(base_stat, base_dir, left_stat, left_dir,
                             filename):
                # Changed on LHS
                result.conflicts.add(filename)

        elif S_ISREG(left_stat.st_mode) and S_ISREG(right_stat.st_mode):
            # Common case: left and right are both files
            handle_file(left_stat, left_dir, left_name, left_distro,
                        right_dir, right_stat, right_name, right_distro,
                        base_stat, base_dir,
                        merged_dir, filename, po_files, result)

        elif same_file(left_stat, left_dir, right_stat, right_dir, filename):
            # left and right are the same, doesn't matter which we keep
            tree.copyfile("%s/%s" % (right_dir, filename),
                          "%s/%s" % (merged_dir, filename))

        elif same_file(base_stat, base_dir, left_stat, left_dir, filename):
            # right has changed in some way, keep that one
            logger.debug("preserving non-file change in %s: %s",
                          right_distro, filename)
            tree.copyfile("%s/%s" % (right_dir, filename),
                          "%s/%s" % (merged_dir, filename))

        elif same_file(base_stat, base_dir, right_stat, right_dir, filename):
            # left has changed in some way, keep that one
            logger.debug("preserving non-file change in %s: %s",
                          left_distro, filename)
            tree.copyfile("%s/%s" % (left_dir, filename),
                          "%s/%s" % (merged_dir, filename))
            result.modified_files.add(filename)
        else:
            # all three differ, mark a conflict
            result.conflicts.add(filename)

    # Look for files in the left hand side that aren't in the base,
    # conflict if new on both sides or copy into the tree
    for filename in tree.walk(left_dir):
        # If both packages are 3.0 (quilt), ignore everything except the
        # debian directory
        if both_formats_quilt and not tree.under("debian", filename):
            continue

        if tree.under(".pc", filename):
            # Not interested in merging quilt metadata
            continue

        if tree.exists("%s/%s" % (base_dir, filename)):
            continue

        if not tree.exists("%s/%s" % (right_dir, filename)):
            logger.debug("new in %s: %s", left_distro, filename)
            tree.copyfile("%s/%s" % (left_dir, filename),
                          "%s/%s" % (merged_dir, filename))
            result.added_files.add(filename)
            continue

        left_stat = os.lstat("%s/%s" % (left_dir, filename))
        right_stat = os.lstat("%s/%s" % (right_dir, filename))

        if S_ISREG(left_stat.st_mode) and S_ISREG(right_stat.st_mode):
            # Common case: left and right are both files
            handle_file(left_stat, left_dir, left_name, left_distro,
                        right_dir, right_stat, right_name, right_distro,
                        None, None, merged_dir, filename,
                        po_files, result)

        elif same_file(left_stat, left_dir, right_stat, right_dir, filename):
            # left and right are the same, doesn't matter which we keep
            tree.copyfile("%s/%s" % (right_dir, filename),
                          "%s/%s" % (merged_dir, filename))

        else:
            # they differ, mark a conflict
            result.conflicts.add(filename)

    # Copy new files on the right hand side only into the tree
    for filename in tree.walk(right_dir):
        if tree.under(".pc", filename):
            # Not interested in merging quilt metadata
            continue

        if both_formats_quilt and not tree.under("debian", filename):
            # Always copy right version for quilt non-debian files
            if not tree.exists("%s/%s" % (left_dir, filename)):
                logger.debug("new in %s: %s", right_distro, filename)
        else:
            if tree.exists("%s/%s" % (base_dir, filename)):
                continue

            if tree.exists("%s/%s" % (left_dir, filename)):
                continue

            logger.debug("new in %s: %s", right_distro, filename)

        tree.copyfile("%s/%s" % (right_dir, filename),
                      "%s/%s" % (merged_dir, filename))

    # Handle po files separately as they need special merging
    for filename in po_files:
        if not merge_po(left_dir, right_dir, merged_dir, filename):
            result.conflicts.add(filename)
            continue

        merge_attr(base_dir, left_dir, right_dir, merged_dir, filename, result)
        result.modified_files.add(filename)

    for conflict in result.conflicts:
        conflict_file(left_dir, left_distro, right_dir, right_distro,
                      merged_dir, conflict)

    return result

# Returns a tuple of two booleans:
# 1. conflicts: True if the merge attempt generated conflicts
# 2. deferred: True if we'll handle this file in a later stage
def merge_file_contents(left_stat, left_dir, left_name, left_distro,
                right_dir, right_stat, right_name, right_distro,
                base_stat, base_dir, merged_dir, filename, po_files):
    if filename == "debian/changelog":
        # two-way merge of changelogs
        try:
          merge_changelog(left_dir, right_dir, merged_dir, filename)
          return False, False
        except:
          return True, False
    elif filename.endswith(".po"):
        # two-way merge of po contents (do later)
        po_files.append(filename)
        return False, True
    elif filename.endswith(".pot"):
        # two-way merge of pot contents
        ret = merge_pot(left_dir, right_dir, merged_dir, filename)
        return not ret, False
    elif base_stat is not None and S_ISREG(base_stat.st_mode):
        # was file in base: diff3 possible
        ret = diff3_merge(left_dir, left_name, left_distro, base_dir,
                          right_dir, right_name, right_distro, merged_dir,
                          filename)
        return not ret, False
    else:
        # general file conflict
        return True, False

def handle_file(left_stat, left_dir, left_name, left_distro,
                right_dir, right_stat, right_name, right_distro,
                base_stat, base_dir, merged_dir, filename, po_files, result):
    """Handle the common case of a file in both left and right."""
    do_attrs = True

    if same_file(left_stat, left_dir, right_stat, right_dir, filename):
        # same file contents in left and right
        logger.debug("%s and %s both turned into same file: %s",
                      left_distro, right_distro, filename)
        tree.copyfile("%s/%s" % (left_dir, filename),
                      "%s/%s" % (merged_dir, filename))
    else:
        conflicts, deferred = \
            merge_file_contents(left_stat, left_dir, left_name, left_distro,
                                right_dir, right_stat, right_name,
                                right_distro, base_stat, base_dir,
                                merged_dir, filename, po_files)
        if conflicts:
            result.conflicts.add(filename)
            do_attrs = False

        if deferred:
            do_attrs = False
        else:
            result.modified_files.add(filename)

    # Merge file permissions
    if do_attrs:
        merge_attr(base_dir, left_dir, right_dir, merged_dir, filename, result)

def same_file(left_stat, left_dir, right_stat, right_dir, filename):
    """Are two filesystem objects the same?"""
    if S_IFMT(left_stat.st_mode) != S_IFMT(right_stat.st_mode):
        # Different fundamental types
        return False
    elif S_ISREG(left_stat.st_mode):
        # Files with the same size and MD5sum are the same
        if left_stat.st_size != right_stat.st_size:
            return False
        elif md5sum("%s/%s" % (left_dir, filename)) \
                 != md5sum("%s/%s" % (right_dir, filename)):
            return False
        else:
            return True
    elif S_ISDIR(left_stat.st_mode) or S_ISFIFO(left_stat.st_mode) \
             or S_ISSOCK(left_stat.st_mode):
        # Directories, fifos and sockets are always the same
        return True
    elif S_ISCHR(left_stat.st_mode) or S_ISBLK(left_stat.st_mode):
        # Char/block devices are the same if they have the same rdev
        if left_stat.st_rdev != right_stat.st_rdev:
            return False
        else:
            return True
    elif S_ISLNK(left_stat.st_mode):
        # Symbolic links are the same if they have the same target
        if os.readlink("%s/%s" % (left_dir, filename)) \
               != os.readlink("%s/%s" % (right_dir, filename)):
            return False
        else:
            return True
    else:
        return True


def merge_changelog(left_dir, right_dir, merged_dir, filename):
    """Merge a changelog file."""
    logger.debug("Knitting %s", filename)

    left_cl = read_changelog("%s/%s" % (left_dir, filename))
    right_cl = read_changelog("%s/%s" % (right_dir, filename))
    tree.ensure(filename)

    with open("%s/%s" % (merged_dir, filename), "w") as output:
        for right_ver, right_text in right_cl:
            while len(left_cl) and left_cl[0][0] > right_ver:
                (left_ver, left_text) = left_cl.pop(0)
                print >>output, left_text

            while len(left_cl) and left_cl[0][0] == right_ver:
                (left_ver, left_text) = left_cl.pop(0)

            print >>output, right_text

        for left_ver, left_text in left_cl:
            print >>output, left_text

    return False

def read_changelog(filename):
    """Return a parsed changelog file."""
    entries = []

    with open(filename) as cl:
        (ver, text) = (None, "")
        for line in cl:
            match = CL_RE.search(line)
            if match:
                try:
                    ver = Version(match.group(2))
                except ValueError:
                    ver = None

                text += line
            elif line.startswith(" -- "):
                if ver is None:
                    ver = Version("0")

                text += line
                entries.append((ver, text))
                (ver, text) = (None, "")
            elif len(line.strip()) or ver is not None:
                text += line

    if len(text):
        entries.append((ver, text))

    return entries


def merge_po(left_dir, right_dir, merged_dir, filename):
    """Update a .po file using msgcat or msgmerge."""
    merged_po = "%s/%s" % (merged_dir, filename)
    closest_pot = find_closest_pot(merged_po)
    if closest_pot is None:
        return merge_pot(left_dir, right_dir, merged_dir, filename)

    left_po = "%s/%s" % (left_dir, filename)
    right_po = "%s/%s" % (right_dir, filename)

    logger.debug("Merging PO file %s", filename)
    try:
        tree.ensure(merged_po)
        shell.run(("msgmerge", "--force-po", "-o", merged_po,
                   "-C", left_po, right_po, closest_pot))
    except (ValueError, OSError):
        logger.error("PO file merge failed: %s", filename)
        return False

    return True

def merge_pot(left_dir, right_dir, merged_dir, filename):
    """Update a .po file using msgcat."""
    merged_pot = "%s/%s" % (merged_dir, filename)

    left_pot = "%s/%s" % (left_dir, filename)
    right_pot = "%s/%s" % (right_dir, filename)

    logger.debug("Merging POT file %s", filename)
    try:
        tree.ensure(merged_pot)
        shell.run(("msgcat", "--force-po", "--use-first", "-o", merged_pot,
                   right_pot, left_pot))
    except (ValueError, OSError):
        logger.error("POT file merge failed: %s", filename)
        return False

    return True

def find_closest_pot(po_file):
    """Find the closest .pot file to the po file given."""
    dirname = os.path.dirname(po_file)
    for entry in os.listdir(dirname):
        if entry.endswith(".pot"):
            return os.path.join(dirname, entry)
    else:
        return None


def diff3_merge(left_dir, left_name, left_distro, base_dir,
                right_dir, right_name, right_distro, merged_dir, filename):
    """Merge a file using diff3."""
    dest = "%s/%s" % (merged_dir, filename)
    tree.ensure(dest)

    with open(dest, "w") as output:
        status = shell.run(("diff3", "-E", "-m",
                            "-L", left_name, "%s/%s" % (left_dir, filename),
                            "-L", "BASE", "%s/%s" % (base_dir, filename),
                            "-L", right_name, "%s/%s" % (right_dir, filename)),
                           stdout=output, okstatus=(0,1,2))

    if status != 0:
        if not tree.exists(dest) or os.stat(dest).st_size == 0:
            # Probably binary
            if same_file(os.stat("%s/%s" % (left_dir, filename)), left_dir,
                         os.stat("%s/%s" % (right_dir, filename)), right_dir,
                         filename):
                logger.debug("binary files are the same: %s", filename)
                tree.copyfile("%s/%s" % (left_dir, filename),
                              "%s/%s" % (merged_dir, filename))
            elif same_file(os.stat("%s/%s" % (base_dir, filename)), base_dir,
                           os.stat("%s/%s" % (left_dir, filename)), left_dir,
                           filename):
                logger.debug("preserving binary change in %s: %s",
                              right_distro, filename)
                tree.copyfile("%s/%s" % (right_dir, filename),
                              "%s/%s" % (merged_dir, filename))
            elif same_file(os.stat("%s/%s" % (base_dir, filename)), base_dir,
                           os.stat("%s/%s" % (right_dir, filename)), right_dir,
                           filename):
                logger.debug("preserving binary change in %s: %s",
                              left_distro, filename)
                tree.copyfile("%s/%s" % (left_dir, filename),
                              "%s/%s" % (merged_dir, filename))
            else:
                logger.debug("binary file conflict: %s", filename)
                return False
        else:
            logger.debug("Conflict in %s", filename)
            return False
    else:
        return True


def merge_attr(base_dir, left_dir, right_dir, merged_dir, filename, result):
    """Set initial and merge changed attributes."""
    if base_dir is not None \
           and os.path.isfile("%s/%s" % (base_dir, filename)) \
           and not os.path.islink("%s/%s" % (base_dir, filename)):
        set_attr(base_dir, merged_dir, filename)
        apply_attr(base_dir, left_dir, merged_dir, filename, result)
        apply_attr(base_dir, right_dir, merged_dir, filename, result)
    else:
        set_attr(right_dir, merged_dir, filename)
        apply_attr(right_dir, left_dir, merged_dir, filename, result)

def set_attr(src_dir, dest_dir, filename):
    """Set the initial attributes."""
    mode = os.stat("%s/%s" % (src_dir, filename)).st_mode & 0777
    os.chmod("%s/%s" % (dest_dir, filename), mode)

def apply_attr(base_dir, src_dir, dest_dir, filename, result):
    """Apply attribute changes from one side to a file."""
    src_stat = os.stat("%s/%s" % (src_dir, filename))
    base_stat = os.stat("%s/%s" % (base_dir, filename))
    changed = False

    for shift in range(0, 9):
        bit = 1 << shift

        # Permission bit added
        if not base_stat.st_mode & bit and src_stat.st_mode & bit:
            change_attr(dest_dir, filename, bit, shift, True)
            changed = True

        # Permission bit removed
        if base_stat.st_mode & bit and not src_stat.st_mode & bit:
            change_attr(dest_dir, filename, bit, shift, False)
            changed = True

    if changed:
        result.modified_files.add(filename)


def change_attr(dest_dir, filename, bit, shift, add):
    """Apply a single attribute change."""
    logger.debug("Setting %s %s", filename,
                  [ "u+r", "u+w", "u+x", "g+r", "g+w", "g+x",
                    "o+r", "o+w", "o+x" ][shift])

    dest = "%s/%s" % (dest_dir, filename)
    attr = os.stat(dest).st_mode & 0777
    if add:
        attr |= bit
    else:
        attr &= ~bit

    os.chmod(dest, attr)


def conflict_file(left_dir, left_distro, right_dir, right_distro,
                  dest_dir, filename):
    """Copy both files as conflicts of each other."""
    left_src = "%s/%s" % (left_dir, filename)
    right_src = "%s/%s" % (right_dir, filename)
    dest = "%s/%s" % (dest_dir, filename)

    logger.debug("Conflicted: %s", filename)
    tree.remove(dest)

    # We need to take care here .. if one of the items involved in a
    # conflict is a directory then it might have children and we don't want
    # to throw an error later.
    #
    # We get round this by making the directory a symlink to the conflicted
    # one.
    #
    # Fortunately this is so rare it may never happen!

    if tree.exists(left_src):
        tree.copyfile(left_src, "%s.%s" % (dest, left_distro.upper()))
    if os.path.isdir(left_src):
        os.symlink("%s.%s" % (os.path.basename(dest), left_distro.upper()),
                   dest)

    if tree.exists(right_src):
        tree.copyfile(right_src, "%s.%s" % (dest, right_distro.upper()))
    if os.path.isdir(right_src):
        os.symlink("%s.%s" % (os.path.basename(dest), right_distro.upper()),
                   dest)

def add_changelog(package, merged_version, left_distro, left_dist,
                  right_distro, right_dist, merged_dir):
    """Add a changelog entry to the package."""
    changelog_file = "%s/debian/changelog" % merged_dir

    with open(changelog_file) as changelog:
        with open(changelog_file + ".new", "w") as new_changelog:
            print >>new_changelog, ("%s (%s) UNRELEASED; urgency=low"
                                    % (package, merged_version))
            print >>new_changelog
            print >>new_changelog, "  * Merge from %s %s.  Remaining changes:" \
                  % (right_distro.title(), right_dist)
            print >>new_changelog, "    - SUMMARISE HERE"
            print >>new_changelog
            print >>new_changelog, (" -- %s <%s>  " % (config.get('MOM_NAME'),
                                                       config.get('MOM_EMAIL')) +
                                    time.strftime("%a, %d %b %Y %H:%M:%S %z"))
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
    filename = "%s_%s.dsc" % (package, version.without_epoch)

    tree.ensure("%s/tmp/" % config.get('ROOT'))
    parent = tempfile.mkdtemp(dir="%s/tmp/" % config.get('ROOT'))
    try:
        tree.copytree(merged_dir, "%s/%s" % (parent, contained))

        for ext in ['gz', 'bz2', 'xz']:
            orig_filename = "%s_%s.orig.tar.%s" % (package, version.upstream,
                                                   ext)
            if os.path.isfile("%s/%s" % (output_dir, orig_filename)):
                os.link("%s/%s" % (output_dir, orig_filename),
                        "%s/%s" % (parent, orig_filename))
                break

        cmd = ("dpkg-source",)
        if version.revision is not None and since.upstream != version.upstream:
            cmd += ("-sa",)
        cmd += ("-b", contained)

        try:
            dpkg_source_output = subprocess.check_output(cmd, cwd=parent,
                    stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError, e:
            logger.warning("dpkg-source failed with code %d:\n%s\n",
                e.returncode, e.output)
            # for the message in the JSON report, just take the last line
            # and hope it's relevant...
            lastline = re.sub(r'.*\n', '', e.output.rstrip('\n'),
                flags=re.DOTALL)
            return (MergeResult.FAILED,
                    "unable to build merged source package: "
                    "dpkg-source failed with %d (%s)" % (
                        e.returncode, lastline),
                    create_tarball(package, version, output_dir, merged_dir))
        else:
            logger.debug("dpkg-source succeeded:\n%s\n", dpkg_source_output)

        if os.path.isfile("%s/%s" % (parent, filename)):
            logger.info("Created dpkg-source %s", filename)
            for name in os.listdir(parent):
                src = "%s/%s" % (parent, name)
                dest = "%s/%s" % (output_dir, name)
                if os.path.isfile(src) and not os.path.isfile(dest):
                    os.link(src, dest)

            return (MergeResult.MERGED, None, os.path.basename(filename))
        else:
            message = ("dpkg-source did not produce expected filename %s" %
                tree.subdir(config.get('ROOT'), filename))
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
            logger.info("Created %s", tree.subdir(config.get('ROOT'), filename))

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

def get_common_ancestor(target, downstream, downstream_versions, upstream,
        upstream_versions, tried_bases):
  logger.debug('looking for common ancestor of %s and %s',
          downstream.version, upstream.version)
  for downstream_version, downstream_text in downstream_versions:
    if downstream_version is None:
      # sometimes read_changelog gets confused
      continue

    for upstream_version, upstream_text in upstream_versions:
      if downstream_version != upstream_version:
        continue

      logger.debug('%s looks like a possibility', downstream_version)

      # See if we have this version in the target distro
      try:
        return target.distro.findPackage(downstream.package.name,
                                         searchDist=target.dist,
                                         version=downstream_version)[0]
      except model.error.PackageNotFound:
        pass

      # See if we have this version in a source distro
      source_lists = target.getSourceLists(downstream.package.name)
      for sl in source_lists:
        try:
          return sl.findPackage(downstream.package.name,
                                version=downstream_version)[0]
        except model.error.PackageNotFound:
          pass

      # See if we have this version archived in a pool somewhere
      sources = []
      for sl in source_lists:
        for source in sl:
          sources.append(source)

      for source in sources:
        base_dir = None

        # Try to get it from one of its pool directories on disk.
        # FIXME: if we have more than one source differing only
        # by suite, this searches the corresponding pool directory
        # that many times, because they share a pool directory.
        # It would make more sense if we could just iterate over
        # pool directory instances... but then we wouldn't have a
        # suite (dist) to make the necessary Package so we can hav
        # a PackageVersion.
        for component in source.distro.components():
          pkg = Package(source.distro, source.dist, component,
                        downstream.package.name)
          for package_version in pkg.getPoolVersions():
            if package_version.version == downstream_version:
              return package_version

      # Maybe the old version is still present on the server, just
      # not listed in the Sources file. Try to get it from there.
      target.fetchMissingVersion(downstream.package.name, downstream_version)
      # If that was successful, we'll now find it in a source distro
      for sl in source_lists:
        try:
          return sl.findPackage(downstream.package.name,
                                version=downstream_version)[0]
        except model.error.PackageNotFound:
          pass

      tried_bases.add(downstream_version)

  raise NoBase('unable to find a usable base version for %s and %s' %
          (downstream, upstream))

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

def produce_merge(target, left, upstream, output_dir):

  left_dir = unpack_source(left)
  upstream_dir = unpack_source(upstream)

  report = MergeReport(left=left, right=upstream)
  report.target = target.name
  report.mom_version = str(VERSION)
  report.merge_date = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

  cleanup(output_dir)

  # Try to find the newest common ancestor
  tried_bases = set()
  downstream_versions = None
  upstream_versions = None
  try:
    downstream_versions = read_changelog(left_dir + '/debian/changelog')
    upstream_versions = read_changelog(upstream_dir + '/debian/changelog')
    base = get_common_ancestor(target,
            left, downstream_versions, upstream, upstream_versions, tried_bases)
    base_dir = unpack_source(base)
  except Exception as e:
    report.bases_not_found = sorted(tried_bases, reverse=True)

    if isinstance(e, NoBase):
      report.result = MergeResult.NO_BASE
      logger.info('%s', e)
    else:
      report.result = MergeResult.FAILED
      report.message = 'error finding base version: %s' % e
      logger.exception('error finding base version:\n')

    if downstream_versions:
      report.left_changelog = save_changelog(output_dir, downstream_versions,
          left, set(), 1)

    if upstream_versions:
      report.right_changelog = save_changelog(output_dir, upstream_versions,
          upstream, set(), 1)

    report.write_report(output_dir)
    return report

  stop_at = set([base.version]).union(tried_bases)
  report.left_changelog = save_changelog(output_dir, downstream_versions,
      left, stop_at)
  report.right_changelog = save_changelog(output_dir, upstream_versions,
      upstream, stop_at)

  report.set_base(base)
  report.bases_not_found = sorted(tried_bases, reverse=True)

  logger.info('base version: %s', base.version)

  generate_patch(base, left.package.distro, left, slipped=False, force=False,
          unpacked=True)
  generate_patch(base, upstream.package.distro, upstream, slipped=False,
          force=False, unpacked=True)

  report.merged_version = Version(str(upstream.version)+config.get('LOCAL_SUFFIX'))

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

    write_report(report,
        left=left,
        base=base,
        right=upstream,
        src_file=None,
        # this is MergeReport.merged_dir...
        output_dir=output_dir,
        # ... and for a SYNC_THEIRS merge, we don't need to look at the
        # unpacked source code
        merged_dir=None)
    return report

  merged_dir = work_dir(left.package.name, report.merged_version)

  logger.info("Merging %s..%s onto %s", upstream, base, left)

  try:
    merge_data = do_merge(left_dir, left.package.name,
                          left.getDscContents()['Format'],
                          left.package.distro.name,
                          base_dir,
                          upstream_dir, upstream.package.name,
                          upstream.getDscContents()['Format'],
                          upstream.package.distro.name,
                          merged_dir)
  except OSError as e:
    cleanup(merged_dir)
    logger.exception("Could not merge %s, probably bad files?", left)
    report.result = MergeResult.FAILED
    report.message = 'Could not merge: %s' % e
    report.write_report(output_dir)
    return report

  if len(merge_data.conflicts) == 0 and merge_data.total_modifications == 1 \
     and len(merge_data.modified_files) == 1 \
     and 'debian/changelog' in merge_data.modified_files:
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

      write_report(report,
                   left=left,
                   base=base,
                   right=upstream,
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

  if 'debian/changelog' not in merge_data.conflicts:
    try:
      add_changelog(left.package.name, report.merged_version, left.package.distro.name, left.package.dist,
                    upstream.package.distro.name, upstream.package.dist, merged_dir)
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

  if len(merge_data.conflicts):
    src_file = create_tarball(left.package.name, report.merged_version, output_dir, merged_dir)
    report.result = MergeResult.CONFLICTS
    report.conflicts = sorted(merge_data.conflicts)
    report.merge_failure_tarball = src_file
    report.merged_dir = None
  else:
    result, message, src_file = create_source(left.package.name,
        report.merged_version, left.version, output_dir, merged_dir)
    report.result = result

    if result == MergeResult.MERGED:
      assert src_file.endswith('.dsc'), src_file
      dsc = ControlFile("%s/%s" % (output_dir, src_file), signed=True).para
      report.build_metadata_changed = is_build_metadata_changed(left.getDscContents(), dsc)
      report.merged_files = [src_file] + [f[2] for f in files(dsc)]
      report.merged_patch = create_patch(report.merged_version,
              "%s/%s_%s_from-theirs.patch" % (output_dir, left.package.name,
                  report.merged_version),
              merged_dir,
              upstream,
              upstream_dir)
      report.proposed_patch = create_patch(report.merged_version,
              "%s/%s_%s_from-ours.patch" % (output_dir, left.package.name,
                  report.merged_version),
              merged_dir,
              left,
              left_dir)
    else:
      report.result = result
      report.message = message
      report.merged_dir = ""
      report.merge_failure_tarball = src_file

  write_report(report,
               left,
               base,
               upstream,
               src_file=src_file,
               output_dir=output_dir,
               merged_dir=merged_dir)
  logger.info("Wrote output to %s", src_file)
  cleanup(merged_dir)
  cleanup_source(upstream)
  cleanup_source(base)
  cleanup_source(left)
  return report

if __name__ == "__main__":
    run(main, options, usage="%prog",
        description="produce merged packages")
