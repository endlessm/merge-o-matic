class PackageNotFound(Exception):
  def __init__(self, name, dist, component):
    self._n = name
    self._d = dist
    self._c = component

  def __str__(self):
    return repr(self)

  def __repr__(self):
    return "(%s, %s, %s)"%(self._n, self._d, self._c)

class PackageVersionNotFound(Exception):
  def __init__(self, package, version):
    self._p = package
    self._v = version

  def __str__(self):
    return repr(self)

  def __repr__(self):
    return "%s(%s)"%(self._p, self._v)
