import json
import os.path
import subprocess
from flask import jsonify, request, url_for
from config import ANSIBLE_PROJECT_PATH

from wg_ha_backend import app
from wg_ha_backend.tasks import run_playbook
from wg_ha_backend.utils import generate_next_virtual_client_ips, generate_allowed_ips, render_ansible_config_template, check_public_key_exists
from wg_ha_backend.database import server_public_key, server_endpoint, clients


@app.route("/api/playbook", methods=["POST"])
def route_playbook():
    data = request.json
    playbook = data.get("playbook")
    extra_vars = data.get("extra_vars")
    task = run_playbook.delay(playbook=playbook, extra_vars=extra_vars)
    return jsonify({}), 202, {'Location': url_for('route_playbook_status', task_id=task.id)}


@app.route('/api/playbook/<task_id>')
def route_playbook_status(task_id):
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
def route_inventory():
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
    client_public_key = data.get("public_key")
    client_tags = data.get("tags")
    client_services = data.get("services")

    if check_public_key_exists(client_public_key):
        raise ValueError("another client with the same public key already exists")

    client_interface_ips = generate_next_virtual_client_ips()
    client_allowed_ips = generate_allowed_ips(client_interface_ips)

    clients.append({
        "public_key": client_public_key,
        "allowed_ips": client_allowed_ips,
        "tags": client_tags,
        "services": client_services
    })
    ansible_config = render_ansible_config_template()

    ansible_config_path = os.path.join(ANSIBLE_PROJECT_PATH, "group_vars", "all", "wireguard_peers")
    with open(ansible_config_path, "w") as f:
        f.write(ansible_config)

    # TODO: run ansible
    run_playbook.delay(playbook="test.yml")

    # TODO: display user the client config
    # [Interface]
    # Address = {", ".join(client_interface_ips)}
    # PrivateKey = {client_private_key}
    #
    # [Peer]
    # PublicKey = {server_public_key}
    # AllowedIPs = 10.0.0.0/16, fdc9:281f:04d7:9ee9::0:0/96
    # Endpoint = {server_endpoint}
    # PersistentKeepalive = 21

    return {}