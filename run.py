#!flask/bin/python
from cineapp import app, socketio

# We need to run the application with SocketIO object
# If not the apply doesn't work well on socket event detection
socketio.run(app,debug=True,host="0.0.0.0",keyfile='/usr/local/etc/letsencrypt/live/ares.ptitoliv.net/privkey.pem', certfile='/usr/local/etc/letsencrypt/live/ares.ptitoliv.net/fullchain.pem')
