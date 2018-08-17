from filecmp import dircmp
import os
import shutil
import stat
from tempfile import mkdtemp
from subprocess import check_call, CalledProcessError
import unittest

import testhelper
from util.debtreemerger import DebTreeMerger

class DebTreeMergerTest(unittest.TestCase):
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

    merger = DebTreeMerger(self.left_dir, 'foo', '', 'left',
                           self.right_dir, 'foo', '', 'right',
                           self.base_dir, self.merged_dir)
    merger.run()

    self.assertEqual(len(merger.conflicts), 0)
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

    merger = DebTreeMerger(self.left_dir, 'foo', '', 'left',
                           self.right_dir, 'foo', '', 'right',
                           self.base_dir, self.merged_dir)
    merger.run()

    self.assertEqual(len(merger.conflicts), 0)
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

    merger = DebTreeMerger(self.left_dir, 'foo', '3.0 (quilt)', 'left',
                           self.right_dir, 'foo', '3.0 (quilt)', 'right',
                           self.base_dir,
                           self.merged_dir)
    merger.run()

    self.assertEqual(len(merger.conflicts), 0)
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

    merger = DebTreeMerger(self.left_dir, 'foo', '', 'left',
                           self.right_dir, 'foo', '', 'right',
                           self.base_dir,
                           self.merged_dir)
    merger.run()

    self.assertEqual(len(merger.conflicts), 0)
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

    merger = DebTreeMerger(self.left_dir, 'foo', '', 'left',
                           self.right_dir, 'foo', '', 'right',
                           self.base_dir,
                           self.merged_dir)
    merger.run()

    self.assertEqual(len(merger.conflicts), 0)
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

    merger = DebTreeMerger(self.left_dir, 'foo', '', 'left',
                           self.right_dir, 'foo', '', 'right',
                           self.base_dir,
                           self.merged_dir)
    merger.run()

    self.assertEqual(len(merger.conflicts), 6)
    self.assertIn('file1', merger.conflicts)
    self.assertIn('file2', merger.conflicts)
    self.assertIn('file3', merger.conflicts)
    self.assertIn('file4', merger.conflicts)
    self.assertIn('link1', merger.conflicts)
    self.assertIn('link4', merger.conflicts)

  # Debian only accepts quilt patches with no fuzz.
  # Here we test our functionality to auto-refresh fuzzy quilt patches.
  # A quilt patch is added on the left side, touching a file which has
  # some fuzz-inducing whitespace changes on the right side.
  def test_fuzzyQuiltPatch(self):
    open(self.base_dir + '/mainfile', 'w').write('5\n6\n7')
    open(self.left_dir + '/mainfile', 'w').write('5\n6\n7')
    os.makedirs(self.left_dir + '/debian/patches')

    quiltexec = {'env': {'QUILT_PATCHES': 'debian/patches'},
                 'cwd': self.left_dir}

    check_call(['quilt', 'new', 'test.patch'], **quiltexec)
    check_call(['quilt', 'add', 'mainfile'], **quiltexec)
    open(self.left_dir + '/mainfile', 'w').write('5\nsix\n7')
    check_call(['quilt', 'refresh'], **quiltexec)
    check_call(['quilt', 'pop'], **quiltexec)
    shutil.rmtree(self.left_dir + '/.pc')

    # Make a whitespace change on line 1 to introduce fuzz
    open(self.right_dir + '/mainfile', 'w').write('5 \n6\n7')

    # Check that the original patch indeed fails to apply on the right
    with self.assertRaises(CalledProcessError):
      check_call(['patch', '-p1', '--fuzz=0', '--dry-run', '-i',
                  self.left_dir + '/debian/patches/test.patch'],
                 cwd=self.right_dir)

    merger = DebTreeMerger(self.left_dir, 'foo', '3.0 (quilt)', 'left',
                           self.right_dir, 'foo', '3.0 (quilt)', 'right',
                           self.base_dir,
                           self.merged_dir)
    merger.run()

    self.assertEqual(len(merger.conflicts), 0)
    self.assertIn('debian/patches/series', merger.changes_made)
    self.assertIn('debian/patches/test.patch', merger.changes_made)
    self.assertEqual(merger.total_changes_made, 2)

    # Check that the new patch applies without fuzz
    check_call(['patch', '-p1', '--fuzz=0', '--dry-run', '-i',
                           'debian/patches/test.patch'],
                          cwd=self.merged_dir)

  # Our downstream changes just append a quilt patch to the end of the list.
  # Upstream then makes conflicting changes to the series file.
  # This should be merged by taking the new upstream series file and
  # appending our patch again at the end.
  def test_quiltSeriesMerge(self):
    os.makedirs(self.base_dir + '/debian/patches')
    with open(self.base_dir + '/debian/patches/series', 'w') as fd:
      fd.write('one.patch\n')

    os.makedirs(self.left_dir + '/debian/patches')
    with open(self.left_dir + '/debian/patches/series', 'w') as fd:
      fd.write('one.patch\n')
      fd.write('endless.patch\n')

    os.makedirs(self.right_dir + '/debian/patches')
    with open(self.right_dir + '/debian/patches/series', 'w') as fd:
      fd.write('one.patch\n')
      fd.write('two.patch\n')

    merger = DebTreeMerger(self.left_dir, 'foo', '3.0 (quilt)', 'left',
                           self.right_dir, 'foo', '3.0 (quilt)', 'right',
                           self.base_dir,
                           self.merged_dir)
    merger.run()

    self.assertEqual(len(merger.conflicts), 0)
    self.assertIn('debian/patches/series', merger.changes_made)
    merged = open(self.merged_dir + '/debian/patches/series', 'r').read()
    self.assertEqual(merged, 'one.patch\ntwo.patch\nendless.patch\n')