from celery import Celery
from flask import Flask
from flask_cors import CORS

from config import CELERY_BROKER_URL, CELERY_RESULT_BACKEND
from pymongo import MongoClient

app = Flask(__name__)

CORS(app)

app.config['CELERY_BROKER_URL'] = CELERY_BROKER_URL
app.config['result_backend'] = CELERY_RESULT_BACKEND
celery = Celery(app.name, broker=CELERY_BROKER_URL, backend=CELERY_RESULT_BACKEND)
celery.conf.update(app.config)

client = MongoClient('mongo', 27017)
db = client.flask_db
if not db.server.find_one({}):
    db.server.insert_one({
        "interface_ips": [
            "10.0.0.1/24",
            "fdc9:281f:04d7:9ee9::1/112"
        ],
        "private_key": "gG38NoQ9UEYzu5LAHzT3n9Kfk6VJz7iDcHEEuNovIHE=",
        "public_key": "SPlAIzq4bkT3IxpFDnxfxACIaLoYMsv/WjxHTr6ZDR8=",
        "endpoint": "116.202.189.178:51820"
    })
