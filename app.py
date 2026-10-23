import json
import os
import time

import streamlit as st
from groq import Groq


def get_client():
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        try:
            key = st.secrets["GROQ_API_KEY"]   # for Streamlit Cloud
        except Exception:
            pass
    if not key:
        st.error("GROQ_API_KEY is not set.")
        st.stop()
    return Groq(api_key=key)


client = get_client()

# Order matters: the first one available is used.
# For the fastest quiz, move "llama-3.1-8b-instant" to the front.
CANDIDATES = ["openai/gpt-oss-20b", "openai/gpt-oss-120b", "llama-3.1-8b-instant"]


def pick_model():
    available = {m.id for m in client.models.list().data}
    for name in CANDIDATES:
        if name in available:
            return name
    st.error("No known model available. Check console.groq.com/docs/models.")
    st.stop()


MODEL = pick_model()

# ---------- Pattern 1: PERSONA ----------
PERSONA = (
    "You are Study Buddy, a friendly and encouraging tutor for college students. "
    "You are realistic about time, explain things simply, never invent facts, "
    "and keep answers concise."
)

# ---------- Pattern 2: FEW-SHOT ----------
PLAN_EXAMPLE_IN = "Topic: Photosynthesis | Days: 2 | Hours/day: 1 | Level: beginner"
PLAN_EXAMPLE_OUT = """**Day 1 (1h)**
- 20 min: Read the overview of light vs. dark reactions
- 30 min: Draw and label a chloroplast
- 10 min: Self-test: what goes in, what comes out?

**Day 2 (1h)**
- 30 min: Practice problems on the Calvin cycle
- 20 min: Explain the whole process aloud without notes
- 10 min: Review mistakes"""

QUIZ_FORMAT = (
    'Respond with ONLY valid JSON, no extra text, in this shape: '
    '{"questions": [{"question": "...", "options": ["A", "B", "C", "D"], '
    '"answer_index": 0, "explanation": "..."}]}. '
    "Rules: the questions array must contain EXACTLY the number of questions requested, "
    "exactly 4 options per question, exactly one correct answer, "
    "and plausible wrong options. "
    "Never use double quotes inside question, option, or explanation text; "
    "use single quotes instead. "
    "Before responding, check that answer_index points to the correct option."
)
QUIZ_EXAMPLE_OUT = json.dumps({"questions": [
    {
        "question": "Where do the light reactions occur?",
        "options": ["Stroma", "Thylakoid membrane", "Nucleus", "Mitochondria"],
        "answer_index": 1,
        "explanation": "Light reactions happen in the thylakoid membranes of the chloroplast."
    },
    {
        "question": "Which molecule is produced by the Calvin cycle?",
        "options": ["Oxygen", "Glucose precursor (G3P)", "ATP", "Water"],
        "answer_index": 1,
        "explanation": "The Calvin cycle uses ATP and NADPH to build G3P, which becomes glucose."
    },
]})


def ask(messages, temperature=0.5, json_mode=False):
    kwargs = {"model": MODEL, "messages": messages, "temperature": temperature}
    if MODEL.startswith("openai/gpt-oss"):
        kwargs["reasoning_effort"] = "low"          # less hidden thinking = faster
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    try:
        resp = client.chat.completions.create(**kwargs)
    except Exception:
        # the model may not support these options, so retry plainly
        kwargs.pop("reasoning_effort", None)
        kwargs.pop("response_format", None)
        resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content


def clean_input(text):
    """Swap double and curly quotes for single quotes before sending to the model."""
    for ch in ['"', "\u201c", "\u201d"]:
        text = text.replace(ch, "'")
    return text.replace("\u2018", "'").replace("\u2019", "'")


def parse_quiz(raw, n):
    """Pull the JSON object out of the reply, validate it, and enforce the count."""
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON found")
    questions = json.loads(raw[start:end + 1], strict=False)["questions"]
    for q in questions:
        if len(q["options"]) < 2 or not (0 <= q["answer_index"] < len(q["options"])):
            raise ValueError("bad question structure")
    if len(questions) < n:
        raise ValueError("too few questions")
    return questions[:n]                              # trim extras


def repair_json(raw):
    """Last resort: ask the model to fix its own broken JSON."""
    fix = [
        {"role": "system", "content": "You fix broken JSON. Output ONLY the corrected JSON object. "
                                      "Replace any double quotes inside string values with single quotes."},
        {"role": "user", "content": raw},
    ]
    return ask(fix, temperature=0, json_mode=True)


st.title("📚 Study Buddy")
st.caption(f"Model: {MODEL}")
tab_plan, tab_quiz = st.tabs(["Study Plan", "Quiz"])

# ---------------- Study plan ----------------
with tab_plan:
    topic = st.text_area("What are you studying?", key="plan_topic", height=160)
    c1, c2, c3 = st.columns(3)
    days = c1.number_input("Days", 1, 30, 3)
    hours = c2.number_input("Hours/day", 0.5, 8.0, 1.0, step=0.5)
    level = c3.selectbox("Level", ["beginner", "intermediate", "advanced"])

    if st.button("Generate plan") and topic:
        user_msg = f"Topic: {topic} | Days: {days} | Hours/day: {hours} | Level: {level}"
        st.session_state.plan_msgs = [
            {"role": "system", "content": PERSONA + " Produce a day-by-day study plan in the same format as the example."},
            {"role": "user", "content": PLAN_EXAMPLE_IN},
            {"role": "assistant", "content": PLAN_EXAMPLE_OUT},
            {"role": "user", "content": user_msg},
        ]
        with st.spinner("Planning..."):
            reply = ask(st.session_state.plan_msgs)
        st.session_state.plan_msgs.append({"role": "assistant", "content": reply})

    if "plan_msgs" in st.session_state:
        st.markdown(st.session_state.plan_msgs[-1]["content"])

        # ---------- Pattern 3: ITERATIVE REFINEMENT ----------
        tweak = st.text_area("Want changes? (e.g. 'make day 2 lighter')", key="tweak", height=100)
        if st.button("Refine plan") and tweak:
            st.session_state.plan_msgs.append({"role": "user", "content": tweak})
            with st.spinner("Revising..."):
                reply = ask(st.session_state.plan_msgs)
            st.session_state.plan_msgs.append({"role": "assistant", "content": reply})
            st.rerun()

# ---------------- Quiz ----------------
with tab_quiz:
    qtopic = st.text_area("Quiz topic", key="quiz_topic", height=140)
    n = st.slider("Number of questions", 3, 10, 5)

    if st.button("Make quiz") and qtopic:
        msgs = [
            {"role": "system", "content": PERSONA + " " + QUIZ_FORMAT},
            {"role": "user", "content": "Topic: Photosynthesis. Make exactly 2 questions."},
            {"role": "assistant", "content": QUIZ_EXAMPLE_OUT},
            {"role": "user", "content": f"Topic: {clean_input(qtopic)}. Make exactly {n} questions."},
        ]
        quiz, raw = None, ""
        t0 = time.time()
        with st.spinner(f"Writing {n} questions..."):
            for attempt in range(2):                  # up to 2 tries
                raw = ask(msgs, temperature=0.3, json_mode=True)
                try:
                    quiz = parse_quiz(raw, n)
                    break
                except json.JSONDecodeError:          # broken JSON: try one repair
                    try:
                        raw = repair_json(raw)
                        quiz = parse_quiz(raw, n)
                        break
                    except (ValueError, KeyError, TypeError):
                        continue
                except (ValueError, KeyError, TypeError):   # wrong count or structure
                    continue
        if quiz:
            # clear old radio selections so a new quiz starts blank
            for k in list(st.session_state.keys()):
                if k.startswith("q") and k[1:].isdigit():
                    del st.session_state[k]
            st.session_state.quiz = quiz
            st.caption(f"Generated {len(quiz)} questions in {time.time() - t0:.1f}s")
        else:
            st.error("Couldn't build a valid quiz. Try fewer questions or simpler wording.")
            with st.expander("Raw model output (for debugging)"):
                st.code(raw)

    if "quiz" in st.session_state:
        answers = {}
        for i, q in enumerate(st.session_state.quiz):
            answers[i] = st.radio(f"{i + 1}. {q['question']}", q["options"],
                                  index=None, key=f"q{i}")
        if st.button("Check answers"):
            score = 0
            for i, q in enumerate(st.session_state.quiz):
                correct = q["options"][q["answer_index"]]
                if answers[i] == correct:
                    score += 1
                    st.success(f"Q{i + 1}: Correct!")
                else:
                    st.error(f"Q{i + 1}: Answer is **{correct}**. {q['explanation']}")
            st.subheader(f"Score: {score}/{len(st.session_state.quiz)}")