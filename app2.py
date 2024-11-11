import json
import logging
import websockets
import asyncio
import serial
import serial.tools.list_ports
from collections import defaultdict

# Global variables to manage connections and tasks
clients = set()
streaming_task = None
instances = defaultdict(dict)  # Dictionary to manage instances per client

# Define predefined_keys globally
predefined_keys = ["time", "date", "easting", "northing", "depth", "kp", "heading", "altitude", "dcc"]

# Global variable for the serial connection
serial_connection = None

async def handle_client(websocket, path):
    clients.add(websocket)
    logging.info(f"Client connected: {websocket.remote_address}")

    try:
        async for message in websocket:
            logging.info(f"Raw message received: {message}")
            try:
                command_data = json.loads(message)
                command = command_data.get("command")
                instance_id = command_data.get("instance_id")
                command_uid = command_data.get("command_uid")
                params = command_data.get("parameter", {})
                logging.info(f"Command received: {command} with params: {params}")
            except json.JSONDecodeError as e:
                logging.error(f"Failed to parse command: {e}")
                await websocket.send(json.dumps({
                    "status": "error",
                    "command_uid": command_uid,
                    "message": "Invalid JSON format"
                }))
                continue

            # Dispatch command to the appropriate handler
            if command == "CONNECT_WEBSOCKET":
                await handle_connect_websocket(websocket, command_uid, params)
            elif command == "DISCONNECT_WEBSOCKET":
                await handle_disconnect_websocket(websocket, command_uid, instance_id)
            elif command == "GET_COM_PORTS":
                await handle_get_com_ports(websocket, command_uid, instance_id)
            elif command == "OPEN_COM_PORT":
                await handle_open_com_port(websocket, command_uid, instance_id, params)
            elif command == "CLOSE_COM_PORT":
                await handle_close_com_port(websocket, command_uid, instance_id, params)
            elif command == "GET_DATA_STREAM":
                await handle_get_data_stream(websocket, command_uid, instance_id, params)
            elif command == "STOP_DATA_STREAM":
                await handle_stop_data_stream(websocket, command_uid, instance_id, params)
            elif command == "GET_COM_STATUS":
                await handle_get_com_status(websocket, command_uid, instance_id, params)
            elif command == "GET_PREDEFINED_KEYS":
                await handle_get_predefined_keys(websocket, command_uid, instance_id)
            elif command == "SET_DATA_BLOCKS":
                await handle_set_data_blocks(websocket, command_uid, instance_id, params)
            else:
                logging.warning(f"Unknown command received: {command}")
                await websocket.send(json.dumps({
                    "status": "error",
                    "command_uid": command_uid,
                    "message": "Unknown command received"
                }))
    except websockets.ConnectionClosed:
        logging.info(f"Connection closed: {websocket.remote_address}")
    finally:
        clients.remove(websocket)
        logging.info(f"Client disconnected: {websocket.remote_address}")
        # Cancel the streaming task if the client disconnects
        if streaming_task:
            streaming_task.cancel()
            streaming_task = None

async def handle_connect_websocket(websocket, command_uid, params):
    instance_id = f"{websocket.remote_address}-{len(clients)}"
    instances[websocket][instance_id] = {
        "ip_address": params.get("ip_address", "localhost"),
        "port": params.get("port", 8080)
    }
    logging.info(f"WebSocket connected with instance_id: {instance_id}")
    await websocket.send(json.dumps({
        "status": "success",
        "command_uid": command_uid,
        "message": "WebSocket connected successfully",
        "data": {
            "ip_address": instances[websocket][instance_id]["ip_address"],
            "port": instances[websocket][instance_id]["port"],
            "instance_id": instance_id
        }
    }))

async def handle_disconnect_websocket(websocket, command_uid, instance_id):
    if instance_id in instances[websocket]:
        del instances[websocket][instance_id]
        logging.info(f"WebSocket disconnected with instance_id: {instance_id}")
        await websocket.send(json.dumps({
            "status": "success",
            "command_uid": command_uid,
            "message": "WebSocket disconnected successfully"
        }))
    else:
        await websocket.send(json.dumps({
            "status": "error",
            "command_uid": command_uid,
            "message": "Invalid instance_id"
        }))

async def handle_get_com_ports(websocket, command_uid, instance_id):
    if instance_id in instances[websocket]:
        # Retrieve the list of available COM ports
        com_ports_list = list(serial.tools.list_ports.comports())
        com_ports = []
        for idx, port in enumerate(com_ports_list, start=1):
            com_ports.append({
                "index_no": idx,
                "name": port.device
            })
        
        logging.info(f"Returning COM ports for instance_id: {instance_id}")
        await websocket.send(json.dumps({
            "status": "success",
            "command_uid": command_uid,
            "message": "List of available COM ports",
            "instance_id": instance_id,
            "data": {"com_ports": com_ports}
        }))
    else:
        await websocket.send(json.dumps({
            "status": "error",
            "command_uid": command_uid,
            "message": "Invalid instance_id"
        }))

async def handle_open_com_port(websocket, command_uid, instance_id, params):
    global serial_connection
    if instance_id in instances[websocket]:
        index_no = params.get("index_no")
        baud_rate = params.get("baud_rate", 9600)
        data_bits = params.get("data_bits", 8)
        stop_bits = params.get("stop_bits", 1)
        parity = serial.PARITY_NONE  # Default parity

        # Retrieve the list of available COM ports
        com_ports_list = list(serial.tools.list_ports.comports())
        
        # Ensure the selected index is within the available range
        if 0 <= index_no - 1 < len(com_ports_list):
            selected_port = com_ports_list[index_no - 1].device
            
            # Check if the port is already open
            if serial_connection and serial_connection.is_open and serial_connection.port == selected_port:
                await websocket.send(json.dumps({
                    "status": "error",
                    "command_uid": command_uid,
                    "message": f"COM port {selected_port} is already opened or currently busy.",
                    "instance_id": instance_id
                }))
            else:
                try:
                    # Open the serial port with the provided settings
                    serial_connection = serial.Serial(
                        port=selected_port,
                        baudrate=baud_rate,
                        bytesize=data_bits,
                        stopbits=stop_bits,
                        parity=parity,
                        timeout=1
                    )
                    logging.info(f"COM port {selected_port} opened for instance_id: {instance_id}")
                    await websocket.send(json.dumps({
                        "status": "success",
                        "command_uid": command_uid,
                        "message": f"{selected_port} opened successfully",
                        "instance_id": instance_id,
                        "data": {
                            "index_no": index_no,
                            "name": selected_port
                        }
                    }))
                except serial.SerialException as e:
                    logging.error(f"Failed to open COM port {selected_port}: {e}")
                    await websocket.send(json.dumps({
                        "status": "error",
                        "command_uid": command_uid,
                        "message": f"Error: COM port {selected_port} is currently busy or unavailable.",
                        "instance_id": instance_id
                    }))
        else:
            await websocket.send(json.dumps({
                "status": "error",
                "command_uid": command_uid,
                "message": "Selected index is not available from the COM port list given.",
                "instance_id": instance_id
            }))
    else:
        await websocket.send(json.dumps({
            "status": "error",
            "command_uid": command_uid,
            "message": "Invalid instance_id"
        }))


async def handle_close_com_port(websocket, command_uid, instance_id, params):
    if instance_id in instances[websocket]:
        index_no = params.get("index_no")
        com_name = f"COM{index_no}"  # Example, replace with actual COM port handling

        if "com_port" in instances[websocket][instance_id] and instances[websocket][instance_id]["com_port"]["index_no"] == index_no:
            del instances[websocket][instance_id]["com_port"]
            logging.info(f"COM port {com_name} closed for instance_id: {instance_id}")
            await websocket.send(json.dumps({
                "status": "success",
                "command_uid": command_uid,
                "message": f"{com_name} closed successfully",
                "instance_id": instance_id,
                "data": {
                    "index_no": index_no,
                    "name": com_name
                }
            }))
        else:
            await websocket.send(json.dumps({
                "status": "error",
                "command_uid": command_uid,
                "message": f"{com_name} not open"
            }))
    else:
        await websocket.send(json.dumps({
            "status": "error",
            "command_uid": command_uid,
            "message": "Invalid instance_id"
        }))

# Dictionary to keep track of which instances are streaming data
streaming_instances = defaultdict(set)

async def handle_get_data_stream(websocket, command_uid, instance_id, params):
    global streaming_task
    if instance_id in instances[websocket]:
        index_no = params.get("index_no")
        com_name = f"COM{index_no}"  # Example, replace with actual COM port handling

        # Add this instance to the list of streaming instances for this COM port
        streaming_instances[com_name].add(instance_id)

        logging.info(f"Starting data stream for COM port {com_name}, instance_id: {instance_id}")

        # If a streaming task is already running, don't start another one
        if not streaming_task:
            async def stream_data():
                while True:
                    if serial_connection.in_waiting:
                        try:
                            # Read the data from the serial port
                            data = serial_connection.readline().decode('utf-8').strip()
                            logging.info(f"Raw data received: {data}")
                            
                            # Split the data and map to predefined keys
                            data_array = data.split(",")
                            data_list = [
                                {"name": predefined_keys[i] if i < len(predefined_keys) else f"datablock{i+1}", "value": value}
                                for i, value in enumerate(data_array)
                            ]

                            # Convert to JSON
                            data_json = json.dumps({
                                "status": "success",
                                "command_uid": command_uid,
                                "message": f"{com_name} returning data successfully",
                                "instance_id": instance_id,
                                "data": {
                                    "server_timestamp": "2024-08-28 14:00:00",
                                    "data_blocks": data_list
                                }
                            })

                            # Send data to all instances that are streaming this COM port
                            for ws, ws_instances in instances.items():
                                for ws_instance_id in ws_instances:
                                    if ws_instance_id in streaming_instances[com_name]:
                                        await ws.send(data_json)
                                        logging.info(f"Sent data to instance: {ws_instance_id}")
                        except Exception as e:
                            logging.error(f"Error processing data: {e}")
                            for ws, ws_instances in instances.items():
                                for ws_instance_id in ws_instances:
                                    if ws_instance_id in streaming_instances[com_name]:
                                        await ws.send(f"Error: {e}")
                    
                    await asyncio.sleep(0.1)

            streaming_task = asyncio.create_task(stream_data())
    else:
        await websocket.send(json.dumps({
            "status": "error",
            "command_uid": command_uid,
            "message": "Invalid instance_id"
        }))


async def handle_stop_data_stream(websocket, command_uid, instance_id, params):
    global streaming_task
    if instance_id in instances[websocket]:
        index_no = params.get("index_no")
        com_name = f"COM{index_no}"

        # Remove this instance from the list of streaming instances for this COM port
        if instance_id in streaming_instances[com_name]:
            streaming_instances[com_name].remove(instance_id)
            logging.info(f"Stopped data stream for instance_id: {instance_id}")

        # If no instances are streaming this COM port, stop the streaming task
        if not streaming_instances[com_name]:
            if streaming_task:
                streaming_task.cancel()
                streaming_task = None
                logging.info(f"Data streaming task has been cancelled for {com_name}")

        await websocket.send(json.dumps({
            "status": "success",
            "command_uid": command_uid,
            "message": f"Data stream on {com_name} has stopped returning data successfully",
            "instance_id": instance_id
        }))
    else:
        await websocket.send(json.dumps({
            "status": "error",
            "command_uid": command_uid,
            "message": "Invalid instance_id"
        }))

async def handle_get_com_status(websocket, command_uid, instance_id, params):
    global serial_connection
    if instance_id in instances[websocket]:
        index_no = params.get("index_no")
        
        # Retrieve the list of available COM ports
        com_ports_list = list(serial.tools.list_ports.comports())

        # Ensure the selected index is within the available range
        if 0 <= index_no - 1 < len(com_ports_list):
            selected_port = com_ports_list[index_no - 1].device
            
            if serial_connection and serial_connection.is_open and serial_connection.port == selected_port:
                status = "open"
            else:
                status = "closed"
        else:
            selected_port = f"COM{index_no}"  # This should be a fallback, normally unreachable if the index is valid
            status = "not available"

        com_status = [{"index_no": index_no, "name": selected_port, "status": status}]

        logging.info(f"Returning COM status for instance_id: {instance_id}")
        await websocket.send(json.dumps({
            "status": "success",
            "command_uid": command_uid,
            "message": "COM port status returned successfully",
            "instance_id": instance_id,
            "data": com_status
        }))
    else:
        await websocket.send(json.dumps({
            "status": "error",
            "command_uid": command_uid,
            "message": "Invalid instance_id"
        }))


async def handle_get_predefined_keys(websocket, command_uid, instance_id):
    if instance_id in instances[websocket]:
        global predefined_keys

        logging.info(f"Returning predefined keys for instance_id: {instance_id}")
        await websocket.send(json.dumps({
            "status": "success",
            "command_uid": command_uid,
            "message": "Predefined keys are returning successfully",
            "instance_id": instance_id,
            "data": predefined_keys
        }))
    else:
        await websocket.send(json.dumps({
            "status": "error",
            "command_uid": command_uid,
            "message": "Invalid instance_id"
        }))

async def handle_set_data_blocks(websocket, command_uid, instance_id, params):
    if instance_id in instances[websocket]:
        data_blocks = params.get("data_blocks", [])
        global predefined_keys

        # Clear the existing predefined_keys
        predefined_keys.clear()

        # Append the new keys provided by the client
        for block in data_blocks:
            predefined_keys.append(block["name"])

        logging.info(f"Updated predefined keys: {predefined_keys}")

        await websocket.send(json.dumps({
            "status": "success",
            "command_uid": command_uid,
            "message": "Data block settings applied successfully",
            "instance_id": instance_id,
            "data": data_blocks
        }))
    else:
        await websocket.send(json.dumps({
            "status": "error",
            "command_uid": command_uid,
            "message": "Invalid instance_id"
        }))

# WebSocket server start code
async def main():
    async with websockets.serve(handle_client, "localhost", 8080):
        logging.info("WebSocket server started on ws://localhost:8080")
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())