<?php
session_start();
include 'constants.php'; // DB_SERVER, DB_USER, DB_PASSWORD, DB_NAME, gui_username, gui_password, etc.

/*
 |----------------------------------------------------------------------------------
 | 1) Check if user is logged in
 |----------------------------------------------------------------------------------
*/
if (!(isset($_SESSION['logged_in']) && $_SESSION['logged_in'] === true)) {
    // If user submitted login form, validate credentials
    if (isset($_POST['username']) && isset($_POST['password'])) {
        if ($_POST['username'] == gui_username && $_POST['password'] == gui_password) {
            $_SESSION['logged_in'] = true;
            header("Refresh:0");
            exit();
        } else {
            $login_error = "Invalid credentials!";
        }
    }
    // Show the login form:
    ?>
    <!DOCTYPE html>
    <html>
    <head>
        <title>Door Grid - Login</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {
                margin: 0; padding: 0;
                font-family: Arial, sans-serif;
                display: flex; justify-content: center; align-items: center;
                height: 100vh; background-color: #f0f0f0;
            }
            form {
                background: white; padding: 20px;
                box-shadow: 0 0 10px rgba(0,0,0,0.1);
                border-radius: 8px; width: 90%; max-width: 400px;
            }
            input[type="text"], input[type="password"] {
                width: 100%; padding: 10px; margin-top: 8px;
                border: 1px solid #ccc; border-radius: 4px;
            }
            button {
                width: 100%; padding: 10px; border: none;
                background-color: #007BFF; color: white;
                border-radius: 4px; margin-top: 20px; cursor: pointer;
            }
            button:hover { background-color: #0056b3; }
            p.error-message { color: red; text-align: center; }
        </style>
    </head>
    <body>
        <form method="post">
            <input type="text" placeholder="Username" name="username"><br>
            <input type="password" placeholder="Password" name="password"><br>
            <button type="submit">Login</button>
        </form>
        <?php
        if (!empty($login_error)) {
            echo '<p class="error-message">' . $login_error . '</p>';
        }
        ?>
    </body>
    </html>
    <?php
    exit();
}

/*
 |----------------------------------------------------------------------------------
 | 2) If logged in, display the door grid
 |----------------------------------------------------------------------------------
*/

// Handle logout if requested
if (isset($_POST['logout'])) {
    session_destroy();
    header("Location: doors_grid.php");
    exit();
}

// Determine link mode: Admin vs Public
$mode = isset($_GET['mode']) ? $_GET['mode'] : 'admin';
$modeLabel = ($mode === 'public') ? 'Public Links' : 'Admin Links';

// Connect to the DB
$conn = new mysqli(DB_SERVER, DB_USER, DB_PASSWORD, DB_NAME);
if ($conn->connect_error) {
    die("Database connection error: " . $conn->connect_error);
}

// Helper functions to handle possible serialization
function maybe_unserialize($data) {
    if (is_serialized($data)) {
        return unserialize($data);
    }
    return $data;
}
function is_serialized($data) {
    return (@unserialize($data) !== false || $data === 'b:0;');
}

/*
 |----------------------------------------------------------------------------------
 | 3) Query Explanation
 |----------------------------------------------------------------------------------
 | This query looks up products in parent cat ID=216 or children (tt.term_id=216 or tt.parent=216).
 | The assumption: 216 is the term_id of 'sykkeldelautomat'.
*/
$sql = "
SELECT
  p.ID AS product_id,
  p.post_name AS product_slug,
  p.post_title,
  product_attrs.meta_value AS product_attributes,
  stock.meta_value AS stock_qty,
  price.meta_value AS item_price,
  parent_t.term_id AS parent_term_id,
  parent_t.slug    AS parent_cat_slug,
  parent_t.name    AS parent_cat_name,
  child_t.term_id AS child_term_id,
  child_t.slug    AS sub_cat_slug,
  child_t.name    AS sub_cat_name
FROM wpia_posts p
JOIN wpia_term_relationships tr 
  ON p.ID = tr.object_id
JOIN wpia_term_taxonomy tt 
  ON tr.term_taxonomy_id = tt.term_taxonomy_id
JOIN wpia_terms parent_t
  ON tt.term_id = parent_t.term_id
LEFT JOIN wpia_postmeta product_attrs
  ON p.ID = product_attrs.post_id
  AND product_attrs.meta_key = '_product_attributes'
LEFT JOIN wpia_postmeta stock
  ON p.ID = stock.post_id
  AND stock.meta_key = '_stock'
LEFT JOIN wpia_postmeta price
  ON p.ID = price.post_id
  AND price.meta_key = '_price'
LEFT JOIN (
  SELECT
    tt2.term_taxonomy_id,
    t2.term_id,
    t2.slug,
    t2.name,
    tr2.object_id
  FROM wpia_term_relationships tr2
  JOIN wpia_term_taxonomy tt2
    ON tr2.term_taxonomy_id = tt2.term_taxonomy_id
  JOIN wpia_terms t2
    ON tt2.term_id = t2.term_id
  WHERE tt2.taxonomy = 'product_cat'
    AND tt2.parent = 216
) AS child_t
  ON child_t.object_id = p.ID
WHERE p.post_type = 'product'
  AND p.post_status = 'publish'
  AND tt.taxonomy = 'product_cat'
  AND (
      tt.term_id = 216
   OR tt.parent  = 216
  )
GROUP BY p.ID
ORDER BY p.post_title
";

$result = $conn->query($sql);

// Prepare the door arrays: 1..20
$doors = [];
for ($i = 1; $i <= 20; $i++) {
    $doors[$i] = [];
}

/*
 |----------------------------------------------------------------------------------
 | 4) Build the product list
 |----------------------------------------------------------------------------------
*/
if ($result && $result->num_rows > 0) {
    while ($row = $result->fetch_assoc()) {
        $productID     = $row['product_id'];
        $productSlug   = $row['product_slug'];
        $productName   = $row['post_title'];
        $attrSerialized= $row['product_attributes'];
        $stockQty      = $row['stock_qty'];
        $itemPrice     = $row['item_price'];
        $subCatSlug    = $row['sub_cat_slug'] ?: '';
        $subCatName    = $row['sub_cat_name'];
        $doorValue = null;
        if (!empty($attrSerialized)) {
            $attributes = maybe_unserialize($attrSerialized);
            if (isset($attributes['door']['value'])) {
                $doorValue = trim($attributes['door']['value']);
            }
        }
        if ($doorValue && ctype_digit($doorValue)) {
            $doorInt = (int)$doorValue;
            if ($doorInt >= 1 && $doorInt <= 20) {
                $doors[$doorInt][] = [
                    'id'          => $productID,
                    'slug'        => $productSlug,
                    'name'        => $productName,
                    'stock'       => $stockQty,
                    'price'       => $itemPrice,
                    'sub_cat_slug'=> strtolower($subCatSlug),
                    'sub_cat_name'=> $subCatName
                ];
            }
        }
    }
}
$conn->close();

/*
 |----------------------------------------------------------------------------------
 | 5) Color-Coding by Sub-Category + Legend
 |----------------------------------------------------------------------------------
*/
$colorMap = [
    'diy'                   => '#ffdada',
    'drivverk'              => '#daffda',
    'slanger'               => '#dadaff',
    'bremser'               => '#fff5da',
    'wire-og-stromper'      => '#f5daff',
    'vask-og-vedlikehold'   => '#f5ccaa'
];
$defaultColor = '#eaeaea';
?>

<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Doors Grid (<?php echo htmlspecialchars($modeLabel); ?>)</title>
    <style>
        body {
            font-family: Arial, sans-serif; background-color: #f4f4f4; margin: 20px;
        }
        .logout-btn {
            background-color: red; color: white; border: none;
            padding: 10px 15px; cursor: pointer; float: right; border-radius: 4px;
        }
        .logout-btn:hover { background-color: darkred; }
        .admin-link { display: inline-block; margin-right: 10px; }
        h2 { margin-top: 0; }
        .grid-container {
            display: grid; 
            grid-template-columns: repeat(4, 1fr);
            grid-gap: 20px; 
            margin-top: 30px;
        }
        .grid-item {
            background: #fff; 
            border: 1px solid #ccc; 
            border-radius: 6px;
            padding: 15px; 
            box-shadow: 0 0 5px rgba(0,0,0,0.1);
        }
        /* New header row for each door */
        .grid-item-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }
        .grid-item-header h3 {
            margin: 0;
        }
        .item-list {
            margin: 0; 
            padding: 0; 
            list-style: none;
        }
        .item-list li {
            margin: 5px 0; 
            padding: 8px; 
            border-radius: 4px;
        }
        .item-list a {
            text-decoration: none; 
            color: #000; 
            font-weight: bold;
        }
        .item-list a:hover {
            text-decoration: underline;
        }
        .stock-label, .price-label {
            font-weight: normal; 
            font-size: 0.9em; 
            color: #666; 
            margin-left: 6px;
        }
        .color-legend {
            display: flex; 
            flex-wrap: wrap; 
            gap: 10px; 
            margin-top: 10px;
        }
        .legend-item {
            display: flex; 
            align-items: center; 
            gap: 6px; 
            margin-bottom: 5px;
        }
        .legend-color-box {
            width: 14px; 
            height: 14px; 
            border-radius: 3px;
            border: 1px solid #ccc;
        }
        /* Button styling for opening a door */
        .open-door-btn {
            padding: 8px 12px;
            background-color: #28a745;
            border: none;
            border-radius: 4px;
            color: #fff;
            cursor: pointer;
        }
        .open-door-btn:hover {
            background-color: #218838;
        }
    </style>
    <script src="https://ajax.googleapis.com/ajax/libs/jquery/3.6.0/jquery.min.js"></script>
</head>
<body>

<!-- Logout Button -->
<form method="post">
    <button type="submit" name="logout" class="logout-btn">Logout</button>
</form>

<p><a href="./">Show Order List</a></p>

<!-- Mode Toggle Links -->
<p>
    <strong>Link Mode:</strong>
    <a class="admin-link" href="?mode=admin">Admin</a> | 
    <a class="admin-link" href="?mode=public">Public</a>
</p>

<!-- Manage All Items link -->
<p>
    <a class="admin-link" href="https://www.bergenfellesverksted.no/wp-admin/edit.php?s&post_status=all&post_type=product&product_cat=sykkeldelautomat" 
       target="_blank">
       Manage All Items (Sykkeldelautomat)
    </a>
</p>

<!-- Color Legend -->
<div class="color-legend">
    <strong>Color Legend:</strong>
    <?php foreach ($colorMap as $slug => $color): ?>
        <div class="legend-item">
            <div class="legend-color-box" style="background-color: <?php echo $color; ?>;"></div>
            <span><?php echo htmlspecialchars($slug); ?></span>
        </div>
    <?php endforeach; ?>
    <div class="legend-item">
        <div class="legend-color-box" style="background-color: <?php echo $defaultColor; ?>;"></div>
        <span>Other / Not Mapped</span>
    </div>
</div>

<h2>Lockers in Sykkeldelautomat (Doors 1–20) - <?php echo htmlspecialchars($modeLabel); ?></h2>

<div class="grid-container">
    <?php for ($doorNumber = 1; $doorNumber <= 20; $doorNumber++): ?>
        <div class="grid-item">
            <div class="grid-item-header">
                <h3>Door <?php echo $doorNumber; ?></h3>
                <button class="open-door-btn" data-door="<?php echo $doorNumber; ?>">Open Door</button>
            </div>
            <?php if (!empty($doors[$doorNumber])): ?>
                <ul class="item-list">
                    <?php foreach ($doors[$doorNumber] as $item):
                        $productID   = $item['id'];
                        $productSlug = $item['slug'];
                        $productName = htmlspecialchars($item['name']);
                        $stock       = $item['stock'];
                        $price       = $item['price'];
                        $subCatSlug  = $item['sub_cat_slug'];
                        $stockText = ($stock !== null && $stock !== '')
                            ? 'Stock: ' . htmlspecialchars($stock)
                            : 'Stock: N/A';
                        $priceText = ($price !== null && $price !== '')
                            ? htmlspecialchars($price) . ' kr'
                            : 'N/A kr';
                        $bgColor = isset($colorMap[$subCatSlug]) ? $colorMap[$subCatSlug] : $defaultColor;
                        
                        if ($mode === 'public') {
                            $finalLink = "https://www.bergenfellesverksted.no/produkt/" . $productSlug;
                        } else {
                            $finalLink = "https://www.bergenfellesverksted.no/wp-admin/post.php?post={$productID}&action=edit";
                        }
                    ?>
                    <li style="background-color: <?php echo $bgColor; ?>;">
                        <a href="<?php echo $finalLink; ?>" target="_blank">
                            <?php echo $productName; ?>
                        </a>
                        <span class="stock-label">(<?php echo $priceText; ?>, <?php echo $stockText; ?>)</span>
                    </li>
                    <?php endforeach; ?>
                </ul>
            <?php else: ?>
                <p>Empty</p>
            <?php endif; ?>
        </div>
    <?php endfor; ?>
</div>

<script>
$(document).ready(function(){
    $(".open-door-btn").click(function(){
        var doorNumber = $(this).data("door");
        var confirmation = confirm("Are you sure you want to open door " + doorNumber + " right now?");
        if (confirmation) {
            var confirmation2 = confirm("Really?");
            if (confirmation2) {
                $.ajax({
                    url: "open_door.php",
                    type: "POST",
                    data: { door: doorNumber },
                    success: function(response) {
                        alert("Request to open door " + doorNumber + " sent successfully!");
                    },
                    error: function(xhr, status, error) {
                        alert("Error opening door " + doorNumber + ": " + error);
                    }
                });
            }
        }
    });
});
</script>

</body>
</html>
