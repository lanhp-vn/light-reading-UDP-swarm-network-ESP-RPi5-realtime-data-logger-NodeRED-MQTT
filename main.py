import gpiod
import time
import socket
import threading
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from datetime import datetime, timedelta
from luma.led_matrix.device import max7219
from luma.core.interface.serial import spi, noop
from luma.core.render import canvas
from statistics import mean
from collections import defaultdict
from collections import deque
import paho.mqtt.client as mqtt
import json

# MQTT Configuration
MQTT_URL = "35097c4b385744609a0a8471720c551d.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USERNAME = "lanhp"
MQTT_PASSWORD = "Lanlanlan@300701"
MQTT_TOPIC_READING = "analogReading"
MQTT_TOPIC_RESET = "resetRequest"
MQTT_TOPIC_DURATION = "masterDuration"

# MQTT Client Setup
mqtt_client = mqtt.Client()
mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
mqtt_client.tls_set()  # Enable TLS encryption

try:
    mqtt_client.connect(MQTT_URL, MQTT_PORT, 60)
    print(f"Connected to MQTT broker at {MQTT_URL}:{MQTT_PORT}")
except Exception as e:
    print(f"Failed to connect to MQTT broker: {e}")
    exit(1)

# Constants for GPIO pins and communication protocol
BUTTON_PIN = 22  # GPIO pin for the button
YELLOW_LED_PIN = 26  # GPIO pin for yellow LED
RPi_startBit = "+++"  # Start delimiter for messages
RPi_endBit = "***"  # End delimiter for messages
localPort = 4210  # Port to listen for incoming UDP messages

# Initialize GPIO chip and request lines for button and LEDs
chip = gpiod.Chip('gpiochip4')
button_line = chip.get_line(BUTTON_PIN)
button_line.request(consumer="Button", type=gpiod.LINE_REQ_DIR_IN)
yellow_led_line = chip.get_line(YELLOW_LED_PIN)
yellow_led_line.request(consumer="Yellow_LED", type=gpiod.LINE_REQ_DIR_OUT, default_vals=[0])

# Set up UDP socket for communication and enable broadcast mode
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(('', localPort))
sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

print(f"Listening for incoming messages on port {localPort}...")

# Global variables
PREV_BUTTON_STATE = 0
RESET_REQUEST = False  # Tracks if a reset request is active
STOP_THREADS = False
analog_readings = []  # Store readings with timestamps
swarm_colors = {}  # To store assigned colors for each Swarm ID
CURRENT_MASTER = None  # To track the current master Swarm ID
master_durations = defaultdict(int)  # To track how long each Swarm ID has been master
master_logs = defaultdict(list)  # Raw data logs for each master
LOG_FILE = None
start_time = datetime.now()

# Graph settings
MATRIX_WIDTH = 8  # Number of columns
MATRIX_HEIGHT = 8  # Number of rows (LEDs per column)
UPDATE_INTERVAL = 4  # Seconds per column
BUFFER_SIZE = int(32 / UPDATE_INTERVAL)  # ~30 seconds of data
reading_buffer = deque(maxlen=BUFFER_SIZE) # Queue to store recent readings
for _ in range(BUFFER_SIZE):
    reading_buffer.append(0)  # Initialize with zeros
current_window_ledMatrix = [] # Temporary storage for readings in the current 4-second window for LED Matrix display
# Create LED matrix device
serial = spi(port=0, device=0, gpio=noop())
device = max7219(serial, width=MATRIX_WIDTH, height=MATRIX_HEIGHT, rotate=2)

def map_reading_to_height(reading, max_value=1023):
    """
    Map analog reading (0-1023) to height on the LED matrix (0-7).
    """
    return min(MATRIX_HEIGHT - 1, int((reading / max_value) * (MATRIX_HEIGHT - 1)))

def update_graph(device, readings):
    """
    Update the LED matrix to display the graph of readings, mirrored horizontally.
    """
    with canvas(device) as draw:
        for x, reading in enumerate(readings):
            # Reverse the x-coordinate to mirror horizontally
            mirrored_x = MATRIX_WIDTH - 1 - x
            height = map_reading_to_height(reading)
            for y in range(height + 1):
                draw.point((mirrored_x, MATRIX_HEIGHT - 1 - y), fill="white")

def get_new_log_file():
    """Creates a new log file with the current timestamp."""
    global LOG_FILE
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    LOG_FILE = f"master_log_{timestamp}.txt"
    print(f"New log file created: {LOG_FILE}")


def save_current_logs():
    """Save the logs to the current log file."""
    global LOG_FILE, master_durations, master_logs
    if not LOG_FILE:
        return

    with open(LOG_FILE, 'w') as log_file:
        log_file.write(f"Log File Created: {datetime.now()}\n\n")
        log_file.write("Masters Summary:\n")
        for swarm_id, duration in master_durations.items():
            log_file.write(f"Swarm ID: {swarm_id}, Total Master Duration: {duration} seconds\n")
                
        log_file.write("\nRaw Data Logs:\n")
        for ip, logs in master_logs.items():
            log_file.write(f"\nIP: {ip}\n")
            log_file.write('\n'.join(logs) + '\n')

    print(f"Logs saved to {LOG_FILE}")


def reset_system():
    """Function to handle reset message."""
    global RESET_REQUEST, swarm_colors, CURRENT_MASTER, master_durations, LOG_FILE, analog_readings, current_window_ledMatrix, reading_buffer, device

    RESET_REQUEST = True  # Prevents other actions during reset

    # Broadcast reset request message to all devices
    reset_message = f"{RPi_startBit}RESET_REQUESTED{RPi_endBit}"
    print(f"Button is pressed. Broadcast: {reset_message}")
    sock.sendto(reset_message.encode('utf-8'), ('<broadcast>', localPort))

    # Reset swarm colors, master tracking, durations, and analog readings
    swarm_colors = {}
    CURRENT_MASTER = None
    master_durations.clear()
    analog_readings.clear()

    # Clear readings for LED Matrix
    current_window_ledMatrix = []
    for _ in range(BUFFER_SIZE):
        reading_buffer.append(0)  # Initialize with zeros
    update_graph(device, list(reading_buffer))

    mqtt_client.publish(MQTT_TOPIC_RESET, json.dumps(1))
    print(f"Published to MQTT: RESET REQUEST")

    # Light up yellow LED for 3 seconds to indicate reset
    yellow_led_line.set_value(1)
    time.sleep(3)
    yellow_led_line.set_value(0)

    RESET_REQUEST = False


def listen_for_messages():
    """Function to listen for UDP messages, process sensor data, and control the LED Matrix."""
    global RESET_REQUEST, STOP_THREADS, CURRENT_MASTER, LOG_FILE, current_window_ledMatrix

    last_update_time_MQTT = time.time()

    while not STOP_THREADS:
        if not RESET_REQUEST:  # Skip listening if reset is active
            try:
                message, address = sock.recvfrom(1024)
            except socket.error:
                break  # Break if socket is closed

            message = message.decode('utf-8')

            # Check for message start and end delimiters
            if message.startswith(RPi_startBit) and message.endswith(RPi_endBit):
                data = message[len(RPi_startBit):-len(RPi_endBit)]
                ip = address[0]

                if ',' in data:
                    swarm_id, analog_reading = data.split(',')
                else:
                    continue

                current_window_ledMatrix.append(int(analog_reading))

                # Record the reading with its timestamp
                timestamp = datetime.now()
                analog_readings.append((timestamp, int(analog_reading)))                                                                                                                                                                                                                                                                                                                                                         

                log_entry = f"Time: {timestamp}, Swarm ID: {swarm_id}, Reading: {analog_reading}"
                master_logs[ip].append(log_entry)
                # print(f"Received from {ip}: {log_entry}")

                # Skip processing if message is reset request confirmation
                if data == "RESET_REQUESTED":
                    continue

                # Remove readings older than 30 seconds
                cutoff_time = datetime.now() - timedelta(seconds=30)
                analog_readings[:] = [(t, r) for t, r in analog_readings if t >= cutoff_time]

                # Assign color to Swarm ID if it's not already assigned
                if swarm_id not in swarm_colors:
                    if len(swarm_colors) == 0:
                        swarm_colors[swarm_id] = 'red'
                    elif len(swarm_colors) == 1:
                        swarm_colors[swarm_id] = 'green'
                    else:
                        swarm_colors[swarm_id] = 'yellow'

                # # Publish the data to the MQTT broker
                # payload = {
                #     "swarmID": swarm_id,
                #     "analogReading": analog_reading
                # }

                # # Convert to JSON string
                # payload_json = json.dumps(payload)
                
                if time.time() - last_update_time_MQTT >= 1:
                    mqtt_client.publish(MQTT_TOPIC_READING, json.dumps(int(analog_reading)))
                    print(f"Published to MQTT: {analog_reading}")
            
                    last_update_time_MQTT = time.time()

                if CURRENT_MASTER != swarm_id:
                    CURRENT_MASTER = swarm_id
                    print(f"New master detected: {ip}")

                master_durations[swarm_id] += 1

def ledMatrix_display():
    global RESET_REQUEST, STOP_THREADS, MATRIX_WIDTH, MATRIX_HEIGHT, UPDATE_INTERVAL, current_window_ledMatrix, reading_buffer, serial, device
    
    last_update_time_ledMatrix = time.time()

    while not STOP_THREADS:
        # Update the graph every 4 seconds
        if time.time() - last_update_time_ledMatrix >= UPDATE_INTERVAL:
            if current_window_ledMatrix:
                # Calculate the average of the current window
                avg_reading_ledMatrix = int(mean(current_window_ledMatrix))
                current_window_ledMatrix = []  # Clear the current window
                
                # Add the averaged reading to the buffer
                reading_buffer.append(avg_reading_ledMatrix)
                
                # Update the graph
                update_graph(device, list(reading_buffer))
            
            last_update_time_ledMatrix = time.time()


def monitor_button():
    """Monitor the button state and handle resets and log rotation on press."""
    global PREV_BUTTON_STATE, STOP_THREADS

    while not STOP_THREADS:
        button_state = button_line.get_value()
        if button_state == 1 and PREV_BUTTON_STATE == 0:  # Button press detected
            save_current_logs()  # Save existing logs
            get_new_log_file()  # Start a new log file
            reset_system()  # Call reset if button is pressed

        PREV_BUTTON_STATE = button_state
        time.sleep(0.1)


def plot_graph():
    global RESET_REQUEST, STOP_THREADS, analog_readings, CURRENT_MASTER, swarm_colors, master_durations

    bar_data = defaultdict(int)  # Bar data for master durations
    last_update_time_MQTT = time.time()

    while not STOP_THREADS:
        # Initialize the figure and subplots
        fig, (ax1, ax2) = plt.subplots(2, 1)
        fig.subplots_adjust(hspace=0.5)

        # Configure line graph (real-time readings)
        ax1.set_ylim(0, 1023)
        ax1.set_xlabel('Time (seconds ago)')
        ax1.set_ylabel('Analog Reading')
        ax1.set_title('Real-time Analog Readings (last 30 seconds)')
        line, = ax1.plot([], [], color='blue', lw=2)

        # Configure bar graph (master durations)
        ax2.set_ylim(0, 30)
        ax2.set_xlabel('Swarm ID')
        ax2.set_ylabel('Duration (seconds)')
        ax2.set_title('Master Device Durations (total time)')

        def update_plot(frame):
            nonlocal line

            # Filter readings within the last 30 seconds
            cutoff_time = datetime.now() - timedelta(seconds=30)
            recent_readings = [(t, r) for t, r in analog_readings if t >= cutoff_time]

            # Prepare x and y data for plotting
            x_data = [(datetime.now() - t).total_seconds() for t, r in recent_readings]
            y_data = [r for t, r in recent_readings]

            # Update line color based on current master
            if CURRENT_MASTER:
                color = swarm_colors.get(CURRENT_MASTER, 'blue')
                line.set_color(color)

                # Update master duration
                bar_data[CURRENT_MASTER] += 1

            line.set_data(x_data, y_data)
            ax1.set_xlim(max(x_data, default=0) + 1, 0)  # Dynamic x-axis (last 30 seconds)
            return line,

        def update_bar(frame):
            ax2.clear()
            ax2.bar(master_durations.keys(), master_durations.values(), 
                    color=[swarm_colors.get(sid, 'blue') for sid in master_durations.keys()])
            ax2.set_ylim(0, max(master_durations.values(), default=30))
            ax2.set_xlabel('Swarm ID')
            ax2.set_ylabel('Duration (seconds)')
            ax2.set_title('Master Device Durations (total time)')

        # Setup animations
        ani = FuncAnimation(fig, update_plot, interval=1000)
        ani2 = FuncAnimation(fig, update_bar, interval=1000)
        plt.show()
        
        if time.time() - last_update_time_MQTT >= 1:
            for swarm_id, duration in master_durations.items():
                # Publish the data to the MQTT broker
                payload = {
                    "swarmID": swarm_id,
                    "duration": duration
                }
                
            mqtt_client.publish(MQTT_TOPIC_DURATION, json.dumps(payload))
            print(f"Published to MQTT: {payload}")
    
            last_update_time_MQTT = time.time()

        # Check for reset
        while RESET_REQUEST:
            plt.close(fig)  # Close the current figure
            x_data = list(range(30))  # Reset X data
            y_data = [0] * 30  # Reset Y data
            bar_data.clear()  # Reset bar data
            master_durations.clear()  # Reset master durations
            break  # Exit the inner loop to reinitialize the graph


# Main entry point to start button monitoring, message listening, and graph display
if __name__ == "__main__":
    try:
        get_new_log_file()  # Initialize the first log file

        # Create separate threads for button monitoring, message reception, and plotting
        button_thread = threading.Thread(target=monitor_button)
        receive_thread = threading.Thread(target=listen_for_messages)
        graph_thread = threading.Thread(target=plot_graph)
        ledMatrix_thread = threading.Thread(target=ledMatrix_display)

        # Start the threads
        button_thread.start()
        receive_thread.start()
        graph_thread.start()
        ledMatrix_thread.start()

        # Keep the program running by joining the threads
        button_thread.join()
        receive_thread.join()
        graph_thread.join()
        ledMatrix_thread.join()

    except KeyboardInterrupt:
        print("\nKeyboard interrupt detected. Shutting down...")
        STOP_THREADS = True  # Signal threads to stop
        sock.close()  # Close the socket
        button_thread.join()  # Ensure the threads are properly stopped
        receive_thread.join()
        ledMatrix_thread.join()
        graph_thread.join()
        print("Shutdown complete.")
