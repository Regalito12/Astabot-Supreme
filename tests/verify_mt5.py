
import sys
import os
import MetaTrader5 as mt5
import logging

# Ensure we can import from current directory
sys.path.append(os.getcwd())

# Import config (will load env vars if set, or defaults)
# Mock Telegram env vars to avoid RuntimeError in config.py if they are not set
if not os.getenv("TELEGRAM_TOKEN"):
    os.environ["TELEGRAM_TOKEN"] = "dummy_token"
if not os.getenv("TELEGRAM_CHAT_ID"):
    os.environ["TELEGRAM_CHAT_ID"] = "123456"

try:
    import config
except ImportError as e:
    print(f"Error importing config: {e}")
    sys.exit(1)

logging.basicConfig(level=logging.INFO)

def verify_mt5_connection():
    login = config.MT5_LOGIN
    password = config.MT5_PASSWORD
    server = config.MT5_SERVER
    
    print("--- Verifying MT5 Connection ---")
    print(f"Login: {login} (Type: {type(login)})")
    # Mask password
    masked_pw = "*" * len(str(password)) if password else "None"
    print(f"Password: {masked_pw}")
    print(f"Server: {server}")
    
    if not login or login == 0:
        print("ERROR: MT5_LOGIN is invalid (0 or None). Please configure it in config.py or environment variables.")
        return False

    if password == "tu_password":
        print("ERROR: MT5_PASSWORD is still the default placeholder 'tu_password'. Please update config.py.")
        return False
        
    if server == "tu_servidor_broker":
        print("ERROR: MT5_SERVER is still the default placeholder 'tu_servidor_broker'. Please update config.py.")
        return False

    # Initialize MT5
    if not mt5.initialize():
        print("initialize() failed, error code =", mt5.last_error())
        return False
    
    # Authorized login
    authorized = mt5.login(login=login, password=password, server=server)
    
    if authorized:
        print(f"Connected to {server} with account {login}")
        # Get account info
        account_info = mt5.account_info()
        if account_info is not None:
            print("Account Info:")
            print(f"  Balance: {account_info.balance}")
            print(f"  Equity: {account_info.equity}")
            print(f"  Leverage: {account_info.leverage}")
            print(f"  Name: {account_info.name}")
        else:
            print("Failed to retrieve account info")
            
        mt5.shutdown()
        return True
    else:
        print("failed to connect at account #{}, error code: {}".format(login, mt5.last_error()))
        mt5.shutdown()
        return False

if __name__ == "__main__":
    success = verify_mt5_connection()
    if success:
        print("VERIFICATION SUCCESSFUL")
        sys.exit(0)
    else:
        print("VERIFICATION FAILED")
        sys.exit(1)
