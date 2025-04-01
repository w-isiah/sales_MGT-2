from flask import render_template, redirect, request, url_for, flash, session,current_app,jsonify
from apps import get_db_connection
from apps.authentication import blueprint
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import mysql.connector

# Access the upload folder from the current Flask app configuration
def allowed_file(filename):
    """Check if the uploaded file has a valid extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']



@blueprint.route('/', methods=['GET', 'POST'])
def route_default():
    return redirect(url_for('authentication_blueprint.login'))


@blueprint.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        try:
            # Get DB connection using context manager
            with get_db_connection() as connection:
                with connection.cursor(dictionary=True) as cursor:
                    # Retrieve the user by username
                    cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
                    user = cursor.fetchone()

                    if user:
                        # Compare the password directly (insecure)
                        if user['password'] == password:  # Direct comparison (no hashing)
                            try:
                                # Insert a new login record in the user_activity table
                                cursor.execute("INSERT INTO user_activity (user_id, login_time) VALUES (%s, %s)", 
                                               (user['id'], datetime.utcnow()))
                            
                                # Set user as online (update `is_online` field to 1)
                                cursor.execute("UPDATE users SET is_online = 1 WHERE id = %s", (user['id'],))
                                connection.commit()  # Commit the changes to the database

                                # Storing user session data
                                session.update({
                                    'loggedin': True,
                                    'id': user['id'],
                                    'username': user['username'],
                                    'profile_image': user['profile_image'],
                                    'first_name': user['first_name'],
                                    'role': user['role'],
                                    'last_activity': datetime.utcnow()
                                })
                                session.permanent = True  # Make the session permanent

                                flash('Login successful!', 'success')
                                return redirect(url_for('home_blueprint.index'))  # Redirect to home page after successful login
                            except Exception as e:
                                # Log the error to the console
                                print(f"Error during session handling or user activity logging: {str(e)}")
                                flash('An error occurred during the login process. Please try again later.', 'danger')
                                return redirect(url_for('authentication_blueprint.login'))  # Redirect back to login page in case of error

                        else:
                            flash('Incorrect password.', 'danger')
                            return redirect(url_for('authentication_blueprint.login'))  # Redirect to login if password is incorrect
                    else:
                        
                        
                        flash('Username not found', 'danger')

                        return redirect(url_for('authentication_blueprint.login'))  # Redirect to login if username is not found

        except Exception as e:
            flash(f"An error occurred: {str(e)}", 'danger')  # Handle any database or other errors

    return render_template('accounts/login.html')  # Render the login page on GET request





@blueprint.route('/logout')
def logout():
    # Before logging out, set the logout time in the user_activity table
    if 'username' in session:
        username = session['username']

        try:
            with get_db_connection() as connection:
                with connection.cursor(dictionary=True) as cursor:
                    # Update the logout time for the current active session
                    cursor.execute("UPDATE user_activity SET logout_time = %s WHERE user_id = %s AND logout_time IS NULL", 
                                   (datetime.utcnow(), session['id']))
                    
                    # Set user as offline (update `is_online` field to 0)
                    cursor.execute("UPDATE users SET is_online = 0 WHERE id = %s", (session['id'],))
                    connection.commit()  # Commit the changes to the database
        except Exception as e:
            flash(f"An error occurred while updating the logout status: {str(e)}", 'danger')

    # Log out the user by clearing the session
    session.clear()  # Remove session data
    flash('You have been logged out.', 'success')
    return redirect(url_for('authentication_blueprint.login'))









@blueprint.route('/manage_users')
def manage_users():
    try:
        with get_db_connection() as connection:
            with connection.cursor(dictionary=True) as cursor:
                # Check if the user has admin privileges
                if session.get('role') == 'admin':
                    cursor.execute("SELECT * FROM users WHERE role != 'admin'")
                else:
                    flash('You do not have permission to access this page.', 'warning')
                    return redirect(url_for('authentication_blueprint.index'))

                users = cursor.fetchall()
                num = len(users)

    except Exception as e:
        flash(f"Error fetching data: {str(e)}", 'danger')
        return redirect(url_for('home_blueprint.index'))

    return render_template('accounts/manage_users.html', num=num, users=users)




# New route for getting user status
@blueprint.route('/get_user_status/<int:user_id>', methods=['GET'])
def get_user_status(user_id):
    try:
        with get_db_connection() as connection:
            with connection.cursor(dictionary=True) as cursor:
                cursor.execute("SELECT is_online FROM users WHERE id = %s", (user_id,))
                user = cursor.fetchone()

                if user:
                    return jsonify({'status': 'online' if user['is_online'] else 'offline'})
                else:
                    return jsonify({'status': 'offline'})  # Default to offline if user not found
    except Exception as e:
        return jsonify({'status': 'offline'})







@blueprint.route('/activity_logs/<int:id>', methods=['GET', 'POST'])
def activity_logs(id):
    try:
        with get_db_connection() as connection:
            with connection.cursor(dictionary=True) as cursor:
                # SQL JOIN query to combine user_activity and users tables
                query = """
                SELECT ua.login_time, ua.logout_time, u.username, u.first_name, u.last_name
                FROM user_activity ua
                JOIN users u ON ua.user_id = u.id
                WHERE ua.user_id = %s
                ORDER BY ua.login_time DESC
                """
                cursor.execute(query, (id,))
                activities = cursor.fetchall()

                return render_template('accounts/activity_logs.html', activities=activities)
    except Exception as e:
        flash(f"An error occurred: {str(e)}", 'danger')
        return redirect(url_for('authentication_blueprint.index'))










# add user

@blueprint.route('/add_user', methods=['GET', 'POST'])
def add_user():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        other_name = request.form['other_name']
        
        # Handle profile image upload (if present)
        profile_image = None
        if 'profile_image' in request.files:
            image_file = request.files['profile_image']
            if image_file and allowed_file(image_file.filename):
                profile_image = handle_image_upload(image_file)

        # Password hashing for security
        hashed_password = generate_password_hash(password)

        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                # Check if the username already exists
                cursor.execute('SELECT 1 FROM users WHERE username = %s', (username,))
                if cursor.fetchone():
                    flash('Username already exists. Please choose a different one.', 'danger')
                    return render_template('accounts/add_user.html', role=session.get('role'), username=session.get('username'))

                try:
                    cursor.execute(''' 
                        INSERT INTO users (username, password, role, first_name, last_name, other_name, profile_image)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ''', (username, hashed_password, role, first_name, last_name, other_name, profile_image))
                    connection.commit()
                    flash('User added successfully!', 'success')
                except mysql.connector.Error as err:
                    flash(f'Error: {err}', 'danger')

        return redirect(url_for('home_blueprint.index'))  # Redirect to user management page

   
    return render_template("accounts/add_user.html", role=session.get('role'), username=session.get('username'))





# Handle the form submission
@blueprint.route('/edit_user/<int:id>', methods=['GET', 'POST'])
def edit_user(id):
    with get_db_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            if request.method == 'POST':
                # Getting user data from the form
                username = request.form['username']
                first_name = request.form['first_name']
                last_name = request.form['last_name']
                other_name = request.form['other_name']
                password = request.form['password']
                role = request.form['role']
                profile_image = request.files.get('profile_image')

                

                # Hash the password only if it was provided (otherwise, keep the existing password)
                hashed_password = generate_password_hash(password) if password else get_user_password(cursor, id)

                # Handle profile image if uploaded
                profile_image_path = handle_profile_image(cursor, profile_image, id)

                # Update the user information in the database
                try:
                    cursor.execute('''
                        UPDATE users 
                        SET username = %s, first_name = %s, last_name = %s, other_name = %s, password = %s, role = %s, 
                            profile_image = %s
                        WHERE id = %s
                    ''', (
                        username, first_name, last_name, other_name, hashed_password, role, 
                        profile_image_path, id
                    ))
                    connection.commit()
                    flash('User updated successfully!', 'success')
                except mysql.connector.Error as err:
                    flash(f'Error: {err}', 'danger')

                return redirect(url_for('home_blueprint.index'))  # Redirect back to the home page or user list

            # Retrieve the user information from the database to pre-fill the form
            cursor.execute('SELECT * FROM users WHERE id = %s', (id,))
            user = cursor.fetchone()

    return render_template("accounts/edit_user.html", user=user)


def get_user_password(cursor, user_id):
    cursor.execute('SELECT password FROM users WHERE id = %s', (user_id,))
    return cursor.fetchone()['password']

def handle_profile_image(cursor, profile_image, user_id):
    if profile_image and allowed_file(profile_image.filename):
        filename = secure_filename(profile_image.filename)
        file_path =os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        profile_image.save(file_path)
        return filename
    else:
        cursor.execute('SELECT profile_image FROM users WHERE id = %s', (user_id,))
        return cursor.fetchone()['profile_image']




# Route for deleting a user
@blueprint.route('/delete_user/<int:id>', methods=['GET'])
def delete_user(id):
    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            try:
                cursor.execute('DELETE FROM users WHERE id = %s', (id,))
                connection.commit()
                flash('User deleted successfully!', 'success')
            except mysql.connector.Error as err:
                flash(f'Error: {err}', 'danger')

    return redirect(url_for('home_blueprint.index'))









# Image upload helper function
def handle_image_upload(image_file):
    filename = secure_filename(image_file.filename)
    #profile_image_path = os.path.join(UPLOAD_FOLDER, filename)
    profile_image_path = os.path.join(current_app.config['UPLOAD_FOLDER'])
    

    try:
        img = Image.open(image_file)
        max_width, max_height = 500, 500
        width, height = img.size
        if width > max_width or height > max_height:
            img.thumbnail((max_width, max_height))
            img.save(profile_image_path, optimize=True, quality=85)
        else:
            img.save(profile_image_path)
    except Exception as e:
        flash(f"Error processing image: {e}", 'danger')
        return None

    return os.path.join(UPLOAD_FOLDER, filename)



    # end of  add user 

@blueprint.route('/edit_user_profile/<int:id>', methods=['GET', 'POST'])
def edit_user_profile(id):
    with get_db_connection() as connection:
        with connection.cursor(dictionary=True) as cursor:
            
            # POST request - Handle profile update
            if request.method == 'POST':
                # Collect form data
                username = request.form['username']
                first_name = request.form['first_name']
                last_name = request.form['last_name']
                other_name = request.form['other_name']
                password = request.form['password']
                profile_image = request.files.get('profile_image')

                # Hash new password if provided; otherwise, keep the current password
                hashed_password = generate_password_hash(password) if password else get_user_password(cursor, id)
                
                # Process profile image
                profile_image_path = handle_profile_image(cursor, profile_image, id)

                try:
                    # Update user details in the database
                    cursor.execute('''
                        UPDATE users 
                        SET username = %s, first_name = %s, last_name = %s, other_name = %s, password = %s, profile_image = %s
                        WHERE id = %s
                    ''', (username, first_name, last_name, other_name, hashed_password, profile_image_path, id))
                    connection.commit()
                    flash('User updated successfully!', 'success')
                except mysql.connector.Error as err:
                    flash(f'Error: {err}', 'danger')

                # Redirect after successful update
                return redirect(url_for('home_blueprint.index'))

            # GET request - Fetch user data to populate the edit form
            cursor.execute('SELECT * FROM users WHERE id = %s', (id,))
            user = cursor.fetchone()

            # If user not found, show error and redirect
            if not user:
                flash('User not found!', 'danger')
                return redirect(url_for('home_blueprint.index'))

    
    return render_template('accounts/edit_user_profile.html',user=user)











# Error Handlers
@blueprint.errorhandler(403)
def access_forbidden(error):
    return render_template('home/page-403.html'), 403

@blueprint.errorhandler(404)
def not_found_error(error):
    return render_template('home/page-404.html'), 404

@blueprint.errorhandler(500)
def internal_error(error):
    return render_template('home/page-500.html'), 500
