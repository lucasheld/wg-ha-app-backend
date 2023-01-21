from flask_socketio import SocketIO, join_room

from .app import app, celery, db

# uses db
from wg_ha_backend.utils import dump

# uses celery
from . import tasks
from .keycloak import user_required, get_keycloak_user_id, is_keycloak_admin

socketio = SocketIO(app, cors_allowed_origins="*")


def emit(event, message, to=None):
    if type(to) != list:
        to = [to]
    for t in to:
        socketio.emit(event, message, to=t)


@socketio.on("connect")
@user_required()
def event_connect():
    user_id = get_keycloak_user_id()
    join_room(user_id)
    if is_keycloak_admin():
        join_room("admin")

    emit("setClients", dump(db.clients.find({"user_id": user_id})), to=user_id)
    emit("setClientsApplied", dump(db.clients_applied.find({"user_id": user_id})), to=user_id)

    settings = dump(db.settings.find_one({}))
    settings.pop("id")
    emit("setSettings", settings, to=user_id)


# namespaces are using socketio
from .apis import api
api.init_app(app)

# uses socketio and db
from .run_flask import create_app
