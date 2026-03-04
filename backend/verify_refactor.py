import sys
import os

# Add backend to path
sys.path.append('/var/smsc/backend')

print("Testing imports...")

try:
    from app.modules.common.account import Account as NewAccount
    print("✅ Successfully imported NewAccount from app.modules.common.account")
except ImportError as e:
    print(f"❌ Failed to import NewAccount: {e}")
    sys.exit(1)

try:
    from app.models.account import Account as OldAccount
    print("✅ Successfully imported OldAccount from app.models.account (Proxy)")
except ImportError as e:
    print(f"❌ Failed to import OldAccount: {e}")
    sys.exit(1)

try:
    from app.modules.sms.sms_log import SMSLog as NewSMSLog
    print("✅ Successfully imported NewSMSLog from app.modules.sms.sms_log")
except ImportError as e:
    print(f"❌ Failed to import NewSMSLog: {e}")
    sys.exit(1)

print("All import tests passed!")
