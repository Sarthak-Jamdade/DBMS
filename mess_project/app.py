import email

from flask import Flask, render_template, request, redirect,session
from datetime import date
import mysql.connector

app = Flask(__name__)
app.secret_key = "mess_secret_key"

def get_connection():
    return mysql.connector.connect(
        host="localhost",
        user="messuser",
        password="1234",
        database="mess_management"
    )

@app.route("/")
def home():
    return render_template("login.html")

@app.route("/login", methods=["POST"])
def login():
    username = request.form["username"]
    
    password = request.form["password"]

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM users WHERE username=%s AND password=%s",
        (username, password)
    )

    user = cursor.fetchone()

    cursor.close()
    conn.close()

    if user:
        session["username"] = user["username"]
        session["role"] = user["role"]
        if user["role"] == "admin":
            return redirect("/admin_dashboard")
        else:
            return redirect("/student_dashboard")
    else:
        return "Invalid Login"

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]

        conn = get_connection()
        cursor = conn.cursor()

        #cheak if email is already registered
        cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
        existing_email = cursor.fetchone()
        if existing_email:
            cursor.close()
            conn.close()
            return "Email already registered. <a href='/register'>Try Again</a>"

        # Check if username is already taken
        cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
        existing_username = cursor.fetchone()
        if existing_username:
            cursor.close()
            conn.close()
            return "Username already taken. <a href='/register'>Try Again</a>"


        # Insert into users
        cursor.execute("""
        INSERT INTO users (username, email, password, role)
        VALUES (%s, %s, %s, 'student')
        """, (username, email, password))

        # Get user_id
        user_id = cursor.lastrowid

        # Insert into students table
        cursor.execute("""
        INSERT INTO students (student_id, name, email)
        VALUES (%s, %s, %s)
        """, (user_id, username, email))

        conn.commit()
        cursor.close()
        conn.close()
        return redirect("/")

    return render_template("register.html")

@app.route("/admin_dashboard")
def admin_dashboard():
    if "role" in session and session["role"] == "admin":

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # Total Students
        cursor.execute("""
            SELECT COUNT(*) AS total_students
            FROM users
            WHERE role = 'student'
        """)
        total_students = cursor.fetchone()["total_students"]

        # Total Active Subscriptions
        cursor.execute("""
            SELECT COUNT(*) AS total_active
            FROM subscriptions
            WHERE status = 'Approved'
            AND end_date >= CURDATE()
        """)
        total_active = cursor.fetchone()["total_active"]

        # Total Pending Requests
        cursor.execute("""
            SELECT COUNT(*) AS total_pending
            FROM subscriptions
            WHERE status = 'Pending'
        """)
        total_pending = cursor.fetchone()["total_pending"]

        # Pending Request Table
        cursor.execute("""
            SELECT s.subscription_id,
                   u.username,
                   u.email,
                   m.plan_name,
                   s.status
            FROM subscriptions s
            JOIN users u ON s.student_id = u.user_id
            JOIN meal_plans m ON s.plan_id = m.plan_id
            WHERE s.status = 'Pending'
        """)
        requests = cursor.fetchall()

        cursor.close()
        conn.close()

        return render_template(
            "admin_dashboard.html",
            total_students=total_students,
            total_active=total_active,
            total_pending=total_pending,
            requests=requests
        )

    return redirect("/")


@app.route("/approve/<int:sub_id>")
def approve(sub_id):

    if session.get("role") != "admin":
        return redirect("/")

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE subscriptions
        SET status = 'Approved'
        WHERE subscription_id = %s
    """, (sub_id,))

    conn.commit()
    cursor.close()
    conn.close()

    return redirect("/admin_dashboard")

@app.route("/reject/<int:sub_id>")
def reject(sub_id):
    if "role" in session and session["role"] == "admin":

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE subscriptions
            SET status = 'Rejected'
            WHERE subscription_id = %s
        """, (sub_id,))

        conn.commit()
        cursor.close()
        conn.close()

        return redirect("/admin_dashboard")

    return redirect("/")

@app.route("/student_dashboard")
def student_dashboard():
    if "role" in session and session["role"] == "student":

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # Get student subscription + plan (JOIN)
        cursor.execute("""
            SELECT s.subscription_id, s.end_date, m.plan_name
            FROM subscriptions s
            JOIN meal_plans m ON s.plan_id = m.plan_id
            JOIN users u ON u.username = %s
            WHERE s.student_id = u.user_id
            ORDER BY s.subscription_id DESC
            LIMIT 1
        """, (session["username"],))

        subscription = cursor.fetchone()

        # Default values
        plan_name = "No Plan"
        days_remaining = 0
        total_attendance = 0
        pending_payment = 0

        if subscription:
            plan_name = subscription["plan_name"]
            end_date = subscription["end_date"]

            days_remaining = (end_date - date.today()).days

            # Count attendance
            cursor.execute("""
                SELECT COUNT(*) AS total
                FROM attendance
                WHERE subscription_id = %s
            """, (subscription["subscription_id"],))
            total_attendance = cursor.fetchone()["total"]

            # Sum payments
            cursor.execute("""
                SELECT SUM(amount) AS total
                FROM payments
                WHERE subscription_id = %s
            """, (subscription["subscription_id"],))
            payment = cursor.fetchone()["total"]

            pending_payment = payment if payment else 0

        cursor.close()
        conn.close()

        return render_template(
            "student_dashboard.html",
            plan_name=plan_name,
            days_remaining=days_remaining,
            total_attendance=total_attendance,
            pending_payment=pending_payment
        )

    return redirect("/")

from datetime import date

@app.route("/my_subscription")
def my_subscription():
    if "role" in session and session["role"] == "student":

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # Get student ID
        cursor.execute(
            "SELECT user_id FROM users WHERE username=%s",
            (session["username"],)
        )
        student = cursor.fetchone()
        student_id = student["user_id"]

        # Approved Plan
        cursor.execute("""
            SELECT s.*, m.plan_name
            FROM subscriptions s
            JOIN meal_plans m ON s.plan_id = m.plan_id
            WHERE s.student_id=%s
            AND s.status='Approved'
            AND s.end_date >= CURDATE()
        """, (student_id,))
        approved = cursor.fetchone()

        days_left = None
        if approved:
            days_left = (approved["end_date"] - date.today()).days

        # Pending Plan
        cursor.execute("""
            SELECT m.plan_name
            FROM subscriptions s
            JOIN meal_plans m ON s.plan_id = m.plan_id
            WHERE s.student_id=%s
            AND s.status='Pending'
        """, (student_id,))
        pending = cursor.fetchone()

        # History
        cursor.execute("""
            SELECT m.plan_name, s.start_date, s.end_date, s.status
            FROM subscriptions s
            JOIN meal_plans m ON s.plan_id = m.plan_id
            WHERE s.student_id=%s
            ORDER BY s.subscription_id DESC
        """, (student_id,))
        history = cursor.fetchall()

        # Plans
        cursor.execute("SELECT * FROM meal_plans")
        plans = cursor.fetchall()

        cursor.close()
        conn.close()

        return render_template(
            "my_subscription.html",
            active=approved,
            pending=pending,
            days_left=days_left,
            history=history,
            plans=plans
        )

    return redirect("/")

@app.route("/buy_plan", methods=["POST"])
def buy_plan():
    if "role" in session and session["role"] == "student":

        plan_id = request.form["plan_id"]

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # Get student id
        cursor.execute(
            "SELECT user_id FROM users WHERE username=%s",
            (session["username"],)
        )
        student = cursor.fetchone()
        student_id = student["user_id"]

        # 🔎 CHECK if already has Pending or Active
        cursor.execute("""
            SELECT * FROM subscriptions
            WHERE student_id=%s
            AND (
                status='Pending'
                OR
                (status='Approved' AND end_date >= CURDATE())
            )
        """, (student_id,))

        existing = cursor.fetchone()

        if existing:
            cursor.close()
            conn.close()
            return redirect("/my_subscription")

        # Get duration
        cursor.execute(
            "SELECT duration_days FROM meal_plans WHERE plan_id=%s",
            (plan_id,)
        )
        plan = cursor.fetchone()
        duration = plan["duration_days"]

        # Insert Pending request
        cursor.execute("""
            INSERT INTO subscriptions
            (student_id, plan_id, start_date, end_date, status)
            VALUES (%s, %s, CURDATE(),
            DATE_ADD(CURDATE(), INTERVAL %s DAY),
            'Pending')
        """, (student_id, plan_id, duration))

        conn.commit()
        cursor.close()
        conn.close()

        return redirect("/my_subscription")

    return redirect("/")

@app.route("/admin_attendance")
def admin_attendance():

    if session.get("role") != "admin":
        return redirect("/")

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT s.subscription_id,
               u.username,
               m.plan_name,

               EXISTS(
                   SELECT 1 FROM attendance a
                   WHERE a.subscription_id = s.subscription_id
                   AND a.date = CURDATE()
                   AND a.meal_type = 'Breakfast'
               ) AS breakfast_marked,

               EXISTS(
                   SELECT 1 FROM attendance a
                   WHERE a.subscription_id = s.subscription_id
                   AND a.date = CURDATE()
                   AND a.meal_type = 'Lunch'
               ) AS lunch_marked,

               EXISTS(
                   SELECT 1 FROM attendance a
                   WHERE a.subscription_id = s.subscription_id
                   AND a.date = CURDATE()
                   AND a.meal_type = 'Dinner'
               ) AS dinner_marked

        FROM subscriptions s
        JOIN users u ON s.student_id = u.user_id
        JOIN meal_plans m ON s.plan_id = m.plan_id
        WHERE s.status = 'Approved'
        AND s.end_date >= CURDATE()
    """)

    students = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("admin_attendance.html", students=students)

@app.route("/mark_attendance", methods=["POST"])
def mark_attendance():

    if session.get("role") != "admin":
        return redirect("/")

    subscription_id = request.form["subscription_id"]
    meal_type = request.form["meal_type"]

    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            INSERT INTO attendance (subscription_id, date, meal_type)
            VALUES (%s, CURDATE(), %s)
        """, (subscription_id, meal_type))

        connection.commit()

    except:
        print("Attendance already marked")

    cursor.close()
    connection.close()

    return redirect("/admin_attendance")

if __name__ == "__main__":
    app.run(debug=True)