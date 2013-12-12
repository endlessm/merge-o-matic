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

def notify_action_needed(target, output_dir, source, report):
    try:
        if (os.path.getmtime(output_dir + '/REPORT.json') <
                os.path.getmtime(output_dir + '/action_needed.eml')):
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

    if report.bases_not_found and report.result != MergeResult.NO_BASE:
        text = (text + """\
The packages' most recent common ancestor could not be found. This merge
was based on an older common ancestor, but you might get a better-quality
automatic merge if you import this version into the package pool:
    %s
""" % report.bases_not_found[0])

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

    if report.merged_patch is not None:
        text = (text + """
You can view the diff from our previous version to the proposed version
here:
    %s/%s/%s
""" % (MOM_URL, rel_output_dir, report.merged_patch))

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

Regards,
    the Merge-o-Matic instance at <%s>
""" % MOM_URL)

    message.attach(MIMEText(text))
    json_part = MIMEText(open(output_dir + '/REPORT.json').read())
    json_part.add_header('Content-Disposition', 'inline',
            filename='%s_REPORT.json' % report.source_package)
    message.attach(json_part)

    with open(output_dir + '/action_needed.eml.tmp', 'w') as email:
        email.write(message.as_string())

    all_ok = True

    for x in config.get('RECIPIENTS', default=[]):
        # FIXME: actually try to send the mail
        all_ok = False

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

        for source in d.newestSources(target.dist, target.component):
            if options.package and source['Package'] not in options.package:
                logger.debug('Skipping package %s: not selected',
                        source['Package'])
                continue

            if source['Package'] in target.blacklist:
                logger.debug('Skipping package %s: blacklisted',
                        source['Package'])
                continue

            try:
                output_dir = result_dir(target.name, source['Package'])
                report = read_report(output_dir)
            except ValueError:
                logger.debug('Skipping package %s: unable to read report',
                    source['Package'])
                continue

            if report.result == MergeResult.KEEP_OURS:
                logger.debug('Skipping package %s: result=%s',
                        source['Package'], report.result)
                continue

            if (target.committable and report.result in (MergeResult.MERGED,
                    MergeResult.SYNC_THEIRS)):
                logger.debug('Skipping package %s: result=%s, would already '
                        'have been committed',
                        source['Package'], report.result)
                continue

            try:
                notify_action_needed(target, output_dir, source, report)
            except Exception:
                logger.exception('Error processing %s:', source['Package'])

if __name__ == "__main__":
    run(main, options, usage="%prog",
        description="send email for actions needed")
