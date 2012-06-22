# Output root
ROOT = "/srv/obs/merge-o-matic"

# Website root
MOM_URL = "http://SERVER:83/"

# Used for emails
MOM_NAME = "DISTRO Merge-o-Matic"
MOM_EMAIL = "mom@SERVER"

# Who to send bug emails to
RECIPIENTS = ['trever.fischer@collabora.co.uk']
#             [ "ubuntu-archive@lists.ubuntu.com",
#               "ubuntu-devel@lists.ubuntu.com" ]

# Distribution definitions
# For additional subprojects, use additional distro definitions
DISTROS = {
    "SUITE_A-target": {
        "obs": {
            "url": "https://SERVER:444",
            "project": "DISTRO:SUITE_A:target"
        },
        "mirror": "http://SERVER:82/debian/DISTRO:/SUITE_A:/target/",
        "dists": [ None ],
        "components": [ None ],
        "expire": True,
        },
    "SUITE_A-sdk": {
        "obs": {
            "url": "https://SERVER:444",
            "project": "DISTRO:SUITE_A:sdk"
        },
        "mirror": "http://SERVER:82/debian/DISTRO:/SUITE_A:/sdk/",
        "dists": [ None ],
        "components": [ None ],
        "expire": True,
        },
    "SUITE_A-devel": {
        "obs": {
            "url": "https://SERVER:444",
            "project": "DISTRO:SUITE_A:development"
        },
        "mirror": "http://SERVER:82/debian/DISTRO:/SUITE_A:/development/",
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

DISTRO_SOURCES = {
    "precise+updates": [
        { "distro": "ubuntu", "dist": "precise-updates" },
        { "distro": "ubuntu", "dist": "precise" } ],
    }

DISTRO_TARGETS = {
    "SUITE_A-target": {
        "distro": "SUITE_A-target",
        "dist": None,
        "component": None,
        "sources": [ "precise+updates", ] },
    }

# Time format for RSS feeds
RSS_TIME_FORMAT = "%a, %d %b %Y %H:%M:%S %Z"
