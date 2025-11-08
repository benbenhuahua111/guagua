# -*- coding: utf-8 -*-
import os, io
from datetime import datetime, date, timedelta
from collections import defaultdict
from urllib.parse import urlencode

from flask import (
    Flask, render_template, request, redirect, url_for, flash, send_file, abort
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, login_user, logout_user, login_required, current_user, UserMixin
)
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func, case, text
from dotenv import load_dotenv

# 加载 .env
load_dotenv()

def create_app():
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-change-me")
    db_url = os.getenv("DATABASE_URL", "sqlite:///data.db")

    # 兼容 URL：postgres / postgresql → 使用 psycopg 驱动
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)
    elif db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    return app

app = create_app()
db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"

# ------------------ 数据模型 ------------------
class User(db.Model, UserMixin):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    accounts = db.relationship("Account", backref="user", lazy=True, cascade="all, delete-orphan")
    entries = db.relationship("Entry", backref="user", lazy=True, cascade="all, delete-orphan")

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

class Account(db.Model):
    __tablename__ = "accounts"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    initial_balance = db.Column(db.Float, default=0.0)

    entries = db.relationship("Entry", backref="account", lazy=True)

class Entry(db.Model):
    __tablename__ = "entries"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, index=True)
    direction = db.Column(db.String(10), nullable=False)  # 收入 / 支出
    amount = db.Column(db.Float, nullable=False)          # 原币金额（正数）
    fee = db.Column(db.Float, default=0.0)                # 原币手续费（正数）
    currency = db.Column(db.String(10), default="CNY")
    rate_to_cny = db.Column(db.Float, default=1.0)        # 1 原币 = ? CNY
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=True)
    category = db.Column(db.String(100), default="其他")
    tags = db.Column(db.String(255), default="")          # 逗号分隔
    note = db.Column(db.Text, default="")
    net_cny = db.Column(db.Float, nullable=False)         # 以 CNY 计的净额（收入为正，支出为负；含手续费）
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ------------------ 登录管理 ------------------
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ------------------ 工具函数 ------------------
def compute_net_cny(direction: str, amount: float, fee: float, rate_to_cny: float) -> float:
    amount_cny = (amount or 0.0) * (rate_to_cny or 1.0)
    fee_cny = (fee or 0.0) * (rate_to_cny or 1.0)
    if direction == "收入":
        return amount_cny - fee_cny
    else:
        return -amount_cny - fee_cny

def ensure_db():
    with app.app_context():
        db.create_all()

@app.context_processor
def inject_globals():
    return {"today_str": date.today().isoformat()}

# --- 在 WSGI (gunicorn) 模式下，首次请求自动建表 ---
@app.before_request
def _ensure_db_once():
    if not getattr(app, "_db_inited", False):
        try:
            ensure_db()
            app._db_inited = True
        except Exception as e:
            app.logger.error(f"DB init failed: {e}")

# ------------------ 路由 ------------------
@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return render_template("index.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        if not email or not password:
            flash("请输入邮箱和密码。", "danger")
            return redirect(url_for("register"))
        if User.query.filter_by(email=email).first():
            flash("该邮箱已注册，请直接登录。", "warning")
            return redirect(url_for("login"))
        user = User(email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        default_account = Account(user_id=user.id, name="默认账户", initial_balance=0.0)
        db.session.add(default_account)
        db.session.commit()
        flash("注册成功，请登录。", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            flash("登录成功。", "success")
            return redirect(url_for("dashboard"))
        flash("邮箱或密码错误。", "danger")
        return redirect(url_for("login"))
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("已退出登录。", "info")
    return redirect(url_for("index"))

@app.route("/dashboard", methods=["GET", "POST"])
@login_required
def dashboard():
    if request.method == "POST":
        try:
            d = request.form
            dt = datetime.strptime(d.get("date") or date.today().isoformat(), "%Y-%m-%d").date()
            direction = d.get("direction") or "支出"
            if direction not in ("收入", "支出"):
                direction = "支出"
            amount = float(d.get("amount") or 0)
            fee = float(d.get("fee") or 0)
            currency = (d.get("currency") or "CNY").upper()
            rate_to_cny = float(d.get("rate_to_cny") or 1.0)
            category = d.get("category") or "其他"
            tags = d.get("tags") or ""
            note = d.get("note") or ""

            account_id = d.get("account_id")
            new_account_name = (d.get("new_account_name") or "").strip()
            account_obj = None
            if new_account_name:
                account_obj = Account(user_id=current_user.id, name=new_account_name, initial_balance=0.0)
                db.session.add(account_obj)
                db.session.flush()
            elif account_id and account_id.isdigit():
                account_obj = Account.query.filter_by(id=int(account_id), user_id=current_user.id).first()

            net_cny = compute_net_cny(direction, amount, fee, rate_to_cny)
            entry = Entry(
                user_id=current_user.id,
                date=dt,
                direction=direction,
                amount=abs(amount),
                fee=abs(fee),
                currency=currency,
                rate_to_cny=rate_to_cny,
                account_id=account_obj.id if account_obj else None,
                category=category,
                tags=tags,
                note=note,
                net_cny=net_cny
            )
            db.session.add(entry)
            db.session.commit()
            flash("已记录。", "success")
            return redirect(url_for("dashboard"))
        except Exception as e:
            db.session.rollback()
            flash(f"保存失败：{e}", "danger")

    today = date.today()
    start_7 = today - timedelta(days=6)
    month_start = today.replace(day=1)

    def sum_range(start_dt: date, end_dt: date):
        q = db.session.query(func.coalesce(func.sum(Entry.net_cny), 0.0)).filter(
            Entry.user_id == current_user.id,
            Entry.date >= start_dt,
            Entry.date <= end_dt
        )
        return float(q.scalar() or 0.0)

    today_pl = sum_range(today, today)
    week_pl = sum_range(start_7, today)
    month_pl = sum_range(month_start, today)

    start_30 = today - timedelta(days=29)
    rows = db.session.query(Entry.date, func.sum(Entry.net_cny)).filter(
        Entry.user_id == current_user.id,
        Entry.date >= start_30,
        Entry.date <= today
    ).group_by(Entry.date).order_by(Entry.date.asc()).all()

    daily_map = {r[0]: float(r[1]) for r in rows}
    labels_30, values_30, cum_values = [], [], []
    running = 0.0
    for i in range(30):
        dt = start_30 + timedelta(days=i)
        labels_30.append(dt.strftime("%m-%d"))
        v = daily_map.get(dt, 0.0)
        values_30.append(round(v, 2))
        running += v
        cum_values.append(round(running, 2))

    engine_name = db.engine.url.drivername
    if engine_name.startswith("sqlite"):
        month_expr = func.strftime("%Y-%m", Entry.date)
    elif engine_name.startswith("postgresql"):
        month_expr = func.to_char(Entry.date, "YYYY-MM")
    else:
        month_expr = func.substr(func.cast(Entry.date, db.String()), 1, 7)

    six_months_ago = (today.replace(day=1) - timedelta(days=1)).replace(day=1) - timedelta(days=150)
    month_rows = db.session.query(month_expr.label("ym"), func.sum(Entry.net_cny)).filter(
        Entry.user_id == current_user.id,
        Entry.date >= six_months_ago
    ).group_by(text("ym")).order_by(text("ym")).all()

    month_labels = [r[0] for r in month_rows]
    month_values = [round(float(r[1] or 0.0), 2) for r in month_rows]

    pos_sum = case((Entry.net_cny > 0, Entry.net_cny), else_=0.0)
    cat_rows = db.session.query(Entry.category, func.sum(pos_sum)).filter(
        Entry.user_id == current_user.id
    ).group_by(Entry.category).all()
    cat_labels = [r[0] or "未分类" for r in cat_rows]
    cat_values = [round(float(r[1] or 0.0), 2) for r in cat_rows]

    accounts = Account.query.filter_by(user_id=current_user.id).order_by(Account.name.asc()).all()

    return render_template(
        "dashboard.html",
        today_pl=round(today_pl, 2),
        week_pl=round(week_pl, 2),
        month_pl=round(month_pl, 2),
        labels_30=labels_30,
        values_30=values_30,
        cum_values=cum_values,
        month_labels=month_labels,
        month_values=month_values,
        cat_labels=cat_labels,
        cat_values=cat_values,
        accounts=accounts
    )

@app.route("/entries")
@login_required
def entries():
    page = int(request.args.get("page", 1))
    per_page = 20
    q = Entry.query.filter_by(user_id=current_user.id)

    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    keyword = request.args.get("kw")
    direction = request.args.get("dir")
    if start_date:
        q = q.filter(Entry.date >= datetime.strptime(start_date, "%Y-%m-%d").date())
    if end_date:
        q = q.filter(Entry.date <= datetime.strptime(end_date, "%Y-%m-%d").date())
    if keyword:
        like = f"%{keyword}%"
        q = q.filter(
            (Entry.category.ilike(like)) | (Entry.tags.ilike(like)) | (Entry.note.ilike(like))
        )
    if direction in ("收入", "支出"):
        q = q.filter(Entry.direction == direction)

    q = q.order_by(Entry.date.desc(), Entry.id.desc())
    pagination = db.paginate(q, page=page, per_page=per_page, error_out=False)
    items = pagination.items

    page_sum = round(sum([e.net_cny for e in items]) if items else 0.0, 2)

    return render_template(
        "entries.html",
        items=items,
        pagination=pagination,
        page_sum=page_sum,
        params={k: v for k, v in request.args.items() if k != "page"}
    )

@app.route("/entries/<int:entry_id>/delete", methods=["POST"])
@login_required
def delete_entry(entry_id):
    entry = Entry.query.filter_by(id=entry_id, user_id=current_user.id).first_or_404()
    db.session.delete(entry)
    db.session.commit()
    flash("已删除。", "info")
    return redirect(request.referrer or url_for("entries"))

@app.route("/accounts", methods=["GET", "POST"])
@login_required
def accounts():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        initial_balance = float(request.form.get("initial_balance") or 0.0)
        if not name:
            flash("账户名不能为空。", "danger")
        else:
            acct = Account(user_id=current_user.id, name=name, initial_balance=initial_balance)
            db.session.add(acct)
            db.session.commit()
            flash("账户已创建。", "success")
            return redirect(url_for("accounts"))

    rows = db.session.query(
        Account,
        func.coalesce(func.sum(Entry.net_cny), 0.0).label("pl")
    ).outerjoin(Entry, (Entry.account_id == Account.id) & (Entry.user_id == current_user.id)).filter(
        Account.user_id == current_user.id
    ).group_by(Account.id).order_by(Account.name.asc()).all()

    acct_info = []
    for acct, pl in rows:
        cur = round((acct.initial_balance or 0.0) + float(pl or 0.0), 2)
        acct_info.append({
            "id": acct.id,
            "name": acct.name,
            "initial_balance": round(acct.initial_balance or 0.0, 2),
            "pl": round(float(pl or 0.0), 2),
            "current_balance": cur
        })
    return render_template("accounts.html", accounts=acct_info)

@app.route("/export")
@login_required
def export_csv():
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    q = Entry.query.filter_by(user_id=current_user.id)
    if start_date:
        q = q.filter(Entry.date >= datetime.strptime(start_date, "%Y-%m-%d").date())
    if end_date:
        q = q.filter(Entry.date <= datetime.strptime(end_date, "%Y-%m-%d").date())
    q = q.order_by(Entry.date.asc(), Entry.id.asc())

    output = []
    header = ["日期", "方向", "金额", "手续费", "币种", "汇率到CNY", "账户", "类别", "标签", "备注", "净额(CNY)"]
    output.append(header)
    for e in q.all():
        acct_name = e.account.name if e.account else ""
        output.append([
            e.date.isoformat(),
            e.direction,
            f"{e.amount:.2f}",
            f"{e.fee:.2f}",
            e.currency,
            f"{e.rate_to_cny:.4f}",
            acct_name,
            e.category or "",
            e.tags or "",
            e.note or "",
            f"{e.net_cny:.2f}"
        ])

    buf = "\n".join([",".join(map(lambda x: f'"{x}"' if ("," in str(x) or '"' in str(x)) else str(x), row)) for row in output])
    filename = f"export_{date.today().isoformat()}.csv"
    return send_file(
        io.BytesIO(buf.encode("utf-8-sig")),
        mimetype="text/csv; charset=utf-8",
        as_attachment=True,
        download_name=filename
    )

if __name__ == "__main__":
    ensure_db()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
