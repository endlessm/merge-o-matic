#!/usr/bin/env python
# -*- coding: utf-8 -*-
# momlib.py - common utility functions
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
import sys
try:
    from hashlib import md5
except ImportError:
    import md5 as _mod_md5
    md5 = _mod_md5.new
import time
import fcntl
import gzip
import errno
import logging
import datetime
import shutil
import stat
import time
import osc.core
import osc.conf

from cgi import escape
from optparse import OptionParser

from deb.controlfile import ControlFile
from deb.version import Version
from util import shell, tree, pathhash

from model import Distro
import model.error

try:
    from xml.etree import ElementTree
except ImportError:
    from elementtree import ElementTree

MOM_CONFIG_PATH = "/etc/merge-o-matic"
sys.path.insert(1, MOM_CONFIG_PATH)
from momsettings import *
sys.path.remove(MOM_CONFIG_PATH)

logger = logging.getLogger('momlib')

# --------------------------------------------------------------------------- #
# Utility functions
# --------------------------------------------------------------------------- #

def cleanup(path):
    """Remove the path and any empty directories up to ROOT."""
    tree.remove(path)

    (dirname, basename) = os.path.split(path)
    while dirname != ROOT:
        try:
            os.rmdir(dirname)
        except OSError, e:
            if e.errno == errno.ENOTEMPTY or e.errno == errno.ENOENT:
                break
            raise

        (dirname, basename) = os.path.split(dirname)

def md5sum(filename):
    """Return an md5sum."""
    return md5(open(filename).read()).hexdigest()


# --------------------------------------------------------------------------- #
# Location functions
# --------------------------------------------------------------------------- #

def uncompressed_sources_file(distro, dist, component):
    """Return the location of a local Sources file."""
    path = "%s/dists/%s" % (ROOT, distro)
    if dist is not None:
        path = "%s-%s" % (path, dist)
    if component is not None:
        path = "%s/%s" % (path, component)
    return path + "/source/Sources"

def sources_file(distro, dist, component):
    return uncompressed_sources_file(distro, dist, component) + ".gz"

def pool_directory(distro, component, package):
    """Return the pool directory for a source"""
    return "pool/%s/%s/%s/%s" % (pool_name(distro), component, pathhash(package), package)

def pool_sources_file(distro, component, package):
    """Return the location of a pool Sources file for a source."""
    pooldir = pool_directory(distro, component, package)
    return "%s/%s/Sources" % (ROOT, pooldir)

def unpack_directory(source):
    """Return the location of a local unpacked source."""
    return "%s/unpacked/%s/%s/%s" % (ROOT, pathhash(source["Package"]),
                                     source["Package"], source["Version"])

def changes_file(distro, source):
    """Return the location of a local changes file."""
    return "%s/changes/%s/%s/%s/%s_%s_source.changes" \
           % (ROOT, distro, pathhash(source["Package"]),
              source["Package"], source["Package"], source["Version"])

def dpatch_directory(distro, source):
    """Return the directory where we put dpatches."""
    return "%s/dpatches/%s/%s/%s/%s" \
           % (ROOT, distro, pathhash(source["Package"]), source["Package"],
              source["Version"])

def diff_directory(distro, source):
    """Return the directory where we can find diffs."""
    return "%s/diffs/%s/%s/%s" \
           % (ROOT, distro, pathhash(source["Package"]), source["Package"])

def diff_file(distro, source):
    """Return the location of a local diff file."""
    return "%s/%s_%s.patch" % (diff_directory(distro, source),
                               source["Package"], source["Version"])

def patch_directory(distro, source):
    """Return the directory where we can find local patch files."""
    return "%s/patches/%s/%s/%s" \
           % (ROOT, distro, pathhash(source["Package"]), source["Package"])

def patch_file(distro, source, slipped=False):
    """Return the location of a local patch file."""
    path = "%s/%s_%s" % (patch_directory(distro, source),
                         source["Package"], source["Version"])
    if slipped:
        return path + ".slipped-patch"
    else:
        return path + ".patch"

def published_file(distro, source):
    """Return the location where published patches should be placed."""
    return "%s/published/%s/%s/%s_%s.patch" \
           % (ROOT, pathhash(source["Package"]), source["Package"],
              source["Package"], source["Version"])

def patch_list_file():
    """Return the location of the patch list."""
    return "%s/published/PATCHES" % ROOT

def patch_rss_file(distro=None, source=None):
    """Return the location of the patch rss feed."""
    if distro is None or source is None:
        return "%s/published/patches.xml" % ROOT
    else:
        return "%s/patches.xml" % patch_directory(distro, source)

def diff_rss_file(distro=None, source=None):
    """Return the location of the diff rss feed."""
    if distro is None or source is None:
        return "%s/diffs/patches.xml" % ROOT
    else:
        return "%s/patches.xml" % diff_directory(distro, source)

def work_dir(package, version):
    """Return the directory to produce the merge result."""
    return "%s/work/%s/%s/%s" % (ROOT, pathhash(package), package, version)

def result_dir(target, package):
    """Return the directory to store the result in."""
    return "%s/merges/%s/%s/%s" % (ROOT, target, pathhash(package), package)

def component_string(distro=None, component=None):
    """Return the short name for a given distro/dist/component for printing"""
    if component:
        return component
    return distro

# --------------------------------------------------------------------------- #
# Pool handling
# --------------------------------------------------------------------------- #

def pool_name(distro):
    """Return the name of the pool for the given distro."""
    if "pool" in DISTROS[distro]:
        return DISTROS[distro]["pool"]
    else:
        return distro

def get_pool_distros():
    """Return the list of distros with pools."""
    distros = []
    for distro in DISTROS.keys():
        pool = pool_name(distro)
        if pool not in distros:
            distros.append(pool)

    return distros

def get_pool_sources(distro, package):
    """Parse the Sources file for a package in the pool."""
    for component in DISTROS[distro]['components']:
      try:
        filename = pool_sources_file(distro, component, package)
        sources = ControlFile(filename, multi_para=True, signed=False)
        return sources.paras
      except:
        pass
    return []

# --------------------------------------------------------------------------- #
# Source meta-data handling
# --------------------------------------------------------------------------- #

def version_sort(sources):
    """Sort the source list by version number."""
    sources.sort(key=lambda x: Version(x["Version"]))

def has_files(source):
    """Return true if source has a Files entry"""
    return "Files" in source

def files(source):
    """Return (md5sum, size, name) for each file."""
    files = source["Files"].strip("\n").split("\n")
    return [ f.split(None, 2) for f in files ]

def read_basis(filename):
    """Read the basis version of a patch from a file."""
    basis_file = filename + "-basis"
    if not os.path.isfile(basis_file):
        return None

    with open(basis_file) as basis:
        return Version(basis.read().strip())

def save_basis(filename, version):
    """Save the basis version of a patch to a file."""
    basis_file = filename + "-basis"
    with open(basis_file, "w") as basis:
        print >>basis, "%s" % version


# --------------------------------------------------------------------------- #
# Unpacked source handling
# --------------------------------------------------------------------------- #

def unpack_source(pv):
    """Unpack the given source and return location."""
    source = pv.getSources()
    destdir = unpack_directory(source)
    if os.path.isdir(destdir):
        return destdir

    srcdir = "%s/%s" % (ROOT, pv.poolDirectory())
    for md5sum, size, name in files(source):
        if name.endswith(".dsc"):
            dsc_file = name
            break
    else:
        raise ValueError, "Missing dsc file"

    logger.info("Unpacking %s from %s/%s", pv, srcdir, dsc_file)

    tree.ensure(destdir)
    try:
        # output directory for "dpkg-source -x" must not exist
        if (os.path.isdir(destdir)):
            os.rmdir(destdir)
        shell.run(("dpkg-source", "--skip-patches", "-x", dsc_file, destdir), chdir=srcdir, stdout=sys.stdout, stderr=sys.stderr)
        # Make sure we can at least read everything under .pc, which isn't
        # automatically true with dpkg-dev 1.15.4.
        pc_dir = os.path.join(destdir, ".pc")
        for filename in tree.walk(pc_dir):
            pc_filename = os.path.join(pc_dir, filename)
            pc_stat = os.lstat(pc_filename)
            if pc_stat is not None and stat.S_IMODE(pc_stat.st_mode) == 0:
                os.chmod(pc_filename, 0400)
    except:
        cleanup(destdir)
        raise

    return destdir

def cleanup_source(source):
    """Cleanup the given source's unpack location."""
    cleanup(unpack_directory(source))

def save_changes_file(filename, source, previous=None):
    """Save a changes file for the given source."""
    srcdir = unpack_directory(source)

    filesdir = "%s/%s" % (ROOT, source["Directory"])

    tree.ensure(filename)
    with open(filename, "w") as changes:
        cmd = ("dpkg-genchanges", "-S", "-u%s" % filesdir)
        orig_cmd = cmd
        if previous is not None:
            cmd += ("-v%s" % previous["Version"],)

        try:
            shell.run(cmd, chdir=srcdir, stdout=changes)
        except (ValueError, OSError):
            shell.run(orig_cmd, chdir=srcdir, stdout=changes)

    return filename

def save_patch_file(filename, last, this):
    """Save a diff or patch file for the difference between two versions."""
    lastdir = unpack_directory(last)
    thisdir = unpack_directory(this)

    diffdir = os.path.commonprefix((lastdir, thisdir))
    diffdir = diffdir[:diffdir.rindex("/")]

    lastdir = tree.subdir(diffdir, lastdir)
    thisdir = tree.subdir(diffdir, thisdir)

    tree.ensure(filename)
    with open(filename, "w") as diff:
        shell.run(("diff", "-pruN", lastdir, thisdir),
                  chdir=diffdir, stdout=diff, okstatus=(0, 1, 2))

# --------------------------------------------------------------------------- #
# Blacklist and whitelist handling
# --------------------------------------------------------------------------- #

class PackageList(object):
    def __init__(self, filename=None):
        self.filename = filename
        self.set = set()
        self.modified = False
        self.has_file = False
        self._lines = ["# Generated automatically by Merge-o-Matic\n"]
        if self.filename:
            self.load_file()

    def __contains__(self, package):
        return package in self.set

    def load_file(self):
        if not os.path.isfile(self.filename):
            return
        with open(self.filename) as f:
            self._lines = []
            for line in f:
                self._lines.append(line)
                try:
                    line = line[:line.index("#")]
                except ValueError:
                    pass

                line = line.strip()
                if not line:
                    continue

                self.set.add(line)
        self.has_file = True

    def add(self, package):
        if package in self.set:
            return
        self.set.add(package)
        self.modified = True
        self._lines.append("%s\n" % package)

    def discard(self, package):
        if package not in self.set:
            return
        self.set.discard(package)
        self.modified = True
        new_lines = []
        for line in self._lines:
            try:
                line = line[:line.index("#")]
            except ValueError:
                pass

            line = line.strip()
            if line != package:
                new_lines.append(line)
        self._lines = new_lines

    def save_if_modified(self):
        if self.modified:
            logger.debug("Writing %s", self.filename)
            with open(self.filename, "w") as f:
                for line in self._lines:
                    f.write(line)

class PackageLists(object):
    def __init__(self, manual_includes=[], manual_excludes=[]):
        """Initialize MoM white/blacklist; manual_includes and manual_excludes are lists of filenames"""
        self.manual = False
        if manual_includes or manual_excludes:
            self.manual = True
        self.manual_includes = [PackageList(filename) for filename in manual_includes]
        self.manual_excludes = [PackageList(filename) for filename in manual_excludes]
        self.include = {}
        self.exclude = {}

        for target in DISTRO_TARGETS:
            filename_exclude = "%s/%s.ignore.txt" % (ROOT, target)
            self.exclude[target] = PackageList(filename_exclude)
            self.include[target] = {}

            for src in DISTRO_TARGETS[target]["sources"]:
                self.include[target][src] = {}
                filename_include = "%s/%s-%s.list.txt" % (ROOT, target, src)
                # Allow short filename form for default sources
                if src == DISTRO_TARGETS[target]["sources"][0] and not os.path.isfile(filename_include):
                    filename_include = "%s/%s.list.txt" % (ROOT, target)

                self.include[target][src] = PackageList(filename_include)

    def check_target(self, target, src, package):
        """If src is None, all source groups will be checked"""
        if self.manual:
            return self.check_manual(package)
        includes = []
        src_is_default = True # src is the default (first) source for target
        if src is None:
            includes = [self.include[target][src_] for src_ in self.include[target]]
        else:
            includes = [self.include[target][src]]
            if DISTRO_TARGETS[target]["sources"] and src != DISTRO_TARGETS[target]["sources"][0]:
                src_is_default = False
        found = False
        findable = False
        for s in includes:
            if s.has_file or s.modified:
                findable = True
                if package in s:
                    found = True
                    break
        if findable:
            return found and package not in self.exclude[target]
        else:
            return src_is_default and package not in self.exclude[target]

    def add(self, target, src, package):
        """If src is None, the default source group is used"""
        if src is None:
            src = DISTRO_TARGETS[target]["sources"][0]
        return self.include[target][src].add(package)

    def add_if_needed(self, target, src, package):
        """If src is None, the default source group is used"""
        if src is None:
            src = DISTRO_TARGETS[target]["sources"][0]
        for src_ in self.include[target]:
            if package in self.include[target][src_]:
                return False
        return self.add(target, src, package)

    def discard(self, target, src, package):
        """If src is None, the default source group is used"""
        if src is None:
            src = DISTRO_TARGETS[target]["sources"][0]
        return self.include[target][src].discard(package)

    def save_if_modified(self, target, src=None):
        if src is None:
            src = DISTRO_TARGETS[target]["sources"][0]
        return self.include[target][src].save_if_modified()

    def check_manual(self, package):
        if self.manual_includes:
            found = False
            for s in self.manual_includes:
                if package in s:
                    found = True
            if not found:
                return False
            for s in self.manual_excludes:
                if package in s:
                    return False
        else:
            for s in self.manual_excludes:
                if package in s:
                    return False

        return True

PACKAGELISTS = PackageLists()

def get_target_distro_dist_component(target):
    """Return the distro, dist, and component for a given distribution target"""
    distro = DISTRO_TARGETS[target]["distro"]
    try:
        dist = DISTRO_TARGETS[target]["dist"]
    except KeyError:
        dist = None
    try:
        component = DISTRO_TARGETS[target]["component"]
    except KeyError:
        component = None
    return (distro, dist, component)

# --------------------------------------------------------------------------- #
# RSS feed handling
# --------------------------------------------------------------------------- #

def read_rss(filename, title, link, description):
    """Read an RSS feed, or generate a new one."""
    rss = ElementTree.Element("rss", version="2.0")

    channel = ElementTree.SubElement(rss, "channel")

    e = ElementTree.SubElement(channel, "title")
    e.text = title

    e = ElementTree.SubElement(channel, "link")
    e.text = link

    e = ElementTree.SubElement(channel, "description")
    e.text = description

    now = time.gmtime()

    e = ElementTree.SubElement(channel, "pubDate")
    e.text = time.strftime(RSS_TIME_FORMAT, now)

    e = ElementTree.SubElement(channel, "lastBuildDate")
    e.text = time.strftime(RSS_TIME_FORMAT, now)

    e = ElementTree.SubElement(channel, "generator")
    e.text = "Merge-o-Matic"


    if os.path.isfile(filename):
        cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=7)

        tree = ElementTree.parse(filename)
        for i, item in enumerate(tree.find("channel").findall("item")):
            dt = datetime.datetime(*time.strptime(item.findtext("pubDate"),
                                                  RSS_TIME_FORMAT)[:6])
            if dt > cutoff or i < 10:
                channel.append(item)

    return rss

def write_rss(filename, rss):
    """Write out an RSS feed."""
    tree.ensure(filename)
    etree = ElementTree.ElementTree(rss)
    etree.write(filename + ".new")
    os.rename(filename + ".new", filename)

def append_rss(rss, title, link, author=None, filename=None):
    """Append an element to an RSS feed."""
    item = ElementTree.Element("item")

    e = ElementTree.SubElement(item, "title")
    e.text = title

    e = ElementTree.SubElement(item, "link")
    e.text = link

    if author is not None:
        e = ElementTree.SubElement(item, "author")
        e.text = author

    if filename is not None:
        e = ElementTree.SubElement(item, "pubDate")
        e.text = time.strftime(RSS_TIME_FORMAT,
                               time.gmtime(os.stat(filename).st_mtime))


    channel = rss.find("channel")
    for i, e in enumerate(channel):
        if e.tag == "item":
            channel.insert (i, item)
            break
    else:
        channel.append(item)


# --------------------------------------------------------------------------- #
# Comments handling
# --------------------------------------------------------------------------- #

def comments_file():
    """Return the location of the comments."""
    return "%s/comments.txt" % ROOT

def get_comments():
    """Extract the comments from file, and return a dictionary
        containing comments corresponding to packages"""
    comments = {}

    with open(comments_file(), "r") as file_comments:
        fcntl.flock(file_comments, fcntl.LOCK_SH)
        for line in file_comments:
            package, comment = line.rstrip("\n").split(": ", 1)
            comments[package] = comment

    return comments

def add_comment(package, comment):
    """Add a comment to the comments file"""
    with open(comments_file(), "a") as file_comments:
        fcntl.flock(file_comments, fcntl.LOCK_EX)
        the_comment = comment.replace("\n", " ")
        the_comment = escape(the_comment[:100], quote=True)
        file_comments.write("%s: %s\n" % (package, the_comment))

def remove_old_comments(status_file, merges):
    """Remove old comments from the comments file using
       component's existing status file and merges"""
    if not os.path.exists(status_file):
        return

    packages = [ m[2] for m in merges ]
    toremove = []

    with open(status_file, "r") as file_status:
        for line in file_status:
            package = line.split(" ")[0]
            if package not in packages:
                toremove.append(package)

    with open(comments_file(), "a+") as file_comments:
        fcntl.flock(file_comments, fcntl.LOCK_EX)

        new_lines = []
        for line in file_comments:
            if line.split(": ", 1)[0] not in toremove:
                new_lines.append(line)

        file_comments.truncate(0)

        for line in new_lines:
            file_comments.write(line)

def gen_buglink_from_comment(comment):
    """Return an HTML formatted Debian/Ubuntu bug link from comment"""
    debian = re.search(".*Debian bug #([0-9]{1,6}).*", comment, re.I)
    ubuntu = re.search(".*bug #([0-9]{1,6}).*", comment, re.I)

    html = ""
    if debian:
        html += "<img src=\".img/debian.png\" alt=\"Debian\" />"
        html += "<a href=\"http://bugs.debian.org/%s\">#%s</a>" \
            % (debian.group(1), debian.group(1))
    elif ubuntu:
        html += "<img src=\".img/ubuntu.png\" alt=\"Ubuntu\" />"
        html += "<a href=\"https://launchpad.net/bugs/%s\">#%s</a>" \
            % (ubuntu.group(1), ubuntu.group(1))
    else:
        html += "&nbsp;"

    return html
