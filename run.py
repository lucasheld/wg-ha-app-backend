from werkzeug.serving import is_running_from_reloader

from wg_ha_backend import app, create_app

if __name__ == "__main__":
    if is_running_from_reloader():
        app = create_app()
    app.run(host="0.0.0.0", debug=True)
