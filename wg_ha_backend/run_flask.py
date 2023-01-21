import time
from threading import Thread

from celery.result import AsyncResult

from wg_ha_backend import app, celery, db, socketio, emit
from wg_ha_backend.utils import dump
from wg_ha_backend.keycloak import get_keycloak_user_id


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

                # only admin can see tasks
                emit(event_type, {
                    "uuid": task.uuid,
                    "name": task.name,
                    "received": task.received,
                    "state": task_state,
                    **task.info()
                }, admins=True)
            elif event_type == "task-progress":
                # only admin can see tasks
                emit(event_type, {
                    "uuid": task.uuid,
                    "output": event["output"]
                }, admins=True)
            elif event_type == "clients-applied":
                db.clients_applied.delete_many({})
                data = [{k:v for k, v in client.items() if k != "id"} for client in event["clients"]]
                if data:
                    db.clients_applied.insert_many(data)

                # send clientsApplied to the client owners and admins
                clients_applied = dump(db.clients_applied.find())
                clients_applied_by_user_id = {}
                for client_applied in clients_applied:
                    user_id = client_applied["user_id"]
                    if user_id not in clients_applied_by_user_id:
                        clients_applied_by_user_id[user_id] = []
                    clients_applied_by_user_id[user_id].append(client_applied)
                for user_id in clients_applied_by_user_id:
                    emit("setClientsApplied", clients_applied_by_user_id[user_id], to=user_id)
                emit("setClientsApplied", clients_applied, admins=True)

    with celery.connection() as connection:
        recv = celery.events.Receiver(connection, handlers={
            '*': announce_tasks,
        })
        recv.capture(limit=None, timeout=None, wakeup=True)


def apply_clients():
    from wg_ha_backend.utils import render_and_run_ansible, check_apply_config_necessary

    while True:
        if check_apply_config_necessary():
            # start task
            task = render_and_run_ansible()
            task_id = task.task_id
            # wait until task is finished
            while not AsyncResult(task_id).ready():
                time.sleep(1)
        # wait before next check
        time.sleep(1)


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

    # init collection settings
    if not db.settings.find_one({}):
        db.settings.insert_one({
            "review": False
        })

    celery_monitor_thread = Thread(target=celery_monitor, daemon=True)
    celery_monitor_thread.start()

    apply_clients_thread = Thread(target=apply_clients, daemon=True)
    apply_clients_thread.start()

    return app
