import os

REPLACEMENTS = {
    # Common
    'from app.models.account': 'from app.modules.common.account',
    'import app.models.account': 'import app.modules.common.account',
    
    'from app.models.admin_user': 'from app.modules.common.admin_user',
    'import app.models.admin_user': 'import app.modules.common.admin_user',
    
    'from app.models.api_key': 'from app.modules.common.api_key',
    'from app.models.balance_log': 'from app.modules.common.balance_log',
    'from app.models.ticket': 'from app.modules.common.ticket',
    'from app.models.telegram_binding': 'from app.modules.common.telegram_binding',
    'from app.models.telegram_user': 'from app.modules.common.telegram_user',
    'from app.models.system_config': 'from app.modules.common.system_config',
    'from app.models.notification': 'from app.modules.common.notification',
    'from app.models.security_log': 'from app.modules.common.security_log',
    
    # SMS
    'from app.models.sms_log': 'from app.modules.sms.sms_log',
    'from app.models.sms_batch': 'from app.modules.sms.sms_batch',
    'from app.models.sms_template': 'from app.modules.sms.sms_template',
    'from app.models.channel': 'from app.modules.sms.channel',
    'from app.models.routing_rule': 'from app.modules.sms.routing_rule',
    'from app.models.supplier': 'from app.modules.sms.supplier',
    'from app.models.country_pricing': 'from app.modules.sms.country_pricing',
    
    # Data
    'from app.models.data_pool': 'from app.modules.data.models',
}

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    new_content = content
    for old, new in REPLACEMENTS.items():
        new_content = new_content.replace(old, new)
        
    if new_content != content:
        print(f"Updating {filepath}")
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)

def main():
    base_dir = '/var/smsc/backend/app'
    for root, dirs, files in os.walk(base_dir):
        for file in files:
            if file.endswith('.py'):
                process_file(os.path.join(root, file))

    # Also process telegram_bot
    bot_dir = '/var/smsc/telegram_bot'
    for root, dirs, files in os.walk(bot_dir):
        for file in files:
            if file.endswith('.py'):
                process_file(os.path.join(root, file))

    # Also process tests
    tests_dir = '/var/smsc/backend/tests'
    for root, dirs, files in os.walk(tests_dir):
        for file in files:
            if file.endswith('.py'):
                process_file(os.path.join(root, file))

if __name__ == '__main__':
    main()
