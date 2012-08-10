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
import logging
import tempfile
import json
import time
import urllib
import model
from os import path

MOM_CONFIG_PATH = "/etc/merge-o-matic"
sys.path.insert(1, MOM_CONFIG_PATH)
import momsettings
configdb = momsettings
sys.path.remove(MOM_CONFIG_PATH)

SOURCES_CACHE = {}

def loadConfig(data):
  global configdb
  configdb = data

def get(*args, **kwargs):
  def _get(item, *args, **kwargs):
    global configdb
    if len(args) == 0:
      return item
    if hasattr(item, args[0]):
      return _get(getattr(item, args[0]), *(args[1:]), **kwargs)
    if hasattr(item, "__iter__"):
      if args[0] in item:
        return _get(item[args[0]], *(args[1:]), **kwargs)
    return kwargs.setdefault("default", None)
  return _get(configdb, *args, **kwargs)

class Source(object):
  def __init__(self, distro, dist):
    super(Source, self).__init__()
    self._distro = model.Distro.get(distro)
    self._dist = dist

  @property
  def distro(self):
    return self._distro

  @property
  def dist(self):
    return self._dist

class SourceList(object):
  def __init__(self, name):
    super(SourceList, self).__init__()
    self._name = name
    self._sources = map(lambda x:Source(x['distro'], x['dist']), get('DISTRO_SOURCES', self._name))

  @property
  def name(self):
    return self._name

  def __iter__(self):
    return self._sources.__iter__()

  def __getitem__(self, i):
    return self._sources[i]

class Target(object):
  def __init__(self, name):
    super(Target, self).__init__()
    self._name = name

  def config(self, *args, **kwargs):
    args = (self._name,)+args
    return get('DISTRO_TARGETS', *args, **kwargs)

  @property
  def distro(self):
    return model.Distro.get(self.config('distro'))

  @property
  def dist(self):
    return self.config('dist')

  @property
  def component(self):
    return self.config('component')

  @property
  def sources(self):
    return map(SourceList, self.config('sources', default=[]))

  @property
  def committable(self):
    return self.config('commit', default=False)

def targets(names=[]):
  if len(names) == 0:
    names = get('DISTRO_TARGETS').keys()
  return map(Target, names)
