from bson import ObjectId
from flask import Response
from flask_restx import Resource, reqparse, Namespace

from wg_ha_backend import db, emit
from wg_ha_backend.keycloak import user_required, admin_required, get_keycloak_user_id, is_keycloak_admin
from wg_ha_backend.utils import generate_next_interface_address, generate_allowed_ips, \
    generate_wireguard_config, allowed_ips_to_interface_address, Wireguard, get_changed_keys, dump

api = Namespace('client', description='Endpoints to manage WireGuard clients')

client_parser = reqparse.RequestParser()
client_parser.add_argument('title', type=str, help='Title of the client', location='json')
client_parser.add_argument('public_key', type=str, help='Public key of the client', location='json')
client_parser.add_argument('tags', type=list, help='Tags of the client', location='json')
client_parser.add_argument('services', type=list, help='Services of the client', location='json')
client_parser.add_argument('subnet', type=str, help='Subnet of the client interface ip address', location='json')

client_review_parser = reqparse.RequestParser()
client_review_parser.add_argument('permitted', type=str, help='Indicates if the client is permitted and used when generating the WireGuard config. Allowed values: PENDING, ACCEPTED, DECLINED.', location='json')


def abort_if_public_key_exists(public_key):
    if public_key and db.clients.find_one({"public_key": public_key}):
        api.abort(400, "Another client with the same public key already exists.")


def get_default_permitted_value():
    settings = dump(db.settings.find_one({}))
    need_review = settings["review"] and not is_keycloak_admin()
    return "PENDING" if need_review else "ACCEPTED"


@api.route("")
class ClientList(Resource):
    @api.doc(security='token')
    @user_required()
    def get(self):
        user_id = get_keycloak_user_id()

        r = db.clients.find({"user_id": user_id})
        return dump(r)

    @api.doc(security='token', parser=client_parser)
    @user_required()
    def post(self):
        user_id = get_keycloak_user_id()

        args = client_parser.parse_args()

        subnet = args.get("subnet", 0)
        interface_address = generate_next_interface_address(subnet)
        allowed_ips = generate_allowed_ips(interface_address)

        abort_if_public_key_exists(args["public_key"])

        client = {
            "title": args["title"],
            "public_key": args["public_key"],
            "tags": args["tags"],
            "services": args["services"],
            "subnet": args["subnet"],
            "permitted": get_default_permitted_value(),
            "allowed_ips": allowed_ips,
            "user_id": user_id
        }
        db.clients.insert_one(client)

        emit("addClient", dump(client), to=user_id, admins=True)

        return {}


@api.route("/<id>")
@api.doc(params={
    'id': 'Id of the client'
})
class Client(Resource):
    @api.response(404, 'Not found')
    @api.doc(security='token', parser=client_parser)
    @user_required()
    def patch(self, id):
        user_id = get_keycloak_user_id()

        client = db.clients.find_one({"_id": ObjectId(id)})
        client = dump(client)

        if not client:
            api.abort(404)

        if client["user_id"] != user_id and not is_keycloak_admin():
            api.abort(401)

        args = client_parser.parse_args()

        public_key = args.get("public_key")

        if client["public_key"] != public_key:
            abort_if_public_key_exists(public_key)

        subnet = args.get("subnet", 0)
        allowed_ips = client["allowed_ips"]
        if client["subnet"] != subnet:
            interface_address = generate_next_interface_address(subnet)
            allowed_ips = generate_allowed_ips(interface_address)

        new_client_args = {
            "id": id,
            "title": args.get("title"),
            "public_key": public_key,
            "tags": args.get("tags"),
            "services": args.get("services"),
            "subnet": args.get("subnet"),
            "permitted": get_default_permitted_value(),
            "allowed_ips": allowed_ips
        }
        new_client_args = {k: v for k, v in new_client_args.items() if v is not None}

        new_client = {k: v for k, v in client.items()}
        new_client.update(new_client_args)

        new_client_without_id = {k: v for k, v in new_client.items() if k != "id"}

        changed_keys = get_changed_keys(client, new_client_without_id)
        if changed_keys:
            db.clients.update_one({"_id": ObjectId(id)}, {'$set': new_client_without_id})

            # send message to user who requested the edit, the client owner and all admins
            emit("editClient", new_client, to=[user_id, client["user_id"]], admins=True)
        return {}

    @api.response(404, 'Not found')
    @api.doc(security='token')
    @user_required()
    def delete(self, id):
        user_id = get_keycloak_user_id()

        client = db.clients.find_one({"_id": ObjectId(id)})
        if client["user_id"] != user_id and not is_keycloak_admin():
            api.abort(401)

        r = db.clients.delete_one({"_id": ObjectId(id)})

        # send message to user who requested the deletion, the client owner and all admins
        emit("deleteClient", id, to=[user_id, client["user_id"]], admins=True)

        if r.deleted_count:
            return {}
        api.abort(404)


@api.route("/<id>/review")
@api.doc(params={
    'id': 'Id of the client'
})
class Review(Resource):
    @api.response(404, 'Not found')
    @api.doc(security='token', parser=client_review_parser)
    @admin_required()
    def patch(self, id):
        client = db.clients.find_one({"_id": ObjectId(id)})
        client = dump(client)

        if not client:
            api.abort(404)

        args = client_review_parser.parse_args()

        client.update({
            "permitted": args["permitted"],
        })
        client_without_id = {k: v for k, v in client.items() if k != "id"}

        db.clients.update_one({"_id": ObjectId(id)}, {'$set': client_without_id})

        # notify client owner and admins, the current keycloak user is not necessarily the owner of the client
        user_id = client["user_id"]
        emit("editClient", client, to=user_id, admins=True)

        return {}


@api.route("/<id>/config")
@api.doc(params={
    'id': 'Id of the client'
})
class Config(Resource):
    @api.response(404, 'Not found')
    @api.doc(security='token')
    @user_required()
    def get(self, id):
        user_id = get_keycloak_user_id()

        client = db.clients.find_one({"_id": ObjectId(id)})
        if not client:
            api.abort(404)

        if client["user_id"] != user_id and not is_keycloak_admin():
            api.abort(401)

        server = dump(db.settings.find_one({}))["server"]

        # peer interface
        interface = {
            "address": allowed_ips_to_interface_address(client["allowed_ips"]),
            "private_key": "INSERT_PRIVATE_KEY",
        }
        peers = [{
            "public_key": Wireguard.gen_public_key(server["private_key"]),
            "endpoint": server["endpoint"],
        }]

        wireguard_config = generate_wireguard_config(interface=interface, peers=peers)
        return Response(wireguard_config)
