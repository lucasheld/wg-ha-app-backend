from flask_socketio import SocketIO, join_room

from .app import app, celery, db

# uses db
from wg_ha_backend.utils import dump

# uses celery
from . import tasks
from .keycloak import user_required, get_keycloak_user_id, is_keycloak_admin

socketio = SocketIO(app, cors_allowed_origins="*")

socketio_admins = []

def emit(event, message, to=None, admins=False):
    destinations = []
    if admins:
        destinations.extend(socketio_admins)
    if to and to not in destinations:
        destinations.append(to)
    for destination in destinations:
        socketio.emit(event, message, to=destination)


@socketio.on("connect")
@user_required()
def event_connect():
    user_id = get_keycloak_user_id()
    join_room(user_id)
    if is_keycloak_admin():
        socketio_admins.append(user_id)

        emit("setClients", dump(db.clients.find()), to=user_id)
        emit("setClientsApplied", dump(db.clients_applied.find()), to=user_id)

        settings = dump(db.settings.find_one({}))
        settings.pop("id")
        emit("setSettings", settings, to=user_id)
    else:
        emit("setClients", dump(db.clients.find({"user_id": user_id})), to=user_id)
        emit("setClientsApplied", dump(db.clients_applied.find({"user_id": user_id})), to=user_id)


# namespaces are using socketio
from .apis import api
api.init_app(app)

# uses socketio and db
from .run_flask import create_app
