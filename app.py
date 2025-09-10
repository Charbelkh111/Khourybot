import streamlit as st
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey
from datetime import datetime
import json
import uuid
import os
import time
import streamlit.components.v1 as components

# --- Database Setup ---
# using the provided database URL directly in the code
DATABASE_URL = "postgresql://bibokh_user:Ric9h1SaTADxdkV0LgNmF8c0RPWhWYzy@dpg-d30mrpogjchc73f1tiag-a.oregon-postgres.render.com/bibokh"
engine = sa.create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
Base = declarative_base()

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

# --- Create tables if they don't exist ---
# This is crucial for the first deployment
Base.metadata.create_all(engine)

# --- File-Based Authentication ---
ALLOWED_EMAILS_FILE = 'user_ids.txt'

def is_email_allowed(email):
    """Checks if an email is present in the user_ids.txt file."""
    try:
        if os.path.exists(ALLOWED_EMAILS_FILE):
            with open(ALLOWED_EMAILS_FILE, 'r') as f:
                allowed_emails = {line.strip() for line in f if line.strip()} # Ensure no empty lines
                return email in allowed_emails
        return False
    except Exception as e:
        print(f"Error reading {ALLOWED_EMAILS_FILE}: {e}")
        return False

# --- Database Session Management ---
def get_or_create_user_and_session(email):
    """
    Checks if email is allowed, then gets or creates user and bot session.
    Ensures user is created in DB only if allowed and returns session data.
    """
    if not is_email_allowed(email):
        return None # Email not authorized

    s = Session()
    try:
        user = s.query(User).filter_by(email=email).first()
        if not user:
            # User is allowed but not in DB yet, create them
            user = User(email=email)
            s.add(user)
            # Commit immediately to get user ID for the session
            s.commit()
            
        # Now that user is guaranteed to exist in DB (either found or just created)
        # Fetch or create the bot session for this user
        bot_session = s.query(BotSession).filter_by(user_id=user.id).first()
        if not bot_session:
            bot_session = BotSession(user_id=user.id)
            s.add(bot_session)
            s.commit()
            
        # Load session data to be returned
        session_data = {
            'session_id': bot_session.session_id,
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
        return session_data

    except Exception as e:
        s.rollback() # Rollback any partial changes
        print(f"Error in get_or_create_user_and_session: {e}")
        return None
    finally:
        s.close()

def load_bot_state(session_id):
    """Loads bot state from the database for a given session ID."""
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
    """Updates bot settings in the database for a given session ID."""
    s = Session()
    try:
        bot_session = s.query(BotSession).filter_by(session_id=session_id).first()
        if bot_session:
            for key, value in new_settings.items():
                if hasattr(bot_session, key):
                    setattr(bot_session, key, value)
            s.commit()
    except Exception as e:
        s.rollback()
        print(f"Error updating bot settings for {session_id}: {e}")
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
        session_info = get_or_create_user_and_session(email)
        if session_info:
            st.session_state.user_email = email
            st.session_state.session_id = session_info['session_id']
            st.session_state.logged_in = True
            st.session_state.session_data = session_info
            st.success("Login successful! Redirecting to bot control...")
            st.rerun()
        else:
            st.error("Access denied. Your email is not activated or an error occurred.")
else:
    st.title("KHOURYBOT - Automated Trading 🤖")
    st.write(f"Logged in as: **{st.session_state.user_email}**")
    st.header("1. Bot Control")

    # Reload state to ensure latest data is shown
    st.session_state.session_data = load_bot_state(st.session_state.session_id)
    current_status = "Running" if st.session_state.session_data.get('is_running') else "Stopped"
    is_session_active = st.session_state.session_data.get('api_token') is not None
    
    # Display settings based on whether bot is running or not
    if not is_session_active or not current_status == "Running":
        st.warning("Please enter your Deriv API token and settings to start a new session.")
        api_token = st.text_input("Enter your Deriv API token:", type="password", value=st.session_state.session_data.get('api_token', ''))
        base_amount = st.number_input("Base Amount ($)", min_value=0.5, step=0.5, value=st.session_state.session_data.get('base_amount', 0.5))
        tp_target = st.number_input("Take Profit Target ($)", min_value=1.0, step=1.0, value=st.session_state.session_data.get('tp_target', 1.0))
        max_losses = st.number_input("Max Consecutive Losses", min_value=1, step=1, value=st.session_state.session_data.get('max_consecutive_losses', 5))
    else:
        api_token = st.session_state.session_data.get('api_token')
        base_amount = st.session_state.session_data.get('base_amount')
        tp_target = st.session_state.session_data.get('tp_target')
        max_losses = st.session_state.session_data.get('max_consecutive_losses')
        st.write(f"**API Token:** {'********'}") # Mask token
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
    
    # Refresh the UI every 5 seconds to get the latest logs
    time.sleep(5)
    st.rerun()
