"""
Simple WebSocket proxy for Lyria RealTime (demo).
- Listens for inbound WebSocket connections from a browser client
- For each client, opens a connection to the upstream Lyria WS with API key
- Forwards messages bidirectionally

Notes:
- This is a minimal demo. For production, add authentication, rate limits, validation, and TLS.
- You must place your API key in a local `.env` file (see `.env.example`).
"""

import asyncio
import os
import json
from typing import Any
from dotenv import load_dotenv
import websockets
from websockets import WebSocketServerProtocol

load_dotenv()
LYRIA_WS_URL = os.environ.get("LYRIA_WS_URL")
LYRIA_API_KEY = os.environ.get("LYRIA_API_KEY")
PROXY_HOST = os.environ.get("PROXY_HOST", "0.0.0.0")
PROXY_PORT = int(os.environ.get("PROXY_PORT", 8765))

if not LYRIA_WS_URL:
    raise RuntimeError("LYRIA_WS_URL is not set in environment")

if not LYRIA_API_KEY:
    print("Warning: LYRIA_API_KEY not set. Upstream may reject connections.")

async def forward(ws_from: WebSocketServerProtocol, ws_to: Any, direction: str):
    try:
        async for message in ws_from:
            # Optionally inspect/validate/transform message here
            if isinstance(message, bytes):
                await ws_to.send(message)
            else:
                await ws_to.send(message)
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        try:
            await ws_to.close()
        except Exception:
            pass

async def handle_client(client_ws: WebSocketServerProtocol, path: str):
    # Connect to upstream Lyria WS with API key in headers
    headers = [("x-goog-api-key", LYRIA_API_KEY)] if LYRIA_API_KEY else None
    async with websockets.connect(LYRIA_WS_URL, extra_headers=headers) as upstream_ws:
        # Start two tasks to forward messages in both directions
        task1 = asyncio.create_task(forward(client_ws, upstream_ws, "client->upstream"))
        task2 = asyncio.create_task(forward(upstream_ws, client_ws, "upstream->client"))
        done, pending = await asyncio.wait([task1, task2], return_when=asyncio.FIRST_COMPLETED)
        for p in pending:
            p.cancel()

async def main():
    print(f"Starting proxy on ws://{PROXY_HOST}:{PROXY_PORT} -> {LYRIA_WS_URL}")
    async with websockets.serve(handle_client, PROXY_HOST, PROXY_PORT):
        await asyncio.Future()  # run forever

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Proxy stopped by user")
