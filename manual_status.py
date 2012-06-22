#!/usr/bin/env python
# -*- coding: utf-8 -*-
# manual-status.py - output status of manual merges
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
import bz2
import re

from rfc822 import parseaddr
from momlib import *


# Order of priorities
PRIORITY = [ "unknown", "required", "important", "standard", "optional",
             "extra" ]
COLOURS =  [ "#fffd80", "#ffb580", "#ffea80", "#dfff80", "#abff80", "#80ff8b" ]

# Sections
SECTIONS = [ "new", "committed" ]


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

def main(options, args):
    if options.target:
        targets = [options.target]
    else:
        targets = DISTRO_TARGETS.keys()

    # For each package in the destination distribution, find out whether
    # there's an open merge, and if so add an entry to the table for it.
    for target in targets:
        our_distro, our_dist, our_component = get_target_distro_dist_component(target)
        merges = []

        for our_source in get_sources(our_distro, our_dist, our_component):
            try:
                package = our_source["Package"]
                our_version = Version(our_source["Version"])
                our_pool_source = get_pool_source(our_distro, package,
                                                our_version)
                logging.debug("%s: %s is %s", package, our_distro, our_version)
            except IndexError:
                continue

            try:
                if options.source_distro is None:
                    (src_source, src_version, src_pool_source, src_distro, src_dist) \
                                = PACKAGELISTS.find_in_source_distros(target, package)
                else:
                    src_distro = options.source_distro
                    src_dist = options.source_suite
                    (src_source, src_version, src_pool_source) \
                                = get_same_source(src_distro, src_dist, package)

                logging.debug("%s: %s is %s", package, src_distro, src_version)
            except IndexError:
                continue

            try:
                base = get_base(our_pool_source)
                base_source = get_nearest_source(our_distro, src_distro, package, base)
                base_version = Version(base_source["Version"])
                logging.debug("%s: base is %s (%s wanted)",
                            package, base_version, base)
                continue
            except IndexError:
                pass

            try:
                priority_idx = PRIORITY.index(our_source["Priority"])
            except KeyError:
                priority_idx = 0

            section = "new"
            try:
                report = read_report(output_dir)
                if report["committed"]:
                    section = "committed"
            except:
                pass

            merges.append((section, priority_idx, package,
                        our_source, our_version, src_version))

        write_status_page(target, merges, our_distro, src_distro)
        write_status_json(target, merges, our_distro, src_distro)

        status_file = "%s/merges/tomerge-%s-manual" % (ROOT, target)
        remove_old_comments(status_file, merges)
        write_status_file(status_file, merges)


def write_status_page(target, merges, left_distro, right_distro):
    """Write out the manual merge status page."""
    merges.sort()

    status_file = "%s/merges/%s-manual.html" % (ROOT, target)
    if not os.path.isdir(os.path.dirname(status_file)):
        os.makedirs(os.path.dirname(status_file))
    with open(status_file + ".new", "w") as status:
        print >>status, "<html>"
        print >>status
        print >>status, "<head>"
        print >>status, "<meta http-equiv=\"Content-Type\" content=\"text/html; charset=utf-8\">"
        print >>status, "<title>Merge-o-Matic: %s manual</title>" \
              % target
        print >>status, "<style>"
        print >>status, "h1 {"
        print >>status, "    padding-top: 0.5em;"
        print >>status, "    font-family: sans-serif;"
        print >>status, "    font-size: 2.0em;"
        print >>status, "    font-weight: bold;"
        print >>status, "}"
        print >>status, "h2 {"
        print >>status, "    padding-top: 0.5em;"
        print >>status, "    font-family: sans-serif;"
        print >>status, "    font-size: 1.5em;"
        print >>status, "    font-weight: bold;"
        print >>status, "}"
        print >>status, "p, td {"
        print >>status, "    font-family: sans-serif;"
        print >>status, "    margin-bottom: 0;"
        print >>status, "}"
        print >>status, "li {"
        print >>status, "    font-family: sans-serif;"
        print >>status, "    margin-bottom: 1em;"
        print >>status, "}"
        print >>status, "tr.first td {"
        print >>status, "    border-top: 2px solid white;"
        print >>status, "}"
        print >>status, "</style>"
        print >>status, "</head>"
        print >>status, "<body>"
        print >>status, "<h1> Merge-o-Matic: %s manual</h1>" % target

        for section in SECTIONS:
            section_merges = [ m for m in merges if m[0] == section ]
            print >>status, ("<p><a href=\"#%s\">%s %s merges</a></p>"
                             % (section, len(section_merges), section))

        try:
            comments = get_comments()
        except IOError:
            comments = {}

        for section in SECTIONS:
            section_merges = [ m for m in merges if m[0] == section ]

            print >>status, ("<h2 id=\"%s\">%s Merges</h2>"
                             % (section, section.title()))

            do_table(status, section_merges, comments, left_distro, right_distro, target)

        print >>status, "</body>"
        print >>status, "</html>"

    os.rename(status_file + ".new", status_file)

def get_uploader(distro, source):
    """Obtain the uploader from the dsc file signature."""
    for md5sum, size, name in files(source):
        if name.endswith(".dsc"):
            dsc_file = name
            break
    else:
        return None

    filename = "%s/pool/%s/%s/%s/%s" \
            % (ROOT, distro, pathhash(source["Package"]), source["Package"], 
               dsc_file)

    (a, b, c) = os.popen3("gpg --verify %s" % filename)
    stdout = c.readlines()
    try:
        return stdout[1].split("Good signature from")[1].strip().strip("\"")
    except IndexError:
        return None

def do_table(status, merges, comments, left_distro, right_distro, target):
    """Output a table."""
    print >>status, "<table cellspacing=0>"
    print >>status, "<tr bgcolor=#d0d0d0>"
    print >>status, "<td rowspan=2><b>Package</b></td>"
    print >>status, "<td rowspan=2><b>Comment</b></td>"
    print >>status, "</tr>"
    print >>status, "<tr bgcolor=#d0d0d0>"
    print >>status, "<td><b>%s Version</b></td>" % left_distro.title()
    print >>status, "<td><b>%s Version</b></td>" % right_distro.title()
    print >>status, "</tr>"

    for uploaded, priority, package, source, \
            left_version, right_version in merges:
        print >>status, "<tr bgcolor=%s class=first>" % COLOURS[priority]
        print >>status, "<td><tt><a href=\"%s" \
              "%s/%s/%s_%s.patch\">%s</a></tt>" \
              % (MOM_URL, pathhash(package), package, package, left_version, package)
        print >>status, " <sup><a href=\"https://launchpad.net/ubuntu/" \
              "+source/%s\">LP</a></sup>" % package
        print >>status, " <sup><a href=\"http://packages.qa.debian.org/" \
              "%s\">PTS</a></sup></td>" % package
        print >>status, "<td rowspan=2>%s</td>" % (comments[package] if package in comments else "")
        print >>status, "</tr>"
        print >>status, "<tr bgcolor=%s>" % COLOURS[priority]
        print >>status, "<td><small>%s</small></td>" % source["Binary"]
        print >>status, "<td>%s</td>" % left_version
        print >>status, "<td>%s</td>" % right_version
        print >>status, "</tr>"

    print >>status, "</table>"


def write_status_json(target, merges, left_distro, right_distro):
    """Write out the merge status JSON dump."""
    status_file = "%s/merges/%s-manual.json" % (ROOT, target)
    with open(status_file + ".new", "w") as status:
        # No json module available on merges.ubuntu.com right now, but it's
        # not that hard to do it ourselves.
        print >>status, '['
        cur_merge = 0
        for uploaded, priority, package, source, \
                left_version, right_version in merges:
            print >>status, ' {',
            # source_package, short_description, and link are for
            # Harvest (http://daniel.holba.ch/blog/?p=838).
            print >>status, '"source_package": "%s",' % package,
            print >>status, '"short_description": "merge %s",' % right_version,
            print >>status, '"link": "%s/%s/%s/",' % (MOM_URL, pathhash(package), package),
            print >>status, '"uploaded": "%s",' % uploaded,
            print >>status, '"priority": "%s",' % priority,
            binaries = re.split(', *', source["Binary"].replace('\n', ''))
            print >>status, '"binaries": [ %s ],' % \
                            ', '.join(['"%s"' % b for b in binaries]),
            print >>status, '"left_version": "%s",' % left_version,
            print >>status, '"right_version": "%s"' % right_version,
            cur_merge += 1
            if cur_merge < len(merges):
                print >>status, '},'
            else:
                print >>status, '}'
        print >>status, ']'

    os.rename(status_file + ".new", status_file)


def write_status_file(status_file, merges):
    """Write out the merge status file."""
    with open(status_file + ".new", "w") as status:
        for uploaded, priority, package, source, \
                left_version, right_version in merges:
            print >>status, "%s %s %s %s, %s" \
                  % (package, priority,
                     left_version, right_version, uploaded)

    os.rename(status_file + ".new", status_file)


if __name__ == "__main__":
    run(main, options, usage="%prog",
        description="output status of manual merges")

