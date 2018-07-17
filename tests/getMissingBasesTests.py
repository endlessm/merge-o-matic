import os
import unittest
from tempfile import mkdtemp
import json
import hashlib
import shutil

from momlib import files
from deb.controlfile import ControlFile

import testhelper
import get_missing_bases

class GetMissingBasesTest(unittest.TestCase):
  def setUp(self):
    # Create a single package (not in any repo) and then set up json files
    # and directory structure in a way that matches snapshot.debian.org
    assert(get_missing_bases.BASE_URL.startswith('file://'))
    debsnap_base = get_missing_bases.BASE_URL[7:]

    filedir = os.path.join(debsnap_base, 'file')
    os.makedirs(os.path.join(filedir))

    data = {
      '_comment': "foo",
      'version': "1.2-1",
      'fileinfo': {},
    }

    foo = testhelper.TestPackage(name='foo', version='1.2-1')
    foo.build()
    dsc_path = foo.dsc_path
    dsc_data = ControlFile(dsc_path, multi_para=False, signed=True).para

    with open(dsc_path, 'r') as fd:
      sha1 = hashlib.sha1(fd.read()).hexdigest()
      data['fileinfo'][sha1] = [{
        'name': os.path.basename(dsc_path),
        'archive_name': 'debian',
        'path': '/pool/main/f/foo',
        'size': os.path.getsize(dsc_path),
      }]
    shutil.copyfile(dsc_path, os.path.join(filedir, sha1))

    for dsc_hash, size, filename in files(dsc_data):
      path = os.path.join(foo.base_path, filename)
      with open(path, 'r') as fd:
        sha1 = hashlib.sha1(fd.read()).hexdigest()

      data['fileinfo'][sha1] = [{
        'name': filename,
        'archive_name': 'debian',
        'path': '/pool/main/f/foo',
        'size': size,
      }]
      shutil.copyfile(path, os.path.join(filedir, sha1))

    path = os.path.join(debsnap_base, 'mr/package/foo/1.2-1')
    os.makedirs(path)
    with open(os.path.join(path, 'srcfiles?fileinfo=1'), 'w') as fd:
      json.dump(data, fd)

  def test_fetchFromSnapshot(self):
    # Test that we can download the package from the fake snapshot server
    output_dir = mkdtemp()
    ret = get_missing_bases.fetch_from_snapshot('foo', '1.2-1', output_dir)
    self.assertTrue(ret)
    dir_contents = os.listdir(output_dir)
    self.assertEqual(len(dir_contents), 3)
    self.assertIn('foo_1.2-1.dsc', dir_contents)
