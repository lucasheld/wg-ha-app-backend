from bson import ObjectId
from flask_restx import Resource, reqparse, Namespace

from wg_ha_backend import db, emit
from wg_ha_backend.keycloak import admin_required
from wg_ha_backend.utils import get_changed_keys, dump, render_write_ansible_config

api = Namespace('custom-rule', description='Endpoints to manage custom rules')

custom_rule_parser = reqparse.RequestParser()
custom_rule_parser.add_argument('title', type=str, help='Title of the custom rule', location='json')
custom_rule_parser.add_argument('type', type=str, help='IP address type of the custom rule', location='json')
custom_rule_parser.add_argument('src', type=str, help='Source of the custom rule', location='json')
custom_rule_parser.add_argument('dst', type=str, help='Destination of the custom rule', location='json')
custom_rule_parser.add_argument('protocol', type=str, help='Protocol of the custom rule', location='json')
custom_rule_parser.add_argument('port', type=str, help='Port of the custom rule', location='json')


def render_custom_rules():
    render_write_ansible_config("wireguard_custom_rules.j2", "wireguard_custom_rules", custom_rules=dump(db.custom_rules.find()))


@api.route("")
class CustomRuleList(Resource):
    @api.doc(security='token')
    @admin_required()
    def get(self):
        return dump(db.custom_rules.find())

    @api.doc(security='token', parser=custom_rule_parser)
    @admin_required()
    def post(self):
        args = custom_rule_parser.parse_args()

        custom_rule = {
            "title": args["title"],
            "type": args["type"],
            "src": args["src"],
            "dst": args["dst"],
            "protocol": args["protocol"],
            "port": args["port"]
        }
        db.custom_rules.insert_one(custom_rule)

        render_custom_rules()

        emit("addCustomRule", dump(custom_rule), admins=True)

        return {}


@api.route("/<id>")
@api.doc(params={
    'id': 'Id of the custom_rule'
})
class CustomRule(Resource):
    @api.response(404, 'Not found')
    @api.doc(security='token', parser=custom_rule_parser)
    @admin_required()
    def patch(self, id):
        custom_rule = db.custom_rules.find_one({"_id": ObjectId(id)})
        custom_rule = dump(custom_rule)

        if not custom_rule:
            api.abort(404)

        args = custom_rule_parser.parse_args()

        new_custom_rule_args = {
            "id": id,
            "title": args.get("title"),
            "type": args.get("type"),
            "src": args.get("src"),
            "dst": args.get("dst"),
            "protocol": args.get("protocol"),
            "port": args.get("port")
        }
        new_custom_rule_args = {k: v for k, v in new_custom_rule_args.items() if v is not None}

        new_custom_rule = {k: v for k, v in custom_rule.items()}
        new_custom_rule.update(new_custom_rule_args)

        new_custom_rule_without_id = {k: v for k, v in new_custom_rule.items() if k != "id"}

        changed_keys = get_changed_keys(custom_rule, new_custom_rule_without_id)
        if changed_keys:
            db.custom_rules.update_one({"_id": ObjectId(id)}, {'$set': new_custom_rule_without_id})

            render_custom_rules()

            emit("editCustomRule", new_custom_rule, admins=True)
        return {}

    @api.response(404, 'Not found')
    @api.doc(security='token')
    @admin_required()
    def delete(self, id):
        custom_rule = db.custom_rules.find_one({"_id": ObjectId(id)})

        if not custom_rule:
            api.abort(404)

        r = db.custom_rules.delete_one({"_id": ObjectId(id)})

        render_custom_rules()

        emit("deleteCustomRule", id, admins=True)

        if r.deleted_count:
            return {}
        api.abort(404)
