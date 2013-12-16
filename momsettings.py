# vim: set sw=4 sts=4 et fileencoding=utf-8 :
#
# Merge-o-Matic configuration file, in Python syntax.

# Not directly used for anything, but we use them to reduce duplication
# in this file
_OBS_SERVER = "obs.example.com"
# MoM often runs on the same machine as the OBS master, but it can be
# different if you want. Again, this is not used by MoM, just used within
# this file.
_MOM_SERVER = _OBS_SERVER

# Output root
ROOT = "/srv/obs/merge-o-matic"

# Website root
MOM_URL = "http://%s:83/" % _MOM_SERVER

# Used as the 'from' for any mails sent
MOM_NAME = "Merge-o-Matic"
MOM_EMAIL = "mom@%s" % _MOM_SERVER

# Who to send bug emails to
RECIPIENTS = ['mom@%s' % _MOM_SERVER]

# Distribution definitions
# For additional subprojects, use additional distro definitions
DISTROS = {
    # dderivative: an example Debian derivative that we're maintaining
    # in OBS
    "dderivative": {
        "obs": {
            "url": "https://%s:444" % _OBS_SERVER,
            "web": "https://%s" % _OBS_SERVER,
            # The OBS projects are expected to be something like
            # dderivative:alpha:main
            "project": "dderivative",
        },
        "mirror": "http://%s:82/shared/dderivative/" % _OBS_SERVER,
        "dists": [ "alpha", "beta" ],
        "components": [ "main", "contrib", "non-free" ],
        "expire": True,
    },
    # uderivative: an example Ubuntu derivative in the same OBS instance
    "uderivative": {
        "obs": {
            "url": "https://%s:444" % _OBS_SERVER,
            "web": "https://%s" % _OBS_SERVER,
            # The OBS projects are expected to be something like
            # home:somebody:uderivative:aardvark:misc
            "project": "home:somebody:uderivative",
        },
        "mirror": "http://%s:82/shared/somebody-uderivative/" % _OBS_SERVER,
        "dists": [ "aardvark", "badger" ],
        "components": [ "misc", "other" ],
        "expire": True,
    },
    # Ubuntu, an upstream project from which we can pull packages
    "ubuntu": {
        "mirror": "http://archive.ubuntu.com/ubuntu",
        "dists": [
            "precise", "precise-updates", "precise-security",
            "raring", "raring-updates", "raring-security",
        ],
        "components": [ "main", "restricted", "universe", "multiverse" ],
        "expire": True,
    },
    # Debian, another upstream project
    "debian": {
        "mirror": "http://ftp.debian.org/debian",
        "dists": [
            "squeeze", "squeeze-updates",
            "wheezy", "wheezy-updates",
            "jessie", "jessie-updates", "testing-proposed-updates",
            "unstable", "experimental",
        ],
        "components": [ "main", "contrib", "non-free" ],
        "expire": True,
    },
    # Debian's security updates are in a separate apt repository, so we
    # have to treat them like a separate upstream distro
    "debian-security": {
        "mirror": "http://security.debian.org",
        "dists": [ "squeeze/updates", "wheezy/updates" ],
        "components": [ "main", "contrib", "non-free" ],
        "expire": True,
    },
}

# Sets of sources of upstream packages
DISTRO_SOURCES = {
    # Ubuntu 'raring' and its updates
    'raring+updates': [
        { "distro": "ubuntu", "dist": "raring-updates" },
        { "distro": "ubuntu", "dist": "raring-security" },
        { "distro": "ubuntu", "dist": "raring" },
    ],
    # Ubuntu 'precise' and its updates
    'precise+updates': [
        { "distro": "ubuntu", "dist": "precise-updates" },
        { "distro": "ubuntu", "dist": "precise-security" },
        { "distro": "ubuntu", "dist": "precise" },
    ],
    # Debian unstable
    'unstable': [
        { "distro": "debian", "dist": "unstable" },
    ],
    # Debian wheezy (Debian 7) and its updates, including security updates
    # from a separate apt repository
    'wheezy+updates': [
        { "distro": "debian", "dist": "wheezy" },
        { "distro": "debian", "dist": "wheezy-updates" },
        { "distro": "debian-security", "dist": "wheezy/updates" },
    ],
}

DISTRO_TARGETS = {}

def defineDist(distro, name, upstreams, commitable,
        sources_per_package=None):
  """Adds an entry to DISTRO_TARGETS.

     @param name The name of the distro
     @param upstream A key from DISTRO_SOURCES, linking this distro with a collection of upstream repos
     @param commitable Whether or not you want to be able to commit to OBS, or submit merge requests.
     @param distro The distro to use
  """
  if sources_per_package is None:
    sources_per_package = {}

  for component in DISTROS[distro]['components']:
    DISTRO_TARGETS["%s-%s"%(name, component)] = {
      'distro': distro,
      'dist': name,
      'component': component,
      'sources': [ upstreams, ],
      'commit': commitable,
      'sources_per_package': sources_per_package,
    }

# Some example targets:

# dderivative alpha gets packages from Debian wheezy, except that we
# need a newer version of miscfiles from unstable for some reason
defineDist('dderivative', 'alpha', 'wheezy+updates', False,
      sources_per_package={
        'miscfiles': [ 'unstable' ],
      })
# dderivative beta is entirely based on unstable
defineDist('dderivative', 'beta', 'unstable', False)
# uderivative aardvark is based on Ubuntu precise
defineDist('uderivative', 'aardvark', 'precise+updates', False)
# uderivative badger is mostly based on Ubuntu raring, but picks up systemd
# updates from Debian
defineDist('uderivative', 'badger', 'raring+updates', False,
        sources_per_package={
            'systemd': [ 'unstable' ],
        })

# Time format for RSS feeds
RSS_TIME_FORMAT = "%a, %d %b %Y %H:%M:%S %Z"

# Debian packaging revision suffix for the first derived version; for instance
# Ubuntu's patched hello_1.2-3 package would be hello_1.2-3ubuntu1,
# hello_1.2-3ubuntu2, etc., so they would use "ubuntu1" in their
# MOM installation.
LOCAL_SUFFIX = "local1"
