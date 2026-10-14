"""
Simple mock upstream server to simulate Lyria RealTime behavior for local tests.
It echoes received text messages with a wrapper JSON including a server timestamp.
"""
import asyncio
import json
from datetime import datetime
import websockets

HOST = '127.0.0.1'
PORT = 9876

async def handler(ws, path):
    print(f"Mock upstream: client connected from {ws.remote_address}")
    try:
        async for message in ws:
            print(f"Mock upstream received: {message}")
            try:
                payload = json.loads(message)
            except Exception:
                payload = {"raw": message}
            response = {
                "type": "mock_response",
                "received": payload,
                "server_time": datetime.utcnow().isoformat() + 'Z'
            }
            await ws.send(json.dumps(response))
    except websockets.exceptions.ConnectionClosed:
        print("Mock upstream: connection closed")

async def main():
    print(f"Starting mock upstream at ws://{HOST}:{PORT}")
    async with websockets.serve(handler, HOST, PORT):
        await asyncio.Future()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('Stopping mock upstream')
