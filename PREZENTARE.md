# UniVoice — Checklist prezentare (Docker Swarm)

> Repo: `UniVoice/`  
> Stack name folosit mai jos: `univoice_stack`

## 0) Pornire rapidă (primele comenzi din prezentare)

### A. (Recomandat) WSL helper (dacă ești în WSL)
```bash
cd /home/darius/fac/UniVoice
./deploy_wsl.sh
```
- La final îți printează URL-ul aplicației.

### B. Pornire manuală (Linux/WSL, fără helper)
```bash
cd /home/darius/fac/UniVoice

# 1) Swarm init (doar dacă nu e deja activ)
docker info -f '{{.Swarm.LocalNodeState}}'
# dacă e "inactive":
docker swarm init

# 2) Build imagini (Swarm nu build-uiește la deploy)
docker build -t univoice-poll-manager:latest poll_manager
docker build -t univoice-poll-promoter:latest poll_promoter
docker build -t univoice-profile-service:latest profile_service
docker build -t univoice-db-backup:latest db_backup

# 3) Deploy stack
WSL_HOST_IP=$(hostname -I | awk '{print $1}') \
  docker stack deploy -c stack.yml univoice_stack

# 4) Configurează Keycloak (realm/client/users/roles)
KEYCLOAK_REDIRECT_URIS="http://${WSL_HOST_IP}:5000/*,http://127.0.0.1:5000/*,http://localhost:5000/*,http://wsl.localhost:5000/*" \
  /home/darius/fac/UniVoice/.venv/bin/python setup_keycloak.py

echo "App: http://${WSL_HOST_IP}:5000"
echo "Keycloak: http://${WSL_HOST_IP}:8080"
```

## 0.1) Verificare că e totul sus
```bash
docker stack services univoice_stack
```

---

## Replicare (comenzi pentru a arăta numărul de replici)

```bash
# tabel cu REPLICAS pe fiecare serviciu
docker stack services univoice_stack

# arată task-urile (replicile) pentru poll_manager
# (Swarm păstrează istoric; folosim filter ca să arătăm doar replicile active)
docker service ps --filter desired-state=running univoice_stack_poll_manager

# arată replica count configurat în spec
docker service inspect univoice_stack_poll_manager -f '{{.Spec.Mode.Replicated.Replicas}}'

# (opțional, dacă întreabă de "Failed" în istoric)
docker service logs --since 10m univoice_stack_poll_manager
```

---

# Cerințe 1–10 (ce arăți + ce comenzi rulezi)

## 1) Autentificare și autorizare (SSO)
**Ce demonstrezi:** login prin Keycloak (OIDC) + protecție rute.

Comenzi / pași:
- Deschizi Keycloak: `http://<IP>:8080`
- Deschizi aplicația: `http://<IP>:5000`
- Apeși **Login SSO** și arăți redirect-ul către Keycloak + back to app.

(Extra, din CLI)
```bash
docker service logs -f univoice_stack_poll_manager
```

## 2) Management roluri + profiluri auto
**Ce demonstrezi:** roluri în token și comportament diferit în app.

Comenzi:
```bash
# arată că scriptul creează roluri + useri demo în Keycloak
/home/darius/fac/UniVoice/.venv/bin/python setup_keycloak.py
```
Pași în UI:
- Te loghezi ca `student1` (parola: `student`) și arăți că vede doar poll-uri pentru studenți.
- Te loghezi ca `profesor1` (parola: `profesor`) și arăți că vede poll-uri pentru profesori.

Notă (pentru transparență): profile-ul afișat în aplicație este calculat din DB (statistici); dacă vrei profil persistent (tabel `users` creat automat la login), se poate adăuga ulterior.

## 3) Baza de date + ORM
**Ce demonstrezi:** persistență în Postgres + SQLAlchemy în app.

Comenzi:
```bash
# arată serviciul DB
docker service ps univoice_stack_db

# intri în postgres și verifici tabele/date demo
DB_CONT=$(docker ps --filter name=univoice_stack_db -q | head -n 1)
docker exec -it "$DB_CONT" psql -U admin -d univoice_db -c "\\dt"
docker exec -it "$DB_CONT" psql -U admin -d univoice_db -c "select id,title,target_audience from polls order by id desc limit 5;"
```

## 4) Livrare out-of-the-box
**Ce demonstrezi:** 1 comandă deploy => servicii funcționale.

Comenzi:
```bash
# deploy + status
docker stack deploy -c stack.yml univoice_stack
docker stack services univoice_stack
```

## 5) Microservicii + Dockerfile pentru fiecare componentă proprie
**Ce demonstrezi:** există cod + Dockerfile pentru serviciile tale.

Comenzi:
```bash
ls -la poll_manager/Dockerfile poll_promoter/Dockerfile profile_service/Dockerfile db_backup/Dockerfile
```

## 6) Structura proiectului (minim 5 componente, minim 2 proprii)
**Ce demonstrezi:** lista serviciilor din stack.

Comenzi:
```bash
docker stack services univoice_stack
```
Explici rapid:
- Open-source: `db` (Postgres), `keycloak`, `pgadmin`
- Proprii: `poll_manager`, `poll_promoter`, `profile_service`, `db_backup`

## 7) Stack Docker Swarm (servicii separate în .yml)
**Ce demonstrezi:** deploy din `stack.yml`.

Comenzi:
```bash
cat stack.yml | sed -n '1,200p'
docker stack deploy -c stack.yml univoice_stack
```

## 8) Interconectare prin DNS Docker + env vars (fără hardcodări)
**Ce demonstrezi:** nume de servicii ca DNS (`db`, `keycloak`, `poll_promoter`, `profile_service`) + configurare prin env.

Comenzi:
```bash
# vezi env vars pe poll_manager (DNS + URL-uri)
PM_TASK=$(docker ps --filter name=univoice_stack_poll_manager -q | head -n 1)
docker exec -it "$PM_TASK" sh -lc 'env | grep -E "DATABASE_URL|POLL_PROMOTER_URL|PROFILE_SERVICE_URL|KEYCLOAK_"'

# verifică rezolvarea DNS în rețeaua Swarm
docker exec -it "$PM_TASK" sh -lc 'getent hosts db; getent hosts poll_promoter; getent hosts profile_service; getent hosts keycloak'

# ping/curl între servicii prin DNS
docker exec -it "$PM_TASK" sh -lc 'wget -qO- http://profile_service:5002/health; echo; wget -qO- http://poll_promoter:5001/health; echo'
```

## 9) Rețele și securitate (servicii doar pe rețelele necesare)
**Ce demonstrezi:** ai rețele separate (ex: `db-net`, `idp-net`, `app-net`) și servicii atașate minimal.

Comenzi:
```bash
# listează rețelele stack-ului
docker network ls | grep univoice_stack

# inspect pe un serviciu: la ce networks e atașat
docker service inspect univoice_stack_db -f '{{json .Spec.TaskTemplate.Networks}}'
docker service inspect univoice_stack_keycloak -f '{{json .Spec.TaskTemplate.Networks}}'
docker service inspect univoice_stack_poll_manager -f '{{json .Spec.TaskTemplate.Networks}}'
```

## 10) Replicare + testare (unit tests)
**Ce demonstrezi:** replicare + “advanced function” testată prin unit tests.

Comenzi:
```bash
# replicare deja arătată mai sus (poll_manager)
docker service ps univoice_stack_poll_manager

# rulezi testele
cd /home/darius/fac/UniVoice
/home/darius/fac/UniVoice/.venv/bin/python -m pytest -q

# (opțional, pentru a arăta verificarea pe sistemele avansate)
/home/darius/fac/UniVoice/.venv/bin/python -m pytest -q poll_manager/tests/test_advanced_systems.py
```

---

## 11) Sisteme avansate (distribuite): Rate limiting + caching (Redis)
**Ce demonstrezi:** limitare de trafic și cache partajat între replici (funcționează și când ai 2+ replici).

### A. Verifici că Redis e sus
```bash
docker stack services univoice_stack | grep redis
REDIS_CONT=$(docker ps --filter name=univoice_stack_redis -q | head -n 1)
docker exec -it "$REDIS_CONT" redis-cli ping
```

### B. Rate limiting distribuit (poll_manager)
```bash
IP=$(hostname -I | awk '{print $1}')

# trimite multe request-uri rapid pe /login; după prag, primești 429 Too Many Requests
for i in $(seq 1 40); do curl -s -o /dev/null -w "%{http_code}\n" "http://${IP}:5000/login"; done

# (opțional) vezi cheile de rate-limit în Redis
docker exec -it "$REDIS_CONT" redis-cli --scan --pattern 'rl:*' | head
```

### C. Caching distribuit (profile_service + poll_manager)
```bash
IP=$(hostname -I | awk '{print $1}')

# 1) cache pe profile_service (endpoint fără auth)
curl -s "http://${IP}:5002/profile/student1" | head

# 2) vezi cheia în Redis (TTL scade)
docker exec -it "$REDIS_CONT" redis-cli ttl 'profile_stats:student1'

# 3) poți arăta și chei de poll results (după ce accesezi pagina principală)
docker exec -it "$REDIS_CONT" redis-cli --scan --pattern 'poll_results:*' | head
```

---

## (Opțional) Clean-up după prezentare
```bash
docker stack rm univoice_stack
```
