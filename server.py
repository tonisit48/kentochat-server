from flask import Flask
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import sqlite3
from datetime import datetime

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# База данных
conn = sqlite3.connect('chat.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS messages 
             (id INTEGER PRIMARY KEY, user TEXT, text TEXT, time TEXT)''')
conn.commit()

# Активные пользователи
active_users = {}

@app.route('/')
def index():
    return 'КентоЧат сервер работает!'

@socketio.on('connect')
def handle_connect():
    print(f'Кент подключился')

@socketio.on('join')
def handle_join(data):
    user_name = data.get('name')
    active_users[request.sid] = user_name
    
    # Отправляем список всех в чате
    users_list = list(active_users.values())
    emit('users_update', users_list, broadcast=True)
    
    # Отправляем историю
    c.execute("SELECT user, text, time FROM messages ORDER BY id DESC LIMIT 50")
    history = c.fetchall()[::-1]
    
    for msg in history:
        emit('old_message', {
            'user': msg[0],
            'text': msg[1],
            'time': msg[2]
        })
    
    # Оповещаем всех
    emit('system_message', {
        'text': f'{user_name} присоединился',
        'time': datetime.now().strftime("%H:%M")
    }, broadcast=True)

@socketio.on('message')
def handle_message(data):
    user = active_users.get(request.sid, 'Аноним')
    text = data.get('text')
    time_now = datetime.now().strftime("%H:%M")
    
    # Сохраняем
    c.execute("INSERT INTO messages (user, text, time) VALUES (?, ?, ?)",
              (user, text, time_now))
    conn.commit()
    
    # Рассылаем
    emit('new_message', {
        'user': user,
        'text': text,
        'time': time_now
    }, broadcast=True)

@socketio.on('typing')
def handle_typing(data):
    emit('user_typing', {'user': data['user']}, broadcast=True, include_self=False)

@socketio.on('disconnect')
def handle_disconnect():
    user = active_users.pop(request.sid, None)
    if user:
        emit('system_message', {
            'text': f'{user} вышел',
            'time': datetime.now().strftime("%H:%M")
        }, broadcast=True)
        
        users_list = list(active_users.values())
        emit('users_update', users_list, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)