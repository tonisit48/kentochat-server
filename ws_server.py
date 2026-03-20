from flask import Flask, request, jsonify, send_file
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import sqlite3
import os
import uuid
import io
from datetime import datetime
import base64

app = Flask(__name__)
CORS(app, origins="*")
socketio = SocketIO(app, cors_allowed_origins="*")

# База данных
conn = sqlite3.connect('chat.db', check_same_thread=False)
c = conn.cursor()

# Таблицы
c.execute('''CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE,
    status TEXT,
    last_seen TEXT
)''')

c.execute('''CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    from_user TEXT,
    to_user TEXT,
    text TEXT,
    file TEXT,
    file_type TEXT,
    timestamp TEXT,
    read INTEGER DEFAULT 0
)''')

c.execute('''CREATE TABLE IF NOT EXISTS files (
    id TEXT PRIMARY KEY,
    filename TEXT,
    data BLOB,
    mime_type TEXT,
    size INTEGER
)''')

conn.commit()

active_users = {}
user_sockets = {}

@app.route('/')
def index():
    return 'КентоЧат сервер работает!'

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    
    if not username:
        return jsonify({'error': 'Ник нужен'}), 400
    
    user_id = str(uuid.uuid4())
    
    try:
        c.execute("INSERT INTO users (id, username, status, last_seen) VALUES (?, ?, ?, ?)",
                  (user_id, username, 'offline', datetime.now().isoformat()))
        conn.commit()
        return jsonify({'user_id': user_id, 'username': username})
    except sqlite3.IntegrityError:
        c.execute("SELECT id FROM users WHERE username = ?", (username,))
        user_id = c.fetchone()[0]
        return jsonify({'user_id': user_id, 'username': username})

@app.route('/api/users', methods=['GET'])
def get_users():
    c.execute("SELECT username, status FROM users")
    users = [{'username': row[0], 'status': row[1]} for row in c.fetchall()]
    return jsonify(users)

@app.route('/api/messages/<username>', methods=['GET'])
def get_messages(username):
    other = request.args.get('with')
    c.execute('''SELECT id, from_user, text, file, file_type, timestamp, read 
                 FROM messages 
                 WHERE (from_user = ? AND to_user = ?) OR (from_user = ? AND to_user = ?)
                 ORDER BY timestamp''',
              (username, other, other, username))
    messages = []
    for row in c.fetchall():
        messages.append({
            'id': row[0],
            'from': row[1],
            'text': row[2] or '',
            'file': row[3],
            'file_type': row[4],
            'timestamp': row[5],
            'read': bool(row[6])
        })
    return jsonify(messages)

@app.route('/api/upload', methods=['POST'])
def upload_file():
    try:
        data = request.json
        file_data = data.get('file', '')
        filename = data.get('filename', 'file')
        mime_type = data.get('mime_type', 'application/octet-stream')
        
        # Убираем префикс data:image/jpeg;base64, если есть
        if ',' in file_data:
            file_data = file_data.split(',')[1]
        
        file_bytes = base64.b64decode(file_data)
        file_id = str(uuid.uuid4())
        
        c.execute("INSERT INTO files (id, filename, data, mime_type, size) VALUES (?, ?, ?, ?, ?)",
                  (file_id, filename, file_bytes, mime_type, len(file_bytes)))
        conn.commit()
        
        return jsonify({'file_id': file_id, 'filename': filename, 'size': len(file_bytes)})
    except Exception as e:
        print(f'Upload error: {e}')
        return jsonify({'error': str(e)}), 500

@app.route('/api/file/<file_id>')
def get_file(file_id):
    try:
        c.execute("SELECT filename, data, mime_type FROM files WHERE id = ?", (file_id,))
        row = c.fetchone()
        if row:
            return send_file(
                io.BytesIO(row[1]),
                mimetype=row[2],
                as_attachment=False,
                download_name=row[0]
            )
        return jsonify({'error': 'File not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@socketio.on('connect')
def handle_connect():
    pass

@socketio.on('login')
def handle_login(data):
    username = data.get('username')
    active_users[request.sid] = username
    user_sockets[username] = request.sid
    
    c.execute("UPDATE users SET status = 'online', last_seen = ? WHERE username = ?",
              (datetime.now().isoformat(), username))
    conn.commit()
    
    c.execute("SELECT username, status FROM users")
    users = [{'username': row[0], 'status': row[1]} for row in c.fetchall()]
    emit('users_update', users, broadcast=True)

@socketio.on('private_message')
def handle_private_message(data):
    from_user = active_users.get(request.sid)
    to_user = data.get('to')
    text = data.get('text', '')
    file_id = data.get('file_id')
    file_type = data.get('file_type')
    
    msg_id = str(uuid.uuid4())
    timestamp = datetime.now().isoformat()
    
    c.execute('''INSERT INTO messages (id, from_user, to_user, text, file, file_type, timestamp, read)
                 VALUES (?, ?, ?, ?, ?, ?, ?, 0)''',
              (msg_id, from_user, to_user, text, file_id, file_type, timestamp))
    conn.commit()
    
    msg_data = {
        'id': msg_id,
        'from': from_user,
        'text': text,
        'file': file_id,
        'file_type': file_type,
        'timestamp': timestamp
    }
    
    if to_user in user_sockets:
        emit('new_message', msg_data, to=user_sockets[to_user])
    emit('new_message', msg_data, to=request.sid)

@socketio.on('disconnect')
def handle_disconnect():
    username = active_users.pop(request.sid, None)
    if username:
        user_sockets.pop(username, None)
        c.execute("UPDATE users SET status = 'offline', last_seen = ? WHERE username = ?",
                  (datetime.now().isoformat(), username))
        conn.commit()
        
        c.execute("SELECT username, status FROM users")
        users = [{'username': row[0], 'status': row[1]} for row in c.fetchall()]
        emit('users_update', users, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)
