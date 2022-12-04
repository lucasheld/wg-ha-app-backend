import json
import subprocess

from bson import ObjectId
from flask import jsonify, request, url_for, Response

from config import ANSIBLE_PROJECT_PATH
from wg_ha_backend import app, db
from wg_ha_backend.tasks import run_playbook
from wg_ha_backend.utils import generate_next_virtual_client_ips, generate_allowed_ips, \
    generate_wireguard_config, allowed_ips_to_interface_address, Wireguard, render_and_run_ansible, \
    get_changed_client_keys, dump, dumps


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
    r = db.clients.find()
    return Response(dumps(r), status=200, mimetype='application/json')


@app.route("/api/client", methods=["POST"])
def route_client_post():
    data = request.json

    interface_ips = generate_next_virtual_client_ips()
    allowed_ips = generate_allowed_ips(interface_ips)

    private_key = data.get("private_key")
    public_key = Wireguard.gen_public_key(private_key)

    client = data
    client.update({
        "public_key": public_key,
        "allowed_ips": allowed_ips,
    })
    db.clients.insert_one(client)

    render_and_run_ansible()
    return {}


@app.route("/api/client/<id>", methods=["PATCH"])
def route_client_patch(id):
    client = db.clients.find_one({"_id": ObjectId(id)})
    if not client:
        return Response({}, status=404, mimetype='application/json')

    data = request.json
    data.pop("id")

    changed_keys = get_changed_client_keys(client, data)
    if changed_keys:
        db.clients.update_one({"_id": ObjectId(id)}, {'$set': data})

        # do not run the ansible playbook if only the title has changed
        if changed_keys != ["title"]:
            render_and_run_ansible()
    return {}


@app.route("/api/client/<id>", methods=["DELETE"])
def route_client_delete(id):
    r = db.clients.delete_one({"_id": ObjectId(id)})
    if r.deleted_count:
        render_and_run_ansible()
        return Response({}, status=200, mimetype='application/json')
    return Response({}, status=404, mimetype='application/json')


@app.route("/api/config/<id>")
def route_config_get(id):
    client = db.clients.find_one({"_id": ObjectId(id)})
    if not client:
        return Response({}, status=404, mimetype='application/json')

    server = db.server.find_one({})
    server = dump(server)

    # peer interface
    interface = {
        "address": allowed_ips_to_interface_address(client["allowed_ips"]),
        "private_key": client["private_key"],
    }
    peers = [{
        "public_key": server["public_key"],
        "endpoint": server["endpoint"],
    }]

    wireguard_config = generate_wireguard_config(interface=interface, peers=peers)
    return wireguard_config
