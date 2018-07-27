# implementation of 'python -m tests'

import unittest

suite = unittest.defaultTestLoader.discover('.', pattern='*Tests.py')
unittest.TextTestRunner(verbosity=2).run(suite)
