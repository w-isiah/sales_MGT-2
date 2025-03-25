from apps.products import blueprint
from flask import render_template, request, redirect, url_for, flash, session
from flask import Flask
import mysql.connector
from werkzeug.utils import secure_filename
from mysql.connector import Error
from datetime import datetime
import os
import random
import logging
from apps import get_db_connection


# Helper function to calculate formatted totals
def calculate_formatted_totals(products):
    total_sum = sum(product['total_price'] for product in products)
    total_price = sum(product['price'] for product in products)

    formatted_total_sum = "{:,.2f}".format(total_sum) if total_sum else '0.00'
    formatted_total_price = "{:,.2f}".format(total_price) if total_price else '0.00'

    for product in products:
        product['formatted_total_price'] = "{:,.2f}".format(product['total_price']) if product['total_price'] else '0.00'
        product['formatted_price'] = "{:,.2f}".format(product['price']) if product['price'] else '0.00'

    return formatted_total_sum, formatted_total_price


# Route for the 'products' page
@blueprint.route('/products')
def products():
    """Renders the 'products' page."""
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute('''
            SELECT *, (quantity * price) AS total_price
            FROM product_list
            ORDER BY name
        ''')
        products = cursor.fetchall()

        # Calculate totals and format them
        formatted_total_sum, formatted_total_price = calculate_formatted_totals(products)

    except Error as e:
        logging.error(f"Database error: {e}")
        flash("An error occurred while fetching products.", "error")
        return render_template('products/page-500.html'), 500

    finally:
        cursor.close()
        connection.close()

    return render_template('products/products.html',
                           
                           formatted_total_price=formatted_total_price,
                           products=products,
                           formatted_total_sum=formatted_total_sum,
                           segment='products')


# Define upload folder and allowed extensions
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# Ensure the upload folder exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    """Check if the uploaded file has a valid extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# Route to add a new product
@blueprint.route('/add_product', methods=['GET', 'POST'])
def add_product():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    # Fetch categories from the database
    cursor.execute('SELECT * FROM category_list')
    categories = cursor.fetchall()

    # Generate a random SKU
    random_num = random.randint(1005540, 9978799)

    # Ensure the SKU is unique
    while True:
        cursor.execute('SELECT * FROM product_list WHERE sku = %s', (random_num,))
        if not cursor.fetchone():
            break  # Unique SKU found
        random_num = random.randint(1005540, 9978799)

    if request.method == 'POST':
        # Retrieve form data
        category_id = request.form.get('category_id')
        sku = request.form.get('serial_no') or random_num
        price = request.form.get('price')
        name = request.form.get('name')
        description = request.form.get('description')
        quantity = request.form.get('quantity')
        reorder_level = request.form.get('reorder_level')

        # Check for existing product with the same name in the selected category
        cursor.execute('SELECT * FROM product_list WHERE category_id = %s AND name = %s', (category_id, name))
        existing_product = cursor.fetchone()

        if existing_product:
            flash("This product already exists in the selected category!", "danger")
        else:
            # Handle image upload
            image_file = request.files.get('image')
            image_filename = None  # Default if no image is uploaded

            if image_file and allowed_file(image_file.filename):
                filename = secure_filename(image_file.filename)
                image_filename = f"{random_num}_{filename}"  # Rename with SKU to avoid conflicts
                image_path = os.path.join(UPLOAD_FOLDER, image_filename)
                image_file.save(image_path)  # Save image

            # Insert new product into the database
            cursor.execute('''INSERT INTO product_list 
                (category_id, sku, price, name, description, quantity, reorder_level, image) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)''',
                (category_id, sku, price, name, description, quantity, reorder_level, image_filename))
            
            connection.commit()
            flash("Product successfully added!", "success")

    cursor.close()
    connection.close()

    return render_template('products/add_product.html', random_num=random_num,  categories=categories,segment='add_product')


# Route to edit an existing product
@blueprint.route('/edit_product/<int:product_id>', methods=['GET', 'POST'])
def edit_product(product_id):
    # Connect to the database
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    # Fetch the product data from the database
    cursor.execute('SELECT * FROM product_list WHERE ProductID = %s', (product_id,))
    product = cursor.fetchone()

    if not product:
        flash("Product not found!")
        return redirect(url_for('products_blueprint.products'))  # Redirect to a products list page or home

    # Fetch categories from the database for the dropdown
    cursor.execute('SELECT * FROM category_list')
    categories = cursor.fetchall()

    if request.method == 'POST':
        # Get the form data
        category_id = request.form.get('category_id')
        sku = request.form.get('serial_no')
        price = request.form.get('price')
        name = request.form.get('name')
        description = request.form.get('description')
        quantity = request.form.get('quantity')
        reorder_level = request.form.get('reorder_level')

        # Handle image upload
        image_filename = product['image']  # Default to existing image if no new one is uploaded
        image_file = request.files.get('image')

        if image_file and allowed_file(image_file.filename):
            filename = secure_filename(image_file.filename)
            image_filename = f"{product_id}_{filename}"  # Rename with product ID to avoid conflicts
            image_path = os.path.join(UPLOAD_FOLDER, image_filename)
            image_file.save(image_path)  # Save new image

        # Update the product data in the database
        cursor.execute(''' 
            UPDATE product_list
            SET category_id = %s, sku = %s, price = %s, name = %s, description = %s,
                quantity = %s, reorder_level = %s, image = %s, updated_at = CURRENT_TIMESTAMP
            WHERE ProductID = %s
        ''', (category_id, sku, price, name, description, quantity, reorder_level, image_filename, product_id))

        # Commit the transaction
        connection.commit()

        flash("Product updated successfully!")
        return redirect(url_for('products_blueprint.products'))  

    cursor.close()
    connection.close()

    return render_template('products/edit_product.html',  product=product, categories=categories)




# Route to restock product
@blueprint.route('/restock_product', methods=['GET', 'POST'])
def restock_product():
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    if request.method == 'POST':
        # Retrieve form data
        sku = request.form.get('sku')
        restock_quantity = int(request.form.get('restock_quantity'))

        # Check if the product exists
        cursor.execute('SELECT * FROM product_list WHERE sku = %s', (sku,))
        product = cursor.fetchone()

        if product:
            # Calculate new quantity
            new_quantity = product['quantity'] + restock_quantity

            # Update the product's quantity in the database
            cursor.execute('UPDATE product_list SET quantity = %s WHERE sku = %s', (new_quantity, sku))
            connection.commit()

            # Log the inventory change (restock)
            cursor.execute("""
                INSERT INTO inventory_logs (product_id, quantity_change, reason, log_date)
                VALUES (%s, %s, %s, NOW())
            """, (product['ProductID'], restock_quantity, 'restock'))
            connection.commit()

            # Flash a success message to the user
            flash(f"Product with SKU {sku} has been restocked successfully. New quantity: {new_quantity}.")
        else:
            # Flash an error message if the product does not exist
            flash(f"Product with SKU {sku} does not exist!")

    cursor.close()
    connection.close()

    return render_template('products/restock_product.html',segment='restock_product')



# Dynamic route for rendering other templates
@blueprint.route('/<template>')
def route_template(template):
    try:
        # Ensure the template ends with '.html' for correct render
        if not template.endswith('.html'):
            template += '.html'

        segment = get_segment(request)

        return render_template("products/" + template, segment=segment)

    except TemplateNotFound:
        return render_template('products/page-404.html'), 404

    except Exception as e:
        return render_template('products/page-500.html'), 500


def get_segment(request):
    """Extracts the last part of the URL path to identify the current page."""
    try:
        segment = request.path.split('/')[-1]
        if segment == '':
            segment = 'products'
        return segment

    except Exception as e:
        return None
