from celery import Celery
from flask import Flask
from flask_cors import CORS
from flask_socketio import SocketIO
from pymongo import MongoClient

from config import CELERY_BROKER_URL, CELERY_RESULT_BACKEND

app = Flask(__name__)

CORS(app)

app.config['CELERY_BROKER_URL'] = CELERY_BROKER_URL
app.config['result_backend'] = CELERY_RESULT_BACKEND
celery = Celery(app.name, broker=CELERY_BROKER_URL, backend=CELERY_RESULT_BACKEND)
celery.conf.update(app.config)

socketio = SocketIO(app, cors_allowed_origins="*")

client = MongoClient('mongo', 27017)
db = client.flask_db
