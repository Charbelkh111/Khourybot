import streamlit as st
# Modified import for declarative_base
from sqlalchemy.orm import sessionmaker, declarative_base 
import sqlalchemy as sa
from datetime import datetime
import json
import uuid
import os
import time
import streamlit.components.v1 as components

# --- Database Setup ---
DATABASE_URL = "postgresql://khourybotes_db_user:HeAQEQ68txKKjTVQkDva3yaMx3npqTuw@dpg-d2uvmvogjchc73ao6060-a/khourybotes_db"
engine = sa.create_engine(DATABASE_URL)

# --- Correct import for declarative_base ---
Base = declarative_base() 

Session = sessionmaker(bind=engine)

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False)

class BotSession(Base):
    __tablename__ = 'bot_sessions'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    session_id = Column(String, unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    api_token = Column(String, nullable=True)
    base_amount = Column(Float, default=0.5)
    tp_target = Column(Float, nullable=True)
    max_consecutive_losses = Column(Integer, default=5)
    current_amount = Column(Float, default=0.5)
    consecutive_losses = Column(Integer, default=0)
    total_wins = Column(Integer, default=0)
    total_losses = Column(Integer, default=0)
    is_running = Column(Boolean, default=False)
    is_trade_open = Column(Boolean, default=False)
    initial_balance = Column(Float, nullable=True)
    logs = Column(String, default="[]")

# --- IMPORTANT: Create tables if they don't exist ---
# This ensures the tables are created when the app starts, especially if the DB was empty.
Base.metadata.create_all(engine) 

# --- File-Based Authentication ---
ALLOWED_EMAILS_FILE = 'user_ids.txt'

def is_email_allowed(email):
    try:
        if os.path.exists(ALLOWED_EMAILS_FILE):
            with open(ALLOWED_EMAILS_FILE, 'r') as f:
                allowed_emails = {line.strip() for line in f}
                return email in allowed_emails
        return False
    except Exception:
        return False

# --- Database Session Management ---
def get_or_create_user(email):
    s = Session()
    try:
        user = s.query(User).filter_by(email=email).first()
        if not user:
            user = User(email=email)
            s.add(user)
            s.commit()
        return user
    finally:
        s.close()

def get_or_create_bot_session(user):
    s = Session()
    try:
        bot_session = s.query(BotSession).filter_by(user_id=user.id).first()
        if not bot_session:
            bot_session = BotSession(user_id=user.id)
            s.add(bot_session)
            s.commit()
        return bot_session
    finally:
        s.close()

def load_bot_state(session_id):
    s = Session()
    try:
        bot_session = s.query(BotSession).filter_by(session_id=session_id).first()
        if bot_session:
            return {
                'api_token': bot_session.api_token,
                'base_amount': bot_session.base_amount,
                'tp_target': bot_session.tp_target,
                'max_consecutive_losses': bot_session.max_consecutive_losses,
                'current_amount': bot_session.current_amount,
                'consecutive_losses': bot_session.consecutive_losses,
                'total_wins': bot_session.total_wins,
                'total_losses': bot_session.total_losses,
                'is_running': bot_session.is_running,
                'is_trade_open': bot_session.is_trade_open,
                'initial_balance': bot_session.initial_balance,
                'logs': json.loads(bot_session.logs) if bot_session.logs else [],
            }
        return {}
    finally:
        s.close()

def update_bot_settings(session_id, new_settings):
    s = Session()
    try:
        bot_session = s.query(BotSession).filter_by(session_id=session_id).first()
        if bot_session:
            for key, value in new_settings.items():
                if hasattr(bot_session, key):
                    setattr(bot_session, key, value)
            s.commit()
    finally:
        s.close()

# --- Streamlit UI ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user_email' not in st.session_state:
    st.session_state.user_email = None
if 'session_id' not in st.session_state:
    st.session_state.session_id = None
if 'session_data' not in st.session_state:
    st.session_state.session_data = {}

if not st.session_state.logged_in:
    st.title("KHOURYBOT Login 🤖")
    email = st.text_input("Enter your email address:")
    if st.button("Login", type="primary"):
        if is_email_allowed(email):
            user = get_or_create_user(email)
            bot_session = get_or_create_bot_session(user)
            st.session_state.user_email = email
            st.session_state.session_id = bot_session.session_id
            st.session_state.logged_in = True
            st.session_state.session_data = load_bot_state(st.session_state.session_id)
            st.success("Login successful! Redirecting to bot control...")
            st.rerun()
        else:
            st.error("Access denied. Your email is not activated.")
else:
    st.title("KHOURYBOT - Automated Trading 🤖")
    st.write(f"Logged in as: **{st.session_state.user_email}**")
    st.header("1. Bot Control")
    st.session_state.session_data = load_bot_state(st.session_state.session_id)
    current_status = "Running" if st.session_state.session_data.get('is_running') else "Stopped"
    is_session_active = st.session_state.session_data.get('api_token') is not None
    
    if not is_session_active or not current_status == "Running":
        st.warning("Please enter new settings to start a new session.")
        api_token = st.text_input("Enter your Deriv API token:", type="password", value=st.session_state.session_data.get('api_token', ''))
        base_amount = st.number_input("Base Amount ($)", min_value=0.5, step=0.5, value=st.session_state.session_data.get('base_amount', 0.5))
        tp_target = st.number_input("Take Profit Target ($)", min_value=1.0, step=1.0, value=st.session_state.session_data.get('tp_target', 1.0))
        max_losses = st.number_input("Max Consecutive Losses", min_value=1, step=1, value=st.session_state.session_data.get('max_consecutive_losses', 5))
    else:
        api_token = st.session_state.session_data.get('api_token')
        base_amount = st.session_state.session_data.get('base_amount')
        tp_target = st.session_state.session_data.get('tp_target')
        max_losses = st.session_state.session_data.get('max_consecutive_losses')
        st.write(f"**API Token:** {'********'}")
        st.write(f"**Base Amount:** {base_amount}$")
        st.write(f"**TP Target:** {tp_target}$")
        st.write(f"**Max Losses:** {max_losses}")
    
    col1, col2 = st.columns(2)
    with col1:
        start_button = st.button("Start Bot", type="primary", disabled=(current_status == 'Running' or not api_token))
    with col2:
        stop_button = st.button("Stop Bot", disabled=(current_status == 'Stopped'))

    if start_button:
        new_settings = {
            'is_running': True, 'api_token': api_token, 'base_amount': base_amount, 'tp_target': tp_target,
            'max_consecutive_losses': max_losses, 'current_amount': base_amount, 'consecutive_losses': 0,
            'total_wins': 0, 'total_losses': 0, 'initial_balance': None,
            'logs': json.dumps([f"[{datetime.now().strftime('%H:%M:%S')}] 🟢 Bot has been started."])
        }
        update_bot_settings(st.session_state.session_id, new_settings)
        st.success("Bot has been started.")
        st.rerun()

    if stop_button:
        logs = st.session_state.session_data.get('logs', [])
        logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] 🛑 Bot stopped by user.")
        update_bot_settings(st.session_state.session_id, {'is_running': False, 'logs': json.dumps(logs)})
        st.warning("Bot has been stopped.")
        st.rerun()

    st.info(f"Bot Status: **{'Running' if current_status == 'Running' else 'Stopped'}**")
    st.markdown("---")
    st.header("2. Live Bot Logs")
    logs = st.session_state.session_data.get('logs', [])
    with st.container(height=600):
        st.text_area("Logs", "\n".join(logs), height=600, key="logs_textarea")
    time.sleep(5)
    st.rerun()
