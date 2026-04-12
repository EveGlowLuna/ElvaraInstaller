import asyncio
import websockets
from typing import Dict, Set

from installer import *

CONNECTED: Dict[int, websockets.WebSocketServerProtocol] = {}
MAIN_LOOP = None

async def handler(websocket):
    global MAIN_LOOP
    MAIN_LOOP = asyncio.get_running_loop()
    client_id = id(websocket)
    CONNECTED[client_id] = websocket
    print(f"Client {client_id} connected")
    try:
        async for message in websocket:
            print(f"收到: {message}")
    finally:
        del CONNECTED[client_id]

def send_msg(msg: str):
    if MAIN_LOOP is not None and CONNECTED:
        for ws in CONNECTED.values():
            asyncio.run_coroutine_threadsafe(
                ws.send(msg),
                MAIN_LOOP
            )

