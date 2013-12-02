#!/usr/bin/env python
# -*- coding: utf-8 -*-
# merge-status.py - output merge status
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
from model import Distro, OBSDistro
from util import run


# Order of priorities
PRIORITY = [ "unknown", "required", "important", "standard", "optional",
             "extra" ]
COLOURS =  [ "#fffd80", "#ffb580", "#ffea80", "#dfff80", "#abff80", "#80ff8b" ]

# Sections
SECTIONS = [ "outstanding", "new", "committed" ]


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

    outstanding = []
    if os.path.isfile("%s/outstanding-merges.txt" % ROOT):
        after_uvf = True

        with open("%s/outstanding-merges.txt" % ROOT) as f:
            for line in f:
                outstanding.append(line.strip())
    else:
        after_uvf = False
        SECTIONS.remove("new")

    # For each package in the destination distribution, find out whether
    # there's an open merge, and if so add an entry to the table for it.
    for target in targets:
        our_distro, our_dist, our_component = get_target_distro_dist_component(target)
        merges = []

        d = Distro.get(our_distro)
        for source in d.getSources(our_dist, our_component):
            try:
                output_dir = result_dir(target, source["Package"])
                report = read_report(output_dir)
            except ValueError:
                continue

            try:
                priority_idx = PRIORITY.index(source["Priority"])
            except (KeyError, ValueError) as e:
                # either it has no priority, or the priority is something
                # not in our array; Debian packages can end up with
                # Priority: source
                priority_idx = 0

            if report["committed"]:
                section = "committed"
            elif not after_uvf:
                section = "outstanding"
            elif source["Package"] in outstanding:
                section = "outstanding"
            else:
                section = "new"

            merges.append((section, priority_idx, source["Package"],
                        source, report["base_version"],
                        report["left_version"], report["right_version"],
                        report["right_distro"], output_dir))

        merges.sort()

        if isinstance(d, OBSDistro):
            obs_project = d.obsProject(our_dist, our_component)
        else:
            obs_project = None

        write_status_page(target, merges, our_distro, obs_project)
        write_status_json(target, merges)

        status_file = "%s/merges/tomerge-%s" % (ROOT, target)
        remove_old_comments(status_file, merges)
        write_status_file(status_file, merges)


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


def write_status_page(target, merges, our_distro, obsProject):
    """Write out the merge status page."""
    status_file = "%s/merges/%s.html" % (ROOT, target)
    if not os.path.isdir(os.path.dirname(status_file)):
        os.makedirs(os.path.dirname(status_file))
    with open(status_file + ".new", "w") as status:
        print >>status, "<html>"
        print >>status
        print >>status, "<head>"
        print >>status, "<meta http-equiv=\"Content-Type\" content=\"text/html; charset=utf-8\">"
        print >>status, "<title>Merge-o-Matic: %s</title>" % target
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
        print >>status, "<h1>Merge-o-Matic: %s</h1>" % target

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

            do_table(status, section_merges, comments, our_distro, target,
                obsProject)

        print >>status, "<h2 id=stats>Statistics</h2>"
        print >>status, ("<img src=\"%s-now.png\" title=\"Current stats\">"
                         % target)
        print >>status, ("<img src=\"%s-trend.png\" title=\"Six month trend\">"
                         % target)
        print >>status, "</body>"
        print >>status, "</html>"

    os.rename(status_file + ".new", status_file)

def do_table(status, merges, comments, our_distro, target, obsProject):
    """Output a table."""
    default_src_distro =DISTRO_SOURCES[DISTRO_TARGETS[target]["sources"][0]][0]["distro"]
    print >>status, "<table cellspacing=0>"
    print >>status, "<tr bgcolor=#d0d0d0>"
    print >>status, "<td rowspan=2><b>Package</b></td>"
    print >>status, "<td rowspan=2><b>Comment</b></td>"
    print >>status, "</tr>"
    print >>status, "<tr bgcolor=#d0d0d0>"
    print >>status, "<td><b>%s Version</b></td>" % our_distro.title()
    print >>status, "<td><b>%s Version</b></td>" % default_src_distro.title()
    print >>status, "<td><b>Base Version</b></td>"
    print >>status, "</tr>"

    for uploaded, priority, package, source, \
            base_version, left_version, right_version, right_distro, output_dir in merges:

        print >>status, "<tr bgcolor=%s class=first>" % COLOURS[priority]
        print >>status, "<td><tt><a href=\"%s/REPORT\">" \
              "%s</a></tt>" % (re.sub('^' + re.escape(ROOT), MOM_URL, output_dir, 1), package)
        print >>status, " <sup><a href=\"https://launchpad.net/ubuntu/" \
              "+source/%s\">LP</a></sup>" % package
        print >>status, " <sup><a href=\"http://packages.qa.debian.org/" \
              "%s\">PTS</a></sup>" % package
        print >>status, " <sup><a href=\"https://SERVER/package/show?package=%s" \
              "&project=%s\">OBS</a></sup></td>" % (package, obsProject)
        print >>status, "<td rowspan=2>%s</td>" % (comments[package] if package in comments else "")
        print >>status, "</tr>"
        print >>status, "<tr bgcolor=%s>" % COLOURS[priority]
        print >>status, "<td><small>%s</small></td>" % source["Binary"]
        print >>status, "<td>%s</td>" % left_version
        print >>status, "<td>%s" % right_version
        if right_distro != default_src_distro:
            print >>status, "<br/>(%s)" % right_distro
        print >>status, "</td>"
        if base_version is None:
            print >>status, "<td style='text-align:center'><em>???</em></td>"
        else:
            print >>status, "<td>%s</td>" % base_version
        print >>status, "</tr>"

    print >>status, "</table>"


def write_status_json(target, merges):
    """Write out the merge status JSON dump."""
    status_file = "%s/merges/%s.json" % (ROOT, target)
    with open(status_file + ".new", "w") as status:
        # No json module available on merges.ubuntu.com right now, but it's
        # not that hard to do it ourselves.
        print >>status, '['
        cur_merge = 0
        for uploaded, priority, package, source, \
                base_version, left_version, right_version, right_distro, output_dir in merges:
            print >>status, ' {',
            # source_package, short_description, and link are for
            # Harvest (http://daniel.holba.ch/blog/?p=838).
            print >>status, '"source_package": "%s",' % package,
            print >>status, '"short_description": "merge %s",' % right_version,
            print >>status, '"link": "%s/%s/",' % (MOM_URL, output_dir),
            print >>status, '"uploaded": "%s",' % uploaded,
            print >>status, '"priority": "%s",' % priority,
            binaries = re.split(', *', source["Binary"].replace('\n', ''))
            print >>status, '"binaries": [ %s ],' % \
                            ', '.join(['"%s"' % b for b in binaries]),
            if base_version is None:
                print >>status, '"base_version": "???",'
            else:
                print >>status, '"base_version": "%s",' % base_version,
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
                base_version, left_version, right_version, right_distro, output_dir in merges:
            if base_version is None:
                base_version = "???"
            print >>status, "%s %s %s %s %s, %s" \
                  % (package, priority, base_version,
                     left_version, right_version, uploaded)

    os.rename(status_file + ".new", status_file)

if __name__ == "__main__":
    run(main, options, usage="%prog",
        description="output merge status")

