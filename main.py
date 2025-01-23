from fastapi import FastAPI, HTTPException, status, Query,Depends
from pydantic import BaseModel
import sqlite3
from typing import List, Optional
import datetime
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from datetime import datetime, timedelta


# FastAPI instance
app = FastAPI()

# Database Setup
DATABASE = 'orders_and_categories.db'

# OAuth2 password bearer for token authentication
oauth_scheme = OAuth2PasswordBearer(tokenUrl="token")



def get_db():
    db_connection = sqlite3.connect(DATABASE, check_same_thread=False)
    db_connection.row_factory = sqlite3.Row  # Enable access by column name
    return db_connection

# Pydantic Models
class OrderItem(BaseModel):
    dish_id: int
    quantity: int

class CreateOrder(BaseModel):
    user_id: Optional[int] = None  # Make user_id optional
    items: List[OrderItem]

class OrderResponse(BaseModel):
    order_id: int
    user_id: int
    items: List[OrderItem]
    status: str
    order_date: str

class UpdateOrderStatus(BaseModel):
    status: str
class Feedback(BaseModel):
    user_id: int
    order_id: int
    dish_id: int
    comments: str
    rating: int  # Rating can be between 1 and 5

class FeedbackResponse(BaseModel):
    message: str


class CategoryResponse(BaseModel):
    category_id: int
    name: str

class CreateCategory(BaseModel):
    name: str

class UpdateCategory(BaseModel):
    name: str


# Initialize database tables on startup
@app.on_event("startup")
def startup():
    db = get_db()
    cursor = db.cursor()

    # Create users table if it doesn't exist
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL
    )''')

    # Create orders table with a timestamp column if it does not exist
    cursor.execute('''CREATE TABLE IF NOT EXISTS orders (
        order_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        status TEXT NOT NULL,
        order_date DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )''')

    # Create order_items table if it does not exist
    cursor.execute('''CREATE TABLE IF NOT EXISTS order_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL,
        dish_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL,
        added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (order_id) REFERENCES orders (order_id)
    )''')
# Create the categories table
    cursor.execute('''CREATE TABLE IF NOT EXISTS categories (
        category_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')

    # Create the feedback table
    cursor.execute('''CREATE TABLE IF NOT EXISTS feedback (
        feedback_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        order_id INTEGER NOT NULL,
        dish_id INTEGER NOT NULL,
        comments TEXT,
        rating INTEGER NOT NULL,
        feedback_date DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (order_id) REFERENCES orders (order_id),
        FOREIGN KEY (dish_id) REFERENCES order_items (dish_id)
    )''')

    # Predefined categories to insert
    predefined_categories = [
        'Appetizer', 'Veg Curries', 'Pickles', 'Veg Fry', 'Dal',
        'Non Veg Curries', 'Veg Rice', 'Non-Veg Rice', 'Veg Pulusu', 'Breads', 'Desserts'
    ]
    cursor.execute('SELECT COUNT(*) FROM categories')
    if cursor.fetchone()[0] == 0:
        cursor.executemany('INSERT INTO categories (name) VALUES (?)', [(name,) for name in predefined_categories])
        db.commit()



   
# Order Management Routes
@app.post("/orders", response_model=OrderResponse, status_code=status.HTTP_201_CREATED, tags=["Order Management"])
async def create_order(order: CreateOrder):
    try:
        db = get_db()
        cursor = db.cursor()

        # If user_id is not provided, allocate a new user_id
        if not order.user_id:
            # Generate a new user ID by inserting a dummy user (with name as "New User")
            cursor.execute('INSERT INTO users (name) VALUES (?)', ("New User",))
            db.commit()
            order.user_id = cursor.lastrowid  # Get the newly allocated user_id
        
        # Insert order into orders table
        cursor.execute('INSERT INTO orders (user_id, status) VALUES (?, ?)', (order.user_id, 'Booked Successfully'))
        db.commit()
        order_id = cursor.lastrowid  # Get the last inserted order ID

        # Fetch the order date
        cursor.execute('SELECT order_date FROM orders WHERE order_id = ?', (order_id,))
        order_date = cursor.fetchone()["order_date"]

        # Insert order items into order_items table
        for item in order.items:
            cursor.execute('INSERT INTO order_items (order_id, dish_id, quantity) VALUES (?, ?, ?)', 
                           (order_id, item.dish_id, item.quantity))
        db.commit()

        return {
            "order_id": order_id,
            "user_id": order.user_id,
            "items": order.items,
            "status": "Booked Successfully",
            "order_date": order_date  # Include the order date in the response
        }
    except sqlite3.Error as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Error creating order: {str(e)}")

@app.get("/users/{user_id}/orders", response_model=List[OrderResponse], tags=["Order Management"])
async def get_user_orders(user_id: int):
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT * FROM orders WHERE user_id = ?', (user_id,))
    orders = cursor.fetchall()

    if not orders:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No orders found for user")

    response_orders = []
    for order in orders:
        cursor.execute('SELECT * FROM order_items WHERE order_id = ?', (order["order_id"],))
        items = cursor.fetchall()
        order_items = [{"dish_id": item["dish_id"], "quantity": item["quantity"]} for item in items]
        response_orders.append({
            "order_id": order["order_id"],
            "user_id": order["user_id"],
            "items": order_items,
            "status": order["status"],
            "order_date": order["order_date"]  # Include the order_date in the response
        })
    
    return response_orders


@app.get("/orders", response_model=List[OrderResponse], tags=["Order Management"])
async def get_all_orders():
    db = get_db()
    cursor = db.cursor()

    # Retrieve all orders from the database
    cursor.execute('SELECT order_id, user_id, status, order_date FROM orders')  # Explicitly select order_date
    orders = cursor.fetchall()

    if not orders:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No orders found")

    response_orders = []
    for order in orders:
        # Retrieve all items for the current order
        cursor.execute('SELECT * FROM order_items WHERE order_id = ?', (order["order_id"],))
        items = cursor.fetchall()

        # Prepare the order items
        order_items = [{"dish_id": item["dish_id"], "quantity": item["quantity"]} for item in items]

        # Append order details including date to the response
        response_orders.append({
            "order_id": order["order_id"],
            "user_id": order["user_id"],
            "items": order_items,
            "status": order["status"],
            "order_date": order["order_date"]  # Include the order_date in the response
        })

    return response_orders

@app.patch("/orders/{order_id}/status", response_model=OrderResponse, tags=["Order Management"])
async def update_order_status(order_id: int, status_update: UpdateOrderStatus):
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT * FROM orders WHERE order_id = ?', (order_id,))
    order = cursor.fetchone()

    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    
    cursor.execute('UPDATE orders SET status = ? WHERE order_id = ?', (status_update.status, order_id))
    db.commit()

    cursor.execute('SELECT * FROM order_items WHERE order_id = ?', (order_id,))
    items = cursor.fetchall()
    order_items = [{"dish_id": item["dish_id"], "quantity": item["quantity"]} for item in items]

    return {
        "order_id": order["order_id"],
        "user_id": order["user_id"],
        "items": order_items,
        "status": status_update.status,
        "order_date": order["order_date"]  # Include the order_date in the response
    }
@app.delete("/orders/{order_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Order Management"])
async def delete_order(order_id: int):
    db = get_db()
    cursor = db.cursor()

    # Check if the order exists
    cursor.execute('SELECT * FROM orders WHERE order_id = ?', (order_id,))
    order = cursor.fetchone()

    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    try:
        # Delete all items associated with the order
        cursor.execute('DELETE FROM order_items WHERE order_id = ?', (order_id,))

        # Delete the order
        cursor.execute('DELETE FROM orders WHERE order_id = ?', (order_id,))

        db.commit()

        return {"detail": "Order deleted successfully"}

    except sqlite3.Error as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Error deleting order: {str(e)}")

@app.get("/admin/reports/sales", tags=["Reports"])
async def get_sales_report(token: str = Depends(oauth_scheme), period: str = Query("daily", enum=["daily", "weekly", "monthly"], description="Time period for the sales report")):
    """
    Generate a sales report based on the number of orders and items sold for the specified period.
    """
    try:
        db = get_db()
        cursor = db.cursor()

        # Get the current time
        now = datetime.now()

        # Calculate the start date based on the period
        if period == "daily":
            start_date = now - timedelta(days=1)
        elif period == "weekly":
            start_date = now - timedelta(weeks=1)
        elif period == "monthly":
            start_date = now - timedelta(weeks=4)
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid period specified")

        # Format the start_date to match SQLite format
        start_date_str = start_date.strftime('%Y-%m-%d %H:%M:%S')

        # Query to get sales data grouped by date
        cursor.execute('''
            SELECT DATE(o.order_date) AS sale_date,
                   COUNT(DISTINCT o.order_id) AS total_orders,
                   SUM(oi.quantity) AS total_items_sold
            FROM orders o
            JOIN order_items oi ON o.order_id = oi.order_id
            WHERE o.order_date >= ?
            GROUP BY sale_date
            ORDER BY sale_date DESC;
        ''', (start_date_str,))

        sales_data = cursor.fetchall()

        # If no data is found, return a friendly message
        if not sales_data:
            return {"message": "No sales data found for the specified period"}

        # Prepare the sales report
        sales_report = [
            {
                "sale_day": row["sale_date"],
                "total_orders": row["total_orders"],
                "total_items_sold": row["total_items_sold"]
            }
            for row in sales_data
        ]

        return sales_report

    except sqlite3.Error as e:
        # Handle database errors
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        # Catch other exceptions and return a server error
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")


@app.post("/token")
async def token_generate(form_data: OAuth2PasswordRequestForm = Depends()):
    # Example: We return the username as the access token (in a real-world scenario, JWT tokens are recommended)
    return {"access_token": form_data.username, "token_type": "bearer"}

@app.get("/categories", response_model=List[CategoryResponse], tags=["Category Management"])
async def get_categories(token: str = Depends(oauth_scheme)):
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT * FROM categories')
    categories = cursor.fetchall()

    if not categories:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No categories found")

    return [{"category_id": category["category_id"], "name": category["name"]} for category in categories]

@app.post("/categories", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED, tags=["Category Management"])
async def add_category(category: CreateCategory,token: str = Depends(oauth_scheme)):
    db = get_db()
    cursor = db.cursor()

    # Check if the category already exists
    cursor.execute('SELECT * FROM categories WHERE name = ?', (category.name,))
    existing_category = cursor.fetchone()
    if existing_category:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category already exists")

    # Insert the new category into the database
    cursor.execute('INSERT INTO categories (name) VALUES (?)', (category.name,))
    db.commit()

    return {
        "category_id": cursor.lastrowid,
        "name": category.name
    }

@app.put("/categories/{category_id}", tags=["Category Management"])
async def update_category(category_id: int, updated_category: UpdateCategory,token: str = Depends(oauth_scheme)):
    db = get_db()
    cursor = db.cursor()

    # Check if the category exists
    cursor.execute('SELECT * FROM categories WHERE category_id = ?', (category_id,))
    existing_category = cursor.fetchone()
    if not existing_category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

    # Check if the new name already exists in another category
    cursor.execute('SELECT * FROM categories WHERE name = ? AND category_id != ?', (updated_category.name, category_id))
    duplicate_category = cursor.fetchone()
    if duplicate_category:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category name already exists")

    # Update the category name
    cursor.execute('UPDATE categories SET name = ? WHERE category_id = ?', (updated_category.name, category_id))
    db.commit()

    return {
        "message": f"Category with ID {category_id} updated successfully",
        "category_id": category_id,
        "name": updated_category.name
    }

@app.delete("/categories/{category_id}", tags=["Category Management"])
async def delete_category(category_id: int,token: str = Depends(oauth_scheme)):
    db = get_db()
    cursor = db.cursor()

    # Check if the category exists
    cursor.execute('SELECT * FROM categories WHERE category_id = ?', (category_id,))
    existing_category = cursor.fetchone()
    if not existing_category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

    # Delete the category
    cursor.execute('DELETE FROM categories WHERE category_id = ?', (category_id,))
    db.commit()

    return {
        "message": f"Category with ID {category_id} deleted successfully"
    }

# ========================
# Feedback Routes
# ========================
@app.post("/feedback", response_model=FeedbackResponse, tags=["Feedback"])
async def submit_feedback(feedback: Feedback):
    db = get_db()
    cursor = db.cursor()

    try:
        # Check if the order exists
        cursor.execute('SELECT * FROM orders WHERE order_id = ?', (feedback.order_id,))
        order = cursor.fetchone()
        if not order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

        # Insert feedback into feedback table
        cursor.execute('''INSERT INTO feedback (user_id, order_id, dish_id, comments, rating)
                          VALUES (?, ?, ?, ?, ?)''', 
                          (feedback.user_id, feedback.order_id, feedback.dish_id, feedback.comments, feedback.rating))
        db.commit()

        return {"message": "Feedback submitted successfully"}
    except sqlite3.Error as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Error submitting feedback: {str(e)}")

@app.get("/menu/dishes/{dish_id}/feedback", response_model=List[Feedback], tags=["Feedback"])
async def get_feedback_for_dish(dish_id: int):
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute('''SELECT * FROM feedback WHERE dish_id = ?''', (dish_id,))
    feedbacks = cursor.fetchall()

    if not feedbacks:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No feedback found for this dish")

    return [
        {"user_id": feedback["user_id"], 
         "order_id": feedback["order_id"], 
         "dish_id": feedback["dish_id"], 
         "comments": feedback["comments"], 
         "rating": feedback["rating"]}
        for feedback in feedbacks
    ]
