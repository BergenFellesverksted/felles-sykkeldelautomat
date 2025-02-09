// Functions to generate pickup codes for the sykkeldelautomat
function generate_unique_pickup_code() {
    $letters = ['A', 'B', 'C', 'D'];
    $numbers = range(0, 9);
    $existing_codes = get_existing_codes();

    do {
        $code = [];
        $code[] = $letters[array_rand($letters)];
        $code[] = $numbers[array_rand($numbers)];
        for ($i = 0; $i < 2; $i++) {
            $code[] = (rand(0, 1) ? $letters[array_rand($letters)] : $numbers[array_rand($numbers)]);
        }
        shuffle($code);
        $final_code = implode('', $code);
    } while (in_array($final_code, $existing_codes));

    return $final_code;
}

function get_existing_codes() {
    global $wpdb;
    return $wpdb->get_col("SELECT meta_value FROM wpia_postmeta WHERE meta_key IN ('_pickup_code', '_return_code')");
}

function assign_pickup_code($order_id) {
    $order = wc_get_order($order_id);
    $items = $order->get_items();
    $contains_sykkeldelautomat = false;

    foreach ($items as $item) {
        $product_id = $item->get_product_id();
        $terms = get_the_terms($product_id, 'product_cat');

        if ($terms) {
            foreach ($terms as $term) {
                if ($term->slug == 'sykkeldelautomat') {
                    $contains_sykkeldelautomat = true;
                }
            }
        }
    }

    if ($contains_sykkeldelautomat) {
        $pickup_code = generate_unique_pickup_code();
        update_post_meta($order_id, '_pickup_code', $pickup_code);

        $email = $order->get_billing_email();
        $subject = "Pickup code for order $order_id";
		$qrUrl = "https://quickchart.io/qr?text=" . urlencode($pickup_code) ;

		// Now include this URL in your email HTML:
		$message = "
			<p>Your order contains items from the Sykkeldelautomat.</p>
			<p>Your pickup code is: <strong>$pickup_code</strong></p>
			<p>Please use this code or scan the QR code below at the pickup station:</p>
			<p><img src='$qrUrl' alt='QR Code' /></p>
		";

        wp_mail($email, $subject, $message);
    }
}
add_action('woocommerce_payment_complete', 'assign_pickup_code', 10, 1);

// function for the bookly items
function assign_pickup_code_bookly($order_id) {
    global $wpdb;
    
    // Wait 10 seconds to let all metadata be saved
    sleep(10);
    
    // Get the WooCommerce order object
    $order = wc_get_order($order_id);
    if (!$order) {
        return;
    }
    
    // Retrieve the booking info: extract service_id and staff_id from the serialized meta
    $booking = $wpdb->get_row(
        $wpdb->prepare("
            SELECT 
                oi.order_id,
                CAST(
                    SUBSTRING_INDEX(
                        SUBSTRING_INDEX(oi_meta.meta_value, 's:10:\"service_id\";i:', -1),
                        ';', 1
                    ) AS UNSIGNED
                ) AS service_id,
                CAST(
                    SUBSTRING_INDEX(
                        SUBSTRING_INDEX(oi_meta.meta_value, 's:9:\"staff_ids\";a:1:{i:0;i:', -1),
                        ';', 1
                    ) AS UNSIGNED
                ) AS staff_id
            FROM wpia_woocommerce_order_items oi
            JOIN wpia_woocommerce_order_itemmeta oi_meta 
                ON oi.order_item_id = oi_meta.order_item_id
            JOIN wpia_bookly_services bs 
                ON bs.id = CAST(
                        SUBSTRING_INDEX(
                            SUBSTRING_INDEX(oi_meta.meta_value, 's:10:\"service_id\";i:', -1),
                            ';', 1
                        ) AS UNSIGNED
                    )
            WHERE oi_meta.meta_key = 'bookly'
              AND oi.order_id = %d
              AND bs.title = 'SykkelLab'
            LIMIT 1;
        ", $order_id)
    );
    
    // If no matching booking is found, exit the function
    if (!$booking) {
        return;
    }
    
    // Extract service_id and staff_id from the query result
    $service_id = $booking->service_id;
    $staff_id   = $booking->staff_id;
    
    // Optionally update the order meta with the extracted IDs for later reference
    update_post_meta($order_id, '_bookly_service_id', $service_id);
    update_post_meta($order_id, '_bookly_staff_id', $staff_id);
    
    // Generate unique pickup & return codes
    $pickup_code = generate_unique_pickup_code();
    $return_code = generate_unique_pickup_code();
    update_post_meta($order_id, '_pickup_code', $pickup_code);
    update_post_meta($order_id, '_return_code', $return_code);
    
    // Prepare and send the email with the codes and the extracted IDs
    $email   = $order->get_billing_email();
    $subject = "Pickup and return code for order $order_id";
    $message = "Your booking for SykkelLab is confirmed.\n\n" .
               "Pickup Code: *$pickup_code*\n" .
               "Return Code: *$return_code*\n" .
               "Please use these codes at the pickup station. Each code works only once.";
    
    wp_mail($email, $subject, $message);
}
add_action('woocommerce_payment_complete', 'assign_pickup_code_bookly', 10, 1);


// Trigger the assign_pickup_code_bookly() function based on an order_id passed via GET
function trigger_assign_pickup_code_bookly_from_get() {
    // For security, you might want to check if the current user is logged in
    // or has a specific capability. For example:
    // if ( ! current_user_can('manage_options') ) { return; }
    
    if ( isset($_GET['order_id']) && !empty($_GET['order_id']) ) {
        $order_id = intval($_GET['order_id']);
        // Optionally log that we're triggering the function
        error_log("Triggering assign_pickup_code_bookly() for Order ID: $order_id via GET");
        assign_pickup_code_bookly($order_id);
    }
}
add_action('init', 'trigger_assign_pickup_code_bookly_from_get');