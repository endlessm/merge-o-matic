#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright © 2008 Canonical Ltd.
# Copyright © 2013 Collabora Ltd.
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

import json
import logging
import os
import re
import time
from collections import (OrderedDict)
from textwrap import fill

import config
from deb.controlfile import ControlFile
from deb.version import (Version)
from model import (Distro, PackageVersion)
from model.obs import (OBSDistro)
from momlib import files
from momversion import VERSION
from util import tree

logger = logging.getLogger('merge_report')

class MergeResult(str):
    def __new__(cls, s):
        s = s.upper()

        if s in cls.__dict__:
            return cls.__dict__[s]

        raise ValueError('Not a MergeResult: %r' % s)

    def __repr__(self):
        return 'MergeResult(%r)' % str(self)

# We have to bypass MergeResult.__new__ here, to avoid chicken/egg:
# we're ensuring that there are constants in MergeResult.__dict__ so
# that MergeResult.__new__ will work :-)
MergeResult.UNKNOWN = str.__new__(MergeResult, 'UNKNOWN')
MergeResult.UNKNOWN.message = "???"
MergeResult.NO_BASE = str.__new__(MergeResult, 'NO_BASE')
MergeResult.NO_BASE.message = ("Failed to merge because the base version " +
        "required for a 3-way merge is missing from the pool")
MergeResult.SYNC_THEIRS = str.__new__(MergeResult, 'SYNC_THEIRS')
MergeResult.SYNC_THEIRS.message = ("Version in 'right' distro supersedes the "
        "'left' version")
MergeResult.KEEP_OURS = str.__new__(MergeResult, 'KEEP_OURS')
MergeResult.KEEP_OURS.message = "Version in 'left' distro is up-to-date"
MergeResult.FAILED = str.__new__(MergeResult, 'FAILED')
MergeResult.FAILED.message = "Unexpected failure"
MergeResult.MERGED = str.__new__(MergeResult, 'MERGED')
MergeResult.MERGED.message = "Merge appears to have been successful"
MergeResult.CONFLICTS = str.__new__(MergeResult, 'CONFLICTS')
MergeResult.CONFLICTS.message = "3-way merge encountered conflicts"

def read_report(output_dir):
    """Read the report to determine the versions that went into it."""

    report = MergeReport()

    filename = "%s/REPORT" % output_dir

    if os.path.isfile(filename + '.json'):
        with open(filename + '.json') as r:
            for (k, v) in json.load(r).iteritems():
                if k.startswith('#'):
                    continue

                try:
                    report[k] = v
                except KeyError:
                    logger.exception('ignoring unknown key in JSON %r:',
                            filename)
    elif os.path.isfile(filename):
        _read_report_text(output_dir, filename, report)
    else:
        raise ValueError, "No report exists"

    report.check()
    return report

def _read_report_text(output_dir, filename, report):
    """Read an old-style semi-human-readable REPORT."""

    merged_is_right = False

    with open(filename) as r:
        report["source_package"] = next(r).strip()
        in_list = None
        for line in r:
            if line.startswith("    "):
                if in_list == "base":
                    report["base_files"].append(line.strip())
                elif in_list == "left":
                    report["left_files"].append(line.strip())
                elif in_list == "right":
                    report["right_files"].append(line.strip())
                elif in_list == "merged":
                    report["merged_files"].append(line.strip())
            else:
                in_list = None

            if line.startswith("base:"):
                report["base_version"] = Version(line[5:].strip())
                in_list = "base"
            elif line.startswith("our distro "):
                m = re.match("our distro \(([^)]+)\): (.+)", line)
                if m:
                    report["left_distro"] = m.group(1)
                    report["left_version"] = Version(m.group(2).strip())
                    in_list = "left"
            elif line.startswith("source distro "):
                m = re.match("source distro \(([^)]+)\): (.+)", line)
                if m:
                    report["right_distro"] = m.group(1)
                    report["right_version"] = Version(m.group(2).strip())
                    in_list = "right"
            elif line.startswith("generated:"):
                in_list = "merged"
            elif line.startswith("Merged without changes: YES"):
                merged_is_right = True
            elif line.startswith("Build-time metadata changed: NO"):
                report["build_metadata_changed"] = False
            elif line.startswith("Merge committed: YES"):
                report["committed"] = True
            elif line.startswith("  C  ") or line.startswith("  C* "):
                report["conflicts"].append(line[5:].strip())

    # Try to synthesize a meaningful result from those fields
    if report["base_version"] is None:
        report["result"] = MergeResult.NO_BASE
    elif merged_is_right:
        report["result"] = MergeResult.SYNC_THEIRS
    elif report["merged_files"]:
        report["result"] = MergeResult.MERGED
    elif report["conflicts"]:
        report["result"] = MergeResult.CONFLICTS
    else:
        # doesn't look good... assume FAILED
        report["result"] = MergeResult.FAILED

    return report

class MergeReport(object):
    __slots__ = (
            'source_package',
            'mom_version',
            'merge_date',
            'result',
            'message',
            'obs_project',
            'obs_package',
            'left_version',
            'left_distro',
            'left_suite',
            'left_component',
            'left_files',
            'left_patch',
            'base_version',
            'bases_not_found',
            'base_distro',
            'base_suite',
            'base_component',
            'base_files',
            'right_version',
            'right_distro',
            'right_suite',
            'right_component',
            'right_files',
            'right_patch',
            'merged_version',
            'merged_dir',
            'merged_files',
            'merged_patch',
            'build_metadata_changed',
            'merge_failure_tarball',
            'conflicts',
            'genchanges',
            'committed',
            'committed_to',
            'commit_detail',
            'obs_request_url',
            )

    def __init__(self, left=None, right=None, base=None):
        # Defaults
        for f in self.__slots__:
            setattr(self, f, None)
        self.bases_not_found = []
        self.left_files = []
        self.base_files = []
        self.right_files = []
        self.merged_files = []
        self.build_metadata_changed = True
        self.conflicts = []
        self.committed = False
        self.result = MergeResult.UNKNOWN

        if base is not None:
            self.source_package = base.package.name
            self.base_version = base.version
            self.base_distro = base.package.distro.name
            self.base_suite = base.package.dist
            self.base_component = base.package.component
            self.base_files = [f[2] for f in files(base.getSources())]

        if right is not None:
            self.source_package = right.package.name
            self.right_distro = right.package.distro.name
            self.right_suite = right.package.dist
            self.right_component = right.package.component
            self.right_version = right.version
            self.right_files = [f[2] for f in files(right.getSources())]

        if left is not None:
            self.source_package = left.package.name
            self.left_distro = left.package.distro.name
            self.left_suite = left.package.dist
            self.left_component = left.package.component
            self.left_version = left.version
            self.left_files = [f[2] for f in files(left.getSources())]

            if isinstance(left.package.distro, OBSDistro):
                self.obs_project = left.package.distro.obsProject(
                        left.package.dist,
                        left.package.component)

                # this requires a just-in-time-populated cache of stuff from
                # OBS, so it isn't 100% reliable yet
                try:
                    self.obs_package = left.package.obsName
                except Exception:
                    logger.exception('ignoring error getting obsName for %s:',
                            left.package)

    def __setitem__(self, k, v):
        if k not in self.__slots__:
            raise KeyError('%r not allowed in MergeReport' % str(k))

        setattr(self, k, v)

    def __getitem__(self, k):
        if k not in self.__slots__:
            raise KeyError('%r not in MergeReport' % str(k))

        return getattr(self, k)

    def check(self):
        try:
            self.result = MergeResult(self.result)
        except ValueError:
            self.message = 'unparsed result %s: %s' % (
                    self.result, self.message)
            self.result = MergeResult.UNKNOWN

        if self.source_package is None:
            raise AttributeError('Insufficient detail in report: no '
                    'source package')

        if self.left_version is None:
            raise AttributeError('Insufficient detail in report: our '
                    'version is missing')

        if self.left_distro is None:
            raise AttributeError('Insufficient detail in report: our '
                    'distro is missing')

        if self.result != MergeResult.KEEP_OURS:
            if self.right_version is None:
                raise AttributeError('Insufficient detail in report: '
                        'their version is missing')

            if self.right_distro is None:
                raise AttributeError('Insufficient detail in report: '
                        'their distro is missing')

        # promote versions to Version objects
        for k in ("left_version", "right_version", "base_version",
                "merged_version"):
            v = getattr(self, k)

            if v is not None:
                setattr(self, k, Version(v))

        if self.result == MergeResult.NO_BASE:
            assert self.base_version is None, self.base_version
        elif self.result == MergeResult.SYNC_THEIRS:
            assert not self.conflicts, self.conflicts
            self.merged_dir = ""
            self.merged_files = self.right_files
        elif self.result == MergeResult.KEEP_OURS:
            assert not self.conflicts, self.conflicts
            self.merged_dir = ""
            self.merged_files = self.left_files
        elif self.result == MergeResult.FAILED:
            pass
        elif self.result == MergeResult.MERGED:
            assert not self.conflicts, self.conflicts
        elif self.result == MergeResult.CONFLICTS:
            assert self.conflicts

        if self.result in (MergeResult.CONFLICTS, MergeResult.FAILED,
                MergeResult.MERGED):
            if (self.merged_version is None or
                    (self.merged_version.revision is not None and
                        self.left_version.upstream !=
                        self.merged_version.upstream)):
                maybe_sa = ' -sa'
            else:
                maybe_sa = ''
            self["genchanges"] = "-S -v%s%s" % (self.left_version, maybe_sa)

    def to_dict(self):
        # Use an OrderedDict to make the report more human-readable, and
        # provide pseudo-comments to clarify
        report = OrderedDict()
        comments = dict(
            result=self.result.message,
            left_version="'our' version",
            left_patch="diff(base version ... left version)",
            base_version="common ancestor of 'left' and 'right'",
            bases_not_found="these common ancestors could not be found",
            right_version="'their' version",
            right_patch="diff(base version ... right version)",
            merged_patch="diff(left version ... merged version) for review",
            genchanges=("Pass these arguments to dpkg-genchanges, " +
                "dpkg-buildpackage or debuild when you have completed the " +
                "merge"),
        )
        for f in self.__slots__:
            if f in ('left_version', 'right_version', 'merged_version',
                    'base_version'):
                # each of these is a Version, which we can't serialize directly
                v = getattr(self, f)
                if v is not None:
                    if f in comments:
                        report['#' + f] = comments[f]
                    report[f] = str(v)
            elif f == 'bases_not_found':
                v = getattr(self, f)
                if v:
                    report['#' + f] = comments[f]
                    # each of these is a Version
                    report[f] = [str(x) for x in v]
            else:
                v = getattr(self, f)
                if v is not None:
                    if f in comments:
                        report['#' + f] = comments[f]
                    report[f] = v

        return report

    def write_report(self, output_dir):
        self.check()
        report = self.to_dict()

        filename = "%s/REPORT.json" % output_dir
        tree.ensure(filename)
        with open(filename + '.tmp', "w") as fh:
            json.dump(report, fh, indent=2, sort_keys=False)
            fh.write('\n')
        os.rename(filename + '.tmp', filename)

def write_report(left, left_patch,
                 base, tried_bases,
                 right, right_patch,
                 merged_version, conflicts, src_file, patch_file, output_dir,
                 merged_dir, merged_is_right, build_metadata_changed):
    """Write the merge report."""

    package = left.package.name
    assert package == right.package.name, (package, right.package.name)

    assert isinstance(left, PackageVersion)
    left_source = left.getSources()
    left_distro = left.package.distro.name

    if base is None:
        base_source = None
    else:
        assert isinstance(base, PackageVersion)
        base_source = base.getSources()

    assert isinstance(right, PackageVersion)
    right_source = right.getSources()
    right_distro = right.package.distro.name

    filename = "%s/REPORT" % output_dir
    tree.ensure(filename)
    with open(filename, "w") as report:
        # Package and time
        print >>report, "%s" % package
        print >>report, "%s" % time.ctime()
        print >>report

        # General rambling
        print >>report, fill("Below now follows the report of the automated "
                             "merge of the %s changes to the %s source "
                             "package against the new %s version."
                             % (left_distro.title(), package,
                                right_distro.title()))
        print >>report
        print >>report, fill("This file is designed to be both human readable "
                             "and machine-parseable.  Any line beginning with "
                             "four spaces is a file that should be downloaded "
                             "for the complete merge set.")
        print >>report
        print >>report

        print >>report, fill("Here are the particulars of the three versions "
                             "of %s that were chosen for the merge.  The base "
                             "is the newest version that is a common ancestor "
                             "of both the %s and %s packages.  It may be of "
                             "a different upstream version, but that's not "
                             "usually a problem."
                             % (package, left_distro.title(),
                                right_distro.title()))
        print >>report
        print >>report, fill("The files are the source package itself, and "
                             "the patch from the common base to that version.")
        print >>report

        # Base version and files
        if tried_bases:
            # We print this even if base_source is not None: we want to
            # record the better base versions we tried and failed to find
            print >>report, "missing base version(s):"
            for v in tried_bases:
                print >>report, " %s" % v

        if base_source is not None:
            print >>report, "base: %s" % base_source["Version"]
            for md5sum, size, name in files(base_source):
                print >>report, "    %s" % name
        print >>report

        # Left version and files
        print >>report, "our distro (%s): %s" % (left_distro, left_source["Version"])
        for md5sum, size, name in files(left_source):
            print >>report, "    %s" % name
        print >>report
        if left_patch is not None:
            print >>report, "base -> %s" % left_distro
            print >>report, "    %s" % left_patch
            print >>report

        # Right version and files
        print >>report, "source distro (%s): %s" % (right_distro, right_source["Version"])
        for md5sum, size, name in files(right_source):
            print >>report, "    %s" % name
        print >>report
        if right_patch is not None:
            print >>report, "base -> %s" % right_distro
            print >>report, "    %s" % right_patch
            print >>report

        # Generated section
        print >>report
        print >>report, "Generated Result"
        print >>report, "================"
        print >>report
        if base_source is None:
            print >>report, fill("Failed to merge because the base version "
                                 "required for a 3-way diff is missing from %s pool. "
                                 "You will need to either merge manually; or add the "
                                 "missing base version sources to '%s/%s/*/%s/' and run "
                                 "update_sources.py."
                                 % (right_distro, config.get('ROOT'), right_distro, package))
            print >>report
        elif merged_is_right:
            print >>report, fill("The %s version supercedes the %s version "
                                 "and can be added to %s with no changes." %
                                 (right_distro.title(), left_distro.title(),
                                  left_distro.title()))
            print >>report
            print >>report, "Merged without changes: YES"
            print >>report
            if build_metadata_changed:
                print >>report, "Build-time metadata changed: NO"
                print >>report
        else:
            if src_file.endswith(".dsc"):
                print >>report, fill("No problems were encountered during the "
                                    "merge, so a source package has been "
                                    "produced along with a patch containing "
                                    "the differences from the %s version to the "
                                    "new version." % right_distro.title())
                print >>report
                print >>report, fill("You should compare the generated patch "
                                    "against the patch for the %s version "
                                    "given above and ensure that there are no "
                                    "unexpected changes.  You should also "
                                    "sanity check the source package."
                                    % left_distro.title())
                print >>report

                print >>report, "generated: %s" % merged_version

                # Files from the dsc
                dsc = ControlFile("%s/%s" % (output_dir, src_file),
                                multi_para=False, signed=True).para
                print >>report, "    %s" % src_file
                for md5sum, size, name in files(dsc):
                    print >>report, "    %s" % name
                print >>report
                if patch_file is not None:
                    print >>report, "%s -> generated" % right_distro
                    print >>report, "    %s" % patch_file
                    print >>report
                if build_metadata_changed:
                    print >>report, "Build-time metadata changed: NO"
                    print >>report
            else:
                print >>report, fill("Due to conflict or error, it was not "
                                    "possible to automatically create a source "
                                    "package.  Instead the result of the merge "
                                    "has been placed into the following tar file "
                                    "which you will need to turn into a source "
                                    "package once the problems have been "
                                    "resolved.")
                print >>report
                print >>report, "    %s" % src_file
                print >>report

            if len(conflicts):
                print >>report
                print >>report, "Conflicts"
                print >>report, "========="
                print >>report
                print >>report, fill("In one or more cases, there were different "
                                    "changes made in both %s and %s to the same "
                                    "file; these are known as conflicts."
                                    % (left_distro.title(), right_distro.title()))
                print >>report
                print >>report, fill("It is not possible for these to be "
                                    "automatically resolved, so this source "
                                    "needs human attention.")
                print >>report
                print >>report, fill("Those files marked with 'C ' contain diff3 "
                                    "conflict markers, which can be resolved "
                                    "using the text editor of your choice.  "
                                    "Those marked with 'C*' could not be merged "
                                    "that way, so you will find .%s and .%s "
                                    "files instead and should chose one of them "
                                    "or a combination of both, moving it to the "
                                    "real filename and deleting the other."
                                    % (left_distro.upper(), right_distro.upper()))
                print >>report

                conflicts.sort()
                for name in conflicts:
                    if os.path.isfile("%s/%s" % (merged_dir, name)):
                        print >>report, "  C  %s" % name
                    else:
                        print >>report, "  C* %s" % name
                print >>report

            if merged_version.revision is not None \
                and Version(left_source["Version"]).upstream != merged_version.upstream:
                sa_arg = " -sa"
            else:
                sa_arg = ""

            print >>report
            print >>report, fill("Once you have a source package you are happy "
                                "to upload, you should make sure you include "
                                "the orig.tar.gz if appropriate and information "
                                "about all the versions included in the merge.")
            print >>report
            print >>report, fill("Use the following command to generate a "
                                "correct .changes file:")
            print >>report
            print >>report, "  $ dpkg-genchanges -S -v%s%s" \
                % (left_source["Version"], sa_arg)

    report = MergeReport(left=left, right=right, base=base)
    report.mom_version = str(VERSION)
    report["merge_date"] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

    if left_patch is not None:
        report["left_patch"] = left_patch

    if tried_bases:
        report["bases_not_found"] = tried_bases

    if right_patch is not None:
        report["right_patch"] = right_patch

    if merged_version is not None:
        report["merged_version"] = merged_version

    report["merged_dir"] = output_dir

    if base is None:
        report["result"] = MergeResult.NO_BASE

    elif merged_is_right:
        assert not conflicts
        report["result"] = MergeResult.SYNC_THEIRS
    elif src_file is None:
        report["result"] = MergeResult.FAILED
        report["merged_files"] = report["right_files"]
        report["merged_dir"] = ""
    elif src_file.endswith(".dsc"):
        assert not conflicts
        dsc = ControlFile("%s/%s" % (output_dir, src_file),
                        multi_para=False, signed=True).para
        report["result"] = MergeResult.MERGED
        report["merged_files"] = [f[2] for f in files(dsc)]
        report["build_metadata_changed"] = bool(build_metadata_changed)
    else:
        report["merge_failure_tarball"] = src_file

        if conflicts:
            report["result"] = MergeResult.CONFLICTS
        else:
            report["result"] = MergeResult.FAILED

    if patch_file is not None:
        report["merged_patch"] = patch_file

    if conflicts:
        report["conflicts"] = sorted(conflicts)

    report["committed"] = False

    report.write_report(output_dir)
