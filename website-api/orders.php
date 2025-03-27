<?php
require 'constants.php';

// Set the correct headers for JSON output
header("Content-Type: application/json");

// Check if API key is provided in the request
if (!isset($_GET['api_key']) || $_GET['api_key'] !== API_KEY) {
    echo json_encode(["error" => "Unauthorized: Invalid API Key"]);
    http_response_code(403);
    exit();
}

$conn = new mysqli(DB_SERVER, DB_USER, DB_PASSWORD, DB_NAME);

// Check connection
if ($conn->connect_error) {
    echo json_encode(["error" => "Failed to connect to MySQL: " . $conn->connect_error]);
    exit();
}

// SQL Query to fetch WooCommerce orders with products from "sykkeldelautomat"
$sql = "
SELECT DISTINCT 
    wpia_posts.ID AS order_id, 
    wpia_posts.post_date, 
    wpia_postmeta.meta_value AS order_total, -- Include order total
    wpia_woocommerce_order_items.order_item_id,
    wpia_woocommerce_order_items.order_item_name AS product_name,
    wpia_woocommerce_order_itemmeta.meta_value AS product_id,
    product_attributes.meta_value AS product_attributes,
    billing_first.meta_value AS first_name,
    billing_last.meta_value AS last_name,
    pickup.meta_value AS pickup_code,
    pickup_time.meta_value AS pickup_time,
    return_time.meta_value AS return_time,
    opening_code.meta_value AS opening_code,
    opening_time.meta_value AS opening_time,
    start_time.meta_value AS start_time,
    end_time.meta_value AS end_time
FROM wpia_posts
LEFT JOIN wpia_woocommerce_order_items 
    ON wpia_posts.ID = wpia_woocommerce_order_items.order_id
LEFT JOIN wpia_woocommerce_order_itemmeta 
    ON wpia_woocommerce_order_items.order_item_id = wpia_woocommerce_order_itemmeta.order_item_id
LEFT JOIN wpia_term_relationships 
    ON wpia_woocommerce_order_itemmeta.meta_value = wpia_term_relationships.object_id
LEFT JOIN wpia_term_taxonomy 
    ON wpia_term_relationships.term_taxonomy_id = wpia_term_taxonomy.term_taxonomy_id
LEFT JOIN wpia_terms 
    ON wpia_term_taxonomy.term_id = wpia_terms.term_id
LEFT JOIN wpia_postmeta AS wpia_postmeta 
    ON wpia_posts.ID = wpia_postmeta.post_id 
    AND wpia_postmeta.meta_key = '_order_total'
LEFT JOIN wpia_postmeta AS billing_first 
    ON wpia_posts.ID = billing_first.post_id 
    AND billing_first.meta_key = '_billing_first_name'
LEFT JOIN wpia_postmeta AS billing_last 
    ON wpia_posts.ID = billing_last.post_id 
    AND billing_last.meta_key = '_billing_last_name'
LEFT JOIN wpia_postmeta AS pickup 
    ON wpia_posts.ID = pickup.post_id 
    AND pickup.meta_key = '_pickup_code'
LEFT JOIN wpia_postmeta AS pickup_time 
    ON wpia_posts.ID = pickup_time.post_id 
    AND pickup_time.meta_key = '_pickup_time'
LEFT JOIN wpia_postmeta AS return_time 
    ON wpia_posts.ID = return_time.post_id 
    AND return_time.meta_key = '_return_time'
LEFT JOIN wpia_postmeta AS opening_code 
    ON wpia_posts.ID = opening_code.post_id 
    AND opening_code.meta_key = '_opening_code'
LEFT JOIN wpia_postmeta AS opening_time 
    ON wpia_posts.ID = opening_time.post_id 
    AND opening_time.meta_key = '_opening_time'
LEFT JOIN wpia_postmeta AS start_time 
    ON wpia_posts.ID = start_time.post_id 
    AND start_time.meta_key = '_start_time'
LEFT JOIN wpia_postmeta AS end_time 
    ON wpia_posts.ID = end_time.post_id 
    AND end_time.meta_key = '_end_time'
LEFT JOIN wpia_postmeta AS product_attributes 
    ON wpia_woocommerce_order_itemmeta.meta_value = product_attributes.post_id 
    AND product_attributes.meta_key = '_product_attributes'
WHERE wpia_posts.post_type = 'shop_order'
AND wpia_posts.post_status IN ('wc-completed', 'wc-processing', 'wc-on-hold')
AND wpia_woocommerce_order_itemmeta.meta_key = '_product_id'
AND (
    wpia_terms.slug = 'sykkeldelautomat'
    OR wpia_term_taxonomy.parent = (SELECT term_id FROM wpia_terms WHERE slug = 'sykkeldelautomat')
)
ORDER BY wpia_posts.ID, wpia_woocommerce_order_items.order_item_id;
";

$result = $conn->query($sql);

$orders = [];

// Process WooCommerce Orders
if ($result->num_rows > 0) {
    while ($row = $result->fetch_assoc()) {
        $order_id = $row['order_id'];
        $product_name = $row['product_name'];
        $customer_name = trim($row['first_name'] . ' ' . $row['last_name']);
        $pickup_code = $row['pickup_code'] ? $row['pickup_code'] : "Not Assigned";
        $pickup_time = $row['pickup_time'] ? $row['pickup_time'] : "Not Picked Up";
        $opening_code = $row['opening_code'] ? $row['opening_code'] : "Not Assigned";
        
        // Process opening_time field (may be serialized array)
        $opening_time = !empty($row['opening_time']) ? maybe_unserialize($row['opening_time']) : [];
        
        // Process start_time field
        $start_time = !empty($row['start_time']) ? maybe_unserialize($row['start_time']) : [];
        
        // Process end_time field
        $end_time = !empty($row['end_time']) ? maybe_unserialize($row['end_time']) : [];

        if (!isset($orders[$order_id])) {
            $orders[$order_id] = [
                "order_id" => $order_id,
                "customer_name" => $customer_name,
                "order_date" => $row["post_date"],
                "order_total" => $row["order_total"],
                "pickup_code" => $pickup_code,
                "pickup_time" => $pickup_time,
                "opening_code" => $opening_code,
                "opening_time" => $opening_time,
                "start_time" => $start_time,
                "end_time" => $end_time,
                "items" => []
            ];
        }

        $door_value = "Unknown";
        if (!empty($row['product_attributes'])) {
            $attributes = maybe_unserialize($row['product_attributes']);
            if (isset($attributes['door']['value'])) {
                $door_value = $attributes['door']['value'];
            }
        }

        $orders[$order_id]["items"][] = [
            "product_name" => $product_name,
            "door" => $door_value
        ];
    }
}

// SQL Query to fetch Bookly Orders
$bookly_sql = "
SELECT 
    oi.order_id,                          
    oi.order_item_id,                     
    o.post_date,                          
    wp_total.meta_value AS order_total,   -- Order total from order meta
    oi.order_item_name,                   
    bs.id AS service_id,                  
    bs.title AS service_name,             
    bookly_staff.full_name AS product_name, -- Staff name is used as product name
    billing_first.meta_value AS first_name,
    billing_last.meta_value AS last_name,
    wp_productmeta.meta_value AS product_attributes,
    oi_meta.meta_value AS bookly_data,    
    pm1.meta_value AS pickup_code,        
    pm2.meta_value AS return_code,        
    pm3.meta_value AS pickup_time,   
    pm4.meta_value AS return_time,
    pm5.meta_value AS opening_code,
    pm6.meta_value AS opening_time,
    pm7.meta_value AS start_time,
    pm8.meta_value AS end_time
FROM wpia_woocommerce_order_items oi
JOIN wpia_posts o ON oi.order_id = o.ID
JOIN wpia_woocommerce_order_itemmeta oi_meta 
    ON oi.order_item_id = oi_meta.order_item_id
-- Join the order meta that stores the Bookly IDs:
LEFT JOIN wpia_postmeta service_meta 
    ON oi.order_id = service_meta.post_id AND service_meta.meta_key = '_bookly_service_id'
LEFT JOIN wpia_postmeta staff_meta 
    ON oi.order_id = staff_meta.post_id AND staff_meta.meta_key = '_bookly_staff_id'
-- Use the saved service ID to join the Bookly services table:
JOIN wpia_bookly_services bs 
    ON bs.id = service_meta.meta_value
-- Use the saved staff ID to join the Bookly staff table:
JOIN wpia_bookly_staff bookly_staff
    ON bookly_staff.id = staff_meta.meta_value
-- Match the staff name to a WooCommerce product (to retrieve product attributes such as door)
JOIN wpia_posts wp_products 
    ON wp_products.post_title = bookly_staff.full_name 
    AND wp_products.post_type = 'product'
LEFT JOIN wpia_postmeta wp_productmeta 
    ON wp_products.ID = wp_productmeta.post_id 
    AND wp_productmeta.meta_key = '_product_attributes'
-- Also join billing info and order meta for codes/total:
LEFT JOIN wpia_postmeta billing_first 
    ON oi.order_id = billing_first.post_id 
    AND billing_first.meta_key = '_billing_first_name'
LEFT JOIN wpia_postmeta billing_last 
    ON oi.order_id = billing_last.post_id 
    AND billing_last.meta_key = '_billing_last_name'
LEFT JOIN wpia_postmeta pm1 
    ON oi.order_id = pm1.post_id 
    AND pm1.meta_key = '_pickup_code'
LEFT JOIN wpia_postmeta pm2 
    ON oi.order_id = pm2.post_id 
    AND pm2.meta_key = '_return_code'
LEFT JOIN wpia_postmeta pm3 
    ON oi.order_id = pm3.post_id 
    AND pm3.meta_key = '_pickup_time'
LEFT JOIN wpia_postmeta pm4 
    ON oi.order_id = pm4.post_id 
    AND pm4.meta_key = '_return_time'
LEFT JOIN wpia_postmeta pm5 
    ON oi.order_id = pm5.post_id 
    AND pm5.meta_key = '_opening_code'
LEFT JOIN wpia_postmeta pm6 
    ON oi.order_id = pm6.post_id 
    AND pm6.meta_key = '_opening_time'
LEFT JOIN wpia_postmeta pm7 
    ON oi.order_id = pm7.post_id 
    AND pm7.meta_key = '_start_time'
LEFT JOIN wpia_postmeta pm8 
    ON oi.order_id = pm8.post_id 
    AND pm8.meta_key = '_end_time'
LEFT JOIN wpia_postmeta wp_total 
    ON o.ID = wp_total.post_id 
    AND wp_total.meta_key = '_order_total'
WHERE oi_meta.meta_key = 'bookly' 
  AND oi.order_item_name LIKE '%Booking%'
  AND bs.title = 'SykkelLab'
GROUP BY oi.order_id
ORDER BY oi.order_id DESC;
";

$bookly_result = $conn->query($bookly_sql);

if ($bookly_result->num_rows > 0) {
    while ($row = $bookly_result->fetch_assoc()) {
        $order_id = $row['order_id'];
        $product_name = $row['product_name']; // Staff name is used as product name
        $customer_name = trim($row['first_name'] . ' ' . $row['last_name']); 
        $order_total = $row['order_total'] ? $row['order_total'] : "Unknown";
        $pickup_code = $row['pickup_code'] ? $row['pickup_code'] : "Not Assigned";
        $return_code = $row['return_code'] ? $row['return_code'] : "Not Assigned";
        $pickup_time = $row['pickup_time'] ? $row['pickup_time'] : "Not Picked Up";
        $return_time = $row['return_time'] ? $row['return_time'] : "Not Returned";
        $opening_code = $row['opening_code'] ? $row['opening_code'] : "Not Assigned";
        
        // Process opening_time field
        $opening_time = !empty($row['opening_time']) ? maybe_unserialize($row['opening_time']) : [];
        // Process start_time field
        $start_time = !empty($row['start_time']) ? maybe_unserialize($row['start_time']) : [];
        // Process end_time field
        $end_time = !empty($row['end_time']) ? maybe_unserialize($row['end_time']) : [];

        // Extract "Door" attribute from serialized product attributes
        $door_value = "Unknown";
        if (!empty($row['product_attributes'])) {
            $attributes = maybe_unserialize($row['product_attributes']);
            if (isset($attributes['door']['value'])) {
                $door_value = $attributes['door']['value'];
            }
        }

        if (!isset($orders[$order_id])) {
            $orders[$order_id] = [
                "order_id" => $order_id,
                "customer_name" => $customer_name,
                "order_date" => $row["post_date"],
                "order_total" => $order_total,
                "pickup_code" => $pickup_code,
                "return_code" => $return_code,
                "pickup_time" => $pickup_time,
                "return_time" => $return_time,
                "opening_code" => $opening_code,
                "opening_time" => $opening_time,
                "start_time" => $start_time,
                "end_time" => $end_time,
                "items" => []
            ];
        }

        $orders[$order_id]["items"][] = [
            "product_name" => $product_name,
            "door" => $door_value
        ];
    }
}

function maybe_unserialize($data) {
    if (is_serialized($data)) {
        return unserialize($data);
    }
    return $data;
}

function is_serialized($data) {
    return (@unserialize($data) !== false || $data === 'b:0;');
}

// Convert to JSON and output to the browser
echo json_encode(array_values($orders), JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE);

// Close the connection
$conn->close();
?>
