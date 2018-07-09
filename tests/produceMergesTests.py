import unittest
import config
import testhelper
import produce_merges
from copy import copy
from momlib import result_dir
from testhelper import config_add_distro_from_repo, config_add_distro_sources
from merge_report import MergeResult

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

    upstream = produce_merges.find_upstream(target, pkg_version.package,
                                            pkg_version)
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

    upstream = produce_merges.find_upstream(target, pkg_version.package,
                                            pkg_version)
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

    upstream = produce_merges.find_upstream(target, pkg_version.package,
                                            pkg_version)
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

    upstream = produce_merges.find_upstream(target, pkg_version.package,
                                            pkg_version)
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

    upstream = produce_merges.find_upstream(target, pkg_version.package,
                                            pkg_version)
    self.assertEqual(upstream.package.name, 'foo')
    self.assertEqual(upstream.version, '2.1')
    self.assertTrue(upstream > pkg_version)

class ProduceMergeTest(unittest.TestCase):
  def setUp(self):
    self.target_repo, self.source1_repo, self.source2_repo = \
      testhelper.standard_simple_config(num_stable_sources=2)

  # Target has foo-1.0
  # Source has foo-2.0
  # Target should be synced to new version
  def test_simpleSync(self):
    foo = testhelper.build_and_import_simple_package('foo', '1.0',
                                                     self.target_repo)

    foo.changelog_entry('2.0')
    foo.build()
    self.source1_repo.importPackage(foo)

    target = config.targets()[0]
    testhelper.update_all_distro_sources()
    testhelper.update_all_distro_source_pools()

    our_version = target.distro.findPackage(foo.name, version='1.0')[0]
    upstream = target.findSourcePackage(foo.name, '2.0')[0]

    output_dir = result_dir(target.name, foo.name)
    report = produce_merges.produce_merge(target, our_version, upstream,
                                          output_dir)
    self.assertEqual(report.result, MergeResult.SYNC_THEIRS)
    self.assertEqual(report.merged_version, upstream.version)

  # Base version foo-1.0-1
  # Target has foo-1.0-1mom1 with modified changelog only
  # Source has foo-1.2-1
  # Target version should be synced to source version
  def test_onlyDiffIsChangelog(self):
    package = testhelper.build_and_import_simple_package('foo', '1.0-1',
                                                         self.source1_repo)

    forked = copy(package)
    forked.changelog_entry(version='1.0-1mom1')
    forked.build()
    self.target_repo.importPackage(forked)

    package.changelog_entry(version='1.2-1')
    package.create_orig()
    package.build()
    self.source2_repo.importPackage(package)

    target = config.targets()[0]
    testhelper.update_all_distro_sources()
    testhelper.update_all_distro_source_pools()

    our_version = target.distro.findPackage(package.name, version='1.0-1mom1')[0]
    upstream = target.findSourcePackage(package.name, version='1.2-1')[0]

    output_dir = result_dir(target.name, package.name)
    report = produce_merges.produce_merge(target, our_version, upstream,
                                          output_dir)
    self.assertEqual(report.result, MergeResult.SYNC_THEIRS)
    self.assertEqual(report.merged_version, upstream.version)

  # Base version foo-1.0-1
  # Target has foo-1.0-1mom1 with a new file
  # Source has foo-1.2-1
  # Target version should be merged with source version
  def test_mergeNewFile(self):
    package = testhelper.build_and_import_simple_package('foo', '1.0-1',
                                                         self.source1_repo)

    forked = copy(package)
    forked.changelog_entry(version='1.0-1mom1')
    open(forked.pkg_path + '/debian/new.file', 'w').write('hello')
    forked.build()
    self.target_repo.importPackage(forked)

    package.changelog_entry(version='1.2-1')
    package.create_orig()
    package.build()
    self.source2_repo.importPackage(package)

    target = config.targets()[0]
    testhelper.update_all_distro_sources()
    testhelper.update_all_distro_source_pools()

    our_version = target.distro.findPackage(package.name, version='1.0-1mom1')[0]
    upstream = target.findSourcePackage(package.name, version='1.2-1')[0]

    output_dir = result_dir(target.name, package.name)
    report = produce_merges.produce_merge(target, our_version, upstream,
                                          output_dir)
    self.assertEqual(report.result, MergeResult.MERGED)
    self.assertTrue(report.merged_version > upstream.version)

  # Base version foo-1.0-1
  # Target has foo-1.0-1mom1 with a new file
  # Source has foo-1.2-1 with a conflicting new file
  # Merge should fail due to conflicts
  def test_mergeConflicts(self):
    package = testhelper.build_and_import_simple_package('foo', '1.0-1',
                                                         self.source1_repo)

    forked = copy(package)
    forked.changelog_entry(version='1.0-1mom1')
    open(forked.pkg_path + '/debian/new.file', 'w').write('hello')
    forked.build()
    self.target_repo.importPackage(forked)

    package.changelog_entry(version='1.2-1')
    open(package.pkg_path + '/debian/new.file', 'w').write('conflict')
    package.create_orig()
    package.build()
    self.source2_repo.importPackage(package)

    target = config.targets()[0]
    testhelper.update_all_distro_sources()
    testhelper.update_all_distro_source_pools()

    our_version = target.distro.findPackage(package.name, version='1.0-1mom1')[0]
    upstream = target.findSourcePackage(package.name, version='1.2-1')[0]

    output_dir = result_dir(target.name, package.name)
    report = produce_merges.produce_merge(target, our_version, upstream,
                                          output_dir)
    self.assertEqual(report.result, MergeResult.CONFLICTS)
