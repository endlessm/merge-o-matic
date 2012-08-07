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


def main(options, args):
    if len(args):
        distros = args
    else:
        distros = get_pool_distros()

    # Iterate the pool directory of the given distributions
    for distro in distros:
        d = Distro.get(distro)
        for component in d.components():
          for dist in d.dists():
            for p in d.packages(dist, component):
              p.updatePoolSource()


if __name__ == "__main__":
    run(main, usage="%prog [DISTRO...]",
        description="update the Sources file in a distribution's pool")
