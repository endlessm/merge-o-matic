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
import model.error
from util import tree, run
import config

def options(parser):
    parser.add_option("-t", "--target", type="string", metavar="TARGET",
                      default=None,
                      help="Distribution target to fetch for")
    parser.add_option("-D", "--source-distro", type="string", metavar="DISTRO",
                      default=None,
                      help="Source distribution")
    parser.add_option("-S", "--source-suite", type="string", metavar="SUITE",
                      default=None,
                      help="Source suite (aka distrorelease)")

def main(options, args):
    for target in config.targets(args):
      distro = target.distro
      for pkg in distro.packages(target.dist, target.component):
        if options.package is not None and pkg.name not in options.package:
          continue

        try:
          base = target.findNearestVersion(pkg.newestVersion())
          if base > pkg.newestVersion():
            raise IndexError
        except IndexError:
          logging.debug("Attempting to fetch missing base %s for %s",
              pkg.newestVersion().version.base(), pkg.newestVersion())
          target.fetchMissingVersion(pkg, pkg.newestVersion().version.base())

if __name__ == "__main__":
    run(main, options, usage="%prog]",
        description="download missing base versions to make 3-way merge possible")
