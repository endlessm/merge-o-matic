import unittest

import testhelper
from deb.version import Version

class BaseTest(unittest.TestCase):
  def setUp(self):
    testhelper.setup_test_config()

  def test_simple(self):
    base = Version('3.0.0-2mom1').base()
    self.assertEqual(base.upstream, '3.0.0')
    self.assertEqual(base.revision, '2')
    self.assertEqual(str(base), '3.0.0-2')

  def test_complex(self):
    base = Version('2:1.2.3-4ubuntu3mom1').base()
    self.assertEqual(base.epoch, 2)
    self.assertEqual(base.upstream, '1.2.3')
    self.assertEqual(base.revision, '4')
    self.assertEqual(str(base), '2:1.2.3-4')

class EpochTest(unittest.TestCase):
  # Some Debian packages explicitly state epoch zero. If that's what the
  # metadata states then we have to be careful not to drop that when
  # converting to a string.
  def test_zeroEpoch(self):
    version = Version('0:1.2.3-4')
    self.assertEqual(str(version), '0:1.2.3-4')
