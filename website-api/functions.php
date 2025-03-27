<?php

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
		//$message = "
		//	<p>Your order contains items from the Sykkeldelautomat.</p>
		//	<p>Your pickup code is: <strong>$pickup_code</strong></p>
		//	<p>Please use this code or scan the QR code below at the pickup station:</p>
		//	<p><img src='$qrUrl' alt='QR Code' /></p>
		//";
		$message = "
			<p>Your order contains items from the Sykkeldelautomat.</p>
			<p>Your pickup code is: <strong>$pickup_code</strong></p>
			<p>Start and end your code with * on the keypad at the pickup station.</p>
		";

        wp_mail($email, $subject, $message);
    }
}
add_action('woocommerce_payment_complete', 'assign_pickup_code', 10, 1);

function assign_opening_code_bookly($order_id) {
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
    
    // Update order meta with the extracted booking IDs for later reference
    update_post_meta($order_id, '_bookly_service_id', $booking->service_id);
    update_post_meta($order_id, '_bookly_staff_id', $booking->staff_id);
    
    // Retrieve the appointment from the wpia_bookly_appointments table
    $appointment = $wpdb->get_row(
        $wpdb->prepare(
            "SELECT id, start_date, end_date FROM wpia_bookly_appointments 
             WHERE service_id = %d AND staff_id = %d 
             ORDER BY id DESC LIMIT 1", 
            $booking->service_id, 
            $booking->staff_id
        )
    );
    
    if ($appointment && !empty($appointment->start_date)) {
        $start_timestamp      = strtotime($appointment->start_date);
        $end_timestamp        = strtotime($appointment->end_date);
        $current_timestamp    = time();
        $used_start_timestamp = $start_timestamp; // default to the original start
        
        if (($start_timestamp - $current_timestamp) < 86400) { // less than 24 hours away
            // Get current time in MySQL datetime format
            $current_time_mysql = current_time('mysql');
            
            // Search for conflicting appointments with the same service and staff
            // whose start_date falls between the current time and the original appointment start date.
            $conflicting_appointments = $wpdb->get_results(
                $wpdb->prepare(
                    "SELECT id, start_date 
                     FROM wpia_bookly_appointments 
                     WHERE service_id = %d 
                       AND staff_id = %d 
                       AND start_date BETWEEN %s AND %s 
                       AND id != %d",
                    $booking->service_id,
                    $booking->staff_id,
                    $current_time_mysql,
                    $appointment->start_date,
                    $appointment->id
                )
            );
            
            if (empty($conflicting_appointments)) {
                // No conflicts found; update the appointment's start_date
                $wpdb->update(
                    'wpia_bookly_appointments',
                    array('start_date' => $current_time_mysql),
                    array('id' => $appointment->id),
                    array('%s'),
                    array('%d')
                );
                $used_start_timestamp = $current_time_mysql;
            } else {
                // Conflict found: abort the update and log a message.
                error_log("Conflict: Found " . count($conflicting_appointments) . " conflicting appointment(s) for order $order_id. Aborting start_date update.");
                // $used_start_timestamp remains as the original start time.
            }
        }
    } else {
        // If no appointment is found, set defaults.
        $used_start_timestamp = current_time('mysql');
        $end_timestamp = time();
    }
    
    // Generate a unique opening code
    $opening_code = generate_unique_pickup_code();
    update_post_meta($order_id, '_opening_code', $opening_code);
    
    // Format the timestamps to "d.m.Y H:i"
    $formatted_start = date("d.m.Y H:i", strtotime($used_start_timestamp));
    $formatted_end   = date("d.m.Y H:i", $end_timestamp);
    
    // Also include validity timestamps 
    update_post_meta($order_id, '_start_time', date("Y-m-d H:i:s", $used_start_timestamp));
    update_post_meta($order_id, '_end_time', date("Y-m-d H:i:s", $end_timestamp));
    
    // Prepare and send the email with the opening code
    $email   = $order->get_billing_email();
    $subject = "Opening code for order $order_id";
    $message = "<p>Your booking for SykkelLab is confirmed.</p>" .
               "<p>Booking is valid from " . $formatted_start . " to " . $formatted_end . "</p>" .
               "<p>Your opening code is: <strong>*$opening_code*</strong></p>" .
               "<p>Start and end your code with * on the keypad at the pickup station.</p>" .
               "<p>This code will work within the entire booking window, and you can open the cabinet door as many times as you want.</p>";
    
    wp_mail($email, $subject, $message);
}
add_action('woocommerce_payment_complete', 'assign_opening_code_bookly', 10, 1);


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

?>