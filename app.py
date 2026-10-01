from flask import Flask, render_template, request, redirect, url_for, session
import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = "food_waste_secret_key"


# -----------------------------
# MySQL Database Connection
# -----------------------------
def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME")
    )

# -----------------------------
# Home Page
# -----------------------------
@app.route("/")
def home():
    return render_template("index.html")


# -----------------------------
# Register
# -----------------------------
@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]
        account_type = request.form["account_type"]
        phone = request.form["phone"]
        address = request.form["address"]

        db = get_db_connection()
        cursor = db.cursor()

        try:
            query = """
                INSERT INTO users
                (name, email, password, account_type, phone, address)
                VALUES (%s, %s, %s, %s, %s, %s)
            """

            values = (
                name,
                email,
                password,
                account_type,
                phone,
                address
            )

            cursor.execute(query, values)
            db.commit()

        except mysql.connector.Error as error:
            db.rollback()
            return f"Registration failed: {error}"

        finally:
            cursor.close()
            db.close()

        return redirect(url_for("login"))

    return render_template("register.html")


# -----------------------------
# Login
# -----------------------------
@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        query = """
            SELECT * FROM users
            WHERE email = %s AND password = %s
        """

        cursor.execute(query, (email, password))
        user = cursor.fetchone()

        cursor.close()
        db.close()

        if user:

            session["user_id"] = user["id"]
            session["name"] = user["name"]
            session["account_type"] = user["account_type"]

            if user["account_type"] == "restaurant":
                return redirect(url_for("restaurant_dashboard"))

            else:
                return redirect(url_for("ngo_dashboard"))

        return "Invalid email or password"

    return render_template("login.html")


# -----------------------------
# Restaurant Dashboard
@app.route("/restaurant/dashboard")
def restaurant_dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if session["account_type"] != "restaurant":
        return redirect(url_for("login"))

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    query = """
        SELECT *
        FROM donations
        WHERE restaurant_id = %s
        ORDER BY created_at DESC
    """

    cursor.execute(query, (session["user_id"],))
    donations = cursor.fetchall()

    total_donations = len(donations)
    total_quantity = sum(donation["quantity"] for donation in donations)

    cursor.close()
    db.close()

    return render_template(
        "restaurant_dashboard.html",
        name=session["name"],
        donations=donations,
        total_donations=total_donations,
        total_quantity=total_quantity
    )


@app.route("/restaurant/post-donation", methods=["GET", "POST"])
def post_donation():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("account_type") != "restaurant":
        return redirect(url_for("login"))

    if request.method == "POST":

        food_name = request.form["food_name"]
        description = request.form["description"]
        quantity = request.form["quantity"]
        food_category = request.form["food_category"]
        pickup_location = request.form["pickup_location"]
        available_until = request.form["available_until"]

        db = get_db_connection()
        cursor = db.cursor()

        query = """
            INSERT INTO donations
            (
                restaurant_id,
                food_name,
                description,
                quantity,
                food_category,
                pickup_location,
                available_until
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """

        cursor.execute(query, (
            session["user_id"],
            food_name,
            description,
            quantity,
            food_category,
            pickup_location,
            available_until
        ))

        db.commit()

        cursor.close()
        db.close()

        return redirect(url_for("restaurant_dashboard"))

    return render_template("post_donation.html")

@app.route("/restaurant/requests")
def restaurant_requests():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("account_type") != "restaurant":
        return redirect(url_for("login"))

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    query = """
        SELECT
            donation_requests.id AS request_id,
            donation_requests.message,
            donation_requests.status AS request_status,
            donation_requests.requested_at,
            donations.id AS donation_id,
            donations.food_name,
            donations.quantity,
            donations.food_category,
            users.name AS ngo_name,
            users.email AS ngo_email
        FROM donation_requests
        JOIN donations
            ON donation_requests.donation_id = donations.id
        JOIN users
            ON donation_requests.ngo_id = users.id
        WHERE donations.restaurant_id = %s
        ORDER BY donation_requests.requested_at DESC
    """

    cursor.execute(query, (session["user_id"],))
    requests = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "restaurant_requests.html",
        name=session["name"],
        requests=requests
    )

@app.route("/restaurant/request/<int:request_id>/<action>", methods=["POST"])
def update_request(request_id, action):

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("account_type") != "restaurant":
        return redirect(url_for("login"))

    if action not in ["accept", "reject"]:
        return redirect(url_for("restaurant_requests"))

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    # Check that this request belongs to this restaurant
    query = """
        SELECT donation_requests.id,
               donation_requests.donation_id
        FROM donation_requests
        JOIN donations
            ON donation_requests.donation_id = donations.id
        WHERE donation_requests.id = %s
        AND donations.restaurant_id = %s
    """

    cursor.execute(
        query,
        (request_id, session["user_id"])
    )

    request_data = cursor.fetchone()

    if not request_data:
        cursor.close()
        db.close()
        return redirect(url_for("restaurant_requests"))

    if action == "accept":

        new_status = "Accepted"

        donation_status = "Completed"

    else:

        new_status = "Rejected"

        donation_status = "Available"

    # Update request
    update_request = """
        UPDATE donation_requests
        SET status = %s
        WHERE id = %s
    """

    cursor.execute(
        update_request,
        (new_status, request_id)
    )

    # Update donation
    update_donation = """
        UPDATE donations
        SET status = %s
        WHERE id = %s
    """

    cursor.execute(
        update_donation,
        (donation_status, request_data["donation_id"])
    )

    db.commit()

    cursor.close()
    db.close()

    return redirect(url_for("restaurant_requests"))

# -----------------------------
# NGO Dashboard
@app.route("/ngo/dashboard")
def ngo_dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session["account_type"] != "ngo":
        return redirect(url_for("login"))

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    query = """
        SELECT *
        FROM donations
        WHERE status = 'Available'
        ORDER BY created_at DESC
    """

    cursor.execute(query)
    donations = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "ngo_dashboard.html",
        name=session["name"],
        donations=donations
    )

@app.route("/ngo/request-food/<int:donation_id>", methods=["POST"])
def request_food(donation_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("account_type") != "ngo":
        return redirect(url_for("login"))

    message = request.form.get("message", "")

    db = get_db_connection()
    cursor = db.cursor()

    # Check whether this NGO has already requested this donation
    check_query = """
        SELECT id
        FROM donation_requests
        WHERE donation_id = %s
        AND ngo_id = %s
        AND status = 'Pending'
    """

    cursor.execute(
        check_query,
        (donation_id, session["user_id"])
    )

    existing_request = cursor.fetchone()

    if existing_request:
        cursor.close()
        db.close()

        return redirect(url_for("ngo_dashboard"))

    # Create new request
    insert_query = """
        INSERT INTO donation_requests
        (donation_id, ngo_id, message)
        VALUES (%s, %s, %s)
    """

    cursor.execute(
        insert_query,
        (
            donation_id,
            session["user_id"],
            message
        )
    )

    # Change donation status
    update_query = """
        UPDATE donations
        SET status = 'Requested'
        WHERE id = %s
        AND status = 'Available'
    """

    cursor.execute(update_query, (donation_id,))

    db.commit()

    cursor.close()
    db.close()

    return redirect(url_for("ngo_dashboard"))
@app.route("/ngo/requests")
def ngo_requests():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("account_type") != "ngo":
        return redirect(url_for("login"))

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    query = """
        SELECT
            donation_requests.id AS request_id,
            donation_requests.message,
            donation_requests.status AS request_status,
            donation_requests.requested_at,
            donations.food_name,
            donations.description,
            donations.quantity,
            donations.food_category,
            donations.pickup_location,
            donations.available_until,
            users.name AS restaurant_name
        FROM donation_requests
        JOIN donations
            ON donation_requests.donation_id = donations.id
        JOIN users
            ON donations.restaurant_id = users.id
        WHERE donation_requests.ngo_id = %s
        ORDER BY donation_requests.requested_at DESC
    """

    cursor.execute(query, (session["user_id"],))
    requests = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "ngo_requests.html",
        name=session["name"],
        requests=requests
    )

# -----------------------------
# Donation History
# -----------------------------
@app.route("/history")
def donation_history():

    if "user_id" not in session:
        return redirect(url_for("login"))

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    if session["account_type"] == "restaurant":

        query = """
        SELECT *
        FROM donations
        WHERE restaurant_id = %s
        ORDER BY created_at DESC
        """

        cursor.execute(query, (session["user_id"],))

    else:

        query = """
        SELECT d.food_name,
               d.quantity,
               d.food_category,
               dr.status,
               dr.requested_at
        FROM donation_requests dr
        JOIN donations d
            ON dr.donation_id = d.id
        WHERE dr.ngo_id = %s
        ORDER BY dr.requested_at DESC
        """

        cursor.execute(query, (session["user_id"],))

    history = cursor.fetchall()

    cursor.close()
    db.close()

    return render_template(
        "history.html",
        history=history,
        user_type=session["account_type"]
    )
# -----------------------------
# Logout
# -----------------------------
@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("home"))


# -----------------------------
# Run Application
# -----------------------------
if __name__ == "__main__":
    app.run(debug=True)
