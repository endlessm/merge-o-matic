# Output root
ROOT = "/srv/obs/merge-o-matic"

# Website root
MOM_URL = "http://SERVER:83/"

# Used for emails
MOM_NAME = "Merge-o-Matic"
MOM_EMAIL = "mom@SERVER"

# Who to send bug emails to
RECIPIENTS = ['trever.fischer@collabora.co.uk']
#             [ "ubuntu-archive@lists.ubuntu.com",
#               "ubuntu-devel@lists.ubuntu.com" ]

# Distribution definitions
# For additional subprojects, use additional distro definitions
DISTROS = {
    "DISTRO": {
        "obs": {
            "url": "https://SERVER:444",
            "project": "DISTRO",
        },
        "mirror": "http://SERVER:82/debian/",
        "dists": [ "SUITE_A", "SUITE_B", "SUITE_C" ],
        "components": [ "target", "sdk", "development" ],
        "expire": True,
        },
    "ubuntu": {
        "mirror": "http://archive.ubuntu.com/ubuntu",
        "dists": [ "precise-updates", "precise-security", "precise", "quantal", "quantal-updates", "quantal-security" ],
        "components": [ "main", "restricted", "universe", "multiverse" ],
        "expire": True,
        },
#    "debian": {
#        "mirror": "http://ftp.uk.debian.org/debian",
#        "dists": [ "unstable", "testing", "testing-proposed-updates", "experimental" ],
#        "components": [ "main", "contrib", "non-free" ],
#        "expire": True,
#        },
    }

DISTRO_SOURCES = {
    "precise+updates": [
        { "distro": "ubuntu", "dist": "precise-updates" },
        { "distro": "ubuntu", "dist": "precise-security" },
        { "distro": "ubuntu", "dist": "precise" } ],
    'quantal+updates': [
        { "distro": "ubuntu", "dist": "quantal-updates" },
        { "distro": "ubuntu", "dist": "quantal-security" },
        { "distro": "ubuntu", "dist": "quantal" } ],
    }

DISTRO_TARGETS = {}

def defineDist(name, upstream, commitable):
  for component in DISTROS['DISTRO']['components']:
    DISTRO_TARGETS["%s-%s"%(name, component)] = {
      'distro': 'DISTRO',
      'dist': name,
      'component': component,
      'sources': [ upstream, ],
      'commit': commitable
    }

defineDist('SUITE_A', 'precise+updates', False)
defineDist('SUITE_B', 'precise+updates', True)
defineDist('SUITE_C', 'quantal+updates', True)

# Time format for RSS feeds
RSS_TIME_FORMAT = "%a, %d %b %Y %H:%M:%S %Z"
