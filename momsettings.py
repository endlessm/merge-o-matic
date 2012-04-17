# Output root
ROOT = "/srv/obs/merge-o-matic"

# Website root
MOM_URL = "http://SERVER2:83/"

# Used for emails
MOM_NAME = "DISTRO Merge-o-Matic"
MOM_EMAIL = "mom@SERVER"

# Who to send bug emails to
RECIPIENTS = []
#             [ "ubuntu-archive@lists.ubuntu.com",
#               "ubuntu-devel@lists.ubuntu.com" ]

# Distribution definitions
# For additional subprojects, use additional distro definitions
DISTROS = {
    "DISTRO-standard": {
        "obs": {
            "url": "https://SERVER:444",
            "project": "DISTRO"
        },
        "mirror": "http://SERVER:82/debian/DISTRO/standard/",
        "dists": [ None ],
        "components": [ None ],
        "expire": True,
        },
    "ubuntu": {
        "mirror": "http://archive.ubuntu.com/ubuntu",
        "dists": [ "precise" ],
        "components": [ "main", "restricted", "universe", "multiverse" ],
        "expire": True,
        },
    "DISTRO-SERVER2": {
        "obs": {
            "url": "https://SERVER2:444",
            "project": "DISTRO"
        },
        "dists": [ None ],
        "components": [ None ],
        "expire": True,
        },
    }

# Destination distributions and releases
OUR_DISTROS = [ "DISTRO-standard" ]
OUR_DISTS   = { "DISTRO-standard" : [ None ] }

# Default source distribution and release
SRC_DISTRO = "ubuntu"
SRC_DIST   = "precise"


# Time format for RSS feeds
RSS_TIME_FORMAT = "%a, %d %b %Y %H:%M:%S %Z"
