#!/usr/bin/env python
# -*- coding: utf-8 -*-
# update-sources.py - update the Sources files in a distribution's pool
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

import sys
import os

from model import Distro
from momlib import *
import config
import model.error


def main(options, args):
    for target in config.targets(args):
      d = target.distro
      d.updateSources(target.dist, target.component)
      d.updatePool(target.dist, target.component)
      for upstreamList in target.sources:
        for source in upstreamList:
          for component in source.distro.components():
            source.distro.updateSources(source.dist, component)
      for package in target.distro.packages(target.dist, target.component):
        package.updatePoolSource()
        for source in upstreamList:
          try:
            upstreamPkg = source.distro.findPackage(package.name, dist=source.dist)
            upstreamPkg.updatePool()
            upstreamPkg.updatePoolSource()
          except model.error.PackageNotFound:
            pass


if __name__ == "__main__":
    run(main, usage="%prog [DISTRO...]",
        description="update the Sources file in a distribution's pool")
