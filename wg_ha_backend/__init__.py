from flask_socketio import SocketIO

from .app import app, celery, db

# uses db
from wg_ha_backend.utils import dump

# uses celery
from . import tasks
from .keycloak import user_required

socketio = SocketIO(app, cors_allowed_origins="*")

@socketio.on("connect")
@user_required()
def event_connect():
    socketio.emit("setClients", dump(db.clients.find()))
    socketio.emit("setClientsApplied", dump(db.clients_applied.find()))


# namespaces are using socketio
from .apis import api
api.init_app(app)

# uses socketio and db
from .run_flask import create_app
