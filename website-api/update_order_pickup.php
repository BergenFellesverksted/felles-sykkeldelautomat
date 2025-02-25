<?php
date_default_timezone_set('Europe/Oslo');
require 'constants.php';

// Set the correct headers for JSON output
header("Content-Type: application/json");

// Check if API key is provided in the request
if (!isset($_GET['api_key']) || $_GET['api_key'] !== API_KEY) {
    echo json_encode(["error" => "Unauthorized: Invalid API Key"]);
    http_response_code(403);
    exit();
}

// Check if order_id is provided
if (!isset($_GET['order_id']) || empty($_GET['order_id'])) {
    echo json_encode(["error" => "Missing order_id"]);
    http_response_code(400);
    exit();
}

// Determine which timestamp to update based on GET parameter 'action'
// Acceptable values: 'pickup' (default) or 'dropoff' (or 'return')
$action = isset($_GET['action']) ? strtolower($_GET['action']) : 'pickup';
if ($action === 'pickup') {
    $meta_key   = '_pickup_time';
    $action_text = "Pickup time";
} elseif ($action === 'dropoff' || $action === 'return') {
    $meta_key   = '_return_time';
    $action_text = "Return time";
} else {
    echo json_encode(["error" => "Invalid action"]);
    http_response_code(400);
    exit();
}

$conn = new mysqli(DB_SERVER, DB_USER, DB_PASSWORD, DB_NAME);

// Check connection
if ($conn->connect_error) {
    echo json_encode(["error" => "Failed to connect to MySQL: " . $conn->connect_error]);
    exit();
}

$order_id  = intval($_GET['order_id']);

// Use provided action_time if available, otherwise use the current time.
if (isset($_GET['action_time']) && !empty($_GET['action_time'])) {
    $timestamp = $_GET['action_time'];
} else {
    $timestamp = date("Y-m-d H:i:s");
}

// SQL Query to insert or update the meta key (pickup or dropoff time)
$insert_meta_sql = "
INSERT INTO wpia_postmeta (post_id, meta_key, meta_value) 
VALUES (?, ?, ?) 
ON DUPLICATE KEY UPDATE meta_value = VALUES(meta_value);
";

$stmt_meta = $conn->prepare($insert_meta_sql);
if (!$stmt_meta) {
    echo json_encode(["error" => "Prepare failed: " . $conn->error]);
    exit();
}
$stmt_meta->bind_param("iss", $order_id, $meta_key, $timestamp);

if ($stmt_meta->execute()) {
    echo json_encode([
        "success"   => $action_text . " updated",
        "order_id"  => $order_id,
        "timestamp" => $timestamp
    ]);
} else {
    echo json_encode(["error" => "Failed to update " . $action_text]);
    http_response_code(500);
}

$stmt_meta->close();
$conn->close();
?>
