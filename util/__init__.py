#!/usr/bin/env python
# -*- coding: utf-8 -*-
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

import time
import logging
from optparse import OptionParser
import sys

from util import shell
from util import tree


def pathhash(path):
    """Return the path hash component for path."""
    if path.startswith("lib"):
        return path[:4]
    else:
        return path[:1]


# --------------------------------------------------------------------------- #
# Command-line tool functions
# --------------------------------------------------------------------------- #
def get_option_parser(usage=None, description=None):
    parser = OptionParser(usage=usage, description=description)
    parser.add_option("-q", "--quiet", action="callback",
                      callback=quiet_callback, help="Be less chatty")
    parser.add_option("-v", "--verbose", action="callback",
                      callback=verbose_callback, help="Be more noisy")
    parser.add_option("-p", "--package", type="string", metavar="PACKAGE",
                      action="append", help="Process only this package")
    parser.add_option("-f", "--force", action="store_true",
                      help="Force processing (ignore caches and previous "
                      "merges)")
    parser.add_option("--use-upstream", help="Only consider the specified "
                      "upstream distro")
    return parser


def run(main_func, options_func=None, usage=None, description=None):
    """Run the given main function after initialising options."""
    logging.Formatter.converter = time.gmtime
    # RFC 2822
    logging.basicConfig(format="%(asctime)s  %(name)s.%(levelname)s: "
                        "%(message)s", datefmt="%a, %d %b %Y %H:%M:%S +0000")
    logging.getLogger().setLevel(logging.INFO)

    parser = get_option_parser(usage, description)
    if options_func is not None:
        options_func(parser)

    (options, args) = parser.parse_args()
    sys.exit(main_func(options, args))


def quiet_callback(opt, value, parser, *args, **kwds):
    logging.getLogger().setLevel(logging.WARNING)


def verbose_callback(opt, value, parser, *args, **kwds):
    logging.getLogger().setLevel(logging.DEBUG)


def files(source):
    """Return (md5sum, size, name) for each file."""
    files = source["Files"].strip("\n").split("\n")
    return [f.split(None, 2) for f in files]
