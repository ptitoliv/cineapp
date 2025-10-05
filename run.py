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
socketio.run(app,debug=True,host="0.0.0.0",keyfile='certs/key.pem', certfile='certs/cert.pem')
