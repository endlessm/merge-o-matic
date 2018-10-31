import os
import shutil
from tempfile import mkdtemp
import unittest

import testhelper
from util.debcontrolmerger import DebControlMerger


class DebControlMergerTest(unittest.TestCase):
    def setUp(self):
        self.base_dir = mkdtemp(prefix='mom.control_test.base.')
        self.left_dir = mkdtemp(prefix='mom.control_test.left.')
        self.right_dir = mkdtemp(prefix='mom.control_test.right.')
        self.merged_dir = mkdtemp(prefix='mom.control_test.merged.')

        os.makedirs(self.base_dir + '/debian')
        os.makedirs(self.left_dir + '/debian')
        os.makedirs(self.right_dir + '/debian')
        os.makedirs(self.merged_dir + '/debian')

        self.base_path = os.path.join(self.base_dir, 'debian', 'control')
        self.left_path = os.path.join(self.left_dir, 'debian', 'control')
        self.right_path = os.path.join(self.right_dir, 'debian', 'control')
        self.merged_path = os.path.join(self.merged_dir, 'debian', 'control')

    def tearDown(self):
        if testhelper.should_cleanup():
            shutil.rmtree(self.base_dir)
            shutil.rmtree(self.left_dir)
            shutil.rmtree(self.right_dir)
            shutil.rmtree(self.merged_dir)

    def write_control(self, path, contents):
        with open(path, 'w') as fd:
            fd.write(contents)

    def write_base(self, contents):
        return self.write_control(self.base_path, contents)

    def write_left(self, contents):
        return self.write_control(self.left_path, contents)

    def write_right(self, contents):
        return self.write_control(self.right_path, contents)

    def assertResult(self, result):
        with open(self.merged_path, 'r') as fd:
            self.assertEqual(fd.read(), result)

    def merge(self):
        merger = DebControlMerger(self.left_dir, 'left',
                                  self.right_dir, 'right',
                                  self.base_dir, self.merged_dir)
        return merger, merger.run()

    # Some development routines involve the downstream developer being
    # added to debian/control Uploaders when modifying packages. This
    # can cause merge conflicts going forward. Test our codepath that
    # explicitly drops the Uploaders modification to avoid a conflicting file.
    def test_controlFileUploadersReset(self):
        self.write_base('Source: cheese\n'
                        'Uploaders: Fish <fish@fish.com>\n'
                        'Build-Depends: debhelper\n')

        self.write_left('Source: cheese\n'
                        'Uploaders: Fish <f@fish.com>, me <down@stream.com>\n'
                        'Build-Depends: debhelper\n')

        self.write_right('Source: cheese\n'
                         'Uploaders: Fish <fish@fish.com>, Frog <fr@g.com>\n'
                         'Build-Depends: debhelper\n')

        merger, merged = self.merge()
        self.assertTrue(merged)
        self.assertFalse(merger.modified)

    # If a package is removed on the left, it should be removed on the right
    # even if that package definition changed in the update.
    def test_droppedPackages(self):
        self.write_base('Source: foo\n\n'
                        'Package: one\n'
                        'Suggests: foo2\n\n'
                        'Package: bar\n'
                        'Suggests: foo3\n')

        self.write_left('Source: foo\n\n'
                        'Package: bar\n'
                        'Suggests: foo3\n')

        self.write_right('Source: foo\n\n'
                         'Package: one\n'
                         'Recommends: foo2\n\n'
                         'Package: bar\n'
                         'Suggests: foo3\n')

        merger, merged = self.merge()
        self.assertTrue(merged)
        self.assertTrue(merger.modified)
        self.assertResult('Source: foo\n\n'
                          'Package: bar\n'
                          'Suggests: foo3\n')

    # If a package is added on the left, it should be added on the right
    def test_addedPackage(self):
        self.write_base('Source: foo\n'
                        'Build-Depends: a (> 3)\n\n'
                        'Package: one\n'
                        'Suggests: foo2\n')

        self.write_left('Source: foo\n'
                        'Build-Depends: a (> 3)\n\n'
                        'Package: bar\n'
                        'Suggests: foo3\n\n'
                        'Package: one\n'
                        'Suggests: foo2\n')

        self.write_right('Source: foo\n'
                         'Build-Depends: a (> 4)\n\n'
                         'Package: zzz\n'
                         'Suggests: zzz2\n')

        merger, merged = self.merge()
        self.assertTrue(merged)
        self.assertTrue(merger.modified)
        self.assertResult('Source: foo\n'
                          'Build-Depends: a (> 4)\n\n'
                          'Package: zzz\n'
                          'Suggests: zzz2\n\n'
                          'Package: bar\n'
                          'Suggests: foo3\n')

    # If a package field is added on the left, this addition should be
    # carried over to the right.
    def test_fieldAdded(self):
        self.write_base('Source: foo\n\n'
                        'Package: one\n'
                        'Suggests: foo2\n\n'
                        'Package: bar\n'
                        'Suggests: foo3\n')

        self.write_left('Source: foo\n\n'
                        'Package: one\n'
                        'Breaks: foo7\n'
                        'Suggests: foo2\n\n'
                        'Package: bar\n'
                        'Suggests: foo3\n')

        self.write_right('Source: foo\n\n'
                         'Package: one\n'
                         'Recommends: foo37\n\n'
                         'Package: bar\n'
                         'Suggests: foo3\n')

        merger, merged = self.merge()
        self.assertTrue(merged)
        self.assertTrue(merger.modified)
        self.assertResult('Source: foo\n\n'
                          'Package: one\n'
                          'Recommends: foo37\n'
                          'Breaks: foo7\n\n'
                          'Package: bar\n'
                          'Suggests: foo3\n')
