import unittest
import config
import model
import configTestsConfig

class ConfigTest(unittest.TestCase):
  def setUp(self):
    config.loadConfig(configTestsConfig)

  def test_valid(self):
    self.assertEqual(config.get("ROOT"), configTestsConfig.ROOT)

  def test_invalid(self):
    self.assertEqual(config.get("nonExistantConfigValue"), None)

  def test_default(self):
    self.assertEqual(config.get("nonExistantConfigValue", default=42), 42)

  def test_recursion(self):
    self.assertEqual(config.get("DISTROS", "target", "obs", "url"), configTestsConfig.DISTROS["target"]["obs"]["url"])

class DistroTest(unittest.TestCase):
  def setUp(self):
    config.loadConfig(configTestsConfig)
    self.distro = model.base.Distro.get("target")

  def test_name(self):
    self.assertTrue(self.distro.name, "target")

  def testConfig(self):
    self.assertEqual(self.distro.config("obs", "url"), configTestsConfig.DISTROS["target"]["obs"]["url"])
    self.assertEqual(self.distro.config("nonExistantConfig", default=42), 42)

  def test_all(self):
    distros = model.base.Distro.all()
    self.assertEqual(len(distros), len(configTestsConfig.DISTROS))
    found = False
    for d in distros:
      self.assertIsInstance(d, model.base.Distro)
      if d.name == "target":
        found = True
    self.assertTrue(found)

  def test_oscDir(self):
    self.assertEqual(self.distro.oscDirectory(), "/tmp/mom/osc/target")

    self.assertEqual(self.distro.obsProject("unstable", "contrib"),
            "target:unstable:contrib")

  def test_branch(self):
    homeBranch = self.distro.branch("mom-test")
    self.assertEqual(homeBranch.name, "mom-test")
    self.assertEqual(homeBranch.config("obs", "url"), self.distro.config("obs", "url"))
    self.assertEqual(homeBranch.obsProject("experimental", "main"),
        "mom-test:target:experimental:main")
    self.assertEqual(homeBranch.oscDirectory(), "/tmp/mom/osc/mom-test")
