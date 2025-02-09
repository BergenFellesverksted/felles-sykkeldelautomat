<?php
session_start();
include 'constants.php';

// Check if the user is already logged in
if (!(isset($_SESSION['logged_in']) && $_SESSION['logged_in'] === true)) {
    if (isset($_POST['username']) && isset($_POST['password'])) {
        if ($_POST['username'] == gui_username && $_POST['password'] == gui_password) {
            $_SESSION['logged_in'] = true;
            header("Refresh:0");
        } else {
            $login_error = "Invalid credentials!";
        }
    }
    ?>
    <html>
        <head>
            <title>Login</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {
                    margin: 0;
                    padding: 0;
                    font-family: Arial, sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    background-color: #f0f0f0;
                }
                form {
                    background: white;
                    padding: 20px;
                    box-shadow: 0 0 10px rgba(0,0,0,0.1);
                    border-radius: 8px;
                    width: 90%;
                    max-width: 400px;
                }
                input[type="text"], input[type="password"] {
                    width: 100%;
                    padding: 10px;
                    margin-top: 8px;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                }
                button {
                    width: 100%;
                    padding: 10px;
                    border: none;
                    background-color: #007BFF;
                    color: white;
                    border-radius: 4px;
                    margin-top: 20px;
                    cursor: pointer;
                }
                button:hover {
                    background-color: #0056b3;
                }
                p.error-message {
                    color: red;
                    text-align: center;
                }
            </style>
        </head>
        <body>
    <?php
    echo '<form method="post">
            <input type="text" placeholder="Username" name="username"><br>
            <input type="password" placeholder="Password" name="password"><br>
            <button type="submit">Login</button>
          </form>';

    if (!empty($login_error)) {
        echo '<p class="error-message">' . $login_error . '</p>';
    }
    ?>
        </body>
    </html>
    <?php
    return;
} else {
?>

<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Sykkeldelautomat Orders</title>
    <link rel="stylesheet" href="https://cdn.datatables.net/1.11.3/css/jquery.dataTables.min.css">
    <script src="https://ajax.googleapis.com/ajax/libs/jquery/3.6.0/jquery.min.js"></script>
    <script src="https://cdn.datatables.net/1.11.3/js/jquery.dataTables.min.js"></script>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f4f4f4;
        }
        table {
            width: 100%;
            background-color: white;
        }
        .logout-btn {
            background-color: red;
            color: white;
            border: none;
            padding: 10px 15px;
            cursor: pointer;
            float: right;
            border-radius: 4px;
        }
        .logout-btn:hover {
            background-color: darkred;
        }
    </style>
</head>
<body>

<h2>Orders from Sykkeldelautomat</h2>
<form method="post">
    <button type="submit" name="logout" class="logout-btn">Logout</button>
</form>

<table id="ordersTable" class="display">
    <thead>
        <tr>
            <th>Order ID</th>
            <th>Customer Name</th>
            <th>Order Date</th>
            <th>Order Total</th>
            <th>Pickup Code</th>
            <th>Pickup Time</th>
            <th>Return Code</th>
            <th>Return Time</th>
            <th>Items</th>
        </tr>
    </thead>
    <tbody>
        <!-- Data will be inserted here by JavaScript -->
    </tbody>
</table>

<script>
    $(document).ready(function() {
        let apiKey = "<?php echo API_KEY; ?>"; // Replace with your actual API key

        fetch(`orders.php?api_key=${apiKey}`)
            .then(response => response.json())
            .then(data => {
                let tableBody = $("#ordersTable tbody");

                data.forEach(order => {
                    let itemsHTML = order.items.map(item => `- ${item.product_name} (Door: ${item.door})`).join("<br>");
                    let rowHTML = `
                        <tr>
                            <td>${order.order_id}</td>
                            <td>${order.customer_name}</td>
                            <td>${order.order_date}</td>
                            <td>${order.order_total}</td>
                            <td>${order.pickup_code}</td>
                            <td>${order.pickup_time}</td>
                            <td>${order.return_code}</td>
                            <td>${order.return_time}</td>
                            <td>${itemsHTML}</td>
                        </tr>
                    `;
                    tableBody.append(rowHTML);
                });

                $('#ordersTable').DataTable({
                    "pageLength": 50,
                    "lengthMenu": [[10, 25, 50, 100, 500], [10, 25, 50, 100, "500"]],
                    "order": [[2, "desc"]]
                });
            })
            .catch(error => console.error("Error fetching orders:", error));
    });
</script>

</body>
</html>

<?php
}

// Logout functionality
if (isset($_POST['logout'])) {
    session_destroy();
    header("Location: index.php");
    exit();
}
?>
