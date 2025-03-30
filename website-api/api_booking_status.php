<?php
// api_booking_status.php
// Used for visulizing same day availibility for each Bookly item in the Woocommerse store

header('Content-Type: application/json; charset=utf-8');
date_default_timezone_set('Europe/Oslo');

/** Ensure WordPress bootstrap has loaded */
require './wp-load.php';
require './constants.php';

// Connect with mysqli
$mysqli = new mysqli(DB_SERVER, DB_USER, DB_PASSWORD, DB_NAME);

if ($mysqli->connect_errno) {
    echo json_encode(['error' => 'Failed to connect to MySQL: ' . $mysqli->connect_error]);
    exit();
}

// GET params
$staff_id = isset($_GET['staff_id']) ? intval($_GET['staff_id']) : 0;
$service_id = isset($_GET['service_id']) ? intval($_GET['service_id']) : 0;

if ($staff_id == 0 || $service_id == 0) {
    echo json_encode(['error' => 'staff_id and service_id required']);
    exit();
}

// Today's range
$today_start = date('Y-m-d 00:00:01');
$today_end = date('Y-m-d 23:59:59');

// Adjusted query to prevent overlap into next day
$query = "
    SELECT COUNT(*) AS total_booked
    FROM wpia_bookly_appointments
    WHERE (
        start_date <= ?
        AND end_date >= ?
    )
    AND staff_id = ?
    AND service_id = ?
";

$stmt = $mysqli->prepare($query);
if (!$stmt) {
    echo json_encode(['error' => 'SQL Prepare failed: ' . $mysqli->error]);
    exit();
}

$stmt->bind_param('ssii', $today_end, $today_start, $staff_id, $service_id);
$stmt->execute();
$stmt->bind_result($total_booked);
$stmt->fetch();

$status = ($total_booked > 0) ? 'booked' : 'available';

// Output JSON response
echo json_encode([
    'date' => date('Y-m-d'),
    'staff_id' => $staff_id,
    'service_id' => $service_id,
    'status' => $status
]);

$stmt->close();
$mysqli->close();