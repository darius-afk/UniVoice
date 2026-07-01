import logic


# Test: normalize_roles taie spațiile și elimină duplicatele/rolurile goale.
def test_normalize_roles_trims_and_dedupes():
    roles = logic.normalize_roles([" student ", "student", "", "  ", "admin", "admin"])
    assert roles == {"student", "admin"}


# Test: target_audience='all' e vizibil chiar și fără login.
def test_can_view_poll_public_all_even_logged_out():
    assert logic.can_view_poll("all", is_logged_in=False, roles=None) is True


# Test: sondajele pentru studenți cer login + rol 'student'.
def test_can_view_poll_students_requires_login_and_student_role():
    assert logic.can_view_poll("students", is_logged_in=False, roles=["student"]) is False
    assert logic.can_view_poll("students", is_logged_in=True, roles=[]) is False
    assert logic.can_view_poll("students", is_logged_in=True, roles=["student"]) is True


# Test: sondajele pentru profesori sunt vizibile doar pentru rol 'professor'.
def test_can_view_poll_professors_requires_professor_role():
    assert logic.can_view_poll("professors", is_logged_in=True, roles=["student"]) is False
    assert logic.can_view_poll("professors", is_logged_in=True, roles=["professor"]) is True


# Test: admin vede orice sondaj (indiferent de target_audience).
def test_admin_sees_everything():
    assert logic.can_view_poll("students", is_logged_in=True, roles=["admin"]) is True
    assert logic.can_view_poll("professors", is_logged_in=True, roles=["admin"]) is True


# Test: student (fără profesor/admin) poate crea doar pentru 'students' (nu 'all'/'professors').
def test_enforce_target_audience_students_locked_to_students():
    assert logic.enforce_target_audience_for_creator("all", roles=["student"]) == "students"
    assert logic.enforce_target_audience_for_creator("professors", roles=["student"]) == "students"
    assert logic.enforce_target_audience_for_creator(None, roles=["student"]) == "students"


# Test: profesor poate alege target valid (all/students/professors).
def test_enforce_target_audience_professor_can_choose():
    assert logic.enforce_target_audience_for_creator("professors", roles=["professor"]) == "professors"
    assert logic.enforce_target_audience_for_creator("students", roles=["professor"]) == "students"
    assert logic.enforce_target_audience_for_creator("all", roles=["professor"]) == "all"


# Test: promovarea e permisă doar dacă ești creator + ai >=3 voturi + target_audience='students'.
def test_decide_promote_requires_creator_and_votes_and_students_target():
    d = logic.decide_promote(is_creator=False, total_votes=10, target_audience="students")
    assert d.allowed is False
    assert d.reason == "not_creator"

    d = logic.decide_promote(is_creator=True, total_votes=2, target_audience="students")
    assert d.allowed is False
    assert d.reason == "not_enough_votes"

    d = logic.decide_promote(is_creator=True, total_votes=3, target_audience="all")
    assert d.allowed is False
    assert d.reason == "not_student_target"

    d = logic.decide_promote(is_creator=True, total_votes=3, target_audience="students")
    assert d.allowed is True
    assert d.new_target_audience == "all"


# Test: target_audience necunoscut e ascuns (safe-by-default), dar admin îl poate vedea.
def test_can_view_poll_unknown_target_is_hidden_even_if_logged_in():
    assert logic.can_view_poll("unknown", is_logged_in=True, roles=["student"]) is False
    assert logic.can_view_poll("unknown", is_logged_in=True, roles=["admin"]) is True


# Test: valori invalide pentru target (profesor/admin) => fallback la 'all'.
def test_enforce_target_audience_invalid_values_fallback_to_all_for_professor_admin():
    assert logic.enforce_target_audience_for_creator("", roles=["professor"]) == "all"
    assert logic.enforce_target_audience_for_creator("   ", roles=["admin"]) == "all"
    assert logic.enforce_target_audience_for_creator("weird", roles=["admin"]) == "all"


# Stress test: verifică invarianta de promovare pe multe combinații (determinist).
def test_stress_decide_promote_invariants():
    # Deterministic stress test: decision should be allowed IFF
    # creator=True AND total_votes>=3 AND target_audience=='students'
    for total_votes in range(0, 250):
        for is_creator in (False, True):
            for target in ("students", "all", "professors", "", " students "):
                decision = logic.decide_promote(
                    is_creator=is_creator,
                    total_votes=total_votes,
                    target_audience=target,
                )
                should_allow = is_creator and total_votes >= 3 and target.strip() == "students"
                assert decision.allowed is should_allow
                if decision.allowed:
                    assert decision.new_target_audience == "all"
                else:
                    assert decision.new_target_audience is None


# Stress/fuzz test: combină target/roluri random (seed fix) și verifică invariantele de vizibilitate.
def test_stress_can_view_poll_invariants_fuzz():
    # Fuzz-ish stress test with deterministic pseudo-random inputs.
    import random

    rng = random.Random(1537)
    targets = ["all", "students", "professors", "unknown", "", "   "]
    role_pool = ["student", "professor", "admin", "", "  student  ", "ADMIN", "visitor"]

    for _ in range(10_000):
        target = rng.choice(targets)
        is_logged_in = rng.choice([True, False])
        roles = [rng.choice(role_pool) for __ in range(rng.randint(0, 4))]

        normalized_target = (target or "all").strip()

        result = logic.can_view_poll(target, is_logged_in=is_logged_in, roles=roles)

        # Invariant 1: 'all' is always visible
        if normalized_target == "all":
            assert result is True

        # Invariant 2: if not logged in, only 'all' can be visible
        if not is_logged_in and normalized_target != "all":
            assert result is False

