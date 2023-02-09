from bson import ObjectId
from flask_restx import Resource, reqparse, Namespace

from wg_ha_backend import db, emit
from wg_ha_backend.keycloak import admin_required
from wg_ha_backend.utils import Wireguard, dump

api = Namespace('settings', description='Endpoint to manage settings')

settings_parser = reqparse.RequestParser()
settings_parser.add_argument('review', type=bool, help='Enable client review', location='json')
settings_parser.add_argument('server', type=dict, help='WireGuard server config', location='json')


@api.route("")
class Settings(Resource):
    @api.doc(security='token')
    @admin_required()
    def get(self):
        r = db.settings.find()
        return dump(r)

    @api.doc(security='token', parser=settings_parser)
    @admin_required()
    def patch(self):
        args = settings_parser.parse_args()

        settings = dump(db.settings.find_one({}))
        id = settings["id"]

        server = args["server"]
        server["public_key"] = Wireguard.gen_public_key(server["private_key"])

        new_settings = {
            "review": args["review"],
            "server": server
        }
        db.settings.update_one({"_id": ObjectId(id)}, {'$set': new_settings})

        emit("setSettings", new_settings, admins=True)

        return {}
