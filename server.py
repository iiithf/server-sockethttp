#!/usr/bin/env python
import socket
import selectors
import types
import sys
import os


# Global variables
sel = selectors.DefaultSelector()


# HTTP request format
class HttpRequest:
  headers = {}
  trailers = {}
  version = 1.1
  method = ''
  url = ''
  body = b''

# HTTP response format
class HttpResponse:
  headers = {}
  trailers = {}
  version = 1.1
  statusCode = 0
  statusMessage = ''
  body = b''


# Check if request is HTTP
def http_is(data):
  return b'HTTP/' not in data

# Process HTTP head
def http_head(data):
  head_end = data.index(b'\r\n\r\n')
  if head_end<0:
    return None, data
  req = HttpRequest()
  head = data[0:head_end].decode('ascii')
  head_lines = head.split('\r\n')
  head_top = head_lines[0].split(' ')
  req.method = head_top[0]
  req.url = head_top[1]
  req.version = float(head_top[2].split('/')[1])
  for head_line in head_lines[1:]:
    header = head_line.split(': ')
    req.headers[header[0]] = header[1]
  return req, data[head_end+2:]

# Process HTTP body
def http_body(req, data):
  size = int(float(req.headers.get('Content-Length', '0')))
  if len(data)<size:
    return False, data
  req.body = data[0:size]
  return True, data[size:]

# Process HTTP response
def http_response(res):
  data = 'HTTP/{} {} {}\r\n'.format(res.version, res.statusCode, res.statusMessage)
  for key in res.headers:
    data += '{}: {}\r\n'.format(key, res.headers[key])
  data += '\r\n'
  return data.encode('ascii')+res.body

# Service HTTP request
def http_service(data):
  req = data.req
  print('\nHTTP request', data.addr, req.method, req.url)
  if req.url[0:1]=='/':
    req.url = req.url[1:]
  if len(req.url)==0:
    req.url = 'index.html'
  res = HttpResponse()
  res.headers['Connection'] = 'close'
  if not os.path.isfile(req.url):
    print('Bad request', req.url)
    res.statusCode = 403
    res.statusMessage = 'Forbidden'
    res.headers['Content-Length'] = 0
    data.outb += http_response(res)
    return
  print('Served file', req.url)
  file_id = open(req.url, 'rb')
  file_data = file_id.read()
  res.statusCode = 200
  res.statusMessage = 'OK'
  res.headers['Content-Length'] = len(file_data)
  res.body = file_data
  data.outb += http_response(res)
  
# Accept TCP connection
def tcp_accept(s):
  conn, addr = s.accept()
  print('Got a connection', addr)
  conn.setblocking(False)
  data = types.SimpleNamespace(addr=addr, inb=b'', outb=b'', req=None)
  events = selectors.EVENT_READ | selectors.EVENT_WRITE
  sel.register(conn, events, data=data)

# Service TCP connection
def tcp_service(key, mask):
  conn = key.fileobj
  data = key.data
  if mask & selectors.EVENT_READ:
    recv_data = conn.recv(1024)
    if recv_data:
      data.inb += recv_data
      if data.req is None:
        data.req, data.inb = http_head(data.inb)
      if data.req:
        body_got, data.inb = http_body(data.req, data.inb)
        if body_got:
          http_service(data)
          data.req = None
    else:
      print('Connection broke', data.addr)
      sel.unregister(conn)
      conn.close()
  if mask & selectors.EVENT_WRITE:
    if data.outb:
      print('Sending', len(data.outb), 'bytes to', data.addr)
      sent = conn.send(data.outb)
      data.outb = data.outb[sent:]


# Main
port = 8000
if len(sys.argv)>1:
  port = int(float(sys.argv[1]))
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
addr = ('', port)
s.bind(addr)
s.listen()
s.setblocking(False)
sel.register(s, selectors.EVENT_READ, data=None)
print('Listening on', addr)
while True:
  events = sel.select(timeout=None)
  for key, mask in events:
    if key.data is None:
      tcp_accept(key.fileobj)
    else:
      tcp_service(key, mask)
