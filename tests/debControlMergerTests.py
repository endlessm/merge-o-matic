import os
import shutil
from tempfile import mkdtemp
import unittest
import textwrap

import testhelper
from util.debcontrolmerger import DebControlMerger


class DebControlMergerTest(unittest.TestCase):
    def setUp(self):
        self.parent_dir = mkdtemp(prefix='mom.control_test.')
        self.base_dir   = os.path.join(self.parent_dir, 'base')
        self.left_dir   = os.path.join(self.parent_dir, 'left')
        self.right_dir  = os.path.join(self.parent_dir, 'right')
        self.merged_dir = os.path.join(self.parent_dir, 'merged')

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
            shutil.rmtree(self.parent_dir)

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
            self.assertMultiLineEqual(fd.read(), result)

    def merge(self):
        merger = DebControlMerger('debian/control',
                                  self.left_dir, 'left',
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

    # Downstream version adds an Architecture to the end of the list
    # Upstream version otherwise conflicts
    # Check that the architecture is readded
    def test_addArchitecture(self):
        self.write_base('Source: binutils\n\n'
                        'Package: binutils-aarch64-linux-gnu\n'
                        'Architecture: amd64 i386 x32\n'
                        'Depends: binutils\n')

        self.write_left('Source: binutils\n\n'
                        'Package: binutils-aarch64-linux-gnu\n'
                        'Architecture: amd64 i386 x32 armhf\n'
                        'Depends: binutils\n')

        self.write_right('Source: binutils\n\n'
                         'Package: binutils-aarch64-linux-gnu\n'
                         'Architecture: arm64 amd64 i386 x32 ppc64el\n'
                         'Depends: binutils\n')

        merger, merged = self.merge()
        self.assertTrue(merged)
        self.assertTrue(merger.modified)
        self.assertResult('Source: binutils\n\n'
                          'Package: binutils-aarch64-linux-gnu\n'
                          'Architecture: arm64 amd64 i386 x32 ppc64el armhf\n'
                          'Depends: binutils\n')

    # Downstream version adds an Architecture to the end of the list
    # That package disappeared upstream
    # Merge succeeds using upstream version
    def test_addArchToRemovedPackage(self):
        self.write_base('Source: gcc-defaults\n\n'
                        'Package: gcj\n'
                        'Architecture: amd64 i386 x32\n')

        self.write_left('Source: gcc-defaults\n\n'
                        'Package: gcj\n'
                        'Architecture: amd64 i386 x32 armhf\n')

        self.write_right('Source: gcc-defaults\n\n'
                         'Package: gfortran\n'
                         'Architecture: amd64 i386 x32\n')

        merger, merged = self.merge()
        self.assertTrue(merged)
        self.assertFalse(merger.modified)

    # Check that changes to Suggests and Recommends are dropped
    def test_resetSuggests(self):
        self.write_base('Source: cryptsetup\n\n'
                        'Package: cryptsetup\n'
                        'Suggests: foo, console-setup\n'
                        'Recommends: bar\n')

        self.write_left('Source: cryptsetup\n\n'
                        'Package: cryptsetup\n'
                        'Suggests: foo\n'
                        'Recommends: bar, console-setup\n')

        self.write_right('Source: cryptsetup\n\n'
                         'Package: cryptsetup\n'
                         'Breaks: something\n')

        merger, merged = self.merge()
        self.assertTrue(merged)
        self.assertFalse(merger.modified)

    # Test that the Recomends field is restored if it was completely dropped
    def test_restoreRecommends(self):
        self.write_base('Source: kbd\n\n'
                        'Package: kbd\n'
                        'Recommends: console-setup\n'
                        'Depends: foo\n')

        self.write_left('Source: kbd\n\n'
                        'Package: kbd\n'
                        'Depends: foo\n')

        self.write_right('Source: kbd\n\n'
                         'Package: kbd\n'
                         'Recommends: console-setup\n'
                         'Depends: foo2\n')

        merger, merged = self.merge()
        self.assertTrue(merged)
        self.assertFalse(merger.modified)

    # If it comes down to it, we drop comment modifications if that helps
    # with the merge.
    def test_commentRemoval(self):
        self.write_base('Source: foo\n'
                        '# a comment that we will remove\n'
                        '# another comment\n'
                        'Build-Depends: foo3\n')

        self.write_left('Source: foo\n'
                        '# another comment\n'
                        'Build-Depends: foo3\n')

        self.write_right('Source: foo\n'
                         '# a comment that we will remove\n'
                         '# newly added comment that conflicts\n'
                         '# another comment\n'
                         'Build-Depends: foo3\n')

        merger, merged = self.merge()
        self.assertTrue(merged)
        self.assertFalse(merger.modified)

    def test_trickyMesonMerge(self):
        # This is based on a real merge of 0.49.2-1, 0.49.2-1endless1 and
        # 0.51.1-1.  Downstream, we drop all of the test dependencies. In
        # Debian, a trick is used to add optional build dependencies by OR-ing
        # with bash-doc. Previously, the merger would delete one or other
        # branch of the OR but leave the | in place, causing a parse failure.
        self.write_base(textwrap.dedent("""
            Source: meson
            Build-Depends: debhelper (>= 11),
              ninja-build (>= 1.6),
              rustc [i386 amd64] <!nocheck> | bash-doc <!nocheck>,
              g++-arm-linux-gnueabihf [!armhf] <!nocheck> | bash-doc <!nocheck>,
              nasm <!nocheck>,
        """).lstrip())
        self.write_left(textwrap.dedent("""
            Source: meson
            Build-Depends: debhelper (>= 11),
              ninja-build (>= 1.6),
        """).lstrip())
        self.write_right(textwrap.dedent("""
            Source: meson
            Build-Depends: debhelper (>= 11),
              python2-dev <!nocheck>,
              ninja-build (>= 1.6),
              rustc [i386 amd64] <!nocheck> | bash-doc <!nocheck>,
              g++-arm-linux-gnueabihf [!armhf] <!nocheck> | bash-doc <!nocheck>,
              nasm <!nocheck>,
        """).lstrip())
        merger, merged = self.merge()
        self.assertTrue(merged)
        self.assertTrue(merger.modified)
        self.assertResult(textwrap.dedent("""
            Source: meson
            Build-Depends: debhelper (>= 11),
              python2-dev <!nocheck>,
              ninja-build (>= 1.6),
        """).lstrip())
