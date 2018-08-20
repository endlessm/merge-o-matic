class PackageNotFound(Exception):
    def __init__(self, name, dist=None, component=None, version=None):
        self._n = name
        self._d = dist
        self._c = component
        self._v = version

    def __str__(self):
        return repr(self)

    def __repr__(self):
        return "(%s, %s, %s, %s)" % (self._n, self._d, self._c, self._v)


class PackageVersionNotFound(Exception):
    def __init__(self, package, version):
        self._p = package
        self._v = version

    def __str__(self):
        return repr(self)

    def __repr__(self):
        return "%s(%s)" % (self._p, self._v)
