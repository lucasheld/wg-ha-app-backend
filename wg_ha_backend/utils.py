import ipaddress
import json
import os
import re
import subprocess

import jinja2

from config import ANSIBLE_PROJECT_PATH
from wg_ha_backend import db
from wg_ha_backend.tasks import run_playbook


def get_ip_version(ip_address):
    try:
        return 4 if type(ipaddress.ip_address(ip_address)) is ipaddress.IPv4Address else 6
    except ValueError:
        return


class CIDR(object):
    def __init__(self, cidr):
        ip, prefix = cidr.split("/")
        self.ip = ip
        self.prefix = prefix
        self.version = get_ip_version(ip)

    def __str__(self):
        # return f"{self.ip}/{self.prefix}"
        return json.dumps(self.__dict__)

    def __repr__(self):
        return self.__str__()


def next_num(nums, start=1):
    num = start
    while num in nums:
        num += 1
    return num


def generate_next_interface_address(subnet=0):
    ips = []

    server = dump(db.settings.find_one({}))["server"]
    clients = dump(db.clients.find())

    for cidr in server["address"]:
        ip = cidr.split("/")[0]
        ips.append(ip)

    for client in clients:
        for cidr in client["allowed_ips"]:
            ip = cidr.split("/")[0]
            ips.append(ip)

    host_nums = []
    for ip in ips:
        if get_ip_version(ip) == 4:
            match = re.search(r'\d+\.\d+\.(\d+)\.(\d+)$', ip)
            subnet_id = int(match.group(1))
            host_id = int(match.group(2))
            if subnet_id == int(subnet):
                host_nums.append(host_id)

    new_host_num = next_num(host_nums)

    return [
        CIDR(f"10.0.{subnet}.{new_host_num}/32"),
        CIDR(f"fdc9:281f:4d7:9ee9::{subnet}:{new_host_num}/128")
    ]


class Wireguard(object):
    @staticmethod
    def gen_private_key():
        return subprocess.check_output("wg genkey", shell=True).decode("utf-8").strip()

    @staticmethod
    def gen_public_key(private_key: str):
        return subprocess.check_output(f"echo '{private_key}' | wg pubkey", shell=True).decode("utf-8").strip()

    @staticmethod
    def gen_preshared_key():
        return subprocess.check_output("wg genpsk", shell=True).decode("utf-8").strip()


def generate_allowed_ips(virtual_client_ips):
    allowed_ips = []
    for cidr in virtual_client_ips:
        allowed_ip = f"{cidr.ip}/{32 if cidr.version == 4 else 128}"
        allowed_ips.append(allowed_ip)
    return allowed_ips


def generate_wireguard_config(interface, peers):
    env = jinja2.Environment(loader=jinja2.FileSystemLoader("./wg_ha_backend/"))
    template = env.get_template("wireguard_config.j2")
    rendered = template.render(
        interface=interface,
        peers=peers
    )
    return rendered


def allowed_ips_to_interface_address(allowed_ips):
    addresses = [i.replace("/32", "/24").replace("/128", "/112") for i in allowed_ips]
    return ", ".join(addresses)


def check_apply_config_necessary():
    clients = dump(db.clients.find({"permitted": "ACCEPTED"}))
    clients_applied = dump(db.clients_applied.find())
    ignores_keys = ["id", "title"]
    return remove_keys(clients, ignores_keys) != remove_keys(clients_applied, ignores_keys)


def render_write_ansible_config(template_name, config_name, **kwargs):
    env = jinja2.Environment(loader=jinja2.FileSystemLoader("./wg_ha_backend/"))
    template = env.get_template(template_name)
    ansible_config = template.render(**kwargs)

    ansible_config_path = os.path.join(ANSIBLE_PROJECT_PATH, "group_vars", "all", config_name)
    with open(ansible_config_path, "w") as f:
        f.write(ansible_config)


def render_and_run_ansible():
    clients = dump(db.clients.find({"permitted": "ACCEPTED"}))

    render_write_ansible_config("wireguard_peers.j2", "wireguard_peers", clients=clients)

    return run_playbook.delay(playbook="apply-config.yml", clients=clients)


def get_changed_keys(client_old, client_new):
    changed = []
    for i in client_new:
        if client_new[i] != client_old.get(i):
            changed.append(i)
    return changed


def dump(r):
    if r is None:
        return
    if type(r) == dict:
        data = r
    else:
        data = list(r)
    # dump mongo response as string
    string = json.dumps(data, default=lambda o: str(o))
    # load json from string
    data = json.loads(string)
    # replace key "_id" with "id"
    if type(r) == dict:
        data = {"id" if k == "_id" else k: v for k, v in data.items()}
    else:
        data = [{"id" if k == "_id" else k: v for k, v in i.items()} for i in data]
    return data


def remove_keys(data, keys):
    if type(data) == list:
        return [{k: v for k, v in i.items() if k not in keys} for i in data]
    else:
        return {k: v for k, v in data.items() if k not in keys}
