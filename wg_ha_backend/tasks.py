import os
import subprocess
from threading import Thread

from config import ANSIBLE_PROJECT_PATH
from wg_ha_backend import celery, socketio
from wg_ha_backend.exceptions import PlaybookException


@celery.task(bind=True)
def run_playbook(self, playbook, extra_vars=None):
    # check if playbook exists
    playbook_path = os.path.join(ANSIBLE_PROJECT_PATH, playbook)
    if not os.path.isfile(playbook_path):
        raise Exception("Playbook does not exist")

    command = [
        "ansible-playbook",
        playbook
    ]

    # add extra-vars to command
    if extra_vars:
        extra_vars_str = ""
        for key, value in extra_vars.items():
            extra_vars_str += "{}={} ".format(key, value)
        extra_vars_str = extra_vars_str.strip()
        command.append("--extra-vars")
        command.append(extra_vars_str)

    # execute command
    process = subprocess.Popen(
        command,
        cwd=ANSIBLE_PROJECT_PATH,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT
    )

    output = ""
    last_output_stripped = ""
    # read new lines while process is running
    while process.poll() is None:
        line = process.stdout.readline().decode()
        output += line
        output_stripped = output.strip()
        if output_stripped and output_stripped != last_output_stripped:
            last_output_stripped = output_stripped
            self.update_state(state='PROGRESS', meta={'output': output_stripped})
            self.send_event("task-progress", output=output_stripped)
    # read the rest after process has stopped
    line = process.stdout.read().decode()
    output += line
    if process.returncode != 0:
        raise PlaybookException(output.strip())
    return {
        'output': output.strip()
    }


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
                    "output": event['output']
                })

    with celery.connection() as connection:
        recv = celery.events.Receiver(connection, handlers={
            '*': announce_tasks,
        })
        recv.capture(limit=None, timeout=None, wakeup=True)


celery_thread = Thread(target=celery_monitor, daemon=True)
celery_thread.start()
