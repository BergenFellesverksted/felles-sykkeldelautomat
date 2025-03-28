<?php
session_start();
include 'constants.php';

// Only allow if user is logged in
if (!(isset($_SESSION['logged_in']) && $_SESSION['logged_in'] === true)) {
    http_response_code(403);
    echo json_encode(["error" => "Unauthorized"]);
    exit();
}

// Validate the door parameter
if (!isset($_POST['door']) || !ctype_digit($_POST['door'])) {
    http_response_code(400);
    echo json_encode(["error" => "Invalid door parameter"]);
    exit();
}

$door = intval($_POST['door']);
if ($door < 1 || $door > 20) {
    http_response_code(400);
    echo json_encode(["error" => "Door number out of range"]);
    exit();
}

// Connect to the database
$conn = new mysqli(DB_SERVER, DB_USER, DB_PASSWORD, DB_NAME);
if ($conn->connect_error) {
    http_response_code(500);
    echo json_encode(["error" => "Database connection error"]);
    exit();
}

// Insert a new door command
$stmt = $conn->prepare("INSERT INTO sykkeldelautomat_onlinerequests (door_number, command, timestamp, executed) VALUES (?, 'open', NOW(), 0)");
if (!$stmt) {
    http_response_code(500);
    echo json_encode(["error" => "Prepare failed: " . $conn->error]);
    exit();
}
$stmt->bind_param("i", $door);
if ($stmt->execute()) {
    echo json_encode(["success" => "Door command inserted", "door" => $door]);
} else {
    http_response_code(500);
    echo json_encode(["error" => "Failed to insert door command"]);
}
$stmt->close();
$conn->close();
?>
