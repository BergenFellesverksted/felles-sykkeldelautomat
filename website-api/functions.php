<?php
// These are functions to be placed in the Wordpress theme functions.php. They are addon features for the Wordpress, 
// and are used for various parts of the Sykkeldelautomat. In BFVs case this file is currently availible at 
// https://www.bergenfellesverksted.no/wp-admin/theme-editor.php?file=functions.php&theme=twentyseventeen


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

// Get existing codes to avoid creating duplicates
function get_existing_codes() {
    global $wpdb;
    return $wpdb->get_col("SELECT meta_value FROM wpia_postmeta WHERE meta_key IN ('_pickup_code', '_return_code', '_opening_code')");
}

// Assign pickup code to orders containing items from the sykkeldelautomat. This only covers Woocommerce orders, not Bookly.
// It checks if the order contains items from the sykkeldelautomat category and assigns a pickup code if it does.
function assign_pickup_code($order_id) {
    $order = wc_get_order($order_id);
    $items = $order->get_items();
    $contains_sykkeldelautomat = false;

    foreach ($items as $item) {
        $product_id = $item->get_product_id();
        $terms = get_the_terms($product_id, 'product_cat');
        $is_in_sykkeldelautomat = false;

        if ($terms) {
            foreach ($terms as $term) {
                // Check if term is sykkeldelautomat or a subcategory of it
                if ($term->slug === 'sykkeldelautomat' || term_is_ancestor_of(get_term_by('slug', 'sykkeldelautomat', 'product_cat'), $term, 'product_cat')) {
                    $is_in_sykkeldelautomat = true;
                    break;
                }
            }
        }

        // If in correct category, check for Door attribute
        if ($is_in_sykkeldelautomat) {
            $doorValue = null;
            $product_attributes = get_post_meta($product_id, '_product_attributes', true);

            if (!empty($product_attributes) && is_array($product_attributes)) {
                if (isset($product_attributes['door']['value'])) {
                    $doorValue = trim($product_attributes['door']['value']);
                }
            }

            if (!empty($doorValue)) {
                $contains_sykkeldelautomat = true;
                break; // One match is enough, exit loop
            }
        }
    }

    // Assign code and notify customer
    if ($contains_sykkeldelautomat) {
        $pickup_code = generate_unique_pickup_code();
        update_post_meta($order_id, '_pickup_code', $pickup_code);

        $email = $order->get_billing_email();
        $subject = "Pickup code for order $order_id";

        $message = "
            <p>Your order includes items from the Sykkeldelautomat.</p>
            <p>Your pickup code is: <strong>$pickup_code</strong></p>
            <p>Enter your code on the pickup station keypad, starting and ending with an asterisk (*), to unlock the doors containing your items.</p>
            <p>Please note that each door may contain multiple different items. Make sure to take only the items you ordered.</p>
            <p>Your pickup code is valid for a single use. However, once activated, it will remain valid for an additional 15 minutes in case you forgot something or took the wrong item.</p>
        ";

        wp_mail($email, $subject, $message);
    }
}
add_action('woocommerce_payment_complete', 'assign_pickup_code', 10, 1);

// Assign pickup code to Bookly orders. This is a custom function for the Bookly plugin. 
// It basically does the same as the function above, but for Bookly orders.
// It also includes a check to see if the order is for the service "SykkelLab" and only then assigns a pickup code.
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
                       AND (start_date BETWEEN %s AND %s OR end_date BETWEEN %s AND %s)
                       AND id != %d",
                    $booking->service_id,
                    $booking->staff_id,
                    $current_time_mysql,
                    $appointment->start_date,
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
                $used_start_timestamp = strtotime($current_time_mysql);
            } else {
                // Conflict found: abort the update and log a message.
                error_log("Conflict: Found " . count($conflicting_appointments) . " conflicting appointment(s) for order $order_id. Aborting start_date update.");
                // $used_start_timestamp remains as the original start time.
            }
        }
    }
    
    // Generate a unique opening code
    $opening_code = generate_unique_pickup_code();
    update_post_meta($order_id, '_opening_code', $opening_code);
    
    // Format the timestamps to "d.m.Y H:i"
    $formatted_start = date("d.m.Y H:i", $used_start_timestamp);
    $formatted_end   = date("d.m.Y H:i", $end_timestamp);
	
	// Also include validity timestamps 
    update_post_meta($order_id, '_start_time', date("Y-m-d H:i:s", $used_start_timestamp));
    update_post_meta($order_id, '_end_time', date("Y-m-d H:i:s", $end_timestamp));
    
    // Prepare and send the email with the opening code
    $email   = $order->get_billing_email();
    $subject = "Opening code for order $order_id";
    $message = "
        <p>Your booking for SykkelLab is confirmed.</p>
        <p>Your booking is valid from <strong>$formatted_start</strong> to <strong>$formatted_end</strong>.</p>
        <p>Your access code is: <strong>*$opening_code*</strong></p>
        <p>Enter your code on the keypad at the pickup station, starting and ending with an asterisk (*).</p>
        <p>This code is valid for the entire booking period, and you can open the cabinet door as many times as needed during this time.</p>
        <p>Your access will expire automatically after your booking period ends, so please ensure you finish using the cabinet by the end time shown above. If you require additional time, consider extending your booking and obtaining a new access code.</p>
    ";
    
    wp_mail($email, $subject, $message);
}
add_action('woocommerce_payment_complete', 'assign_opening_code_bookly', 10, 1);


// Trigger the assign_pickup_code_bookly function from a GET request.
// This is useful for testing or manual triggering of the function without going through the WooCommerce payment process.
// Uncomment the following lines to enable this feature. Be cautious with security implications.
// function trigger_assign_pickup_code_bookly_from_get() {
//     // For security, you might want to check if the current user is logged in
//     // or has a specific capability. For example:
//     // if ( ! current_user_can('manage_options') ) { return; }
    
//     if ( isset($_GET['order_id']) && !empty($_GET['order_id']) ) {
//         $order_id = intval($_GET['order_id']);
//         // Optionally log that we're triggering the function
//         error_log("Triggering assign_pickup_code_bookly() for Order ID: $order_id via GET");
//         assign_pickup_code_bookly($order_id);
//     }
// }
// add_action('init', 'trigger_assign_pickup_code_bookly_from_get');


// Create a shortcode used in woocommerse item descriptions to show the booking status of a Bookly item the same day.
function booking_status_shortcode($atts) {
    $atts = shortcode_atts([
        'staff_id' => '0',
        'service_id' => '0'
    ], $atts);

    ob_start();
    ?>

    <div id="booking-status-<?php echo esc_attr($atts['staff_id'] . '-' . $atts['service_id']); ?>" style="margin-bottom:20px;">
        Checking availability...
    </div>

    <script>
    document.addEventListener('DOMContentLoaded', function () {
        const statusDiv = document.getElementById('booking-status-<?php echo esc_js($atts['staff_id'] . '-' . $atts['service_id']); ?>');

        fetch('/api_booking_status.php?staff_id=<?php echo esc_js($atts['staff_id']); ?>&service_id=<?php echo esc_js($atts['service_id']); ?>')
            .then(res => res.json())
            .then(data => {
                if (data.status === 'booked') {
                    statusDiv.innerHTML = 'Denne varen er: <strong style="color:red;">Opptatt i dag</strong>';
                } else if (data.status === 'available') {
                    statusDiv.innerHTML = 'Denne varen er: <strong style="color:green;">Tilgjengelig i dag</strong>';
                } else {
                    statusDiv.innerHTML = 'Status unavailable';
                }
            })
            .catch(err => {
                statusDiv.innerHTML = 'Error checking status';
                console.error(err);
            });
    });
    </script>

    <?php
    return ob_get_clean();
}
add_shortcode('booking_status', 'booking_status_shortcode');

?>