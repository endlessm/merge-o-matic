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
import json
import urllib2

import osc.core

from momlib import *
from deb.version import Version
from deb.controlfile import ControlFile
from model import Distro, UpdateInfo
from model.obs import OBSDistro
import config
import model.error
import logging
from util import run

logger = logging.getLogger('update_sources')

SNAPSHOT_BASE = 'http://snapshot.debian.org'


# Get the list of available versions archived on snapshot.debian.org
def get_debian_snapshot_versions(package_name):
    url = '%s/mr/package/%s/' % (SNAPSHOT_BASE, package_name)
    try:
        fd = urllib2.urlopen(url)
        data = json.load(fd)
    except urllib2.HTTPError, e:
        if e.code == 404:
            return []
        raise
    except urllib2.URLError, e:
        if isinstance(e.reason, OSError) and e.reason.errno == errno.ENOENT:
            return []
        raise

    versions = []
    for vdict in data['result']:
        versions.append(Version(vdict['version']))

    return versions


def debsnap_get_file_hash(data, filename):
    # Find the sha1 hash for a given file from the debsnap data
    for filehash, files in data['fileinfo'].iteritems():
        for fileinfo in files:
            if fileinfo['name'] == filename:
                return filehash
    return None


def debsnap_download_file(url, output_path):
    # Download a specific file from debsnap
    logging.debug('Downloading debsnap file %s', url)
    fd = urllib2.urlopen(url)
    with open(output_path, 'w') as output:
        output.write(fd.read())


def download_from_debsnap(target_dir, package_name, version):
    # Download a given package version from debsnap
    url = '%s/mr/package/%s/%s/srcfiles?fileinfo=1' % \
          (SNAPSHOT_BASE, package_name, version)
    logging.debug('Fetching debsnap metadata %s', url)
    fd = urllib2.urlopen(url)
    data = json.load(fd)

    dsc_name = '%s_%s.dsc' % (package_name, version.without_epoch)
    dsc_hash = debsnap_get_file_hash(data, dsc_name)
    dsc_path = os.path.join(target_dir, dsc_name)
    dsc_path_tmp = '%s.tmp' % dsc_path

    url = '%s/file/%s' % (SNAPSHOT_BASE, dsc_hash)
    debsnap_download_file(url, dsc_path_tmp)

    dsc_data = ControlFile(dsc_path_tmp, multi_para=False, signed=True).para
    for filehash, size, filename in files(dsc_data):
        snapshot_hash = debsnap_get_file_hash(data, filename)
        url = '%s/file/%s' % (SNAPSHOT_BASE, snapshot_hash)
        path = os.path.join(target_dir, filename)
        debsnap_download_file(url, path)

    # Atomically put the .dsc file in place as the last step, making the
    # pool entry valid.
    os.rename(dsc_path_tmp, dsc_path)
    logger.info('Downloaded %s base %s from debsnap', package_name, version)
    return True


def find_upstream(target, pv, specific_upstream=None):
    upstream = None
    package_name = pv.package.name
    our_base_version = pv.version.base()

    if specific_upstream:
        sourcelists = [config.SourceList(specific_upstream)]
    else:
        sourcelists = target.getSourceLists(package_name,
                                            include_unstable=False)

    for srclist in sourcelists:
        for src in srclist:
            logger.debug('considering source %s', src)
            try:
                for possible in src.distro.findPackage(package_name,
                                                       searchDist=src.dist):
                    logger.debug('- contains version %s', possible)
                    if upstream is None or possible > upstream:
                        logger.debug('    - that version is the best yet seen')
                        upstream = possible
            except model.error.PackageNotFound:
                pass

    # There are two situations in which we will look in unstable distros
    # for a better version:
    try_unstable = False

    # 1. If our version is newer than the stable upstream version, we
    #        assume that our version was sourced from unstable, so let's
    #        check for an update there.
    #        However we must use the base version for the comparison here,
    #        otherwise we would consider our version 1.0-1endless1 newer
    #        than the stable 1.0-1 and look in unstable for an update.
    if upstream is not None and pv.version >= upstream.version:
        logger.debug("our version %s >= their version %s, "
                     "checking base version %s",
                     pv, upstream, our_base_version)
        if our_base_version > upstream.version:
            logger.debug("base version still newer than their version, "
                         "checking in unstable")
            try_unstable = True

    # 2. If we didn't find any upstream version at all, it's possible
    #        that it's a brand new package where our version was imported
    #        from unstable, so let's see if we can find a better version
    #        there.
    if upstream is None:
        try_unstable = True

    # However, if this package has been assigned a specific source,
    # we'll honour that.
    if target.packageHasSpecificSource(package_name):
        try_unstable = False

    if try_unstable:
        for srclist in target.unstable_sources:
            for src in srclist:
                logger.debug('considering unstable source %s', src)
                try:
                    for possible in src.distro.findPackage(
                            package_name, searchDist=src.dist):
                        logger.debug('- contains version %s', possible)
                        if upstream is None or possible > upstream:
                            logger.debug('    - that version is the best '
                                         'yet seen')
                            upstream = possible
                except model.error.PackageNotFound:
                    pass

            # Stop at the first upstream that provides a version upgrade
            if upstream is not None and upstream.version >= our_base_version:
                break

    return upstream


def find_and_download_package(target, package_name, version):
    # Try to find the requested package in the target distro, just in case
    # it is there
    try:
        pv = target.distro.findPackage(package_name, searchDist=target.dist,
                                       version=version)
        pv.download()
    except model.error.PackageNotFound:
        pass

    # Try all the source distros
    for source_list in target.getAllSourceLists():
        try:
            pv = source_list.findPackage(package_name, version)[0]
            pv.download()
            logger.info('Downloaded %s base version %s from distros',
                        package_name, pv.version)
            return True
        except model.error.PackageNotFound:
            pass

    logger.debug('Did not find %s base %s in distros', package_name, version)
    return False


def download_removed_package(target_dir, target, package_name, version):
    # As a last ditch attempt, see if we can find the version we are looking
    # for lying around on the distro server. This assumes that Debian leaves
    # old versions around on the servers for a bit, even when they have been
    # removed from the Sources file, in hope that clients who are not
    # fully synced can still download the old versions.

    # We try this on just one of the upstreams - the first one we find that
    # indexes a package version newer than the one we are looking for.
    found = None
    for pv in target.findSourcePackage(package_name):
        if pv.version >= version:
            found = pv
            break

    if not found:
        return False

    mirror = found.package.distro.mirrorURL()
    pooldir = found.package.getCurrentSources()[0]['Directory']
    name = "%s_%s.dsc" % (package_name, version.without_epoch)
    url = "%s/%s/%s" % (mirror, pooldir, name)
    dsc_file = "%s/%s" % (target_dir, name)
    dsc_file_tmp = "%s.tmp" % dsc_file
    logger.debug("Downloading %s to %s", url, dsc_file_tmp)
    try:
        fd = urllib2.urlopen(url)
        open(dsc_file_tmp, 'w').write(fd.read())
    except urllib2.HTTPError, e:
        if e.code == 404:
            return False
        raise

    dsc_data = ControlFile(dsc_file_tmp, multi_para=False, signed=True).para
    for md5sum, size, name in files(dsc_data):
        url = "%s/%s/%s" % (mirror, pooldir, name)
        outfile = "%s/%s" % (target_dir, name)
        try:
            fd = urllib2.urlopen(url)
            open(outfile, 'w').write(fd.read())
        except urllib2.HTTPError, e:
            if e.code == 404:
                return False
            raise

    # Atomically put the .dsc file in place as the last step, making it's
    # entry in the pool valid.
    os.rename(dsc_file_tmp, dsc_file)
    logger.info('Downloaded removed package %s %s', package_name, version)
    return True


# Set the stage for updating a specific package
def handle_package(target, package, force=False, specific_upstream=None):
    # Store our results in a UpdateInfo file and use that to avoid repeating
    # the work we do below.
    update_info = UpdateInfo(package)

    # Find the PackageVersion that we will look to update from upstream,
    # and download its sources.
    pv = package.newestVersion()
    logger.debug('Handling package %s with UpdateInfo %s', pv, update_info)
    pv.download()

    # Look at the upstreams and figure out which is the right version to
    # upgrade to.
    upstream = find_upstream(target, pv, specific_upstream)
    if upstream is not None:
        upstream_version = upstream.version
    else:
        upstream_version = None

    # Make that new version available for the upgrade process
    if upstream is not None and upstream > pv:
        upstream.download()

    # If UpdateInfo is already recorded to upgrade this version to the
    # detected upstream (or a better version), then nothing has changed since
    # last time and we do not need to repeat that work.
    if not force and update_info.version == pv.version \
            and ((update_info.upstream_version is not None
                  and upstream_version is not None
                  and update_info.upstream_version >= upstream_version)
                 or update_info.upstream_version == upstream_version):
        logger.debug('Using existing base info for base=%s upstream=%s',
                     pv, upstream)
        return

    update_info.set_version(pv.version)
    update_info.set_upstream_version(upstream_version)
    update_info.set_specific_upstream(specific_upstream)

    # Now we try to figure out which version that our package is based
    # upon, and we make a strong effort to download that version to
    # a local pool.
    base_version = pv.version.base()
    update_info.set_base_version(base_version)

    # If our version number is the same as the base then that means
    # we have taken the package as-is from upstream, so no merging
    # is necessary.
    if base_version == pv.version:
        logger.debug('%s is unmodified from upstream', pv)
        update_info.save()
        return

    # If we already have the base version present in a local pool
    # then we have nothing else to do.
    pool_versions = target.getAllPoolVersions(pv.package.name)
    pool_versions = map(lambda x: x.version, pool_versions)
    if base_version in pool_versions:
        logger.info('%s base %s was found in local pool', pv, base_version)
        update_info.save()
        return

    # Look for the base package in one of our standard distros and
    # download it from there.
    if find_and_download_package(target, pv.package.name, base_version):
        update_info.save()
        return

    # Fall back on checking snapshot.debian.org
    debsnap_versions = get_debian_snapshot_versions(pv.package.name)
    if base_version in debsnap_versions:
        ret = download_from_debsnap(pv.package.poolPath, pv.package.name,
                                    base_version)
        if ret:
            update_info.save()
            return

    # Fall back on plucking the file from the source distro server
    ret = download_removed_package(pv.package.poolPath, target,
                                   pv.package.name, base_version)
    if ret:
        update_info.save()
        return

    # We can't find that base version anywhere. Examine our package
    # changelog and see if we have access to any of the other previous
    # versions there. They might be close enough to enable a 3-way merge.
    logging.debug('Checking changelog for older base versions')
    unpacked_dir = unpack_source(pv)
    changelog_versions = read_changelog(unpacked_dir + '/debian/changelog')
    found = None
    for cl_version, text in changelog_versions:
        # Only consider versions that correspond to unmodified packages
        if cl_version.base() != cl_version:
            continue

        logger.debug('Considering changelog version %s', cl_version)

        # Do we have it in the pool?
        if cl_version in pool_versions:
            logger.debug('Found %s in pool', cl_version)
            found = cl_version
            break

        # Can we get it from a standard distro?
        if find_and_download_package(target, pv.package.name, cl_version):
            found = cl_version
            break

        # Can we get it with debsnap?
        if cl_version in debsnap_versions:
            ret = download_from_debsnap(pv.package.poolPath, pv.package.name,
                                        cl_version)
            if ret:
                found = cl_version
                break

    cleanup_source(pv)
    if found:
        logger.info('Couldn\'t find %s true base %s, using %s instead',
                    pv, base_version, found)
        update_info.set_base_version(found)
        update_info.save()
        return

    # None of the above approaches worked, so we won't be able to merge.
    # Record this and move on.
    logger.info('Failed to find base for %s', pv)
    update_info.set_base_version(None)
    update_info.save()


def main(options, args):
    logger.info('Updating source packages in target and source distros...')

    upstreamSources = []
    packages = []
    for target in config.targets(args):
        logger.info("Updating sources for %s", target)
        d = target.distro
        d.updateSources(target.dist)

        for upstreamList in target.getAllSourceLists():
            for source in upstreamList:
                if source not in upstreamSources:
                    logger.info("Updating upstream sources for %s", source)
                    source.distro.updateSources(source.dist)

        for package in target.distro.packages(target.dist, target.component):
            if options.package and package.name not in options.package:
                continue
            try:
                handle_package(target, package, options.force,
                               options.use_upstream)
            except urllib2.HTTPError, e:
                logger.warning('Caught HTTPError while handling %s: %s:',
                               package, e)


if __name__ == "__main__":
    run(main, usage="%prog [DISTRO...]",
        description="update the Sources file in a distribution's pool")
