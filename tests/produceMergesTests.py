import unittest
import config
import testhelper
import produce_merges
import shutil
import os
import stat
from filecmp import dircmp
from copy import copy
from momlib import result_dir
from testhelper import config_add_distro_from_repo, config_add_distro_sources
from merge_report import MergeResult

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
    report = produce_merges.produce_merge(target, our_version, our_version,
                                          upstream, output_dir)
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
    base = target.findSourcePackage(package.name, version='1.0-1')[0]

    output_dir = result_dir(target.name, package.name)
    report = produce_merges.produce_merge(target, base, our_version, upstream,
                                          output_dir)
    self.assertEqual(report.result, MergeResult.SYNC_THEIRS)
    self.assertEqual(report.merged_version, upstream.version)
    self.assertTrue(len(report.notes) > 0)

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
    base = target.findSourcePackage(package.name, version='1.0-1')[0]

    output_dir = result_dir(target.name, package.name)
    report = produce_merges.produce_merge(target, base, our_version, upstream,
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
    base = target.findSourcePackage(package.name, version='1.0-1')[0]

    output_dir = result_dir(target.name, package.name)
    report = produce_merges.produce_merge(target, base, our_version, upstream,
                                          output_dir)
    self.assertEqual(report.result, MergeResult.CONFLICTS)

  # Base version foo-2.0-1
  # Target has foo-2.0-1mom1 with a new file
  # Source has foo-3.0-1 with another new file
  # Package has multiple orig files
  # Merge should succeed
  def test_multipleOrig(self):
    package = testhelper.TestPackage('foo', '2.0-1')
    os.makedirs(package.pkg_path + '/mydir')
    open(package.pkg_path + '/mydir/mainfile', 'w').write('hello')
    package.create_orig()
    package.create_orig(subdir='mydir')
    package.build()
    self.source1_repo.importPackage(package)

    forked = copy(package)
    forked.changelog_entry(version='2.0-1mom1')
    open(forked.pkg_path + '/debian/new.file', 'w').write('hello')
    forked.build()
    self.target_repo.importPackage(forked)

    package.changelog_entry(version='3.0-1')
    open(package.pkg_path + '/debian/new.file2', 'w').write('another')
    package.create_orig()
    package.create_orig(subdir='mydir')
    package.build()
    self.source2_repo.importPackage(package)

    target = config.targets()[0]
    testhelper.update_all_distro_sources()
    testhelper.update_all_distro_source_pools()

    our_version = target.distro.findPackage(package.name, version='2.0-1mom1')[0]
    upstream = target.findSourcePackage(package.name, version='3.0-1')[0]
    base = target.findSourcePackage(package.name, version='2.0-1')[0]

    output_dir = result_dir(target.name, package.name)
    report = produce_merges.produce_merge(target, base, our_version, upstream,
                                          output_dir)
    self.assertEqual(report.result, MergeResult.MERGED)
