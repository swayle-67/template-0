import os
from cs50 import SQL
from flask import Flask, flash, render_template, request, redirect, session
from flask_session import Session
from werkzeug.security import generate_password_hash, check_password_hash

from helpers import login_required, apology

app = Flask(__name__)

app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
app.secret_key = "stayeasy_secret_key"
Session(app)

db = SQL("sqlite:///airbnb.db")


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
            db.execute(
                "INSERT INTO users (username, hash) VALUES (?, ?)",
                username, hash_pw
            )
        except:
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

        rows = db.execute("SELECT * FROM users WHERE username = ?", username)

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
        listings = db.execute("""
            SELECT listings.*, users.username
            FROM listings
            JOIN users ON users.id = listings.user_id
            WHERE listings.title LIKE ? OR listings.location LIKE ?
        """, f"%{q}%", f"%{q}%")
    else:
        listings = db.execute("""
            SELECT listings.*, users.username
            FROM listings
            JOIN users ON users.id = listings.user_id
            ORDER BY listings.id DESC
        """)

    return render_template("index.html", listings=listings, q=q)


@app.route("/listings/<int:listing_id>")
def listing_detail(listing_id):
    rows = db.execute("""
        SELECT listings.*, users.username
        FROM listings
        JOIN users ON users.id = listings.user_id
        WHERE listings.id = ?
    """, listing_id)

    if not rows:
        return apology("listing not found", 404)

    listing = rows[0]

    reviews = db.execute("""
        SELECT reviews.*, users.username
        FROM reviews
        JOIN users ON users.id = reviews.user_id
        WHERE reviews.listing_id = ?
        ORDER BY reviews.id DESC
    """, listing_id)

    avg_rating = None
    if reviews:
        avg_rating = round(sum(r["rating"] for r in reviews) / len(reviews), 1)

    already_reviewed = False
    if session.get("user_id"):
        existing = db.execute(
            "SELECT id FROM reviews WHERE user_id = ? AND listing_id = ?",
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

        db.execute("""
            INSERT INTO listings (user_id, title, description, price, location, guests, image_url)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, session["user_id"], title, description, price, location, guests, image_url)

        flash("Listing created successfully!", "success")
        return redirect("/")

    return render_template("create.html")


@app.route("/delete/<int:listing_id>", methods=["POST"])
@login_required
def delete_listing(listing_id):
    rows = db.execute("SELECT user_id FROM listings WHERE id = ?", listing_id)

    if not rows or rows[0]["user_id"] != session["user_id"]:
        return apology("not authorized", 403)

    db.execute("DELETE FROM bookings WHERE listing_id = ?", listing_id)
    db.execute("DELETE FROM reviews WHERE listing_id = ?", listing_id)
    db.execute("DELETE FROM listings WHERE id = ?", listing_id)

    flash("Listing deleted.", "info")
    return redirect("/")


@app.route("/book/<int:listing_id>", methods=["POST"])
@login_required
def book(listing_id):
    rows = db.execute("SELECT * FROM listings WHERE id = ?", listing_id)

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

    db.execute("""
        INSERT INTO bookings (user_id, listing_id, check_in, check_out)
        VALUES (?, ?, ?, ?)
    """, session["user_id"], listing_id, check_in, check_out)

    flash("Booking confirmed!", "success")
    return redirect("/bookings")


@app.route("/bookings")
@login_required
def bookings():
    user_bookings = db.execute("""
        SELECT bookings.*, listings.title, listings.location, listings.price, listings.image_url
        FROM bookings
        JOIN listings ON listings.id = bookings.listing_id
        WHERE bookings.user_id = ?
        ORDER BY bookings.check_in DESC
    """, session["user_id"])

    return render_template("bookings.html", bookings=user_bookings)


@app.route("/review/<int:listing_id>", methods=["POST"])
@login_required
def review(listing_id):
    rows = db.execute("SELECT id FROM listings WHERE id = ?", listing_id)

    if not rows:
        return apology("listing not found", 404)

    existing = db.execute(
        "SELECT id FROM reviews WHERE user_id = ? AND listing_id = ?",
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

    db.execute("""
        INSERT INTO reviews (user_id, listing_id, rating, comment)
        VALUES (?, ?, ?, ?)
    """, session["user_id"], listing_id, rating, comment)

    flash("Review submitted!", "success")
    return redirect(f"/listings/{listing_id}")
