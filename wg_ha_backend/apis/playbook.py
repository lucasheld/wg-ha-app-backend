from flask import jsonify, url_for
from flask_restx import Resource, reqparse, Namespace

from wg_ha_backend.keycloak import admin_required
from wg_ha_backend.tasks import run_playbook

api = Namespace('playbook', description='Endpoints to execute an Ansible Playbook and receive the output')

playbook_parser = reqparse.RequestParser()
playbook_parser.add_argument('playbook', type=str, help='Filename of the playbook', location='json')
playbook_parser.add_argument('extra_vars', type=str, help='Variables that should be used to execute the playbook', location='json')


@api.route("")
class PlaybookList(Resource):
    @api.doc(security='token', parser=playbook_parser)
    @admin_required()
    def post(self):
        args = playbook_parser.parse_args()
        playbook = args["playbook"]
        extra_vars = args["extra_vars"]
        task = run_playbook.delay(playbook=playbook, extra_vars=extra_vars)
        return jsonify({}), 202, {'Location': url_for('route_playbook_status', task_id=task.id)}


@api.route("/<id>")
@api.doc(params={
    'id': 'Id of the celery task that executes the ansible playbook'
})
class Playbook(Resource):
    @api.doc(security='token')
    @admin_required()
    def get(self, id):
        task = run_playbook.AsyncResult(id)
        if task.state == 'FAILURE':
            response = {
                'state': task.state,
                'output': str(task.info),  # exception message
            }
        else:
            output = ""
            if task.info:
                output = task.info.get('output', "")
            response = {
                'state': task.state,
                'output': output,
            }
        return jsonify(response)
