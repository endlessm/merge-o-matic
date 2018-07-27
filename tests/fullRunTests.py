from copy import copy
from optparse import OptionParser
import unittest

import testhelper
from util import get_option_parser

import main

class FullRunTest(unittest.TestCase):
  # Run full program to check it doesn't raise any exceptions
  def test_fullRun(self):
    target_repo, source1_repo, source2_repo = \
      testhelper.standard_simple_config(num_stable_sources=2)

    # Set up a merge
    package = testhelper.build_and_import_simple_package('foo', '1.0-1',
                                                         source1_repo)

    forked = copy(package)
    forked.changelog_entry(version='1.0-1mom1')
    open(forked.pkg_path + '/debian/new.file', 'w').write('hello')
    forked.build()
    target_repo.importPackage(forked)

    package.changelog_entry(version='1.2-1')
    package.create_orig()
    package.build()
    source2_repo.importPackage(package)

    # Set up a conflict
    package = testhelper.build_and_import_simple_package('bar', '2.0-1',
                                                         source1_repo)

    forked = copy(package)
    forked.changelog_entry(version='2.0-1mom1')
    open(forked.pkg_path + '/debian/new.file', 'w').write('hello')
    forked.build()
    target_repo.importPackage(forked)

    package.changelog_entry(version='2.2-1')
    open(package.pkg_path + '/debian/new.file', 'w').write('conflicts')
    package.create_orig()
    package.build()
    source2_repo.importPackage(package)

    # Set up a sync
    package = testhelper.build_and_import_simple_package('eek', '3.0-1',
                                                         target_repo)

    updated = copy(package)
    updated.changelog_entry(version='3.1-1')
    updated.create_orig()
    updated.build()
    source1_repo.importPackage(updated)

    # Run the program
    parser = get_option_parser()
    main.options(parser)
    options, args = parser.parse_args()
    main.main(options, [])
