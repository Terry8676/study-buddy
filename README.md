# Study Buddy

An AI study assistant that builds personalized study plans and generates quizzes.
Built for CS4680 Prompt Engineering using the Groq API.

## Problem
Students often don't know how to organize their study time or test themselves.
Study Buddy turns a topic, a deadline, and available hours into a day-by-day plan,
then quizzes them on it.

## Features
- **Study plan generator:** topic, days, hours/day, and level in, day-by-day plan out
- **Plan refinement:** ask for changes ("make day 2 lighter") and the plan is revised
- **Quiz generator:** multiple-choice questions with scoring and explanations

## Prompt engineering techniques
- **Persona:** a system prompt defines a friendly, realistic tutor
- **Few-shot:** example input/output pairs lock in the plan format and the quiz JSON schema
- **Iterative refinement:** the conversation history is passed back so the model revises its own plan

## Setup
1. `pip install -r requirements.txt`
2. Get a free API key at https://console.groq.com/keys
3. Set it: `export GROQ_API_KEY=your-key-here`
4. Run: `streamlit run app.py`

## Tech
Python, Streamlit, Groq API

## Web URL
https://terry8676-study-buddy-app-8dkxpw.streamlit.app/
