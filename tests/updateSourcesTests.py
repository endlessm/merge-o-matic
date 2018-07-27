import os
import unittest
from tempfile import mkdtemp
import json
import hashlib
import shutil

from momlib import files
from deb.controlfile import ControlFile

import config
import testhelper
import update_sources
from model import UpdateInfo, Version

class FindUpstreamTest(unittest.TestCase):
  def setUp(self):
    self.target_repo, self.source_repo = testhelper.standard_simple_config()

  # Target distro has foo-1.0
  # Source distro has foo-2.0
  # Target should be upgraded to foo-2.0
  def test_sourceIsNewer(self):
    testhelper.build_and_import_simple_package('foo', '1.0', self.target_repo)
    testhelper.build_and_import_simple_package('foo', '2.0', self.source_repo)
    testhelper.update_all_distro_sources()

    target = config.targets()[0]
    pkg_version = target.distro.findPackage('foo', version='1.0')[0]

    upstream = update_sources.find_upstream(target, pkg_version)
    self.assertEqual(upstream.package.name, 'foo')
    self.assertEqual(upstream.version, '2.0')
    self.assertTrue(upstream > pkg_version)

  # Target distro has foo-1.0
  # No upstream version available
  def test_noUpstream(self):
    testhelper.build_and_import_simple_package('foo', '1.0', self.target_repo)
    testhelper.update_all_distro_sources()

    target = config.targets()[0]
    pkg_version = target.distro.findPackage('foo', version='1.0')[0]

    upstream = update_sources.find_upstream(target, pkg_version)
    self.assertIsNone(upstream)

  # Target distro has foo-4.0
  # Source distro has foo-3.0
  # Target should not be upgraded
  def test_targetIsNewer(self):
    testhelper.build_and_import_simple_package('foo', '4.0', self.target_repo)
    testhelper.build_and_import_simple_package('foo', '3.0', self.source_repo)
    testhelper.update_all_distro_sources()

    target = config.targets()[0]
    pkg_version = target.distro.findPackage('foo', version='4.0')[0]

    upstream = update_sources.find_upstream(target, pkg_version)
    self.assertEqual(upstream.package.name, 'foo')
    self.assertEqual(upstream.version, '3.0')
    self.assertTrue(pkg_version > upstream)


class FindUnstableUpstreamTest(unittest.TestCase):
  def setUp(self):
    self.target_repo, self.stable_source_repo, self.unstable_source_repo = \
      testhelper.standard_simple_config(num_unstable_sources=1)

  # Target distro has foo-2.3
  # Stable source distro has foo-2.1
  # Unstable source distro has foo-2.4
  # Target should be updated to unstable source, since it is already
  # newer than the stable version.
  def test_upstreamFromUnstable(self):
    testhelper.build_and_import_simple_package('foo', '2.3', self.target_repo)
    testhelper.build_and_import_simple_package('foo', '2.1',
                                               self.stable_source_repo)
    testhelper.build_and_import_simple_package('foo', '2.4',
                                               self.unstable_source_repo)
    testhelper.update_all_distro_sources()

    target = config.targets()[0]
    pkg_version = target.distro.findPackage('foo', version='2.3')[0]

    upstream = update_sources.find_upstream(target, pkg_version)
    self.assertEqual(upstream.package.name, 'foo')
    self.assertEqual(upstream.version, '2.4')
    self.assertTrue(upstream > pkg_version)

  # Target distro has foo-2.0
  # Stable source distro has foo-2.1
  # Unstable source distro has foo-2.4
  # Target should be updated to stable source, ignoring unstable
  def test_upstreamFromStable(self):
    testhelper.build_and_import_simple_package('foo', '2.0', self.target_repo)
    testhelper.build_and_import_simple_package('foo', '2.1',
                                               self.stable_source_repo)
    testhelper.build_and_import_simple_package('foo', '2.4',
                                               self.unstable_source_repo)
    testhelper.update_all_distro_sources()

    target = config.targets()[0]
    pkg_version = target.distro.findPackage('foo', version='2.0')[0]

    upstream = update_sources.find_upstream(target, pkg_version)
    self.assertEqual(upstream.package.name, 'foo')
    self.assertEqual(upstream.version, '2.1')
    self.assertTrue(upstream > pkg_version)


class HandlePackageTest(unittest.TestCase):
  def setUp(self):
    self.target_repo, self.source1_repo, self.source2_repo = \
      testhelper.standard_simple_config(num_stable_sources=2)

  # Target has foo-2.0
  # Source has foo-1.0
  # Target version should be kept because it's newer
  def test_ourVersionNewer(self):
    testhelper.build_and_import_simple_package('foo', '2.0',
                                               self.target_repo)
    testhelper.build_and_import_simple_package('foo', '1.0',
                                               self.source1_repo)

    target = config.targets()[0]
    testhelper.update_all_distro_sources()
    pv = target.distro.findPackage('foo', version='2.0')[0]

    update_sources.handle_package(target, pv.package)
    update_info = UpdateInfo(pv.package)
    self.assertEqual(update_info.upstream_version, '1.0')

  # Target has foo-1.0
  # Source has foo-2.0
  # Should find upstream version as 2.0, using the 1.0 base
  def test_unmodifiedUpgrade(self):
    testhelper.build_and_import_simple_package('foo', '1.0',
                                               self.target_repo)
    testhelper.build_and_import_simple_package('foo', '2.0',
                                               self.source1_repo)

    target = config.targets()[0]
    testhelper.update_all_distro_sources()
    pv = target.distro.findPackage('foo', version='1.0')[0]

    update_sources.handle_package(target, pv.package)
    update_info = UpdateInfo(pv.package)
    self.assertEqual(update_info.upstream_version, '2.0')
    self.assertEqual(update_info.base_version, '1.0')

  # Target has foo-1.0mom1
  # No versions in source, test that no base can be found
  def test_noBase(self):
    testhelper.build_and_import_simple_package('foo', '1.0-1mom1',
                                               self.target_repo)

    target = config.targets()[0]
    testhelper.update_all_distro_sources()
    pv = target.distro.findPackage('foo', version='1.0-1mom1')[0]

    update_sources.handle_package(target, pv.package)
    update_info = UpdateInfo(pv.package)
    self.assertIsNone(update_info.base_version)

  # Target has foo-1.0-1mom1
  # Source distros have foo-1.0-1 and foo-2.0-1
  # Check that appropriate base and upstream versions are found
  def test_mergeUpgrade(self):
    testhelper.build_and_import_simple_package('foo', '1.0-1mom1',
                                               self.target_repo)
    testhelper.build_and_import_simple_package('foo', '1.0-1',
                                               self.source1_repo)
    testhelper.build_and_import_simple_package('foo', '2.0-1',
                                               self.source2_repo)
    target = config.targets()[0]
    testhelper.update_all_distro_sources()
    pv = target.distro.findPackage('foo', version='1.0-1mom1')[0]

    update_sources.handle_package(target, pv.package)
    update_info = UpdateInfo(pv.package)
    self.assertEqual(update_info.base_version, '1.0-1')
    self.assertEqual(update_info.upstream_version, '2.0-1')

  def test_baseFromChangelog(self):
    foo = testhelper.build_and_import_simple_package('foo', '3.0-1',
                                                     self.source1_repo)

    foo.changelog_entry('4.0-1mom1')
    foo.create_orig()
    foo.build()
    self.target_repo.importPackage(foo)

    target = config.targets()[0]
    testhelper.update_all_distro_sources()
    pv = target.distro.findPackage('foo', version='4.0-1mom1')[0]

    update_sources.handle_package(target, pv.package)
    update_info = UpdateInfo(pv.package)
    self.assertEqual(update_info.base_version, '3.0-1')


class DebsnapFetchTest(unittest.TestCase):
  def setUp(self):
    # Create a single package (not in any repo) and then set up json files
    # and directory structure in a way that matches snapshot.debian.org
    assert(update_sources.SNAPSHOT_BASE.startswith('file://'))
    self.debsnap_base = update_sources.SNAPSHOT_BASE[7:]

    filedir = os.path.join(self.debsnap_base, 'file')
    os.makedirs(os.path.join(filedir))

    data = {
      '_comment': "foo",
      'version': "1.2-1",
      'fileinfo': {},
    }

    foo = testhelper.TestPackage(name='foo', version='1.2-1')
    foo.build()
    dsc_path = foo.dsc_path
    dsc_data = ControlFile(dsc_path, multi_para=False, signed=True).para

    with open(dsc_path, 'r') as fd:
      sha1 = hashlib.sha1(fd.read()).hexdigest()
      data['fileinfo'][sha1] = [{
        'name': os.path.basename(dsc_path),
        'archive_name': 'debian',
        'path': '/pool/main/f/foo',
        'size': os.path.getsize(dsc_path),
      }]
    shutil.copyfile(dsc_path, os.path.join(filedir, sha1))

    for dsc_hash, size, filename in files(dsc_data):
      path = os.path.join(foo.base_path, filename)
      with open(path, 'r') as fd:
        sha1 = hashlib.sha1(fd.read()).hexdigest()

      data['fileinfo'][sha1] = [{
        'name': filename,
        'archive_name': 'debian',
        'path': '/pool/main/f/foo',
        'size': size,
      }]
      shutil.copyfile(path, os.path.join(filedir, sha1))

    path = os.path.join(self.debsnap_base, 'mr/package/foo/1.2-1')
    os.makedirs(path)
    with open(os.path.join(path, 'srcfiles?fileinfo=1'), 'w') as fd:
      json.dump(data, fd)

    self.output_dir = mkdtemp(prefix='momtest.ustest.')

  def tearDown(self):
    shutil.rmtree(self.output_dir)
    shutil.rmtree(self.debsnap_base)
    os.makedirs(self.debsnap_base)

  def test_fetchFromSnapshot(self):
    # Test that we can download the package from the fake snapshot server
    output_dir = mkdtemp()
    ret = update_sources.download_from_debsnap(self.output_dir, 'foo',
                                               Version('1.2-1'))
    self.assertTrue(ret)
    dir_contents = os.listdir(self.output_dir)
    self.assertEqual(len(dir_contents), 3)
    self.assertIn('foo_1.2-1.dsc', dir_contents)
