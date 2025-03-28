<?php
require 'constants.php';
header("Content-Type: application/json");

// Authenticate using the API key.
if (!isset($_POST['api_key']) || $_POST['api_key'] !== API_KEY) {
    echo json_encode(["error" => "Unauthorized"]);
    http_response_code(403);
    exit();
}

// Validate request_id parameter.
if (!isset($_POST['request_id']) || !ctype_digit($_POST['request_id'])) {
    echo json_encode(["error" => "Invalid request_id"]);
    http_response_code(400);
    exit();
}

$request_id = intval($_POST['request_id']);

$conn = new mysqli(DB_SERVER, DB_USER, DB_PASSWORD, DB_NAME);
if ($conn->connect_error) {
    echo json_encode(["error" => "Database connection error: " . $conn->connect_error]);
    exit();
}

$stmt = $conn->prepare("UPDATE sykkeldelautomat_onlinerequests SET executed = 1 WHERE id = ?");
$stmt->bind_param("i", $request_id);

if ($stmt->execute()) {
    echo json_encode(["success" => "Request marked as executed"]);
} else {
    http_response_code(500);
    echo json_encode(["error" => "Failed to update request"]);
}

$stmt->close();
$conn->close();
?>
