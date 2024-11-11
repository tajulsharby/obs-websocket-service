from obsws_python import ReqClient
from aiohttp import web
import aiohttp_cors
import json
import os
from datetime import datetime
import argparse
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)

# Parse command line arguments
parser = argparse.ArgumentParser(description='OBS HTTP API Service')
parser.add_argument('--obs_host', type=str, default='localhost', help='OBS WebSocket host')
parser.add_argument('--obs_port', type=int, default=4455, help='OBS WebSocket port')
parser.add_argument('--obs_password', type=str, default='', help='OBS WebSocket password')
parser.add_argument('--api_host', type=str, default='0.0.0.0', help='API server host')
parser.add_argument('--api_port', type=int, default=8080, help='API server port')
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

# Create an instance of OBSService
obs_service = OBSService()

# HTTP API handlers
async def start_recording(request):
    try:
        obs_service.start_recording()
        return web.json_response({"status": "Recording started"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def stop_recording(request):
    try:
        video_path = obs_service.stop_recording()
        return web.json_response({"status": "Recording stopped", "file_path": video_path})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def pause_recording(request):
    try:
        obs_service.toggle_record_pause()
        return web.json_response({"status": "Toggled recording pause state"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def take_snapshot(request):
    try:
        file_path = obs_service.take_snapshot()
        return web.json_response({"status": "Snapshot taken", "file_path": file_path})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def start_replay_buffer(request):
    try:
        obs_service.start_replay_buffer()
        return web.json_response({"status": "Replay buffer started"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def save_replay_buffer(request):
    try:
        file_path = obs_service.save_replay_buffer()
        return web.json_response({"status": "Replay buffer saved", "file_path": file_path})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

# Start the API server using aiohttp
app = web.Application()
app.router.add_post('/start_recording', start_recording)
app.router.add_post('/stop_recording', stop_recording)
app.router.add_post('/pause_recording', pause_recording)
app.router.add_post('/take_snapshot', take_snapshot)
app.router.add_post('/start_replay_buffer', start_replay_buffer)
app.router.add_post('/save_replay_buffer', save_replay_buffer)

# Configure default CORS settings
cors = aiohttp_cors.setup(app)
for route in list(app.router.routes()):
    cors.add(route, {
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*"
        )
    })

if __name__ == "__main__":
    web.run_app(app, host=args.api_host, port=args.api_port)
