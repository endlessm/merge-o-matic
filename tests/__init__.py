# "packages cannot be executed directly", see __main__.py for main()

import os
import logging
import shutil

os.environ['MOM_TEST'] = '1'

if 'MOM_TEST_DEBUG' in os.environ:
    logging.basicConfig(level=logging.DEBUG)
