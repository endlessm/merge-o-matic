import unittest
import config
import testingConfig

config.loadConfig(testingConfig)

class CheckoutTests(unittest.TestCase):
  def setUp(self):
    self.distro = config.Distro("live-test")

  def test_checkout(self):
    self.distro.osc().checkout(('aalib',))

  def test_update(self):
    self.distro.osc().update(('aalib',))

  def test_sync(self):
    self.distro.osc().sync()
