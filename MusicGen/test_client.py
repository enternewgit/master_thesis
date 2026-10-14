"""
Simple test client that connects to the local proxy, sends a JSON message,
and prints any responses. Useful to validate proxy -> mock_upstream path.
"""
import asyncio
import json
import os
import websockets

URL = os.environ.get("TEST_PROXY_URL", "ws://127.0.0.1:8765/")

async def main():
    print(f"Connecting to {URL}")
    try:
        async with websockets.connect(URL) as ws:
            msg = {"type": "test", "payload": "hello-from-test-client"}
            await ws.send(json.dumps(msg))
            print("Sent:", msg)
            # wait for a single response
            resp = await ws.recv()
            print("Received:", resp)
    except Exception as e:
        print("Error:", e)

if __name__ == '__main__':
    asyncio.run(main())
