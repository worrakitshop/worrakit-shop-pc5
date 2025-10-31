from __future__ import annotations
from datetime import datetime, date, time, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy

BRAND_NAME = "Worrakit Shop — Premium"
ADMIN_USER = "sudket204"
ADMIN_PASS = "1329900935042"
SECRET_KEY = "change-this-to-production-secret"

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///rental.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = SECRET_KEY
db = SQLAlchemy(app)

# Models
class Computer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    spec = db.Column(db.String(250), nullable=True)
    rate_hour = db.Column(db.Float, default=0.0)
    rate_day = db.Column(db.Float, default=0.0)
    is_active = db.Column(db.Boolean, default=True)
    rentals = db.relationship("Booking", backref="computer", lazy=True, cascade="all, delete-orphan")

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    computer_id = db.Column(db.Integer, db.ForeignKey('computer.id'), nullable=False)
    customer = db.Column(db.String(120), nullable=False)
    start_at = db.Column(db.DateTime, nullable=False)
    end_at = db.Column(db.DateTime, nullable=False)

# Helpers
def parse_date(s: str | None, default: date | None = None) -> date:
    if not s:
        return default or date.today()
    return datetime.strptime(s, "%Y-%m-%d").date()

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('login', next=request.full_path))
        return f(*args, **kwargs)
    return decorated

# Routes
@app.route('/')
def home():
    return redirect(url_for('schedule'))

def _sched_ctx(day: date):
    start_of_day = datetime.combine(day, time(0,0))
    end_of_day = start_of_day + timedelta(days=1)
    comps = Computer.query.filter_by(is_active=True).order_by(Computer.id.asc()).all()
    bookings = Booking.query.filter(Booking.start_at < end_of_day, Booking.end_at > start_of_day).all()
    by_comp = {c.id: [] for c in comps}
    for b in bookings:
        by_comp.setdefault(b.computer_id, []).append(b)
    hours = [start_of_day + timedelta(hours=h) for h in range(24)]
    return dict(day=day, comps=comps, hours=hours, by_comp=by_comp, timedelta=timedelta)

@app.route('/schedule')
def schedule():
    day = parse_date(request.args.get('date'))
    ctx = _sched_ctx(day)
    ctx['brand'] = BRAND_NAME
    if request.args.get('partial') == '1':
        return render_template('_schedule_table.html', **ctx)
    return render_template('schedule.html', **ctx)

@app.route('/price')
def price():
    comps = Computer.query.order_by(Computer.id.asc()).all()
    return render_template('price.html', computers=comps, brand=BRAND_NAME)

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        user = request.form.get('username','').strip()
        pwd = request.form.get('password','').strip()
        if user == ADMIN_USER and pwd == ADMIN_PASS:
            session['admin_logged_in'] = True
            flash('ล็อกอินสำเร็จ', 'success')
            return redirect(request.args.get('next') or url_for('schedule'))
        flash('ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง', 'danger')
    return render_template('login.html', brand=BRAND_NAME)

@app.route('/logout')
def logout():
    session.pop('admin_logged_in', None)
    flash('ออกจากระบบแล้ว', 'info')
    return redirect(url_for('schedule'))

# --- Computer Management Routes ---
@app.route('/computer/new', methods=['GET','POST'])
@admin_required
def new_computer():
    if request.method == 'POST':
        name = request.form['name'].strip()
        spec = request.form['spec'].strip()
        # Ensure conversion to float for numeric fields
        try:
            rate_hour = float(request.form['rate_hour'])
            rate_day = float(request.form['rate_day'])
        except ValueError:
            flash('ราคาต้องเป็นตัวเลขที่ถูกต้อง', 'danger')
            return redirect(url_for('new_computer'))

        comp = Computer(name=name, spec=spec, rate_hour=rate_hour, rate_day=rate_day)
        db.session.add(comp)
        db.session.commit()
        flash(f'เพิ่มเครื่อง "{name}" แล้ว', 'success')
        return redirect(url_for('price'))

    return render_template('computer_form.html', mode='new', brand=BRAND_NAME)

@app.route('/computer/<int:cid>/edit', methods=['GET','POST'])
@admin_required
def edit_computer(cid):
    comp = Computer.query.get_or_404(cid)
    
    if request.method == 'POST':
        comp.name = request.form['name'].strip()
        comp.spec = request.form['spec'].strip()
        # Ensure conversion to float for numeric fields
        try:
            comp.rate_hour = float(request.form['rate_hour'])
            comp.rate_day = float(request.form['rate_day'])
        except ValueError:
            flash('ราคาต้องเป็นตัวเลขที่ถูกต้อง', 'danger')
            return redirect(url_for('edit_computer', cid=cid))

        # Checkbox presence determines is_active status
        comp.is_active = 'is_active' in request.form 
        
        db.session.commit()
        flash(f'แก้ไขข้อมูลเครื่อง "{comp.name}" แล้ว', 'success')
        return redirect(url_for('price'))

    return render_template('computer_form.html', comp=comp, mode='edit', brand=BRAND_NAME)

@app.route('/computer/<int:cid>/delete', methods=['POST'])
@admin_required
def delete_computer(cid):
    comp = Computer.query.get_or_404(cid)
    name = comp.name
    # Cascading delete is set up on the model, so related bookings will be deleted automatically
    db.session.delete(comp)
    db.session.commit()
    flash(f'ลบเครื่อง "{name}" และการจองทั้งหมดที่เกี่ยวข้องแล้ว', 'info')
    return redirect(url_for('price'))

# --- End Computer Management Routes ---

@app.route('/booking/new', methods=['GET','POST'])
@admin_required
def new_booking():
    comps = Computer.query.filter_by(is_active=True).order_by(Computer.id.asc()).all()
    if request.method == 'POST':
        cid = int(request.form['computer_id'])
        customer = request.form['customer'].strip()
        day = parse_date(request.form['day'])
        start_t = datetime.strptime(request.form['start_time'], "%H:%M").time()
        end_t = datetime.strptime(request.form['end_time'], "%H:%M").time()
        start_at = datetime.combine(day, start_t)
        end_at = datetime.combine(day, end_t)
        # basic valid
        if end_at <= start_at:
            flash('เวลาไม่ถูกต้อง: เวลาเสร็จต้องมากกว่าเวลาเริ่ม', 'danger')
            return redirect(url_for('new_booking', date=day.isoformat()))
        # overlap check
        overlap = Booking.query.filter(
            Booking.computer_id==cid,
            Booking.start_at < end_at,
            Booking.end_at > start_at
        ).count() > 0
        if overlap:
            flash('ช่วงเวลานี้ถูกจองแล้ว เลือกเวลาอื่น', 'warning')
            return redirect(url_for('new_booking', date=day.isoformat()))
        db.session.add(Booking(computer_id=cid, customer=customer, start_at=start_at, end_at=end_at))
        db.session.commit()
        flash('สร้างการจองแล้ว', 'success')
        return redirect(url_for('schedule', date=day.isoformat()))
    day = parse_date(request.args.get('date'))
    return render_template('booking_form.html', comps=comps, day=day, brand=BRAND_NAME)

@app.route('/booking/<int:bid>/delete', methods=['POST'])
@admin_required
def delete_booking(bid):
    b = Booking.query.get_or_404(bid)
    d = b.start_at.date().isoformat()
    db.session.delete(b)
    db.session.commit()
    flash('ลบการจองแล้ว', 'info')
    return redirect(url_for('schedule', date=d))

# --- Database Initialization Functions ---
@app.cli.command('init-db')
def init_db():
    db.create_all()
    if Computer.query.count() == 0:
        seed()
        print('Seeded.')

def seed():
    comps = [
        Computer(name='เครื่องที่ 1', spec='Intel Core Ultra 9 + RTX 5070', rate_hour=60, rate_day=450),
        Computer(name='เครื่องที่ 2', spec='Ryzen 7 7800X3D + RX 9060 XT', rate_hour=80, rate_day=600),
    ]
    db.session.add_all(comps); db.session.commit()

# ****************************************************
# ** FINAL FIX: โค้ดนี้จะถูกรันทันทีที่ Gunicorn โหลดไฟล์ **
# ****************************************************
with app.app_context():
    # 1. สร้างตารางทั้งหมด (ถ้ายังไม่มี)
    db.create_all()
    # 2. เพิ่มข้อมูลเริ่มต้น (ถ้ายังไม่มีข้อมูล)
    if Computer.query.count() == 0:
        seed()

# (ไม่มี if __name__ == '__main__': ใน Production)
