# -*- coding: utf-8 -*-
from datetime import date, timedelta
from app import app, db, User, Account, Entry, compute_net_cny

def ensure_user(email="demo@example.com", password="demo123"):
    u = User.query.filter_by(email=email).first()
    if not u:
        u = User(email=email)
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        acc = Account(user_id=u.id, name="默认账户", initial_balance=1000.0)
        db.session.add(acc)
        db.session.commit()
    return u

def add_entry(user, **kwargs):
    e = Entry(user_id=user.id, **kwargs)
    db.session.add(e)

def run():
    with app.app_context():
        db.create_all()
        u = ensure_user()
        Entry.query.filter_by(user_id=u.id).delete()
        db.session.commit()
        acc = Account.query.filter_by(user_id=u.id).first()
        today = date.today()
        samples = [
            dict(date=today - timedelta(days=1), direction="收入", amount=1200, fee=10, currency="CNY", rate_to_cny=1, account_id=acc.id, category="销售", tags="项目A", note="线下收款"),
            dict(date=today - timedelta(days=1), direction="支出", amount=300, fee=0, currency="CNY", rate_to_cny=1, account_id=acc.id, category="广告", tags="推广", note="投放"),
            dict(date=today, direction="收入", amount=200, fee=2, currency="USD", rate_to_cny=7.0, account_id=acc.id, category="投资", tags="股息", note="美股分红"),
            dict(date=today, direction="支出", amount=500, fee=0, currency="CNY", rate_to_cny=1, account_id=acc.id, category="办公", tags="设备", note="采购键盘"),
            dict(date=today, direction="支出", amount=50, fee=1, currency="EUR", rate_to_cny=7.8, account_id=acc.id, category="手续费", tags="提现", note="平台手续费"),
        ]
        for s in samples:
            s["amount"] = abs(s["amount"]); s["fee"] = abs(s["fee"])
            s["net_cny"] = compute_net_cny(s["direction"], s["amount"], s["fee"], s["rate_to_cny"])
            add_entry(u, **s)
        db.session.commit()
        print("示例数据已写入。登录：demo@example.com / demo123")

if __name__ == "__main__":
    run()
