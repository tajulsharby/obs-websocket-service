import asyncio
import websockets

async def command_handler(websocket, path):
    async for message in websocket:
        print(f"Received command: {message}")
        response = f"Command '{message}' executed successfully"
        await websocket.send(response)

async def main():
    # Use "0.0.0.0" to listen on all network interfaces, allowing external connections.
    async with websockets.serve(command_handler, "0.0.0.0", 8765):
        print("WebSocket server started on all network interfaces")
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    asyncio.run(main())
