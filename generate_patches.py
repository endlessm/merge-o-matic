#!/usr/bin/env python
# -*- coding: utf-8 -*-
# generate-patches.py - generate patches between distributions
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

import logging
from re import search

import config
from deb.version import Version
from model import Distro
import model.error
from momlib import *
from util import tree, run


def generate_patch(base, distro, ours,
                   slipped=False, force=False, unpacked=False):
    """Generate a patch file for the given comparison."""
    if base.version > ours.version:
        # Allow comparison of source -1 against our -0coX (slipped)
        if not slipped:
            return
        elif ours.version.revision is None:
            return
        elif not ours.version.revision.startswith("0co"):
            return
        elif base.version.revision != "1":
            return
        elif base.version.upstream != ours.version.upstream:
            return
        elif base.version.epoch != ours.version.epoch:
            return

        logging.debug("Allowing comparison of -1 against -0coX")
    elif base.version == ours.version:
        return

    filename = patch_file(distro, ours, slipped)
    if not force:
        basis = read_basis(filename)
        if basis is not None and basis == base.version:
            return

    if not os.path.exists(filename):
        if not unpacked:
            unpack_source(base)
            unpack_source(ours)

        tree.ensure(filename)
        save_patch_file(filename, base, ours)
        save_basis(filename, base.version)
        logging.info("Saved patch file: %s", tree.subdir(config.get('ROOT'),
                                                         filename))
