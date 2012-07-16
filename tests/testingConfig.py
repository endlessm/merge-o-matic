ROOT = "/tmp/mom"

DISTROS = {
  "target": {
    "obs": {
      "url": "https://localhost:444",
      "project": "target"
    }
  },
  "live-test": {
    "obs": {
      "url": "https://SERVER:444/",
      "project": "DISTRO:SUITE_A:target"
    }
  }
}
