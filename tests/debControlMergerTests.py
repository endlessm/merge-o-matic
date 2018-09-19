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

    # Downstream version modifies the version constraint of a build dep.
    # Upstream version drops that build dep altogether.
    # Check that we auto-merge by dropping our local change.
    def test_changeBuildDepVersionOfDroppedDep(self):
        self.write_base('Source: appstream\n'
                        'Build-Depends: cmake (>= 2.8),\n'
                        ' debhelper (>= 10),\n'
                        ' gettext,\n'
                        'Uploaders: Fish <fish@fish.com>\n')

        self.write_left('Source: appstream\n'
                        'Build-Depends: cmake (>= 3.2),\n'
                        ' debhelper (>= 10),\n'
                        ' gettext,\n'
                        'Uploaders: Fish <fish@fish.com>\n')

        self.write_right('Source: appstream\n'
                         'Build-Depends: debhelper (>= 11),\n'
                         ' gettext,\n'
                         'Uploaders: Fish <fish@fish.com>\n')

        merger, merged = self.merge()
        self.assertTrue(merged)
        self.assertFalse(merger.modified)

    # Downstream version removes the version constraint of 2 build deps.
    # Upstream version drops that build dep altogether.
    # Check that we auto-merge by dropping our local changes.
    # Also tests 2 modifications on the same line
    def test_removeBuildDepVersionOfDroppedDep(self):
        self.write_base('Source: fonts-cantarell\n'
                        'Build-Depends-Indep: fontforge (>= 1), foo (> 3)\n'
                        'Uploaders: Fish <fish@fish.com>\n')

        self.write_left('Source: fonts-cantarell\n'
                        'Build-Depends-Indep: fontforge, foo\n'
                        'Uploaders: Fish <fish@fish.com>\n')

        self.write_right('Source: fonts-cantarell\n'
                         'Build-Depends-Indep: fontmake, bar\n'
                         'Uploaders: Fish <fish@fish.com>\n')

        merger, merged = self.merge()
        self.assertTrue(merged)
        self.assertFalse(merger.modified)

    # If the left side modifies a version constraint, this should be carried
    # over to the new version
    def test_changeVersionConstraint(self):
        self.write_base('Source: foo\n'
                        'Build-Depends: one (> 3.0), two\n')

        self.write_left('Source: foo\n'
                        'Build-Depends: one (> 4.0), two\n')

        self.write_right('Source: foo\n'
                         'Build-Depends: one (> 3.0), three\n')

        merger, merged = self.merge()
        self.assertTrue(merged)
        self.assertTrue(merger.modified)
        self.assertResult('Source: foo\n'
                          'Build-Depends: one (> 4.0), three\n')

    # If the left side increases a "greater than" version constraint
    # but the right side increases it even further, then we can
    # drop our local change.
    def test_changeVersionConstraintGtUpgrade(self):
        self.write_base('Source: foo\n'
                        'Uploaders: a <b@c.com>\n\n'
                        'Package: pkg\n'
                        'Depends: one (> 3.0), two\n')

        self.write_left('Source: foo\n'
                        'Uploaders: a <b@c.com>\n\n'
                        'Package: pkg\n'
                        'Depends: one (> 4.0), two\n')

        self.write_right('Source: foo\n'
                         'Uploaders: a <b@c.com>\n\n'
                         'Package: pkg\n'
                         'Depends: one (> 5.0), four\n')

        merger, merged = self.merge()
        self.assertTrue(merged)
        self.assertFalse(merger.modified)

    # Downstream version removes a build dep
    # Upstream version removes the same build dep, and otherwise conflicts
    # Should take the upstream version
    def test_removeEliminatedBuildDep(self):
        self.write_base('Source: gnome-online-accounts\n'
                        'Build-Depends: soup,\n'
                        ' telepathy,\n'
                        ' webkit\n')

        self.write_left('Source: gnome-online-accounts\n'
                        'Build-Depends: soup,\n'
                        ' webkit\n')

        self.write_right('Source: gnome-online-accounts\n'
                         'Build-Depends: other,\n'
                         ' stuff\n')

        merger, merged = self.merge()
        self.assertTrue(merged)
        self.assertFalse(merger.modified)

    # If there are only syntactical changes in the build deps, they
    # should be dropped.
    def test_buildDepNoChange(self):
        self.write_base('Source: foo\n'
                        'Build-Depends: one, two\n')

        self.write_left('Source: foo\n'
                        'Build-Depends: two,   one,\n')

        self.write_right('Source: foo\n'
                         'Build-Depends: one, three\n')

        merger, merged = self.merge()
        self.assertTrue(merged)
        self.assertFalse(merger.modified)

    # Left side adds a Build-Depends-Indep entry
    # Right side removes that field altogether
    # Check that the field is readded
    def test_buildDepFieldRemoved(self):
        self.write_base('Source: foo\n'
                        'Build-Depends-Indep: one, two\n')

        self.write_left('Source: foo\n'
                        'Build-Depends-Indep: one, foo, two\n')

        self.write_right('Source: foo\n'
                         'Build-Depends: one, two\n')

        merger, merged = self.merge()
        self.assertTrue(merged)
        self.assertTrue(merger.modified)
        self.assertResult('Source: foo\n'
                          'Build-Depends: one, two\n'
                          'Build-Depends-Indep: foo\n')

    def test_addArchList(self):
        self.write_base('Source: foo\n'
                        'Build-Depends: one, two\n')

        self.write_left('Source: foo\n'
                        'Build-Depends: one [!armhf], two\n')

        self.write_right('Source: foo\n'
                         'Build-Depends: one, three\n')

        merger, merged = self.merge()
        self.assertTrue(merged)
        self.assertTrue(merger.modified)
        self.assertResult('Source: foo\n'
                          'Build-Depends: one [!armhf], three\n')
