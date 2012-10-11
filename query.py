#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright © 2012 Collabora
# Author: Trever Fischer <tdfischer@fedoraproject.org>
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

import config
import model.error
from util import run

def options(parser):
  parser.add_option("-m", "--merges", action="store_true",
                    help="Only list packages that need merged")
  parser.add_option("-s", "--sync", action="store_true",
                    help="Only list packages that need synced")

def main(options, args):
  pkglist = []
  if options.package:
    pkglist = options.package
  else:
    for target in config.targets(args):
      for pkg in target.distro.packages(target.dist, target.component):
        pkglist.append(pkg.name)
  for pkgname in pkglist:
    namePrinted = False
    for target in config.targets(args):
      try:
        pkg = target.distro.package(target.dist, target.component, pkgname)
      except model.error.PackageNotFound:
        continue
      our_version = pkg.newestVersion()
      for srclist in target.sources:
        upstream = None
        for src in srclist:
          try:
            possible = src.distro.findPackage(pkg.name,
                searchDist=src.dist)[0]
            if upstream is None or possible > upstream:
              upstream = possible
          except model.error.PackageNotFound:
            pass
      base = target.findNearestVersion(pkg.newestVersion())
      if options.merges and (not upstream or not our_version.version <
        upstream.version):
        continue
      if options.sync and (not upstream or not base.version ==
          our_version.version):
        continue
      if not namePrinted:
        print "%s:"%(pkgname)
        namePrinted = True
      print "\t%s/%s: %s"%(pkg.dist, pkg.component, our_version.version)
      if pkgname in target.blacklist:
        print "\t\tblacklisted"
      print "\t\tBase: %s"%(base)
      if upstream:
        print "\t\t%s/%s: %s"%(upstream.package.dist, upstream.package.component,
            upstream.version)
        if upstream.version == our_version.version:
          print "\t\tUnmodified"
        elif base > upstream:
          print "\t\tLocally repackaged"
        elif base.version == our_version.version:
          print "\t\tNeeds sync"
        elif our_version.version < upstream.version:
          print "\t\tNeeds merge"
        else:
          print "\t\tModified"
      else:
        print "\t\tNo upstream."

if __name__ == "__main__":
  run(main, options, usage="%prog",
      description="Ask MoM stuff")
