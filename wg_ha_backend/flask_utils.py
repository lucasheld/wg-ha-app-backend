from bson import ObjectId
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask_socketio import join_room

from wg_ha_backend import socketio, db
from wg_ha_backend.utils import dump


