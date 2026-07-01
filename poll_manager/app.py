import os
import socket
import json
import base64
import time
from urllib.parse import quote
from flask import Flask, render_template, redirect, url_for, session, request
import requests
from flask_sqlalchemy import SQLAlchemy
from authlib.integrations.flask_client import OAuth
from sqlalchemy import text
from config import Config
import logic
import redis_utils

app = Flask(__name__)
app.config.from_object(Config)


def _env_flag(name: str, default: str = "0") -> bool:
    val = os.environ.get(name, default)
    return str(val).strip().lower() in {"1", "true", "yes", "on"}


def _cache_enabled() -> bool:
    return _env_flag("CACHE_ENABLED", "1")


def _rate_limit_enabled() -> bool:
    return _env_flag("RATE_LIMIT_ENABLED", "1")


def _cache_ttl(name: str, default_seconds: int) -> int:
    try:
        return int(os.environ.get(name, str(default_seconds)))
    except Exception:
        return default_seconds


def _redis():
    return redis_utils.get_redis()


def _json_cache_get(redis_client, key: str):
    if not redis_client or not _cache_enabled():
        return None
    try:
        raw = redis_client.get(key)
        return json.loads(raw) if raw else None
    except Exception as e:
        print(f"CACHE get failed for {key}: {e}", flush=True)
        return None


def _json_cache_set(redis_client, key: str, value, *, ttl_seconds: int):
    if not redis_client or not _cache_enabled():
        return
    try:
        redis_client.setex(key, int(ttl_seconds), json.dumps(value))
    except Exception as e:
        print(f"CACHE set failed for {key}: {e}", flush=True)


def _cache_del(redis_client, *keys: str):
    if not redis_client or not _cache_enabled() or not keys:
        return
    try:
        redis_client.delete(*keys)
    except Exception as e:
        print(f"CACHE delete failed: {e}", flush=True)


def _rate_limit_identifier() -> str:
    user = session.get('user')
    if user and user.get('sub'):
        return f"user:{user.get('sub')}"
    # fallback: IP
    ip = request.headers.get('X-Forwarded-For', request.remote_addr or 'unknown')
    ip = ip.split(',')[0].strip() if ip else 'unknown'
    return f"ip:{ip}"


def _rate_limit_or_reject(action: str, *, limit: int, window_seconds: int):
    if not _rate_limit_enabled():
        return None
    redis_client = _redis()
    if not redis_client:
        return None

    ident = _rate_limit_identifier()
    key = f"rl:{action}:{ident}"
    try:
        count, ttl = redis_utils.rate_limit_increment(redis_client, key, window_seconds=window_seconds)
        if count > limit:
            retry_after = ttl if ttl >= 0 else window_seconds
            resp = (f"Rate limit depășit pentru {action}. Încearcă din nou în {retry_after}s.", 429)
            return resp
    except Exception as e:
        print(f"Rate limit error for {action}: {e}", flush=True)
        return None
    return None


@app.before_request
def _apply_rate_limits():
    # Apply rate-limits per endpoint to demonstrate distributed protection across replicas.
    endpoint = (request.endpoint or "").strip()
    method = request.method.upper()

    # Limits are configurable from env.
    limits = {
        # Demo-friendly: can be triggered with curl (no auth needed)
        ("login", "GET"): ("login", int(os.environ.get("RATE_LIMIT_LOGIN", "15")), 60),
        # More sensitive operations
        ("create_poll", "POST"): ("create_poll", int(os.environ.get("RATE_LIMIT_CREATE_POLL", "5")), 60),
        ("vote", "POST"): ("vote", int(os.environ.get("RATE_LIMIT_VOTE", "10")), 60),
        ("promote_poll", "POST"): ("promote_poll", int(os.environ.get("RATE_LIMIT_PROMOTE", "5")), 60),
    }

    rule = limits.get((endpoint, method))
    if not rule:
        return None

    action, limit, window = rule
    rejected = _rate_limit_or_reject(action, limit=limit, window_seconds=window)
    return rejected

# --- Configurare Bază de Date ---
db = SQLAlchemy(app)


def _ensure_db_schema():
    # Swarm doesn't guarantee startup ordering; also older DB volumes may have an older schema.
    # We keep this small + idempotent (CREATE TABLE IF NOT EXISTS / ALTER TABLE ... IF NOT EXISTS).
    last_error = None
    for attempt in range(1, 31):
        try:
            with app.app_context():
                db.session.execute(text('SELECT 1'))

                # Tables might be missing entirely if an older Postgres volume was created
                # before we introduced init.sql (entrypoint init scripts only run on first init).
                db.session.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS polls (
                            id SERIAL PRIMARY KEY,
                            title VARCHAR(255) NOT NULL,
                            question TEXT NOT NULL,
                            created_by VARCHAR(100),
                            is_official BOOLEAN DEFAULT FALSE,
                            allow_multiple BOOLEAN DEFAULT FALSE,
                            target_audience VARCHAR(50) DEFAULT 'all',
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                        """
                    )
                )
                db.session.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS poll_options (
                            id SERIAL PRIMARY KEY,
                            poll_id INT NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
                            text VARCHAR(255) NOT NULL
                        );
                        """
                    )
                )
                db.session.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS votes (
                            id SERIAL PRIMARY KEY,
                            poll_id INT REFERENCES polls(id),
                            user_id VARCHAR(100),
                            poll_option_id INT REFERENCES poll_options(id),
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                        """
                    )
                )

                # If the table existed from an older schema, ensure expected columns exist.
                db.session.execute(text("ALTER TABLE votes ADD COLUMN IF NOT EXISTS poll_id INT"))
                db.session.execute(text("ALTER TABLE votes ADD COLUMN IF NOT EXISTS user_id VARCHAR(100)"))
                db.session.execute(
                    text(
                        "ALTER TABLE votes ADD COLUMN IF NOT EXISTS poll_option_id INT"
                    )
                )
                db.session.execute(
                    text(
                        "ALTER TABLE votes ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
                    )
                )

                db.session.execute(
                    text(
                        "ALTER TABLE polls ADD COLUMN IF NOT EXISTS allow_multiple BOOLEAN DEFAULT FALSE"
                    )
                )
                db.session.execute(
                    text(
                        "ALTER TABLE polls ADD COLUMN IF NOT EXISTS target_audience VARCHAR(50) DEFAULT 'all'"
                    )
                )

                # Backfill other columns we rely on in templates/routes.
                db.session.execute(
                    text(
                        "ALTER TABLE polls ADD COLUMN IF NOT EXISTS is_official BOOLEAN DEFAULT FALSE"
                    )
                )
                db.session.execute(
                    text(
                        "ALTER TABLE polls ADD COLUMN IF NOT EXISTS created_by VARCHAR(100)"
                    )
                )
                db.session.execute(
                    text(
                        "ALTER TABLE polls ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
                    )
                )

                # Seed a test poll if none exists.
                db.session.execute(
                    text(
                        """
                        INSERT INTO polls (title, question, created_by, is_official, allow_multiple, target_audience)
                        SELECT 'Test Poll', 'Functioneaza conexiunea la baza de date?', 'admin', TRUE, FALSE, 'all'
                        WHERE NOT EXISTS (SELECT 1 FROM polls WHERE title = 'Test Poll');
                        """
                    )
                )

                # Ensure options exist for the test poll.
                db.session.execute(
                    text(
                        """
                        INSERT INTO poll_options (poll_id, text)
                        SELECT p.id, 'DA' FROM polls p
                        WHERE p.title = 'Test Poll'
                          AND NOT EXISTS (
                            SELECT 1 FROM poll_options o WHERE o.poll_id = p.id AND o.text = 'DA'
                          );
                        """
                    )
                )
                db.session.execute(
                    text(
                        """
                        INSERT INTO poll_options (poll_id, text)
                        SELECT p.id, 'NU' FROM polls p
                        WHERE p.title = 'Test Poll'
                          AND NOT EXISTS (
                            SELECT 1 FROM poll_options o WHERE o.poll_id = p.id AND o.text = 'NU'
                          );
                        """
                    )
                )

                db.session.commit()
                print('DB schema OK', flush=True)
                return
        except Exception as e:
            last_error = e
            try:
                db.session.rollback()
            except Exception:
                pass
            print(f'DB not ready / schema update failed (attempt {attempt}/30): {e}', flush=True)
            time.sleep(2)

    print(f'WARNING: DB schema check did not succeed: {last_error}', flush=True)


_ensure_db_schema()

# --- Configurare Keycloak (SSO) ---
oauth = OAuth(app)
oauth.register(
    name='keycloak',
    client_id=app.config['KEYCLOAK_CLIENT_ID'],
    client_secret=app.config['KEYCLOAK_CLIENT_SECRET'],
    
    # URL-uri luate din config
    authorize_url=app.config['OAUTH_AUTHORIZE_URL'],
    access_token_url=app.config['OAUTH_ACCESS_TOKEN_URL'],
    api_base_url=app.config['OAUTH_API_BASE_URL'],
    server_metadata_url=app.config['OAUTH_METADATA_URL'],
    
    client_kwargs={
        'scope': 'openid email profile',
        'token_endpoint_auth_method': 'client_secret_post'
    }
)

# Configurare pentru a accepta issuer-ul de la Keycloak
import os
os.environ['AUTHLIB_INSECURE_TRANSPORT'] = '1'  # Permite HTTP în dev

# --- Modele DB ---
class Poll(db.Model):
    __tablename__ = 'polls'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    question = db.Column(db.Text, nullable=False)
    is_official = db.Column(db.Boolean, default=False)
    allow_multiple = db.Column(db.Boolean, default=False)
    target_audience = db.Column(db.String(50), default='all') # 'all', 'students', 'professors'
    created_by = db.Column(db.String(100))
    options = db.relationship('PollOption', backref='poll', lazy=True, cascade="all, delete-orphan")

    def get_results(self):
        results = {}
        total_votes = 0
        for option in self.options:
            count = Vote.query.filter_by(poll_option_id=option.id).count()
            results[option.text] = count
            total_votes += count
        return results, total_votes

class PollOption(db.Model):
    __tablename__ = 'poll_options'
    id = db.Column(db.Integer, primary_key=True)
    poll_id = db.Column(db.Integer, db.ForeignKey('polls.id'), nullable=False)
    text = db.Column(db.String(255), nullable=False)

class Vote(db.Model):
    __tablename__ = 'votes'
    id = db.Column(db.Integer, primary_key=True)
    poll_id = db.Column(db.Integer, db.ForeignKey('polls.id'))
    user_id = db.Column(db.String(100))
    poll_option_id = db.Column(db.Integer, db.ForeignKey('poll_options.id'))
    # Eliminăm constrângerea unică simplă pentru a permite voturi multiple dacă e cazul
    # Validarea se va face în cod

# --- Helper Functions ---
def decode_jwt_payload_manual(token_str):
    try:
        parts = token_str.split('.')
        if len(parts) != 3:
            return {}
        # Add padding if needed
        padding = '=' * (4 - len(parts[1]) % 4)
        payload = base64.urlsafe_b64decode(parts[1] + padding).decode('utf-8')
        return json.loads(payload)
    except Exception as e:
        print(f"Error manual decode: {e}", flush=True)
        return {}

def get_user_roles(token):
    if not token:
        return []
    
    try:
        if 'access_token' in token:
            payload = decode_jwt_payload_manual(token['access_token'])
            realm_access = payload.get('realm_access', {})
            roles = realm_access.get('roles', [])
            print(f"DEBUG: Token Payload Roles: {roles}", flush=True)
            return roles
    except Exception as e:
        print(f"Error extracting roles: {e}", flush=True)
        return []
    return []

# --- Rute ---
@app.route('/')
def index():
    user = session.get('user') # Verificăm dacă e logat
    token = session.get('token')
    roles = get_user_roles(token) if token else []
    
    container_id = socket.gethostname()
    
    try:
        all_polls = Poll.query.all()
    except:
        all_polls = []

    # Filter polls based on visibility and user role
    # If not logged in, maybe show only 'all' or nothing? Let's say nothing or public polls if we had them.
    # Assuming login is not strict for index but voting requires it.
    
    visible_polls = []
    for poll in all_polls:
        if logic.can_view_poll(
            poll.target_audience,
            is_logged_in=bool(user),
            roles=roles,
        ):
            visible_polls.append(poll)

    # Precompute results to avoid complex Jinja/JS mixing in template.
    # Also calculate total votes for the button logic.
    # Cache poll results in Redis to reduce repeated DB queries under load.
    redis_client = _redis()
    poll_results_ttl = _cache_ttl('CACHE_TTL_POLL_RESULTS_SECONDS', 15)

    polls_data_final = []
    for poll in visible_polls:
        cache_key = f"poll_results:{poll.id}"
        cached = _json_cache_get(redis_client, cache_key)
        if cached and isinstance(cached, dict) and 'results' in cached and 'total_votes' in cached:
            res = cached.get('results', {})
            total = int(cached.get('total_votes', 0))
        else:
            res, total = poll.get_results()
            _json_cache_set(
                redis_client,
                cache_key,
                {"results": res, "total_votes": total},
                ttl_seconds=poll_results_ttl,
            )
        polls_data_final.append({
            "id": poll.id,
            "results": res,
            "total_votes": total,
            "can_promote": (user and poll.created_by == user.get('sub') and total >= 3 and poll.target_audience == 'students')
        })
    
    return render_template('index.html', polls=visible_polls, polls_data=polls_data_final, user=user, container_id=container_id)

@app.route('/profile')
def profile():
    user = session.get('user')
    if not user:
        return redirect('/login')
        
    user_id = user.get('sub')

    redis_client = _redis()
    profile_cache_ttl = _cache_ttl('CACHE_TTL_PROFILE_SECONDS', 30)
    profile_cache_key = f"profile_stats:{user_id}"

    cached = _json_cache_get(redis_client, profile_cache_key)
    if cached and isinstance(cached, dict):
        return render_template(
            'profile.html',
            user=user,
            voted_polls_count=cached.get('voted_polls_count', 0),
            created_polls_count=cached.get('created_polls_count', 0),
            created_polls_votes_count=cached.get('created_polls_votes_count', 0),
        )

    profile_service_url = os.environ.get('PROFILE_SERVICE_URL')
    if profile_service_url:
        try:
            resp = requests.get(
                f"{profile_service_url.rstrip('/')}/profile/{user_id}",
                timeout=3,
            )
            if resp.status_code == 200:
                data = resp.json() or {}
                _json_cache_set(redis_client, profile_cache_key, data, ttl_seconds=profile_cache_ttl)
                return render_template(
                    'profile.html',
                    user=user,
                    voted_polls_count=data.get('voted_polls_count', 0),
                    created_polls_count=data.get('created_polls_count', 0),
                    created_polls_votes_count=data.get('created_polls_votes_count', 0),
                )
        except Exception as e:
            print(f"Profile service error, falling back to local queries: {e}", flush=True)
    
    # 1. Statistic: you voted in x pools
    try:
        voted_polls_count = db.session.query(Vote.poll_id).filter_by(user_id=user_id).distinct().count()
    except Exception as e:
        print(f"Error counting voted polls: {e}")
        voted_polls_count = 0

    # 2. Statistic: you created y pools
    try:
        created_polls_count = Poll.query.filter_by(created_by=user_id).count()
    except Exception as e:
        print(f"Error counting created polls: {e}")
        created_polls_count = 0

    # 3. Statistic: your created pools got z votes in total
    try:
        created_polls_votes_count = db.session.query(Vote).join(Poll, Vote.poll_id == Poll.id).filter(Poll.created_by == user_id).count()
    except Exception as e:
        print(f"Error counting votes on created polls: {e}")
        created_polls_votes_count = 0
    
    result = {
        "voted_polls_count": voted_polls_count,
        "created_polls_count": created_polls_count,
        "created_polls_votes_count": created_polls_votes_count,
    }
    _json_cache_set(redis_client, profile_cache_key, result, ttl_seconds=profile_cache_ttl)
    return render_template(
        'profile.html',
        user=user,
        voted_polls_count=voted_polls_count,
        created_polls_count=created_polls_count,
        created_polls_votes_count=created_polls_votes_count,
    )

@app.route('/login')
def login():
    # Trimitem utilizatorul la Keycloak să se logheze
    # redirect_uri trebuie să fie URL-ul public unde se întoarce browser-ul.
    # În WSL/Swarm, utilizatorul poate accesa aplicația via IP (ex: 172.x) sau wsl.localhost,
    # deci derivăm host-ul din request.
    redirect_uri = url_for('auth', _external=True)
    return oauth.keycloak.authorize_redirect(redirect_uri=redirect_uri)
@app.route('/auth')
def auth():
    try:
        # Keycloak ne trimite înapoi aici cu un cod
        # Dezactivăm validarea claims pentru a evita problema cu issuer-ul
        token = oauth.keycloak.authorize_access_token(
            claims_options={
                "iss": {"essential": False}
            }
        )
        
        # Folosim datele din ID Token care sunt deja parsate
        # Authlib pune claims-urile din ID Token în cheia 'userinfo'
        user_info = token.get('userinfo')
        
        if not user_info:
            # Fallback: încercăm să decodăm manual id_token dacă authlib nu a făcut-o
            print("Warning: No userinfo in token, trying manual decode...")
            from authlib.jose import jwt
            claims = jwt.decode(token['id_token'], oauth.keycloak.client_secret)
            pass

        # Salvăm userul în sesiune (cookie)
        session['user'] = user_info
        session['token'] = token
        return redirect('/')
        
    except Exception as e:
        print(f"Error in auth: {e}")
        return f"Authentication error: {e}", 500

@app.route('/logout')
def logout():
    session.pop('user', None)
    token = session.pop('token', None)

    # Pentru a schimba utilizatorul, trebuie să ne delogăm și din Keycloak
    keycloak_logout_url = app.config['OAUTH_LOGOUT_URL']
    # Redirect back to whatever host the user is currently using.
    redirect_uri = quote(request.url_root.rstrip('/'), safe='')
    
    logout_url = f"{keycloak_logout_url}?post_logout_redirect_uri={redirect_uri}"
    
    if token and 'id_token' in token:
        logout_url += f"&id_token_hint={token['id_token']}"
    else:
        client_id = app.config['KEYCLOAK_CLIENT_ID']
        logout_url += f"&client_id={client_id}"
    
    return redirect(logout_url)

@app.route('/create_poll', methods=['GET', 'POST'])
def create_poll():
    user = session.get('user')
    token = session.get('token')
    if not user:
        return redirect('/login')
        
    roles = get_user_roles(token) if token else []
    print(f"DEBUG: User: {user.get('preferred_username', 'unknown')}, Roles: {roles}", flush=True)
    is_professor = 'professor' in roles
    is_admin = 'admin' in roles
    print(f"DEBUG: is_professor={is_professor}, is_admin={is_admin}", flush=True)

    if request.method == 'POST':
        title = request.form.get('title')
        question = request.form.get('question')
        # Multi-answer polls are disabled; keep schema field but force to False.
        allow_multiple = False
        options_text = request.form.get('options') # Textarea cu opțiuni pe linii noi
        target_audience = logic.enforce_target_audience_for_creator(
            request.form.get('target_audience'),
            roles,
        )
        
        if not title or not question or not options_text:
            return "Toate câmpurile sunt obligatorii!", 400
            
        # target_audience is already enforced by logic.enforce_target_audience_for_creator

        # Creăm sondajul
        new_poll = Poll(
            title=title,
            question=question,
            is_official=False, # Doar adminii ar trebui să poată face oficiale, simplificăm momentan
            allow_multiple=allow_multiple,
            target_audience=target_audience,
            created_by=user.get('sub')
        )
        db.session.add(new_poll)
        db.session.commit() # Commit pentru a avea ID-ul sondajului
        
        # Adăugăm opțiunile
        options_list = [opt.strip() for opt in options_text.split('\n') if opt.strip()]
        for opt_text in options_list:
            option = PollOption(poll_id=new_poll.id, text=opt_text)
            db.session.add(option)
            
        db.session.commit()

        # Invalidate creator profile stats cache.
        redis_client = _redis()
        _cache_del(redis_client, f"profile_stats:{user.get('sub')}")
        return redirect('/')
        
    return render_template('create_poll.html', user=user, is_professor=is_professor, is_admin=is_admin)

@app.route('/promote_poll/<int:poll_id>', methods=['POST'])
def promote_poll(poll_id):
    user = session.get('user')
    if not user:
        return redirect('/login')

    poll = Poll.query.get_or_404(poll_id)
    user_id = user.get('sub')
    
    promoter_url = os.environ.get('POLL_PROMOTER_URL')
    if promoter_url:
        try:
            resp = requests.post(
                f"{promoter_url.rstrip('/')}/promote/{poll_id}",
                json={"user_id": user_id},
                timeout=3,
            )
            if resp.status_code == 200:
                # Refresh local object and continue
                db.session.expire(poll)
                return redirect('/')
            # If promoter responds with an expected error, surface a friendly message.
            if resp.status_code == 403:
                return "Nu aveți permisiunea de a modifica acest sondaj!", 403
            if resp.status_code == 400:
                return "Sondajul nu poate fi promovat în starea curentă!", 400
            if resp.status_code == 404:
                return "Sondajul nu există!", 404
        except Exception as e:
            print(f"Promoter service error, falling back to local promote: {e}", flush=True)

    # Fallback: local logic + DB write
    total_votes = Vote.query.filter_by(poll_id=poll.id).count()
    decision = logic.decide_promote(
        is_creator=(poll.created_by == user_id),
        total_votes=total_votes,
        target_audience=poll.target_audience,
    )
    if not decision.allowed:
        if decision.reason == 'not_creator':
            return "Nu aveți permisiunea de a modifica acest sondaj!", 403
        if decision.reason == 'not_enough_votes':
            return "Sondajul are nevoie de cel puțin 3 voturi pentru a fi promovat!", 400
        return "Sondajul nu poate fi promovat în starea curentă!", 400

    poll.target_audience = decision.new_target_audience or poll.target_audience
    db.session.commit()
    
    return redirect('/')

@app.route('/vote/<int:poll_id>', methods=['GET', 'POST'])
def vote(poll_id):
    user = session.get('user')
    if not user:
        return redirect('/login')
    
    poll = Poll.query.get_or_404(poll_id)
    
    if request.method == 'POST':
        user_id = user.get('sub')
        
        # Multi-answer polls are disabled. Accept exactly one option.
        selected_options = request.form.getlist('choice')

        if len(selected_options) != 1:
            return "Acest sondaj permite o singură opțiune!", 400

        # Ștergem voturile anterioare (dacă există) pentru a permite modificarea opțiunii
        Vote.query.filter_by(poll_id=poll_id, user_id=user_id).delete()
             
        # Salvăm noile voturi
        opt_id = selected_options[0]
        new_vote = Vote(poll_id=poll_id, user_id=user_id, poll_option_id=int(opt_id))
        db.session.add(new_vote)
            
        db.session.commit()

        # Invalidate caches affected by voting.
        redis_client = _redis()
        keys = [
            f"poll_results:{poll_id}",
            f"profile_stats:{user_id}",
        ]
        if poll.created_by:
            keys.append(f"profile_stats:{poll.created_by}")
        _cache_del(redis_client, *keys)
        return redirect('/')
        
    return render_template('vote.html', poll=poll, user=user)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)