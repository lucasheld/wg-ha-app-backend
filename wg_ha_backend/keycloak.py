import os
from functools import wraps

from flask import request
from keycloak.keycloak_openid import KeycloakOpenID

def get_keycloak_roles():
    authorization = request.headers.get("Authorization")
    token = ""
    if authorization:
        token = authorization.split("Bearer ")[1]
    try:
        keycloak_openid_client = KeycloakOpenID(
            server_url=os.environ.get("KEYCLOAK_SERVER_URL"),
            client_id=os.environ.get("KEYCLOAK_CLIENT_ID"),
            client_secret_key=os.environ.get("KEYCLOAK_SECRET_KEY"),
            realm_name=os.environ.get("KEYCLOAK_REALM_NAME")
        )
        options = {
            "verify_signature": True,
            "verify_aud": False,
            "verify_exp": True
        }
        keycloak_public_key = "-----BEGIN PUBLIC KEY-----\n" + keycloak_openid_client.public_key() + "\n-----END PUBLIC KEY-----"
        r = keycloak_openid_client.decode_token(
            token,
            key=keycloak_public_key,
            options=options
        )
        roles = r["realm_access"]["roles"]
    except:
        roles = []
    return roles


def user_required():
    def wrapper(fn):
        @wraps(fn)
        def decorator(*args, **kwargs):
            roles = get_keycloak_roles()
            if "app-user" in roles:
                return fn(*args, **kwargs)
            else:
                return "Unauthorized", 401
        return decorator
    return wrapper


def admin_required():
    def wrapper(fn):
        @wraps(fn)
        def decorator(*args, **kwargs):
            roles = get_keycloak_roles()
            if "app-admin" in roles:
                return fn(*args, **kwargs)
            else:
                return "Unauthorized", 401
        return decorator
    return wrapper
