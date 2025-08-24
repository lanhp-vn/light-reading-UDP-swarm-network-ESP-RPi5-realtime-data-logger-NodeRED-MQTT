# IoT Swarm System - Light Sensor Master-Slave Network

## Project Overview

This project implements a distributed IoT swarm system where multiple ESP8266 devices compete to become the "master" based on light sensor readings. The system consists of ESP8266 nodes with light sensors, a Raspberry Pi 5 coordinator, and a Node-RED dashboard for real-time monitoring and visualization.

## Demo Video

Watch the project demonstration: [IoT Swarm System Demo](https://youtu.be/Ev6wZzGC3QY)

## System Architecture

The system operates on a master-slave principle where:
- Multiple ESP8266 devices continuously read light sensor values
- The device with the lowest light reading becomes the master
- The master device communicates with a Raspberry Pi 5 coordinator
- Real-time data is visualized through Node-RED dashboard
- MQTT cloud communication enables remote monitoring

## Hardware Requirements

### ESP8266 Devices (Multiple)
- ESP8266 development boards (NodeMCU or similar)
- Photoresistor/LDR (Light Dependent Resistor)
- RGB LED (for visual feedback)
- On-board LED (for master status indication)
- Optional: LED bar graph (for enhanced visual feedback)

### Raspberry Pi 5
- Raspberry Pi 5 with WiFi capability
- MAX7219 LED matrix (8x8)
- Push button
- Yellow LED (for reset indication)
- GPIO connections

### Network Requirements
- WiFi network for device communication
- Internet connection for MQTT cloud communication

## Software Requirements

### ESP8266
- Arduino IDE
- ESP8266WiFi library
- WiFiUdp library

### Raspberry Pi 5
- Python 3.x
- Required Python packages:
  - gpiod
  - matplotlib
  - luma.led_matrix
  - paho-mqtt
  - socket
  - threading
  - statistics
  - collections

### Node-RED
- Node-RED installation
- MQTT nodes
- Dashboard nodes
- Chart nodes

## Development Order

To replicate this project, it's recommended to follow the development progression and read the project documentation in this order:

1. **Basic UDP Communication**: Start with [ligh-reading-UDP-ESP-RPi5](https://github.com/lanhp-vn/ligh-reading-UDP-ESP-RPi5) - Learn basic ESP8266 to Raspberry Pi UDP communication
2. **Enhanced Features**: Continue with [ligh-reading-UDP-ESP-RPi5](https://github.com/lanhp-vn/ligh-reading-UDP-ESP-RPi5) - Add LED matrix and visual feedback components  
3. **Complete Swarm System**: Finish with [light-reading-UDP-swarm-network-ESP-RPi5-realtime-data-logger](https://github.com/lanhp-vn/light-reading-UDP-swarm-network-ESP-RPi5-realtime-data-logger) - Implement the full master-slave swarm network with real-time data logging

## Installation and Setup

### 1. ESP8266 Setup

#### Basic ESP8266 Code (ESP_code.ino)
1. Open Arduino IDE
2. Install ESP8266 board support
3. Upload `ESP_code/ESP_code.ino` to your ESP8266 devices
4. Configure WiFi credentials in the code:
   ```cpp
   const char* ssid = "your_wifi_ssid";
   const char* password = "your_wifi_password";
   ```

#### Enhanced ESP8266 Code (ESP_LED_bar_graph.ino)
For devices with LED bar graph:
1. Upload `ESP_LED_bar_graph/ESP_LED_bar_graph.ino`
2. Connect LED bar graph to pins D2, D3, D5, D6, D7, D8
3. Ensure proper power supply for LED bar graph

### 2. Raspberry Pi 5 Setup

#### Install Required Packages
```bash
sudo apt update
sudo apt install python3-pip python3-gpiod
pip3 install matplotlib luma.led_matrix paho-mqtt
```

#### Hardware Connections
- MAX7219 LED Matrix: Connect to SPI pins (MOSI, MISO, CLK, CS)
- Push Button: Connect to GPIO 22
- Yellow LED: Connect to GPIO 26

#### Configure MQTT Settings
Edit `main.py` and update MQTT credentials:
```python
MQTT_URL = "your_mqtt_broker_url"
MQTT_USERNAME = "your_username"
MQTT_PASSWORD = "your_password"
```

#### Run the Coordinator
```bash
python3 main.py
```

### 3. Node-RED Setup

#### Install Node-RED
```bash
npm install -g node-red
```

#### Install Required Nodes
```bash
npm install node-red-dashboard
npm install node-red-contrib-mqtt-broker
```

#### Import Flow Configuration
1. Start Node-RED: `node-red`
2. Open Node-RED dashboard in browser
3. Import the `flows.json` file
4. Configure MQTT broker settings in the flow

## System Operation

### Master-Slave Logic
1. Each ESP8266 device reads light sensor values every 100ms
2. Devices broadcast their readings to other devices via UDP
3. The device with the lowest light reading becomes master
4. Master device communicates with Raspberry Pi coordinator
5. System automatically switches master when light conditions change

### Communication Protocol
- **ESP-to-ESP**: Uses UDP broadcast with delimiters `~~~` and `---`
- **Master-to-RPi**: Uses UDP with delimiters `+++` and `***`
- **RPi-to-Cloud**: Uses MQTT for remote monitoring
- **Reset Protocol**: Button press broadcasts reset to all devices

### Data Flow
1. Light sensors → ESP8266 devices
2. ESP8266 devices → UDP broadcast (peer-to-peer)
3. Master ESP8266 → Raspberry Pi (UDP)
4. Raspberry Pi → MQTT cloud
5. MQTT cloud → Node-RED dashboard

## Features

### Real-time Monitoring
- Live light sensor readings from all devices
- Master device identification and tracking
- Duration tracking for each master device
- Visual feedback through LEDs and LED matrix

### Data Visualization
- Real-time line chart of light sensor readings
- Bar chart showing master device durations
- Color-coded data based on device IDs
- Historical data tracking

### System Control
- Manual reset functionality via button press
- Automatic log file rotation
- System state persistence
- Remote monitoring capabilities

### Visual Feedback
- LED matrix showing real-time sensor data graph
- RGB LED brightness based on light readings
- On-board LED indicating master status
- LED bar graph showing light intensity levels

## Configuration

### Network Settings
- **UDP Port**: 4210 (default)
- **MQTT Broker**: HiveMQ Cloud (configurable)
- **WiFi**: Configure SSID and password in ESP8266 code

### Timing Parameters
- **Broadcast Interval**: 100ms (configurable)
- **Graph Update**: 4 seconds per column
- **Data Retention**: 30 seconds for real-time data
- **Log Rotation**: On button press

### Device Identification
- **Swarm ID**: Automatically assigned based on IP address last digit
- **Color Assignment**: Red, Green, Yellow for different devices
- **Master Tracking**: Real-time master device identification