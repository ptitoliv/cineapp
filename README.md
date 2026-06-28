# cineapp
A small application for rating movies

# gunicorn start

`gunicorn -u www -g www -w 1 --threads 100 -D cineapp:app`

SocketIO runs in `threading` async mode; WebSocket transport is provided by the `simple-websocket` package (no eventlet/gevent).

Be careful just having one worker. If there is more than one, SocketIO will generate a lot of bad requests with 400 error code.

# Apache Configuration
## SocketIO redirection

```
RewriteEngine on

# socket.io 1.0+ starts all connections with an HTTP polling request
RewriteCond %{QUERY_STRING} transport=polling       [NC]
RewriteRule /(.*)           http://localhost:8000/$1 [P]

# When socket.io wants to initiate a WebSocket connection, it sends an
# "upgrade: websocket" request that should be transferred to ws://
RewriteCond %{HTTP:Upgrade} websocket               [NC]
RewriteRule /(.*)           ws://localhost:8000/$1  [P]
```

## Flask redirection
```
ProxyPass           /   http://localhost:8000/
ProxyPassReverse    /   http://localhost:8000/
```

## Headers Write

We send these headers to the application in order to have the external URLs correctly generated.

```
ProxyPreserveHost On
RequestHeader set Host "cineapp.ptitoliv.net"
RequestHeader set X-Forwarded-Proto "https"
```

## Proxy Exclusion

Don't proxify static content

```
ProxyPassMatch ^/static !
```



