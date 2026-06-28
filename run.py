#!/usr/bin/env python3
import argparse
from cineapp import socketio, create_app

# Parse the command line
parser = argparse.ArgumentParser()
parser.add_argument('--config')
args=parser.parse_args()

# Create the application
app = create_app(args.config)

# We need to run the application with SocketIO object
# If not the apply doesn't work well on socket event detection
# async_mode='threading' makes socketio.run() use the Werkzeug dev server:
#  - it refuses to start unless allow_unsafe_werkzeug=True (dev server only,
#    production runs under gunicorn, so it is safe here);
#  - TLS is passed as ssl_context=(certfile, keyfile), not keyfile/certfile
#    (those kwargs were specific to the eventlet/gevent servers).
socketio.run(app,debug=True,host="0.0.0.0",ssl_context=('certs/cert.pem','certs/key.pem'),allow_unsafe_werkzeug=True)
