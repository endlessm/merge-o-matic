# Output root
ROOT = "/srv/obs/merge-o-matic"

# Website root
MOM_URL = "http://SERVER:83/"

# Used as the 'from' for any mails sent
MOM_NAME = "Merge-o-Matic"
MOM_EMAIL = "singularity-sysadmin@collabora.co.uk"

# Who to send bug emails to
RECIPIENTS = ['singularity-sysadmin@collabora.co.uk']

# Distribution definitions
# For additional subprojects, use additional distro definitions
DISTROS = {
    "singularity": {
        "obs": {
            "url": "https://build.collabora.co.uk:444",
            "project": "singularity",
        },
        "mirror": "http://SERVER:82/shared/singularity/",
        "dists": [ "alphacentauri" ],
        "components": [ "core", "sdk" ],
        "expire": True,
        },
    "DISTRO": {
	"obs": {
	    "url": "https://build.collabora.co.uk:444",
	    "project": "DISTRO",
	},
	"mirror": "http://SERVER:82/shared/DISTRO/",
	"dists": [ "SUITE" ],
	# "components": [ "COMPONENT" ],
	"components": [ ],
	"expire": True,
	},
    "ubuntu": {
        "mirror": "http://archive.ubuntu.com/ubuntu",
        "dists": [ "raring", "raring-updates", "raring-security" ],
        "components": [ "main", "restricted", "universe", "multiverse" ],
        "expire": True,
        },
    "debian": {
        "mirror": "http://ftp.uk.debian.org/debian",
        "dists": [ "unstable", "testing", "testing-proposed-updates", "experimental" ],
        "components": [ "main", "contrib", "non-free" ],
        "expire": True,
        },
  }
  
DISTRO_SOURCES = {
    'raring+updates': [
        { "distro": "ubuntu", "dist": "raring-updates" },
        { "distro": "ubuntu", "dist": "raring-security" },
        { "distro": "ubuntu", "dist": "raring" },
    ],
    'unstable': [
        { "distro": "debian", "dist": "unstable" },
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
      'sources': [ upstream, ],
      'commit': commitable,
      'sources_per_package': sources_per_package,
    }

defineDist('singularity','alphacentauri', 'raring+updates', False,
      'sources_per_package': {
        'miscfiles': [ 'unstable' ],
      })
defineDist('DISTRO','SUITE', 'raring+updates', False)

# Time format for RSS feeds
RSS_TIME_FORMAT = "%a, %d %b %Y %H:%M:%S %Z"

LOCAL_SUFFIX = "co1"
