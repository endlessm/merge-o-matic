# Fake config for use in the configTests unit tests
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
      "url": "https://obs:444/",
      "project": "dderivative"
    }
  }
}
