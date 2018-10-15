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
