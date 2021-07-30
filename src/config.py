import json
import os
import platform
import socket
import subprocess
import sys

import util

APP = os.path.basename(sys.argv[0])

USER = os.environ.get('SUDO_USER')
if not USER:
    USER = os.environ.get('USER')
HOME = os.path.expanduser(f"~{USER}")
HOME_ROOT = os.path.expanduser("~root")
BASE_PATH = os.path.dirname(os.path.dirname(__file__))
HOSTNAME = socket.gethostname()
HOSTUNAME = platform.uname().system

if util.on_macos or util.on_windows:
    NAME = platform.uname()[0]

else:
    NAME = open('/etc/os-release', 'r').read().split('NAME="')[1].split('"')[0]

if util.on_macos:
    VERSION_MAJOR_ID = '.'.join(platform.mac_ver()[0].split('.')[0:2])
    version = platform.mac_ver()[0].split('.')
    OS_VERSION = int(version[1]) + int(version[0]) * 1000
elif util.on_windows or util.on_wsl:
    VERSION_MAJOR_ID = subprocess.run(['powershell.exe', '[Environment]::OSVersion.Version.Major'],
                                      capture_output=True, text=True).stdout.split('\n')[0]
    version = [VERSION_MAJOR_ID, 0]

else:
    VERSION_MAJOR_ID = open(
        '/etc/os-release', 'r').read().split('VERSION_ID="')[1].split('"')[0]
    version = VERSION_MAJOR_ID.split('.')

if len(version) > 1:
    OS_VERSION = int(version[1]) + int(version[0]) * 1000

else:
    OS_VERSION = int(version[0]) * 1000

OS = f'{HOSTUNAME}_{NAME}'
TOP_LEVEL_DOMAIN = (util.read_cache('tld') or 'docker').strip()
DOCKER_CONTAINER_TAG = (util.read_cache('tag') or 'ns0').strip()
DOCKER_CONTAINER_NAME = (util.read_cache('name') or DOCKER_CONTAINER_TAG).strip()
SUPPORTED_OSES = json.load(open(f'{BASE_PATH}/supported_os.json', 'r'))
