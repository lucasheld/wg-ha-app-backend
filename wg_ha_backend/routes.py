import json
import os.path
import subprocess
from flask import jsonify, request, url_for
from config import ANSIBLE_PROJECT_PATH

from wg_ha_backend import app
from wg_ha_backend.tasks import run_playbook
from wg_ha_backend.utils import generate_next_virtual_client_ips, generate_allowed_ips, render_ansible_config_template, \
    check_private_key_exists, generate_wireguard_config, allowed_ips_to_interface_address, Wireguard
from wg_ha_backend.database import server_public_key, server_private_key, server_endpoint, clients, server_interface_ips


@app.route("/api/playbook", methods=["POST"])
def route_playbook_post():
    data = request.json
    playbook = data.get("playbook")
    extra_vars = data.get("extra_vars")
    task = run_playbook.delay(playbook=playbook, extra_vars=extra_vars)
    return jsonify({}), 202, {'Location': url_for('route_playbook_status', task_id=task.id)}


@app.route('/api/playbook/<task_id>')
def route_playbook_status_get(task_id):
    task = run_playbook.AsyncResult(task_id)
    if task.state == 'FAILURE':
        response = {
            'state': task.state,
            'output': str(task.info),  # exception message
        }
    else:
        output = ""
        if task.info:
            output = task.info.get('output', "")
        response = {
            'state': task.state,
            'output': output,
        }
    return jsonify(response)


@app.route("/api/inventory")
def route_inventory_get():
    command = [
        "ansible-inventory",
        "--list"
    ]
    inventory = request.args.get('inventory')
    if inventory:
        command.append("-i")
        command.append(inventory)
    process = subprocess.Popen(
        command,
        cwd=ANSIBLE_PROJECT_PATH,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    output, error = process.communicate()
    if error:
        return jsonify({"error": error.decode()}), 500

    output = output.decode()
    return json.loads(output)


@app.route("/api/client")
def route_client_get():
    return clients


@app.route("/api/client", methods=["POST"])
def route_client_post():
    data = request.json
    # client_public_key = data.get("public_key")
    title = data.get("title")
    client_private_key = data.get("private_key")
    client_tags = data.get("tags")
    client_services = data.get("services")

    if check_private_key_exists(client_private_key):
        raise ValueError("another client with the same public key already exists")

    client_interface_ips = generate_next_virtual_client_ips()
    client_allowed_ips = generate_allowed_ips(client_interface_ips)

    client_public_key = Wireguard.gen_public_key(client_private_key)

    clients.append({
        "title": title,
        "public_key": client_public_key,
        "private_key": client_private_key,
        "allowed_ips": client_allowed_ips,
        "tags": client_tags,
        "services": client_services
    })
    ansible_config = render_ansible_config_template()

    ansible_config_path = os.path.join(ANSIBLE_PROJECT_PATH, "group_vars", "all", "wireguard_peers")
    with open(ansible_config_path, "w") as f:
        f.write(ansible_config)

    run_playbook.delay(playbook="apply-config.yml")

    return {}


@app.route("/api/config/<path:public_key>")
def route_config_get(public_key):
    client = None
    for i in clients:
        if i["public_key"] == public_key:
            client = i

    # peer interface
    # client_private_key = "0000000000000000000000000000000000000000000="
    interface = {
        "address": allowed_ips_to_interface_address(client["allowed_ips"]),
        "private_key": client["private_key"],
    }
    peers = [{
        "public_key": server_public_key,
        "endpoint": server_endpoint,
    }]

    wireguard_config = generate_wireguard_config(interface=interface, peers=peers)
    return wireguard_config
