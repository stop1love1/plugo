"""
Mock API endpoints for demo/playground pages.
Simulates a real e-commerce site so the AI agent can demonstrate tool calling.
All state is in-memory and resets on server restart.
"""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from typing import Optional
from logging_config import logger

router = APIRouter(prefix="/api/demo", tags=["demo"])

# ---------------------------------------------------------------------------
# In-memory data store
# ---------------------------------------------------------------------------

PRODUCTS = [
    {"id": 1, "name": "Wireless Headphones Pro", "price": 79.99, "category": "electronics",
     "description": "Premium noise-cancelling wireless headphones with 30h battery life.",
     "rating": 4.7, "stock": 25, "image": "headphones"},
    {"id": 2, "name": "Smart Watch X200", "price": 199.99, "category": "electronics",
     "description": "Fitness tracker, heart rate monitor, GPS, 5ATM water resistance.",
     "rating": 4.5, "stock": 12, "image": "watch"},
    {"id": 3, "name": "Organic Coffee Beans 1kg", "price": 24.99, "category": "food",
     "description": "Single-origin Arabica beans from Colombia. Medium roast.",
     "rating": 4.8, "stock": 50, "image": "coffee"},
    {"id": 4, "name": "Ergonomic Office Chair", "price": 349.99, "category": "furniture",
     "description": "Adjustable lumbar support, mesh back, 4D armrests.",
     "rating": 4.6, "stock": 8, "image": "chair"},
    {"id": 5, "name": "Running Shoes AirMax", "price": 129.99, "category": "sports",
     "description": "Lightweight mesh upper, responsive cushioning, 8mm drop.",
     "rating": 4.4, "stock": 30, "image": "shoes"},
    {"id": 6, "name": "Mechanical Keyboard RGB", "price": 89.99, "category": "electronics",
     "description": "Cherry MX Blue switches, per-key RGB, hot-swappable.",
     "rating": 4.3, "stock": 18, "image": "keyboard"},
    {"id": 7, "name": "Yoga Mat Premium", "price": 39.99, "category": "sports",
     "description": "6mm thick, non-slip surface, eco-friendly TPE material.",
     "rating": 4.9, "stock": 45, "image": "yogamat"},
    {"id": 8, "name": "Portable Bluetooth Speaker", "price": 49.99, "category": "electronics",
     "description": "360-degree sound, IPX7 waterproof, 12h playtime.",
     "rating": 4.2, "stock": 22, "image": "speaker"},
]

FAQS = [
    {"id": 1, "question": "What is your return policy?",
     "answer": "You can return any item within 30 days of purchase for a full refund. Items must be in original packaging."},
    {"id": 2, "question": "How long does shipping take?",
     "answer": "Standard shipping: 5-7 business days. Express shipping: 2-3 business days. Free shipping on orders over $50."},
    {"id": 3, "question": "Do you offer international shipping?",
     "answer": "Yes, we ship to over 50 countries. International shipping takes 10-15 business days."},
    {"id": 4, "question": "How do I track my order?",
     "answer": "After your order ships, you'll receive an email with a tracking number. You can also check order status in your account dashboard."},
    {"id": 5, "question": "What payment methods do you accept?",
     "answer": "We accept Visa, Mastercard, PayPal, Apple Pay, and Google Pay."},
]

# Mutable state (per-process, resets on restart)
_users: dict[str, dict] = {
    "demo@shop.com": {
        "id": "usr_demo_001",
        "name": "Demo User",
        "email": "demo@shop.com",
        "password": "demo123",
        "created_at": "2025-01-15T10:00:00Z",
    }
}
_tokens: dict[str, str] = {}  # token → email
_carts: dict[str, list] = {}  # user_id → cart items
_orders: dict[str, dict] = {}  # order_id → order
_user_orders: dict[str, list] = {}  # user_id → [order_id]
_tickets: dict[str, dict] = {}  # ticket_id → ticket


def _get_user_from_token(authorization: str | None) -> dict | None:
    if not authorization:
        return None
    token = authorization.replace("Bearer ", "")
    email = _tokens.get(token)
    if not email:
        return None
    return _users.get(email)


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str


@router.post("/auth/login")
async def demo_login(data: LoginRequest):
    user = _users.get(data.email)
    if not user or user["password"] != data.password:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = f"demo_tk_{uuid.uuid4().hex[:16]}"
    _tokens[token] = data.email
    return {
        "token": token,
        "user": {"id": user["id"], "name": user["name"], "email": user["email"]},
        "message": "Login successful",
    }


@router.post("/auth/register")
async def demo_register(data: RegisterRequest):
    if data.email in _users:
        raise HTTPException(status_code=400, detail="Email already registered")
    user_id = f"usr_{uuid.uuid4().hex[:8]}"
    _users[data.email] = {
        "id": user_id,
        "name": data.name,
        "email": data.email,
        "password": data.password,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    token = f"demo_tk_{uuid.uuid4().hex[:16]}"
    _tokens[token] = data.email
    return {
        "token": token,
        "user": {"id": user_id, "name": data.name, "email": data.email},
        "message": "Registration successful",
    }


@router.get("/auth/me")
async def demo_get_me(authorization: Optional[str] = Header(None)):
    user = _get_user_from_token(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated. Please log in first.")
    return {"id": user["id"], "name": user["name"], "email": user["email"], "created_at": user["created_at"]}


# ---------------------------------------------------------------------------
# Products endpoints
# ---------------------------------------------------------------------------

@router.get("/products")
async def demo_list_products(category: Optional[str] = None, search: Optional[str] = None):
    results = PRODUCTS
    if category:
        results = [p for p in results if p["category"] == category.lower()]
    if search:
        q = search.lower()
        results = [p for p in results if q in p["name"].lower() or q in p["description"].lower()]
    return {"products": results, "total": len(results)}


@router.get("/products/{product_id}")
async def demo_get_product(product_id: int):
    product = next((p for p in PRODUCTS if p["id"] == product_id), None)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


# ---------------------------------------------------------------------------
# Cart endpoints
# ---------------------------------------------------------------------------

class CartAddRequest(BaseModel):
    product_id: int
    quantity: int = 1


class CartRemoveRequest(BaseModel):
    product_id: int


@router.post("/cart/add")
async def demo_add_to_cart(data: CartAddRequest, authorization: Optional[str] = Header(None)):
    user = _get_user_from_token(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Please log in to add items to cart.")
    uid = user["id"]
    if uid not in _carts:
        _carts[uid] = []
    product = next((p for p in PRODUCTS if p["id"] == data.product_id), None)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    # Check if already in cart
    for item in _carts[uid]:
        if item["product_id"] == data.product_id:
            item["quantity"] += data.quantity
            return _build_cart_response(uid)
    _carts[uid].append({"product_id": data.product_id, "name": product["name"],
                         "price": product["price"], "quantity": data.quantity})
    return _build_cart_response(uid)


@router.get("/cart")
async def demo_get_cart(authorization: Optional[str] = Header(None)):
    user = _get_user_from_token(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Please log in to view your cart.")
    return _build_cart_response(user["id"])


@router.post("/cart/remove")
async def demo_remove_from_cart(data: CartRemoveRequest, authorization: Optional[str] = Header(None)):
    user = _get_user_from_token(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Please log in first.")
    uid = user["id"]
    if uid in _carts:
        _carts[uid] = [i for i in _carts[uid] if i["product_id"] != data.product_id]
    return _build_cart_response(uid)


def _build_cart_response(user_id: str) -> dict:
    items = _carts.get(user_id, [])
    total = sum(i["price"] * i["quantity"] for i in items)
    return {"items": items, "total": round(total, 2), "item_count": sum(i["quantity"] for i in items)}


# ---------------------------------------------------------------------------
# Orders endpoints
# ---------------------------------------------------------------------------

@router.post("/orders/create")
async def demo_create_order(authorization: Optional[str] = Header(None)):
    user = _get_user_from_token(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Please log in to place an order.")
    uid = user["id"]
    cart = _carts.get(uid, [])
    if not cart:
        raise HTTPException(status_code=400, detail="Cart is empty. Add items before placing an order.")
    order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
    total = round(sum(i["price"] * i["quantity"] for i in cart), 2)
    order = {
        "id": order_id,
        "user_id": uid,
        "items": list(cart),
        "total": total,
        "status": "confirmed",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "estimated_delivery": "3-5 business days",
    }
    _orders[order_id] = order
    if uid not in _user_orders:
        _user_orders[uid] = []
    _user_orders[uid].append(order_id)
    _carts[uid] = []  # Clear cart
    return {"message": "Order placed successfully!", "order": order}


@router.get("/orders")
async def demo_list_orders(authorization: Optional[str] = Header(None)):
    user = _get_user_from_token(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Please log in to view orders.")
    uid = user["id"]
    order_ids = _user_orders.get(uid, [])
    orders = [_orders[oid] for oid in order_ids if oid in _orders]
    return {"orders": orders, "total": len(orders)}


@router.get("/orders/{order_id}")
async def demo_get_order(order_id: str, authorization: Optional[str] = Header(None)):
    user = _get_user_from_token(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Please log in to view order details.")
    order = _orders.get(order_id)
    if not order or order["user_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


# ---------------------------------------------------------------------------
# Support endpoints
# ---------------------------------------------------------------------------

class TicketRequest(BaseModel):
    subject: str
    message: str


@router.get("/support/faq")
async def demo_faq():
    return {"faqs": FAQS}


@router.post("/support/ticket")
async def demo_create_ticket(data: TicketRequest, authorization: Optional[str] = Header(None)):
    user = _get_user_from_token(authorization)
    ticket_id = f"TK-{uuid.uuid4().hex[:6].upper()}"
    ticket = {
        "id": ticket_id,
        "subject": data.subject,
        "message": data.message,
        "status": "open",
        "user": user["name"] if user else "Anonymous",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _tickets[ticket_id] = ticket
    return {"message": "Support ticket created.", "ticket": ticket}


# ---------------------------------------------------------------------------
# Auto-provision demo tools for a site
# ---------------------------------------------------------------------------

DEMO_TOOLS = [
    {
        "name": "search_products",
        "description": "Search products in the store catalog. Use when user asks about products, items, or shopping.",
        "method": "GET",
        "url": "/api/demo/products",
        "params_schema": {
            "category": {"type": "string", "description": "Filter by category: electronics, food, furniture, sports"},
            "search": {"type": "string", "description": "Search keyword in product name/description"},
        },
    },
    {
        "name": "get_product_details",
        "description": "Get detailed info about a specific product by its ID.",
        "method": "GET",
        "url": "/api/demo/products/{product_id}",
        "params_schema": {
            "product_id": {"type": "integer", "description": "The product ID number", "required": True},
        },
    },
    {
        "name": "user_login",
        "description": "Log in a user with email and password. Default demo account: demo@shop.com / demo123",
        "method": "POST",
        "url": "/api/demo/auth/login",
        "params_schema": {
            "email": {"type": "string", "description": "User email address", "required": True},
            "password": {"type": "string", "description": "User password", "required": True},
        },
    },
    {
        "name": "user_register",
        "description": "Register a new user account.",
        "method": "POST",
        "url": "/api/demo/auth/register",
        "params_schema": {
            "name": {"type": "string", "description": "Full name", "required": True},
            "email": {"type": "string", "description": "Email address", "required": True},
            "password": {"type": "string", "description": "Password", "required": True},
        },
    },
    {
        "name": "add_to_cart",
        "description": "Add a product to the user's shopping cart. Requires login.",
        "method": "POST",
        "url": "/api/demo/cart/add",
        "params_schema": {
            "product_id": {"type": "integer", "description": "Product ID to add", "required": True},
            "quantity": {"type": "integer", "description": "Quantity (default 1)"},
        },
    },
    {
        "name": "view_cart",
        "description": "View current shopping cart contents and total. Requires login.",
        "method": "GET",
        "url": "/api/demo/cart",
        "params_schema": {},
    },
    {
        "name": "remove_from_cart",
        "description": "Remove a product from cart. Requires login.",
        "method": "POST",
        "url": "/api/demo/cart/remove",
        "params_schema": {
            "product_id": {"type": "integer", "description": "Product ID to remove", "required": True},
        },
    },
    {
        "name": "place_order",
        "description": "Place an order for all items in cart. Requires login and non-empty cart.",
        "method": "POST",
        "url": "/api/demo/orders/create",
        "params_schema": {},
    },
    {
        "name": "view_orders",
        "description": "View user's order history. Requires login.",
        "method": "GET",
        "url": "/api/demo/orders",
        "params_schema": {},
    },
    {
        "name": "get_faq",
        "description": "Get frequently asked questions about shipping, returns, payments, etc.",
        "method": "GET",
        "url": "/api/demo/support/faq",
        "params_schema": {},
    },
    {
        "name": "create_support_ticket",
        "description": "Create a support ticket for the user. Use when user has a problem or complaint.",
        "method": "POST",
        "url": "/api/demo/support/ticket",
        "params_schema": {
            "subject": {"type": "string", "description": "Ticket subject/title", "required": True},
            "message": {"type": "string", "description": "Detailed description of the issue", "required": True},
        },
    },
]


async def ensure_demo_tools(site_id: str, repos, base_url: str = "http://localhost:8000"):
    """Create demo tools for a site if they don't exist yet."""
    try:
        existing = await repos.tools.list_by_site(site_id)
        existing_names = {t["name"] for t in existing}
        created = 0
        for tool_def in DEMO_TOOLS:
            if tool_def["name"] in existing_names:
                continue
            url = tool_def["url"]
            if url.startswith("/"):
                url = base_url + url
            await repos.tools.create({
                "site_id": site_id,
                "name": tool_def["name"],
                "description": tool_def["description"],
                "method": tool_def["method"],
                "url": url,
                "params_schema": tool_def["params_schema"],
                "headers": {},
                "auth_type": None,
                "auth_value": None,
                "enabled": True,
            })
            created += 1
        if created:
            logger.info("Demo tools provisioned", site_id=site_id, count=created)
    except Exception as e:
        logger.warning("Failed to provision demo tools", site_id=site_id, error=str(e))
