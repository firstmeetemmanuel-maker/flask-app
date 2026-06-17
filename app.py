from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import json
import os
import uuid
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, template_folder='templates')
app.secret_key = os.environ.get('SECRET_KEY', 'change-this-to-a-long-random-secret-key')

app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'webm'}
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

PRODUCTS_FILE = os.path.join(BASE_DIR, 'products.json')
CHATS_FILE = os.path.join(BASE_DIR, 'chats.json')
ADMIN_FILE = os.path.join(BASE_DIR, 'admin.json')

_JSON_CACHE = {}

def load_json(path, default):
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return default

    cached = _JSON_CACHE.get(path)
    if cached and cached['mtime'] == mtime:
        return cached['data']

    with open(path, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except:
            data = default

    _JSON_CACHE[path] = {'mtime': mtime, 'data': data}
    return data

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    try:
        _JSON_CACHE[path] = {'mtime': os.path.getmtime(path), 'data': data}
    except OSError:
        pass

def load_products():
    products = load_json(PRODUCTS_FILE, [])
    for p in products:
        try:
            p['id'] = int(p['id'])
        except:
            pass
    return products

def save_products(products):
    save_json(PRODUCTS_FILE, products)

def load_chats():
    return load_json(CHATS_FILE, {})

def save_chats(chats):
    save_json(CHATS_FILE, chats)

def load_admin():
    admin = load_json(ADMIN_FILE, {})
    if not admin:
        admin = {
            "username": "admin",
            "password_hash": generate_password_hash("pathaan2345")
        }
        save_admin(admin)
    return admin

def save_admin(admin):
    save_json(ADMIN_FILE, admin)

def get_visitor_id():
    if 'visitor_id' not in session:
        session['visitor_id'] = str(uuid.uuid4())
    return session['visitor_id']

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_chat_status(chat):
    return chat.get('status', 'pending' if chat.get('messages') else 'new')

@app.context_processor
def inject_notifications():
    chats = load_chats()
    visitor_id = session.get('visitor_id')
    unread_reply_count = 0
    pending_chat_count = 0

    for chat in chats.values():
        if chat.get('status') == 'pending':
            pending_chat_count += 1
        if visitor_id and chat.get('visitor_id') == visitor_id and chat.get('status') == 'replied' and not chat.get('customer_seen_reply'):
            unread_reply_count += 1

    return dict(
        unread_reply_count=unread_reply_count,
        pending_chat_count=pending_chat_count,
        admin_name=session.get('admin_name')
    )

@app.route('/')
def index():
    products = load_products()
    chats = load_chats()
    visitor_id = session.get('visitor_id')
    unread_replies = []
    search_query = request.args.get('q', '').strip().lower()

    if search_query:
        products = [
            p for p in products
            if search_query in str(p.get('name', '')).lower()
            or search_query in str(p.get('description', '')).lower()
        ]

    if visitor_id:
        for chat_id, chat in chats.items():
            if chat.get('visitor_id') == visitor_id and chat.get('status') == 'replied':
                unread_replies.append(chat)

    return render_template(
        'index.html',
        products=products,
        unread_replies=unread_replies,
        show_welcome=True,
        search_query=search_query,
        manufacturer_name="Bemzy",
        welcome_message="Welcome to Picass's electronics"
    )

@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    admin = load_admin()
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if username == admin.get('username') and check_password_hash(admin.get('password_hash', ''), password):
            session['admin_logged_in'] = True
            session['admin_name'] = admin.get('username')
            return redirect(url_for('admin_dashboard'))

        flash('Incorrect username or password', 'danger')
    return render_template('admin.html', admin_name=admin.get('username', 'admin'))

@app.route('/admin/settings', methods=['GET', 'POST'])
def admin_settings():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    admin = load_admin()

    if request.method == 'POST':
        new_username = request.form.get('username', '').strip()
        new_password = request.form.get('password', '').strip()

        if 'admin' not in new_username.lower():
            flash("Admin name must include 'admin'.", 'danger')
            return redirect(url_for('admin_settings'))

        admin['username'] = new_username
        if new_password:
            admin['password_hash'] = generate_password_hash(new_password)

        save_admin(admin)
        session['admin_name'] = admin['username']
        flash('Admin profile updated successfully.', 'success')
        return redirect(url_for('admin_settings'))

    return render_template('admin_settings.html', admin=admin)

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    products = load_products()
    chats = load_chats()
    chat_list = []
    pending_chats = []

    for chat_id, chat in chats.items():
        messages = chat.get('messages', [])
        last_message = messages[-1].get('text', '') if messages else ''
        item = {
            'chat_id': chat_id,
            'product_id': chat.get('product_id'),
            'visitor_id': chat.get('visitor_id'),
            'last_message': last_message,
            'updated_at': chat.get('updated_at', ''),
            'status': get_chat_status(chat)
        }
        chat_list.append(item)

        if item['status'] == 'pending':
            pending_chats.append(item)

    chat_list = sorted(chat_list, key=lambda x: x['updated_at'], reverse=True)
    pending_chats = sorted(pending_chats, key=lambda x: x['updated_at'], reverse=True)

    return render_template(
        'admin_dashboard.html',
        products=products,
        chats=chat_list,
        pending_chats=pending_chats,
        pending_chat_count=len(pending_chats)
    )

@app.route('/admin/add_product', methods=['POST'])
def add_product():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    products = load_products()
    file = request.files.get('media')
    media_url = ''

    if file and file.filename:
        if allowed_file(file.filename):
            filename = secure_filename(file.filename)
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(save_path)
            media_url = '/' + os.path.relpath(save_path, BASE_DIR).replace('\\', '/')
        else:
            flash('Only image or video files are allowed', 'danger')
            return redirect(url_for('admin_dashboard'))

    new_product = {
        'id': (max([p.get('id', 0) for p in products], default=0) + 1),
        'name': request.form.get('product_name'),
        'description': request.form.get('product_description'),
        'price': request.form.get('product_price'),
        'old_price': request.form.get('old_price', ''),
        'image': media_url or request.form.get('product_image') or '',
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }

    products.append(new_product)
    save_products(products)
    flash('Product added successfully', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/update_price/<int:product_id>', methods=['POST'])
def update_price(product_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    products = load_products()
    new_price = request.form.get('new_price', '').strip()

    for product in products:
        if int(product.get('id', 0)) == product_id:
            current_price = str(product.get('price', ''))
            if current_price and current_price != new_price:
                product['old_price'] = current_price
                product['price'] = new_price
                product['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            elif new_price:
                product['price'] = new_price
            break

    save_products(products)
    flash('Price updated successfully', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/product/<int:product_id>/chat', methods=['GET', 'POST'])
def private_chat(product_id):
    visitor_id = get_visitor_id()
    chats = load_chats()
    chat_id = f"{product_id}_{visitor_id}"

    if chat_id not in chats:
        chats[chat_id] = {
            'product_id': product_id,
            'visitor_id': visitor_id,
            'messages': [],
            'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'status': 'new',
            'customer_seen_reply': False
        }

    if request.method == 'POST':
        message = request.form.get('message', '').strip()
        if message:
            chats[chat_id]['messages'].append({
                'sender': 'visitor',
                'text': message,
                'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
            chats[chat_id]['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            chats[chat_id]['status'] = 'pending'
            chats[chat_id]['customer_seen_reply'] = False
            save_chats(chats)
            flash('Message sent', 'success')
        return redirect(url_for('private_chat', product_id=product_id))

    product = next((p for p in load_products() if int(p.get('id', 0)) == product_id), None)
    chat = chats[chat_id]

    if chat.get('status') == 'replied' and not chat.get('customer_seen_reply'):
        flash('Your message has been replied to.', 'info')
        chat['customer_seen_reply'] = True
        save_chats(chats)

    return render_template('chat.html', product=product, chat=chat, chat_id=chat_id)

@app.route('/admin/chat/<chat_id>', methods=['GET', 'POST'])
def admin_chat(chat_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    chats = load_chats()
    if chat_id not in chats:
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        reply = request.form.get('message', '').strip()
        if reply:
            chats[chat_id]['messages'].append({
                'sender': 'admin',
                'text': reply,
                'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
            chats[chat_id]['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            chats[chat_id]['status'] = 'replied'
            chats[chat_id]['customer_seen_reply'] = False
            save_chats(chats)
            flash('Reply sent', 'success')
        return redirect(url_for('admin_chat', chat_id=chat_id))

    products = load_products()
    product = next((p for p in products if int(p.get('id', 0)) == int(chats[chat_id]['product_id'])), None)
    return render_template('admin_chat.html', chat=chats[chat_id], product=product, chat_id=chat_id)

@app.route('/admin/delete_product/<int:product_id>')
def delete_product(product_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    products = load_products()
    products = [p for p in products if int(p.get('id', 0)) != product_id]
    save_products(products)
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/logout')
def logout():
    session.pop('admin_logged_in', None)
    session.pop('admin_name', None)
    return redirect(url_for('index'))

@app.errorhandler(413)
def too_large(e):
    return 'File too large. Maximum size is 10 MB.', 413

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)