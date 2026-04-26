from collections import Counter


def safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def get_week_status(total_sessions, weekly_goal=3):
    if total_sessions >= weekly_goal:
        return "Meta semanal atingida"
    if total_sessions == 0:
        return "Semana não iniciada"
    return "Semana em progresso"


def get_adherence(total_sessions, weekly_goal=3):
    if weekly_goal <= 0:
        return 0
    percentage = int((total_sessions / weekly_goal) * 100)
    return min(percentage, 100)


def calculate_readiness_score(energy_level, sleep_hours, shoulder_pain_level, stiffness_level):
    score = 70
    energy = (energy_level or "").lower()

    if energy == "alta":
        score += 10
    elif energy == "baixa":
        score -= 10
    elif energy == "muito baixa":
        score -= 20

    sleep = safe_float(sleep_hours, None)
    if sleep is not None:
        if sleep >= 8:
            score += 10
        elif sleep < 6:
            score -= 15

    pain = safe_int(shoulder_pain_level, 0)
    stiffness = safe_int(stiffness_level, 0)

    score -= pain * 3
    score -= stiffness * 2

    return max(0, min(score, 100))


def get_day_mode(score):
    if score >= 80:
        return "Alta performance controlada"
    elif score >= 60:
        return "Treino produtivo com controle"
    elif score >= 40:
        return "Dia de técnica e consistência"
    return "Recuperação ativa"


def get_main_insight(total_sessions, readiness_score=None, pain_area=None):
    if total_sessions == 0:
        return "Comece registrando sua primeira sessão para gerar insights."

    if pain_area and pain_area.lower() not in ["", "nenhuma"]:
        return f"Atenção em {pain_area}: mantenha técnica, controle e progressão conservadora."

    if readiness_score is not None:
        if readiness_score >= 80:
            return "Seu estado atual favorece uma sessão forte, mas com qualidade técnica."
        elif readiness_score >= 60:
            return "Boa prontidão para treinar. Foque em consistência e execução."
        elif readiness_score >= 40:
            return "Hoje pede mais controle do que agressividade."
        else:
            return "Seu estado sugere recuperação ativa ou sessão leve."

    if total_sessions == 1:
        return "Bom começo. Agora vale começar a registrar séries para enriquecer a leitura."
    if total_sessions == 2:
        return "Você está perto da meta semanal. Falta pouco."

    return "Boa consistência semanal. Continue acompanhando volume, recuperação e qualidade."


def calc_pace_per_100(avg_time_seconds, distance_m):
    avg_time_seconds = safe_float(avg_time_seconds, 0.0)
    distance_m = safe_int(distance_m, 0)

    if distance_m <= 0:
        return 0.0

    return round((avg_time_seconds / distance_m) * 100, 2)


def calc_session_volume(swim_sets):
    total = 0
    for item in swim_sets:
        total += safe_int(item.get("distance_m"), 0) * safe_int(item.get("reps"), 0)
    return total


def calc_avg_pace_per_100(swim_sets):
    weighted_sum = 0.0
    total_reps = 0

    for item in swim_sets:
        reps = safe_int(item.get("reps"), 0)
        pace = calc_pace_per_100(item.get("avg_time_seconds"), item.get("distance_m"))
        weighted_sum += pace * reps
        total_reps += reps

    if total_reps == 0:
        return 0.0

    return round(weighted_sum / total_reps, 2)


def calc_avg_rpe_from_sets(swim_sets):
    values = []

    for item in swim_sets:
        values.append(safe_int(item.get("effort_rpe"), 0))

    values = [v for v in values if v > 0]

    if not values:
        return 0.0

    return round(sum(values) / len(values), 1)


def calc_session_load(swim_sets):
    volume = calc_session_volume(swim_sets)
    avg_rpe = calc_avg_rpe_from_sets(swim_sets)
    return round(volume * avg_rpe, 2)


def detect_pace_drop(swim_sets):
    paces = []

    for item in swim_sets:
        pace = calc_pace_per_100(item.get("avg_time_seconds"), item.get("distance_m"))
        if pace > 0:
            paces.append(pace)

    if len(paces) < 2:
        return "Ainda não há séries suficientes para comparar início e fim da sessão."

    mid = len(paces) // 2
    first_half = paces[:mid]
    second_half = paces[mid:]

    if not first_half or not second_half:
        return "Ainda não há séries suficientes para comparar início e fim da sessão."

    first_avg = sum(first_half) / len(first_half)
    second_avg = sum(second_half) / len(second_half)

    if second_avg > first_avg * 1.07:
        return "Queda clara de pace no fim da sessão."
    elif second_avg > first_avg * 1.03:
        return "Leve queda de pace nas séries finais."
    return "Boa consistência de pace ao longo da sessão."


def generate_session_summary(swim_sets):
    if not swim_sets:
        return "Adicione séries para gerar a leitura completa da sessão."

    volume = calc_session_volume(swim_sets)
    avg_rpe = calc_avg_rpe_from_sets(swim_sets)
    pace_msg = detect_pace_drop(swim_sets)

    if volume >= 3000 and avg_rpe >= 8:
        base = "Sessão exigente, com carga alta."
    elif volume >= 2000:
        base = "Sessão sólida, com bom volume de trabalho."
    else:
        base = "Sessão mais enxuta, útil para técnica, controle ou recuperação."

    return f"{base} {pace_msg}"


def format_seconds_as_pace(seconds_value):
    seconds_value = safe_float(seconds_value, 0.0)

    if seconds_value <= 0:
        return "--"

    minutes = int(seconds_value // 60)
    seconds = seconds_value - (minutes * 60)
    rounded_seconds = round(seconds, 1)

    if abs(rounded_seconds - round(rounded_seconds)) < 0.05:
        return f"{minutes}:{int(round(rounded_seconds)):02d}"
    return f"{minutes}:{rounded_seconds:04.1f}"


def get_primary_stroke(swim_sets):
    if not swim_sets:
        return "livre"

    counter = Counter()

    for item in swim_sets:
        stroke = (item.get("stroke") or "livre").lower()
        reps = max(1, safe_int(item.get("reps"), 1))
        counter[stroke] += reps

    if not counter:
        return "livre"

    return counter.most_common(1)[0][0]


def calculate_shoulder_risk(recent_sessions, recent_sets):
    score = 0.0
    shoulder_strokes = {"livre", "costas", "borboleta", "pull"}

    for item in recent_sessions:
        pain_area = (item.get("pain_area") or "").lower()
        shoulder_pain_level = safe_int(item.get("shoulder_pain_level"), 0)
        energy = (item.get("energy_level") or "").lower()

        if pain_area == "ombro":
            score += 5

        score += shoulder_pain_level * 2

        if energy in ["baixa", "muito baixa"]:
            score += 1

    for item in recent_sets:
        stroke = (item.get("stroke") or "").lower()
        reps = min(safe_int(item.get("reps"), 0), 12)
        effort = safe_int(item.get("effort_rpe"), 0)

        if stroke in shoulder_strokes:
            score += (reps * 0.35) + (effort * 0.8)

        if stroke == "borboleta":
            score += 1.5

        if stroke == "costas":
            score += 0.5

    if score >= 30:
        return {
            "label": "alto",
            "tone": "danger",
            "score": round(score, 1),
            "message": "Carga recente sugere cautela para estímulos agressivos de ombro."
        }
    elif score >= 16:
        return {
            "label": "moderado",
            "tone": "warn",
            "score": round(score, 1),
            "message": "Há sinais de acúmulo no ombro. Vale controlar volume e técnica."
        }
    return {
        "label": "baixo",
        "tone": "good",
        "score": round(score, 1),
        "message": "Sem sinais fortes de sobrecarga de ombro no histórico recente."
    }


def format_cycle_model_label(model):
    mapping = {
        "tradicional": "Tradicional",
        "sprint": "Sprint",
        "fundo": "Fundo",
        "college": "College / School",
        "clube": "Clube",
        "personalizado": "Personalizado"
    }
    return mapping.get((model or "").lower(), "Não definido")


def format_phase_focus_label(focus):
    mapping = {
        "tecnica": "Técnica",
        "aerobio": "Aeróbio",
        "forca": "Força específica",
        "velocidade": "Velocidade",
        "ritmo_prova": "Ritmo de prova",
        "recuperacao": "Recuperação",
        "potencia": "Potência",
        "tolerancia": "Tolerância à fadiga",
        "controle": "Controle"
    }
    return mapping.get((focus or "").lower(), "Não definido")


def format_load_profile_label(load_profile):
    mapping = {
        "volume_alto": "Volume alto",
        "volume_moderado": "Volume moderado",
        "volume_baixo": "Volume baixo",
        "intensidade_alta": "Intensidade alta",
        "intensidade_moderada": "Intensidade moderada",
        "intensidade_baixa": "Intensidade baixa",
        "misto": "Misto"
    }
    return mapping.get((load_profile or "").lower(), "Não definido")


def generate_cycle_support(cycle_model, phase_name, phase_focus, load_profile, weeks_to_race, readiness_score, shoulder_risk_label):
    model_label = format_cycle_model_label(cycle_model)
    focus_label = format_phase_focus_label(phase_focus)
    load_label = format_load_profile_label(load_profile)

    phase_display = phase_name or "Fase não definida"
    race_window = safe_int(weeks_to_race, None)

    main_focus = f"Você está usando o modelo {model_label}, na fase “{phase_display}”, com foco em {focus_label.lower()}."
    load_guidance = f"O perfil de carga declarado é {load_label.lower()}."
    risk_point = "Sem alerta específico além da leitura normal do dia."
    coach_note = "O sistema usa esse contexto para não falar uma linguagem genérica de treino."

    if shoulder_risk_label == "alto":
        risk_point = "O ombro está pedindo cautela. Mesmo em fase agressiva, controle técnico vem primeiro."
    elif shoulder_risk_label == "moderado":
        risk_point = "Há acúmulo moderado de carga no ombro. Vale monitorar perda de água e rigidez."

    if readiness_score is not None and readiness_score < 40:
        coach_note = "Sua prontidão está baixa. A fase da temporada importa, mas hoje a prioridade é preservar qualidade."
    elif readiness_score is not None and readiness_score >= 75:
        coach_note = "Sua prontidão ajuda a aproveitar bem a fase atual, desde que o treino continue coerente com o ciclo."

    if race_window is not None:
        if race_window <= 2:
            load_guidance += " Você está perto da competição, então precisão e frescor ganham mais peso."
        elif race_window <= 6:
            load_guidance += " Você já está numa janela onde especificidade e consistência começam a importar mais."
        else:
            load_guidance += " Ainda existe espaço para construir e consolidar trabalho com calma."

    return {
        "main_focus": main_focus,
        "load_guidance": load_guidance,
        "risk_point": risk_point,
        "coach_note": coach_note
    }


def generate_daily_focus(readiness_score, shoulder_risk_label, latest_goal=None, phase_focus=None, load_profile=None):
    goal = (latest_goal or "").lower()
    focus = (phase_focus or "").lower()
    load = (load_profile or "").lower()

    if shoulder_risk_label == "alto":
        return {
            "label": "Controle técnico e proteção",
            "reason": "O radar do ombro pede cautela. Hoje a prioridade é preservar qualidade e não brigar com a água."
        }

    if readiness_score is None:
        return {
            "label": "Construção de base",
            "reason": "Ainda falta histórico suficiente. O melhor é produzir com controle e registrar mais contexto."
        }

    if readiness_score < 40:
        return {
            "label": "Recuperação ativa",
            "reason": "Sua prontidão está baixa. Hoje vale mais sair melhor do que entrou do que tentar forçar estímulo."
        }

    if readiness_score < 60 and focus in ["velocidade", "potencia", "ritmo_prova"]:
        return {
            "label": "Técnica e consistência",
            "reason": "A fase pode pedir mais, mas seu estado atual sugere uma adaptação mais inteligente do estímulo."
        }

    focus_map = {
        "tecnica": ("Técnica e eficiência", "Hoje o sistema favorece refinamento de braçada, alinhamento e economia de nado."),
        "aerobio": ("Sustentação aeróbia", "Bom momento para volume produtivo com estabilidade mecânica."),
        "forca": ("Força específica controlada", "O foco pode ser pressão de nado e sustentação, sem perder desenho técnico."),
        "velocidade": ("Velocidade controlada", "Hoje cabe intensidade, mas com limpeza de execução e sem quebrar padrão."),
        "ritmo_prova": ("Ritmo de prova", "A direção mais coerente é aproximar o corpo do comportamento da prova."),
        "recuperacao": ("Recuperação ativa", "O contexto do ciclo favorece aliviar fadiga e manter boa sensação de água."),
        "potencia": ("Potência e velocidade curta", "Boa janela para estímulos curtos, fortes e tecnicamente limpos."),
        "tolerancia": ("Sustentação sob fadiga", "Hoje faz sentido tolerar desconforto com controle técnico e leitura fina."),
        "controle": ("Treino produtivo com controle", "Boa oportunidade para produzir sem deixar o treino perder forma.")
    }

    if focus in focus_map:
        return {"label": focus_map[focus][0], "reason": focus_map[focus][1]}

    if "veloc" in goal:
        return {
            "label": "Velocidade controlada",
            "reason": "O objetivo recente ainda aponta para uma sessão mais rápida, mas sem abrir mão da qualidade."
        }

    if load == "volume_alto":
        return {
            "label": "Sustentação aeróbia",
            "reason": "Seu perfil de carga atual combina melhor com produção estável e densidade de trabalho."
        }

    if load == "intensidade_alta":
        return {
            "label": "Ritmo de prova",
            "reason": "A carga atual sugere blocos mais específicos e precisos, em vez de volume solto."
        }

    if readiness_score >= 80:
        return {
            "label": "Treino produtivo com controle",
            "reason": "Sua prontidão permite boa produção hoje, mantendo execução coerente."
        }

    return {
        "label": "Técnica e consistência",
        "reason": "Sem um foco explícito claro, o melhor caminho é treinar bem e com padrão."
    }


def suggest_target_pace(swim_sets, focus_label, preferred_stroke):
    if not swim_sets:
        return None

    filtered_sets = [
        item for item in swim_sets
        if (item.get("stroke") or "").lower() == (preferred_stroke or "").lower()
    ]

    target_sets = filtered_sets if filtered_sets else swim_sets
    baseline = calc_avg_pace_per_100(target_sets)

    if baseline <= 0:
        return None

    multipliers = {
        "Velocidade controlada": 0.97,
        "Ritmo de prova": 1.00,
        "Sustentação aeróbia": 1.03,
        "Técnica e eficiência": 1.05,
        "Técnica e consistência": 1.05,
        "Treino produtivo com controle": 1.02,
        "Recuperação ativa": 1.10,
        "Controle técnico e proteção": 1.08,
        "Construção de base": 1.04,
        "Força específica controlada": 1.02,
        "Potência e velocidade curta": 0.96,
        "Sustentação sob fadiga": 1.01,
    }

    multiplier = multipliers.get(focus_label, 1.03)
    target = round(baseline * multiplier, 1)

    return {
        "baseline_per_100": baseline,
        "target_per_100": target,
        "baseline_label": format_seconds_as_pace(baseline),
        "target_label": format_seconds_as_pace(target)
    }


def generate_main_set(focus_label, course_type, primary_stroke, target_pace_label, readiness_score, shoulder_risk_label):
    stroke_label = (primary_stroke or "livre").capitalize()
    course = course_type or "50m"
    pace_text = target_pace_label if target_pace_label else "pace controlado"

    if focus_label == "Velocidade controlada":
        if course == "50m":
            return {
                "title": f"8x100 {stroke_label}",
                "detail": f"Pace alvo {pace_text}/100 · descanso 20s",
                "note": "Segurar técnica nas últimas repetições e evitar quebrar o padrão."
            }
        return {
            "title": f"12x50 {stroke_label}",
            "detail": f"Pace alvo {pace_text}/100 · descanso 15s",
            "note": "Buscar velocidade com boa eficiência de saída e alinhamento."
        }

    if focus_label == "Ritmo de prova":
        return {
            "title": f"3 blocos de 4x100 {stroke_label}",
            "detail": f"Ritmo alvo {pace_text}/100 · descanso 15s · 100 solto entre blocos",
            "note": "Objetivo é manter regularidade de ritmo sem queda brusca no final."
        }

    if focus_label == "Sustentação aeróbia":
        if course == "50m":
            return {
                "title": f"3x400 {stroke_label}",
                "detail": f"Ritmo estável próximo de {pace_text}/100 · descanso 30s",
                "note": "Boa opção para construir resistência sem perder qualidade."
            }
        return {
            "title": f"12x100 {stroke_label}",
            "detail": f"Ritmo estável próximo de {pace_text}/100 · descanso 20s",
            "note": "Volume consistente com foco em economia de nado."
        }

    if focus_label == "Força específica controlada":
        return {
            "title": f"8x50 {stroke_label} forte",
            "detail": "Saída com boa pressão, controle técnico e recuperação suficiente · descanso 25s",
            "note": "Pensar em tração limpa e sustentação, não em força bruta desorganizada."
        }

    if focus_label == "Potência e velocidade curta":
        return {
            "title": f"16x25 {stroke_label}",
            "detail": "Explosão com técnica limpa · descanso 20s",
            "note": "Pouco volume, muita intenção, sem desfigurar a mecânica."
        }

    if focus_label == "Sustentação sob fadiga":
        return {
            "title": f"2 blocos de 6x100 {stroke_label}",
            "detail": f"Ritmo próximo de {pace_text}/100 · descanso 15s",
            "note": "O ponto é sustentar padrão mesmo quando o bloco começar a pesar."
        }

    if focus_label in ["Técnica e eficiência", "Técnica e consistência", "Controle técnico e proteção"]:
        chosen_stroke = "Drill" if shoulder_risk_label == "alto" else stroke_label
        return {
            "title": f"10x50 {chosen_stroke}",
            "detail": "Foco em alinhamento, contagem de braçadas e controle técnico · descanso 20s",
            "note": "Hoje vale priorizar limpeza de movimento acima de agressividade."
        }

    if focus_label == "Recuperação ativa":
        return {
            "title": "8x50 leve + 200 solto",
            "detail": "Alternar drill, perna e nado leve · descanso 20s",
            "note": "Objetivo é circular bem, manter sensação de água e sair melhor do que entrou."
        }

    return {
        "title": f"10x100 {stroke_label}",
        "detail": f"Ritmo controlado próximo de {pace_text}/100 · descanso 20s",
        "note": "Sessão base para produzir com controle e sem forçar demais."
    }


def classify_session_dna(swim_sets, goal=None):
    if not swim_sets:
        return {
            "label": "Sem DNA definido",
            "description": "Ainda não há séries suficientes para classificar a personalidade da sessão."
        }

    volume = calc_session_volume(swim_sets)
    avg_rpe = calc_avg_rpe_from_sets(swim_sets)
    goal_text = (goal or "").lower()

    if "veloc" in goal_text or (avg_rpe >= 8 and volume < 1800):
        return {
            "label": "Explosiva",
            "description": "Sessão com tendência a intensidade alta e estímulo mais agressivo."
        }

    if "téc" in goal_text or avg_rpe <= 5:
        return {
            "label": "Técnica",
            "description": "Sessão com foco maior em eficiência, limpeza de movimento e controle."
        }

    if volume >= 2500 and avg_rpe >= 7:
        return {
            "label": "Sustentada",
            "description": "Sessão densa, com volume relevante e estímulo consistente."
        }

    if volume < 1500 and avg_rpe <= 4:
        return {
            "label": "Regenerativa",
            "description": "Sessão leve, útil para recuperação ativa e sensação de água."
        }

    return {
        "label": "Controle",
        "description": "Sessão equilibrada, sem extremos, boa para construir base com qualidade."
    }