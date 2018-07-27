import unittest
import config
import testhelper
import shutil
import os
from model.error import PackageNotFound

class DistroTest(unittest.TestCase):
  def setUp(self):
    self.target_repo, self.source_repo = testhelper.standard_simple_config()

  # Test finding a source distro and reading its package database
  def test_distroSources(self):
    testhelper.build_and_import_simple_package('foo', '1.0', self.source_repo)

    target = config.targets()[0]
    self.assertEqual(target.name, 'testtarget')
    sourceLists = target.getAllSourceLists()
    upstreamList = sourceLists[0]
    source = upstreamList[0]
    component = source.distro.components()[0]

    source.distro.updateSources(source.dist)
    sources = source.distro.getSources(source.dist, component)
    self.assertEqual(len(sources), 1)
    self.assertEqual(sources[0].get('Package'), 'foo')
    self.assertEqual(sources[0].get('Version'), '1.0')

  # Test download package source into pool directory
  def test_poolDirectory(self):
    foo = testhelper.build_and_import_simple_package('foo', '1.0',
                                                     self.target_repo)
    testhelper.update_all_distro_sources()

    target = config.targets()[0]
    pkgs = target.distro.findPackage(foo.name, searchDist=target.dist)
    self.assertEqual(len(pkgs), 1)
    pv = pkgs[0]
    pv.download()
    self.assertTrue(os.path.isdir(pv.package.poolPath))
    versions = pv.package.getPoolVersions()
    self.assertEqual(len(versions), 1)
    self.assertEqual(versions[0].version, foo.version)

  # Test findPackage method
  def test_findPackage(self):
    foo = testhelper.build_and_import_simple_package('foo', '1.0',
                                                     self.target_repo)
    testhelper.update_all_distro_sources()

    target = config.targets()[0]
    pkgs = target.distro.findPackage(foo.name, searchDist=target.dist)
    self.assertEqual(len(pkgs), 1)

    pkgs = target.distro.findPackage(foo.name, searchDist=target.dist,
                                     version=foo.version)
    self.assertEqual(len(pkgs), 1)

    with self.assertRaises(PackageNotFound):
      target.distro.findPackage(foo.name, searchDist=target.dist, version="9")
