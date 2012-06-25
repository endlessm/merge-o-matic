#!/usr/bin/env python
# -*- coding: utf-8 -*-
# syndicate.py - send out e-mails and update rss feeds
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

from __future__ import with_statement

import os
import bz2
import fcntl
import logging

from email.MIMEMultipart import MIMEMultipart
from email.MIMEText import MIMEText
from email.Utils import formatdate, make_msgid, parseaddr
from fnmatch import fnmatch
from smtplib import SMTP, SMTPSenderRefused, SMTPDataError

from momlib import *
from deb.controlfile import ControlFile
from deb.version import Version


def options(parser):
    parser.add_option("-p", "--package", type="string", metavar="PACKAGE",
                      action="append",
                      help="Process only these packages")
    parser.add_option("-t", "--target", type="string", metavar="TARGET",
                      default=None,
                      help="Process only this distribution target")

def main(options, args):
    if options.target is not None:
        target_distro, target_dist, target_component = get_target_distro_dist_component(options.target)
        distros = [target_distro]
    elif len(args):
        distros = args
    else:
        distros = get_pool_distros()

    subscriptions = read_subscriptions()

    patch_rss = read_rss(patch_rss_file(),
                         title="DISTRO Merge-o-Matic Patches from Ubuntu",
                         link=MOM_URL,
                         description="This feed announces new patches from "
                         "DISTRO to Ubuntu, each patch filename contains "
                         "the complete difference between the two "
                         "distributions for that package.")

    diff_rss = read_rss(diff_rss_file(),
                        title="DISTRO Merge-o-Matic Uploads",
                        link=MOM_URL + "by-release/atomic/",
                        description="This feed announces new changes in DISTRO"
                        ", each patch filename contains the difference "
                        "between the new version and the previous one.")


    # For latest version of each package in the given distributions, iterate the pool in order
    # and select various interesting files for syndication
    for distro in distros:
        if options.target is None:
            dists = DISTROS[distro]["dists"]
        else:
            dists = [target_dist]
        for dist in dists:
            if options.target is None:
                components = DISTROS[distro]["components"]
            else:
                components = [target_component]
            for component in components:
                for source in get_newest_sources(distro, dist, component):
                    if options.package is not None \
                           and source["Package"] not in options.package:
                        continue
                    if not PACKAGELISTS.check_any_distro(distro, dist, source["Package"]):
                        continue

                    watermark = read_watermark(distro, source)
                    sources = get_pool_sources(distro, source["Package"])
                    version_sort(sources)

                    for this in sources:
                        if watermark < this["Version"]:
                            break
                    else:
                        continue

                    this_patch_rss = read_rss(patch_rss_file(distro, source),
                                             title="DISTRO Merge-o-Matic Patches from Ubuntu for %s" % source["Package"],
                                             link=(MOM_URL + "by-release/" +
                                                   tree.subdir("%s/patches" % ROOT,
                                                               patch_directory(distro, source))),
                                              description="This feed announces new patches from "
                                              "DISTRO to Ubuntu for %s, each patch filename contains "
                                              "the complete difference between the two "
                                              "distributions for that package." % source["Package"])
                    this_diff_rss = read_rss(diff_rss_file(distro, source),
                                             title="DISTRO Merge-o-Matic Uploads for %s" % source["Package"],
                                             link=(MOM_URL + "by-release/atomic/" +
                                                   tree.subdir("%s/diffs" % ROOT,
                                                               diff_directory(distro, source))),
                                             description="This feed announces new changes in DISTRO "
                                             "for %s, each patch filename contains the difference "
                                             "between the new version and the previous one." % source["Package"])

                    last = None
                    for this in sources:
                        if watermark >= this["Version"]:
                            last = this
                            continue

                        logging.debug("%s: %s %s", distro,
                                      this["Package"], this["Version"])

                        changes_filename = changes_file(distro, this)
                        if os.path.isfile(changes_filename):
                            changes = open(changes_filename)
                        elif os.path.isfile(changes_filename + ".bz2"):
                            changes = bz2.BZ2File(changes_filename + ".bz2")
                        else:
                            logging.warning("Missing changes file")
                            continue

                        # Extract the author's e-mail from the changes file
                        try:
                            info = ControlFile(fileobj=changes,
                                               multi_para=False,
                                               signed=False).para
                            if "Changed-By" not in info:
                                uploader = None
                            else:
                                uploader = parseaddr(info["Changed-By"])[-1]
                        finally:
                            changes.close()

                        update_feeds(distro, last, this, uploader,
                                     patch_rss, this_patch_rss,
                                     diff_rss, this_diff_rss)

                        try:
                            mail_diff(distro, last, this, uploader,
                                      subscriptions)
                        except MemoryError:
                            logging.error("Ran out of memory")

                        last = this

                    write_rss(patch_rss_file(distro, source), this_patch_rss)
                    write_rss(diff_rss_file(distro, source), this_diff_rss)
                    save_watermark(distro, source, this["Version"])

    write_rss(patch_rss_file(), patch_rss)
    write_rss(diff_rss_file(), diff_rss)

def distro_is_src(distro):
    for src in DISTRO_SOURCES:
        for sub_src in DISTRO_SOURCES[src]:
            if distro == sub_src["distro"]:
                return True
    return False

def distro_is_target(distro):
    for target in DISTRO_TARGETS:
        if distro == DISTRO_TARGETS[target]["distro"]:
                return True
    return False

def mail_diff(distro, last, this, uploader, subscriptions):
    """Mail a diff out to the subscribers."""
    recipients = get_recipients(distro, this["Package"],
                                uploader, subscriptions)
    if not len(recipients):
        return

    if distro_is_src(distro):
        # Source distro uploads always just have a diff
        subject = "%s %s %s" % (distro, this["Package"], this["Version"])
        intro = MIMEText("""\
This e-mail has been sent due to an upload to %s, and contains the
difference between the new version and the previous one.""" % distro)
        payload = diff_part(distro, this)
    elif not distro_is_target(distro):
        # Ignore distros which are neither source nor target
        return
    elif get_base(this) == this["Version"]:
        # Never e-mail our uploads without local changes
        return
    elif last is None:
        # Our initial uploads, send the patch
        subject = "DISTRO (new) %s %s" % (this["Package"], this["Version"])
        intro = MIMEText("""\
This e-mail has been sent due to an upload to DISTRO of a new source package
which already contains DISTRO changes.  It contains the difference between
the DISTRO version and the equivalent base version in Ubuntu.""")
        payload = patch_part(distro, this)
    elif get_base(last) != get_base(this):
        # We changed upstream version, send the patch
        subject = "DISTRO (new upstream) %s %s"\
                  % (this["Package"], this["Version"])
        intro = MIMEText("""\
This e-mail has been sent due to an upload to DISTRO of a new upstream
version which still contains DISTRO changes.  It contains the difference
between the DISTRO version and the equivalent base version in Ubuntu, note
that this difference may include the upstream changes.""")
        payload = patch_part(distro, this)
    else:
        # Our revision, send the diff
        subject = "Ubuntu %s %s" % (this["Package"], this["Version"])
        intro = MIMEText("""\
This e-mail has been sent due to an upload to DISTRO that contains DISTRO
changes.  It contains the difference between the new version and the
previous version of the same source package in DISTRO.""")
        payload = diff_part(distro, this)

    # Allow patches to be missing (no Ubuntu version)
    if payload is None:
        return

    # Extract the changes file
    changes_filename = changes_file(distro, this)
    if os.path.isfile(changes_filename):
        changes = MIMEText(open(changes_filename).read())
    elif os.path.isfile(changes_filename + ".bz2"):
        changes = MIMEText(bz2.BZ2File(changes_filename + ".bz2").read())
    changes.add_header("Content-Disposition", "inline",
                       filename="%s" % os.path.basename(changes_filename))

    # Build up the message
    message = MIMEMultipart()
    message.add_header("From", "%s <%s>" % (MOM_NAME, MOM_EMAIL))
    message.add_header("To", "%s <%s>" % (MOM_NAME, MOM_EMAIL))
    message.add_header("Date", formatdate())
    message.add_header("Subject", subject)
    message.add_header("Message-ID", make_msgid())
    message.add_header("X-Your-Mom", "%s %s" % (MOM_URL, this["Package"]))
    message.add_header("X-PTS-Approved", "yes")
    message.attach(intro)
    message.attach(changes)
    message.attach(payload)

    send_message(message, recipients)

def patch_part(distro, this):
    """Construct an e-mail part containing the current patch."""
    patch_filename = patch_file(distro, this, True)
    if os.path.isfile(patch_filename):
        part = MIMEText(open(patch_filename).read())
    elif os.path.isfile(patch_filename + ".bz2"):
        part = MIMEText(bz2.BZ2File(patch_filename + ".bz2").read())
    else:
        patch_filename = patch_file(distro, this, False)
        if os.path.isfile(patch_filename):
            part = MIMEText(open(patch_filename).read())
        elif os.path.isfile(patch_filename + ".bz2"):
            part = MIMEText(bz2.BZ2File(patch_filename + ".bz2").read())
        else:
            return None

    part.add_header("Content-Disposition", "attachment",
                    filename="%s" % os.path.basename(patch_filename))
    return part

def diff_part(distro, this):
    """Construct an e-mail part containing the current diff."""
    diff_filename = diff_file(distro, this)
    if os.path.isfile(diff_filename):
        part = MIMEText(open(diff_filename).read())
    elif os.path.isfile(diff_filename + ".bz2"):
        part = MIMEText(bz2.BZ2File(diff_filename + ".bz2").read())
    else:
        return None

    part.add_header("Content-Disposition", "attachment",
                    filename="%s" % os.path.basename(diff_filename))
    return part


def get_recipients(distro, package, uploader, subscriptions):
    """Figure out who should receive this message."""
    recipients = []

    for sub_addr, sub_distro, sub_filter in subscriptions:
        sub_addr = sub_addr.replace("%s", package)

        if sub_distro != distro:
            continue

        if sub_filter.startswith("my:"):
            sub_filter = sub_filter[3:]

            if uploader != sub_addr:
                continue

        if not fnmatch(package, sub_filter):
            continue

        recipients.append(sub_addr)

    return recipients

def send_message(message, recipients):
    """Send out a message to everyone subscribed to it."""
    smtp = SMTP("localhost")

    for addr in recipients:
        if "##" in addr:
            (env_addr, addr) = addr.split("##")
        else:
            env_addr = addr

        logging.debug("Sending to %s", addr)
        message.replace_header("To", addr)

        try:
            smtp.sendmail(MOM_EMAIL, env_addr , message.as_string())
        except (SMTPSenderRefused, SMTPDataError):
            logging.exception("smtp failed")
            smtp = SMTP("localhost")

    smtp.quit()


def update_feeds(distro, last, this, uploader, patch_rss, this_patch_rss,
                 diff_rss, this_diff_rss):
    """Update the various RSS feeds."""
    patch_filename = patch_file(distro, this, True)
    if os.path.isfile(patch_filename):
        pass
    elif os.path.isfile(patch_filename + ".bz2"):
        patch_filename += ".bz2"
    else:
        patch_filename = patch_file(distro, this, False)
        if os.path.isfile(patch_filename):
            pass
        elif os.path.isfile(patch_filename + ".bz2"):
            patch_filename += ".bz2"
        else:
            patch_filename = None

    if patch_filename is not None:
        append_rss(patch_rss,
                   title=os.path.basename(patch_filename),
                   link=(MOM_URL + "by-release/" +
                         tree.subdir("%s/patches" % ROOT, patch_filename)),
                   author=uploader,
                   filename=patch_filename)

        append_rss(this_patch_rss,
                   title=os.path.basename(patch_filename),
                   link=(MOM_URL + "by-release/" +
                         tree.subdir("%s/patches" % ROOT, patch_filename)),
                   author=uploader,
                   filename=patch_filename)

    diff_filename = diff_file(distro, this)
    if os.path.isfile(diff_filename):
        pass
    elif os.path.isfile(diff_filename + ".bz2"):
        diff_filename += ".bz2"
    else:
        diff_filename = None

    if diff_filename is not None:
        append_rss(diff_rss,
                   title=os.path.basename(diff_filename),
                   link=(MOM_URL + "by-release/atomic/" +
                         tree.subdir("%s/diffs" % ROOT, diff_filename)),
                   author=uploader,
                   filename=diff_filename)

        append_rss(this_diff_rss,
                   title=os.path.basename(diff_filename),
                   link=(MOM_URL + "by-release/atomic/" +
                         tree.subdir("%s/diffs" % ROOT, diff_filename)),
                   author=uploader,
                   filename=diff_filename)


def read_subscriptions():
    """Read the subscriptions file."""
    subscriptions = []

    subscriptions_filename = "%s/subscriptions.txt" % ROOT
    if not os.path.exists(subscriptions_filename):
        return subscriptions

    with open(subscriptions_filename) as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_SH)

        for line in f:
            if line.startswith("#"):
                continue

            (addr, distro, filter) = line.strip().split()
            subscriptions.append((addr, distro, filter))

    return subscriptions

def read_watermark(distro, source):
    """Read the watermark for a given source."""
    mark_file = "%s/%s/watermark" \
                % (ROOT, pool_directory(distro, source["Package"]))
    if not os.path.isfile(mark_file):
        return Version("0")

    with open(mark_file) as mark:
        return Version(mark.read().strip())

def save_watermark(distro, source, version):
    """Save the watermark for a given source."""
    mark_file = "%s/%s/watermark" \
                % (ROOT, pool_directory(distro, source["Package"]))
    with open(mark_file, "w") as mark:
        print >>mark, "%s" % version


if __name__ == "__main__":
    run(main, options, usage="%prog [DISTRO...]",
        description="send out e-mails and update rss feeds")
