import datetime

from flask_bcrypt import check_password_hash
from flask_jwt_extended import create_access_token
from flask_restx import Resource, reqparse, Namespace

from wg_ha_backend import db
from wg_ha_backend.utils import dump

api = Namespace('session', description='Endpoint to login and receive a new JWT')

session_parser = reqparse.RequestParser()
session_parser.add_argument('username', type=str, help='Username of the user', location='json')
session_parser.add_argument('password', type=str, help='Password of the user', location='json')


@api.route("")
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
