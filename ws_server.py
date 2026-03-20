import asyncio
import websockets
import json

connected = set()
users = {}

async def handler(ws):
    connected.add(ws)
    try:
        async for message in ws:
            data = json.loads(message)
            if data['type'] == 'join':
                users[ws] = data['name']
                for client in connected:
                    await client.send(json.dumps({
                        'type': 'system_message',
                        'text': f'{data["name"]} присоединился'
                    }))
            elif data['type'] == 'message':
                for client in connected:
                    await client.send(json.dumps({
                        'type': 'new_message',
                        'user': users.get(ws, 'Аноним'),
                        'text': data['text']
                    }))
    finally:
        connected.remove(ws)
        if ws in users:
            for client in connected:
                await client.send(json.dumps({
                    'type': 'system_message',
                    'text': f'{users[ws]} вышел'
                }))
            del users[ws]

async def main():
    async with websockets.serve(handler, "0.0.0.0", 5000):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
