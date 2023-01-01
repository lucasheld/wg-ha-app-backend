from flask_restx import Api

from .client import api as client_namespace
from .inventory import api as inventory_namespace
from .playbook import api as playbook_namespace
from .session import api as session_namespace
from .user import api as user_namespace

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
api.add_namespace(session_namespace)
api.add_namespace(user_namespace)
