#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright © 2012-2013 Collabora Ltd.
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
import os
from smtplib import SMTP

from email.MIMEMultipart import (MIMEMultipart)
from email.MIMEText import (MIMEText)
from email.Utils import (formatdate, make_msgid)

import config
from merge_report import (MergeResult, read_report)
from model.obs import (OBSDistro)
from momlib import (result_dir)
from util import (run)

logger = logging.getLogger('notify_action_needed')

def options(parser):
    parser.add_option("-t", "--target", type="string", metavar="TARGET",
                      default=None,
                      help="Process only this distribution target")

def notify_action_needed(target, output_dir, report):
    try:
        json_mtime = os.path.getmtime(output_dir + '/REPORT.json')
    except OSError as e:
        # presumably it only has an old-style REPORT; skip it
        logger.debug('Skipping package %s: %s', report.source_package, e)
        return

    try:
        if json_mtime < os.path.getmtime(output_dir + '/action_needed.eml'):
            logger.debug('already sent notification for %s', output_dir)
            return
    except OSError:
        # file is inaccessible, assume re-notification is necessary
        pass

    ROOT = config.get('ROOT')
    MOM_NAME = config.get('MOM_NAME')
    MOM_EMAIL = config.get('MOM_EMAIL')
    MOM_URL = config.get('MOM_URL')

    obs_project = report.obs_project
    if obs_project is None:
        # guess something reasonable
        obs_project = ':'.join((report.left_distro, report.left_suite,
            report.left_component))

    rel_output_dir = output_dir
    if rel_output_dir.startswith(ROOT):
        rel_output_dir = rel_output_dir[len(ROOT):]
    rel_output_dir = rel_output_dir.strip('/')

    # Some typical example subject lines:
    # [CONFLICTS] dderivative:alpha:main/curl
    # [FAILED] dderivative:alpha:main/coreutils
    # [MERGED] dderivative:alpha:main/robotfindskitten (if not committable)
    # [NO_BASE] dderivative:alpha:main/hello-debhelper
    # [SYNC_THEIRS] dderivative:alpha:main/hello       (if not committable)
    subject = '[%s] %s/%s' % (report.result, obs_project,
            report.source_package)
    logger.info('%s', subject)

    message = MIMEMultipart()
    message.add_header('From', '%s <%s>' % (MOM_NAME, MOM_EMAIL))
    message.add_header('To', '%s <%s>' % (MOM_NAME, MOM_EMAIL))
    message.add_header('Date', formatdate())
    message.add_header('Message-ID', make_msgid())
    message.add_header('X-Your-Mom', '%s %s' % (MOM_URL,
        report.source_package))
    message.add_header('Subject', subject)

    if report.result == MergeResult.CONFLICTS:
        text = ("""\
This package could not be merged: an automated 3-way merge detected conflicts.
Please carry out a manual merge and commit the result to OBS.
""")
    elif report.result == MergeResult.FAILED:
        text = ("""\
This package could not be merged for some reason. Please carry out a
manual merge and commit the result to OBS.
""")
    elif report.result == MergeResult.MERGED:
        text = ("""\
This package was merged automatically and it seems to have worked.
Please check that the result makes sense.
""")
    elif report.result == MergeResult.NO_BASE:
        text = ("""\
None of the packages' common ancestors could be found in the package pool.
This package cannot be merged until you import one.
""")
    elif report.result == MergeResult.SYNC_THEIRS:
        text = ("""\
The version in the source distribution supersedes our version.
Please check that it's OK to update to the newer version.
""")

    if report.bases_not_found:
        if report.result == MergeResult.NO_BASE:
            text = (text + """\
The most recent common ancestor was:""")
        else:
            text = (text + """
The packages' most recent common ancestor could not be found. This merge
was based on an older common ancestor, but you might get a better-quality
automatic merge if you import this version into the package pool:""")

        text += ("""
    %(base_not_found)s
If that version was in Debian or Ubuntu, you might be able to get it from:
    http://snapshot.debian.org/package/%(source_package)s/
    https://launchpad.net/ubuntu/+source/%(source_package)s
See the "bases_not_found" list in the attached JSON report for some older
versions that might also work.

Download the source package with dget(1) or similar, and put it in:
    %(right_pool_dir)s
before the next merge-o-matic run.
""" % {
            'right_pool_dir': report.right_pool_dir,
            'base_not_found': report.bases_not_found[0],
            'source_package': report.source_package,
        })

    text = (text + """
Our version in %s: %s/%s
Newest common ancestor: %s
Their version in %s:%s:%s: %s
""" % (obs_project,
        report.source_package,
        report.left_version,
        report.base_version,
        report.right_distro,
        report.right_suite,
        report.right_component,
        report.right_version))

    if report.obs_request_url is not None:
        text = (text + """
OBS submit request for the proposed version:
    %s
""" % report.obs_request_url)
    elif report.committed:
        text = (text + """
This package was successfully committed to %s/%s.
""" % (report.committed_to, report.obs_package))
    elif report.commit_detail:
        text = (text + """
A commit to OBS was attempted, but it appears to have failed:
    %s
The merge-o-matic log file might have more details.
""" % report.commit_detail)
    else:
        text = (text + """
This package was not committed to OBS.
""")

    if report.merged_patch is not None:
        text = (text + """
You can view the diff from the upstream version to the proposed version
here:
    %s/%s/%s
""" % (MOM_URL, rel_output_dir, report.merged_patch))

    if report.proposed_patch is not None:
        text = (text + """
You can view the diff from our current version to the proposed version
here:
    %s/%s/%s
""" % (MOM_URL, rel_output_dir, report.proposed_patch))

    if report.right_changelog is not None:
        text = (text + """
The upstream version's changelog is attached.
""")

    dsc = None

    for x in report.merged_files:
        if x.endswith('.dsc'):
            dsc = x

    if dsc is not None:
        text = (text + """
Download the proposed source package for testing here:
    %s/%s/%s
""" % (MOM_URL, rel_output_dir, dsc))

    if report.merge_failure_tarball is not None:
        text = (text + """
You can download a tarball containing the failed merge here:
    %s/%s/%s
""" % (MOM_URL, rel_output_dir, report.merge_failure_tarball))

    text = (text + """
A detailed merge report in JSON format is attached.
More information at:
    %(MOM_URL)s/%(rel_output_dir)s/REPORT.html

Regards,
    the Merge-o-Matic instance at <%(MOM_URL)s>
""" % {
    'MOM_URL': MOM_URL,
    'rel_output_dir': rel_output_dir,
    })

    message.attach(MIMEText(text))

    if report.right_changelog:
        cl_part = MIMEText(
                open(output_dir + '/' + report.right_changelog).read())
        cl_part.add_header('Content-Disposition', 'inline',
                filename=report.right_changelog)
        message.attach(cl_part)

    json_part = MIMEText(open(output_dir + '/REPORT.json').read())
    json_part.add_header('Content-Disposition', 'inline',
            filename='%s_REPORT.json' % report.source_package)
    message.attach(json_part)

    if 'MOM_TEST' in os.environ:
        return

    with open(output_dir + '/action_needed.eml.tmp', 'w') as email:
        email.write(message.as_string())

    all_ok = True

    smtp = SMTP('localhost')
    for addr in config.get('RECIPIENTS', default=[]):
        message.replace_header('To', addr)
        try:
            smtp.sendmail(MOM_EMAIL, addr, message.as_string())
        except:
            logger.exception('sending to %s failed:', addr)
            all_ok = False
            smtp = SMTP('localhost')

    # If all emails succeeded,
    if all_ok:
        os.rename(output_dir + '/action_needed.eml.tmp',
                output_dir + '/action_needed.eml')

def main(options, args):
    logger.debug('Sending email if actions are needed...')

    for target in config.targets(args):
        logger.debug('%r', target)
        d = target.distro

        if not isinstance(d, OBSDistro):
            logger.debug('Skipping %r distro %r: not an OBSDistro', target, d)
            continue

        for pkg in d.packages(target.dist, target.component):
            if options.package and pkg.name not in options.package:
                logger.debug('Skipping package %s: not selected', pkg.name)
                continue

            if pkg.name in target.blacklist:
                logger.debug('Skipping package %s: blacklisted', pkg.name)
                continue

            try:
                output_dir = result_dir(target.name, pkg.name)
                report = read_report(output_dir)
            except ValueError:
                logger.debug('Skipping package %s: unable to read report',
                             pkg.name)
                continue

            if report.result == MergeResult.KEEP_OURS:
                logger.debug('Skipping package %s: result=%s',
                        pkg.name, report.result)
                continue

            if (target.committable and report.result in (MergeResult.MERGED,
                    MergeResult.SYNC_THEIRS)):
                logger.debug('Skipping package %s: result=%s, would already '
                        'have been committed',
                        pkg.name, report.result)
                continue

            try:
                notify_action_needed(target, output_dir, report)
            except Exception:
                logger.exception('Error processing %s:', pkg.name)

if __name__ == "__main__":
    run(main, options, usage="%prog",
        description="send email for actions needed")
