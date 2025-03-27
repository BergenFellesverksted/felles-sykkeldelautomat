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
// Acceptable values: 'pickup' (default), 'dropoff' (or 'return'), or 'opening'
$action = isset($_GET['action']) ? strtolower($_GET['action']) : '';
if ($action === 'pickup') {
    $meta_key   = '_pickup_time';
    $action_text = "Pickup time";
} elseif ($action === 'dropoff' || $action === 'return') {
    $meta_key   = '_return_time';
    $action_text = "Return time";
} elseif ($action === 'opening') {
    $meta_key   = '_opening_time';
    $action_text = "Opening time";
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

if ($action === 'opening') {
    // For opening, if meta already exists, append new time to it.
    $select_sql = "SELECT meta_value FROM wpia_postmeta WHERE post_id = ? AND meta_key = ?";
    $stmt_select = $conn->prepare($select_sql);
    if (!$stmt_select) {
        echo json_encode(["error" => "Prepare failed: " . $conn->error]);
        exit();
    }
    $stmt_select->bind_param("is", $order_id, $meta_key);
    $stmt_select->execute();
    $stmt_select->bind_result($existing_meta_value);
    
    if ($stmt_select->fetch()) {
        // Record exists—append new timestamp.
        $stmt_select->close();
        $current = @unserialize($existing_meta_value);
        if ($current === false && $existing_meta_value !== 'b:0;') {
            // Not a serialized array, so convert it to an array.
            $current = [$existing_meta_value];
        }
        if (!is_array($current)) {
            $current = [$current];
        }
        // Append the new timestamp
        $current[] = $timestamp;
        // Serialize the updated array
        $new_meta_value = serialize($current);
        
        $update_sql = "UPDATE wpia_postmeta SET meta_value = ? WHERE post_id = ? AND meta_key = ?";
        $stmt_update = $conn->prepare($update_sql);
        if (!$stmt_update) {
            echo json_encode(["error" => "Prepare failed: " . $conn->error]);
            exit();
        }
        $stmt_update->bind_param("sis", $new_meta_value, $order_id, $meta_key);
        if ($stmt_update->execute()) {
            echo json_encode([
                "success"   => $action_text . " updated (appended)",
                "order_id"  => $order_id,
                "timestamp" => $timestamp
            ]);
        } else {
            echo json_encode(["error" => "Failed to update " . $action_text]);
            http_response_code(500);
        }
        $stmt_update->close();
    } else {
        // No record exists, so insert a new one with the timestamp in a serialized array.
        $stmt_select->close();
        $new_meta_value = serialize([$timestamp]);
        $insert_sql = "INSERT INTO wpia_postmeta (post_id, meta_key, meta_value) VALUES (?, ?, ?)";
        $stmt_insert = $conn->prepare($insert_sql);
        if (!$stmt_insert) {
            echo json_encode(["error" => "Prepare failed: " . $conn->error]);
            exit();
        }
        $stmt_insert->bind_param("iss", $order_id, $meta_key, $new_meta_value);
        if ($stmt_insert->execute()) {
            echo json_encode([
                "success"   => $action_text . " updated (inserted new)",
                "order_id"  => $order_id,
                "timestamp" => $timestamp
            ]);
        } else {
            echo json_encode(["error" => "Failed to update " . $action_text]);
            http_response_code(500);
        }
        $stmt_insert->close();
    }
} else {
    // For pickup and return actions, use the existing INSERT ON DUPLICATE KEY UPDATE method.
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
}

$conn->close();
?>
