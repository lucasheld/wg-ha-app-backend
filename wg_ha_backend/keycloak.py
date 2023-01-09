import os
from functools import wraps

from flask import request, g
from keycloak.keycloak_openid import KeycloakOpenID

KEYCLOAK_ROLE_USER = "app-user"
KEYCLOAK_ROLE_ADMIN = "app-admin"


def decode_keycloak_token():
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
        return r
    except:
        return


def user_required():
    def wrapper(fn):
        @wraps(fn)
        def decorator(*args, **kwargs):
            decoded_token = decode_keycloak_token()
            g._app_backend_keycloak = decoded_token
            if decoded_token and (KEYCLOAK_ROLE_USER in decoded_token["realm_access"]["roles"] or KEYCLOAK_ROLE_ADMIN in decoded_token["realm_access"]["roles"]):
                return fn(*args, **kwargs)
            else:
                return "Unauthorized", 401
        return decorator
    return wrapper


def admin_required():
    def wrapper(fn):
        @wraps(fn)
        def decorator(*args, **kwargs):
            decoded_token = decode_keycloak_token()
            g._app_backend_keycloak = decoded_token
            if decoded_token and KEYCLOAK_ROLE_ADMIN in decoded_token["realm_access"]["roles"]:
                return fn(*args, **kwargs)
            else:
                return "Unauthorized", 401
        return decorator
    return wrapper


def get_keycloak_user_id():
    decoded_token = g.get("_app_backend_keycloak")
    if decoded_token is None:
        raise RuntimeError("You must call `@user_required()` or `@admin_required()` before using this method")
    return decoded_token["sub"]
