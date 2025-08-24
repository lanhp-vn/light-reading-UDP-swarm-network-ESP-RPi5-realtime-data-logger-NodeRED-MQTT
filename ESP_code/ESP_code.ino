#include <ESP8266WiFi.h>
#include <WiFiUdp.h>

// Pins for components
#define PHOTORESISTOR_PIN A0           // Analog pin for light sensor
#define ONBOARD_LED 16                // On-board LED for signal indication
#define RGB_LED D4

// WiFi credentials and UDP communication settings
const char* ssid = "zentirot";              // Network SSID
const char* password = "Lanlanlan";    // Network password
const unsigned int localPort = 4210;   // Port for receiving UDP messages
const IPAddress broadcastIP(255, 255, 255, 255); // Broadcast IP for UDP communication
WiFiUDP udp;                           // UDP instance for network communication

// Communication timing parameters
unsigned long lastReceivedTime = 0;    // Tracks time of the last received message
const unsigned long silentTime = 100;  // Broadcast if no message is received within 200 ms

// Device-specific variables
int swarmID = -1;                      // Unique ID based on IP address
int analogValue = 0;                   // Stores light sensor reading
bool isMaster = true;                  // Status flag for Master device
String role = "Master";                // Role of this ESP8266 (Master or Slave)

// Array to store readings from other devices by Swarm ID
int readings[10] = {-1};               // Initialize readings array with invalid (-1) values

// Delimiters for packet structure
const String ESP_startBit = "~~~";     // Start delimiter for ESP messages
const String ESP_endBit = "---";       // End delimiter for ESP messages
const String RPi_startBit = "+++";     // Start delimiter for RPi messages
const String RPi_endBit = "***";       // End delimiter for RPi messages


// Function to control the brightness of an LED based on an analog input value
void ledBright(int ledPin, int analogValue) {
  // Calculate the brightness level for the LED based on the analog input
  // The formula scales the input value and adjusts it with a constant offset
  int led_brightness = 0.25 * analogValue - 6;

  // Set the LED brightness by writing the calculated value to the specified pin
  // The value should be between 0 and 255 for the analogWrite function to work correctly
  analogWrite(ledPin, led_brightness);
}


// Setup function to initialize WiFi, LEDs, and calculate slope-intercept for LED intervals
void setup() {
  /* Input: None
  
     Process: Initializes Serial communication, WiFi connection, LED pin modes, and 
              UDP communication. Assigns a unique swarmID based on the last digit of IP.
              Also calculates slope and intercept for flashing intervals.
              
     Output: Sets up the device with connected WiFi, UDP, and initialized LEDs.
  */
  Serial.begin(115200);

  // Initialize LED pins
  pinMode(ONBOARD_LED, OUTPUT);
  pinMode(RGB_LED, OUTPUT);
  digitalWrite(ONBOARD_LED, HIGH);
  digitalWrite(RGB_LED, LOW);

  // Connect to WiFi
  WiFi.begin(ssid, password);
  Serial.print("Connecting to WiFi...");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected");
  Serial.print("IP address: ");
  Serial.println(WiFi.localIP());

  // Assign a swarm ID based on the last digit of IP address
  IPAddress ip = WiFi.localIP();
  swarmID = ip[3] % 10;
  Serial.print("Swarm ID assigned: ");
  Serial.println(swarmID);

  // Begin UDP communication
  udp.begin(localPort);
  Serial.printf("Listening on UDP port %d\n", localPort);
}

// Main loop to handle LEDs, broadcasting, and receiving messages
void loop() {

  ledBright(RGB_LED, analogValue);
  
  // Light up the on-board LED if this device is the Master
  if (isMaster) {
    digitalWrite(ONBOARD_LED, LOW);
  } else {
    digitalWrite(ONBOARD_LED, HIGH);  // Turn off LEDs if not Master
  }

  // Check if any packet has been received
  int packetSize = udp.parsePacket();
  if (packetSize) {
    char incomingPacket[255];
    int len = udp.read(incomingPacket, 255);
    if (len > 0) {
      incomingPacket[len] = '\0';
    }

    // Convert incoming packet to String for easier manipulation
    String packetStr = String(incomingPacket);

    // Process ESP-to-ESP message format
    if (packetStr.startsWith(ESP_startBit) && packetStr.endsWith(ESP_endBit)) {
      String data = packetStr.substring(ESP_startBit.length(), packetStr.length() - ESP_endBit.length());
      Serial.printf("Received packet: %s\n", data);
      int receivedSwarmID, receivedReading;
      sscanf(data.c_str(), "%d,%d", &receivedSwarmID, &receivedReading);

      // Store the reading in the array and update last received time
      readings[receivedSwarmID] = receivedReading;
      lastReceivedTime = millis();
    }

    // Process RPi reset message format
    if (packetStr.startsWith(RPi_startBit) && packetStr.endsWith(RPi_endBit)) {
      String data = packetStr.substring(RPi_startBit.length(), packetStr.length() - RPi_endBit.length());
      if (data == "RESET_REQUESTED") {
        digitalWrite(RGB_LED, LOW);
        digitalWrite(ONBOARD_LED, HIGH);
        isMaster = true;
        Serial.println("RESET REQUESTED BY RPI5");
        delay(3000);  // Hold reset state for 3 seconds
      }
    }
  }

  // Check if silent time has elapsed and broadcast reading if needed
  if (millis() - lastReceivedTime > silentTime) {
    analogValue = analogRead(PHOTORESISTOR_PIN);

    // Broadcast this device's reading to other devices
    String message = ESP_startBit + String(swarmID) + "," + String(analogValue) + ESP_endBit;
    Serial.printf("Broadcasting message: %s\n", message.c_str());
    udp.beginPacket(broadcastIP, localPort);
    udp.write(message.c_str());
    udp.endPacket();
    lastReceivedTime = millis();

    // Determine if this device is the Master
    isMaster = true;
    for (int i = 0; i < 10; i++) {
      if (i != swarmID && readings[i] >= 0 && readings[i] > analogValue) {
        isMaster = false;
        break;
      }
    }

    // Update role and broadcast to RPi if Master
    if (isMaster) {
      role = "Master";
      String masterMessage = RPi_startBit + String(swarmID) + "," + String(analogValue) + RPi_endBit;
      Serial.printf("Master to RPi: %s\n", message.c_str());
      udp.beginPacket(broadcastIP, localPort);
      udp.write(masterMessage.c_str());
      udp.endPacket();
    } else {
      role = "Slave";
    }
    Serial.printf("Current role: %s (Reading: %d)\n", role.c_str(), analogValue);
    Serial.println("");
  }
}
