# Output root
ROOT = "/srv/obs/merge-o-matic"

# Website root
MOM_URL = "http://SERVER:83/"

# Used as the 'from' for any mails sent
MOM_NAME = "Merge-o-Matic for DISTRO"
MOM_EMAIL = "mom@SERVER"

# Who to send bug emails to
RECIPIENTS = ['DISTRO-sysadmin@collabora.co.uk']

# Distribution definitions
# For additional subprojects, use additional distro definitions
DISTROS = {
    "DISTRO": {
        "mirror": "http://SERVER:82/shared/DISTRO",
        "dists": [ "SUITE_C", "SUITE_D"],
        "components": [ "target", "sdk", "development" ],
        "expire": True,
        },
    "ubuntu": {
        "mirror": "http://archive.ubuntu.com/ubuntu",
        "dists": [ "quantal", "quantal-updates", "quantal-security" ],
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
    'quantal+updates': [
        { "distro": "ubuntu", "dist": "quantal-updates" },
        { "distro": "ubuntu", "dist": "quantal-security" },
        { "distro": "ubuntu", "dist": "quantal" } ],
    }

DISTRO_TARGETS = {}

def defineDist(distro, name, upstream, commitable):
  """Adds an entry to DISTRO_TARGETS.

     @param name The name of the distro
     @param upstream A key from DISTRO_SOURCES, linking this distro with a collection of upstream repos
     @param commitable Whether or not you want to be able to commit to OBS, or submit merge requests.
     @param distro The distro to use
  """
  for component in DISTROS[distro]['components']:
    DISTRO_TARGETS["%s-%s"%(name, component)] = {
      'distro': distro,
      'dist': name,
      'component': component,
      'sources': [ upstream, ],
      'commit': commitable
    }

defineDist('DISTRO', 'SUITE_C', 'quantal+updates', False)
defineDist('DISTRO', 'SUITE_D', 'quantal+updates', False)

# Time format for RSS feeds
RSS_TIME_FORMAT = "%a, %d %b %Y %H:%M:%S %Z"

LOCAL_SUFFIX = "co1"
