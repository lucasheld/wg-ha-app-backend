import datetime
import json
import subprocess
from functools import wraps

from bson import ObjectId
from flask import jsonify, request, url_for
from flask_bcrypt import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, verify_jwt_in_request, get_jwt
from flask_restx import Resource, reqparse
from flask_socketio import join_room

from config import ANSIBLE_PROJECT_PATH
from wg_ha_backend import api, db, socketio
from wg_ha_backend.tasks import run_playbook
from wg_ha_backend.utils import generate_next_virtual_client_ips, generate_allowed_ips, \
    generate_wireguard_config, allowed_ips_to_interface_address, Wireguard, render_and_run_ansible, \
    get_changed_keys, dump, remove_keys


def admin_required():
    def wrapper(fn):
        @wraps(fn)
        def decorator(*args, **kwargs):
            verify_jwt_in_request()
            claims = get_jwt()
            if claims.get("is_administrator", False):
                return fn(*args, **kwargs)
            else:
                api.abort(403, "Admins only!")
        return decorator
    return wrapper


playbook_namespace = api.namespace('playbook', description='TODO operations')


playbook_parser = reqparse.RequestParser()
playbook_parser.add_argument('playbook', type=str, help='Filename of the playbook')
playbook_parser.add_argument('extra_vars', type=str, help='Variables that should be used to execute the playbook')


@playbook_namespace.route("")
class PlaybookList(Resource):
    @api.doc(security='token', parser=playbook_parser)
    @admin_required()
    def post(self):
        args = session_parser.parse_args()
        playbook = args["playbook"]
        extra_vars = args["extra_vars"]
        task = run_playbook.delay(playbook=playbook, extra_vars=extra_vars)
        return jsonify({}), 202, {'Location': url_for('route_playbook_status', task_id=task.id)}


@playbook_namespace.route("/<int:id>")
@api.doc(params={
    'id': 'Id of the celery task that executes the ansible playbook'
})
class Playbook(Resource):
    @api.doc(security='token')
    @admin_required()
    def get(self, id):
        task = run_playbook.AsyncResult(id)
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


inventory_namespace = api.namespace('inventory', description='TODO operations')


@inventory_namespace.route("")
class InventoryList(Resource):
    @api.doc(security='token')
    @admin_required()
    def get(self):
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
            api.abort(500, error.decode())

        output = output.decode()
        return json.loads(output)


client_namespace = api.namespace('client', description='TODO operations')

client_parser = reqparse.RequestParser()
client_parser.add_argument('title', type=str, help='Title of the client')
client_parser.add_argument('private_key', type=str, help='Private key of the client')
client_parser.add_argument('tags', type=list, help='Tags of the client')
client_parser.add_argument('services', type=list, help='Services of the client')


@client_namespace.route("")
class ClientList(Resource):
    @api.doc(security='token')
    @jwt_required()
    def get(self):
        r = db.clients.find()
        return dump(r)

    @api.doc(security='token', parser=client_parser)
    @jwt_required()
    def post(self):
        args = client_parser.parse_args()

        interface_ips = generate_next_virtual_client_ips()
        allowed_ips = generate_allowed_ips(interface_ips)

        private_key = args["private_key"]
        public_key = Wireguard.gen_public_key(private_key)

        client = args
        client.update({
            "public_key": public_key,
            "allowed_ips": allowed_ips
        })
        db.clients.insert_one(client)

        socketio.emit("addClient", dump(client))

        render_and_run_ansible()
        return {}


@client_namespace.route("/<id>")
@api.doc(params={
    'id': 'Id of the client'
})
class Client(Resource):
    @api.response(404, 'Not found')
    @api.doc(security='token', parser=client_parser)
    @jwt_required()
    def patch(self, id):
        client = db.clients.find_one({"_id": ObjectId(id)})
        if not client:
            api.abort(404)

        new_client = client_parser.parse_args()
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

    @api.response(404, 'Not found')
    @api.doc(security='token')
    @jwt_required()
    def delete(self, id):
        r = db.clients.delete_one({"_id": ObjectId(id)})

        socketio.emit("deleteClient", id)

        if r.deleted_count:
            render_and_run_ansible()
            return {}
        api.abort(404)


@client_namespace.route("/<id>/config")
@api.doc(params={
    'id': 'Id of the client'
})
class Config(Resource):
    @api.response(404, 'Not found')
    @api.doc(security='token')
    @jwt_required()
    def get(self, id):
        client = db.clients.find_one({"_id": ObjectId(id)})
        if not client:
            api.abort(404)

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
    try:
        user_role = user["roles"][0]
    except IndexError:
        user_role = "user"
    join_room(user_role)

    # messages to all
    socketio.emit("setClients", dump(db.clients.find()))
    socketio.emit("setClientsApplied", dump(db.clients_applied.find()))

    # messages to admins
    users = dump(db.users.find())
    users_without_password = [{k: v for k, v in user.items() if k != "password"} for user in users]
    socketio.emit("setUsers", users_without_password, to="admin")


session_namespace = api.namespace('session', description='TODO operations')

session_parser = reqparse.RequestParser()
session_parser.add_argument('username', type=str, help='Username of the user')
session_parser.add_argument('password', type=str, help='Password of the user')


@session_namespace.route("")
class Session(Resource):
    @api.response(401, 'Username or password invalid')
    @api.doc(security='token', parser=session_parser)
    def post(self):
        args = session_parser.parse_args()
        username = args["username"]
        password = args["password"]

        user = dump(db.users.find_one({"username": username}))
        authorized = False
        if user:
            pw_hash = user["password"]
            authorized = check_password_hash(pw_hash, password)
        if not authorized:
            api.abort(401)

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
        }


user_namespace = api.namespace('user', description='TODO operations')

user_parser = reqparse.RequestParser()
user_parser.add_argument('username', type=str, help='Username of the user')
user_parser.add_argument('password', type=str, help='Password of the user')
user_parser.add_argument('roles', type=str, help='Roles of the user')


@user_namespace.route("")
class UserList(Resource):
    @api.doc(security='token')
    @admin_required()
    def get(self):
        users = dump(db.users.find())
        return remove_keys(users, ["password"])

    @api.doc(parser=user_parser)
    @admin_required()
    def post(self):
        args = user_parser.parse_args()
        username = args["username"]
        password = args["password"]
        roles = args["roles"]

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


@user_namespace.route("/<id>")
@api.doc(params={
    'id': 'Id of the user'
})
class User(Resource):
    @api.response(404, 'Not found')
    @api.doc(security='token', parser=user_parser)
    @jwt_required()
    def patch(self, id):
        args = user_parser.parse_args()

        user = db.users.find_one({"_id": ObjectId(id)})
        if not user:
            api.abort(404)

        new_user = {
            "id": id
        }
        if get_jwt().get("is_administrator", False):
            username = args["username"]
            roles = args["roles"]
            new_user.update({
                "username": username,
                "roles": roles
            })

        password = args["password"]
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

    @api.response(404, 'Not found')
    @api.doc(security='token')
    @admin_required()
    def delete(self, id):
        r = db.users.delete_one({"_id": ObjectId(id)})
        socketio.emit("deleteUser", id)

        if r.deleted_count:
            return {}
        api.abort(404)
