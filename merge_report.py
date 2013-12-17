#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright © 2008 Canonical Ltd.
# Copyright © 2013 Collabora Ltd.
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

class MergeResult(str):
    def __new__(cls, s):
        s = s.upper()

        if s in cls.__dict__:
            return cls.__dict__[s]

        raise ValueError('Not a MergeResult: %r' % s)

    def __repr__(self):
        return 'MergeResult(%r)' % str(self)

# We have to bypass MergeResult.__new__ here, to avoid chicken/egg:
# we're ensuring that there are constants in MergeResult.__dict__ so
# that MergeResult.__new__ will work :-)
MergeResult.UNKNOWN = str.__new__(MergeResult, 'UNKNOWN')
MergeResult.NO_BASE = str.__new__(MergeResult, 'NO_BASE')
MergeResult.SYNC_THEIRS = str.__new__(MergeResult, 'SYNC_THEIRS')
MergeResult.KEEP_OURS = str.__new__(MergeResult, 'KEEP_OURS')
MergeResult.FAILED = str.__new__(MergeResult, 'FAILED')
MergeResult.MERGED = str.__new__(MergeResult, 'MERGED')
MergeResult.CONFLICTS = str.__new__(MergeResult, 'CONFLICTS')
