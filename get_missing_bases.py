#!/usr/bin/env python
# -*- coding: utf-8 -*-
# get_missing_bases.py - download missing base versions to make a 3-way
# merge possible
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

import sys
import urllib
from momlib import *
from config import *
from model import Distro
from util import tree

def options(parser):
    parser.add_option("-t", "--target", type="string", metavar="TARGET",
                      default=None,
                      help="Distribution target to fetch for")
    parser.add_option("-p", "--package", type="string", metavar="PACKAGE",
                      action="append",
                      help="Process only these packages")
    parser.add_option("-D", "--source-distro", type="string", metavar="DISTRO",
                      default=None,
                      help="Source distribution")
    parser.add_option("-S", "--source-suite", type="string", metavar="SUITE",
                      default=None,
                      help="Source suite (aka distrorelease)")

def main(options, args):
    if options.target:
        targets = [options.target]
    else:
        targets = filter(lambda target: "obs" in DISTROS[DISTRO_TARGETS[target]["distro"]], DISTRO_TARGETS)

    for target in targets:
        our_distro, our_dist, our_component = get_target_distro_dist_component(target)
        distro = Distro.get(our_distro)
        for source in distro.newestSources(our_dist, our_component):
            package = source["Package"]

            if options.package is not None and package not in options.package:
                continue
            if not PACKAGELISTS.check_target(target, None, package):
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
            except IndexError:
                continue

            base = get_base(source)
            try:
                base_source = get_nearest_source(our_distro, src_distro, package, base)
            except IndexError:
                logging.debug("Attempting to fetch missing base %s_%s for %s", package, base, src_version)
                get_source(src_distro, package, base, src_source["Directory"])

def get_source(distro, package, version, sourcedir):
    """Download a source package into our pool."""
    try:
        mirror = DISTROS[distro]["mirror"]
    except:
        logging.debug("Distro '%s' has no mirror specified" % distro)
        return

    pooldir = pool_directory(distro, package)
    
    try:
        name = "%s_%s.dsc" % (package, version)
        url = "%s/%s/%s" % (mirror, sourcedir, name)
        filename = "%s/%s/%s" % (ROOT, pooldir, name)
        get_file(url, filename)
        source = SourceControl(filename)
    except:
        return

    for md5sum, size, name in files(source):
        url = "%s/%s/%s" % (mirror, sourcedir, name)
        filename = "%s/%s/%s" % (ROOT, pooldir, name)
        get_file(url, filename, size)

    update_pool_sources(distro, package)

def get_file(url, filename, size=None):
    if os.path.isfile(filename):
        if size is None or os.path.getsize(filename) == int(size):
            return

    logging.debug("Downloading %s", url)
    tree.ensure(filename)
    try:
        urllib.URLopener().retrieve(url, filename)
    except IOError as e:
        logging.error("Downloading %s failed: %s", url, e.args)
        raise
    logging.info("Saved %s", tree.subdir(ROOT, filename))

if __name__ == "__main__":
    run(main, options, usage="%prog]",
        description="download missing base versions to make 3-way merge possible")
