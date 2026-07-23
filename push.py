import secrets

def generate_secret_key(length=32):
    return secrets.token_hex(length)

print("APP_SECRET_KEY =", generate_secret_key(32))
print("SUPER_SECRET_KEY =", generate_secret_key(32))
