import unittest
from tempfile import mkdtemp
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
from produce_merges import do_merge

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


class DoMergeTest(unittest.TestCase):
  def setUp(self):
    self.base_dir = mkdtemp(prefix='mom.merge_test.base.')
    self.left_dir = mkdtemp(prefix='mom.merge_test.left.')
    self.right_dir = mkdtemp(prefix='mom.merge_test.right.')
    self.merged_dir = mkdtemp(prefix='mom.merge_test.merged.')

  def tearDown(self):
    if testhelper.should_cleanup():
      shutil.rmtree(self.base_dir)
      shutil.rmtree(self.left_dir)
      shutil.rmtree(self.right_dir)
      shutil.rmtree(self.merged_dir)

  def clone_dir(self, source, target):
    os.rmdir(target)
    shutil.copytree(source, target, symlinks=True)

  # Test that identical left/right/base gives an identical merge
  def test_noChanges(self):
    open(self.left_dir + '/file1', 'w').write('New file')
    os.chmod(self.left_dir + '/file1', 0755)
    os.mkdir(self.left_dir + '/dir1')
    open(self.left_dir + '/dir1/file2', 'w').write('hello')
    open(self.left_dir + '/dir1/file2', 'w').write('hello')
    os.symlink('file1', self.left_dir + '/link1')

    self.clone_dir(self.left_dir, self.right_dir)
    self.clone_dir(self.left_dir, self.base_dir)

    result = do_merge(self.left_dir, 'foo', '', 'left',
                      self.base_dir,
                      self.right_dir, 'foo', '', 'right',
                      self.merged_dir)

    self.assertEqual(len(result.conflicts), 0)
    self.assertEqual(stat.S_IMODE(os.stat(self.merged_dir + '/file1').st_mode),
                     0755)
    self.assertEqual(os.readlink(self.merged_dir + '/link1'), 'file1')

    dcmp = dircmp(self.left_dir, self.merged_dir)
    self.assertEqual(len(dcmp.left_only), 0)
    self.assertEqual(len(dcmp.right_only), 0)
    self.assertEqual(len(dcmp.diff_files), 0)
    self.assertEqual(len(dcmp.funny_files), 0)

  # Test basic file merging functionality (add, remove, modify)
  def test_basicMerge(self):
    # Pre-populate base version
    open(self.left_dir + '/file1', 'w').write('one')
    open(self.left_dir + '/file2', 'w').write('two')
    os.mkdir(self.left_dir + '/dir1')
    open(self.left_dir + '/dir1/file3', 'w').write('3')
    self.clone_dir(self.left_dir, self.base_dir)
    self.clone_dir(self.left_dir, self.right_dir)

    # Add a file on the left side
    open(self.left_dir + '/file4', 'w').write('cuatro')

    # Add a link on the left side
    os.symlink('/foo', self.left_dir + '/link1')
    
    # Remove a file on the right side
    os.unlink(self.right_dir + '/file2')

    # Modify a file on the left side
    open(self.left_dir + '/dir1/file3', 'a').write('three')

    result = do_merge(self.left_dir, 'foo', '', 'left',
                      self.base_dir,
                      self.right_dir, 'foo', '', 'right',
                      self.merged_dir)

    self.assertEqual(len(result.conflicts), 0)
    self.assertTrue(os.path.exists(self.merged_dir + '/file1'))
    self.assertFalse(os.path.exists(self.merged_dir + '/file2'))
    self.assertTrue(os.path.exists(self.merged_dir + '/dir1/file3'))
    self.assertEqual(open(self.merged_dir + '/dir1/file3', 'r').read(),
                     '3three')
    self.assertTrue(os.path.exists(self.merged_dir + '/file4'))
    self.assertEqual(os.readlink(self.merged_dir + '/link1'), '/foo')
    
  # Test that for debian-format packages, we only try to merge files under
  # the debian directory.
  def test_quiltDebianOnly(self):
    open(self.left_dir + '/newfile', 'w').write('New file')
    os.mkdir(self.left_dir + '/debian')
    open(self.left_dir + '/debian/newfile2', 'w').write('New file2')

    result = do_merge(self.left_dir, 'foo', '3.0 (quilt)', 'left',
                      self.base_dir,
                      self.right_dir, 'foo', '3.0 (quilt)', 'right',
                      self.merged_dir)

    self.assertEqual(len(result.conflicts), 0)
    self.assertFalse(os.path.exists(self.merged_dir + '/newfile'))
    self.assertTrue(os.path.exists(self.merged_dir + '/debian/newfile2'))

  # Test that permission changes are carried over, even when the file
  # has been modified.
  def test_fileMode(self):
    # Pre-populate base version
    open(self.left_dir + '/file1', 'w').write('one')
    open(self.left_dir + '/file2', 'w').write('two')
    self.clone_dir(self.left_dir, self.base_dir)
    self.clone_dir(self.left_dir, self.right_dir)

    os.chmod(self.left_dir + '/file1', 0600)
    os.chmod(self.left_dir + '/file2', 0755)
    open(self.left_dir + '/file2', 'a').write('2')

    result = do_merge(self.left_dir, 'foo', '', 'left',
                      self.base_dir,
                      self.right_dir, 'foo', '', 'right',
                      self.merged_dir)

    self.assertEqual(len(result.conflicts), 0)
    self.assertEqual(stat.S_IMODE(os.stat(self.merged_dir + '/file1').st_mode),
                     0600)
    self.assertEqual(stat.S_IMODE(os.stat(self.merged_dir + '/file2').st_mode),
                     0755)

  # Test merging of symlinks
  def test_mergeSymlinks(self):
    os.symlink('file1', self.left_dir + '/link1')
    os.symlink('file2', self.left_dir + '/link2')
    os.symlink('file3', self.left_dir + '/link3')

    self.clone_dir(self.left_dir, self.right_dir)
    self.clone_dir(self.left_dir, self.base_dir)

    # Add a link on the left
    os.symlink('fileNewL', self.left_dir + '/linkL')

    # Remove a link on the left
    os.unlink(self.left_dir + '/link2')

    # Add a link on the right
    os.symlink('fileNewR', self.right_dir + '/linkR')

    # Remove a link on the right
    os.unlink(self.right_dir + '/link3')

    result = do_merge(self.left_dir, 'foo', '', 'left',
                      self.base_dir,
                      self.right_dir, 'foo', '', 'right',
                      self.merged_dir)

    self.assertEqual(len(result.conflicts), 0)
    self.assertEqual(os.readlink(self.merged_dir + '/link1'), 'file1')
    self.assertEqual(os.readlink(self.merged_dir + '/linkL'), 'fileNewL')
    self.assertEqual(os.readlink(self.merged_dir + '/linkR'), 'fileNewR')
    self.assertFalse(os.path.exists(self.merged_dir + '/link2'))
    self.assertFalse(os.path.exists(self.merged_dir + '/link3'))

  # Test merge conflicts
  def test_mergeConflicts(self):
    open(self.left_dir + '/file1', 'w').write('hello')
    open(self.left_dir + '/file2', 'w').write('hola')
    open(self.left_dir + '/file3', 'w').write('...')
    os.symlink('file4', self.left_dir + '/link4')

    self.clone_dir(self.left_dir, self.right_dir)
    self.clone_dir(self.left_dir, self.base_dir)

    # Make an existing file contents conflict
    open(self.left_dir + '/file1', 'w').write('left')
    open(self.right_dir + '/file1', 'w').write('right')

    # Make a new file contents conflict
    open(self.left_dir + '/file4', 'w').write('left')
    open(self.right_dir + '/file4', 'w').write('right')

    # Make an existing symlink conflict
    os.unlink(self.left_dir + '/link4')
    os.symlink('leftconflict', self.left_dir + '/link4')
    os.unlink(self.right_dir + '/link4')
    os.symlink('rightconflict', self.right_dir + '/link4')

    # Make new symlink conflict
    os.symlink('leftconflict', self.left_dir + '/link1')
    os.symlink('rightconflict', self.right_dir + '/link1')

    # Modify a file on left, that got removed on right
    open(self.left_dir + '/file2', 'w').write('modified')
    os.unlink(self.right_dir + '/file2')

    # Modify a file on left that got changed into a symlink on right
    open(self.left_dir + '/file3', 'w').write('modified')
    os.unlink(self.right_dir + '/file3')
    os.symlink('rightconflict', self.right_dir + '/file3')

    result = do_merge(self.left_dir, 'foo', '', 'left',
                      self.base_dir,
                      self.right_dir, 'foo', '', 'right',
                      self.merged_dir)

    self.assertEqual(len(result.conflicts), 6)
    self.assertIn('file1', result.conflicts)
    self.assertIn('file2', result.conflicts)
    self.assertIn('file3', result.conflicts)
    self.assertIn('file4', result.conflicts)
    self.assertIn('link1', result.conflicts)
    self.assertIn('link4', result.conflicts)

