import asyncio
import websockets

async def command_handler(websocket, path):
    async for message in websocket:
        print(f"Received command: {message}")
        response = f"Command '{message}' executed successfully"
        await websocket.send(response)

start_server = websockets.serve(command_handler, "192.168.50.11", 8765)

asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()
