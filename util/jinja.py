#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright © 2010-2013 by the Jinja team, see jinja2-AUTHORS
# Copyright © 2014 Collabora Ltd.
#
# Some rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#
#     * Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#
#     * Redistributions in binary form must reproduce the above
#       copyright notice, this list of conditions and the following
#       disclaimer in the documentation and/or other materials provided
#       with the distribution.
#
#     * The names of the contributors may not be used to endorse or
#       promote products derived from this software without specific
#       prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import sys


def patch_environment(env):
    """Give a jinja2 environment a backported urlencode filter."""
    if 'urlencode' not in env.filters:
        env.filters['urlencode'] = do_urlencode


# Code below this point is an excerpt from jinja2 version 2.7.2

PY2 = sys.version_info[0] == 2
if not PY2:
    text_type = str
    string_types = (str,)
    iteritems = lambda d: iter(d.items())
else:
    text_type = unicode
    string_types = (str, unicode)
    iteritems = lambda d: d.iteritems()

try:
    from urllib.parse import quote_from_bytes as url_quote
except ImportError:
    from urllib import quote as url_quote


def unicode_urlencode(obj, charset='utf-8'):
    """URL escapes a single bytestring or unicode string with the
    given charset if applicable to URL safe quoting under all rules
    that need to be considered under all supported Python versions.

    If non strings are provided they are converted to their unicode
    representation first.
    """
    if not isinstance(obj, string_types):
        obj = text_type(obj)
    if isinstance(obj, text_type):
        obj = obj.encode(charset)
    return text_type(url_quote(obj))


def do_urlencode(value):
    """Escape strings for use in URLs (uses UTF-8 encoding).  It accepts both
    dictionaries and regular strings as well as pairwise iterables.

    .. versionadded:: 2.7
    """
    itemiter = None
    if isinstance(value, dict):
        itemiter = iteritems(value)
    elif not isinstance(value, string_types):
        try:
            itemiter = iter(value)
        except TypeError:
            pass
    if itemiter is None:
        return unicode_urlencode(value)
    return u'&'.join(unicode_urlencode(k) + '=' +
                     unicode_urlencode(v) for k, v in itemiter)
