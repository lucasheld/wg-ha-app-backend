import datetime
import json
import subprocess
from functools import wraps

from bson import ObjectId
from flask import jsonify, request, url_for, Response
from flask_bcrypt import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, verify_jwt_in_request, get_jwt
from flask_jwt_extended.exceptions import NoAuthorizationError
from flask_socketio import ConnectionRefusedError
from flask_socketio import join_room

from config import ANSIBLE_PROJECT_PATH
from wg_ha_backend import app, db, socketio
from wg_ha_backend.tasks import run_playbook
from wg_ha_backend.utils import generate_next_virtual_client_ips, generate_allowed_ips, \
    generate_wireguard_config, allowed_ips_to_interface_address, Wireguard, render_and_run_ansible, \
    get_changed_keys, dump, dumps, remove_keys


def admin_required():
    def wrapper(fn):
        @wraps(fn)
        def decorator(*args, **kwargs):
            verify_jwt_in_request()
            claims = get_jwt()
            if claims.get("is_administrator", False):
                return fn(*args, **kwargs)
            else:
                return jsonify(msg="Admins only!"), 403
        return decorator
    return wrapper



@app.route("/api/playbook", methods=["POST"])
@admin_required()
def route_playbook_post():
    data = request.json
    playbook = data.get("playbook")
    extra_vars = data.get("extra_vars")
    task = run_playbook.delay(playbook=playbook, extra_vars=extra_vars)
    return jsonify({}), 202, {'Location': url_for('route_playbook_status', task_id=task.id)}


@app.route('/api/playbook/<task_id>')
@admin_required()
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
@admin_required()
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
@jwt_required()
def route_client_get():
    r = db.clients.find()
    return Response(dumps(r), status=200, mimetype='application/json')


@app.route("/api/client", methods=["POST"])
@jwt_required()
def route_client_post():
    data = request.json

    interface_ips = generate_next_virtual_client_ips()
    allowed_ips = generate_allowed_ips(interface_ips)

    private_key = data.get("private_key")
    public_key = Wireguard.gen_public_key(private_key)

    client = data
    client.update({
        "public_key": public_key,
        "allowed_ips": allowed_ips
    })
    db.clients.insert_one(client)

    socketio.emit("addClient", dump(client))

    render_and_run_ansible()
    return {}


@app.route("/api/client/<id>", methods=["PATCH"])
@jwt_required()
def route_client_patch(id):
    client = db.clients.find_one({"_id": ObjectId(id)})
    if not client:
        return Response({}, status=404, mimetype='application/json')

    new_client = request.json
    new_client = {k: v for k, v in new_client.items() if v is not None}
    new_client_without_id = {k: v for k, v in new_client.items() if k != "id"}

    changed_keys = get_changed_keys(client, new_client_without_id)
    if changed_keys:
        db.clients.update_one({"_id": ObjectId(id)}, {'$set': new_client_without_id})

        socketio.emit("editClient", new_client)

        # do not run the ansible playbook if only the title has changed
        if changed_keys != ["title"]:
            render_and_run_ansible()
    return {}


@app.route("/api/client/<id>", methods=["DELETE"])
@jwt_required()
def route_client_delete(id):
    r = db.clients.delete_one({"_id": ObjectId(id)})

    socketio.emit("deleteClient", id)

    if r.deleted_count:
        render_and_run_ansible()
        return Response({}, status=200, mimetype='application/json')
    return Response({}, status=404, mimetype='application/json')


@app.route("/api/config/<id>")
@jwt_required()
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


@socketio.on("connect")
@jwt_required()
def event_connect():
    # add user to role room
    user_id = get_jwt_identity()
    user = db.users.find_one({"_id": ObjectId(user_id)})
    user_role = user["roles"][0]
    join_room(user_role)

    # messages to all
    socketio.emit("setClients", dump(db.clients.find()))
    socketio.emit("setClientsApplied", dump(db.clients_applied.find()))

    # messages to admins
    users = dump(db.users.find())
    users_without_password = [{k: v for k, v in user.items() if k != "password"} for user in users]
    socketio.emit("setUsers", users_without_password, to="admin")


@app.route("/api/session", methods=["POST"])
def route_login_post():
    username = request.json.get("username")
    password = request.json.get("password")

    user = dump(db.users.find_one({"username": username}))
    authorized = False
    if user:
        pw_hash = user["password"]
        authorized = check_password_hash(pw_hash, password)
    if not authorized:
        return {'error': 'Username or password invalid'}, 401

    user_id = str(user["id"])
    expires = datetime.timedelta(days=7)
    access_token = create_access_token(
        identity=user_id,
        expires_delta=expires,
        additional_claims={"is_administrator": True}
    )
    return {
        "token": access_token,
        "roles": user["roles"],
        "user_id": user_id
    }, 200


@app.errorhandler(NoAuthorizationError)
def internal_error(error):
    raise ConnectionRefusedError('unauthorized')


@app.route("/api/user")
@admin_required()
def route_user_get():
    users = dumps(db.users.find())
    return Response(remove_keys(users, ["password"]), status=200, mimetype='application/json')


@app.route("/api/user", methods=["POST"])
@admin_required()
def route_user_post():
    username = request.json.get("username")
    password = request.json.get("password")
    roles = request.json.get("roles")

    pw_hash = generate_password_hash(password).decode('utf8')
    r = db.users.insert_one({
        "username": username,
        "password": pw_hash,
        "roles": roles
    })
    user_id = r.inserted_id

    user = dump(db.users.find_one({"_id": ObjectId(user_id)}))
    socketio.emit("addUser", remove_keys(user, ["password"]))
    return {}


@app.route("/api/user/<id>", methods=["PATCH"])
@jwt_required()
def route_user_patch(id):
    user = db.users.find_one({"_id": ObjectId(id)})
    if not user:
        return Response({}, status=404, mimetype='application/json')

    new_user = {}
    if get_jwt().get("is_administrator", False):
        username = request.json.get("username")
        roles = request.json.get("roles")
        new_user = {
            "username": username,
            "roles": roles
        }

    password = request.json.get("password")
    pw_hash = generate_password_hash(password).decode('utf8')
    new_user.update({
        "password": pw_hash,
    })
    new_user = {k: v for k, v in new_user.items() if v is not None}

    new_user_without_id = remove_keys(new_user, ["id"])
    changed_keys = get_changed_keys(user, new_user_without_id)
    if changed_keys:
        db.users.update_one({"_id": ObjectId(id)}, {'$set': new_user_without_id})
        socketio.emit("editUser", remove_keys(new_user, ["password"]))
    return {}


@app.route("/api/user/<id>", methods=["DELETE"])
@admin_required()
def route_user_delete(id):
    r = db.users.delete_one({"_id": ObjectId(id)})
    socketio.emit("deleteUser", id)

    if r.deleted_count:
        return Response({}, status=200, mimetype='application/json')
    return Response({}, status=404, mimetype='application/json')
