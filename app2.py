import asyncio
import json
import websockets
import logging

# Global variables to manage connections and tasks
clients = set()

# WebSocket handler for incoming connections
async def handle_client(websocket, path):
    clients.add(websocket)
    logging.info(f"Client connected: {websocket.remote_address}")

    try:
        async for message in websocket:
            logging.info(f"Raw message received: {message}")
            try:
                command_data = json.loads(message)
                command = command_data.get("command")
                logging.info(f"Command received: {command}")
            except json.JSONDecodeError as e:
                logging.error(f"Failed to parse command: {e}")
                await websocket.send(json.dumps({
                    "status": "error",
                    "message": "Invalid JSON format"
                }))
                continue

            # Dispatch command to the appropriate handler
            if command == "PING":
                await websocket.send(json.dumps({
                    "status": "success",
                    "message": "PONG"
                }))
            else:
                logging.warning(f"Unknown command received: {command}")
                await websocket.send(json.dumps({
                    "status": "error",
                    "message": "Unknown command received"
                }))
    except websockets.ConnectionClosed:
        logging.info(f"Connection closed: {websocket.remote_address}")
    finally:
        clients.remove(websocket)
        logging.info(f"Client disconnected: {websocket.remote_address}")

# WebSocket server start code
async def main():
    async with websockets.serve(handle_client, "localhost", 8765):
        logging.info("WebSocket server started on ws://localhost:8765")
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
