<?php
require 'constants.php';
header("Content-Type: application/json");

// Authenticate using the API key.
if (!isset($_GET['api_key']) || $_GET['api_key'] !== API_KEY) {
    echo json_encode(["error" => "Unauthorized"]);
    http_response_code(403);
    exit();
}

$conn = new mysqli(DB_SERVER, DB_USER, DB_PASSWORD, DB_NAME);
if ($conn->connect_error) {
    echo json_encode(["error" => "Database connection error: " . $conn->connect_error]);
    exit();
}

// Select pending door commands from the table that are less than 60 seconds old.
$sql = "SELECT id, door_number, command, timestamp 
        FROM sykkeldelautomat_onlinerequests 
        WHERE executed = 0 
          AND timestamp >= NOW() - INTERVAL 60 SECOND
        ORDER BY timestamp ASC";
$result = $conn->query($sql);

$requests = [];
if ($result) {
    while ($row = $result->fetch_assoc()) {
        $requests[] = $row;
    }
}

echo json_encode($requests);
$conn->close();
?>
