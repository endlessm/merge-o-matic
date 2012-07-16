import unittest
from configTests import *
from oscTests import *
import logging

def main():
  logging.basicConfig(level=logging.DEBUG)
  unittest.main()

if __name__ == "__main__":
  main()
