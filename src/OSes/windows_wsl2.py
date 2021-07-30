import os
import shutil
import subprocess
import time

import config
import dockerapi as docker

FLAVOR = 'windows.wsl2'
DOCKER_CONF_FOLDER = '/etc/docker'
DNSMASQ_LOCAL_CONF = '/etc/NetworkManager/dnsmasq.d/01_docker'
KNOWN_HOSTS_FILE = f'{config.HOME_ROOT}/.ssh/known_hosts'
WSL_CONF = '/etc/wsl.conf'
DNS = '127.0.0.1'
DISABLE_MAIN_RESOLVCONF_ROUTINE = True
RESOLVCONF = '/run/resolvconf/resolv.conf'
RESOLVCONF_HEADER = 'options timeout:1 #@docker-dns\nnameserver 127.0.0.1 #@docker-dns'
CMD_PATH = '/mnt/c/Windows/System32/cmd.exe'
STARTUP_FOLDER_PATH = '/mnt/c/Users/[USERNAME]/AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Startup'
DOCKER_BUILD_TARGET = 'base'

if not os.path.exists(DNSMASQ_LOCAL_CONF):
    DNSMASQ_LOCAL_CONF = DNSMASQ_LOCAL_CONF.replace('dnsmasq.d', 'conf.d')


def __generate_resolveconf():
    if os.path.exists(RESOLVCONF):
        RESOLVCONF_DATA = open(RESOLVCONF, 'r').read()

    else:
        RESOLVCONF_DATA = open('/etc/resolv.conf', 'r').read()

    if '#@docker-dns' not in RESOLVCONF_DATA:
        RESOLVCONF_DATA = f"{RESOLVCONF_HEADER}\n{RESOLVCONF_DATA}"

    resolv_script = f"""#!/usr/bin/env sh
[ "$(ps a | grep tunnel | wc -l)" -le 1 ] && {config.BASE_PATH}/bin/docker-dns tunnel &

if `grep -q \@docker-dns /etc/resolv.conf`; then
    exit 0
fi
cp /etc/resolv.conf /tmp/resolv.ddns
rm /etc/resolv.conf > /dev/null || true;
cat <<EOL > /etc/resolv.conf
{RESOLVCONF_HEADER}
EOL

if [ -f "{RESOLVCONF}" ]; then
    cat {RESOLVCONF} >> /etc/resolv.conf
else
    cat /tmp/resolv.ddns >> /etc/resolv.conf
fi
rm /tmp/resolv.ddns
"""
    open('/etc/resolv.conf', 'w').write(RESOLVCONF_DATA)

    open(f'{config.BASE_PATH}/bin/docker-dns.service.sh',
         'w').write(resolv_script)
    os.chmod(f'{config.BASE_PATH}/bin/docker-dns.service.sh', 0o744)

    # Gotta find a better way to start that service, as real services does not work on WSL2 as you have microsoft's init.
    bashrc_content = open(f'{config.HOME}/.bashrc', 'r').read()
    if 'docker-dns end' in bashrc_content:
        bashrc_content_pre = bashrc_content.split('# docker-dns "service"')[0]
        bashrc_content_pos = bashrc_content.split('# docker-dns end')
        if len(bashrc_content_pos) == 1:
            bashrc_content_pos = bashrc_content_pos[0]
        else:
            bashrc_content_pos = bashrc_content_pos[1]
        bashrc_content = f'{bashrc_content_pre}{bashrc_content_pos}'

    service_script = f"""# docker-dns "service"  for windows wsl2
[ "$(ps a | grep tunnel | wc -l)" -le 1 ] && sudo {config.BASE_PATH}/bin/docker-dns.service.sh
# docker-dns end
"""
    bashrc_content = f"{bashrc_content}{service_script}"
    open(f'{config.HOME}/.bashrc', 'w').write(bashrc_content)
    os.system(
        f"echo '%sudo   ALL=(ALL) NOPASSWD: {config.BASE_PATH}/bin/docker-dns.service.sh' > /etc/sudoers.d/99-dockerdns")


def __get_windows_username():
    return subprocess.run(['powershell.exe', '$env:UserName'], capture_output=True, text=True).stdout.split('\n')[0]


def __generate_proxy_bat(ssh_port=None):
    if not ssh_port:
        return False

    proxy_override = ''
    for a in range(1, 255):
        if a != 172:
            proxy_override += f'{a}.*;'
        else:
            for b in range(0, 15):
                proxy_override += f'{a}.{b}.*;'
            for b in range(32, 255):
                proxy_override += f'{a}.{b}.*;'

    script = f"""
start /B "" ssh -N root@127.0.0.1 -p {ssh_port} -f  -D 31080

reg add "HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /f /v ProxyEnable /t REG_DWORD /d 1
reg add "HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /f /v ProxyServer /t REG_SZ /d socks=127.0.0.1:31080
reg add "HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /f /v ProxyOverride /t REG_SZ /d {proxy_override}"
"""

    file_name = f'{STARTUP_FOLDER_PATH}/docker-dns.bat'
    file_name = file_name.replace('[USERNAME]', __get_windows_username())
    open(file_name, 'w').write(script)

    file_name = file_name.replace('/mnt/c', 'C:').replace(' ', '\ ').replace('/', '\\\\')
    os.system(f'{CMD_PATH} /c {file_name} &')


def __get_ssh_port():
    port = False
    ports = docker.get_exposed_port(config.DOCKER_CONTAINER_NAME)
    if '22/tcp' in ports:
        port = int(ports['22/tcp'][0]['HostPort'])

    return port


def setup(tld=config.TOP_LEVEL_DOMAIN):
    if not os.path.isdir('/etc/resolver'):
        os.mkdir('/etc/resolver')
    open(f'/etc/resolver/{tld}',
         'w').write(f'nameserver 127.0.0.1')

    return True


def install(tld=config.TOP_LEVEL_DOMAIN):
    print('Generating known_hosts backup for user "root", if necessary')
    if not os.path.exists(f'{config.HOME_ROOT}/.ssh'):
        os.mkdir(f'{config.HOME_ROOT}/.ssh')
        os.chmod(f'{config.HOME_ROOT}/.ssh', 700)

    if os.path.exists(KNOWN_HOSTS_FILE):
        shutil.copy2(KNOWN_HOSTS_FILE,
                     f'{config.HOME_ROOT}/.ssh/known_hosts_pre_docker-dns')

    time.sleep(3)
    port = __get_ssh_port()
    if not port:
        raise ('Problem fetching ssh port')

    os.system(
        f'ssh-keyscan -H -t ecdsa-sha2-nistp256 -p {port} 127.0.0.1 2> /dev/null >> {KNOWN_HOSTS_FILE}')

    __generate_resolveconf()

    __generate_proxy_bat(ssh_port=port)

    # create etc/resolv.conf for
    return True


def uninstall(tld=config.TOP_LEVEL_DOMAIN):
    if os.path.exists(f'/etc/resolver/{tld}'):
        print('Removing resolver file')
        os.unlink(f'/etc/resolver/{tld}')

    ini = open(WSL_CONF, 'r').read()
    ini = ini.replace('ngenerateResolvConf = false',
                      'ngenerateResolvConf = true')
    open(WSL_CONF, 'w').write(ini)

    if os.path.exists(DNSMASQ_LOCAL_CONF):
        os.unlink(DNSMASQ_LOCAL_CONF)

    if os.path.exists(f'{config.HOME_ROOT}/.ssh/known_hosts_pre_docker-dns'):
        print('Removing kwown_hosts backup')
        os.unlink(f'{config.HOME_ROOT}/.ssh/known_hosts_pre_docker-dns')

    file_name = f'{STARTUP_FOLDER_PATH}/docker-dns.bat'
    if os.path.exists(file_name):
        print('Removing bat file from Windows Startup folder')
        os.unlink(file_name)
