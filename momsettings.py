# Output root
ROOT = "/srv/obs/merge-o-matic"

# Website root
MOM_URL = "http://SERVER:83/"

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
    #"DISTRO-standard": {
        #"obs": {
            #"url": "https://SERVER:444",
            #"project": "DISTRO"
        #},
        #"mirror": "http://SERVER:82/debian/DISTRO/standard/",
        #"dists": [ None ],
        #"components": [ None ],
        #"expire": True,
        #},
    "DISTRO-SUITE_A-target": {
        "obs": {
            "url": "https://SERVER:444",
            "project": "DISTRO:SUITE_A:target"
        },
        "dists": [ None ],
        "components": [ None ],
        "expire": True,
        },
    "ubuntu": {
        "mirror": "http://archive.ubuntu.com/ubuntu",
        "dists": [ "precise-updates", "precise" ],
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

# Destination distributions and releases
OUR_DISTROS = [ "DISTRO-SUITE_A-target" ]
OUR_DISTS   = { "DISTRO-SUITE_A-target" : [ None ] }

# Default source distribution and release
SRC_DISTROS = { "DISTRO-SUITE_A-target" : "ubuntu" }
SRC_DISTS   = { "DISTRO-SUITE_A-target" : "precise-updates" }

# Time format for RSS feeds
RSS_TIME_FORMAT = "%a, %d %b %Y %H:%M:%S %Z"
