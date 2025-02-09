void setup() {
  Serial.begin(9600);

  // Initialize relay pins as output and set them to OFF
  for (int pin = 22; pin <= 53; pin++) {
    pinMode(pin, OUTPUT);
    digitalWrite(pin, HIGH); // HIGH = relay OFF
  }
}

// Store activation timestamps, wait times, and durations for relays
unsigned long relayTimers[32] = {0};  // Activation time storage
unsigned long relayDurations[32] = {0};  // Stores duration for each relay
unsigned long relayWaitTimes[32] = {0};  // Stores wait time before activation
bool relayStates[32] = {false};  // Tracks if relay is on (true) or off (false)

void loop() {
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    
    if (command.startsWith("OPEN:")) {
      String relays = command.substring(5);
      int startIdx = 0;

      while (startIdx < relays.length()) {
        int endIdx = relays.indexOf(',', startIdx);
        if (endIdx == -1) endIdx = relays.length();

        String relayData = relays.substring(startIdx, endIdx);
        int firstColonIdx = relayData.indexOf(':');
        int secondColonIdx = relayData.indexOf(':', firstColonIdx + 1);

        if (firstColonIdx != -1 && secondColonIdx != -1) {
          int relayNum = relayData.substring(0, firstColonIdx).toInt();
          int waitTime = relayData.substring(firstColonIdx + 1, secondColonIdx).toInt();
          int duration = relayData.substring(secondColonIdx + 1).toInt();
          int relayPin;

          if (relayNum >= 1 && relayNum <= 16) {
            relayPin = 22 + (relayNum - 1) * 2; // Map relay 1-16 to 22-52 (even)
          } else if (relayNum >= 17 && relayNum <= 32) {
            relayPin = 23 + (relayNum - 17) * 2; // Map relay 17-32 to 23-53 (odd)
          } else {
            startIdx = endIdx + 1;
            continue; // Invalid relay number, skip
          }

          int relayIndex = relayNum - 1; // Map relayNum to array index
          relayWaitTimes[relayIndex] = millis() + waitTime;  // Store wait time
          relayDurations[relayIndex] = duration;  // Store duration
          relayStates[relayIndex] = false; // Set relay to pending activation
        }

        startIdx = endIdx + 1;
      }

      Serial.println("Relays queued for activation");
    }
  }

  // Check if any relay needs to be turned on
  for (int i = 0; i < 32; i++) {
    if (!relayStates[i] && millis() >= relayWaitTimes[i] && relayDurations[i] > 0) {
      int relayPin;
      if (i < 16) {
        relayPin = 22 + (i * 2);
      } else {
        relayPin = 23 + ((i - 16) * 2);
      }
      digitalWrite(relayPin, LOW); // Turn relay ON
      relayTimers[i] = millis();  // Store activation time
      relayStates[i] = true;
    }
  }

  // Check if any relay needs to be turned off
  for (int i = 0; i < 32; i++) {
    if (relayStates[i] && millis() - relayTimers[i] >= relayDurations[i]) {
      int relayPin;
      if (i < 16) {
        relayPin = 22 + (i * 2);
      } else {
        relayPin = 23 + ((i - 16) * 2);
      }
      digitalWrite(relayPin, HIGH); // Turn relay OFF
      relayStates[i] = false;
      relayTimers[i] = 0;  // Reset the timer
      relayDurations[i] = 0;  // Ensure relay does not turn on again
    }
  }
}
