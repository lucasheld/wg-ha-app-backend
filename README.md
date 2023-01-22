# wg-ha-app-backend

## Usage
Adjust the volumes of the celery and flask service inside the file `docker-compose.yml`.

### development
To enable live reload during development and enable flask debugging, run the following command.
```console
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up
```

### production
The production mode uses gunicorn to run the flask app.
```console
docker-compose up
```


## Configure Keycloak

Add realm
- name: wg-app

Clients -> Create
- Client ID: backend

Clients -> backend
- Access Type: bearer-only

Clients -> Create
- Client ID: frontend

Clients -> frontend
- Access Type: public
- Valid Redirect URIs: http://127.0.0.1:3000 and http://127.0.0.1:3000/*
- Web Origins: http://127.0.0.1:3000 and http://127.0.0.1:3000/*

Roles -> Add Role
- Role Name: app-admin

Roles -> Add Role
- Role Name: app-user

Users -> Add User
- Username: user1

Users -> user1 -> Credentials
- Fill "Password" and "Password Confirmation"
- Uncheck "Temporary"

Users -> user1 -> Role Mappings
- In "Realm Roles" assign role "app-admin"
- In "Client Roles" select "realm-management" and assign role "view-users"

Users -> Add User
- Username: user2

Users -> user2 -> Credentials
- Fill "Password" and "Password Confirmation"
- Uncheck "Temporary"

Users -> user2 -> Role Mappings
- In "Realm Roles" assign role "app-user"

Clients -> Backend -> Credentials -> Regenerate Secret
Copy the Secret, open docker-compose.yml, and replace the KEYCLOAK_SECRET_KEY environment variable in the flask service
