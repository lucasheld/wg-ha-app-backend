from flask_restx import Api

from .client import api as client_namespace
from .custom_rule import api as custom_rule_namespace
from .inventory import api as inventory_namespace
from .playbook import api as playbook_namespace
from .settings import api as settings_namespace

api = Api(
    title="Backend REST API",
    version="1.0",
    description="REST API of the Backend",
    authorizations={
        'token': {
            'type': 'apiKey',
            'in': 'header',
            'name': 'Authorization'
        }
    }
)

api.add_namespace(client_namespace)
api.add_namespace(inventory_namespace)
api.add_namespace(playbook_namespace)
api.add_namespace(settings_namespace)
api.add_namespace(custom_rule_namespace)
