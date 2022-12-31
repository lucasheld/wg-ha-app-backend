from bson import ObjectId
from flask_bcrypt import generate_password_hash
from flask_jwt_extended import jwt_required, get_jwt
from flask_restx import Resource, reqparse, Namespace

from wg_ha_backend import admin_required, db, socketio
from wg_ha_backend.utils import get_changed_keys, dump, remove_keys

api = Namespace('user', description='TODO operations')

user_parser = reqparse.RequestParser()
user_parser.add_argument('username', type=str, help='Username of the user')
user_parser.add_argument('password', type=str, help='Password of the user')
user_parser.add_argument('roles', type=str, help='Roles of the user')


@api.route("")
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


@api.route("/<id>")
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
