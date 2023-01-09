from flask_socketio import SocketIO

from .app import app, celery, db

# uses db
from wg_ha_backend.utils import dump

# uses celery
from . import tasks
from .keycloak import user_required, get_keycloak_user_id

socketio = SocketIO(app, cors_allowed_origins="*")

@socketio.on("connect")
@user_required()
def event_connect():
    user_id = get_keycloak_user_id()

    socketio.emit("setClients", dump(db.clients.find({"user_id": user_id})))
    socketio.emit("setClientsApplied", dump(db.clients_applied.find({"user_id": user_id})))


# namespaces are using socketio
from .apis import api
api.init_app(app)

# uses socketio and db
from .run_flask import create_app
