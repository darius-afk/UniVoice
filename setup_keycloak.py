import os
import json
import socket

import requests


KEYCLOAK_URL = os.environ.get("KEYCLOAK_URL", "http://localhost:8080")
ADMIN_USER = os.environ.get("KEYCLOAK_ADMIN", "admin")
ADMIN_PASS = os.environ.get("KEYCLOAK_ADMIN_PASSWORD", "admin")
REALM_NAME = os.environ.get("KEYCLOAK_REALM", "UNIVOICE")
CLIENT_ID = os.environ.get("KEYCLOAK_CLIENT_ID", "flask-app")
CLIENT_SECRET = os.environ.get(
    "KEYCLOAK_CLIENT_SECRET",
    "pVfFZtOAahpdOXkPNOiNjbzNP6rJhASI",  # Matching poll_manager/config.py default
)


def _guess_wsl_ip() -> str | None:
    try:
        # Works in WSL/Linux; returns space-separated IPs.
        ips = socket.gethostbyname_ex(socket.gethostname())[2]
        # Prefer RFC1918-ish addresses when possible.
        for ip in ips:
            if ip.startswith("172.") or ip.startswith("10.") or ip.startswith("192.168."):
                return ip
        return ips[0] if ips else None
    except Exception:
        return None


def _redirect_uris() -> list[str]:
    env_list = os.environ.get("KEYCLOAK_REDIRECT_URIS")
    if env_list:
        # Comma-separated list
        return [u.strip() for u in env_list.split(",") if u.strip()]

    wsl_ip = _guess_wsl_ip()
    uris = [
        "http://localhost:5000/*",
        "http://127.0.0.1:5000/*",
        "http://wsl.localhost:5000/*",
    ]
    if wsl_ip:
        uris.append(f"http://{wsl_ip}:5000/*")
    return uris

def get_admin_token():
    url = f"{KEYCLOAK_URL}/realms/master/protocol/openid-connect/token"
    data = {
        "client_id": "admin-cli",
        "username": ADMIN_USER,
        "password": ADMIN_PASS,
        "grant_type": "password"
    }
    response = requests.post(url, data=data)
    response.raise_for_status()
    return response.json()["access_token"]

def create_realm(token):
    url = f"{KEYCLOAK_URL}/admin/realms"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    data = {
        "id": REALM_NAME,
        "realm": REALM_NAME,
        "enabled": True
    }
    try:
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 409:
            print(f"Realm {REALM_NAME} already exists.")
        else:
            response.raise_for_status()
            print(f"Realm {REALM_NAME} created.")
    except Exception as e:
        print(f"Error creating realm: {e}")

def create_client(token):
    url = f"{KEYCLOAK_URL}/admin/realms/{REALM_NAME}/clients"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    data = {
        "clientId": CLIENT_ID,
        "enabled": True,
        "clientAuthenticatorType": "client-secret",
        "secret": CLIENT_SECRET,
        "redirectUris": _redirect_uris(),
        "webOrigins": ["+"],
        "standardFlowEnabled": True,
        "directAccessGrantsEnabled": True,
        "publicClient": False,
        "protocol": "openid-connect"
    }
    try:
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 409:
            print(f"Client {CLIENT_ID} already exists. Updating redirect URIs...")
            update_client(token, data)
        else:
            response.raise_for_status()
            print(f"Client {CLIENT_ID} created.")
    except Exception as e:
        print(f"Error creating client: {e}")


def get_client_uuid(token) -> str | None:
    url = f"{KEYCLOAK_URL}/admin/realms/{REALM_NAME}/clients?clientId={CLIENT_ID}"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    if not data:
        return None
    return data[0].get("id")


def update_client(token, client_payload: dict):
    client_uuid = get_client_uuid(token)
    if not client_uuid:
        print(f"Could not find client UUID for {CLIENT_ID}; cannot update.")
        return

    url = f"{KEYCLOAK_URL}/admin/realms/{REALM_NAME}/clients/{client_uuid}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # GET existing client, update minimal fields we care about
    existing = requests.get(url, headers={"Authorization": f"Bearer {token}"})
    existing.raise_for_status()
    client = existing.json()

    client["secret"] = CLIENT_SECRET
    client["redirectUris"] = client_payload.get("redirectUris", _redirect_uris())
    client["webOrigins"] = client_payload.get("webOrigins", ["+"])
    client["standardFlowEnabled"] = True
    client["directAccessGrantsEnabled"] = True
    client["publicClient"] = False
    client["protocol"] = "openid-connect"

    resp = requests.put(url, headers=headers, json=client)
    resp.raise_for_status()
    print(f"Client {CLIENT_ID} updated.")

def create_role(token, role_name):
    url = f"{KEYCLOAK_URL}/admin/realms/{REALM_NAME}/roles"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    data = {
        "name": role_name
    }
    try:
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 409:
            print(f"Role '{role_name}' already exists.")
        else:
            response.raise_for_status()
            print(f"Role '{role_name}' created.")
    except Exception as e:
        print(f"Error creating role {role_name}: {e}")

def get_user_id(token, username):
    url = f"{KEYCLOAK_URL}/admin/realms/{REALM_NAME}/users?username={username}"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    users = response.json()
    if users:
        return users[0]['id']
    return None

def get_role_representation(token, role_name):
    url = f"{KEYCLOAK_URL}/admin/realms/{REALM_NAME}/roles/{role_name}"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    return None

def assign_role(token, username, role_name):
    user_id = get_user_id(token, username)
    if not user_id:
        print(f"User {username} not found, cannot assign role.")
        return

    role_rep = get_role_representation(token, role_name)
    if not role_rep:
        print(f"Role {role_name} not found, cannot assign.")
        return

    url = f"{KEYCLOAK_URL}/admin/realms/{REALM_NAME}/users/{user_id}/role-mappings/realm"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    data = [role_rep]
    
    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        print(f"Role '{role_name}' assigned to '{username}'.")
    except Exception as e:
        print(f"Error assigning role to {username}: {e}")

def create_user(token, username, password, email, first_name, last_name):
    url = f"{KEYCLOAK_URL}/admin/realms/{REALM_NAME}/users"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    data = {
        "username": username,
        "enabled": True,
        "email": email,
        "firstName": first_name,
        "lastName": last_name,
        "credentials": [{
            "type": "password",
            "value": password,
            "temporary": False
        }]
    }
    try:
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 409:
            print(f"User '{username}' already exists.")
        else:
            response.raise_for_status()
            print(f"User '{username}' created.")
    except Exception as e:
        print(f"Error creating user {username}: {e}")

if __name__ == "__main__":
    try:
        token = get_admin_token()
        
        # Ensure Realm and Client exist
        create_realm(token)
        create_client(token)
        
        # Create Roles
        create_role(token, "student")
        create_role(token, "professor")
        create_role(token, "admin")

        # Create Students (student1 to student10)
        for i in range(1, 11):
            username = f"student{i}"
            create_user(token, username, "student", f"student{i}@univoice.com", "Student", str(i))
            assign_role(token, username, "student")

        # Create Professors (profesor1 to profesor5)
        for i in range(1, 6):
            username = f"profesor{i}"
            create_user(token, username, "profesor", f"profesor{i}@univoice.com", "Profesor", str(i))
            assign_role(token, username, "professor")

        # Create Admin Test User
        create_user(token, "test_admin", "admin", "admin@univoice.com", "Test", "Admin")
        assign_role(token, "test_admin", "admin")

        print("Keycloak population complete!")
    except Exception as e:
        print(f"Setup failed: {e}")
