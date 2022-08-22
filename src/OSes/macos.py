import os
import shutil
import time
import sys

import config
import dockerapi as docker
import util

FLAVOR = 'macos'
PLIST_PATH = '/Library/LaunchDaemons/com.zanaca.dockerdns-tunnel.plist'
KNOWN_HOSTS_FILE = f'{config.HOME_ROOT}/.ssh/known_hosts'
APP_DESTINATION = f'{config.HOME}/Applications/dockerdns-tunnel.app'
DOCKER_CONF_FOLDER = f'{config.HOME}/.docker'
DOCKER_BUILD_TARGET = 'base'


def setup(tld=config.TOP_LEVEL_DOMAIN) -> int:
    if not os.path.isdir('/etc/resolver'):
        os.mkdir('/etc/resolver')
    open(f'/etc/resolver/{tld}',
         'w').write(f'nameserver {docker.NETWORK_GATEWAY}')

    plist = open('src/templates/com.zanaca.dockerdns-tunnel.plist',
                 'r').read().replace('{PWD}', config.BASE_PATH)
    open(PLIST_PATH, 'w').write(plist)
    os.system(f'sudo launchctl load -w {PLIST_PATH} 1>/dev/null 2>/dev/null')

    return 0


def install(tld=config.TOP_LEVEL_DOMAIN) -> int:
    print('Generating known_hosts backup for user "root", if necessary')
    if not os.path.exists(f'{config.HOME_ROOT}/.ssh'):
        os.mkdir(f'{config.HOME_ROOT}/.ssh')
        os.chmod(f'{config.HOME_ROOT}/.ssh', 700)

    if os.path.exists(KNOWN_HOSTS_FILE):
        shutil.copy2(KNOWN_HOSTS_FILE, f'{config.HOME_ROOT}/.ssh/known_hosts_pre_docker-dns')

    time.sleep(3)
    port = False
    ports = docker.get_exposed_port(config.DOCKER_CONTAINER_NAME)
    if '22/tcp' in ports:
        port = int(ports['22/tcp'][0]['HostPort'])

    if not port:
        print('Problem fetching ssh port')
        return 1

    os.system(f'ssh-keyscan -H -t ecdsa-sha2-nistp256 -p {port} 127.0.0.1 2> /dev/null >> {KNOWN_HOSTS_FILE}')

    if not os.path.exists(APP_DESTINATION):
        uid = os.getuid()
        gid = os.getgid()
        if 'SUDO_UID' in os.environ:
            uid = int(os.environ.get('SUDO_UID'))
            gid = int(os.environ.get('SUDO_GID'))
        shutil.copytree('src/templates/dockerdns-tunnel_app', APP_DESTINATION)
        util.change_owner_recursive(APP_DESTINATION, uid, gid)

    workflow = open(f'{APP_DESTINATION}/Contents/document.wflow', 'r').read()
    workflow = workflow.replace('[PATH]', config.BASE_PATH)
    open(f'{APP_DESTINATION}/Contents/document.wflow', 'w').write(workflow)
    original_arg = sys.argv
    original_arg[1] = 'tunnel'
    original_arg.append('&')
    os.system(' '.join(original_arg))
    return 0


def uninstall(tld=config.TOP_LEVEL_DOMAIN) -> int:
    if os.path.exists(f'/etc/resolver/{tld}'):
        print('Removing resolver file')
        os.unlink(f'/etc/resolver/{tld}')

    if os.path.exists(PLIST_PATH):
        print('Removing tunnel service')
        os.system(f'sudo launchctl unload -w {PLIST_PATH} 1>/dev/null 2>/dev/null')
        os.unlink(PLIST_PATH)

    if os.path.exists(f'{config.HOME_ROOT}/.ssh/known_hosts_pre_docker-dns'):
        print('Removing kwown_hosts backup')
        os.unlink(f'{config.HOME_ROOT}/.ssh/known_hosts_pre_docker-dns')

    if os.path.exists(APP_DESTINATION):
        print('Removing tunnel app')
        shutil.rmtree(APP_DESTINATION)

    return 0
