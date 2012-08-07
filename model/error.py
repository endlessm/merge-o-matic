class PackageNotFound(Exception):
  def __str__(self):
    return repr(self.args)
