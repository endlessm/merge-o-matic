import unittest
import config

class ConfigTest(unittest.TestCase):
  def test_valid(self):
    self.assertFalse(config.get("ROOT") == None)

  def test_invalid(self):
    self.assertEqual(config.get("nonExistantConfigValue"), None)

  def test_recursion(self):
    self.assertEqual(config.get("DISTROS", "SUITE_A-target", "obs", "url"), "https://SERVER:444")
