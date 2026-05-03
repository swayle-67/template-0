import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, flash, render_template, request, redirect, session
from flask_session import Session
from werkzeug.security import generate_password_hash, check_password_hash

from helpers import login_required, apology

app = Flask(__name__)

app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
app.secret_key = os.environ.get("SECRET_KEY", "stayeasy_secret_key")
Session(app)

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn

def db_execute(query, *args):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(query, args if args else None)
    conn.commit()
    try:
        results = cur.fetchall()
    except Exception:
        results = []
    cur.close()
    conn.close()
    return [dict(row) for row in results]

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            hash TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS listings (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            price REAL NOT NULL,
            location TEXT NOT NULL,
            guests INTEGER DEFAULT 1,
            image_url TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            listing_id INTEGER NOT NULL,
            check_in TEXT NOT NULL,
            check_out TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            listing_id INTEGER NOT NULL,
            rating INTEGER NOT NULL,
            comment TEXT
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

try:
    init_db()
    print("Database initialised successfully!")
except Exception as e:
    print(f"Database init failed: {e}")

@app.context_processor
def inject_session():
    return dict(session=session)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirmation = request.form.get("confirmation", "")

        if not username or not password or not confirmation:
            return apology("all fields required")

        if password != confirmation:
            return apology("passwords do not match")

        if len(password) < 6:
            return apology("password must be at least 6 characters")

        hash_pw = generate_password_hash(password)

        try:
            db_execute(
                "INSERT INTO users (username, hash) VALUES (%s, %s)",
                username, hash_pw
            )
        except Exception:
            return apology("username already taken")

        flash("Account created! Please log in.", "success")
        return redirect("/login")

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect("/")

    session.clear()

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            return apology("missing fields")

        rows = db_execute("SELECT * FROM users WHERE username = %s", username)

        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], password):
            return apology("invalid username or password")

        session["user_id"] = rows[0]["id"]
        session["username"] = rows[0]["username"]

        flash(f"Welcome back, {username}!", "success")
        return redirect("/")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/")
def index():
    q = request.args.get("q", "").strip()

    if q:
        listings = db_execute("""
            SELECT listings.*, users.username
            FROM listings
            JOIN users ON users.id = listings.user_id
            WHERE listings.title LIKE %s OR listings.location LIKE %s
        """, f"%{q}%", f"%{q}%")
    else:
        listings = db_execute("""
            SELECT listings.*, users.username
            FROM listings
            JOIN users ON users.id = listings.user_id
            ORDER BY listings.id DESC
        """)

    return render_template("index.html", listings=listings, q=q)


@app.route("/listings/<int:listing_id>")
def listing_detail(listing_id):
    rows = db_execute("""
        SELECT listings.*, users.username
        FROM listings
        JOIN users ON users.id = listings.user_id
        WHERE listings.id = %s
    """, listing_id)

    if not rows:
        return apology("listing not found", 404)

    listing = rows[0]

    reviews = db_execute("""
        SELECT reviews.*, users.username
        FROM reviews
        JOIN users ON users.id = reviews.user_id
        WHERE reviews.listing_id = %s
        ORDER BY reviews.id DESC
    """, listing_id)

    avg_rating = None
    if reviews:
        avg_rating = round(sum(r["rating"] for r in reviews) / len(reviews), 1)

    already_reviewed = False
    if session.get("user_id"):
        existing = db_execute(
            "SELECT id FROM reviews WHERE user_id = %s AND listing_id = %s",
            session["user_id"], listing_id
        )
        already_reviewed = len(existing) > 0

    return render_template(
        "listings.html",
        listing=listing,
        reviews=reviews,
        avg_rating=avg_rating,
        already_reviewed=already_reviewed
    )


@app.route("/create", methods=["GET", "POST"])
@login_required
def create():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        price = request.form.get("price", "")
        location = request.form.get("location", "").strip()
        guests = request.form.get("guests", "1")
        image_url = request.form.get("image_url", "").strip()

        if not title or not description or not price or not location:
            return apology("all required fields must be filled")

        try:
            price = float(price)
            if price <= 0:
                return apology("price must be a positive number")
        except ValueError:
            return apology("invalid price")

        try:
            guests = int(guests)
            if guests < 1:
                guests = 1
        except ValueError:
            guests = 1

        db_execute("""
            INSERT INTO listings (user_id, title, description, price, location, guests, image_url)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, session["user_id"], title, description, price, location, guests, image_url)

        flash("Listing created successfully!", "success")
        return redirect("/")

    return render_template("create.html")


@app.route("/delete/<int:listing_id>", methods=["POST"])
@login_required
def delete_listing(listing_id):
    rows = db_execute("SELECT user_id FROM listings WHERE id = %s", listing_id)

    if not rows or rows[0]["user_id"] != session["user_id"]:
        return apology("not authorized", 403)

    db_execute("DELETE FROM bookings WHERE listing_id = %s", listing_id)
    db_execute("DELETE FROM reviews WHERE listing_id = %s", listing_id)
    db_execute("DELETE FROM listings WHERE id = %s", listing_id)

    flash("Listing deleted.", "info")
    return redirect("/")


@app.route("/book/<int:listing_id>", methods=["POST"])
@login_required
def book(listing_id):
    rows = db_execute("SELECT * FROM listings WHERE id = %s", listing_id)

    if not rows:
        return apology("listing not found", 404)

    if rows[0]["user_id"] == session["user_id"]:
        return apology("you cannot book your own listing")

    check_in = request.form.get("check_in")
    check_out = request.form.get("check_out")

    if not check_in or not check_out:
        return apology("please select check-in and check-out dates")

    if check_in >= check_out:
        return apology("check-out must be after check-in")

    db_execute("""
        INSERT INTO bookings (user_id, listing_id, check_in, check_out)
        VALUES (%s, %s, %s, %s)
    """, session["user_id"], listing_id, check_in, check_out)

    flash("Booking confirmed!", "success")
    return redirect("/bookings")


@app.route("/bookings")
@login_required
def bookings():
    user_bookings = db_execute("""
        SELECT bookings.*, listings.title, listings.location, listings.price, listings.image_url
        FROM bookings
        JOIN listings ON listings.id = bookings.listing_id
        WHERE bookings.user_id = %s
        ORDER BY bookings.check_in DESC
    """, session["user_id"])

    return render_template("bookings.html", bookings=user_bookings)


@app.route("/review/<int:listing_id>", methods=["POST"])
@login_required
def review(listing_id):
    rows = db_execute("SELECT id FROM listings WHERE id = %s", listing_id)

    if not rows:
        return apology("listing not found", 404)

    existing = db_execute(
        "SELECT id FROM reviews WHERE user_id = %s AND listing_id = %s",
        session["user_id"], listing_id
    )

    if existing:
        flash("You have already reviewed this listing.", "error")
        return redirect(f"/listings/{listing_id}")

    rating = request.form.get("rating")
    comment = request.form.get("comment", "").strip()

    if not rating:
        return apology("please select a rating")

    try:
        rating = int(rating)
        if rating < 1 or rating > 5:
            return apology("rating must be between 1 and 5")
    except ValueError:
        return apology("invalid rating")

    db_execute("""
        INSERT INTO reviews (user_id, listing_id, rating, comment)
        VALUES (%s, %s, %s, %s)
    """, session["user_id"], listing_id, rating, comment)

    flash("Review submitted!", "success")
    return redirect(f"/listings/{listing_id}")