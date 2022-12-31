from functools import wraps

from bson import ObjectId
from flask_socketio import join_room
from flask_jwt_extended import verify_jwt_in_request, get_jwt, jwt_required, get_jwt_identity
from flask_socketio import SocketIO

from .app import app, celery, bcrypt, db

# uses db
from wg_ha_backend.utils import dump

# uses celery
from . import tasks

socketio = SocketIO(app, cors_allowed_origins="*")

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


# namespaces are using socketio
from .apis import api
api.init_app(app)

# uses socketio and db
from .run_flask import create_app
