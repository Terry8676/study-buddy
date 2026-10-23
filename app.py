import json
import os

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
    '"answer_index": 0, "explanation": "..."}]}'
)
QUIZ_EXAMPLE_OUT = json.dumps({"questions": [{
    "question": "Where do the light reactions occur?",
    "options": ["Stroma", "Thylakoid membrane", "Nucleus", "Mitochondria"],
    "answer_index": 1,
    "explanation": "Light reactions happen in the thylakoid membranes of the chloroplast."
}]})


def ask(messages, temperature=0.5):
    resp = client.chat.completions.create(
        model=MODEL, messages=messages, temperature=temperature
    )
    return resp.choices[0].message.content


st.title("📚 Study Buddy")
tab_plan, tab_quiz = st.tabs(["Study Plan", "Quiz"])

# ---------------- Study plan ----------------
with tab_plan:
    topic = st.text_input("What are you studying?", key="plan_topic")
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
        tweak = st.text_input("Want changes? (e.g. 'make day 2 lighter')", key="tweak")
        if st.button("Refine plan") and tweak:
            st.session_state.plan_msgs.append({"role": "user", "content": tweak})
            with st.spinner("Revising..."):
                reply = ask(st.session_state.plan_msgs)
            st.session_state.plan_msgs.append({"role": "assistant", "content": reply})
            st.rerun()

# ---------------- Quiz ----------------
with tab_quiz:
    qtopic = st.text_input("Quiz topic", key="quiz_topic")
    n = st.slider("Number of questions", 3, 10, 5)

    if st.button("Make quiz") and qtopic:
        msgs = [
            {"role": "system", "content": PERSONA + " " + QUIZ_FORMAT},
            {"role": "user", "content": "Topic: Photosynthesis. Make 1 question."},
            {"role": "assistant", "content": QUIZ_EXAMPLE_OUT},
            {"role": "user", "content": f"Topic: {qtopic}. Make {n} questions."},
        ]
        with st.spinner("Writing questions..."):
            raw = ask(msgs, temperature=0.4)
        try:
            raw = raw.strip().removeprefix("```json").removesuffix("```").strip()
            st.session_state.quiz = json.loads(raw)["questions"]
            st.session_state.checked = False
        except (json.JSONDecodeError, KeyError):
            st.error("The model returned bad JSON. Click 'Make quiz' again.")

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