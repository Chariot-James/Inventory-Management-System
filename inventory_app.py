import streamlit as st
import pandas as pd
import datetime
import json
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
import certifi
import time

# --- Page Configuration (must be first) ---
st.set_page_config(page_title="Inventory Manager", layout="wide")

# --- MongoDB Connection ---
@st.cache_resource
def init_mongodb():
    """Initialize MongoDB connection"""
    try:
        # Get MongoDB connection string from Streamlit secrets
        if 'mongodb' in st.secrets:
            connection_string = st.secrets['mongodb']['connection_string']
        else:
            # Fallback for local development - you'll set this up
            connection_string = st.text_input("MongoDB Connection String", type="password", help="Enter your MongoDB Atlas connection string")
            if not connection_string:
                st.error("Please provide MongoDB connection string in secrets or input field")
                st.stop()
        
        # Connect with SSL certificate verification
        client = MongoClient(connection_string, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=5000)
        
        # Test connection
        client.admin.command('ping')
        
        # Get database and collection
        db = client.inventory_db
        collection = db.inventory
        
        # Create indexes for better performance
        collection.create_index("product_id", unique=True)
        collection.create_index([("brand", 1), ("product_name", 1)])
        
        return collection
    except (ConnectionFailure, ServerSelectionTimeoutError) as e:
        st.error(f"Failed to connect to MongoDB: {e}")
        st.error("Please check your connection string and internet connection")
        st.stop()
    except Exception as e:
        st.error(f"Database initialization error: {e}")
        st.stop()

# Initialize MongoDB collection
import streamlit as st

@st.cache_resource
def get_mongo_connection():
    return init_mongodb()

try:
    inventory_collection = get_mongo_connection()
    if inventory_collection is None:
        st.stop()
except:
    st.error("Database connection failed. Please check your setup.")
    st.stop()


# --- Enhanced Helper Functions ---
def add_item(brand, name, pid, min_qty, current_amount, per_package, per_box, per_case, cost, last_checked):
    """Add new inventory item"""
    try:
        current_time = datetime.datetime.now()
        
        item = {
            "brand": brand,
            "product_name": name,
            "product_id": pid,
            "minimum_individual_quantity": min_qty,
            "current_amount": current_amount,
            "per_package": per_package if per_package and per_package > 0 else None,
            "per_box": per_box if per_box and per_box > 0 else None,
            "per_case": per_case if per_case and per_case > 0 else None,
            "cost": float(cost),
            "last_checked": last_checked,
            "created_at": current_time,
            "updated_at": current_time
        }
        
        result = inventory_collection.insert_one(item)
        if result.inserted_id:
            return True
        return False
    except Exception as e:
        st.error(f"Failed to add item: {e}")
        return False

def get_inventory(filter_text=None):
    """Get inventory items with optional filtering"""
    try:
        if filter_text:
            # Case-insensitive search across brand, product_name, and product_id
            query = {
                "$or": [
                    {"brand": {"$regex": filter_text, "$options": "i"}},
                    {"product_name": {"$regex": filter_text, "$options": "i"}},
                    {"product_id": {"$regex": filter_text, "$options": "i"}}
                ]
            }
        else:
            query = {}
        
        # Get items sorted by brand, then product_name
        items = list(inventory_collection.find(query).sort([("brand", 1), ("product_name", 1)]))
        
        # Convert MongoDB documents to list format for compatibility
        result = []
        for item in items:
            result.append([
                item["brand"],
                item["product_name"],
                item["product_id"],
                item["minimum_individual_quantity"],
                item["current_amount"],
                item.get("per_package"),
                item.get("per_box"),
                item.get("per_case"),
                item["cost"],
                item["last_checked"],
                str(item["_id"])  # Convert ObjectId to string
            ])
        return result
    except Exception as e:
        st.error(f"Failed to retrieve inventory: {e}")
        return []

def delete_items(ids):
    """Delete items by their MongoDB ObjectIds"""
    try:
        from bson import ObjectId
        # Convert string IDs back to ObjectId
        object_ids = [ObjectId(id_str) for id_str in ids]
        result = inventory_collection.delete_many({"_id": {"$in": object_ids}})
        return result.deleted_count > 0
    except Exception as e:
        st.error(f"Failed to delete items: {e}")
        return False

def update_item(item_id, brand, product_name, product_id, min_qty, current_amount, per_package, per_box, per_case, cost, last_checked):
    """Update existing inventory item"""
    try:
        from bson import ObjectId
        current_time = datetime.datetime.now()
        
        update_data = {
            "brand": brand,
            "product_name": product_name,
            "product_id": product_id,
            "minimum_individual_quantity": min_qty,
            "current_amount": current_amount,
            "per_package": per_package if per_package and per_package > 0 else None,
            "per_box": per_box if per_box and per_box > 0 else None,
            "per_case": per_case if per_case and per_case > 0 else None,
            "cost": float(cost),
            "last_checked": last_checked,
            "updated_at": current_time
        }
        
        result = inventory_collection.update_one(
            {"_id": ObjectId(item_id)},
            {"$set": update_data}
        )
        return result.modified_count > 0
    except Exception as e:
        st.error(f"Failed to update item: {e}")
        return False

def export_csv():
    """Export inventory to CSV format"""
    try:
        items = get_inventory()
        if not items:
            return b""
        
        df = pd.DataFrame(items, columns=[
            'Brand', 'Product Name', 'Product ID', 'Min Individual Qty', 'Current Amount', 
            'Per Package', 'Per Box', 'Per Case', 'Cost', 'Last Checked', '_id'
        ])
        # Drop the internal ID column for export
        df = df.drop(columns=['_id'])
        return df.to_csv(index=False).encode('utf-8')
    except Exception as e:
        st.error(f"Failed to export CSV: {e}")
        return b""

def import_csv(uploaded_file):
    """Import CSV data to MongoDB"""
    try:
        df = pd.read_csv(uploaded_file)
        required_columns = ['Brand', 'Product Name', 'Product ID', 'Min Individual Qty', 'Current Amount', 'Cost', 'Last Checked']
        
        if not all(col in df.columns for col in required_columns):
            st.error(f"CSV must contain columns: {', '.join(required_columns)}")
            return False
        
        # Create backup by exporting current data
        backup_data = export_csv()
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        st.download_button(
            "Download Current Data as Backup",
            data=backup_data,
            file_name=f"backup_before_import_{timestamp}.csv",
            mime="text/csv"
        )
        
        # Ask for confirmation before clearing data
        if not st.session_state.get('confirm_csv_import', False):
            st.warning("⚠️ This will REPLACE ALL existing inventory data!")
            st.warning("Please download the backup above before proceeding.")
            if st.button("I understand - Proceed with Import"):
                st.session_state.confirm_csv_import = True
                st.rerun()
            return False
        
        # Clear existing data
        inventory_collection.delete_many({})
        
        # Import new data
        imported_count = 0
        current_time = datetime.datetime.now()
        
        for _, row in df.iterrows():
            per_package = row.get('Per Package', None)
            per_box = row.get('Per Box', None)
            per_case = row.get('Per Case', None)
            
            # Handle NaN values
            per_package = None if pd.isna(per_package) or per_package == 0 else int(per_package)
            per_box = None if pd.isna(per_box) or per_box == 0 else int(per_box)
            per_case = None if pd.isna(per_case) or per_case == 0 else int(per_case)
            
            item = {
                "brand": str(row['Brand']),
                "product_name": str(row['Product Name']),
                "product_id": str(row['Product ID']),
                "minimum_individual_quantity": int(row['Min Individual Qty']),
                "current_amount": int(row['Current Amount']),
                "per_package": per_package,
                "per_box": per_box,
                "per_case": per_case,
                "cost": float(row['Cost']) if pd.notna(row['Cost']) else 0.0,
                "last_checked": str(row['Last Checked']),
                "created_at": current_time,
                "updated_at": current_time
            }
            
            inventory_collection.insert_one(item)
            imported_count += 1
        
        # Reset confirmation state
        st.session_state.confirm_csv_import = False
        st.success(f"Successfully imported {imported_count} items!")
        return True
        
    except Exception as e:
        st.error(f"Error importing CSV: {e}")
        return False

def get_low_stock_items():
    """Get items that are low on stock"""
    try:
        query = {
            "$expr": {
                "$and": [
                    {"$lte": ["$current_amount", "$minimum_individual_quantity"]},
                    {"$gt": ["$minimum_individual_quantity", 0]}
                ]
            }
        }
        items = list(inventory_collection.find(query))
        
        # Convert to list format for compatibility
        result = []
        for item in items:
            result.append([
                item["brand"],
                item["product_name"],
                item["product_id"],
                item["minimum_individual_quantity"],
                item["current_amount"],
                item.get("per_package"),
                item.get("per_box"),
                item.get("per_case"),
                item["cost"],
                item["last_checked"],
                str(item["_id"])
            ])
        return result
    except Exception as e:
        st.error(f"Failed to get low stock items: {e}")
        return []

def export_inventory_html():
    """Generate HTML inventory report"""
    try:
        rows = get_inventory()
        
        if not rows:
            return None
        
        report_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        total_items = len(rows)
        total_value = sum(row[4] * row[8] for row in rows)  # current_amount * cost
        low_stock_count = sum(1 for row in rows if row[4] <= row[3] and row[3] > 0)
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Inventory Report</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    margin: 40px;
                    color: #333;
                }}
                .header {{
                    text-align: center;
                    border-bottom: 2px solid #333;
                    padding-bottom: 20px;
                    margin-bottom: 30px;
                }}
                .summary {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                    gap: 20px;
                    margin-bottom: 30px;
                    padding: 20px;
                    background-color: #f8f9fa;
                    border-radius: 8px;
                }}
                .summary-item {{
                    text-align: center;
                }}
                .summary-value {{
                    font-size: 24px;
                    font-weight: bold;
                    color: #2c3e50;
                }}
                .summary-label {{
                    font-size: 14px;
                    color: #666;
                    margin-top: 5px;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-bottom: 30px;
                }}
                th, td {{
                    border: 1px solid #ddd;
                    padding: 12px;
                    text-align: left;
                }}
                th {{
                    background-color: #f5f5f5;
                    font-weight: bold;
                }}
                .low-stock {{
                    background-color: #fff3cd;
                    color: #856404;
                }}
                .out-of-stock {{
                    background-color: #f8d7da;
                    color: #721c24;
                }}
                .good-stock {{
                    background-color: #d1edff;
                    color: #0c5460;
                }}
                .footer {{
                    margin-top: 50px;
                    border-top: 1px solid #ccc;
                    padding-top: 20px;
                    font-size: 12px;
                    color: #666;
                }}
                @media print {{
                    body {{ margin: 20px; }}
                    .no-print {{ display: none; }}
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Inventory Report</h1>
                <p>Mom's Inventory Management System</p>
            </div>
            
            <div class="summary">
                <div class="summary-item">
                    <div class="summary-value">{total_items}</div>
                    <div class="summary-label">Total Items</div>
                </div>
                <div class="summary-item">
                    <div class="summary-value">${total_value:.2f}</div>
                    <div class="summary-label">Total Value</div>
                </div>
                <div class="summary-item">
                    <div class="summary-value">{low_stock_count}</div>
                    <div class="summary-label">Low Stock Items</div>
                </div>
                <div class="summary-item">
                    <div class="summary-value">{report_date}</div>
                    <div class="summary-label">Report Generated</div>
                </div>
            </div>
            
            <table>
                <thead>
                    <tr>
                        <th>Brand</th>
                        <th>Product Name</th>
                        <th>Product ID</th>
                        <th>Min Individual Qty</th>
                        <th>Current Amount</th>
                        <th>Per Package</th>
                        <th>Per Box</th>
                        <th>Per Case</th>
                        <th>Unit Cost</th>
                        <th>Total Value</th>
                        <th>Stock Status</th>
                        <th>Last Checked</th>
                    </tr>
                </thead>
                <tbody>
        """
        
        for row in rows:
            brand, product_name, product_id, min_qty, current_amount, per_package, per_box, per_case, cost, last_checked, _ = row
            total_item_value = current_amount * cost
            
            # Determine stock status and styling
            if current_amount == 0:
                stock_status = "Out of Stock"
                row_class = "out-of-stock"
            elif current_amount <= min_qty and min_qty > 0:
                stock_status = "Low Stock"
                row_class = "low-stock"
            else:
                stock_status = "Good"
                row_class = "good-stock"
            
            # Handle None values for display
            per_package_display = per_package if per_package is not None else "-"
            per_box_display = per_box if per_box is not None else "-"
            per_case_display = per_case if per_case is not None else "-"
            
            html_content += f"""
                    <tr class="{row_class}">
                        <td>{brand}</td>
                        <td>{product_name}</td>
                        <td>{product_id}</td>
                        <td>{min_qty}</td>
                        <td>{current_amount}</td>
                        <td>{per_package_display}</td>
                        <td>{per_box_display}</td>
                        <td>{per_case_display}</td>
                        <td>${cost:.2f}</td>
                        <td>${total_item_value:.2f}</td>
                        <td><strong>{stock_status}</strong></td>
                        <td>{last_checked}</td>
                    </tr>
            """
        
        html_content += f"""
                </tbody>
            </table>
            
            <div class="footer">
                <p>Generated by Mom's Inventory Management System on {report_date}</p>
                <p>This report shows the complete inventory status with stock levels and values.</p>
                <p>Data is automatically backed up daily by MongoDB Atlas.</p>
            </div>
        </body>
        </html>
        """
        
        return html_content.encode('utf-8')
    except Exception as e:
        st.error(f"Failed to generate HTML report: {e}")
        return None

# --- Order Form Functions ---
def add_to_order(item_info, quantity):
    """Add item to current order"""
    if 'current_order' not in st.session_state:
        st.session_state.current_order = []
    
    # Check if item already in order
    for i, order_item in enumerate(st.session_state.current_order):
        if order_item['product_id'] == item_info[2]:
            st.session_state.current_order[i]['quantity'] += quantity
            return
    
    order_item = {
        'brand': item_info[0],
        'product_name': item_info[1],
        'product_id': item_info[2],
        'current_amount': item_info[4],
        'per_package': item_info[5],
        'per_box': item_info[6],
        'per_case': item_info[7],
        'cost': item_info[8],
        'quantity': quantity
    }
    st.session_state.current_order.append(order_item)

def remove_from_order(product_id):
    """Remove item from current order"""
    if 'current_order' in st.session_state:
        st.session_state.current_order = [
            item for item in st.session_state.current_order 
            if item['product_id'] != product_id
        ]

def update_order_quantity(product_id, new_quantity):
    """Update quantity of item in order"""
    if 'current_order' in st.session_state:
        for item in st.session_state.current_order:
            if item['product_id'] == product_id:
                item['quantity'] = new_quantity
                break

def clear_order():
    """Clear all items from current order"""
    st.session_state.current_order = []

def generate_order_html():
    """Generate HTML order form"""
    if 'current_order' not in st.session_state or not st.session_state.current_order:
        return None
    
    order_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    total_items = sum(item['quantity'] for item in st.session_state.current_order)
    total_cost = sum(item['quantity'] * item['cost'] for item in st.session_state.current_order)
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Inventory Order Form</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 40px;
                color: #333;
            }}
            .header {{
                text-align: center;
                border-bottom: 2px solid #333;
                padding-bottom: 20px;
                margin-bottom: 30px;
            }}
            .order-info {{
                margin-bottom: 30px;
                padding: 20px;
                background-color: #f8f9fa;
                border-radius: 8px;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin-bottom: 30px;
            }}
            th, td {{
                border: 1px solid #ddd;
                padding: 12px;
                text-align: left;
            }}
            th {{
                background-color: #f5f5f5;
                font-weight: bold;
            }}
            .totals {{
                margin-top: 20px;
                text-align: right;
                font-weight: bold;
                font-size: 16px;
                background-color: #e9ecef;
                padding: 15px;
                border-radius: 5px;
            }}
            .footer {{
                margin-top: 50px;
                border-top: 1px solid #ccc;
                padding-top: 20px;
                font-size: 12px;
                color: #666;
            }}
            @media print {{
                body {{ margin: 20px; }}
                .no-print {{ display: none; }}
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Purchase Order</h1>
            <p>Mom's Inventory Management System</p>
        </div>
        
        <div class="order-info">
            <p><strong>Order Date:</strong> {order_date}</p>
            <p><strong>Total Items Ordered:</strong> {total_items}</p>
            <p><strong>Order Total:</strong> ${total_cost:.2f}</p>
        </div>
        
        <table>
            <thead>
                <tr>
                    <th>Brand</th>
                    <th>Product Name</th>
                    <th>Product ID</th>
                    <th>Current Stock</th>
                    <th>Per Package</th>
                    <th>Per Box</th>
                    <th>Per Case</th>
                    <th>Quantity to Order</th>
                    <th>Unit/Case Cost</th>
                    <th>Total Cost</th>
                </tr>
            </thead>
            <tbody>
    """
    
    for item in st.session_state.current_order:
        item_total = item['quantity'] * item['cost']
        per_package_display = item['per_package'] if item['per_package'] is not None else "-"
        per_box_display = item['per_box'] if item['per_box'] is not None else "-"
        per_case_display = item['per_case'] if item['per_case'] is not None else "-"
        
        html_content += f"""
                <tr>
                    <td>{item['brand']}</td>
                    <td>{item['product_name']}</td>
                    <td>{item['product_id']}</td>
                    <td>{item['current_amount']}</td>
                    <td>{per_package_display}</td>
                    <td>{per_box_display}</td>
                    <td>{per_case_display}</td>
                    <td>{item['quantity']}</td>
                    <td>${item['cost']:.2f}</td>
                    <td>${item_total:.2f}</td>
                </tr>
        """
    
    html_content += f"""
            </tbody>
        </table>
        
        <div class="totals">
            <p>Total Items: {total_items}</p>
            <p>Total Cost: ${total_cost:.2f}</p>
        </div>
        
        <div class="footer">
            <p>Generated by Mom's Inventory Management System on {order_date}</p>
            <p>This purchase order can be printed or saved for your records.</p>
            <p>Data is automatically backed up daily by MongoDB Atlas.</p>
        </div>
    </body>
    </html>
    """
    
    return html_content.encode('utf-8')

# --- Session State Initialization ---
if 'show_add_form' not in st.session_state:
    st.session_state.show_add_form = False
if 'current_order' not in st.session_state:
    st.session_state.current_order = []
if 'confirm_csv_import' not in st.session_state:
    st.session_state.confirm_csv_import = False

# --- UI ---
st.title("Mom's Inventory Management System")

# Create Tabs
tab1, tab2 = st.tabs(["Inventory Management", "Order Form"])

# Sidebar (appears on both tabs)
with st.sidebar: 
    st.subheader("📊 Quick Stats")
    total_items = len(get_inventory())
    low_stock = get_low_stock_items()
    total_value = sum(item[4] * item[8] for item in get_inventory())
    
    st.metric("Total Items", total_items)
    st.metric("Low Stock Items", len(low_stock), delta=-len(low_stock) if low_stock else 0)
    st.metric("Total Inventory Value", f"${total_value:.2f}")
    
    st.divider()
    
    st.subheader("📁 Import/Export")
    
    # Export CSV
    csv_data = export_csv()
    st.download_button(
        "Download CSV", 
        data=csv_data, 
        file_name=f"inventory_{datetime.date.today().strftime('%Y%m%d')}.csv", 
        mime='text/csv',
        width="stretch",
        help="Download inventory data as spreadsheet"
    )
    
    # Export HTML Report
    html_report = export_inventory_html()
    if html_report:
        st.download_button(
            "Download HTML Report", 
            data=html_report, 
            file_name=f"inventory_report_{datetime.date.today().strftime('%Y%m%d')}.html", 
            mime='text/html',
            width="stretch",
            help="Download formatted inventory report"
        )
    
    # Import
    uploaded_file = st.file_uploader("Upload CSV", type=["csv"])
    if uploaded_file:
        import_csv(uploaded_file)

# TAB 1: Inventory Management
with tab1:
    # Low Stock Alert
    if low_stock:
        st.warning(f"**{len(low_stock)} item(s) are low on stock!**")
        with st.expander("View Low Stock Items"):
            low_stock_df = pd.DataFrame(low_stock, columns=[
                'Brand', 'Product Name', 'Product ID', 'Min Individual Qty', 'Current Amount', 
                'Per Package', 'Per Box', 'Per Case', 'Cost', 'Last Checked', '_id'
            ])
            # Drop the internal ID column for display
            low_stock_df = low_stock_df.drop(columns=['_id'])
            st.dataframe(low_stock_df, width="stretch", hide_index=True)

    # Add New Item
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("Add New Item", width="stretch"):
            st.session_state.show_add_form = not st.session_state.show_add_form

    if st.session_state.show_add_form:
        with st.container():
            st.subheader("Add New Item")
            with st.form("add_item_form", clear_on_submit=True):
                col1, col2 = st.columns(2)
                with col1:
                    brand = st.text_input("Brand *", placeholder="e.g., Nike, Apple")
                    product_id = st.text_input("Product ID *", placeholder="e.g., SKU123")
                    current_amount = st.number_input("Current Amount *", min_value=0, step=1, value=0)
                    per_box = st.number_input("Per Box", min_value=0, step=1, value=None, help="Leave empty if not applicable")
                    cost = st.number_input("Cost", min_value=0.0, step=0.01, value=0.0, format="%.2f")
                
                with col2:
                    product_name = st.text_input("Product Name *", placeholder="e.g., Running Shoes")
                    min_qty = st.number_input("Minimum Individual Quantity", min_value=0, step=1, value=1)
                    per_package = st.number_input("Per Package", min_value=0, step=1, value=None, help="Leave empty if not applicable")
                    per_case = st.number_input("Per Case", min_value=0, step=1, value=None, help="Leave empty if not applicable")
                    last_checked = st.date_input("Last Checked", value=datetime.date.today())
                
                col_submit, col_cancel = st.columns(2)
                with col_submit:
                    submitted = st.form_submit_button("Add Item", width="stretch")
                with col_cancel:
                    if st.form_submit_button("Cancel", width="stretch"):
                        st.session_state.show_add_form = False
                        st.rerun()
                
                if submitted:
                    if brand and product_name and product_id:
                        if add_item(brand, product_name, product_id, min_qty, current_amount, per_package, per_box, per_case, cost, last_checked.strftime('%Y-%m-%d')):
                            st.success(f"Added '{product_name}' by {brand}")
                            st.session_state.show_add_form = False
                            st.rerun()
                    else:
                        st.error("Please fill in all required fields (marked with *)")

    # Search & Manage Inventory
    st.subheader("Search & Manage Inventory")
    search = st.text_input("Search by brand, product name, or product ID", placeholder="Type to search...")

    # Inventory Table
    inventory = get_inventory(search)

    if inventory:
        df = pd.DataFrame(inventory, columns=[
            'Brand', 'Product Name', 'Product ID', 'Min Individual Qty', 'Current Amount', 
            'Per Package', 'Per Box', 'Per Case', 'Cost', 'Last Checked', '_id'
        ])
        
        # Convert Last Checked to datetime for proper editing
        df['Last Checked'] = pd.to_datetime(df['Last Checked'], errors='coerce').dt.date
        
        # Create display dataframe without the internal ID
        display_df = df.drop(columns=['_id'])
        
        edited_df = st.data_editor(
            display_df,
            width="stretch",
            hide_index=True,
            num_rows="dynamic",
            key="inventory_table",
            column_config={
                "Brand": st.column_config.TextColumn("Brand", width="medium"),
                "Product Name": st.column_config.TextColumn("Product Name", width="medium"),
                "Product ID": st.column_config.TextColumn("Product ID", width="medium"),
                "Min Individual Qty": st.column_config.NumberColumn("Min Individual Qty", min_value=0, width="small"),
                "Current Amount": st.column_config.NumberColumn("Current Amount", min_value=0, width="small"),
                "Per Package": st.column_config.NumberColumn("Per Package", min_value=0, width="small"),
                "Per Box": st.column_config.NumberColumn("Per Box", min_value=0, width="small"),
                "Per Case": st.column_config.NumberColumn("Per Case", min_value=0, width="small"),
                "Cost": st.column_config.NumberColumn("Cost", min_value=0.0, step=0.01, format="$%.2f", width="small"),
                "Last Checked": st.column_config.DateColumn("Last Checked", width="medium")
            }
        )
        
        # Save Changes Logic
        col_save, col_info = st.columns([2, 1])
        
        with col_save:
            if st.button("Save All Changes", width="stretch", type="primary"):
                try:
                    changes_made = False
                    
                    # Create a mapping of original data for comparison
                    original_data = {}
                    for i, row in df.iterrows():
                        original_data[row['_id']] = {
                            'Brand': row['Brand'],
                            'Product Name': row['Product Name'],
                            'Product ID': row['Product ID'],
                            'Min Individual Qty': row['Min Individual Qty'],
                            'Current Amount': row['Current Amount'],
                            'Per Package': row['Per Package'],
                            'Per Box': row['Per Box'],
                            'Per Case': row['Per Case'],
                            'Cost': row['Cost'],
                            'Last Checked': row['Last Checked']
                        }
                    
                    # Track which IDs we've processed
                    processed_ids = set()
                    
                    # Process each row in the edited dataframe
                    for _, edited_row in edited_df.iterrows():
                        # Skip empty rows
                        if pd.isna(edited_row['Brand']) or pd.isna(edited_row['Product Name']) or pd.isna(edited_row['Product ID']):
                            continue
                        
                        # Convert edited row data to proper types
                        brand = str(edited_row['Brand']).strip()
                        product_name = str(edited_row['Product Name']).strip()
                        product_id = str(edited_row['Product ID']).strip()
                        min_qty = int(edited_row['Min Individual Qty']) if pd.notna(edited_row['Min Individual Qty']) else 0
                        current_amount = int(edited_row['Current Amount']) if pd.notna(edited_row['Current Amount']) else 0
                        per_package = int(edited_row['Per Package']) if pd.notna(edited_row['Per Package']) and edited_row['Per Package'] > 0 else None
                        per_box = int(edited_row['Per Box']) if pd.notna(edited_row['Per Box']) and edited_row['Per Box'] > 0 else None
                        per_case = int(edited_row['Per Case']) if pd.notna(edited_row['Per Case']) and edited_row['Per Case'] > 0 else None
                        cost = float(edited_row['Cost']) if pd.notna(edited_row['Cost']) else 0.0
                        
                        # Handle date conversion
                        if isinstance(edited_row['Last Checked'], datetime.date):
                            last_checked_str = edited_row['Last Checked'].strftime('%Y-%m-%d')
                        elif pd.notna(edited_row['Last Checked']):
                            last_checked_str = str(edited_row['Last Checked'])
                        else:
                            last_checked_str = datetime.date.today().strftime('%Y-%m-%d')
                        
                        # Try to find this item in the original data by matching Product ID
                        matching_id = None
                        for orig_id, orig_data in original_data.items():
                            if orig_id not in processed_ids and str(orig_data['Product ID']).strip() == product_id:
                                matching_id = orig_id
                                break
                        
                        if matching_id:
                            # This is an existing item - check if it needs updating
                            processed_ids.add(matching_id)
                            orig_data = original_data[matching_id]
                            
                            # Check if any values have changed
                            needs_update = (
                                str(orig_data['Brand']).strip() != brand or
                                str(orig_data['Product Name']).strip() != product_name or
                                str(orig_data['Product ID']).strip() != product_id or
                                int(orig_data['Min Individual Qty']) != min_qty or
                                int(orig_data['Current Amount']) != current_amount or
                                orig_data['Per Package'] != per_package or
                                orig_data['Per Box'] != per_box or
                                orig_data['Per Case'] != per_case or
                                float(orig_data['Cost']) != cost or
                                str(orig_data['Last Checked']) != last_checked_str
                            )
                            
                            if needs_update:
                                if update_item(
                                    matching_id,
                                    brand,
                                    product_name, 
                                    product_id,
                                    min_qty,
                                    current_amount,
                                    per_package,
                                    per_box,
                                    per_case,
                                    cost,
                                    last_checked_str
                                ):
                                    changes_made = True
                        else:
                            # This is a new item
                            if add_item(
                                brand,
                                product_name,
                                product_id,
                                min_qty,
                                current_amount,
                                per_package,
                                per_box,
                                per_case,
                                cost,
                                last_checked_str
                            ):
                                changes_made = True
                    
                    # Handle deleted items (original items not found in edited data)
                    deleted_ids = []
                    for orig_id in original_data.keys():
                        if orig_id not in processed_ids:
                            deleted_ids.append(orig_id)
                    
                    if deleted_ids:
                        if delete_items(deleted_ids):
                            changes_made = True
                    
                    # Provide appropriate success message
                    if changes_made:
                        messages = []
                        new_items_count = len(edited_df) - len([pid for pid in processed_ids if pid in original_data])
                        if new_items_count > 0:
                            messages.append(f"Added {new_items_count} new item(s)")
                        if len(deleted_ids) > 0:
                            messages.append(f"Deleted {len(deleted_ids)} item(s)")
                        updated_count = len(processed_ids & original_data.keys())
                        if updated_count > 0:
                            messages.append(f"Updated {updated_count} existing item(s)")
                        
                        if messages:
                            st.success(f"{' and '.join(messages)}!")
                        else:
                            st.success("Changes saved successfully!")
                    else:
                        st.info("No changes detected")
                    
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"Error saving changes: {str(e)}")
        
        with col_info:
            # Show what changes will be made
            if 'inventory_table' in st.session_state:
                try:
                    if not edited_df.equals(display_df):
                        st.info("**Pending:** Changes detected")
                    else:
                        st.info("No changes detected")
                except:
                    st.info("**Pending:** Potential changes detected")
            else:
                st.info("No changes detected")

    else:
        if search:
            st.info(f"No items found matching '{search}'")
        else:
            st.info("No inventory items found. Add some items to get started!")

# TAB 2: Order Form
with tab2:
    st.subheader("Create Purchase Order")
    
    # Get current inventory for selection
    inventory_items = get_inventory()
    
    if not inventory_items:
        st.warning("No inventory items available. Please add items in the Inventory Management tab first.")
    else:
        # Create two columns for the order form layout
        col_left, col_right = st.columns([2, 1])
        
        with col_left:
            st.write("### Available Inventory")
            
            # Search/filter for items
            item_search = st.text_input("Search items to add to order", placeholder="Search by brand, product name, or ID...")
            
            # Filter inventory based on search
            filtered_inventory = get_inventory(item_search) if item_search else inventory_items
            
            if filtered_inventory:
                # Display available items
                for item in filtered_inventory:
                    brand, product_name, product_id, min_qty, current_amount, per_package, per_box, per_case, cost, last_checked, item_id = item
                    
                    # Create a container for each item
                    with st.container():
                        item_col1, item_col2, item_col3 = st.columns([3, 1, 1])
                        
                        with item_col1:
                            st.write(f"**{brand} - {product_name}**")
                            details_parts = [f"ID: {product_id}", f"Stock: {current_amount}", f"Cost: ${cost:.2f}"]
                            if per_package is not None and per_package > 0:
                                details_parts.append(f"Package: {per_package}")
                            if per_box is not None and per_box > 0:
                                details_parts.append(f"Box: {per_box}")
                            if per_case is not None and per_case > 0:
                                details_parts.append(f"Case: {per_case}")
                            st.write(" | ".join(details_parts))
                            
                            # Show stock status
                            if current_amount == 0:
                                st.error("Out of Stock")
                            elif current_amount <= min_qty and min_qty > 0:
                                st.warning(f"Low Stock (Min: {min_qty})")
                            else:
                                st.success("In Stock")
                        
                        with item_col2:
                            # Quantity input for this item
                            qty_key = f"qty_{item_id}_{product_id}"
                            quantity = st.number_input(
                                "Qty", 
                                min_value=1, 
                                value=1, 
                                step=1, 
                                key=qty_key,
                                label_visibility="collapsed"
                            )
                        
                        with item_col3:
                            # Add to order button
                            if st.button(f"Add", key=f"add_{item_id}", width="stretch"):
                                add_to_order(item, quantity)
                                st.success(f"Added {quantity} x {product_name}")
                                st.rerun()
                        
                        st.divider()
            else:
                st.info("No items match your search.")
        
        with col_right:
            st.write("### Current Order")
            
            if 'current_order' in st.session_state and st.session_state.current_order:
                # Order summary
                total_order_items = sum(item['quantity'] for item in st.session_state.current_order)
                total_order_cost = sum(item['quantity'] * item['cost'] for item in st.session_state.current_order)
                
                st.metric("Total Items", total_order_items)
                st.metric("Total Cost", f"${total_order_cost:.2f}")
                
                st.write("#### Order Details")
                
                # Display order items with ability to modify
                for i, order_item in enumerate(st.session_state.current_order):
                    with st.container():
                        st.write(f"**{order_item['brand']} - {order_item['product_name']}**")
                        st.write(f"ID: {order_item['product_id']}")
                        
                        # Show packaging details
                        packaging_parts = []
                        if order_item.get('per_package') is not None and order_item['per_package'] > 0:
                            packaging_parts.append(f"Package: {order_item['per_package']}")
                        if order_item.get('per_box') is not None and order_item['per_box'] > 0:
                            packaging_parts.append(f"Box: {order_item['per_box']}")
                        if order_item.get('per_case') is not None and order_item['per_case'] > 0:
                            packaging_parts.append(f"Case: {order_item['per_case']}")
                        if packaging_parts:
                            st.write(" | ".join(packaging_parts))
                        
                        # Quantity adjustment and remove options
                        order_col1, order_col2, order_col3 = st.columns([2, 1, 1])
                        
                        with order_col1:
                            new_qty = st.number_input(
                                "Quantity",
                                min_value=1,
                                value=order_item['quantity'],
                                step=1,
                                key=f"order_qty_{order_item['product_id']}_{i}"
                            )
                            if new_qty != order_item['quantity']:
                                update_order_quantity(order_item['product_id'], new_qty)
                                st.rerun()
                        
                        with order_col2:
                            st.write(f"${order_item['cost']:.2f} each")
                            st.write(f"**${new_qty * order_item['cost']:.2f}**")
                        
                        with order_col3:
                            if st.button("Remove", key=f"remove_order_{order_item['product_id']}_{i}", help="Remove from order"):
                                remove_from_order(order_item['product_id'])
                                st.rerun()
                        
                        st.divider()
                
                # Order actions
                st.write("#### Actions")
                
                col_export, col_clear = st.columns(2)
                
                with col_export:
                    order_html = generate_order_html()
                    if order_html:
                        st.download_button(
                            "Export Order (HTML)",
                            data=order_html,
                            file_name=f"purchase_order_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.html",
                            mime="text/html",
                            width="stretch",
                            type="primary"
                        )
                
                with col_clear:
                    if st.button("Clear All", width="stretch"):
                        if st.session_state.get('confirm_clear_order', False):
                            clear_order()
                            st.session_state.confirm_clear_order = False
                            st.success("Order cleared!")
                            st.rerun()
                        else:
                            st.session_state.confirm_clear_order = True
                            st.rerun()
                
                if st.session_state.get('confirm_clear_order', False):
                    st.warning("Are you sure you want to clear the entire order?")
                    col_confirm, col_cancel = st.columns(2)
                    with col_confirm:
                        if st.button("Yes, Clear Order"):
                            clear_order()
                            st.session_state.confirm_clear_order = False
                            st.rerun()
                    with col_cancel:
                        if st.button("Cancel"):
                            st.session_state.confirm_clear_order = False
                            st.rerun()
            
            else:
                st.info("No items in current order")
                st.write("Select items from the left to add them to your order.")

# Footer
st.divider()










