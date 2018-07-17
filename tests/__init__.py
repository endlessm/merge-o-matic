# "packages cannot be executed directly", see __main__.py for main()

import os
import logging
import shutil
import tempfile
import shutil
import atexit

import get_missing_bases

os.environ['MOM_TEST'] = '1'

if 'MOM_TEST_DEBUG' in os.environ:
    logging.basicConfig(level=logging.DEBUG)
else:
    logging.basicConfig(level=logging.INFO)

debsnap_base = tempfile.mkdtemp(prefix='momtest.debsnap.')
get_missing_bases.BASE_URL = 'file://' + debsnap_base
if 'MOM_TEST_NO_CLEANUP' not in os.environ:
  atexit.register(shutil.rmtree, debsnap_base)
