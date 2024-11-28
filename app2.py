import asyncio
import json
import logging
import os
import datetime
import uuid
import obsws_python as obs
import websockets
import concurrent.futures
import functools
import traceback
import base64

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
executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)

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

def connect_to_obs(host=DEFAULT_OBS_HOST, port=DEFAULT_OBS_PORT, password=DEFAULT_OBS_PASSWORD):
    global obs_client
    try:
        obs_client = obs.ReqClient(host=host, port=port, password=password, timeout=10)
        logging.info(f"Connected to OBS Studio at {host}:{port}")
    except Exception as e:
        logging.error(f"Failed to connect to OBS Studio: {e}")
        obs_client = None

def disconnect_from_obs():
    global obs_client
    if obs_client:
        obs_client.disconnect()
        obs_client = None
        logging.info("Disconnected from OBS Studio.")

async def handle_client(websocket):
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
            response = handle_connect_websocket(instance_id, command_uid, parameters)
        elif command == 'DISCONNECT_WEBSOCKET':
            response = handle_disconnect_websocket(instance_id, command_uid)
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
        elif command == 'TEST_SAVE_IMAGE_SNAPSHOT':
            response = await test_save_image_snapshot()
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
            "command_uid": data.get('command_uid', ''),
            "instance_id": instance_id,
            "message": f"Error processing command: {str(e)}"
        }
        await clients[instance_id]['websocket'].send(json.dumps(error_response))

def handle_connect_websocket(instance_id, command_uid, parameters):
    ip_address = parameters.get('ip_address', DEFAULT_OBS_HOST)
    port = parameters.get('port', DEFAULT_OBS_PORT)
    password = parameters.get('password', DEFAULT_OBS_PASSWORD)
    # Reconnect to OBS with new parameters if needed
    connect_to_obs(ip_address, port, password)
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

def handle_disconnect_websocket(instance_id, command_uid):
    # Disconnect from OBS
    disconnect_from_obs()
    response = {
        "status": "success",
        "command_uid": command_uid,
        "instance_id": instance_id,
        "message": f"WebSocket instance id {instance_id} disconnected successfully"
    }
    return response

async def handle_start_recording(instance_id, command_uid):
    if obs_client is None:
        return {
            "status": "error",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": "Not connected to OBS Studio"
        }
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(executor, obs_client.start_record)
        clients[instance_id]['state']['recording_start_time'] = datetime.datetime.now()
        # Recording filename may not be available
        response = {
            "status": "success",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": "Video recording started successfully",
            "data": {
                # "file_path": "",  # Optional, remove or set to None
                "datetime": datetime.datetime.now().isoformat()
            }
        }
    except Exception as e:
        logging.error(f"Failed to start recording: {e}")
        response = {
            "status": "error",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": f"Failed to start recording: {e}"
        }
    return response

async def handle_stop_recording(instance_id, command_uid):
    if obs_client is None:
        return {
            "status": "error",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": "Not connected to OBS Studio"
        }
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(executor, obs_client.stop_record)
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
                # "file_path": "",  # Optional, remove or set to None
                "duration": duration,
                "datetime": datetime.datetime.now().isoformat()
            }
        }
    except Exception as e:
        logging.error(f"Failed to stop recording: {e}")
        response = {
            "status": "error",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": f"Failed to stop recording: {e}"
        }
    return response


async def handle_pause_recording(instance_id, command_uid):
    if obs_client is None:
        return {
            "status": "error",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": "Not connected to OBS Studio"
        }
    try:
        loop = asyncio.get_event_loop()
        record_status = await loop.run_in_executor(executor, obs_client.get_record_status)
        if not record_status.output_active:
            return {
                "status": "error",
                "command_uid": command_uid,
                "instance_id": instance_id,
                "message": "No active recording session to pause"
            }
        if record_status.output_paused:
            return {
                "status": "error",
                "command_uid": command_uid,
                "instance_id": instance_id,
                "message": "Video recording is already in pause state"
            }
        await loop.run_in_executor(executor, obs_client.pause_record)
        # Calculate total duration until now
        start_time = clients[instance_id]['state'].get('recording_start_time')
        if start_time:
            total_duration = (datetime.datetime.now() - start_time).total_seconds()
        else:
            total_duration = 0
        response = {
            "status": "success",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": "Video recording paused successfully",
            "data": {
                "total_duration": total_duration,
                "datetime": datetime.datetime.now().isoformat()
            }
        }
    except Exception as e:
        logging.error(f"Failed to pause recording: {e}")
        response = {
            "status": "error",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": f"Failed to pause recording: {e}"
        }
    return response

async def handle_resume_recording(instance_id, command_uid):
    if obs_client is None:
        return {
            "status": "error",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": "Not connected to OBS Studio"
        }
    try:
        loop = asyncio.get_event_loop()
        record_status = await loop.run_in_executor(executor, obs_client.get_record_status)
        if not record_status.output_active:
            return {
                "status": "error",
                "command_uid": command_uid,
                "instance_id": instance_id,
                "message": "No active recording session to resume"
            }
        if not record_status.output_paused:
            return {
                "status": "error",
                "command_uid": command_uid,
                "instance_id": instance_id,
                "message": "Video recording is currently not in pause state"
            }
        await loop.run_in_executor(executor, obs_client.resume_record)
        response = {
            "status": "success",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": "Video recording session resumed successfully",
            "data": {
                "datetime": datetime.datetime.now().isoformat()
            }
        }
    except Exception as e:
        logging.error(f"Failed to resume recording: {e}")
        response = {
            "status": "error",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": f"Failed to resume recording: {e}"
        }
    return response

async def handle_save_image_snapshot(instance_id, command_uid):
    if obs_client is None:
        return {
            "status": "error",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": "Not connected to OBS Studio"
        }
    try:
        loop = asyncio.get_event_loop()

        # Get the current program scene
        resp = await loop.run_in_executor(executor, obs_client.get_current_program_scene)
        scene_name = resp.current_program_scene_name

        # Ensure the snapshot directory exists
        if not os.path.exists(SNAPSHOT_DIR):
            os.makedirs(SNAPSHOT_DIR)

        # Define the file path where the image will be saved
        filename = datetime.datetime.now().strftime("%Y%m%d%H%M%S") + '.png'
        filepath = os.path.abspath(os.path.join(SNAPSHOT_DIR, filename))

        # Prepare the arguments for get_source_screenshot
        args = (
            scene_name,             # source_name
            'png',                  # image_format
            None,                   # image_width
            None,                   # image_height
            100                     # image_compression_quality
            # Exclude image_file_path if not accepted
        )

        # Get the screenshot
        screenshot_resp = await loop.run_in_executor(
            executor,
            functools.partial(obs_client.get_source_screenshot, *args)
        )

        # Access the base64 image data
        img_data_base64 = screenshot_resp.image_data

        if not img_data_base64:
            raise Exception("No image data received from OBS.")

        # Fix base64 padding if necessary
        img_data_base64 = img_data_base64.strip()
        missing_padding = len(img_data_base64) % 4
        if missing_padding:
            img_data_base64 += '=' * (4 - missing_padding)

        # Decode the base64 image data
        img_data = base64.b64decode(img_data_base64)

        # Save the image to a file
        with open(filepath, 'wb') as f:
            f.write(img_data)

        response = {
            "status": "success",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": "Image snapshot saved successfully",
            "data": {
                "file_path": filepath,
                "datetime": datetime.datetime.now().isoformat()
            }
        }
    except Exception as e:
        logging.error(f"Failed to save image snapshot: {e}")
        logging.error(traceback.format_exc())
        response = {
            "status": "error",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": f"Failed to save image snapshot: {e}"
        }
    return response

def test_save_image_snapshot():
    obs_client = obs.ReqClient(host='localhost', port=4455, password='')

    # Get the current program scene
    resp = obs_client.call('GetCurrentProgramScene')
    scene_name = resp['currentProgramSceneName']

    # Prepare the request data
    request_data = {
        'sourceName': scene_name,
        'imageFormat': 'png',
        'imageCompressionQuality': 100
    }

    # Send the request
    resp = obs_client.call('GetSourceScreenshot', request_data)

    # Check for errors
    if 'status' in resp and resp['status'] != 'ok':
        print(f"Failed to save snapshot: {resp.get('error', 'Unknown error')}")
        return

    # Get the base64 image data
    img_data_base64 = resp.get('imageData')

    if not img_data_base64:
        print("No image data received from OBS.")
        return

    # Decode the base64 image data
    img_data = base64.b64decode(img_data_base64)

    # Define the file path
    filepath = os.path.abspath('test_snapshot.png')

    # Save the image to a file
    with open(filepath, 'wb') as f:
        f.write(img_data)

    print(f"Snapshot saved successfully at {filepath}")

async def handle_start_replay_buffer(instance_id, command_uid):
    if obs_client is None:
        return {
            "status": "error",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": "Not connected to OBS Studio"
        }
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(executor, obs_client.start_replay_buffer)
        clients[instance_id]['state']['replay_buffer_start_time'] = datetime.datetime.now()
        response = {
            "status": "success",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": "Video recording replay buffer started successfully",
            "data": {
                "current_duration": 0,
                "datetime": datetime.datetime.now().isoformat()
            }
        }
    except Exception as e:
        logging.error(f"Failed to start replay buffer: {e}")
        response = {
            "status": "error",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": f"Failed to start replay buffer: {e}"
        }
    return response

async def handle_stop_replay_buffer(instance_id, command_uid):
    if obs_client is None:
        return {
            "status": "error",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": "Not connected to OBS Studio"
        }
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(executor, obs_client.stop_replay_buffer)
        start_time = clients[instance_id]['state'].get('replay_buffer_start_time')
        if start_time:
            current_duration = (datetime.datetime.now() - start_time).total_seconds()
            clients[instance_id]['state'].pop('replay_buffer_start_time', None)
        else:
            current_duration = 0
        response = {
            "status": "success",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": "Video recording replay buffer stopped successfully",
            "data": {
                "current_duration": current_duration,
                "datetime": datetime.datetime.now().isoformat()
            }
        }
    except Exception as e:
        logging.error(f"Failed to stop replay buffer: {e}")
        response = {
            "status": "error",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": f"Failed to stop replay buffer: {e}"
        }
    return response

async def handle_save_replay_buffer(instance_id, command_uid):
    if obs_client is None:
        return {
            "status": "error",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": "Not connected to OBS Studio"
        }
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(executor, obs_client.save_replay_buffer)
        # There is no direct way to get the file path or duration
        # after saving the replay buffer in OBS WebSockets
        # So we'll return placeholders or estimations
        current_duration = 0  # You might need to calculate this based on your settings
        file_path = ""  # OBS does not provide the saved file path
        response = {
            "status": "success",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": "Video recording replay buffer saved successfully",
            "data": {
                "file_path": file_path,
                "current_duration": current_duration,
                "datetime": datetime.datetime.now().isoformat()
            }
        }
    except Exception as e:
        logging.error(f"Failed to save replay buffer: {e}")
        response = {
            "status": "error",
            "command_uid": command_uid,
            "instance_id": instance_id,
            "message": f"Failed to save replay buffer: {e}"
        }
    return response

async def start_server():
    connect_to_obs()  # Connect to OBS Studio before starting the server
    port = DEFAULT_WEBSOCKET_PORT
    started = False
    while not started:
        try:
            async with websockets.serve(
                handle_client, "0.0.0.0", port, origins=None
            ):
                logging.info(f"WebSocket server started on port {port}")
                await asyncio.Future()  # Run forever
                started = True
        except OSError:
            logging.warning(f"Port {port} unavailable, trying next port...")
            port += 1

if __name__ == "__main__":
    try:
        asyncio.run(start_server())
    except KeyboardInterrupt:
        logging.info("Server shutdown requested by user.")
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
