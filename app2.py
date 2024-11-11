import asyncio
import websockets

async def custom_handler(websocket, path):
    # Handle incoming messages here
    async for message in websocket:
        print(f"Received: {message}")
        await websocket.send(f"Echo: {message}")

async def main():
    async def handler_with_headers(websocket, path):
        # Custom headers or any checks during the handshake
        print(f"Custom handler called with headers.")

        # Pass control to the normal handler
        await custom_handler(websocket, path)

    async with websockets.serve(handler_with_headers, "0.0.0.0", 8765):
        print("Server started with custom headers")
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    asyncio.run(main())
