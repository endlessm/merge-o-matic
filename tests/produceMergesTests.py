import unittest
import config
import testhelper
import produce_merges
from testhelper import config_add_distro_from_repo, config_add_distro_sources

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
