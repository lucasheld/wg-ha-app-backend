from bson import ObjectId
from flask_restx import Resource, reqparse, Namespace

from wg_ha_backend import db, socketio
from wg_ha_backend.keycloak import admin_required
from wg_ha_backend.utils import dump

api = Namespace('settings', description='Endpoint to manage settings')

settings_parser = reqparse.RequestParser()
settings_parser.add_argument('review', type=bool, help='Enable client review', location='json')


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

        new_settings = {
            "review": args["review"]
        }
        db.settings.update_one({"_id": ObjectId(id)}, {'$set': new_settings})

        socketio.emit("setSettings", new_settings)

        return {}
