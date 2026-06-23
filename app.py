from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from pymongo import MongoClient
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

MONGO_URI = os.environ.get('MONGO_URI', '')
client = MongoClient(MONGO_URI)
db = client['picass_electronics']
products_col = db['products']
chats_col = db['chats']
admin_col = db['admin']

def load_products():
    products = list(products_col.find({}, {'_id': 0}))
    for p in products:
        try:
            p['id'] = int(p['id'])
        except:
            pass
    return products

def load_chats():
    chats = {}
    for chat in chats_col.find({}, {'_id': 0}):
        chats[chat['chat_id']] = chat
    return chats

def load_admin():
    admin = admin_col.find_one({}, {'_id': 0})
    if not admin:
        admin = {
            "username": "admin",
            "password_hash": generate_password_hash("pathaan2345"),
            "shop_name": "Picass's Electronics",
            "whatsapp": "",
            "phone": "",
            "location": "",
            "opening_hours": "",
            "footer_message": "Quality electronics at affordable prices"
        }
        save_admin(admin)
    return admin

def save_admin(admin):
    admin_col.update_one({}, {'$set': admin}, upsert=True)

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

    admin = load_admin()

    return dict(
        unread_reply_count=unread_reply_count,
        pending_chat_count=pending_chat_count,
        admin_name=session.get('admin_name'),
        shop_name=admin.get('shop_name', "Picass's Electronics"),
        whatsapp=admin.get('whatsapp', ''),
        phone=admin.get('phone', ''),
        location=admin.get('location', ''),
        opening_hours=admin.get('opening_hours', ''),
        footer_message=admin.get('footer_message', '')
    )

@app.route('/')
def index():
    skip_welcome = session.pop('skip_welcome', False)
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
        welcome_message="Welcome to Picass's electronics",
        skip_welcome=skip_welcome
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

        admin['shop_name'] = request.form.get('shop_name', '').strip()
        admin['whatsapp'] = request.form.get('whatsapp', '').strip()
        admin['phone'] = request.form.get('phone', '').strip()
        admin['location'] = request.form.get('location', '').strip()
        admin['opening_hours'] = request.form.get('opening_hours', '').strip()
        admin['footer_message'] = request.form.get('footer_message', '').strip()

        save_admin(admin)
        session['admin_name'] = admin['username']
        flash('Settings updated successfully.', 'success')
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

    products_col.insert_one({**new_product, '_id': str(uuid.uuid4())})
    flash('Product added successfully', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/update_price/<int:product_id>', methods=['POST'])
def update_price(product_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    new_price = request.form.get('new_price', '').strip()
    product = products_col.find_one({'id': product_id}, {'_id': 0})

    if product:
        current_price = str(product.get('price', ''))
        if current_price and current_price != new_price:
            products_col.update_one(
                {'id': product_id},
                {'$set': {'old_price': current_price, 'price': new_price, 'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}}
            )
        elif new_price:
            products_col.update_one({'id': product_id}, {'$set': {'price': new_price}})

    flash('Price updated successfully', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/product/<int:product_id>/chat', methods=['GET', 'POST'])
def private_chat(product_id):
    visitor_id = get_visitor_id()
    chat_id = f"{product_id}_{visitor_id}"

    chat = chats_col.find_one({'chat_id': chat_id}, {'_id': 0})
    if not chat:
        chat = {
            'chat_id': chat_id,
            'product_id': product_id,
            'visitor_id': visitor_id,
            'messages': [],
            'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'status': 'new',
            'customer_seen_reply': False
        }
        chats_col.insert_one({**chat, '_id': str(uuid.uuid4())})

    if request.method == 'POST':
        message = request.form.get('message', '').strip()
        if message:
            new_message = {
                'sender': 'visitor',
                'text': message,
                'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            chats_col.update_one(
                {'chat_id': chat_id},
                {'$push': {'messages': new_message},
                 '$set': {'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                          'status': 'pending',
                          'customer_seen_reply': False}}
            )
            flash('Message sent', 'success')
        return redirect(url_for('private_chat', product_id=product_id))

    product = products_col.find_one({'id': product_id}, {'_id': 0})
    chat = chats_col.find_one({'chat_id': chat_id}, {'_id': 0})

    if chat.get('status') == 'replied' and not chat.get('customer_seen_reply'):
        flash('Your message has been replied to.', 'info')
        chats_col.update_one({'chat_id': chat_id}, {'$set': {'customer_seen_reply': True}})

    return render_template('chat.html', product=product, chat=chat, chat_id=chat_id)

@app.route('/admin/chat/<chat_id>', methods=['GET', 'POST'])
def admin_chat(chat_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    chat = chats_col.find_one({'chat_id': chat_id}, {'_id': 0})
    if not chat:
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        reply = request.form.get('message', '').strip()
        if reply:
            new_message = {
                'sender': 'admin',
                'text': reply,
                'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            chats_col.update_one(
                {'chat_id': chat_id},
                {'$push': {'messages': new_message},
                 '$set': {'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                          'status': 'replied',
                          'customer_seen_reply': False}}
            )
            flash('Reply sent', 'success')
        return redirect(url_for('admin_chat', chat_id=chat_id))

    product = products_col.find_one({'id': int(chat.get('product_id', 0))}, {'_id': 0})
    return render_template('admin_chat.html', chat=chat, product=product, chat_id=chat_id)

@app.route('/chat/<chat_id>/clear', methods=['POST'])
def clear_chat(chat_id):
    chat = chats_col.find_one({'chat_id': chat_id}, {'_id': 0})
    if not chat:
        return redirect(url_for('index'))

    visitor_id = session.get('visitor_id')
    is_admin = session.get('admin_logged_in')
    is_owner = visitor_id and chat.get('visitor_id') == visitor_id

    if not is_admin and not is_owner:
        return redirect(url_for('index'))

    chats_col.delete_one({'chat_id': chat_id})

    if is_admin:
        return redirect(url_for('admin_dashboard'))
    return redirect(url_for('index'))

@app.route('/admin/delete_product/<int:product_id>')
def delete_product(product_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    products_col.delete_one({'id': product_id})
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/logout')
def logout():
    session.pop('admin_logged_in', None)
    session.pop('admin_name', None)
    session['skip_welcome'] = True
    return redirect(url_for('index'))

@app.errorhandler(413)
def too_large(e):
    return 'File too large. Maximum size is 10 MB.', 413

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
