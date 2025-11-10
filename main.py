from fastapi import FastAPI, Depends, Request, Form, HTTPException, status, UploadFile, File, WebSocket
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select
from jose import JWTError
import pandas as pd
import os, csv
from .database import init_db, get_session, engine
from .models import *
from .auth import create_access_token, verify_password, hash_password, get_current_user, get_current_admin
from .recs import recommend_for_product
from .ws import hub

app = FastAPI(title="Standout Store")
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.on_event("startup")
def on_startup():
    init_db()
    # seed
    with Session(engine) as s:
        if not s.exec(select(User).where(User.email=="admin@demo.dev")).first():
            admin = User(email="admin@demo.dev", hashed_password=hash_password("admin123"), is_admin=True)
            s.add(admin)
        if not s.exec(select(Category)).all():
            cat = Category(name="Gadgets", slug="gadgets")
            s.add(cat)
            s.flush()
            demo = [
                Product(title="Pocket Drone", description="Mini foldable drone with HD camera and gesture control.", price=129.99, stock=12, category_id=cat.id, image_url="https://images.unsplash.com/photo-1518770660439-4636190af475"),
                Product(title="Smart Mug", description="Self-heating mug keeps your coffee at the perfect temperature.", price=89.00, stock=30, category_id=cat.id, image_url="https://images.unsplash.com/photo-1511920170033-f8396924c348"),
                Product(title="Sleep Headband", description="Bluetooth sleep mask with ultra‑thin speakers for side sleepers.", price=39.50, stock=50, category_id=cat.id, image_url="https://images.unsplash.com/photo-1522335789203-aabd1fc54bc9"),
                Product(title="Air Quality Clip", description="Wearable sensor that tracks VOCs, PM2.5, and CO2 with alerts.", price=59.90, stock=22, category_id=cat.id, image_url="https://images.unsplash.com/photo-1520607162513-77705c0f0d4a"),
            ]
            for p in demo:
                p.variant_a_title = "🔥 " + p.title
                p.variant_b_title = p.title + " — Pro Edition"
                s.add(p)
        if not s.exec(select(FeatureFlag).where(FeatureFlag.name=="experiments")).first():
            s.add(FeatureFlag(name="experiments", enabled=True))
        s.commit()

# ----------- PAGES -----------
@app.get("/", response_class=HTMLResponse)
def home(request: Request, session: Session = Depends(get_session)):
    products = session.exec(select(Product)).all()
    return templates.TemplateResponse("home.html", {"request": request, "products": products})

@app.get("/product/{pid}", response_class=HTMLResponse)
def product_page(pid: int, request: Request, session: Session = Depends(get_session)):
    product = session.get(Product, pid)
    if not product:
        raise HTTPException(404, "Product not found")
    recs = recommend_for_product(session, pid, n=4)
    return templates.TemplateResponse("product.html", {"request": request, "product": product, "recs": recs})

# ----------- AUTH API -----------
@app.post("/api/signup")
def api_signup(email: str = Form(...), password: str = Form(...), session: Session = Depends(get_session)):
    if session.exec(select(User).where(User.email==email)).first():
        raise HTTPException(400, "Email already registered")
    user = User(email=email, hashed_password=hash_password(password))
    session.add(user)
    session.commit()
    token = create_access_token({"sub": str(user.id)})
    return {"access_token": token, "token_type": "bearer"}

@app.post("/api/login")
def api_login(email: str = Form(...), password: str = Form(...), session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.email==email)).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(400, "Invalid credentials")
    token = create_access_token({"sub": str(user.id)})
    return {"access_token": token, "token_type": "bearer"}

# ----------- CART -----------
def get_or_create_cart(session: Session, user_id: int) -> Cart:
    cart = session.exec(select(Cart).where(Cart.user_id==user_id)).first()
    if not cart:
        cart = Cart(user_id=user_id)
        session.add(cart)
        session.commit()
        session.refresh(cart)
    return cart

@app.post("/api/cart/add")
def add_to_cart(product_id: int = Form(...), qty: int = Form(1), user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    product = session.get(Product, product_id)
    if not product or product.stock < qty:
        raise HTTPException(400, "Insufficient stock")
    cart = get_or_create_cart(session, user.id)
    item = session.exec(select(CartItem).where(CartItem.cart_id==cart.id, CartItem.product_id==product_id)).first()
    if item:
        item.qty += qty
    else:
        item = CartItem(cart_id=cart.id, product_id=product_id, qty=qty)
        session.add(item)
    session.add(Event(user_id=user.id, type="add_to_cart", product_id=product_id))
    session.commit()
    return {"ok": True}

@app.get("/api/cart")
def get_cart(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    cart = get_or_create_cart(session, user.id)
    items = session.exec(select(CartItem).where(CartItem.cart_id==cart.id)).all()
    out = []
    total = 0.0
    for it in items:
        p = session.get(Product, it.product_id)
        line = {"id": it.id, "product_id": p.id, "title": p.title, "qty": it.qty, "price": p.price, "subtotal": round(p.price*it.qty,2)}
        total += p.price*it.qty
        out.append(line)
    return {"items": out, "total": round(total,2)}

@app.post("/api/checkout")
def checkout(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    cart = get_or_create_cart(session, user.id)
    items = session.exec(select(CartItem).where(CartItem.cart_id==cart.id)).all()
    if not items:
        raise HTTPException(400, "Cart is empty")
    total = 0.0
    for it in items:
        p = session.get(Product, it.product_id)
        if p.stock < it.qty:
            raise HTTPException(400, f"Insufficient stock for {p.title}")
        total += p.price * it.qty
    order = Order(user_id=user.id, total=round(total,2))
    session.add(order)
    session.commit()
    session.refresh(order)
    for it in items:
        p = session.get(Product, it.product_id)
        p.stock -= it.qty
        session.add(OrderItem(order_id=order.id, product_id=p.id, qty=it.qty, price_each=p.price))
        session.add(Event(user_id=user.id, type="purchase", product_id=p.id))
    # clear cart
    for it in items:
        session.delete(it)
    session.commit()
    return {"ok": True, "order_id": order.id, "total": order.total}

# ----------- ADMIN -----------
@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request, admin: User = Depends(get_current_admin), session: Session = Depends(get_session)):
    products = session.exec(select(Product)).all()
    flags = session.exec(select(FeatureFlag)).all()
    return templates.TemplateResponse("admin.html", {"request": request, "products": products, "flags": flags, "admin": admin})

@app.post("/api/admin/toggle_stock")
def admin_toggle_stock(pid: int = Form(...), admin: User = Depends(get_current_admin), session: Session = Depends(get_session)):
    p = session.get(Product, pid)
    p.stock = 0 if p.stock > 0 else 10
    session.add(p)
    session.commit()
    # notify websocket listeners
    import anyio
    anyio.from_thread.run(hub.broadcast, {"type":"stock_update", "product_id": p.id, "stock": p.stock})
    return {"ok": True, "stock": p.stock}

@app.post("/api/admin/upload_csv")
def admin_upload(file: UploadFile = File(...), admin: User = Depends(get_current_admin), session: Session = Depends(get_session)):
    content = file.file.read().decode("utf-8")
    reader = csv.DictReader(content.splitlines())
    for row in reader:
        p = Product(
            title=row.get("title",""),
            description=row.get("description",""),
            price=float(row.get("price",0)),
            stock=int(row.get("stock",0)),
            image_url=row.get("image_url")
        )
        session.add(p)
    session.commit()
    return {"ok": True}

@app.post("/api/admin/flags")
def admin_flags(name: str = Form(...), enabled: bool = Form(...), admin: User = Depends(get_current_admin), session: Session = Depends(get_session)):
    flag = session.exec(select(FeatureFlag).where(FeatureFlag.name==name)).first()
    if not flag:
        flag = FeatureFlag(name=name, enabled=enabled)
    else:
        flag.enabled = enabled
    session.add(flag)
    session.commit()
    return {"ok": True}

# ----------- ANALYTICS -----------
@app.get("/api/analytics/summary")
def analytics_summary(admin: User = Depends(get_current_admin), session: Session = Depends(get_session)):
    # simple counts
    views = session.exec(select(Event).where(Event.type=="view")).all()
    purchases = session.exec(select(Event).where(Event.type=="purchase")).all()
    # top products by purchases
    from collections import Counter
    c = Counter([e.product_id for e in purchases if e.product_id])
    top = [{"product_id": pid, "count": cnt} for pid, cnt in c.most_common(5)]
    return {"views": len(views), "purchases": len(purchases), "top_products": top}

# ----------- WebSocket -----------
@app.websocket("/ws/inventory")
async def inventory_ws(ws: WebSocket):
    await hub.connect(ws)
    try:
        while True:
            await ws.receive_text()  # heartbeat
    except Exception:
        hub.disconnect(ws)

# ----------- TRACKING -----------
@app.post("/api/track")
def track(event_type: str = Form(...), product_id: int | None = Form(None), session: Session = Depends(get_session), user: User | None = None):
    session.add(Event(type=event_type, product_id=product_id, user_id=user.id if user else None))
    session.commit()
    return {"ok": True}
