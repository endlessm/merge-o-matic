#!/usr/bin/env python
# -*- coding: utf-8 -*-
# config.py - configuration API
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

import sys

MOM_CONFIG_PATH = "/etc/merge-o-matic"
sys.path.insert(1, MOM_CONFIG_PATH)
import momsettings
sys.path.remove(MOM_CONFIG_PATH)

def get(*args, **kwargs):
  def _get(item, *args, **kwargs):
    if len(args) == 0:
      return item
    if hasattr(item, args[0]):
      return _get(getattr(item, args[0]), *(args[1:]), **kwargs)
    if hasattr(item, "__iter__"):
      if args[0] in item:
        return _get(item[args[0]], *(args[1:]), **kwargs)
    return kwargs.setdefault("default", None)
  return _get(momsettings, *args, **kwargs)
