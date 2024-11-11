import json
import logging
import websockets
import asyncio
import os
import shutil
from datetime import datetime
from obsws_python import ReqClient

# OBS WebSocket connection details
OBS_HOST = "localhost"
OBS_PORT = 4455  # Default port for OBS WebSocket v5.x+
OBS_PASSWORD = ""  # No password required if authentication is disabled

# Default paths for recordings, clips, and snapshots
BASE_PATH = os.getcwd()
VIDEO_PATH = os.path.join(BASE_PATH, "videos")
CLIPS_PATH = os.path.join(BASE_PATH, "clips")
SNAPSHOT_PATH = os.path.join(BASE_PATH, "snapshots")

# Ensure directories exist
os.makedirs(VIDEO_PATH, exist_ok=True)
os.makedirs(CLIPS_PATH, exist_ok=True)
os.makedirs(SNAPSHOT_PATH, exist_ok=True)

# Global set to manage connected clients
clients = set()

class OBSService:
    def __init__(self):
        # Initialize and connect to OBS when creating an instance
        self.ws = ReqClient(host=OBS_HOST, port=OBS_PORT, password=OBS_PASSWORD)
        self.current_recording_file = None

    def disconnect(self):
        self.ws.disconnect()

    def start_recording(self):
        # Set recording path
        self.ws.set_record_directory(recordDirectory=VIDEO_PATH)
        # Start recording
        self.ws.start_record()

    def stop_recording(self):
        # Stop recording and retrieve the output path
        response = self.ws.stop_record()
        output_path = response.output_path if response.output_path else None
        if output_path:
            return output_path
        else:
            raise Exception("Failed to retrieve recording file path")

    def toggle_record_pause(self):
        # Toggle pause/resume for the current video recording session
        self.ws.toggle_record_pause()

    def take_snapshot(self, source_name="Scene", image_format="png"):
        # Save a screenshot of the given source or scene to the filesystem
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        file_name = f"{timestamp}.{image_format}"
        file_path = os.path.join(SNAPSHOT_PATH, file_name)

        # Set default width, height, and quality
        width = 1920  # Setting a default width that is reasonable
        height = 1080  # Setting a default height that is reasonable
        quality = -1  # Use default compression quality

        # Request to save the screenshot using `save_source_screenshot` with the expected parameters
        try:
            self.ws.save_source_screenshot(
                name=source_name,
                img_format=image_format,
                file_path=file_path,
                width=width,
                height=height,
                quality=quality
            )
            return file_path
        except Exception as e:
            raise Exception(f"Failed to take snapshot: {str(e)}")

    def start_replay_buffer(self):
        # Start the replay buffer
        self.ws.start_replay_buffer()

    def save_replay_buffer(self):
        # Save the replay buffer as a highlight
        response = self.ws.save_replay_buffer()
        if response and response.output_path:
            return response.output_path
        else:
            raise Exception("Failed to retrieve replay buffer output path")

# WebSocket handler for incoming connections
async def handle_client(websocket, path):
    clients.add(websocket)
    logging.info(f"Client connected: {websocket.remote_address}")
    obs_service = OBSService()

    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                command = data.get("command")

                if command == "START_RECORDING":
                    obs_service.start_recording()
                    await websocket.send(json.dumps({"status": "Recording started"}))

                elif command == "STOP_RECORDING":
                    try:
                        video_path = obs_service.stop_recording()
                        await websocket.send(json.dumps({
                            "status": "Recording stopped",
                            "file_path": video_path
                        }))
                    except Exception as e:
                        await websocket.send(json.dumps({"error": f"Stopping recording failed: {str(e)}"}))

                elif command == "PAUSE_RECORDING":
                    obs_service.toggle_record_pause()
                    await websocket.send(json.dumps({"status": "Toggled recording pause state"}))

                elif command == "TAKE_SNAPSHOT":
                    try:
                        file_path = obs_service.take_snapshot()
                        await websocket.send(json.dumps({
                            "status": "Snapshot taken",
                            "file_path": file_path
                        }))
                    except Exception as e:
                        await websocket.send(json.dumps({"error": f"Snapshot failed: {str(e)}"}))

                elif command == "START_REPLAY_BUFFER":
                    obs_service.start_replay_buffer()
                    await websocket.send(json.dumps({"status": "Replay buffer started"}))

                elif command == "SAVE_REPLAY_BUFFER":
                    try:
                        replay_path = obs_service.save_replay_buffer()
                        await websocket.send(json.dumps({
                            "status": "Replay buffer saved",
                            "file_path": replay_path
                        }))
                    except Exception as e:
                        await websocket.send(json.dumps({"error": f"Saving replay buffer failed: {str(e)}"}))

                else:
                    await websocket.send(json.dumps({"error": "Unknown command"}))
            except json.JSONDecodeError:
                await websocket.send(json.dumps({"error": "Invalid message format"}))

    except websockets.ConnectionClosed:
        logging.info(f"Connection closed: {websocket.remote_address}")
    finally:
        clients.remove(websocket)
        obs_service.disconnect()
        logging.info(f"Client disconnected: {websocket.remote_address}")

# Start the WebSocket server
async def start_server():
    async with websockets.serve(handle_client, "", 8765):
        logging.info("WebSocket server started at ws://localhost:8765")
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(start_server())
