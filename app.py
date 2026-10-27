import sqlite3, os
from datetime import date
from flask import Flask, render_template, request, redirect, url_for, flash, g

app = Flask(__name__)
app.secret_key = "hotel-secret"
DB = os.environ.get("DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "hotel.db"))
REFUND = 0.5  # bekor qilinganda 50% qaytariladi

MENU = [("Osh", 55000), ("Lag'mon", 45000), ("Shashlik (3 ta)", 60000), ("Somsa", 12000),
        ("Sezar salati", 40000), ("Choy (choynak)", 15000), ("Qahva", 20000), ("Tort bo'lagi", 25000)]
SERVICES = [("Kir yuvish", 30000), ("Xona tozalash", 0), ("Taksi chaqirish", 0), ("Spa va massaj", 200000),
            ("Uyg'otish xizmati", 0), ("Transfer (aeroport)", 120000), ("Qo'shimcha adyol/yostiq", 0),
            ("Sport zal", 0), ("Konferens-zal", 500000)]
STAGES = ["Qabul qilindi", "Tayyorlanmoqda", "Yetkazilmoqda", "Yetkazildi"]

def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB); g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close(e):
    d = g.pop("db", None)
    if d: d.close()

def init():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = sqlite3.connect(DB)
    c.executescript("""
    CREATE TABLE IF NOT EXISTS rooms(number INTEGER PRIMARY KEY, floor INT, type TEXT, price INT);
    CREATE TABLE IF NOT EXISTS bookings(id INTEGER PRIMARY KEY, room INT, name TEXT, phone TEXT,
        cin TEXT, cout TEXT, total INT, status TEXT DEFAULT 'faol', refund INT DEFAULT 0);
    CREATE TABLE IF NOT EXISTS requests(id INTEGER PRIMARY KEY, room INT, service TEXT, price INT);
    CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY, room INT, items TEXT, total INT, stage INT DEFAULT 0);
    """)
    if not c.execute("SELECT 1 FROM rooms").fetchone():
        types = [("Standart", 250000), ("Standart", 250000), ("Lux", 450000), ("Lux", 450000), ("Oilaviy", 600000)]
        for f in range(1, 5):
            for i, (t, p) in enumerate(types, 1):
                c.execute("INSERT INTO rooms VALUES(?,?,?,?)", (f * 100 + i, f, t, p))
    c.commit(); c.close()

def busy(room, cin, cout):
    return db().execute("SELECT 1 FROM bookings WHERE room=? AND status='faol' AND cin<? AND cout>?",
                        (room, cout, cin)).fetchone()

@app.route("/")
def rooms():
    floor, cin, cout = request.args.get("floor"), request.args.get("cin"), request.args.get("cout")
    q, a = "SELECT * FROM rooms", []
    if floor: q += " WHERE floor=?"; a.append(floor)
    rs = [dict(r) for r in db().execute(q + " ORDER BY number", a)]
    if cin and cout:
        for r in rs: r["busy"] = bool(busy(r["number"], cin, cout))
    return render_template("rooms.html", rooms=rs, floor=floor, cin=cin or "", cout=cout or "", today=date.today())

@app.route("/book/<int:n>", methods=["GET", "POST"])
def book(n):
    r = db().execute("SELECT * FROM rooms WHERE number=?", (n,)).fetchone()
    if request.method == "POST":
        cin, cout = request.form["cin"], request.form["cout"]
        nights = (date.fromisoformat(cout) - date.fromisoformat(cin)).days
        if nights < 1 or cin < str(date.today()): flash("Sanalar noto'g'ri.")
        elif busy(n, cin, cout): flash("Bu sanalarda xona band.")
        else:
            db().execute("INSERT INTO bookings(room,name,phone,cin,cout,total) VALUES(?,?,?,?,?,?)",
                         (n, request.form["name"], request.form["phone"], cin, cout, nights * r["price"]))
            db().commit()
            flash(f"{n}-xona bron qilindi. Jami: {nights * r['price']:,} so'm")
            return redirect(url_for("bookings", phone=request.form["phone"]))
    return render_template("book.html", r=r, today=date.today())

@app.route("/bookings")
def bookings():
    phone = request.args.get("phone", "")
    bs = db().execute("SELECT * FROM bookings WHERE phone=? ORDER BY id DESC", (phone,)).fetchall() if phone else []
    return render_template("bookings.html", bs=bs, phone=phone)

@app.post("/cancel/<int:i>")
def cancel(i):
    b = db().execute("SELECT * FROM bookings WHERE id=?", (i,)).fetchone()
    if b and b["status"] == "faol":
        ref = int(b["total"] * REFUND)
        db().execute("UPDATE bookings SET status='bekor', refund=? WHERE id=?", (ref, i)); db().commit()
        flash(f"Bron bekor qilindi. {ref:,} so'm (50%) qaytariladi.")
    return redirect(url_for("bookings", phone=b["phone"]))

@app.route("/services", methods=["GET", "POST"])
def services():
    if request.method == "POST":
        room, s = int(request.form["room"]), dict(SERVICES)
        sv = request.form["service"]
        db().execute("INSERT INTO requests(room,service,price) VALUES(?,?,?)", (room, sv, s[sv])); db().commit()
        flash(f"«{sv}» xizmati {room}-xonaga buyurtma qilindi.")
        return redirect(url_for("services"))
    reqs = db().execute("SELECT * FROM requests ORDER BY id DESC LIMIT 10").fetchall()
    return render_template("services.html", services=SERVICES, reqs=reqs)

@app.route("/menu", methods=["GET", "POST"])
def menu():
    if request.method == "POST":
        items, total = [], 0
        for k, (name, p) in enumerate(MENU):
            q = int(request.form.get(f"q{k}") or 0)
            if q > 0: items.append(f"{name} x{q}"); total += p * q
        if not items: flash("Kamida bitta taom tanlang.")
        else:
            db().execute("INSERT INTO orders(room,items,total) VALUES(?,?,?)",
                         (int(request.form["room"]), ", ".join(items), total)); db().commit()
            flash("Buyurtma qabul qilindi, xonangizga yetkaziladi.")
            return redirect(url_for("orders"))
    return render_template("menu.html", menu=list(enumerate(MENU)))

@app.route("/orders")
def orders():
    os_ = db().execute("SELECT * FROM orders ORDER BY id DESC").fetchall()
    return render_template("orders.html", orders=os_, stages=STAGES)

@app.post("/orders/<int:i>/next")
def next_stage(i):
    db().execute("UPDATE orders SET stage=MIN(stage+1,3) WHERE id=?", (i,)); db().commit()
    return redirect(url_for("orders"))

init()

if __name__ == "__main__":
    app.run(debug=True, port=8000)
