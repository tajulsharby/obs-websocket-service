from obsws_python import ReqClient
import asyncio
import websockets
import json
import os
from datetime import datetime
import shutil

# OBS WebSocket connection details
OBS_HOST = "localhost"
OBS_PORT = 4455  # Default port for OBS WebSocket v5.x+
OBS_PASSWORD = ""  # No password required if authentication is disabled

# Default paths for recordings and clips
BASE_PATH = os.getcwd()
VIDEO_PATH = os.path.join(BASE_PATH, "Video")
CLIPS_PATH = os.path.join(BASE_PATH, "Clips")

# Ensure directories exist
os.makedirs(VIDEO_PATH, exist_ok=True)
os.makedirs(CLIPS_PATH, exist_ok=True)

class OBSService:
    def __init__(self):
        # Initialize and connect to OBS when creating an instance
        self.ws = ReqClient(host=OBS_HOST, port=OBS_PORT, password=OBS_PASSWORD)

    def disconnect(self):
        self.ws.disconnect()

    def start_recording(self):
        # Set recording path
        self.ws.set_record_directory(recordDirectory=VIDEO_PATH)
        # Start recording
        self.ws.start_record()

    def stop_recording(self):
        # Stop recording
        self.ws.stop_record()

    def toggle_record_pause(self):
        # Toggle pause/resume for the current video recording session
        self.ws.toggle_record_pause()

    def get_recording_status(self):
        # Get the recording status
        return self.ws.get_record_status()

    def take_snapshot(self, source_name="Scene", image_format="png"):
        # Save a screenshot of the given source or scene to the filesystem
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        file_name = f"{timestamp}.{image_format}"
        file_path = os.path.join(BASE_PATH, file_name)

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
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        destination_path = os.path.join(CLIPS_PATH, f"highlight_{timestamp}.mp4")
        default_obs_path = os.path.expanduser("~/Movies")  # Default OBS replay buffer path

        try:
            self.ws.save_replay_buffer()  # Trigger OBS to save replay buffer
            # Stop the replay buffer after saving
            self.ws.stop_replay_buffer()
            # Look for the most recent replay file in the default OBS location
            files = [f for f in os.listdir(default_obs_path) if f.startswith("Replay")]
            if files:
                latest_file = max(files, key=lambda f: os.path.getmtime(os.path.join(default_obs_path, f)))
                source_path = os.path.join(default_obs_path, latest_file)
                shutil.move(source_path, destination_path)
                return destination_path
        except Exception as e:
            raise Exception(f"Failed to save replay buffer: {str(e)}")

# WebSocket handler for incoming connections
async def handle_client(websocket, path):
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
                    obs_service.stop_recording()
                    await websocket.send(json.dumps({"status": "Recording stopped"}))

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
                        file_path = obs_service.save_replay_buffer()
                        await websocket.send(json.dumps({
                            "status": "Replay buffer saved",
                            "file_path": file_path
                        }))
                    except Exception as e:
                        await websocket.send(json.dumps({"error": f"Saving replay buffer failed: {str(e)}"}))

                else:
                    await websocket.send(json.dumps({"error": "Unknown command"}))
            except json.JSONDecodeError:
                await websocket.send(json.dumps({"error": "Invalid message format"}))

    finally:
        obs_service.disconnect()

# Start the WebSocket server
async def start_server():
    server = await websockets.serve(handle_client, "localhost", 8765)
    print("WebSocket server started at ws://localhost:8765")
    await server.wait_closed()

if __name__ == "__main__":
    try:
        asyncio.run(start_server())
    except KeyboardInterrupt:
        print("Server stopped by user")
