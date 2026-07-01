import requests
import json
import base64

# Configuration
KEYCLOAK_URL = "http://keycloak:8080" # Internal docker network URL
REALM_NAME = "UNIVOICE"
CLIENT_ID = "flask-app"
CLIENT_SECRET = "pVfFZtOAahpdOXkPNOiNjbzNP6rJhASI"
USERNAME = "profesor1"
PASSWORD = "profesor"

def decode_jwt(token):
    parts = token.split('.')
    if len(parts) != 3:
        raise Exception("Invalid JWT")
    # Add padding if needed
    padding = '=' * (4 - len(parts[1]) % 4)
    payload = base64.b64decode(parts[1] + padding).decode('utf-8')
    return json.loads(payload)

def main():
    print(f"Getting token for {USERNAME}...")
    url = f"{KEYCLOAK_URL}/realms/{REALM_NAME}/protocol/openid-connect/token"
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "username": USERNAME,
        "password": PASSWORD,
        "grant_type": "password",
        "scope": "openid email profile"
    }
    
    try:
        response = requests.post(url, data=data)
        response.raise_for_status()
        tokens = response.json()
        access_token = tokens['access_token']
        
        print("\n--- Access Token Payload ---")
        payload = decode_jwt(access_token)
        print(json.dumps(payload, indent=2))
        
        print("\n--- Checking Roles ---")
        realm_access = payload.get('realm_access', {})
        roles = realm_access.get('roles', [])
        print(f"Roles found: {roles}")
        
        if 'professor' in roles:
            print("SUCCESS: 'professor' role is present.")
        else:
            print("FAILURE: 'professor' role is MISSING.")
            
    except Exception as e:
        print(f"Error: {e}")
        if 'response' in locals():
            print(response.text)

if __name__ == "__main__":
    main()
