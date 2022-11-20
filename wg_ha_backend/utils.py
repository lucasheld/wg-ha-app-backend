import re
import json
import jinja2
import ipaddress
import subprocess

from wg_ha_backend.database import clients, server_interface_ips


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


def generate_next_virtual_client_ips():
    ips = []

    for cidr in server_interface_ips:
        ip = cidr.split("/")[0]
        ips.append(ip)

    for client in clients:
        for cidr in client["allowed_ips"]:
            ip = cidr.split("/")[0]
            ips.append(ip)

    host_nums = []
    for ip in ips:
        if get_ip_version(ip) == 4:
            match = re.search(r'\d+\.\d+\.\d+\.(\d+)$', ip)
            host_id = int(match.group(1))
            host_nums.append(host_id)

    new_host_num = next_num(host_nums)

    # TODO: add support for more clients by using another subnet

    return [
        CIDR(f"10.0.0.{new_host_num}/32"),
        CIDR(f"fdc9:281f:4d7:9ee9::{new_host_num}/128")
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


def render_ansible_config_template():
    env = jinja2.Environment(loader=jinja2.FileSystemLoader("./wg_ha_backend/"))
    template = env.get_template("wireguard_peers.j2")
    rendered = template.render(clients=clients)
    return rendered


def check_public_key_exists(public_key):
    for client in clients:
        if client["public_key"] == public_key:
            return True
    return False
