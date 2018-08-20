# Only used when running from the source tree; replaced by a hard-coded version
# in installations.

import os
import subprocess

try:
    VERSION = subprocess.check_output(os.path.join(os.path.dirname(__file__),
                                                   './get-version.sh')).strip()
except Exception:
    VERSION = '0~unknown-version'
