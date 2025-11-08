# 盈亏日记 · Web App（Render 版）
- 登录、快速记账、图表（Chart.js）、CSV 导出
- 多账户/多币种（统一折算 CNY），自动计算净额（含手续费）

## 本地运行
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # 可选
python app.py
```

## 生产部署（Render）
- 本仓库包含 `render.yaml`（Blueprint），在 Render 直接导入即可（会自动创建 Postgres + Web）。
- 启动命令：`gunicorn -w 2 -k gthread -t 120 -b 0.0.0.0:$PORT app:app`。
