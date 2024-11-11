from obsws_python import ReqClient
import asyncio
from aiohttp import web
import json
import os
from datetime import datetime
import shutil
import argparse
import logging
import ssl

# Set up logging
logging.basicConfig(level=logging.INFO)

# Parse command line arguments
parser = argparse.ArgumentParser(description='OBS WebSocket Service')
parser.add_argument('--obs_host', type=str, default='localhost', help='OBS WebSocket host')
parser.add_argument('--obs_port', type=int, default=4455, help='OBS WebSocket port')
parser.add_argument('--obs_password', type=str, default='', help='OBS WebSocket password')
parser.add_argument('--ws_host', type=str, default='0.0.0.0', help='WebSocket server host')
parser.add_argument('--ws_port', type=int, default=8765, help='WebSocket server port')
parser.add_argument('--certfile', type=str, required=True, help='Path to SSL certificate file')
parser.add_argument('--keyfile', type=str, required=True, help='Path to SSL key file')
args = parser.parse_args()

# OBS WebSocket connection details
OBS_HOST = args.obs_host
OBS_PORT = args.obs_port
OBS_PASSWORD = args.obs_password

# Default paths for recordings, clips, and snapshots
BASE_PATH = os.getcwd()
VIDEO_PATH = os.path.join(BASE_PATH, "videos")
CLIPS_PATH = os.path.join(BASE_PATH, "clips")
SNAPSHOT_PATH = os.path.join(BASE_PATH, "snapshots")

# Ensure directories exist
os.makedirs(VIDEO_PATH, exist_ok=True)
os.makedirs(CLIPS_PATH, exist_ok=True)
os.makedirs(SNAPSHOT_PATH, exist_ok=True)

class OBSService:
    def __init__(self):
        # Initialize and connect to OBS when creating an instance
        logging.info("Initializing OBS connection...")
        try:
            self.ws = ReqClient(host=OBS_HOST, port=OBS_PORT, password=OBS_PASSWORD)
            logging.info("OBS connection established successfully.")
        except Exception as e:
            logging.error(f"Failed to connect to OBS WebSocket: {e}")
            raise e

    def disconnect(self):
        logging.info("Disconnecting OBS...")
        self.ws.disconnect()

    def start_recording(self):
        logging.info("Starting recording...")
        self.ws.set_record_directory(recordDirectory=VIDEO_PATH)
        self.ws.start_record()

    def stop_recording(self):
        logging.info("Stopping recording...")
        response = self.ws.stop_record()
        output_path = response.output_path if response.output_path else None
        if output_path:
            logging.info(f"Recording stopped, file path: {output_path}")
            return output_path
        else:
            raise Exception("Failed to retrieve recording file path")

    def toggle_record_pause(self):
        logging.info("Toggling recording pause...")
        self.ws.toggle_record_pause()

    def take_snapshot(self, source_name="Scene", image_format="png"):
        logging.info("Taking snapshot...")
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        file_name = f"{timestamp}.{image_format}"
        file_path = os.path.join(SNAPSHOT_PATH, file_name)

        width, height, quality = 1920, 1080, -1
        try:
            self.ws.save_source_screenshot(
                name=source_name,
                img_format=image_format,
                file_path=file_path,
                width=width,
                height=height,
                quality=quality
            )
            logging.info(f"Snapshot taken, saved at: {file_path}")
            return file_path
        except Exception as e:
            raise Exception(f"Failed to take snapshot: {str(e)}")

    def start_replay_buffer(self):
        logging.info("Starting replay buffer...")
        self.ws.start_replay_buffer()

    def save_replay_buffer(self):
        logging.info("Saving replay buffer...")
        self.ws.save_replay_buffer()
        self.ws.stop_replay_buffer()

        response = self.ws.get_record_status()
        output_path = response.output_path if response.output_path else None
        if output_path:
            logging.info(f"Replay buffer saved, file path: {output_path}")
            return output_path
        else:
            raise Exception("Failed to retrieve replay buffer output path")

# WebSocket handler for incoming connections using aiohttp
async def handle_client(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    obs_service = OBSService()
    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    command = data.get("command")

                    if command == "START_RECORDING":
                        obs_service.start_recording()
                        await ws.send_str(json.dumps({"status": "Recording started"}))

                    elif command == "STOP_RECORDING":
                        try:
                            video_path = obs_service.stop_recording()
                            await ws.send_str(json.dumps({
                                "status": "Recording stopped",
                                "file_path": video_path
                            }))
                        except Exception as e:
                            await ws.send_str(json.dumps({"error": f"Stopping recording failed: {str(e)}"}))

                    elif command == "PAUSE_RECORDING":
                        obs_service.toggle_record_pause()
                        await ws.send_str(json.dumps({"status": "Toggled recording pause state"}))

                    elif command == "TAKE_SNAPSHOT":
                        try:
                            file_path = obs_service.take_snapshot()
                            await ws.send_str(json.dumps({
                                "status": "Snapshot taken",
                                "file_path": file_path
                            }))
                        except Exception as e:
                            await ws.send_str(json.dumps({"error": f"Snapshot failed: {str(e)}"}))

                    elif command == "START_REPLAY_BUFFER":
                        obs_service.start_replay_buffer()
                        await ws.send_str(json.dumps({"status": "Replay buffer started"}))

                    elif command == "SAVE_REPLAY_BUFFER":
                        try:
                            file_path = obs_service.save_replay_buffer()
                            await ws.send_str(json.dumps({
                                "status": "Replay buffer saved",
                                "file_path": file_path
                            }))
                        except Exception as e:
                            await ws.send_str(json.dumps({"error": f"Saving replay buffer failed: {str(e)}"}))

                    else:
                        await ws.send_str(json.dumps({"error": "Unknown command"}))
                except json.JSONDecodeError:
                    await ws.send_str(json.dumps({"error": "Invalid message format"}))

    finally:
        obs_service.disconnect()

    return ws

# Start the WebSocket server using aiohttp with SSL
ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ssl_context.load_cert_chain(certfile=args.certfile, keyfile=args.keyfile)

app = web.Application()
app.router.add_get('/', handle_client)

if __name__ == "__main__":
    web.run_app(app, host=args.ws_host, port=args.ws_port, ssl_context=ssl_context)
