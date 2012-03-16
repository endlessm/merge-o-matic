# Output root
ROOT = "/obs/merge-o-matic"

# Website root
MOM_URL = "http://SERVER:82/DISTRO/merge-o-matic/"

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
#    "dapper-security": {
#        "mirror": "http://security.ubuntu.com/ubuntu",
#        "dists": [ "dapper-security" ],
#        "components": [ "main", "restricted", "universe", "multiverse" ],
#        "expire": False,
#        },
#    "hardy-security": {
#        "mirror": "http://security.ubuntu.com/ubuntu",
#        "dists": [ "hardy-security" ],
#        "components": [ "main", "restricted", "universe", "multiverse" ],
#        "expire": False,
#        },
#    "intrepid-security": {
#        "mirror": "http://security.ubuntu.com/ubuntu",
#        "dists": [ "intrepid-security" ],
#        "components": [ "main", "restricted", "universe", "multiverse" ],
#        "expire": False,
#        },
#    "jaunty-security": {
#        "mirror": "http://security.ubuntu.com/ubuntu",
#        "dists": [ "jaunty-security" ],
#        "components": [ "main", "restricted", "universe", "multiverse" ],
#        "expire": False,
#        },
    }

# Destination distributions and releases
OUR_DISTROS = [ "DISTRO-standard" ]
OUR_DISTS   = { "DISTRO-standard" : [ None ] }

# Default source distribution and release
SRC_DISTRO = "ubuntu"
SRC_DIST   = "precise"


# Time format for RSS feeds
RSS_TIME_FORMAT = "%a, %d %b %Y %H:%M:%S %Z"
