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
        "dists": [ "SUITE_A", "SUITE_B" ],
        "components": [ "target", "sdk", "development" ],
        "expire": True,
        },
    "ubuntu": {
        "mirror": "http://archive.ubuntu.com/ubuntu",
        "dists": [ "precise-updates", "precise-security", "precise" ],
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
    }

DISTRO_TARGETS = {
    "SUITE_A-target": {
        "distro": "DISTRO",
        "dist": "SUITE_A",
        "component": "target",
        "sources": [ "precise+updates", ],
        "commit": False
    },
    "SUITE_A-sdk": {
        "distro": "DISTRO",
        "dist": "SUITE_A",
        "component": "sdk",
        "sources": [ "precise+updates", ],
        "commit": False
    },
    "SUITE_A-development": {
        "distro": "DISTRO",
        "dist": "SUITE_A",
        "component": "development",
        "sources": [ "precise+updates", ],
        "commit": False
    },
    "SUITE_B-target": {
        "distro": "DISTRO",
        "dist": "SUITE_B",
        "component": "target",
        "sources": ["precise+updates", ]
    },
    "SUITE_B-sdk": {
        "distro": "DISTRO",
        "dist": "SUITE_B",
        "component": "sdk",
        "sources": ["precise+updates", ]
    },
    "SUITE_B-development": {
        "distro": "DISTRO",
        "dist": "SUITE_B",
        "component": "development",
        "sources": ["precise+updates", ]
    },
}

# Time format for RSS feeds
RSS_TIME_FORMAT = "%a, %d %b %Y %H:%M:%S %Z"
