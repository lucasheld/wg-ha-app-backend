import json
import subprocess

from flask import jsonify, request, url_for

from config import ANSIBLE_PROJECT_PATH
from wg_ha_backend import app
from wg_ha_backend.database import server_public_key, server_endpoint, clients
from wg_ha_backend.tasks import run_playbook
from wg_ha_backend.utils import generate_next_virtual_client_ips, generate_allowed_ips, check_private_key_exists, \
    generate_wireguard_config, allowed_ips_to_interface_address, Wireguard, get_client, \
    render_and_run_ansible, get_changed_client_keys


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

    private_key = data.get("private_key")
    if check_private_key_exists(private_key):
        raise ValueError("another client with the same public key already exists")

    interface_ips = generate_next_virtual_client_ips()
    allowed_ips = generate_allowed_ips(interface_ips)
    public_key = Wireguard.gen_public_key(private_key)

    client = data
    client.update({
        "public_key": public_key,
        "allowed_ips": allowed_ips,
    })
    clients.append(client)

    render_and_run_ansible()
    return {}


@app.route("/api/client", methods=["PATCH"])
def route_client_patch():
    data = request.json

    private_key = data.get("private_key")
    public_key = Wireguard.gen_public_key(private_key)
    client = get_client(public_key)

    changed_keys = get_changed_client_keys(client, data)
    if client and changed_keys:
        # update the client in the database
        for i in data:
            client[i] = data[i]

        # do not run the ansible playbook if only the title has changed
        if changed_keys != ["title"]:
            render_and_run_ansible()
    return {}


@app.route("/api/client/<path:public_key>", methods=["DELETE"])
def route_client_delete(public_key):
    client = get_client(public_key)
    if client:
        clients.remove(client)
        render_and_run_ansible()
    return {}


@app.route("/api/config/<path:public_key>")
def route_config_get(public_key):
    client = get_client(public_key)

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
