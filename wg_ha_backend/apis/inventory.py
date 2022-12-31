import json
import subprocess

from flask import request
from flask_restx import Resource, Namespace

from config import ANSIBLE_PROJECT_PATH
from wg_ha_backend import admin_required

api = Namespace('inventory', description='TODO operations')


@api.route("")
class InventoryList(Resource):
    @api.doc(security='token')
    @admin_required()
    def get(self):
        command = [
            "ansible-inventory",
            "--list"
        ]
        inventory = request.args.get('inventory')
        if inventory:
            command.append("-i")
            command.append(inventory)
        process = subprocess.Popen(
            command,
            cwd=ANSIBLE_PROJECT_PATH,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        output, error = process.communicate()
        if error:
            api.abort(500, error.decode())

        output = output.decode()
        return json.loads(output)
