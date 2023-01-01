from bson import ObjectId
from flask_jwt_extended import jwt_required
from flask_restx import Resource, reqparse, Namespace

from wg_ha_backend import db, socketio
from wg_ha_backend.utils import generate_next_virtual_client_ips, generate_allowed_ips, \
    generate_wireguard_config, allowed_ips_to_interface_address, Wireguard, render_and_run_ansible, \
    get_changed_keys, dump

api = Namespace('client', description='Endpoints to manage WireGuard clients')

client_parser = reqparse.RequestParser()
client_parser.add_argument('title', type=str, help='Title of the client')
client_parser.add_argument('private_key', type=str, help='Private key of the client')
client_parser.add_argument('tags', type=list, help='Tags of the client')
client_parser.add_argument('services', type=list, help='Services of the client')


@api.route("")
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


@api.route("/<id>")
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


@api.route("/<id>/config")
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
