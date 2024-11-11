import asyncio
import websockets

async def command_handler(websocket, path):
    async for message in websocket:
        print(f"Received command: {message}")
        response = f"Command '{message}' executed successfully"
        await websocket.send(response)

async def main():
    # Change "192.168.50.11" and "8765" to your server IP and port
    async with websockets.serve(command_handler, "192.168.50.11", 8765):
        print("WebSocket server started")
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    asyncio.run(main())
