from threading import Thread

from flask_bcrypt import generate_password_hash

from wg_ha_backend import app, celery, db, socketio
from wg_ha_backend.utils import dump


def celery_monitor():
    state = celery.events.State()

    celery_events_to_state = {
        "task-sent": "PENDING",
        "task-received": "PENDING",
        "task-started": "STARTED",
        "task-succeeded": "SUCCESS",
        "task-failed": "FAILURE",
        "task-rejected": "FAILURE",
        "task-revoked": "REVOKED",
        "task-retried": "RETRY",
    }

    def announce_tasks(event):
        state.event(event)

        if 'uuid' in event:
            event_type = event['type']
            task = state.tasks.get(event['uuid'])
            if event_type in celery_events_to_state:
                task_state = celery_events_to_state[event_type]

                socketio.emit(event_type, {
                    "uuid": task.uuid,
                    "name": task.name,
                    "received": task.received,
                    "state": task_state,
                    **task.info()
                })
            elif event_type == "task-progress":
                socketio.emit(event_type, {
                    "uuid": task.uuid,
                    "output": event["output"]
                })
            elif event_type == "clients-applied":
                db.clients_applied.delete_many({})
                data = [{k:v for k, v in client.items() if k != "id"} for client in event["clients"]]
                if data:
                    db.clients_applied.insert_many(data)

                socketio.emit("setClientsApplied", dump(db.clients_applied.find()))

    with celery.connection() as connection:
        recv = celery.events.Receiver(connection, handlers={
            '*': announce_tasks,
        })
        recv.capture(limit=None, timeout=None, wakeup=True)


def create_app():
    # init collection server
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

    # init collection clients
    # if not db.clients.find_one({}):
    #     ansible_config_path = os.path.join(ANSIBLE_PROJECT_PATH, "group_vars", "all", "wireguard_peers")
    #     with open(ansible_config_path) as f:
    #         data = yaml.safe_load(f)
    #     peers = data.get("wireguard", {}).get("peers", [])
    #     for index, peer in enumerate(peers):
    #         # TODO: title and private_key missing
    #         db.clients.insert_one(peer)

    if not db.users.find_one({}):
        username = "admin"
        password = "123456"
        roles = [
            "admin"
        ]
        db.users.insert_one({
            "username": username,
            "password": generate_password_hash(password).decode('utf8'),
            "roles": roles
        })

    celery_thread = Thread(target=celery_monitor, daemon=True)
    celery_thread.start()

    return app