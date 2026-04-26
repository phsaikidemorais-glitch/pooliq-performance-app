from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_mysqldb import MySQL
from MySQLdb import OperationalError
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

from config import Config
from analysis import (
    get_week_status,
    get_adherence,
    get_main_insight,
    calculate_readiness_score,
    get_day_mode,
    calc_session_volume,
    calc_avg_pace_per_100,
    calc_avg_rpe_from_sets,
    calc_session_load,
    detect_pace_drop,
    generate_session_summary,
    calc_pace_per_100,
    get_primary_stroke,
    calculate_shoulder_risk,
    generate_daily_focus,
    suggest_target_pace,
    generate_main_set,
    classify_session_dna,
    format_cycle_model_label,
    format_phase_focus_label,
    format_load_profile_label,
    generate_cycle_support,
)

app = Flask(__name__)
app.config.from_object(Config)

mysql = MySQL(app)


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


def get_readiness_tone(score):
    if score is None:
        return "info"
    if score >= 80:
        return "good"
    if score >= 60:
        return "info"
    if score >= 40:
        return "warn"
    return "danger"


def get_pace_tone(feedback):
    text = (feedback or "").lower()
    if "queda clara" in text:
        return "danger"
    if "leve queda" in text:
        return "warn"
    if "boa consistência" in text:
        return "good"
    return "info"


def get_week_tone(weekly_sessions, weekly_goal):
    if weekly_sessions >= weekly_goal:
        return "good"
    if weekly_sessions == 0:
        return "warn"
    return "info"


def get_load_tone(load_profile):
    load = (load_profile or "").lower()
    if load == "intensidade_alta":
        return "warn"
    if load == "volume_alto":
        return "info"
    if load in ["volume_baixo", "intensidade_baixa"]:
        return "good"
    return "info"


@app.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        email = request.form["email"].strip()
        password = request.form["password"].strip()

        if not username or not email or not password:
            flash("Preencha todos os campos.", "error")
            return redirect(url_for("register"))

        password_hash = generate_password_hash(password)

        try:
            cur = mysql.connection.cursor()
            cur.execute("SELECT id FROM users WHERE email = %s OR username = %s", (email, username))
            existing_user = cur.fetchone()

            if existing_user:
                cur.close()
                flash("Usuário ou email já cadastrado.", "error")
                return redirect(url_for("register"))

            cur.execute(
                "INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s)",
                (username, email, password_hash)
            )
            mysql.connection.commit()
            cur.close()

            flash("Cadastro realizado com sucesso. Faça login.", "success")
            return redirect(url_for("login"))

        except Exception as e:
            flash(f"Erro ao cadastrar: {e}", "error")
            return redirect(url_for("register"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip()
        password = request.form["password"].strip()

        try:
            cur = mysql.connection.cursor()
            cur.execute("SELECT * FROM users WHERE email = %s", (email,))
            user = cur.fetchone()
            cur.close()

            if user and check_password_hash(user["password_hash"], password):
                session["user_id"] = user["id"]
                session["username"] = user["username"]
                flash("Login realizado com sucesso.", "success")
                return redirect(url_for("dashboard"))
            else:
                flash("Email ou senha inválidos.", "error")
                return redirect(url_for("login"))

        except Exception as e:
            flash(f"Erro no login: {e}", "error")
            return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Você saiu da conta.", "success")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    total_sessions = 0
    total_sets = 0
    weekly_goal = 3
    weekly_sessions = 0
    db_error = None

    readiness_score = None
    day_mode = "Sem leitura ainda"
    pain_area = None

    latest_session = None
    latest_sets = []
    recent_sessions = []
    recent_sets = []

    last_session_volume = 0
    last_session_avg_pace = 0.0
    last_session_avg_rpe = 0.0
    last_session_load = 0.0
    last_session_pace_feedback = "Ainda não há leitura da última sessão."
    last_session_summary = "Registre séries para gerar a leitura automática."
    last_session_has_sets = False

    coach_focus = {
        "label": "Construção de base",
        "reason": "Registre mais contexto para liberar sugestões melhores."
    }
    shoulder_risk = {
        "label": "baixo",
        "tone": "good",
        "score": 0,
        "message": "Sem sinais fortes de sobrecarga de ombro no histórico recente."
    }
    pace_target = None
    main_set = {
        "title": "Sem bloco sugerido",
        "detail": "Registre uma sessão e séries para liberar sugestão automática.",
        "note": "O Coach Brain usa seu histórico recente para calibrar a proposta."
    }
    session_dna = {
        "label": "Sem DNA definido",
        "description": "Ainda não há séries suficientes para classificar a sessão."
    }

    cycle_model_label = "Não definido"
    phase_name_display = "Sem fase definida"
    phase_focus_label = "Não definido"
    load_profile_label = "Não definido"
    target_event_display = "Sem alvo definido"
    weeks_to_race_display = "Sem janela definida"
    cycle_support = {
        "main_focus": "Ainda não há contexto de ciclo definido.",
        "load_guidance": "Defina o modelo, a fase e o foco para o sistema contextualizar melhor a leitura.",
        "risk_point": "Sem leitura específica de fase ainda.",
        "coach_note": "A proposta do PoolIQ é respeitar o modelo do atleta e do treinador."
    }

    try:
        cur = mysql.connection.cursor()

        cur.execute(
            "SELECT COUNT(*) AS total_sessions FROM swim_sessions WHERE user_id = %s",
            (session["user_id"],)
        )
        sessions_result = cur.fetchone()
        total_sessions = sessions_result["total_sessions"] if sessions_result else 0

        cur.execute("""
            SELECT COUNT(*) AS total_sets
            FROM swim_sets ss
            JOIN swim_sessions s ON ss.session_id = s.id
            WHERE s.user_id = %s
        """, (session["user_id"],))
        sets_result = cur.fetchone()
        total_sets = sets_result["total_sets"] if sets_result else 0

        cur.execute("""
            SELECT COUNT(*) AS weekly_sessions
            FROM swim_sessions
            WHERE user_id = %s
              AND YEARWEEK(session_date, 1) = YEARWEEK(CURDATE(), 1)
        """, (session["user_id"],))
        weekly_result = cur.fetchone()
        weekly_sessions = weekly_result["weekly_sessions"] if weekly_result else 0

        cur.execute("""
            SELECT id, session_date, goal, cycle_model, phase_name, phase_focus, load_profile,
                   target_event, weeks_to_race, energy_level, pain_area, notes,
                   sleep_hours, motivation_level, stiffness_level, shoulder_pain_level
            FROM swim_sessions
            WHERE user_id = %s
            ORDER BY session_date DESC, id DESC
            LIMIT 1
        """, (session["user_id"],))
        latest_session = cur.fetchone()

        cur.execute("""
            SELECT id, session_date, goal, cycle_model, phase_name, phase_focus, load_profile,
                   target_event, weeks_to_race, energy_level, pain_area, shoulder_pain_level
            FROM swim_sessions
            WHERE user_id = %s
            ORDER BY session_date DESC, id DESC
            LIMIT 5
        """, (session["user_id"],))
        recent_sessions = cur.fetchall()

        cur.execute("""
            SELECT ss.stroke, ss.course_type, ss.distance_m, ss.reps, ss.avg_time_seconds, ss.effort_rpe
            FROM swim_sets ss
            JOIN swim_sessions s ON s.id = ss.session_id
            WHERE s.user_id = %s
            ORDER BY s.session_date DESC, ss.id DESC
            LIMIT 24
        """, (session["user_id"],))
        recent_sets = cur.fetchall()

        if latest_session:
            pain_area = latest_session["pain_area"]
            readiness_score = calculate_readiness_score(
                latest_session["energy_level"],
                latest_session["sleep_hours"],
                latest_session["shoulder_pain_level"],
                latest_session["stiffness_level"]
            )
            day_mode = get_day_mode(readiness_score)

            cycle_model_label = format_cycle_model_label(latest_session.get("cycle_model"))
            phase_name_display = latest_session.get("phase_name") or "Sem fase definida"
            phase_focus_label = format_phase_focus_label(latest_session.get("phase_focus"))
            load_profile_label = format_load_profile_label(latest_session.get("load_profile"))
            target_event_display = latest_session.get("target_event") or "Sem alvo definido"
            weeks_to_race_display = (
                f"{latest_session['weeks_to_race']} semana(s)"
                if latest_session.get("weeks_to_race") is not None
                else "Sem janela definida"
            )

            cur.execute("""
                SELECT id, stroke, course_type, distance_m, reps, avg_time_seconds, rest_seconds, effort_rpe, notes
                FROM swim_sets
                WHERE session_id = %s
                ORDER BY id ASC
            """, (latest_session["id"],))
            latest_sets = cur.fetchall()

            if latest_sets:
                last_session_has_sets = True
                last_session_volume = calc_session_volume(latest_sets)
                last_session_avg_pace = calc_avg_pace_per_100(latest_sets)
                last_session_avg_rpe = calc_avg_rpe_from_sets(latest_sets)
                last_session_load = calc_session_load(latest_sets)
                last_session_pace_feedback = detect_pace_drop(latest_sets)
                last_session_summary = generate_session_summary(latest_sets)
                session_dna = classify_session_dna(latest_sets, latest_session["goal"])

            shoulder_risk = calculate_shoulder_risk(recent_sessions, recent_sets)
            coach_focus = generate_daily_focus(
                readiness_score,
                shoulder_risk["label"],
                latest_session["goal"],
                latest_session.get("phase_focus"),
                latest_session.get("load_profile")
            )

            cycle_support = generate_cycle_support(
                latest_session.get("cycle_model"),
                latest_session.get("phase_name"),
                latest_session.get("phase_focus"),
                latest_session.get("load_profile"),
                latest_session.get("weeks_to_race"),
                readiness_score,
                shoulder_risk["label"]
            )

            stroke_source = latest_sets if latest_sets else recent_sets
            primary_stroke = get_primary_stroke(stroke_source)

            latest_course_type = "50m"
            for item in stroke_source:
                if item.get("course_type"):
                    latest_course_type = item.get("course_type")
                    break

            pace_target = suggest_target_pace(
                stroke_source,
                coach_focus["label"],
                primary_stroke
            )

            main_set = generate_main_set(
                coach_focus["label"],
                latest_course_type,
                primary_stroke,
                pace_target["target_label"] if pace_target else None,
                readiness_score,
                shoulder_risk["label"]
            )

        cur.close()

    except OperationalError as e:
        db_error = str(e)
    except Exception as e:
        db_error = f"Erro inesperado: {e}"

    week_status = get_week_status(weekly_sessions, weekly_goal)
    adherence = get_adherence(weekly_sessions, weekly_goal)

    if last_session_has_sets:
        main_insight = last_session_summary
    else:
        main_insight = get_main_insight(total_sessions, readiness_score, pain_area)

    readiness_tone = get_readiness_tone(readiness_score)
    pace_tone = get_pace_tone(last_session_pace_feedback)
    week_tone = get_week_tone(weekly_sessions, weekly_goal)
    load_tone = get_load_tone(latest_session.get("load_profile") if latest_session else None)

    return render_template(
        "dashboard.html",
        username=session.get("username"),
        total_sessions=total_sessions,
        total_sets=total_sets,
        weekly_goal=weekly_goal,
        weekly_sessions=weekly_sessions,
        week_status=week_status,
        adherence=adherence,
        main_insight=main_insight,
        readiness_score=readiness_score,
        day_mode=day_mode,
        db_error=db_error,
        latest_session=latest_session,
        last_session_volume=last_session_volume,
        last_session_avg_pace=last_session_avg_pace,
        last_session_avg_rpe=last_session_avg_rpe,
        last_session_load=last_session_load,
        last_session_pace_feedback=last_session_pace_feedback,
        last_session_summary=last_session_summary,
        last_session_has_sets=last_session_has_sets,
        readiness_tone=readiness_tone,
        pace_tone=pace_tone,
        week_tone=week_tone,
        load_tone=load_tone,
        coach_focus=coach_focus,
        shoulder_risk=shoulder_risk,
        pace_target=pace_target,
        main_set=main_set,
        session_dna=session_dna,
        cycle_model_label=cycle_model_label,
        phase_name_display=phase_name_display,
        phase_focus_label=phase_focus_label,
        load_profile_label=load_profile_label,
        target_event_display=target_event_display,
        weeks_to_race_display=weeks_to_race_display,
        cycle_support=cycle_support
    )


@app.route("/new-session", methods=["GET", "POST"])
@login_required
def new_session():
    if request.method == "POST":
        session_date = request.form.get("session_date", "").strip()
        goal = request.form.get("goal", "").strip()
        cycle_model = request.form.get("cycle_model", "").strip()
        phase_name = request.form.get("phase_name", "").strip()
        phase_focus = request.form.get("phase_focus", "").strip()
        load_profile = request.form.get("load_profile", "").strip()
        target_event = request.form.get("target_event", "").strip()

        weeks_to_race = request.form.get("weeks_to_race", "").strip()

        energy_level = request.form.get("energy_level", "").strip()
        pain_area = request.form.get("pain_area", "").strip()
        notes = request.form.get("notes", "").strip()

        sleep_hours = request.form.get("sleep_hours", "").strip()
        motivation_level = request.form.get("motivation_level", "").strip()
        stiffness_level = request.form.get("stiffness_level", "").strip()
        shoulder_pain_level = request.form.get("shoulder_pain_level", "").strip()

        if not session_date:
            flash("A data da sessão é obrigatória.", "error")
            return redirect(url_for("new_session"))

        sleep_hours = float(sleep_hours) if sleep_hours else None
        stiffness_level = int(stiffness_level) if stiffness_level else None
        shoulder_pain_level = int(shoulder_pain_level) if shoulder_pain_level else None
        weeks_to_race = int(weeks_to_race) if weeks_to_race else None

        cycle_model = cycle_model or None
        phase_name = phase_name or None
        phase_focus = phase_focus or None
        load_profile = load_profile or None
        target_event = target_event or None
        goal = goal or None
        energy_level = energy_level or None
        pain_area = pain_area or None
        notes = notes or None
        motivation_level = motivation_level or None

        try:
            cur = mysql.connection.cursor()
            cur.execute("""
                INSERT INTO swim_sessions (
                    user_id, session_date, goal, cycle_model, phase_name, phase_focus,
                    load_profile, target_event, weeks_to_race, energy_level, pain_area, notes,
                    sleep_hours, motivation_level, stiffness_level, shoulder_pain_level
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                session["user_id"],
                session_date,
                goal,
                cycle_model,
                phase_name,
                phase_focus,
                load_profile,
                target_event,
                weeks_to_race,
                energy_level,
                pain_area,
                notes,
                sleep_hours,
                motivation_level,
                stiffness_level,
                shoulder_pain_level
            ))
            mysql.connection.commit()
            cur.close()

            flash("Sessão registrada com sucesso.", "success")
            return redirect(url_for("history"))

        except Exception as e:
            flash(f"Erro ao salvar sessão: {e}", "error")
            return redirect(url_for("new_session"))

    return render_template("new_session.html")


@app.route("/history")
@login_required
def history():
    sessions_data = []

    try:
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT
                s.id,
                s.session_date,
                s.goal,
                s.cycle_model,
                s.phase_name,
                s.phase_focus,
                s.load_profile,
                s.target_event,
                s.weeks_to_race,
                s.energy_level,
                s.pain_area,
                s.notes,
                s.sleep_hours,
                s.motivation_level,
                s.stiffness_level,
                s.shoulder_pain_level,
                COUNT(ss.id) AS sets_count
            FROM swim_sessions s
            LEFT JOIN swim_sets ss ON ss.session_id = s.id
            WHERE s.user_id = %s
            GROUP BY
                s.id, s.session_date, s.goal, s.cycle_model, s.phase_name, s.phase_focus,
                s.load_profile, s.target_event, s.weeks_to_race, s.energy_level, s.pain_area,
                s.notes, s.sleep_hours, s.motivation_level, s.stiffness_level, s.shoulder_pain_level
            ORDER BY s.session_date DESC, s.id DESC
        """, (session["user_id"],))
        sessions_data = cur.fetchall()
        cur.close()

    except Exception as e:
        flash(f"Erro ao carregar histórico: {e}", "error")

    return render_template("history.html", sessions_data=sessions_data)


@app.route("/session/<int:session_id>")
@login_required
def session_detail(session_id):
    swim_session = None
    sets_data = []

    try:
        cur = mysql.connection.cursor()

        cur.execute("""
            SELECT id, session_date, goal, cycle_model, phase_name, phase_focus, load_profile,
                   target_event, weeks_to_race, energy_level, pain_area, notes,
                   sleep_hours, motivation_level, stiffness_level, shoulder_pain_level
            FROM swim_sessions
            WHERE id = %s AND user_id = %s
        """, (session_id, session["user_id"]))
        swim_session = cur.fetchone()

        if not swim_session:
            cur.close()
            flash("Sessão não encontrada.", "error")
            return redirect(url_for("history"))

        cur.execute("""
            SELECT id, stroke, course_type, distance_m, reps, avg_time_seconds, rest_seconds, effort_rpe, notes
            FROM swim_sets
            WHERE session_id = %s
            ORDER BY id ASC
        """, (session_id,))
        sets_data = cur.fetchall()
        cur.close()

        for item in sets_data:
            item["pace_per_100"] = calc_pace_per_100(item["avg_time_seconds"], item["distance_m"])

        total_volume = calc_session_volume(sets_data)
        avg_pace_per_100 = calc_avg_pace_per_100(sets_data)
        avg_rpe = calc_avg_rpe_from_sets(sets_data)
        session_load = calc_session_load(sets_data)
        pace_feedback = detect_pace_drop(sets_data)
        session_summary = generate_session_summary(sets_data)

        pace_labels = [f"Série {index + 1}" for index, _ in enumerate(sets_data)]
        pace_values = [item["pace_per_100"] for item in sets_data]

        pace_tone = get_pace_tone(pace_feedback)
        readiness_tone = get_readiness_tone(
            calculate_readiness_score(
                swim_session["energy_level"],
                swim_session["sleep_hours"],
                swim_session["shoulder_pain_level"],
                swim_session["stiffness_level"]
            )
        )

        return render_template(
            "session_detail.html",
            swim_session=swim_session,
            sets_data=sets_data,
            total_volume=total_volume,
            avg_pace_per_100=avg_pace_per_100,
            avg_rpe=avg_rpe,
            session_load=session_load,
            pace_feedback=pace_feedback,
            session_summary=session_summary,
            pace_labels=pace_labels,
            pace_values=pace_values,
            pace_tone=pace_tone,
            readiness_tone=readiness_tone
        )

    except Exception as e:
        flash(f"Erro ao abrir sessão: {e}", "error")
        return redirect(url_for("history"))


@app.route("/session/<int:session_id>/add-set", methods=["GET", "POST"])
@login_required
def add_set(session_id):
    try:
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT id, session_date, goal
            FROM swim_sessions
            WHERE id = %s AND user_id = %s
        """, (session_id, session["user_id"]))
        swim_session = cur.fetchone()
        cur.close()

        if not swim_session:
            flash("Sessão não encontrada.", "error")
            return redirect(url_for("history"))

    except Exception as e:
        flash(f"Erro ao validar sessão: {e}", "error")
        return redirect(url_for("history"))

    if request.method == "POST":
        stroke = request.form["stroke"].strip()
        course_type = request.form["course_type"].strip()
        distance_m = request.form["distance_m"].strip()
        reps = request.form["reps"].strip()
        avg_time_seconds = request.form["avg_time_seconds"].strip()
        rest_seconds = request.form["rest_seconds"].strip()
        effort_rpe = request.form["effort_rpe"].strip()
        notes = request.form["notes"].strip()

        if not all([stroke, course_type, distance_m, reps, avg_time_seconds, rest_seconds, effort_rpe]):
            flash("Preencha os campos obrigatórios da série.", "error")
            return redirect(url_for("add_set", session_id=session_id))

        try:
            distance_m = int(distance_m)
            reps = int(reps)
            avg_time_seconds = float(avg_time_seconds)
            rest_seconds = int(rest_seconds)
            effort_rpe = int(effort_rpe)

            cur = mysql.connection.cursor()
            cur.execute("""
                INSERT INTO swim_sets (
                    session_id, stroke, course_type, distance_m, reps,
                    avg_time_seconds, rest_seconds, effort_rpe, notes
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                session_id,
                stroke,
                course_type,
                distance_m,
                reps,
                avg_time_seconds,
                rest_seconds,
                effort_rpe,
                notes
            ))
            mysql.connection.commit()
            cur.close()

            flash("Série adicionada com sucesso.", "success")
            return redirect(url_for("session_detail", session_id=session_id))

        except Exception as e:
            flash(f"Erro ao salvar série: {e}", "error")
            return redirect(url_for("add_set", session_id=session_id))

    return render_template("add_set.html", swim_session=swim_session)


@app.route("/session/<int:session_id>/delete", methods=["POST"])
@login_required
def delete_session(session_id):
    try:
        cur = mysql.connection.cursor()
        cur.execute("SELECT id FROM swim_sessions WHERE id = %s AND user_id = %s", (session_id, session["user_id"]))
        owned_session = cur.fetchone()

        if not owned_session:
            cur.close()
            flash("Sessão não encontrada.", "error")
            return redirect(url_for("history"))

        cur.execute("DELETE FROM swim_sessions WHERE id = %s AND user_id = %s", (session_id, session["user_id"]))
        mysql.connection.commit()
        cur.close()

        flash("Sessão apagada com sucesso.", "success")
        return redirect(url_for("history"))

    except Exception as e:
        flash(f"Erro ao apagar sessão: {e}", "error")
        return redirect(url_for("history"))


@app.route("/set/<int:set_id>/delete", methods=["POST"])
@login_required
def delete_set(set_id):
    try:
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT ss.id, ss.session_id
            FROM swim_sets ss
            JOIN swim_sessions s ON s.id = ss.session_id
            WHERE ss.id = %s AND s.user_id = %s
        """, (set_id, session["user_id"]))
        owned_set = cur.fetchone()

        if not owned_set:
            cur.close()
            flash("Série não encontrada.", "error")
            return redirect(url_for("history"))

        session_id = owned_set["session_id"]
        cur.execute("DELETE FROM swim_sets WHERE id = %s", (set_id,))
        mysql.connection.commit()
        cur.close()

        flash("Série apagada com sucesso.", "success")
        return redirect(url_for("session_detail", session_id=session_id))

    except Exception as e:
        flash(f"Erro ao apagar série: {e}", "error")
        return redirect(url_for("history"))


if __name__ == "__main__":
    app.run(debug=True) 