import asyncio
import websockets
import json
import logging
import os
import datetime
import uuid
from obswsrc import OBSWS

# Default configuration
DEFAULT_OBS_HOST = 'localhost'
DEFAULT_OBS_PORT = 4455
DEFAULT_OBS_PASSWORD = ''  # Set your OBS WebSocket password if you have one
DEFAULT_WEBSOCKET_PORT = 8184

# Directories
VIDEO_DIR = 'videos'
SNAPSHOT_DIR = 'snapshots'
LOG_DIR = 'logs'

# Global variables
clients = {}  # Stores client information
obs_client = None  # OBS WebSocket client instance

def setup_logging():
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)
    log_filename = datetime.datetime.now().strftime("%Y%m%d%H%M%S") + '.log'
    log_filepath = os.path.join(LOG_DIR, log_filename)
    logging.basicConfig(
        filename=log_filepath,
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s'
    )
    # Also log to console
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    console.setFormatter(formatter)
    logging.getLogger().addHandler(console)
    logging.info("Logging initialized.")

setup_logging()

def ensure_directories():
    for directory in [VIDEO_DIR, SNAPSHOT_DIR, LOG_DIR]:
        if not os.path.exists(directory):
            os.makedirs(directory)
    logging.info("Directories ensured.")

ensure_directories()

async def on_replay_buffer_saved(event):
    saved_path = event.datain['savedReplayPath']
    logging.info(f"Replay buffer saved at: {saved_path}")
    # You can send this information back to clients if needed

async def connect_to_obs(host=DEFAULT_OBS_HOST, port=DEFAULT_OBS_PORT, password=DEFAULT_OBS_PASSWORD):
    global obs_client
    try:
        obs_client = OBSWS(host, port, password)
        await obs_client.connect()
        # Register event handlers
        obs_client.register_event(on_replay_buffer_saved)
        logging.info(f"Connected to OBS Studio at {host}:{port}")
    except Exception as e:
        logging.error(f"Failed to connect to OBS Studio: {e}")
        obs_client = None

async def handle_client(websocket, path):
    # Assign a unique instance ID to the client
    instance_id = str(uuid.uuid4())
    clients[instance_id] = {
        'websocket': websocket,
        'state': {}
    }
    logging.info(f"New client connected: {instance_id}")

    try:
        async for message in websocket:
            await process_message(instance_id, message)
    except websockets.exceptions.ConnectionClosedOK:
        logging.info(f"Client {instance_id} disconnected normally.")
    except Exception as e:
        logging.error(f"Error with client {instance_id}: {e}")
    finally:
        # Clean up client data
        clients.pop(instance_id, None)
        logging.info(f"Client {instance_id} cleaned up.")

async def process_message(instance_id, message):
    try:
        data = json.loads(message)
        command = data.get('command')
        command_uid = data.get('command_uid')
        parameters = data.get('parameter', {})
        response = {}

        if command == 'CONNECT_WEBSOCKET':
            response = await handle_connect_websocket(instance_id, command_uid, parameters)
        elif command == 'DISCONNECT_WEBSOCKET':
            response = await handle_disconnect_websocket(instance_id, command_uid)
        elif command == 'START_RECORDING':
            response = await handle_start_recording(instance_id, command_uid)
        elif command == 'STOP_RECORDING':
            response = await handle_stop_recording(instance_id, command_uid)
        elif command == 'PAUSE_RECORDING':
            response = await handle_pause_recording(instance_id, command_uid)
        elif command == 'RESUME_RECORDING':
            response = await handle_resume_recording(instance_id, command_uid)
        elif command == 'SAVE_IMAGE_SNAPSHOT':
            response = await handle_save_image_snapshot(instance_id, command_uid)
        elif command == 'START_REPLAY_BUFFER':
            response = await handle_start_replay_buffer(instance_id, command_uid)
        elif command == 'STOP_REPLAY_BUFFER':
            response = await handle_stop_replay_buffer(instance_id, command_uid)
        elif command == 'SAVE_REPLAY_BUFFER':
            response = await handle_save_replay_buffer(instance_id, command_uid)
        else:
            response = {
                "status": "error",
                "command_uid": command_uid,
                "instance_id": instance_id,
                "message": f"Unknown command: {command}"
            }
        # Send response back to the client
        await clients[instance_id]['websocket'].send(json.dumps(response))
        logging.info(f"Processed command: {command} for client {instance_id}")
    except Exception as e:
        logging.error(f"Error processing message from {instance_id}: {e}")
        error_response = {
            "status": "error",
            "command_uid": data.get('command_uid'),
            "instance_id": instance_id,
            "message": f"Error processing command: {str(e)}"
        }
        await clients[instance_id]['websocket'].send(json.dumps(error_response))

async def handle_connect_websocket(instance_id, command_uid, parameters):
    ip_address = parameters.get('ip_address', DEFAULT_OBS_HOST)
    port = parameters.get('port', DEFAULT_OBS_PORT)
    password = parameters.get('password', DEFAULT_OBS_PASSWORD)
    # Reconnect to OBS with new parameters if needed
    await connect_to_obs(ip_address, port, password)
    response = {
        "status": "success",
        "command_uid": command_uid,
        "message": "WebSocket connected successfully",
        "data": {
            "ip_address": ip_address,
            "port": port,
            "instance_id": instance_id
        }
    }
    return response

async def handle_disconnect_websocket(instance_id, command_uid):
    response = {
        "status": "success",
        "command_uid": command_uid,
        "instance_id": instance_id,
        "message": f"WebSocket instance id {instance_id} disconnected successfully"
    }
    # The client will be removed in the main handler's finally block
    return response

async def handle_start_recording(instance_id, command_uid):
    if obs_client is None or not obs_client.connected:
        return {
            "status": "error",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": "Not connected to OBS Studio"
        }
    try:
        await obs_client.call('StartRecord')
        clients[instance_id]['state']['recording_start_time'] = datetime.datetime.now()
        response = {
            "status": "success",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": "Video recording started successfully",
            "data": {
                "datetime": datetime.datetime.now().isoformat()
            }
        }
    except Exception as e:
        response = {
            "status": "error",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": f"Failed to start recording: {e}"
        }
    return response

async def handle_stop_recording(instance_id, command_uid):
    if obs_client is None or not obs_client.connected:
        return {
            "status": "error",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": "Not connected to OBS Studio"
        }
    try:
        await obs_client.call('StopRecord')
        record_status = await obs_client.call('GetRecordStatus')
        file_path = record_status['outputPath']
        start_time = clients[instance_id]['state'].get('recording_start_time')
        if start_time:
            duration = (datetime.datetime.now() - start_time).total_seconds()
            clients[instance_id]['state'].pop('recording_start_time', None)
        else:
            duration = 0
        response = {
            "status": "success",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": "Video recording stopped successfully",
            "data": {
                "file_path": file_path,
                "duration": duration,
                "datetime": datetime.datetime.now().isoformat()
            }
        }
    except Exception as e:
        response = {
            "status": "error",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": f"Failed to stop recording: {e}"
        }
    return response

async def handle_pause_recording(instance_id, command_uid):
    if obs_client is None or not obs_client.connected:
        return {
            "status": "error",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": "Not connected to OBS Studio"
        }
    try:
        record_status = await obs_client.call('GetRecordStatus')
        if record_status['outputPaused']:
            message = "Video recording is already in pause state"
        else:
            await obs_client.call('PauseRecord')
            message = "Video recording paused successfully"
        response = {
            "status": "success",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": message,
            "data": {
                "datetime": datetime.datetime.now().isoformat()
            }
        }
    except Exception as e:
        response = {
            "status": "error",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": f"Failed to pause recording: {e}"
        }
    return response

async def handle_resume_recording(instance_id, command_uid):
    if obs_client is None or not obs_client.connected:
        return {
            "status": "error",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": "Not connected to OBS Studio"
        }
    try:
        record_status = await obs_client.call('GetRecordStatus')
        if not record_status['outputPaused']:
            message = "Video recording is currently not in pause state"
        else:
            await obs_client.call('ResumeRecord')
            message = "Video recording session resumed successfully"
        response = {
            "status": "success",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": message,
            "data": {
                "datetime": datetime.datetime.now().isoformat()
            }
        }
    except Exception as e:
        response = {
            "status": "error",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": f"Failed to resume recording: {e}"
        }
    return response

async def handle_save_image_snapshot(instance_id, command_uid):
    if obs_client is None or not obs_client.connected:
        return {
            "status": "error",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": "Not connected to OBS Studio"
        }
    try:
        filename = datetime.datetime.now().strftime("%Y%m%d%H%M%S") + '.png'
        file_path = os.path.join(SNAPSHOT_DIR, filename)
        await obs_client.call('SaveSourceScreenshot', {
            'sourceName': '',
            'imageFormat': 'png',
            'imageFilePath': file_path
        })
        response = {
            "status": "success",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": "Video image snapshot saved successfully",
            "data": {
                "file_path": file_path,
                "datetime": datetime.datetime.now().isoformat()
            }
        }
    except Exception as e:
        response = {
            "status": "error",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": f"Failed to save image snapshot: {e}"
        }
    return response

async def handle_start_replay_buffer(instance_id, command_uid):
    if obs_client is None or not obs_client.connected:
        return {
            "status": "error",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": "Not connected to OBS Studio"
        }
    try:
        await obs_client.call('StartReplayBuffer')
        clients[instance_id]['state']['replay_buffer_start_time'] = datetime.datetime.now()
        response = {
            "status": "success",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": "Video recording replay buffer started successfully",
            "data": {
                "datetime": datetime.datetime.now().isoformat()
            }
        }
    except Exception as e:
        response = {
            "status": "error",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": f"Failed to start replay buffer: {e}"
        }
    return response

async def handle_stop_replay_buffer(instance_id, command_uid):
    if obs_client is None or not obs_client.connected:
        return {
            "status": "error",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": "Not connected to OBS Studio"
        }
    try:
        await obs_client.call('StopReplayBuffer')
        start_time = clients[instance_id]['state'].get('replay_buffer_start_time')
        if start_time:
            duration = (datetime.datetime.now() - start_time).total_seconds()
            clients[instance_id]['state'].pop('replay_buffer_start_time', None)
        else:
            duration = 0
        response = {
            "status": "success",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": "Video recording replay buffer stopped successfully",
            "data": {
                "current_duration": duration,
                "datetime": datetime.datetime.now().isoformat()
            }
        }
    except Exception as e:
        response = {
            "status": "error",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": f"Failed to stop replay buffer: {e}"
        }
    return response

async def handle_save_replay_buffer(instance_id, command_uid):
    if obs_client is None or not obs_client.connected:
        return {
            "status": "error",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": "Not connected to OBS Studio"
        }
    try:
        await obs_client.call('SaveReplayBuffer')
        # The file path will be obtained from the ReplayBufferSaved event
        response = {
            "status": "success",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": "Video recording replay buffer save initiated successfully",
            "data": {
                "datetime": datetime.datetime.now().isoformat()
            }
        }
    except Exception as e:
        response = {
            "status": "error",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": f"Failed to save replay buffer: {e}"
        }
    return response

async def start_server():
    await connect_to_obs()  # Connect to OBS Studio before starting the server
    port = DEFAULT_WEBSOCKET_PORT
    started = False
    while not started:
        try:
            server = await websockets.serve(handle_client, "0.0.0.0", port)
            logging.info(f"WebSocket server started on port {port}")
            started = True
        except OSError:
            logging.warning(f"Port {port} unavailable, trying next port...")
            port += 1
    await server.wait_closed()

if __name__ == "__main__":
    try:
        asyncio.run(start_server())
    except KeyboardInterrupt:
        logging.info("Server shutdown requested by user.")
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
