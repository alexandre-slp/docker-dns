import os
import time
import shutil
import json
import sys

import config
import dockerapi as docker
import util
import network

if util.on_macos:
    import OSes.macos as OS

elif util.on_wsl:
    import OSes.windows_wsl2 as OS

elif util.on_linux:
    if config.NAME == 'Ubuntu':
        import OSes.ubuntu as OS
    elif config.NAME.lower() == 'linux mint':
        import OSes.mint as OS

RESOLVCONF = '/etc/resolv.conf'
RESOLVCONF_HEAD = '/etc/resolvconf/resolv.conf.d/head'
RESOLVCONF_TAIL = '/etc/resolvconf/resolv.conf.d/tail'


def update_cache():
    util.write_cache('tld', config.TOP_LEVEL_DOMAIN)
    util.write_cache('tag', config.DOCKER_CONTAINER_TAG)
    util.write_cache('name', config.DOCKER_CONTAINER_NAME)


def update_resolvconf():
    if not hasattr(OS, 'DISABLE_MAIN_RESOLVCONF_ROUTINE'):
        if not os.path.exists(RESOLVCONF):
            content = '# Generated by docker-dns\n'
            open(RESOLVCONF, 'w').write(content)

        dns = docker.NETWORK_GATEWAY
        try:
            dns = OS.DNS
        except Exception:
            # no DNS
            pass

        name_servers = f'nameserver {dns} #@docker-dns\n' \
                       f'nameserver 1.1.1.1 #@docker-dns\n' \
                       f'nameserver 8.8.8.8 #@docker-dns\n'
        options = 'options timeout:1 #@docker-dns\n'
        if OS.FLAVOR == 'ubuntu' and config.OS_VERSION >= 18 * 1000:
            open(RESOLVCONF_HEAD, 'a').write(name_servers)
            open(RESOLVCONF_TAIL, 'a').write(options)

        open(RESOLVCONF, 'a').write(f'{name_servers}{options}')


def main(name=config.DOCKER_CONTAINER_NAME, tag=config.DOCKER_CONTAINER_TAG, tld=config.TOP_LEVEL_DOMAIN):
    if not util.is_os_supported(OS.FLAVOR):
        return 1

    if os.path.exists('.cache/INSTALLED'):
        os.unlink('.cache/INSTALLED')

    try:
        update_resolvconf()
    except FileNotFoundError:
        print('package "resolvconf" not installed, please install it with "sudo apt install resolvconf"')
        return 1

    # docker
    docker_conf_file = f"{OS.DOCKER_CONF_FOLDER}/daemon.json"
    if not os.path.exists(docker_conf_file) or os.stat(docker_conf_file).st_size == 0:
        if not os.path.isdir(OS.DOCKER_CONF_FOLDER):
            os.mkdir(OS.DOCKER_CONF_FOLDER)
        shutil.copy2('src/templates/daemon.json', docker_conf_file)

    docker_json = json.loads(open(docker_conf_file, 'r').read())
    docker_json['bip'] = docker.DAEMON_BIP
    docker_json['dns'] = list(
        set([docker.NETWORK_GATEWAY] + network.get_dns_servers()))
    with open(docker_conf_file, 'w') as daemon_file:
        daemon_file.write(json.dumps(docker_json, indent=4, sort_keys=True))

    if docker.check_exists(name):
        print("Stopping existing container...")
        docker.purge(name)
        time.sleep(2)

    print(
        f'Building and running container "{tag}:latest"... Please wait')
    docker.build_container(
        name, tag, tld, bind_port_ip=util.on_linux and not util.on_wsl, target=OS.DOCKER_BUILD_TARGET)
    update_cache()

    # TLD domain certificate
    cert_file = f'certs.d/tld/{tld}.cert'
    key_file = f'certs.d/tld/{tld}.key'
    util.generate_certificate(tld, cert_file=cert_file, key_file=key_file)
    shutil.copy2(cert_file, OS.DOCKER_CONF_FOLDER)
    shutil.copy2(key_file, OS.DOCKER_CONF_FOLDER)

    original_arg = sys.argv
    install_status = OS.install(tld)
    if install_status and util.is_tunnel_needed():
        original_arg[1] = 'tunnel'
        original_arg.append('&')
        os.system(' '.join(original_arg))

    open('.cache/INSTALLED', 'w').write('')
    return 0
