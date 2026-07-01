import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'o_cheie_secreta_random_pentru_sesiune')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Keycloak Settings
    KEYCLOAK_CLIENT_ID = os.environ.get('KEYCLOAK_CLIENT_ID', 'flask-app')
    KEYCLOAK_CLIENT_SECRET = os.environ.get('KEYCLOAK_CLIENT_SECRET', 'pVfFZtOAahpdOXkPNOiNjbzNP6rJhASI')
    KEYCLOAK_REALM = os.environ.get('KEYCLOAK_REALM', 'UNIVOICE')

    # Internal URLs (Container to Container communication)
    KEYCLOAK_INTERNAL_URL = os.environ.get('KEYCLOAK_INTERNAL_URL', 'http://keycloak:8080')
    
    # External URLs (Browser to Container communication)
    KEYCLOAK_EXTERNAL_URL = os.environ.get('KEYCLOAK_EXTERNAL_URL', 'http://localhost:8080')
    APP_EXTERNAL_URL = os.environ.get('APP_EXTERNAL_URL', 'http://localhost:5000')

    # OAuth Endpoints
    OAUTH_AUTHORIZE_URL = f"{KEYCLOAK_EXTERNAL_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/auth"
    OAUTH_ACCESS_TOKEN_URL = f"{KEYCLOAK_INTERNAL_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token"
    OAUTH_API_BASE_URL = f"{KEYCLOAK_INTERNAL_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/"
    OAUTH_METADATA_URL = f"{KEYCLOAK_INTERNAL_URL}/realms/{KEYCLOAK_REALM}/.well-known/openid-configuration"
    OAUTH_LOGOUT_URL = f"{KEYCLOAK_EXTERNAL_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/logout"
